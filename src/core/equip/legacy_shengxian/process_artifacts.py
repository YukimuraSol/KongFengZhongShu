from __future__ import annotations

from typing import Any

from core.equip.piece_identity import append_entry_source_piece, init_entry_source_pieces
from .candidates import get_hp_percent_sub_candidates, get_hp_static_candidates
from .constants import HP_PERCENT_POSITIONS, get_set_type
from .multi_util import has_multi_solution


def process_artifacts(
    json_data: dict[str, Any],
    base_hp: float,
    include_hp_percent: bool,
    avoid_chars: list[str] | None,
    database_settings: dict[int, Any],
) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    """
    与 HolyKeyCalculator.process_artifacts 等价（数据库/合并键/多解标记）。
    """
    artifacts_by_position: dict[str, list[dict]] = {pos: [] for pos in ["flower", "feather", "sand", "cup", "head"]}
    filter_info: dict[str, Any] = {"filtered_chars": set(), "filtered_count": 0}
    avoid_set = set(avoid_chars or [])

    empty_artifacts = {
        pos: {
            "merge_key": "0_0_0_其他",
            "position": pos,
            "star": 0,
            "level": 0,
            "main_type": "empty",
            "main_value": 0,
            "hp_static": 0,
            "hp_static_total": 0,
            "hp_percent_main": 0,
            "set_type": "其他",
            "original_set": "empty",
            "count": 1,
            "full_artifact": None,
            "total_hp_contribution": 0,
            "is_non_contributing": True,
        }
        for pos in ["flower", "feather", "sand", "cup", "head"]
    }

    for position in artifacts_by_position.keys():
        if position not in json_data:
            continue
        for artifact in json_data[position]:
            if artifact.get("omit"):
                continue
            char_name = artifact.get("equip") or artifact.get("equippedCharacter")
            if avoid_set and char_name and char_name in avoid_set:
                filter_info["filtered_chars"].add(char_name)
                filter_info["filtered_count"] += 1
                continue

            main_tag = artifact["mainTag"]
            star = artifact["star"]
            level = artifact["level"]

            if star not in database_settings:
                continue

            if main_tag["name"] == "lifePercentage":
                if not include_hp_percent:
                    continue
                if star not in [5, 4, 3] or position not in HP_PERCENT_POSITIONS:
                    continue
                if database_settings[star]["hp_percent_main"]["mode"] == "none":
                    continue

            total_hp_contribution = 0
            hp_percent_main = 0.0
            hp_static_total = 0

            if main_tag["name"] == "lifePercentage" and position in HP_PERCENT_POSITIONS:
                if star not in [5, 4, 3]:
                    continue
                if not include_hp_percent:
                    continue
                db_mode = database_settings[star]["hp_percent_main"]["mode"]
                if db_mode == "none":
                    continue
                elif db_mode == "custom":
                    db_values = database_settings[star]["hp_percent_main"]["values"]
                    if db_values and level < len(db_values):
                        hp_percent_main = db_values[level]
                    else:
                        hp_percent_main = 0
                elif db_mode == "display":
                    hp_percent_main = main_tag["value"]
                else:
                    hp_percent_main = 0
                total_hp_contribution += hp_percent_main * base_hp

            if main_tag["name"] == "lifeStatic":
                db_mode = database_settings[star].get("hp_main", {}).get("mode", "display")
                if db_mode == "none":
                    continue
                elif db_mode == "custom":
                    db_values = database_settings[star].get("hp_main", {}).get("values", [])
                    if db_values and level < len(db_values):
                        hp_static_main = db_values[level]
                    else:
                        hp_static_main = 0
                elif db_mode == "display":
                    hp_static_main = main_tag["value"]
                else:
                    hp_static_main = 0
            else:
                hp_static_main = 0

            hp_sub_mode = database_settings[star].get("hp_sub", {}).get("mode", "display")
            hp_percent_sub_mode = database_settings[star].get("hp_percent_sub", {}).get("mode", "display")

            has_hp_static_sub = False
            candidates = [0.0]
            has_abnormal_hp = False
            exclude_artifact = False
            for tag in artifact["normalTags"]:
                if tag["name"] == "lifeStatic":
                    if hp_sub_mode == "none":
                        exclude_artifact = True
                        break
                    hp_static_value = tag["value"]
                    if hp_static_value > 2000:
                        has_abnormal_hp = True
                        break
                    candidates = get_hp_static_candidates(hp_static_value, star, database_settings)
                    has_hp_static_sub = True
                    break
            if has_abnormal_hp:
                filter_info["filtered_count"] += 1
                continue
            if exclude_artifact:
                filter_info["filtered_count"] += 1
                continue
            if has_hp_static_sub and not candidates:
                filter_info["filtered_count"] += 1
                continue

            has_hp_percent_sub = False
            hp_percent_sub_candidates: list[float] = []
            for tag in artifact["normalTags"]:
                if tag["name"] == "lifePercentage":
                    if hp_percent_sub_mode == "none":
                        exclude_artifact = True
                        break
                    hp_percent_value = tag["value"]
                    hp_percent_sub_candidates = get_hp_percent_sub_candidates(
                        hp_percent_value, star, database_settings
                    )
                    has_hp_percent_sub = True
                    break
            else:
                hp_percent_sub_candidates = [0.0]

            if exclude_artifact:
                filter_info["filtered_count"] += 1
                continue
            if has_hp_percent_sub and not hp_percent_sub_candidates:
                filter_info["filtered_count"] += 1
                continue

            if has_hp_static_sub and has_hp_percent_sub:
                combined_candidates = [
                    (s, p) for s in candidates for p in hp_percent_sub_candidates
                ]
            elif has_hp_static_sub:
                combined_candidates = [(val, 0.0) for val in candidates]
            elif has_hp_percent_sub:
                combined_candidates = [(0.0, val) for val in hp_percent_sub_candidates]
            else:
                combined_candidates = [(0.0, 0.0)]

            for static_sub, percent_sub in combined_candidates:
                row_total_hp_contribution = 0
                hp_percent_sub_total = percent_sub
                hp_static_total = 0
                if main_tag["name"] == "lifePercentage":
                    row_total_hp_contribution += hp_percent_main * base_hp
                if main_tag["name"] == "lifeStatic":
                    row_total_hp_contribution += hp_static_main
                    hp_static_total += hp_static_main
                hp_static_total += static_sub
                row_total_hp_contribution += static_sub
                row_total_hp_contribution += percent_sub * base_hp

                hp_percent_main_rounded = round(hp_percent_main, 3)
                hp_percent_sub_rounded = round(hp_percent_sub_total, 3)
                key = (
                    f"{int(hp_static_total)}_{int(hp_percent_main_rounded * 1000)}_"
                    f"{int(hp_percent_sub_rounded * 1000)}_{star}_{get_set_type(artifact['setName'])}"
                )

                found = False
                for existing_artifact in artifacts_by_position[position]:
                    if existing_artifact["merge_key"] == key:
                        append_entry_source_piece(existing_artifact, artifact, position)
                        found = True
                        break
                if not found:
                    has_multi = False
                    if has_hp_static_sub and len(candidates) > 1:
                        hp_sub_max_diff = database_settings[star].get("hp_sub", {}).get("max_diff", 0.01)
                        has_multi = has_multi or has_multi_solution(candidates, threshold=hp_sub_max_diff)
                    if has_hp_percent_sub and len(hp_percent_sub_candidates) > 1:
                        hp_percent_sub_max_diff = database_settings[star].get("hp_percent_sub", {}).get(
                            "max_diff", 0.0001
                        )
                        has_multi = has_multi or has_multi_solution(
                            hp_percent_sub_candidates, threshold=hp_percent_sub_max_diff
                        )
                    new_entry = {
                            "merge_key": key,
                            "position": position,
                            "star": star,
                            "level": level,
                            "main_type": main_tag["name"],
                            "main_value": main_tag["value"],
                            "hp_static": static_sub,
                            "hp_static_total": hp_static_total,
                            "hp_percent_main": hp_percent_main,
                            "hp_percent_main_rounded": hp_percent_main_rounded,
                            "hp_percent_sub": hp_percent_sub_total,
                            "hp_percent_sub_rounded": hp_percent_sub_rounded,
                            "set_type": get_set_type(artifact["setName"]),
                            "original_set": artifact["setName"],
                            "count": 1,
                            "full_artifact": artifact,
                            "total_hp_contribution": row_total_hp_contribution,
                            "is_non_contributing": (
                                hp_static_total == 0 and hp_percent_main == 0 and hp_percent_sub_total == 0
                            ),
                            "hp_static_candidates": candidates if has_hp_static_sub else None,
                            "hp_percent_sub_candidates": hp_percent_sub_candidates if has_hp_percent_sub else None,
                            "has_multi_solution": has_multi,
                        }
                    init_entry_source_pieces(new_entry, artifact, position)
                    artifacts_by_position[position].append(new_entry)

    for position in artifacts_by_position.keys():
        artifacts_by_position[position].insert(0, empty_artifacts[position])

    filter_info["filtered_chars"] = list(filter_info["filtered_chars"])
    return artifacts_by_position, filter_info
