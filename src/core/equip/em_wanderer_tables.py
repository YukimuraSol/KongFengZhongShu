"""流浪晚星 v5 精通主/副词条表与多解映射（与参考脚本 EMArtifactMatcher 一致）。"""

from __future__ import annotations

import itertools
from collections import defaultdict

# 参考：参考文件/流浪晚星_v5.py — EMArtifactMatcher.EM_MAIN_TABLE / SUB_TIERS / MAX_UPGRADES / build_multi_map

EM_MAIN_TABLE: dict[int, list[float]] = {
    5: [
        28.00000,
        35.90000,
        43.79999,
        51.79999,
        59.70000,
        67.59999,
        75.5,
        83.5,
        91.40000,
        99.30000,
        107.19999,
        115.19999,
        123.09999,
        131.00000,
        138.89999,
        146.89999,
        154.80000,
        162.699999,
        170.60000,
        178.60000,
        186.50000,
    ],
    4: [
        25.20000,
        32.29999,
        39.40000,
        46.59999,
        53.7000,
        60.79999,
        68.00000,
        75.09999,
        82.19999,
        89.40000,
        96.50000,
        103.5999,
        110.80000,
        117.90000,
        125.00000,
        132.19999,
        139.30000,
    ],
    3: [
        21.00000,
        26.89999,
        32.90000,
        38.79999,
        44.79999,
        50.70000,
        56.70000,
        62.59999,
        68.50000,
        74.5000,
        80.40000,
        86.40000,
        92.3000,
    ],
    2: [16.79999, 21.50000, 26.29999, 31.10000, 36.79999],
    1: [12.60000, 17.29999, 22.10000, 26.89999, 31.60000],
}

SUB_TIERS: dict[int, list[float]] = {
    5: [16.32, 18.65, 20.98, 23.31],
    4: [13.06, 14.92, 16.79, 18.65],
    3: [9.79, 11.19, 12.59, 13.99],
    2: [6.53, 7.93, 9.33],
    1: [4.66, 5.83],
}

MAX_UPGRADES: dict[int, int] = {5: 5, 4: 4, 3: 3, 2: 1, 1: 1}


def get_main_em_from_table(star: int, level: int) -> float:
    """与流浪晚星 get_main_em：精通主按星级+强化等级查表。"""
    table = EM_MAIN_TABLE.get(star)
    if not table:
        return 0.0
    lv = max(0, int(level))
    if lv < len(table):
        return float(table[lv])
    return float(table[-1])


def _build_multi_map() -> dict[int, dict[int, list[float]]]:
    from core.equip.legacy_shengxian.multi_util import (
        SUB_FLAT_EXACT_PLACES,
        SUB_FLAT_MAX_DIFF,
        finalize_exact_candidates,
    )

    result: dict[int, dict[int, list[float]]] = {}
    for star, tiers in SUB_TIERS.items():
        max_up = MAX_UPGRADES[star]
        mapping: dict[int, set[float]] = defaultdict(set)
        for init in tiers:
            for up_count in range(max_up + 1):
                for combo in itertools.product(tiers, repeat=up_count):
                    exact = init + sum(combo)
                    disp = round(exact)
                    mapping[disp].add(exact)
        result[star] = {
            disp: finalize_exact_candidates(vs, SUB_FLAT_MAX_DIFF, SUB_FLAT_EXACT_PLACES)
            for disp, vs in mapping.items()
        }
    return result


_MULTI_MAP = _build_multi_map()


def get_sub_em_candidates(display_value: float, star: int) -> list[float]:
    """与流浪晚星 get_sub_em_candidates：显示值 → 可能精确精通副词条和。"""
    display_int = round(float(display_value))
    candidates = _MULTI_MAP.get(star, {}).get(display_int, [])
    if not candidates:
        return [float(display_value)]
    return list(candidates)
