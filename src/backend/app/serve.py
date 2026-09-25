"""
开发/桌面启动：挑选空闲端口并写入运行时文件，供前端与 Tauri 发现 API 基址。
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


def _user_runtime_path() -> Path:
    """与 Tauri `get_api_base` 及前端约定一致的用户级 runtime.json。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "KongfenZhongShu" / "runtime.json"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "KongfenZhongShu" / "runtime.json"
    return Path.home() / ".local" / "share" / "KongfenZhongShu" / "runtime.json"


def _project_runtime_path() -> Path:
    """仓库根下 .kfzs/runtime.json（cwd 应为控分中枢根目录）。"""
    return Path.cwd() / ".kfzs" / "runtime.json"


def pick_free_port(host: str, port_start: int, port_end: int) -> int:
    """从 port_start 起递增尝试 bind，返回第一个可用端口（探测后释放，uvicorn 再正式监听）。"""
    for port in range(port_start, port_end + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 不要用 SO_REUSEADDR：在 Windows 上会与已有监听套接字「并存 bind」，导致误判端口空闲。
        try:
            sock.bind((host, port))
        except OSError:
            continue
        finally:
            sock.close()
        return port
    raise RuntimeError(f"在 {host} 上未找到可用端口（范围 {port_start}-{port_end}）")


def write_runtime_files(api_base: str) -> None:
    """写入用户目录与项目 .kfzs，便于 Tauri / 可选文件读取与人工排查。"""
    payload = {"apiBase": api_base}
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    user_path = _user_runtime_path()
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text(text, encoding="utf-8")

    proj_path = _project_runtime_path()
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    proj_path.write_text(text, encoding="utf-8")


def read_serve_env() -> tuple[str, int, int]:
    host = os.environ.get("KFZS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port_start = int(os.environ.get("KFZS_PORT", "8000"))
    port_end = int(os.environ.get("KFZS_PORT_MAX", "8099"))
    if port_end < port_start:
        port_end = port_start
    return host, port_start, port_end
