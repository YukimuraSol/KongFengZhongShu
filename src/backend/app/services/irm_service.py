"""Irminsul 抓包控制：复用 irminsul_scanner 的 pipe 与 GOOD→mona 转换。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import irm_paths
from .database_service import get_irm_settings

_scanner_root = irm_paths.scanner_root()
_app_dir = _scanner_root / "app"
_PKG = "_irminsul_pkg"


def _load_scanner_module(name: str):
    fq = f"{_PKG}.{name}"
    cached = sys.modules.get(fq)
    if cached is not None:
        return cached
    if _PKG not in sys.modules:
        pkg = importlib.util.module_from_spec(importlib.util.spec_from_loader(_PKG, loader=None))
        pkg.__path__ = [str(_app_dir)]
        sys.modules[_PKG] = pkg
    path = _app_dir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(fq, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 Irminsul 模块: {path}")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = _PKG
    sys.modules[fq] = mod
    spec.loader.exec_module(mod)
    return mod


control_client = _load_scanner_module("control_client")
good_to_mona = _load_scanner_module("good_to_mona")
trash = _load_scanner_module("trash")
convert_file = good_to_mona.convert_file
send_to_recycle_bin = trash.send_to_recycle_bin

_lock = threading.Lock()
_busy = False
_was_items = False
_auto_fired = False
_last_event = ""
_launch_cancel = threading.Event()

# 与 YAS WinError 740 提示对齐：不依赖 ShellExecute/UAC 弹窗
ADMIN_HINT = irm_paths.ADMIN_HINT


class IrmControlError(RuntimeError):
    pass


def windows_is_elevated() -> bool:
    return irm_paths.windows_is_elevated()


def _set_event(msg: str) -> None:
    global _last_event
    _last_event = msg


def _require_admin_for_capture() -> None:
    if sys.platform == "win32" and not windows_is_elevated():
        _set_event(ADMIN_HINT)
        raise IrmControlError(ADMIN_HINT)


def _fmt_time(dt: datetime | None) -> str:
    return dt.strftime("%H:%M:%S") if dt else ""


_capture_started_at: datetime | None = None
_items_at: datetime | None = None


def _apply_timing(capturing: bool, items: bool) -> None:
    global _capture_started_at, _items_at
    now = datetime.now()
    if capturing and _capture_started_at is None:
        _capture_started_at = now
    if not capturing:
        _capture_started_at = None
    if items and _items_at is None:
        _items_at = now
    if not items:
        _items_at = None


def _status_labels(
    *,
    capturing: bool,
    key_ready: bool,
    items: bool,
    packets: int,
    err: str = "",
) -> tuple[str, str, str, bool]:
    """抓包 / 密钥 / 圣遗物文案。密钥以扫描器 Session key 为准（pipe STATUS key=）。"""
    if err:
        capture_detail = f"异常：{err}"
    elif capturing:
        capture_detail = "正在监听"
    else:
        capture_detail = "等待监听"
    if key_ready:
        key_detail = "已获取"
    elif capturing and packets > 0:
        # 有流量但 sniffer 仍无 Session key → 多半错过握手
        key_detail = "未获取"
    else:
        key_detail = "等待获取"
    items_detail = "已获取" if items else "等待获取"
    return capture_detail, key_detail, items_detail, key_ready


def _format_status(st: dict[str, object] | None, *, connected: bool) -> dict[str, Any]:
    elevated = windows_is_elevated()
    if not connected or st is None:
        return {
            "ok": True,
            "connected": False,
            "capturing": False,
            "items": False,
            "key_ok": False,
            "packets": 0,
            "capture_detail": "等待监听",
            "key_detail": "等待获取",
            "items_detail": "等待获取",
            # ponytail: quit_scanner clears _last_event; keep export/launch result after disconnect
            "event": _last_event,
            "elevated": elevated,
            "admin_hint": "" if elevated else ADMIN_HINT,
        }

    capturing = bool(st.get("capturing"))
    items = bool(st.get("items"))
    packets = int(st.get("packets") or 0)
    err = str(st.get("error") or "").strip()
    key_ready = bool(st.get("key"))
    capture_detail, key_detail, items_detail, key_ok = _status_labels(
        capturing=capturing,
        key_ready=key_ready,
        items=items,
        packets=packets,
        err=err,
    )

    return {
        "ok": True,
        "connected": True,
        "capturing": capturing,
        "items": items,
        "key_ok": key_ok,
        "packets": packets,
        "capture_detail": capture_detail,
        "key_detail": key_detail,
        "items_detail": items_detail,
        "event": _last_event,
        "elevated": elevated,
        "admin_hint": "" if elevated else ADMIN_HINT,
    }


def _read_pipe_status() -> dict[str, object]:
    reply = control_client.status(timeout_s=3.0)
    return control_client.parse_status(reply)


def _connected() -> bool:
    try:
        control_client.ping(timeout_s=2.0)
        return True
    except Exception:
        return False


def get_status(runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    global _was_items, _auto_fired
    try:
        st = _read_pipe_status()
        _apply_timing(bool(st.get("capturing")), bool(st.get("items")))
        out = _format_status(st, connected=True)

        cfg = {**get_irm_settings(), **(runtime or {})}
        items = bool(st.get("items"))
        with _lock:
            if (
                items
                and not _was_items
                and bool(cfg.get("auto_stop_export_on_items", True))
                and not _auto_fired
                and not _busy
            ):
                _auto_fired = True
                _set_event("已收到圣遗物，正在停止抓包并导出…")
                threading.Thread(target=_export_worker, args=(dict(cfg), True), daemon=True).start()
            if not items:
                _auto_fired = False
            _was_items = items
        out["event"] = _last_event
        return out
    except Exception:
        with _lock:
            _was_items = False
            _auto_fired = False
        _apply_timing(False, False)
        return _format_status(None, connected=False)


def _finish_busy() -> None:
    global _busy
    with _lock:
        _busy = False


def _try_quit_scanner(*, timeout_s: float = 2.0) -> None:
    try:
        control_client.quit_server(timeout_s=timeout_s)
    except Exception:
        pass


def _launch_cancelled() -> bool:
    return _launch_cancel.is_set()


def _wait_for_scanner_ping(timeout_s: float = 45.0) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _launch_cancelled():
            _try_quit_scanner()
            raise IrmControlError("启动已取消")
        remaining = max(0.25, min(1.0, deadline - time.time()))
        try:
            reply = control_client.ping(timeout_s=remaining)
            if _launch_cancelled():
                _try_quit_scanner()
                raise IrmControlError("启动已取消")
            return reply
        except IrmControlError:
            raise
        except Exception:
            time.sleep(0.25)
    if _launch_cancelled():
        _try_quit_scanner()
        raise IrmControlError("启动已取消")
    raise IrmControlError("连接扫描器超时")


def _launch_worker(cfg: dict[str, Any]) -> None:
    global _auto_fired
    cancelled = False
    try:
        if _launch_cancelled():
            cancelled = True
            return

        scanner = irm_paths.resolve_scanner()
        out = irm_paths.resolve_output(cfg)
        _try_quit_scanner()

        if sys.platform == "win32":
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(["pktmon", "stop"], capture_output=True, creationflags=flags)
                subprocess.run(["pktmon", "filter", "remove"], capture_output=True, creationflags=flags)
            except Exception:
                pass

        if _launch_cancelled():
            cancelled = True
            return

        if not scanner.is_file():
            raise IrmControlError(f"找不到扫描器：{scanner}")
        out.mkdir(parents=True, exist_ok=True)
        _require_admin_for_capture()

        # 已提权：直接拉起，不走 ShellExecute「runas」（低权限机常无 UAC 弹窗却失败）
        cmd = [str(scanner), "--control", f"--export-dir={out}"]
        pop_kw: dict[str, Any] = {"cwd": str(out)}
        if sys.platform == "win32":
            pop_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(cmd, **pop_kw)

        if _launch_cancelled():
            cancelled = True
            _try_quit_scanner()
            return

        reply = _wait_for_scanner_ping(timeout_s=45.0)
        st = _read_pipe_status()
        _apply_timing(bool(st.get("capturing")), bool(st.get("items")))
        with _lock:
            _auto_fired = False
        _set_event(f"扫描器已启动（{reply}）。请完全退出原神后重进。")
    except IrmControlError as exc:
        _apply_timing(False, False)
        with _lock:
            _auto_fired = False
        if str(exc) == "启动已取消":
            cancelled = True
            _set_event("")
        else:
            _set_event(f"启动失败：{exc}" if not str(exc).startswith("抓包需要管理员") else str(exc))
    except Exception as exc:
        _apply_timing(False, False)
        with _lock:
            _auto_fired = False
        if _launch_cancelled():
            cancelled = True
            _try_quit_scanner()
            _set_event("")
        else:
            _set_event(f"启动失败：{exc}")
    finally:
        if cancelled:
            _try_quit_scanner()
        _launch_cancel.clear()
        _finish_busy()


def launch(cfg: dict[str, Any]) -> dict[str, Any]:
    global _busy
    if not irm_paths.bundled_scanner_exists():
        raise IrmControlError(
            f"未找到内置扫描器，请将 {irm_paths.IRM_BUNDLED_EXE} 置于 irminsul_scanner/resources/ 下。"
        )
    _require_admin_for_capture()
    with _lock:
        if _busy:
            return {"ok": True, "message": "操作进行中，请稍候…", "pending": True}
        if _connected():
            st = get_status()
            return {
                "ok": True,
                "message": "扫描器已在运行。",
                "pending": False,
                **{k: st[k] for k in ("connected", "capturing", "items")},
            }
        _launch_cancel.clear()
        _busy = True
    _set_event(f"正在启动扫描器：{irm_paths.resolve_scanner().name}")
    threading.Thread(target=_launch_worker, args=(cfg,), daemon=True).start()
    return {"ok": True, "message": _last_event, "pending": True}


def start_capture() -> dict[str, Any]:
    global _busy
    with _lock:
        if _busy:
            return {"ok": True, "message": "操作进行中，请稍候…"}
        _busy = True
    try:
        reply = control_client.start_capture()
        st = _read_pipe_status()
        _apply_timing(bool(st.get("capturing")), bool(st.get("items")))
        _set_event(f"抓包已恢复：{reply}")
        return {"ok": True, "message": _last_event}
    except Exception as exc:
        _set_event(f"恢复抓包失败：{exc}")
        raise IrmControlError(str(exc)) from exc
    finally:
        _finish_busy()


def stop_capture() -> dict[str, Any]:
    global _busy
    with _lock:
        if _busy:
            return {"ok": True, "message": "操作进行中，请稍候…"}
        _busy = True
    try:
        reply = control_client.stop_capture()
        st = _read_pipe_status()
        _apply_timing(bool(st.get("capturing")), bool(st.get("items")))
        _set_event(f"抓包已暂停：{reply}")
        return {"ok": True, "message": _last_event}
    except Exception as exc:
        _set_event(f"暂停抓包失败：{exc}")
        raise IrmControlError(str(exc)) from exc
    finally:
        _finish_busy()


def toggle_capture(cfg: dict[str, Any]) -> dict[str, Any]:
    global _busy
    connected = _connected()
    if not connected:
        return launch(cfg)
    st = _read_pipe_status()
    capturing = bool(st.get("capturing"))
    if capturing:
        return stop_capture()
    packets = int(st.get("packets") or 0)
    items = bool(st.get("items"))
    # ponytail: pipe START/STOP does not reset GameSniffer; stale session needs full relaunch
    if packets > 0 and not items:
        try:
            control_client.quit_server(timeout_s=5.0)
        except Exception:
            pass
        with _lock:
            if _busy:
                return {"ok": True, "message": "操作进行中，请稍候…", "pending": True}
            _require_admin_for_capture()
            _launch_cancel.clear()
            _busy = True
        _set_event("检测到旧抓包会话，正在重新启动扫描器…")
        threading.Thread(target=_launch_worker, args=(cfg,), daemon=True).start()
        return {"ok": True, "message": _last_event, "pending": True}
    return start_capture()


def _export_worker(cfg: dict[str, Any], auto: bool) -> None:
    global _busy, _auto_fired
    try:
        out = irm_paths.resolve_output(cfg)
        out.mkdir(parents=True, exist_ok=True)
        min_star = int(cfg.get("min_star") or 1)

        if auto:
            try:
                control_client.stop_capture(timeout_s=10.0)
            except Exception as exc:
                _set_event(f"停止抓包失败（继续导出）：{exc}")

        try:
            st = _read_pipe_status()
            _apply_timing(bool(st.get("capturing")), bool(st.get("items")))
            if not st.get("items"):
                _set_event("导出取消：尚未收到圣遗物数据。")
                return
        except Exception:
            pass

        good_path = control_client.export_good(timeout_s=90.0)
        try:
            good = json.loads(Path(good_path).read_text(encoding="utf-8"))
            art_n = len(good.get("artifacts") or [])
        except Exception:
            art_n = -1

        mona_path = out / "mona.json"
        if art_n == 0:
            _set_event(f"导出 GOOD 为 0 件，未覆盖 mona.json；{good_path}")
            return

        info = convert_file(good_path, mona_path, min_star=min_star)
        piece_count = int(info.get("piece_count") or 0)
        msg = f"已转换 mona.json：{piece_count} 件（≥{min_star}★）→ {mona_path}"

        if piece_count > 0:
            try:
                send_to_recycle_bin(good_path)
                msg += "；GOOD 已移入回收站"
            except Exception as exc:
                msg += f"；删除 GOOD 失败（已保留）：{exc}"

        if auto:
            try:
                control_client.quit_server(timeout_s=5.0)
                msg += "；扫描器已退出"
            except Exception:
                pass
            with _lock:
                _was_items = False
                _auto_fired = False
            _apply_timing(False, False)

        _set_event(msg)
    except Exception as exc:
        _set_event(f"导出失败：{exc}")
    finally:
        _finish_busy()


def export_results(cfg: dict[str, Any]) -> dict[str, Any]:
    global _busy
    if not _connected():
        raise IrmControlError("扫描器未启动，请先开始抓包。")

    try:
        st = _read_pipe_status()
    except Exception as exc:
        raise IrmControlError(f"无法读取状态：{exc}") from exc

    if not st.get("items"):
        packets = int(st.get("packets") or 0)
        raise IrmControlError(
            f"尚未收到圣遗物数据（包数={packets}）。请完全退出后重进。"
        )

    with _lock:
        if _busy:
            return {"ok": True, "message": "操作进行中，请稍候…"}
        _busy = True

    _set_event("正在导出…")
    threading.Thread(target=_export_worker, args=(dict(cfg), False), daemon=True).start()
    return {"ok": True, "message": _last_event, "pending": True}


def quit_scanner() -> dict[str, Any]:
    global _was_items, _auto_fired, _busy, _last_event
    _launch_cancel.set()
    _try_quit_scanner(timeout_s=5.0)
    with _lock:
        _was_items = False
        _auto_fired = False
        _busy = False
    _apply_timing(False, False)
    _last_event = ""
    return {"ok": True, "message": "扫描器已退出"}
