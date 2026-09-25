from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_TABLES_JSON = Path(__file__).with_name("_main_tables_extracted.json")

FLOWER_LIFE_5STAR = (
    717.0, 920.0, 1123.0, 1326.0, 1530.0, 1733.0, 1936.0, 2139.0, 2342.0, 2545.0,
    2749.0, 2952.0, 3155.0, 3358.0, 3561.0, 3764.0, 3967.0, 4171.0, 4374.0, 4577.0, 4780.0,
)
FEATHER_ATK_5STAR = (
    47.0, 60.0, 73.0, 86.0, 100.0, 113.0, 126.0, 139.0, 152.0, 166.0,
    179.0, 192.0, 205.0, 219.0, 232.0, 245.0, 258.0, 272.0, 285.0, 298.0, 311.0,
)


@lru_cache(maxsize=1)
def _tables() -> dict[str, dict[str, list[float | None]]]:
    if not _TABLES_JSON.is_file():
        return {}
    return json.loads(_TABLES_JSON.read_text(encoding="utf-8"))


def main_stat_value(mon_name: str, star: int, level: int, slot: str) -> float:
    lv = max(0, min(20, int(level)))
    st = int(star)

    if slot == "flower" and st == 5:
        return float(FLOWER_LIFE_5STAR[lv])
    if slot == "feather" and st == 5:
        return float(FEATHER_ATK_5STAR[lv])

    star_tables = _tables().get(str(st), {})
    seq = star_tables.get(mon_name)
    if seq and lv < len(seq) and seq[lv] is not None:
        return float(seq[lv])

    # 回退：用 5 星表按等级比例（低星少见）
    fallback = _tables().get("5", {}).get(mon_name)
    if fallback and lv < len(fallback) and fallback[lv] is not None:
        return float(fallback[lv])

    raise KeyError(f"无主词条表: {mon_name} star={star} level={level} slot={slot}")
