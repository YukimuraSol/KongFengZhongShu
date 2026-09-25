"""莫娜式圣遗物卡片展示字段：主词条 + 全部副词条。"""

from __future__ import annotations

from typing import Any

from core.equip.atk_def_bundle import (
    STAT_NAME_CN,
    format_stat_value_for_display,
    normalize_stat_tag_name,
)


def mona_display_line(stat_name_raw: Any, raw_value: Any) -> str:
    mn = normalize_stat_tag_name(stat_name_raw)
    if mn == "其他" or stat_name_raw == "其他":
        return "其他"
    cn = STAT_NAME_CN.get(mn, str(stat_name_raw or "—"))
    val = format_stat_value_for_display(mn, raw_value)
    if val.startswith("+"):
        return f"{cn} {val}"
    return f"{cn} +{val}"


def piece_display_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """从搜索条目提取卡片展示字段，供 API pieces 使用。"""
    is_empty = (
        entry.get("main_type") == "empty"
        or (str(entry.get("original_set") or "").strip().lower() == "empty" and int(entry.get("star") or 0) == 0)
    )
    full = entry.get("full_artifact")
    level = int(entry.get("level") or 0)
    star = int(entry.get("star") or 0)
    main_tag = ""
    sub_tags: list[str] = []

    if isinstance(full, dict):
        level = int(full.get("level") or level or 0)
        star = int(full.get("star") or star or 0)
        main = full.get("mainTag") or {}
        if main:
            main_tag = mona_display_line(main.get("name"), main.get("value"))
        for tag in full.get("normalTags") or []:
            if not isinstance(tag, dict):
                continue
            tn = normalize_stat_tag_name(tag.get("name"))
            sub_tags.append(mona_display_line(tag.get("name"), tag.get("value")))

    return {
        "level": level,
        "star": star,
        "main_tag": main_tag,
        "sub_tags": sub_tags,
        "is_empty": is_empty,
    }


def _active_source_pieces(entry: dict[str, Any], loose_disabled: set[str] | None = None) -> list[dict[str, Any]]:
    source = list(entry.get("source_pieces") or [])
    if not loose_disabled:
        return source
    filtered = [
        sp
        for sp in source
        if str(sp.get("instance_key") or sp.get("piece_key") or "") not in loose_disabled
    ]
    return filtered


def attach_merge_piece_meta(
    piece: dict[str, Any],
    entry: dict[str, Any],
    slot: str,
    merge_line: str,
    *,
    loose_disabled: set[str] | None = None,
) -> dict[str, Any]:
    from core.equip.merged_preview_v2 import preview_piece_from_source

    source = _active_source_pieces(entry, loose_disabled)
    preview_pieces = [preview_piece_from_source(sp, entry, slot) for sp in source] if source else []
    default = source[0] if source else {}
    if default.get("full_artifact"):
        set_name = str((default.get("full_artifact") or {}).get("setName") or entry.get("original_set") or "")
        temp = {**entry, "full_artifact": default["full_artifact"], "original_set": set_name, "count": 1}
        piece.update(piece_display_fields(temp))
        if set_name:
            piece["set_name"] = set_name
    piece.update(
        {
            "merge_key": str(entry.get("merge_key") or ""),
            "merge_line": merge_line,
            "piece_key": str(default.get("piece_key") or ""),
            "instance_key": str(default.get("instance_key") or ""),
            "preview_index": 0,
            "preview_pieces": preview_pieces,
        }
    )
    return piece
