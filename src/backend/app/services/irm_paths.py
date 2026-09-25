"""Irminsul 扫描器路径：内置 exe 与默认输出「圣遗物输出」。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

IRM_BUNDLED_EXE = "irminsul_kfzs.exe"

# 与 YAS WinError 740 提示对齐：不依赖 ShellExecute/UAC 弹窗
ADMIN_HINT = (
    "抓包需要管理员权限。请先退出控分中枢，在桌面或开始菜单中对其右键选择"
    "「以管理员身份运行」后再开始抓包。"
)


def windows_is_elevated() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def scanner_root() -> Path:
    """便携包内优先：{控分中枢根}/irminsul_scanner；开发时回退到同级目录。"""
    bundled = project_root() / "irminsul_scanner"
    if (bundled / "app").is_dir() or (bundled / "resources" / IRM_BUNDLED_EXE).is_file():
        return bundled
    return project_root().parent / "irminsul_scanner"


def scanner_bundle_dir() -> Path:
    return scanner_root() / "resources"


def bundled_scanner_path() -> Path:
    return scanner_bundle_dir() / IRM_BUNDLED_EXE


def default_output_dir() -> Path:
    root = project_root()
    new = root / "圣遗物输出"
    old = root / "输出圣遗物文件"
    if not new.exists() and old.is_dir():
        try:
            old.rename(new)
        except OSError:
            pass
    return new


def resolve_scanner() -> Path:
    return bundled_scanner_path().resolve()


def resolve_output(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("output_dir", "") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default_output_dir().resolve()


def bundled_scanner_exists() -> bool:
    return bundled_scanner_path().is_file()


def builtin_meta() -> dict[str, Any]:
    bundled = bundled_scanner_path()
    out_builtin = default_output_dir()
    elevated = windows_is_elevated()
    return {
        "ok": True,
        "bundled_filename": IRM_BUNDLED_EXE,
        "bundled_scanner_path": str(bundled.resolve()),
        "bundled_scanner_exists": bundled.is_file(),
        "builtin_output_dir": str(out_builtin.resolve()),
        "placeholder_output": "使用内置输出目录（圣遗物输出）",
        "elevated": elevated,
        "admin_hint": "" if elevated else ADMIN_HINT,
    }


def reveal_output(cfg: dict[str, Any]) -> None:
    if sys.platform != "win32":
        raise OSError("仅在 Windows 下支持打开资源管理器。")
    path = resolve_output(cfg)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise NotADirectoryError(f"输出路径不是目录: {path}")
    subprocess.run(["explorer", str(path.resolve())], check=False, shell=False)
