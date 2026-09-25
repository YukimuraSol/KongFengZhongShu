import math
from dataclasses import dataclass

from core.calc_modes.nearest_target_pair import pick_groups_nearest_target_damage


@dataclass
class HpResult:
    required_hp: float
    hp_per_damage: float
    note: str


def solve_hp_normal(
    target_damage: float,
    r: float,
    hp: float,
    dmg: float,
    em: float,
    global_bonus_percent: float = 0.0,
) -> HpResult:
    global_bonus = global_bonus_percent / 100.0
    base_em = em - r * hp
    f_current = 2.78 * em / (em + 1400)
    k = dmg / (1 + global_bonus + f_current)
    em_low, em_high = 0.0, 10000.0
    em_mid = em
    for _ in range(100):
        em_mid = (em_low + em_high) / 2
        f_mid = 2.78 * em_mid / (em_mid + 1400)
        dmg_mid = k * (1 + global_bonus + f_mid)
        if abs(dmg_mid - target_damage) < 0.01:
            break
        if dmg_mid < target_damage:
            em_low = em_mid
        else:
            em_high = em_mid
    required_hp = (em_mid - base_em) / r
    derivative = k * 2.78 * 1400 * r / ((em_mid + 1400) ** 2)
    hp_per_damage = 1 / derivative if derivative != 0 else 0.0
    return HpResult(required_hp=required_hp, hp_per_damage=hp_per_damage, note="普通模式")


def solve_hp_xiteli(
    target_damage: float,
    r: float,
    hp: float,
    dmg: float,
    em_c: float,
    em_x: float,
    base_other: float = 0.0,
    global_bonus_percent: float = 0.0,
) -> HpResult:
    global_bonus = global_bonus_percent / 100.0
    base_em_c = em_c - r * hp
    fixed_current = (em_x + r * hp) * 2
    f_current = 2.78 * em_c / (em_c + 1400)
    total_base_current = r * hp + base_other + fixed_current
    k = dmg / (total_base_current * (1 + global_bonus + f_current))
    hp_low, hp_high = 0.0, 500000.0
    hp_mid = hp
    for _ in range(100):
        hp_mid = (hp_low + hp_high) / 2
        em_mid = base_em_c + r * hp_mid
        f_mid = 2.78 * em_mid / (em_mid + 1400)
        fixed_mid = (em_x + r * hp_mid) * 2
        total_base_mid = r * hp_mid + base_other + fixed_mid
        dmg_mid = k * total_base_mid * (1 + global_bonus + f_mid)
        if abs(dmg_mid - target_damage) < 0.01:
            break
        if dmg_mid < target_damage:
            hp_low = hp_mid
        else:
            hp_high = hp_mid
    em_target = base_em_c + r * hp_mid
    f_target = 2.78 * em_target / (em_target + 1400)
    fixed_target = (em_x + r * hp_mid) * 2
    total_base_target = r * hp_mid + base_other + fixed_target
    df_dh = 2.78 * 1400 * r / ((em_target + 1400) ** 2)
    derivative = k * (3 * r * (1 + global_bonus + f_target) + total_base_target * df_dh)
    hp_per_damage = 1 / derivative if derivative != 0 else 0.0
    return HpResult(required_hp=hp_mid, hp_per_damage=hp_per_damage, note="茜特拉莉一命模式")


def solve_hp_em_model(
    target_damage: float,
    r: float,
    groups: list[tuple[float, float]],
    global_bonus_percent: float = 0.0,
) -> HpResult:
    extra_bonus = global_bonus_percent / 100.0
    if len(groups) < 2:
        raise ValueError("生命值精通模型至少需要2组数据。")
    used_all = len(groups)
    groups = pick_groups_nearest_target_damage(target_damage, groups)
    valid_base_ems: list[float] = []
    valid_ks: list[float] = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            hp_i, damage_i = groups[i]
            hp_j, damage_j = groups[j]
            a_ratio = damage_i / damage_j
            c1 = r * hp_i
            c2 = r * hp_j
            a_coef = a_ratio * 3.78 - 3.78
            b_coef = a_ratio * (3.78 * (c1 + c2 + 1400) + 1400) - (3.78 * (c2 + 1400) + 3.78 * c1 + 1400)
            c_coef = a_ratio * (c1 + 1400) * (3.78 * c2 + 1400) - (3.78 * c1 + 1400) * (c2 + 1400)
            solutions: list[float] = []
            if abs(a_coef) < 1e-10:
                if abs(b_coef) >= 1e-10:
                    solutions.append(-c_coef / b_coef)
            else:
                delta = b_coef**2 - 4 * a_coef * c_coef
                if delta >= 0:
                    sqrt_delta = math.sqrt(delta)
                    solutions.append((-b_coef + sqrt_delta) / (2 * a_coef))
                    solutions.append((-b_coef - sqrt_delta) / (2 * a_coef))
            for base_em in solutions:
                if base_em < 0 or base_em > 10000:
                    continue
                t_i = base_em + r * hp_i
                if abs(t_i + 1400) < 1e-10:
                    continue
                reaction_i = 1 + (2.78 * t_i) / (t_i + 1400) + extra_bonus
                k = damage_i / reaction_i if reaction_i != 0 else 0.0
                if k <= 0:
                    continue
                t_j = base_em + r * hp_j
                if abs(t_j + 1400) < 1e-10:
                    continue
                reaction_j = 1 + (2.78 * t_j) / (t_j + 1400) + extra_bonus
                predicted_j = k * reaction_j
                if abs(predicted_j - damage_j) / damage_j > 0.01:
                    continue
                valid_base_ems.append(base_em)
                valid_ks.append(k)
    if not valid_base_ems:
        raise ValueError("无法由数据拟合出有效的精通模型参数。")
    avg_base_em = sum(valid_base_ems) / len(valid_base_ems)
    avg_k = sum(valid_ks) / len(valid_ks)
    hp_low, hp_high = 0.0, 500000.0
    hp_mid = 0.0
    for _ in range(100):
        hp_mid = (hp_low + hp_high) / 2
        em_mid = avg_base_em + r * hp_mid
        f_mid = 2.78 * em_mid / (em_mid + 1400)
        dmg_mid = avg_k * (1 + extra_bonus + f_mid)
        if abs(dmg_mid - target_damage) < 0.01:
            break
        if dmg_mid < target_damage:
            hp_low = hp_mid
        else:
            hp_high = hp_mid
    em_target = avg_base_em + r * hp_mid
    df_dh = 2.78 * 1400 * r / ((em_target + 1400) ** 2)
    derivative = avg_k * df_dh
    hp_per_damage = 1 / derivative if derivative != 0 else 0.0
    note = "精通模型（邻近目标两组）" if used_all >= 3 and len(groups) == 2 else "精通模型"
    return HpResult(required_hp=hp_mid, hp_per_damage=hp_per_damage, note=note)


def solve_hp_linear_model(target_damage: float, groups: list[tuple[float, float]]) -> HpResult:
    if len(groups) < 2:
        raise ValueError("生命值线性模型至少需要2组数据。")
    used_all = len(groups)
    groups = pick_groups_nearest_target_damage(target_damage, groups)
    n = len(groups)
    sum_h = sum(h for h, _ in groups)
    sum_d = sum(d for _, d in groups)
    sum_hd = sum(h * d for h, d in groups)
    sum_h2 = sum(h * h for h, _ in groups)
    denom = n * sum_h2 - sum_h * sum_h
    if abs(denom) < 1e-10:
        raise ValueError("所有生命值相同，无法线性拟合。")
    a = (n * sum_hd - sum_h * sum_d) / denom
    b = (sum_d - a * sum_h) / n
    required_hp = (target_damage - b) / a if a != 0 else 0.0
    hp_per_damage = 1 / a if a != 0 else 0.0
    note = "线性模型（邻近目标两组）" if used_all >= 3 and n == 2 else "线性模型"
    return HpResult(required_hp=required_hp, hp_per_damage=hp_per_damage, note=note)
