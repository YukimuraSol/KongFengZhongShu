"""1～5★ 副词条单次强化档位（精确值）。

来源：Genshin Impact Wiki Artifact/Stats Minor Affix 表（与 ReliquaryAffix
depotId 101/201/301/401/501 公开 dump 一致）。百分比存小数（0.0408=4.08%）。

门禁：5★ 须与 atk_def_bundle.SUB_ROLLS_5 一致；生命固定/精通与 db·流浪晚星一致。
"""
from __future__ import annotations

from typing import Any

# star -> tag -> tuple of single-roll exacts
SUB_ROLLS_BY_STAR: dict[int, dict[str, tuple[float, ...]]] = {
    5: {
        "lifeStatic": (209.13, 239.00, 268.88, 298.75),
        "attackStatic": (13.62, 15.56, 17.51, 19.45),
        "defendStatic": (16.20, 18.52, 20.83, 23.15),
        "lifePercentage": (0.0408, 0.0466, 0.0525, 0.0583),
        "attackPercentage": (0.0408, 0.0466, 0.0525, 0.0583),
        "defendPercentage": (0.0510, 0.0583, 0.0656, 0.0729),
        "elementalMastery": (16.32, 18.65, 20.98, 23.31),
        "chargeEfficiency": (0.0453, 0.0518, 0.0583, 0.0648),
        "critical": (0.0272, 0.0311, 0.0350, 0.0389),
        "criticalDamage": (0.0544, 0.0622, 0.0699, 0.0777),
    },
    4: {
        "lifeStatic": (167.30, 191.20, 215.10, 239.00),
        "attackStatic": (10.89, 12.45, 14.00, 15.56),
        "defendStatic": (12.96, 14.82, 16.67, 18.52),
        "lifePercentage": (0.0326, 0.0373, 0.0420, 0.0466),
        "attackPercentage": (0.0326, 0.0373, 0.0420, 0.0466),
        "defendPercentage": (0.0408, 0.0466, 0.0525, 0.0583),
        "elementalMastery": (13.06, 14.92, 16.79, 18.65),
        "chargeEfficiency": (0.0363, 0.0414, 0.0466, 0.0518),
        "critical": (0.0218, 0.0249, 0.0280, 0.0311),
        "criticalDamage": (0.0435, 0.0497, 0.0560, 0.0622),
    },
    3: {
        "lifeStatic": (100.38, 114.72, 129.06, 143.40),
        "attackStatic": (6.54, 7.47, 8.40, 9.34),
        "defendStatic": (7.78, 8.89, 10.00, 11.11),
        "lifePercentage": (0.0245, 0.0280, 0.0315, 0.0350),
        "attackPercentage": (0.0245, 0.0280, 0.0315, 0.0350),
        "defendPercentage": (0.0306, 0.0350, 0.0393, 0.0437),
        "elementalMastery": (9.79, 11.19, 12.59, 13.99),
        "chargeEfficiency": (0.0272, 0.0311, 0.0350, 0.0389),
        "critical": (0.0163, 0.0186, 0.0210, 0.0233),
        "criticalDamage": (0.0326, 0.0373, 0.0420, 0.0466),
    },
    2: {
        "lifeStatic": (50.19, 60.95, 71.70),
        "attackStatic": (3.27, 3.97, 4.67),
        "defendStatic": (3.89, 4.72, 5.56),
        "lifePercentage": (0.0163, 0.0198, 0.0233),
        "attackPercentage": (0.0163, 0.0198, 0.0233),
        "defendPercentage": (0.0204, 0.0248, 0.0291),
        "elementalMastery": (6.53, 7.93, 9.33),
        "chargeEfficiency": (0.0181, 0.0220, 0.0259),
        "critical": (0.0109, 0.0132, 0.0155),
        "criticalDamage": (0.0218, 0.0264, 0.0311),
    },
    1: {
        "lifeStatic": (23.90, 29.88),
        "attackStatic": (1.56, 1.95),
        "defendStatic": (1.85, 2.31),
        "lifePercentage": (0.0117, 0.0146),
        "attackPercentage": (0.0117, 0.0146),
        "defendPercentage": (0.0146, 0.0182),
        "elementalMastery": (4.66, 5.83),
        "chargeEfficiency": (0.0130, 0.0162),
        "critical": (0.0078, 0.0097),
        "criticalDamage": (0.0155, 0.0194),
    },
}


def rolls_for(star: int, tag: str) -> tuple[float, ...] | None:
    m = SUB_ROLLS_BY_STAR.get(int(star))
    if not m:
        return None
    t = m.get(tag)
    return tuple(t) if t else None


def assert_aligns_with_hub() -> None:
    """最小门禁：与现网 5★ / 生命固定 / 精通表一致。"""
    from core.equip.atk_def_bundle import SUB_ROLLS_5
    from core.equip.em_wanderer_tables import SUB_TIERS
    from core.equip.legacy_shengxian.db import init_default_hp_database

    for tag, tiers in SUB_ROLLS_5.items():
        got = SUB_ROLLS_BY_STAR[5][tag]
        assert len(got) == len(tiers), tag
        for a, b in zip(got, tiers):
            assert abs(a - b) < 1e-9, (tag, a, b)

    db = init_default_hp_database()
    for star in (5, 4, 3, 2, 1):
        gv = db[star]["hp_sub"]["growth_values"]
        got = SUB_ROLLS_BY_STAR[star]["lifeStatic"]
        assert list(got) == list(gv), (star, got, gv)
        em = SUB_TIERS[star]
        got_em = SUB_ROLLS_BY_STAR[star]["elementalMastery"]
        assert list(got_em) == list(em), (star, got_em, em)


if __name__ == "__main__":
    assert_aligns_with_hub()
    print("sub_rolls_by_star align: ok")
