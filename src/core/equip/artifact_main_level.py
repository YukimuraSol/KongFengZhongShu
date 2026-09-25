"""YAS 三词条圣遗物：level=4 表示 +4 态，主词条按等级表取值。"""

from __future__ import annotations

from core.equip.legacy_shengxian.constants import (
    DEF_PERCENT_MAIN_DISPLAY_5STAR,
    DEF_PERCENT_MAIN_STATS_1STAR,
    DEF_PERCENT_MAIN_STATS_2STAR,
    DEF_PERCENT_MAIN_STATS_3STAR,
    DEF_PERCENT_MAIN_STATS_4STAR,
    HP_ATK_PERCENT_MAIN_DISPLAY_5STAR,
    HP_PERCENT_MAIN_STATS_4STAR,
)

YAS_LEVEL4_ANCHOR = 4
_DISPLAY_MATCH_TOL = 0.15  # 面板 0.1% 容差

HP_ATK_PERCENT_MAIN_TABLES: dict[int, list[float]] = {
    5: list(HP_ATK_PERCENT_MAIN_DISPLAY_5STAR),
    4: list(HP_PERCENT_MAIN_STATS_4STAR),
}

DEF_PERCENT_MAIN_TABLES: dict[int, list[float]] = {
    5: list(DEF_PERCENT_MAIN_DISPLAY_5STAR),
    4: list(DEF_PERCENT_MAIN_STATS_4STAR),
    3: list(DEF_PERCENT_MAIN_STATS_3STAR),
    2: list(DEF_PERCENT_MAIN_STATS_2STAR),
    1: list(DEF_PERCENT_MAIN_STATS_1STAR),
}


def _normalize_main_stat_name(stat_name: str) -> str:
    key = str(stat_name or "").strip()
    aliases = {
        "lifePercentage": "lifePercentage",
        "attackPercentage": "attackPercentage",
        "defendPercentage": "defendPercentage",
        "defensePercentage": "defendPercentage",
    }
    return aliases.get(key, key)


def percent_main_table_for_stat(stat_name: str, star: int) -> list[float] | None:
    name = _normalize_main_stat_name(stat_name)
    if name == "defendPercentage":
        return DEF_PERCENT_MAIN_TABLES.get(int(star))
    if name in ("lifePercentage", "attackPercentage"):
        return HP_ATK_PERCENT_MAIN_TABLES.get(int(star))
    return None


def infer_percent_main_level(stat_name: str, star: int, display_value: float) -> int | None:
    """由面板显示值反推百分比主词条强化等级。"""
    table = percent_main_table_for_stat(stat_name, star)
    if not table:
        return None
    try:
        disp = round(float(display_value) * 100, 1)
    except (TypeError, ValueError):
        return None
    best_idx = None
    best_diff = 1e9
    for idx, panel in enumerate(table):
        diff = abs(round(panel * 100, 1) - disp)
        if diff < best_diff:
            best_diff = diff
            best_idx = idx
    if best_idx is None or best_diff > _DISPLAY_MATCH_TOL:
        return None
    return best_idx


def percent_main_table_value(stat_name: str, star: int, level: int) -> float | None:
    table = percent_main_table_for_stat(stat_name, star)
    if not table:
        return None
    lv = int(level)
    if 0 <= lv < len(table):
        return float(table[lv])
    return None


def yas_level4_main_mismatch(stat_name: str, star: int, level: int, display_value: float) -> bool:
    """
    YAS 将三词条未激活第 4 副的件标为 level=4；主词条面板仍可能是其它等级。
    仅五星且此类「标 4 但主词条不符」需强制按 +4 主词条面板值计。
    """
    if int(star) != 5:
        return False
    if int(level) != YAS_LEVEL4_ANCHOR:
        return False
    inferred = infer_percent_main_level(stat_name, star, display_value)
    return inferred is not None and inferred != YAS_LEVEL4_ANCHOR
