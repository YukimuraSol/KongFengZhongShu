from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

from . import control_client
from .good_to_mona import convert_file
from .settings import (
    load_settings,
    resolve_output,
    resolve_scanner,
    save_settings,
)
from .trash import send_to_recycle_bin

APP_TITLE = "Irminsul 扫描器"
PIPE_NAME = control_client.PIPE_NAME
ADMIN_HINT = (
    "抓包需要管理员权限。请关闭本窗口后，右键「启动Irminsul扫描器.bat」"
    "选择「以管理员身份运行」再打开（不依赖弹窗提权）。"
)

GREEN = "#00ab3f"
RED = "#d93025"
GRAY = "#aaaaaa"
POLL_MS = 1500


def _windows_is_elevated() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class IrminsulScannerApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(APP_TITLE)
        self.root.geometry("720x520")
        self.root.minsize(640, 460)

        self.cfg = load_settings()
        self.scanner_var = ctk.StringVar(value=str(self.cfg.get("scanner_path") or ""))
        self.output_var = ctk.StringVar(value=str(self.cfg.get("output_dir") or ""))
        self.min_star_var = ctk.IntVar(value=int(self.cfg.get("min_star") or 1))
        self._star_menu_var = ctk.StringVar(value=str(self.min_star_var.get()))
        self.delete_good_var = ctk.BooleanVar(
            value=bool(self.cfg.get("delete_good_after_convert", True))
        )
        self.auto_export_var = ctk.BooleanVar(
            value=bool(self.cfg.get("auto_stop_export_on_items", True))
        )

        self._busy = False
        self._server_connected = False
        self._capturing = False
        self._packets = 0
        self._items_ok = False
        self._capture_error = ""
        self._capture_started_at: datetime | None = None
        self._items_at: datetime | None = None
        self._auto_fired = False
        self._last_event = ""

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_poll()
        # 已提权才自动开抓包；未提权等用户点开始时再在日志里写清原因
        if _windows_is_elevated():
            self.root.after(200, self._launch_scanner)
            self._set_event("正在自动启动抓包…")
        else:
            self._set_event("面板就绪")

    def _build_ui(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(outer, text=APP_TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", pady=(0, 12)
        )

        form = ctk.CTkFrame(outer)
        form.pack(fill="x", pady=(0, 10))
        form.grid_columnconfigure(1, weight=1)

        self._path_row(form, 0, "扫描器路径", self.scanner_var, self._pick_scanner)
        self._path_row(form, 1, "输出目录", self.output_var, self._pick_output)

        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(8, 10))
        ctk.CTkLabel(row3, text="最低星级").pack(side="left")

        def _on_star(v: str) -> None:
            self.min_star_var.set(int(v))
            self._star_menu_var.set(v)

        ctk.CTkOptionMenu(
            row3,
            values=["1", "2", "3", "4", "5"],
            variable=self._star_menu_var,
            width=70,
            command=_on_star,
        ).pack(side="left", padx=(8, 16))
        ctk.CTkCheckBox(
            row3,
            text="转换后删除 GOOD（回收站）",
            variable=self.delete_good_var,
        ).pack(side="left", padx=(0, 16))
        ctk.CTkButton(row3, text="保存设置", width=90, command=self._save).pack(side="left")
        ctk.CTkButton(row3, text="导出结果", width=100, command=self._export_results).pack(
            side="right"
        )

        row4 = ctk.CTkFrame(form, fg_color="transparent")
        row4.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkCheckBox(
            row4,
            text="收到圣遗物后自动停止抓包并导出",
            variable=self.auto_export_var,
        ).pack(side="left")

        hint = ctk.CTkLabel(
            outer,
            text="先 ▶ 抓包，再进游戏开背包。自动导出开启时，圣遗物变绿后会停抓包、写出 mona.json 并退出扫描器进程。",
            text_color="#666666",
            anchor="w",
            justify="left",
        )
        hint.pack(fill="x", pady=(0, 8))

        status_frame = ctk.CTkFrame(outer)
        status_frame.pack(fill="both", expand=True)

        cap_hdr = ctk.CTkFrame(status_frame, fg_color="transparent")
        cap_hdr.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            cap_hdr,
            text="抓包状态",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        self._play_btn = ctk.CTkButton(
            cap_hdr,
            text="▶",
            width=44,
            height=36,
            font=ctk.CTkFont(size=20),
            fg_color="#2a7a4b",
            hover_color="#236840",
            command=self._toggle_capture,
        )
        self._play_btn.pack(side="right")

        rows = ctk.CTkFrame(status_frame, fg_color="transparent")
        rows.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        rows.grid_columnconfigure(2, weight=1)

        # Same two signals as original Irminsul capture panel: capturing + Items.
        self._dot_capture = self._status_row(rows, 0, "抓包")
        self._dot_items = self._status_row(rows, 1, "圣遗物")

        self._event_label = ctk.CTkLabel(
            status_frame,
            text=self._last_event,
            anchor="w",
            justify="left",
            text_color="#555555",
            wraplength=640,
        )
        self._event_label.pack(fill="x", padx=12, pady=(0, 10))

        self._refresh_status_ui()

    def _status_row(self, parent, row: int, title: str) -> ctk.CTkLabel:
        dot = ctk.CTkLabel(
            parent,
            text="●",
            width=22,
            font=ctk.CTkFont(size=18),
            text_color=GRAY,
        )
        dot.grid(row=row, column=0, sticky="w", pady=6)
        ctk.CTkLabel(parent, text=title, width=56, anchor="w").grid(
            row=row, column=1, sticky="w", padx=(0, 8), pady=6
        )
        detail = ctk.CTkLabel(parent, text="—", anchor="w", justify="left")
        detail.grid(row=row, column=2, sticky="ew", pady=6)
        setattr(self, f"_detail_{title}", detail)
        return dot

    def _fmt_time(self, dt: datetime | None) -> str:
        return dt.strftime("%H:%M:%S") if dt else ""

    def _set_event(self, msg: str) -> None:
        self._last_event = msg
        self._event_label.configure(text=msg)

    def _refresh_status_ui(self) -> None:
        if not self._server_connected:
            cap_color, cap_text = GRAY, "未启动 — 点 ▶"
        elif self._capture_error:
            cap_color, cap_text = RED, f"异常：{self._capture_error}"
        elif self._capturing:
            cap_color = GREEN
            parts = [f"运行中 · {self._packets} 个包"]
            if self._capture_started_at:
                parts.append(f"自 {self._fmt_time(self._capture_started_at)}")
            cap_text = " · ".join(parts)
        else:
            cap_color, cap_text = RED, "已暂停"

        self._dot_capture.configure(text_color=cap_color)
        self._detail_抓包.configure(text=cap_text)

        if self._items_ok:
            self._dot_items.configure(text_color=GREEN)
            when = self._fmt_time(self._items_at)
            self._detail_圣遗物.configure(
                text=f"已收到 · {when}" if when else "已收到"
            )
        else:
            self._dot_items.configure(text_color=GRAY)
            if not self._capturing:
                item_text = "—"
            elif self._packets > 0:
                # Raw packets without decrypted item cmds → usually missed login keys.
                item_text = "有流量但未解析到背包 — 请完全退出原神后重进并打开圣遗物"
            else:
                item_text = "等待背包数据"
            self._detail_圣遗物.configure(text=item_text)

        if self._busy:
            self._play_btn.configure(state="disabled", text="…")
        elif not self._server_connected:
            self._play_btn.configure(state="normal", text="▶", fg_color="#2a7a4b")
        elif self._capturing:
            self._play_btn.configure(state="normal", text="⏸", fg_color="#b85c00")
        else:
            self._play_btn.configure(state="normal", text="▶", fg_color="#2a7a4b")

    def _apply_status(self, st: dict[str, object]) -> None:
        now = datetime.now()
        capturing = bool(st.get("capturing"))
        if capturing and not self._capturing:
            self._capture_started_at = now
        if not capturing:
            self._capture_started_at = None

        items = bool(st.get("items"))
        was_items = self._items_ok
        if items and not was_items:
            self._items_at = now
        if not items:
            self._items_at = None
            self._auto_fired = False

        self._server_connected = True
        self._capturing = capturing
        self._packets = int(st.get("packets") or 0)
        self._items_ok = items
        self._capture_error = str(st.get("error") or "")
        self._refresh_status_ui()

        if (
            items
            and not was_items
            and bool(self.auto_export_var.get())
            and not self._auto_fired
            and not self._busy
        ):
            self._auto_fired = True
            self._set_event("已收到圣遗物，正在停止抓包并导出…")
            self.root.after(100, self._auto_stop_and_export)

    def _mark_disconnected(self, *, announce: bool = True) -> None:
        if announce and self._server_connected:
            self._set_event("扫描器已断开。")
        self._server_connected = False
        self._capturing = False
        self._packets = 0
        self._items_ok = False
        self._capture_error = ""
        self._capture_started_at = None
        self._items_at = None
        self._auto_fired = False
        self._refresh_status_ui()

    def _schedule_poll(self) -> None:
        self.root.after(POLL_MS, self._poll_status)

    def _poll_status(self) -> None:
        def work() -> None:
            try:
                st = control_client.parse_status(control_client.status(timeout_s=3.0))
                self.root.after(0, lambda: self._apply_status(st))
            except Exception:
                self.root.after(0, self._mark_disconnected)
            finally:
                self.root.after(0, self._schedule_poll)

        threading.Thread(target=work, daemon=True).start()

    def _path_row(self, parent, row: int, label: str, var, browse_cb) -> None:
        ctk.CTkLabel(parent, text=label, width=80, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(10, 8), pady=6
        )
        ctk.CTkEntry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=6)
        ctk.CTkButton(parent, text="浏览", width=70, command=browse_cb).grid(
            row=row, column=2, padx=(8, 10), pady=6
        )

    def _cfg_snapshot(self) -> dict:
        return {
            "scanner_path": self.scanner_var.get().strip(),
            "output_dir": self.output_var.get().strip(),
            "min_star": int(self.min_star_var.get()),
            "delete_good_after_convert": bool(self.delete_good_var.get()),
            "auto_stop_export_on_items": bool(self.auto_export_var.get()),
        }

    def _save(self) -> None:
        self.cfg = save_settings(self._cfg_snapshot())
        self._set_event(
            f"已保存。扫描器={resolve_scanner(self.cfg)} 输出={resolve_output(self.cfg)}"
        )

    def _pick_scanner(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 irminsul_kfzs.exe",
            filetypes=[("可执行文件", "*.exe"), ("全部", "*.*")],
        )
        if path:
            self.scanner_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    def _toggle_capture(self) -> None:
        if self._busy:
            return
        if not self._server_connected:
            self._launch_scanner()
        elif self._capturing:
            self._pipe_stop()
        else:
            self._pipe_start()

    def _launch_scanner(self) -> None:
        if self._busy or self._server_connected:
            return
        if not _windows_is_elevated():
            self._set_event(ADMIN_HINT)
            return
        self._save()
        scanner = resolve_scanner(self.cfg)
        out = resolve_output(self.cfg)
        if not scanner.is_file():
            self._set_event(f"找不到扫描器：{scanner}")
            return
        out.mkdir(parents=True, exist_ok=True)
        self._busy = True
        self._auto_fired = False
        self._refresh_status_ui()
        self._set_event(f"正在启动：{scanner.name}")

        def work() -> None:
            try:
                try:
                    control_client.quit_server(timeout_s=2.0)
                except Exception:
                    pass

                try:
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.run(
                        ["pktmon", "stop"],
                        capture_output=True,
                        creationflags=flags,
                    )
                    subprocess.run(
                        ["pktmon", "filter", "remove"],
                        capture_output=True,
                        creationflags=flags,
                    )
                except Exception:
                    pass

                cmd = [str(scanner), "--control", f"--export-dir={out}"]
                pop_kw: dict = {"cwd": str(out)}
                if sys.platform == "win32":
                    pop_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(cmd, **pop_kw)

                reply = control_client.ping(timeout_s=45.0)
                st = control_client.parse_status(control_client.status())
                self.root.after(
                    0,
                    lambda: (
                        self._apply_status(st),
                        self._set_event(
                            f"扫描器已启动（{reply}）。请完全退出原神后重进，打开背包。"
                        ),
                    ),
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda: (
                        self._mark_disconnected(),
                        self._set_event(f"启动失败：{e}"),
                    ),
                )
            finally:
                self.root.after(0, self._finish_busy)

        threading.Thread(target=work, daemon=True).start()

    def _pipe_start(self) -> None:
        self._busy = True
        self._refresh_status_ui()
        self._set_event("正在恢复抓包…")

        def work() -> None:
            try:
                reply = control_client.start_capture()
                st = control_client.parse_status(control_client.status())
                self.root.after(
                    0,
                    lambda: (
                        self._apply_status(st),
                        self._set_event(f"抓包已恢复：{reply}"),
                    ),
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self._set_event(f"恢复抓包失败：{e}"),
                )
            finally:
                self.root.after(0, self._finish_busy)

        threading.Thread(target=work, daemon=True).start()

    def _pipe_stop(self) -> None:
        self._busy = True
        self._refresh_status_ui()
        self._set_event("正在暂停抓包…")

        def work() -> None:
            try:
                reply = control_client.stop_capture()
                st = control_client.parse_status(control_client.status())
                self.root.after(
                    0,
                    lambda: (
                        self._apply_status(st),
                        self._set_event(f"抓包已暂停：{reply}"),
                    ),
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self._set_event(f"暂停抓包失败：{e}"),
                )
            finally:
                self.root.after(0, self._finish_busy)

        threading.Thread(target=work, daemon=True).start()

    def _finish_busy(self) -> None:
        self._busy = False
        self._refresh_status_ui()

    def _auto_stop_and_export(self) -> None:
        """Stop capture, export mona.json, then quit scanner process."""
        if self._busy:
            return
        if not self._items_ok:
            return
        self._save()
        out = resolve_output(self.cfg)
        out.mkdir(parents=True, exist_ok=True)
        min_star = int(self.min_star_var.get())
        delete_good = bool(self.delete_good_var.get())
        self._busy = True
        self._refresh_status_ui()
        self._set_event("自动流程：停止抓包 → 导出…")

        def work() -> None:
            try:
                try:
                    control_client.stop_capture(timeout_s=10.0)
                except Exception as e:
                    self.root.after(0, lambda: self._set_event(f"停止抓包失败（继续导出）：{e}"))
                st = None
                try:
                    st = control_client.parse_status(control_client.status(timeout_s=15.0))
                    self.root.after(0, lambda: self._apply_status(st))
                except Exception:
                    pass
                if st is not None and not st.get("items"):
                    self.root.after(
                        0,
                        lambda: self._set_event("自动导出取消：STATUS items=false。"),
                    )
                    return
                good_path = control_client.export_good(timeout_s=90.0)
                try:
                    good = json.loads(Path(good_path).read_text(encoding="utf-8"))
                    art_n = len(good.get("artifacts") or [])
                except Exception:
                    art_n = -1
                mona_path = out / "mona.json"
                if art_n == 0:
                    self.root.after(
                        0,
                        lambda: self._set_event(
                            f"自动导出 GOOD 为 0 件，未覆盖 mona.json；{good_path}"
                        ),
                    )
                    return
                info = convert_file(good_path, mona_path, min_star=min_star)
                piece_count = int(info.get("piece_count") or 0)
                msg = f"自动导出完成：{piece_count} 件 → {mona_path}"
                if delete_good and piece_count > 0:
                    try:
                        send_to_recycle_bin(good_path)
                        msg += "；GOOD 已移入回收站"
                    except Exception as e:
                        msg += f"；删除 GOOD 失败：{e}"
                try:
                    control_client.quit_server(timeout_s=5.0)
                    msg += "；扫描器已退出"
                except Exception:
                    pass

                def _done(m: str = msg) -> None:
                    self._mark_disconnected(announce=False)
                    self._set_event(m)

                self.root.after(0, _done)
            except Exception as e:
                self.root.after(0, lambda: self._set_event(f"自动导出失败：{e}"))
            finally:
                self.root.after(0, self._finish_busy)

        threading.Thread(target=work, daemon=True).start()

    def _export_results(self) -> None:
        if self._busy:
            return
        if not self._items_ok:
            self._set_event(
                f"已拦截导出：圣遗物灯未亮（包数={self._packets}）。"
                "请完全退出原神后重进并打开圣遗物背包。"
            )
            return
        self._save()
        out = resolve_output(self.cfg)
        out.mkdir(parents=True, exist_ok=True)
        min_star = int(self.min_star_var.get())
        delete_good = bool(self.delete_good_var.get())
        self._busy = True
        self._refresh_status_ui()
        self._set_event("正在请求 EXPORT…")

        def work() -> None:
            try:
                try:
                    st_before = control_client.parse_status(
                        control_client.status(timeout_s=15.0)
                    )
                    self.root.after(
                        0,
                        lambda: self._set_event(
                            f"导出前：包={st_before['packets']} "
                            f"圣遗物={'是' if st_before['items'] else '否'}"
                        ),
                    )
                    if not st_before.get("items"):
                        self.root.after(
                            0,
                            lambda: self._set_event(
                                "已拦截导出：STATUS items=false。"
                            ),
                        )
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
                    self.root.after(
                        0,
                        lambda: self._set_event(
                            f"导出 GOOD 为 0 件，已保留原 mona.json；{good_path}"
                        ),
                    )
                    return
                info = convert_file(good_path, mona_path, min_star=min_star)
                piece_count = int(info.get("piece_count") or 0)
                msg = f"已转换 mona.json：{piece_count} 件（≥{min_star}★）→ {mona_path}"
                if delete_good and piece_count > 0:
                    try:
                        send_to_recycle_bin(good_path)
                        msg += "；GOOD 已移入回收站"
                    except Exception as e:
                        msg += f"；删除 GOOD 失败（已保留）：{e}"
                self.root.after(0, lambda: self._set_event(msg))
            except Exception as e:
                self.root.after(0, lambda: self._set_event(f"导出失败：{e}"))
            finally:
                self.root.after(0, self._finish_busy)

        threading.Thread(target=work, daemon=True).start()

    def _on_close(self) -> None:
        def cleanup() -> None:
            try:
                if self._server_connected:
                    control_client.quit_server(timeout_s=5.0)
            except Exception:
                pass
            self.root.after(0, self.root.destroy)

        threading.Thread(target=cleanup, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    IrminsulScannerApp().run()
