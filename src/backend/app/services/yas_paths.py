"""YAS 扫描器路径：内置 resources/yas 与默认输出 resources/yas_output。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

# 与 database_service._db_path 一致：backend/app/services -> 控分中枢根为 parents[3]
YAS_BUNDLED_EXE = "yas_artifact_v0.1.28.exe"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def bundled_scanner_path() -> Path:
    return project_root() / "resources" / "yas" / YAS_BUNDLED_EXE


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


def resolve_scanner(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("scanner_path", "") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return bundled_scanner_path().resolve()


def resolve_output(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("output_dir", "") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default_output_dir().resolve()


def bundled_scanner_exists() -> bool:
    p = bundled_scanner_path()
    return p.is_file()


def builtin_meta() -> dict[str, Any]:
    root = project_root()
    bundled = bundled_scanner_path()
    out_builtin = default_output_dir()
    exists = bundled.is_file()
    return {
        "ok": True,
        "bundled_filename": YAS_BUNDLED_EXE,
        "bundled_scanner_path": str(bundled.resolve()),
        "bundled_scanner_exists": exists,
        "builtin_output_dir": str(out_builtin.resolve()),
        "placeholder_scanner": f"使用内置扫描器（{YAS_BUNDLED_EXE}）",
        "placeholder_output": "使用内置输出目录（圣遗物输出）",
    }


def reveal_in_explorer(*, target: Literal["scanner", "output"], cfg: dict[str, Any]) -> None:
    """在资源管理器中显示解析后的路径（Windows）。"""
    if sys.platform != "win32":
        raise OSError("仅在 Windows 下支持打开资源管理器。")

    if target == "scanner":
        # 与输出目录一致：打开扫描器所在文件夹（先确保目录存在），避免 explorer /select 在部分环境下失效
        path = resolve_scanner(cfg)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if not parent.is_dir():
            raise NotADirectoryError(f"扫描器所在目录不可用: {parent}")
        subprocess.run(
            ["explorer", str(parent.resolve())],
            check=False,
            shell=False,
        )
        return

    path = resolve_output(cfg)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise NotADirectoryError(f"输出路径不是目录: {path}")
    subprocess.run(
        ["explorer", str(path.resolve())],
        check=False,
        shell=False,
    )
