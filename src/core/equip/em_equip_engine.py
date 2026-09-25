"""元素精通配装：纯加和模型（无攻防式白值×%），与参考流浪晚星二件套+80 等对齐。"""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from core.equip.piece_identity import append_entry_source_piece, init_entry_source_pieces

from core.equip.legacy_shengxian.display_format import append_set_suffix
from core.equip.em_wanderer_tables import get_main_em_from_table
from core.equip.atk_def_bundle import (
    ALL_STAR_RATINGS,
    POSITION_CN,
    POSITION_ORDER,
    SET_NAME_TRANSLATION,
    STAT_NAME_CN,
    AtkDefEquipEngine,
    format_stat_value_for_display,
    get_set_type,
    has_multi_solution,
    merge_set_segment_for_key,
    normalize_set_name_for_bonus,
    normalize_stat_tag_name,
    round_half_up,
    int_round_half_up,
    sort_combo_by_position_order,
)

# 二件套 +80 元素精通（与参考流浪晚星配装段一致，键为 canonical set id）
SET_TWO_PIECE_EM_80 = frozenset(
    {
        "instructor",
        "GildedDreams",
        "flowerOfParadiseLost",
        "RealmMirrorNight",
        "AubadeOfMorningstarAndMoon",
    }
)

PERCENT_MAIN_POSITIONS = frozenset({"sand", "cup", "head"})
# 与 process_artifacts_for_em 中 combined_totals 离散化一致，避免 merge_key 用整数导致粗粒度去重
EM_FLAT_MERGE_DECIMALS = 2


def calculate_em_set_bonus(combo: tuple[Any, ...]) -> tuple[float, list[str]]:
    """精通向二件套：+80。"""
    cnt: dict[str, int] = defaultdict(int)
    for a in combo:
        sn = str(a.get("original_set") or "")
        if not sn or sn == "empty":
            continue
        cnt[normalize_set_name_for_bonus(sn)] += 1
    bonus = 0.0
    lines: list[str] = []
    for sname, n in cnt.items():
        if n < 2:
            continue
        cn = SET_NAME_TRANSLATION.get(sname, sname)
        if sname in SET_TWO_PIECE_EM_80:
            bonus += 80.0
            lines.append(f"{cn} 二件套: +80 元素精通")
    return bonus, lines


def build_merge_key_em(em_flat: float, star: int, set_name: str) -> str:
    ef = round_half_up(float(em_flat), EM_FLAT_MERGE_DECIMALS)
    seg = merge_set_segment_for_key(set_name)
    return f"em_{ef}_{star}_{seg}"


def format_em_artifact_line(entry: dict[str, Any], show_multi: bool = False, include_set: bool = True) -> str:
    """精通模式展示行：主词条+元素精通副词条。"""
    pos = entry.get("position", "")
    pos_cn = POSITION_CN.get(pos, pos)
    star = int(entry.get("star") or 0)
    if star == 0 and entry.get("main_type") == "empty":
        return f"{pos_cn}:空"
    level = int(entry.get("level") or 0)
    star_str = "★" * star
    orig_set = entry.get("original_set") or ""
    norm_set = normalize_set_name_for_bonus(orig_set) if orig_set else ""
    cn_set = (
        SET_NAME_TRANSLATION.get(orig_set)
        or SET_NAME_TRANSLATION.get(norm_set)
        or (norm_set or orig_set or "空")
    )
    full = entry.get("full_artifact")
    if not full:
        base = f"{pos_cn}: {star_str} {level}级"
        return append_set_suffix(base, cn_set) if include_set else base
    main_tag = full.get("mainTag") or {}
    mn = normalize_stat_tag_name(main_tag.get("name"))
    mv = main_tag.get("value")
    main_cn = STAT_NAME_CN.get(mn, mn if mn else "—")
    if mn == "其他" or (main_tag.get("name") == "其他"):
        main_part = "主词条:其他"
    else:
        main_display = format_stat_value_for_display(mn, mv) if mn else ""
        main_part = f"主词条:{main_cn}+{main_display}" if mn else "主词条:—"
    sub_parts: list[str] = []
    for tag in full.get("normalTags") or []:
        tn = normalize_stat_tag_name(tag.get("name"))
        if tn != "elementalMastery":
            continue
        try:
            v = int_round_half_up(float(tag.get("value") or 0))
        except (TypeError, ValueError):
            v = 0
        suffix = ""
        cands = entry.get("em_flat_candidates") or ()
        if show_multi and isinstance(cands, (list, tuple)) and len(cands) > 1:
            suffix = f"({len(cands)}多解)"
        sub_parts.append(f"+{v}{suffix}")
    sub_line = f"元素精通副词条:{'、'.join(sub_parts)}" if sub_parts else "元素精通副词条:无"
    line = f"{pos_cn}: {star_str} {level}级, {main_part}, {sub_line}"
    return append_set_suffix(line, cn_set) if include_set else line


def process_artifacts_for_em(
    engine: AtkDefEquipEngine,
    json_data: dict[str, Any],
    *,
    allowed_stars: frozenset[int] | None = None,
    include_em_main: bool = True,
    avoid_chars: set[str] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """仅汇总元素精通贡献，用于精通目标枚举。"""
    if allowed_stars is None:
        allowed_stars = ALL_STAR_RATINGS
    filter_info: dict[str, Any] = {"filtered_chars": set(), "filtered_count": 0, "skipped_star_not_in_db": 0}
    artifacts_by_position: dict[str, list[dict[str, Any]]] = {p: [] for p in POSITION_ORDER}

    def empty_entry(pos: str) -> dict[str, Any]:
        return {
            "merge_key": build_merge_key_em(0.0, 0, "empty"),
            "position": pos,
            "star": 0,
            "level": 0,
            "main_type": "empty",
            "count": 1,
            "full_artifact": None,
            "em_flat": 0.0,
            "em_flat_candidates": (0.0,),
            "has_multi_solution": False,
            "original_set": "",
            "set_type": "",
        }

    for p in POSITION_ORDER:
        artifacts_by_position[p].append(empty_entry(p))

    for position in POSITION_ORDER:
        if position not in json_data:
            continue
        for artifact in json_data[position]:
            char_name = artifact.get("equip") or artifact.get("equippedCharacter")
            if avoid_chars and char_name and char_name in avoid_chars:
                filter_info["filtered_chars"].add(char_name)
                filter_info["filtered_count"] += 1
                continue
            star = int(artifact.get("star", 0))
            if star not in allowed_stars:
                continue
            # 精通主/副走流浪晚星表与 builtin 多解，不依赖 database_settings；不因 star 未配置而丢件

            main_tag = artifact.get("mainTag") or {}
            main_name = normalize_stat_tag_name(main_tag.get("name"))
            level = int(artifact.get("level") or 0)
            normal_tags = artifact.get("normalTags") or []
            set_name = normalize_set_name_for_bonus(artifact.get("setName"))

            if main_name == "elementalMastery" and position in PERCENT_MAIN_POSITIONS and not include_em_main:
                continue

            em_main = 0.0
            if main_name == "elementalMastery":
                em_main = get_main_em_from_table(star, level)

            sub_em_groups: list[list[float]] = []
            for tag in normal_tags:
                tn = normalize_stat_tag_name(tag.get("name"))
                if tn != "elementalMastery":
                    continue
                cands = engine.resolve_sub_candidates("elementalMastery", tag.get("value"), star)
                if not cands:
                    try:
                        cands = [float(tag.get("value") or 0)]
                    except (TypeError, ValueError):
                        cands = [0.0]
                sub_em_groups.append([float(x) for x in cands])

            if not sub_em_groups:
                combined_totals = [em_main]
            else:
                combined_totals = []
                for pick in itertools.product(*sub_em_groups):
                    combined_totals.append(em_main + sum(pick))

            seen_keys: set[str] = set()
            for em_flat in sorted(set(round_half_up(x, EM_FLAT_MERGE_DECIMALS) for x in combined_totals)):
                key = build_merge_key_em(em_flat, star, set_name or "")
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                has_multi = bool(sub_em_groups and any(has_multi_solution(tuple(g)) for g in sub_em_groups))
                entry = {
                    "merge_key": key,
                    "position": position,
                    "star": star,
                    "level": level,
                    "main_type": main_name or "",
                    "count": 1,
                    "full_artifact": artifact,
                    "em_flat": float(em_flat),
                    "em_flat_candidates": tuple(combined_totals),
                    "has_multi_solution": has_multi,
                    "original_set": set_name or "",
                    "set_type": get_set_type(set_name),
                }
                dup = False
                for ex in artifacts_by_position[position]:
                    if ex.get("merge_key") == key:
                        append_entry_source_piece(ex, artifact, position)
                        dup = True
                        break
                if not dup:
                    init_entry_source_pieces(entry, artifact, position)
                    artifacts_by_position[position].append(entry)

    filter_info["filtered_chars"] = list(filter_info["filtered_chars"])
    return artifacts_by_position, filter_info


def final_total_em(
    no_artifact_em: float,
    extra_base_em: float,
    combo: tuple[Any, ...],
) -> float:
    piece = sum(float(e.get("em_flat") or 0) for e in combo)
    set_em, _lines = calculate_em_set_bonus(combo)
    return float(no_artifact_em) + float(extra_base_em) + piece + set_em
