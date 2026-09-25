from __future__ import annotations

from collections import defaultdict
from itertools import product
from typing import Any


def calculate_set_bonus(artifact_combination: tuple[Any, ...] | list[Any]) -> tuple[float, float, list[str]]:
    set_count: dict[str, int] = defaultdict(int)
    for artifact in artifact_combination:
        if artifact["set_type"] != "其他":
            set_count[artifact["set_type"]] += 1
    hp_percent_bonus = 0.0
    hp_static_bonus = 0.0
    set_effects: list[str] = []
    if set_count.get("千岩套", 0) >= 2:
        hp_percent_bonus += 0.2
        set_effects.append("千岩牢固 2件套: +20%生命值")
    if set_count.get("花海套", 0) >= 2:
        hp_percent_bonus += 0.2
        set_effects.append("花海甘露之光 2件套: +20%生命值")
    if set_count.get("冒险家", 0) >= 2:
        hp_static_bonus += 1000
        set_effects.append("冒险家 2件套: +1000生命值")
    return hp_percent_bonus, hp_static_bonus, set_effects


def calculate_bennett_hp(
    artifact_combination: tuple[Any, ...] | list[Any],
    base_hp: float,
    no_artifact_hp: float,
) -> tuple[float, list[str]]:
    set_hp_percent, set_hp_static, set_effects = calculate_set_bonus(artifact_combination)
    total_static_hp = 0.0
    total_artifact_hp_percent = 0.0
    for artifact in artifact_combination:
        total_static_hp += artifact.get("hp_static_total", 0)
        total_artifact_hp_percent += artifact.get("hp_percent_main", 0)
        total_artifact_hp_percent += artifact.get("hp_percent_sub", 0)
    total_hp_percent = total_artifact_hp_percent + set_hp_percent
    final_hp = no_artifact_hp + total_static_hp + set_hp_static + (base_hp * total_hp_percent)
    return round(final_hp, 2), set_effects


def calculate_all_hp_variants(
    combination: tuple[Any, ...] | list[Any],
    base_hp: float,
    no_artifact_hp: float,
) -> list[float]:
    set_hp_percent, set_hp_static, _ = calculate_set_bonus(combination)
    total_main_static_hp = 0.0
    total_main_hp_percent = 0.0
    static_candidates_list: list[tuple[float, ...]] = []
    hp_percent_candidates_list: list[tuple[float, ...]] = []
    for artifact in combination:
        total_main_static_hp += artifact.get("hp_static_total", 0) - artifact.get("hp_static", 0)
        total_main_hp_percent += artifact.get("hp_percent_main", 0)
        hp_static_candidates = artifact.get("hp_static_candidates")
        if hp_static_candidates and len(hp_static_candidates) > 1:
            static_candidates_list.append(tuple(hp_static_candidates))
        else:
            static_candidates_list.append((artifact.get("hp_static", 0),))
        hp_percent_sub_candidates = artifact.get("hp_percent_sub_candidates")
        if hp_percent_sub_candidates and len(hp_percent_sub_candidates) > 1:
            hp_percent_candidates_list.append(tuple(hp_percent_sub_candidates))
        else:
            hp_percent_candidates_list.append((artifact.get("hp_percent_sub", 0),))
    base_total_hp = no_artifact_hp + total_main_static_hp + set_hp_static
    base_total_percent = total_main_hp_percent + set_hp_percent
    rounded_variants: set[float] = set()
    percent_combos = list(product(*hp_percent_candidates_list))
    for static_combo in product(*static_candidates_list):
        for percent_combo in percent_combos:
            final_hp = base_total_hp + sum(static_combo) + (
                base_hp * (base_total_percent + sum(percent_combo))
            )
            rounded_variants.add(round(final_hp, 2))
    sorted_variants = sorted(rounded_variants)
    if len(sorted_variants) <= 1:
        return sorted_variants
    filtered_variants = [sorted_variants[0]]
    for i in range(1, len(sorted_variants)):
        if sorted_variants[i] - filtered_variants[-1] >= 0.01:
            filtered_variants.append(sorted_variants[i])
    return filtered_variants
