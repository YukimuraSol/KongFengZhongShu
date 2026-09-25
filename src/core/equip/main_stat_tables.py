"""5★ 花/羽固定主词条精确等级表（禁止线性插值）。

来源：B站 Wiki「圣遗物全等级主词条的具体属性数值」
https://wiki.biligame.com/ys/圣遗物全等级主词条的具体属性数值

JSON / 参考库使用面板整数（与 Wiki 表一致）。
"""

from __future__ import annotations

# 生之花 · 数值生命 · 5★ · 等级 0～20
FLOWER_LIFE_MAIN_DISPLAY_5STAR: tuple[float, ...] = (
    717.0,
    920.0,
    1123.0,
    1326.0,
    1530.0,
    1733.0,
    1936.0,
    2139.0,
    2342.0,
    2545.0,
    2749.0,
    2952.0,
    3155.0,
    3358.0,
    3561.0,
    3764.0,
    3967.0,
    4171.0,
    4374.0,
    4577.0,
    4780.0,
)

# 死之羽 · 数值攻击 · 5★ · 等级 0～20
FEATHER_ATTACK_MAIN_DISPLAY_5STAR: tuple[float, ...] = (
    47.0,
    60.0,
    73.0,
    86.0,
    100.0,
    113.0,
    126.0,
    139.0,
    152.0,
    166.0,
    179.0,
    192.0,
    205.0,
    219.0,
    232.0,
    245.0,
    258.0,
    272.0,
    285.0,
    298.0,
    311.0,
)

MAIN_LEVELS_5STAR = len(FLOWER_LIFE_MAIN_DISPLAY_5STAR) - 1


def flower_life_main_5star(level: int) -> float:
    if level < 0 or level > MAIN_LEVELS_5STAR:
        raise IndexError(f"5★ 花生命主词条等级越界: {level}（有效 0～{MAIN_LEVELS_5STAR}）")
    return float(FLOWER_LIFE_MAIN_DISPLAY_5STAR[level])


def feather_attack_main_5star(level: int) -> float:
    if level < 0 or level > MAIN_LEVELS_5STAR:
        raise IndexError(f"5★ 羽攻击主词条等级越界: {level}（有效 0～{MAIN_LEVELS_5STAR}）")
    return float(FEATHER_ATTACK_MAIN_DISPLAY_5STAR[level])


# 生命/防御/精通库中羽位 0 级载体：与游戏 +0 羽攻击主一致（原错误常量 63 已废弃）
FEATHER_MAIN_CARRIER_5STAR = feather_attack_main_5star(0)

# 花 0 级载体（副词条参考件主词条固定为 +0 花生命）
FLOWER_MAIN_CARRIER_5STAR = flower_life_main_5star(0)
