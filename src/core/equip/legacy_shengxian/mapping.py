from __future__ import annotations

from itertools import combinations_with_replacement

from .constants import MAX_UPGRADES
from .multi_util import (
    SUB_FLAT_EXACT_PLACES,
    SUB_PERCENT_EXACT_PLACES,
    finalize_exact_candidates,
)


def generate_mapping_from_growth_values(
    growth_values: list[float],
    display_precision: float,
    max_diff: float,
    max_upgrades: int,
) -> list[dict]:
    """由成长值生成映射表。

    同一显示值下多个 exact：按原样极差判多解；写入前按游戏精度四舍五入
   （固定 2 位 / 百分比 4 位）。
    """
    all_combinations: set[float] = set()
    for num_upgrades in range(max_upgrades + 1):
        for combo in combinations_with_replacement(growth_values, num_upgrades):
            all_combinations.add(sum(combo))
    sorted_values = sorted(all_combinations)

    if display_precision >= 1:
        decimal_places = 0
        exact_places = SUB_FLAT_EXACT_PLACES
    elif display_precision >= 0.1:
        decimal_places = 1
        exact_places = SUB_FLAT_EXACT_PLACES
    elif display_precision >= 0.01:
        decimal_places = 2
        exact_places = SUB_FLAT_EXACT_PLACES
    elif display_precision >= 0.001:
        decimal_places = 3
        exact_places = SUB_PERCENT_EXACT_PLACES
    else:
        decimal_places = 4
        exact_places = SUB_PERCENT_EXACT_PLACES

    mapping_dict: dict[float, list[float]] = {}
    for exact_value in sorted_values:
        display_value = round(exact_value, decimal_places)
        mapping_dict.setdefault(display_value, []).append(exact_value)

    mapping: list[dict] = []
    for display_value in sorted(mapping_dict.keys()):
        exact_values = list(dict.fromkeys(mapping_dict[display_value]))
        kept = finalize_exact_candidates(exact_values, max_diff, exact_places)
        if len(kept) > 1:
            for exact_value in kept:
                mapping.append(
                    {
                        "enabled": True,
                        "display": display_value,
                        "exact": exact_value,
                        "has_multi": True,
                    }
                )
        else:
            mapping.append(
                {
                    "enabled": True,
                    "display": display_value,
                    "exact": kept[0],
                    "has_multi": False,
                }
            )
    return mapping


def generate_default_sub_stat_mappings(database_settings: dict[int, dict]) -> None:
    """就地填充各星级 hp_sub / hp_percent_sub 的 mapping。"""
    for star in [5, 4, 3, 2, 1]:
        max_upgrades = MAX_UPGRADES.get(star, 5)
        hp_sub_config = database_settings[star].get("hp_sub", {})
        if hp_sub_config.get("mode") == "custom" and "growth_values" in hp_sub_config:
            growth_values = hp_sub_config["growth_values"]
            display_precision = 1.0
            max_diff = 0.01
            mapping = generate_mapping_from_growth_values(
                growth_values, display_precision, max_diff, max_upgrades
            )
            database_settings[star]["hp_sub"]["mapping"] = mapping
            database_settings[star]["hp_sub"]["display_precision"] = display_precision
            database_settings[star]["hp_sub"]["max_diff"] = max_diff
        hp_percent_sub_config = database_settings[star].get("hp_percent_sub", {})
        if hp_percent_sub_config.get("mode") == "custom" and "growth_values" in hp_percent_sub_config:
            growth_values = hp_percent_sub_config["growth_values"]
            display_precision = 0.001
            max_diff = 0.00005
            mapping = generate_mapping_from_growth_values(
                growth_values, display_precision, max_diff, max_upgrades
            )
            database_settings[star]["hp_percent_sub"]["mapping"] = mapping
            database_settings[star]["hp_percent_sub"]["display_precision"] = display_precision
            database_settings[star]["hp_percent_sub"]["max_diff"] = max_diff


if __name__ == "__main__":
    # 候选判多解不 round；写入前精度收口。0.01 边界多解；0.008 单解。
    from .multi_util import has_multi_solution as _has_multi
    from .multi_util import quantize_exact

    assert _has_multi([31.12, 31.13], threshold=0.01)
    assert _has_multi([31.12, 31.130000000000003], threshold=0.01)
    assert not _has_multi([31.134, 31.126], threshold=0.01)  # 极差 0.008
    assert not _has_multi([31.12, 31.125], threshold=0.01)
    assert quantize_exact(31.130000000000003, 2) == 31.13

    m = generate_mapping_from_growth_values(
        [13.62, 15.56, 17.51, 19.45], 1.0, 0.01, 5
    )
    row31 = [r for r in m if r["display"] == 31]
    assert len(row31) >= 2 and all(r["has_multi"] for r in row31), row31
    assert all(r["exact"] == round(r["exact"], 2) for r in row31)
    print("mapping multi + quantize write: ok")
