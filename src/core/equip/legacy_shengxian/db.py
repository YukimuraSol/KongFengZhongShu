from __future__ import annotations

import copy
from typing import Any

from .constants import (
    DEF_PERCENT_MAIN_DISPLAY_5STAR,
    DEF_PERCENT_MAIN_STATS_1STAR,
    DEF_PERCENT_MAIN_STATS_2STAR,
    DEF_PERCENT_MAIN_STATS_3STAR,
    DEF_PERCENT_MAIN_STATS_4STAR,
    HP_ATK_PERCENT_MAIN_DISPLAY_5STAR,
    HP_PERCENT_MAIN_STATS_1STAR,
    HP_PERCENT_MAIN_STATS_2STAR,
    HP_PERCENT_MAIN_STATS_3STAR,
    HP_PERCENT_MAIN_STATS_4STAR,
)
from .mapping import generate_default_sub_stat_mappings
from core.equip.sub_rolls_tables import SUB_ROLLS_BY_STAR


def _default_database_settings() -> dict[int, dict[str, Any]]:
    """圣显 __init__ 默认 database_settings（约 1932–1978 行）。"""
    return {
        5: {
            "hp_main": {"mode": "display", "values": []},
            "hp_percent_main": {"mode": "custom", "values": list(HP_ATK_PERCENT_MAIN_DISPLAY_5STAR)},
            "def_percent_main": {"mode": "custom", "values": list(DEF_PERCENT_MAIN_DISPLAY_5STAR)},
            "hp_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[5]["lifeStatic"]),
            },
            "hp_percent_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[5]["lifePercentage"]),
            },
        },
        4: {
            "hp_main": {"mode": "display", "values": []},
            "hp_percent_main": {"mode": "custom", "values": list(HP_PERCENT_MAIN_STATS_4STAR)},
            "def_percent_main": {"mode": "custom", "values": list(DEF_PERCENT_MAIN_STATS_4STAR)},
            "hp_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[4]["lifeStatic"]),
            },
            "hp_percent_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[4]["lifePercentage"]),
            },
        },
        3: {
            "hp_main": {"mode": "display", "values": []},
            "hp_percent_main": {"mode": "custom", "values": list(HP_PERCENT_MAIN_STATS_3STAR)},
            "def_percent_main": {"mode": "custom", "values": list(DEF_PERCENT_MAIN_STATS_3STAR)},
            "hp_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[3]["lifeStatic"]),
            },
            "hp_percent_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[3]["lifePercentage"]),
            },
        },
        2: {
            "hp_main": {"mode": "display", "values": []},
            "hp_percent_main": {"mode": "custom", "values": list(HP_PERCENT_MAIN_STATS_2STAR)},
            "def_percent_main": {"mode": "custom", "values": list(DEF_PERCENT_MAIN_STATS_2STAR)},
            "hp_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[2]["lifeStatic"]),
            },
            "hp_percent_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[2]["lifePercentage"]),
            },
        },
        1: {
            "hp_main": {"mode": "display", "values": []},
            "hp_percent_main": {"mode": "custom", "values": list(HP_PERCENT_MAIN_STATS_1STAR)},
            "def_percent_main": {"mode": "custom", "values": list(DEF_PERCENT_MAIN_STATS_1STAR)},
            "hp_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[1]["lifeStatic"]),
            },
            "hp_percent_sub": {
                "mode": "custom",
                "mapping": [],
                "growth_values": list(SUB_ROLLS_BY_STAR[1]["lifePercentage"]),
            },
        },
    }


def init_default_hp_database() -> dict[int, dict[str, Any]]:
    db = _default_database_settings()
    generate_default_sub_stat_mappings(db)
    return db


def get_merged_hp_database(user_fragment: dict | None) -> dict[int, dict[str, Any]]:
    """
    内置默认 + 用户 database_settings.json 片段合并（按星级浅合并顶层键）。
    """
    db = init_default_hp_database()
    if not user_fragment:
        return db
    for k, v in user_fragment.items():
        sk = int(k) if isinstance(k, str) else k
        if sk not in db or not isinstance(v, dict):
            continue
        merged = copy.deepcopy(db[sk])
        for sub_k, sub_v in v.items():
            if isinstance(sub_v, dict) and isinstance(merged.get(sub_k), dict):
                inner = copy.deepcopy(merged[sub_k])
                inner.update(sub_v)
                merged[sub_k] = inner
            else:
                merged[sub_k] = copy.deepcopy(sub_v)
        db[sk] = merged
    generate_default_sub_stat_mappings(db)
    return db
