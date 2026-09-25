"""合并条目结构化预览（v2）：含散件列表、去套装展示行。"""

from __future__ import annotations

from typing import Any, Callable

from core.equip.artifact_card_display import piece_display_fields
from core.equip.artifact_meta import enrich_piece_card_fields
from core.equip.piece_identity import entry_piece_keys
from core.equip.set_display_category import append_picker_set_category, two_piece_category_label

_LEGACY_SLOT_ORDER = ["flower", "feather", "sand", "cup", "head"]
_LEGACY_SLOT_TO_UI = {
    "flower": "flower",
    "feather": "plume",
    "sand": "sands",
    "cup": "goblet",
    "head": "circlet",
}


def preview_piece_from_source(
    sp: dict[str, Any],
    entry: dict[str, Any],
    ui_slot: str,
    *,
    format_line: Callable[..., str] | None = None,
    format_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full = sp.get("full_artifact") or {}
    set_name = str(full.get("setName") or entry.get("original_set") or "")
    temp = {**entry, "full_artifact": full, "original_set": set_name, "count": 1}
    fields = piece_display_fields(temp)
    piece: dict[str, Any] = {
        "instance_key": sp.get("instance_key") or sp.get("piece_key") or "",
        "piece_key": sp.get("piece_key") or "",
        "set_name": set_name,
        **fields,
    }
    piece = enrich_piece_card_fields(piece, ui_slot)
    if format_line is not None:
        fmt_kw = format_kwargs or {}
        piece["stat_line_no_set"] = format_line(temp, show_multi=False, include_set=False, **fmt_kw)
        piece["stat_line_with_set"] = format_line(temp, show_multi=False, include_set=True, **fmt_kw)
    return piece


def build_merged_preview_v2_by_slot(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    *,
    format_line: Callable[..., str],
    format_kwargs: dict[str, Any] | None = None,
    target_mode: str = "hp",
) -> dict[str, list[dict[str, Any]]]:
    fmt_kw = format_kwargs or {}
    by_slot: dict[str, list[dict[str, Any]]] = {v: [] for v in _LEGACY_SLOT_TO_UI.values()}
    for legacy_pos in _LEGACY_SLOT_ORDER:
        ui_slot = _LEGACY_SLOT_TO_UI[legacy_pos]
        rows: list[dict[str, Any]] = []
        for art in artifacts_by_position.get(legacy_pos, []):
            if art.get("main_type") == "empty":
                continue
            source_pieces = art.get("source_pieces") or []
            if not source_pieces and art.get("full_artifact"):
                source_pieces = [{"piece_key": "", "instance_key": "", "full_artifact": art.get("full_artifact")}]
            display_line = format_line(art, show_multi=True, include_set=True, **fmt_kw)
            display_line_no_set = format_line(art, show_multi=True, include_set=False, **fmt_kw)
            set_name = str(art.get("original_set") or "")
            set_category = two_piece_category_label(set_name, target=target_mode)
            display_line_picker = append_picker_set_category(
                display_line_no_set,
                set_name,
                target=target_mode,
            )
            preview_pieces = [
                preview_piece_from_source(sp, art, ui_slot, format_line=format_line, format_kwargs=fmt_kw)
                for sp in source_pieces
            ]
            count = int(art.get("count") or len(source_pieces) or 1)
            rows.append(
                {
                    "merge_key": str(art.get("merge_key") or ""),
                    "slot": ui_slot,
                    "count": count,
                    "display_line": display_line,
                    "display_line_no_set": display_line_no_set,
                    "display_line_picker": display_line_picker,
                    "set_category": set_category,
                    "piece_keys": entry_piece_keys(art) if source_pieces else [],
                    "preview_pieces": preview_pieces,
                }
            )
        by_slot[ui_slot] = rows
    return by_slot
