"""Named-pipe client for irminsul_kfzs --control mode."""
from __future__ import annotations

import time
from pathlib import Path

PIPE_NAME = r"\\.\pipe\irminsul_kfzs"


class ControlError(RuntimeError):
    pass


def _open_pipe(timeout_s: float = 30.0):
    """Open Windows named pipe; retry until server is ready."""
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            # Binary mode; we speak line-oriented UTF-8 text.
            return open(PIPE_NAME, "r+b", buffering=0)
        except OSError as e:
            last_err = e
            time.sleep(0.25)
    raise ControlError(f"无法连接命名管道 {PIPE_NAME}: {last_err}")


def send_command(cmd: str, *, timeout_s: float = 30.0) -> str:
    """Send one command, return one reply line (without trailing newline)."""
    pipe = _open_pipe(timeout_s=timeout_s)
    try:
        payload = (cmd.strip() + "\n").encode("utf-8")
        pipe.write(payload)
        # Read until newline
        buf = bytearray()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            chunk = pipe.read(1)
            if not chunk:
                time.sleep(0.05)
                continue
            if chunk == b"\n":
                break
            buf.extend(chunk)
        else:
            raise ControlError(f"等待回复超时: {cmd}")
        return buf.decode("utf-8", errors="replace").strip()
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def ping(timeout_s: float = 30.0) -> str:
    return send_command("PING", timeout_s=timeout_s)


def start_capture(timeout_s: float = 30.0) -> str:
    return send_command("START", timeout_s=timeout_s)


def stop_capture(timeout_s: float = 15.0) -> str:
    return send_command("STOP", timeout_s=timeout_s)


def status(timeout_s: float = 15.0) -> str:
    return send_command("STATUS", timeout_s=timeout_s)


def _as_bool(val: str | None) -> bool:
    # Rust Display for bool is "true"/"false"; accept Python-style too.
    return (val or "").strip().lower() in ("true", "1", "yes")


def parse_status(reply: str) -> dict[str, object]:
    """Parse ``OK STATUS capturing=… packets=… key=… items=… characters=… err=…``."""
    if not reply.startswith("OK STATUS "):
        raise ControlError(reply)
    data: dict[str, str] = {}
    for part in reply[len("OK STATUS ") :].split():
        if "=" in part:
            key, val = part.split("=", 1)
            data[key] = val
    err = data.get("err", "").replace("_", " ")
    return {
        "capturing": _as_bool(data.get("capturing")),
        "packets": int(data.get("packets") or 0),
        "key": _as_bool(data.get("key")),
        "items": _as_bool(data.get("items")),
        "characters": _as_bool(data.get("characters")),
        "error": err,
    }


def export_good(timeout_s: float = 60.0) -> Path:
    reply = send_command("EXPORT", timeout_s=timeout_s)
    if reply.startswith("OK PATH "):
        return Path(reply[len("OK PATH ") :].strip())
    raise ControlError(f"EXPORT 失败: {reply}")


def quit_server(timeout_s: float = 10.0) -> str:
    try:
        return send_command("QUIT", timeout_s=timeout_s)
    except ControlError:
        return "ERR already gone"
