"""内置扫描（YAS / Irm）默认输出目录「圣遗物输出」中的 JSON 列表与安全读取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import yas_paths


DIR_LABEL = "圣遗物输出"


def output_dir() -> Path:
    return yas_paths.default_output_dir().resolve()


def _safe_file(name: str) -> Path:
    """Resolve ``name`` under output dir; reject traversal / escape."""
    raw = (name or "").strip()
    if not raw or "/" in raw or "\\" in raw or raw in (".", ".."):
        raise ValueError("非法文件名")
    root = output_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / raw).resolve()
    if path.parent != root or path.suffix.lower() != ".json":
        raise ValueError("文件不在圣遗物输出目录内")
    return path


def list_export_files() -> dict[str, Any]:
    root = output_dir()
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for p in root.glob("*.json"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        files.append(
            {
                "name": p.name,
                "path": str(p),
                "mtime": st.st_mtime,
                "size": st.st_size,
            }
        )
    # mona.json（Irm 常用）优先，其余按修改时间新→旧
    files.sort(
        key=lambda f: (0 if f["name"].lower() == "mona.json" else 1, -float(f["mtime"]))
    )
    return {
        "ok": True,
        "dir": str(root),
        "dir_label": DIR_LABEL,
        "files": files,
    }


def load_export_json(name: str) -> dict[str, Any]:
    path = _safe_file(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("圣遗物 JSON 根节点须为对象")
    return {
        "ok": True,
        "name": path.name,
        "path": str(path),
        "dir_label": DIR_LABEL,
        "artifact_json": data,
    }
