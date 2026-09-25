"""圣遗物禁用过滤：整条条目 + 散件锁。"""

from __future__ import annotations

import copy
from typing import Any, Callable

from core.equip.piece_identity import entry_piece_keys


def count_loose_disabled(entry: dict[str, Any], loose_set: set[str]) -> int:
    if not loose_set:
        return 0
    keys = entry_piece_keys(entry)
    if keys:
        return sum(1 for k in keys if k in loose_set)
    return 0


def _filter_source_pieces(entry: dict[str, Any], loose_set: set[str]) -> list[dict[str, Any]]:
    if not loose_set:
        return list(entry.get("source_pieces") or [])
    return [
        p
        for p in (entry.get("source_pieces") or [])
        if str(p.get("instance_key") or p.get("piece_key") or "") not in loose_set
    ]


def apply_disable_filter_to_entries(
    arts: list[dict[str, Any]],
    *,
    merged_lines: set[str],
    loose_set: set[str],
    format_line: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for art in arts:
        if art.get("main_type") == "empty":
            kept.append(art)
            continue
        line = format_line(art)
        if line in merged_lines:
            continue
        disabled_n = count_loose_disabled(art, loose_set)
        total = int(art.get("count") or len(art.get("source_pieces") or []) or 1)
        effective = total - disabled_n
        if effective <= 0:
            continue
        if effective < total or disabled_n > 0:
            clone = copy.deepcopy(art)
            pieces = _filter_source_pieces(clone, loose_set)
            if pieces:
                clone["source_pieces"] = pieces
                clone["count"] = len(pieces)
            else:
                clone["count"] = effective
            kept.append(clone)
        else:
            kept.append(art)
    return kept


def filter_artifacts_by_disable(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    *,
    disabled_artifacts: list[str] | None,
    disabled_loose_pieces: list[str] | None,
    format_line: Callable[[dict[str, Any]], str],
) -> dict[str, list[dict[str, Any]]]:
    merged = {str(x).strip() for x in (disabled_artifacts or []) if str(x).strip()}
    loose = {str(x).strip() for x in (disabled_loose_pieces or []) if str(x).strip()}
    if not merged and not loose:
        return artifacts_by_position

    out: dict[str, list[dict[str, Any]]] = {}
    for pos, lst in artifacts_by_position.items():
        kept = apply_disable_filter_to_entries(
            lst,
            merged_lines=merged,
            loose_set=loose,
            format_line=format_line,
        )
        out[pos] = kept if kept else list(lst)
    return out
