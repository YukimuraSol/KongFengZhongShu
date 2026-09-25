from dataclasses import dataclass

from core.calc_modes.nearest_target_pair import pick_groups_nearest_target_damage


@dataclass
class EmResult:
    required_em: float
    em_per_damage: float
    note: str


def solve_em_multi_group(
    target_damage: float,
    k_main: float,
    groups: list[tuple[float, float]],
) -> EmResult:
    raw_n = len(groups)
    groups = pick_groups_nearest_target_damage(target_damage, groups)
    n = len(groups)
    sum_x = sum(em for em, _ in groups)
    sum_y = sum(dmg for _, dmg in groups)
    sum_xy = sum(em * dmg for em, dmg in groups)
    sum_x2 = sum(em * em for em, _ in groups)
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-10:
        raise ValueError("数据组精通值过于接近，无法拟合。")
    a = (n * sum_xy - sum_x * sum_y) / denom
    b = (sum_y - a * sum_x) / n
    c = a / k_main
    base_main = b / c
    atk_target = target_damage / c
    required_em = (atk_target - base_main) / k_main
    sensitivity = c * k_main
    em_per_damage = 1 / sensitivity if sensitivity != 0 else 0.0
    note = "多组拟合（邻近目标两组）" if raw_n >= 3 else "多组拟合"
    return EmResult(required_em=required_em, em_per_damage=em_per_damage, note=note)


def solve_em_single_group(
    target_damage: float,
    k_main: float,
    em0: float,
    dmg0: float,
    atk_total0: float,
) -> EmResult:
    c = dmg0 / atk_total0
    base_main = atk_total0 - k_main * em0
    atk_target = target_damage / c
    required_em = (atk_target - base_main) / k_main
    sensitivity = c * k_main
    em_per_damage = 1 / sensitivity if sensitivity != 0 else 0.0
    return EmResult(required_em=required_em, em_per_damage=em_per_damage, note="单组反推")


def solve_em_single_group_with_other(
    target_damage: float,
    k_main: float,
    em0: float,
    dmg0: float,
    atk_total0: float,
    r: float,
    b: float,
) -> EmResult:
    """单组 + 主C有其他倍率介入（对齐流浪晚星：分母 atk_total0×R+B，乘区 M）。"""
    denominator = atk_total0 * r + b
    if abs(denominator) < 1e-10:
        raise ValueError("分母为零：主C面板攻击×倍率R + 基础倍率B 不可为0。")
    m = dmg0 / denominator
    if abs(m) < 1e-10:
        raise ValueError("主C其他乘区 M 过小，请检查面板与伤害输入。")
    t = target_damage / m
    required_em = ((t - b) / r - atk_total0) / k_main + em0
    sensitivity = k_main * r * m
    em_per_damage = 1 / sensitivity if sensitivity != 0 else 0.0
    return EmResult(required_em=required_em, em_per_damage=em_per_damage, note="单组反推（有其他倍率）")
