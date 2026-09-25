"""
启动入口：python -m backend.app [--reload]

--reload 时通过子进程调用 uvicorn，避免 reload 子进程重复执行本模块导致改端口。
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from .serve import pick_free_port, read_serve_env, write_runtime_files


def main() -> None:
    parser = argparse.ArgumentParser(description="控分中枢 API（自适应端口）")
    parser.add_argument("--reload", action="store_true", help="开发热重载（子进程 uvicorn）")
    args = parser.parse_args()

    host, port_start, port_end = read_serve_env()
    port = pick_free_port(host, port_start, port_end)
    api_base = f"http://{host}:{port}"
    write_runtime_files(api_base)
    print(f"[KFZS] API 监听 {api_base}（runtime 已写入用户目录与 .kfzs/）", flush=True)

    if args.reload:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--reload",
        ]
        raise SystemExit(subprocess.call(cmd))

    import uvicorn  # noqa: PLC0415 — 仅在非 reload 路径按需导入

    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
