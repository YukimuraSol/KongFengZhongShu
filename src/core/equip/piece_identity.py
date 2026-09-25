"""圣遗物散件稳定标识：合并条目内每件实物可单独禁用/刷新。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize_tag(tag: dict[str, Any]) -> dict[str, Any]:
    return {"name": str(tag.get("name") or ""), "value": tag.get("value")}


def build_piece_key(artifact: dict[str, Any], position: str = "") -> str:
    """对原始 JSON 圣遗物计算稳定 hash（同内容跨会话一致）。"""
    pos = position or str(artifact.get("position") or "")
    main = artifact.get("mainTag") or {}
    tags = sorted(
        [_normalize_tag(t) for t in (artifact.get("normalTags") or []) if isinstance(t, dict)],
        key=lambda x: (x["name"], str(x.get("value"))),
    )
    payload = {
        "position": pos,
        "star": int(artifact.get("star") or 0),
        "level": int(artifact.get("level") or 0),
        "setName": str(artifact.get("setName") or ""),
        "mainTag": _normalize_tag(main if isinstance(main, dict) else {}),
        "normalTags": tags,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def make_source_piece(artifact: dict[str, Any], position: str, instance_index: int) -> dict[str, Any]:
    pk = build_piece_key(artifact, position)
    return {
        "piece_key": pk,
        "instance_key": f"{pk}:{instance_index}",
        "full_artifact": artifact,
    }


def init_entry_source_pieces(entry: dict[str, Any], artifact: dict[str, Any], position: str) -> None:
    entry["source_pieces"] = [make_source_piece(artifact, position, 0)]


def append_entry_source_piece(entry: dict[str, Any], artifact: dict[str, Any], position: str) -> None:
    pieces: list[dict[str, Any]] = entry.setdefault("source_pieces", [])
    idx = len(pieces)
    pieces.append(make_source_piece(artifact, position, idx))
    entry["count"] = len(pieces)


def entry_piece_keys(entry: dict[str, Any]) -> list[str]:
    return [str(p.get("instance_key") or p.get("piece_key") or "") for p in entry.get("source_pieces") or []]


def entry_piece_key_set(entry: dict[str, Any]) -> set[str]:
    return {k for k in entry_piece_keys(entry) if k}
