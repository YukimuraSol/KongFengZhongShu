from core.calc_modes.em_solver import (
    solve_em_multi_group,
    solve_em_single_group,
    solve_em_single_group_with_other,
)
from core.calc_modes.hp_solver import (
    solve_hp_em_model,
    solve_hp_linear_model,
    solve_hp_normal,
)
from core.calc_modes.linear_two_point import solve_linear_regression, solve_linear_two_point
from core.common.models import LinearInput

from ..schemas.calc import CalcResult, EmRequest, HpRequest, LinearFitRequest, TwoPointRequest
from .number_parser import safe_eval_number


def calc_two_point(payload: TwoPointRequest) -> CalcResult:
    result = solve_linear_two_point(
        LinearInput(
            x1=payload.x1,
            d1=payload.y1,
            x2=payload.x2,
            d2=payload.y2,
            target_d=payload.target,
        )
    )
    return CalcResult(
        target=payload.target,
        required=result.required_x,
        attr_per_damage=1 / result.slope,
        damage_per_attr=result.slope,
        note="两点定线",
    )


def calc_linear_fit(payload: LinearFitRequest) -> CalcResult:
    groups = [(item.x, item.y) for item in payload.groups]
    result = solve_linear_regression(payload.target, groups)
    note = "线性拟合（邻近目标两组）" if len(groups) >= 3 else "线性拟合"
    return CalcResult(
        target=payload.target,
        required=result.required_x,
        attr_per_damage=1 / result.slope,
        damage_per_attr=result.slope,
        note=note,
    )


def calc_hp(payload: HpRequest) -> CalcResult:
    groups = [(item.x, item.y) for item in payload.groups]
    group_count = int(payload.group_count)
    target = safe_eval_number(payload.target)
    ratio = safe_eval_number(payload.r)
    hp = safe_eval_number(payload.hp)
    damage = safe_eval_number(payload.damage)
    em = safe_eval_number(payload.em)
    global_bonus_percent = safe_eval_number(payload.global_bonus_percent)
    if payload.mode in ("normal",) and group_count != 1:
        raise ValueError("单组模式下，数据组数必须为1。")
    if payload.mode in ("em-model", "linear-model"):
        if group_count < 2:
            raise ValueError("多组模式下，数据组数至少为2。")
        if len(groups) < 2:
            raise ValueError("多组模式至少需要2组有效数据。")

    if payload.mode == "normal":
        result = solve_hp_normal(target, ratio, hp, damage, em, global_bonus_percent)
    elif payload.mode == "em-model":
        result = solve_hp_em_model(target, ratio, groups, global_bonus_percent)
    else:
        result = solve_hp_linear_model(target, groups)
    return CalcResult(
        target=target,
        required=result.required_hp,
        attr_per_damage=result.hp_per_damage,
        damage_per_attr=(1 / result.hp_per_damage if result.hp_per_damage else 0.0),
        note=result.note,
    )


def _em_single_use_other_branch(payload: EmRequest) -> bool:
    """显式 mode 优先；legacy mode=single-group 时读 has_other_multiplier。"""
    if payload.mode == "single-other":
        return True
    if payload.mode == "single-normal":
        return False
    if payload.mode == "single-group":
        return bool(getattr(payload, "has_other_multiplier", False))
    return False


def calc_em(payload: EmRequest) -> CalcResult:
    target = safe_eval_number(payload.target)
    k_main = safe_eval_number(payload.k_main)
    if payload.mode == "multi-group":
        groups = [(item.x, item.y) for item in payload.groups]
        for i, (em_i, dmg_i) in enumerate(groups):
            if float(dmg_i) <= 0:
                raise ValueError(f"第{i + 1}组：主C伤害须为正数。")
            if float(em_i) < 0:
                raise ValueError(f"第{i + 1}组：辅助精通须为非负数（可为 0）。")
        result = solve_em_multi_group(target, k_main, groups)
    else:
        em0 = safe_eval_number(payload.em0)
        dmg0 = safe_eval_number(payload.dmg0)
        atk0 = safe_eval_number(payload.atk_total0)
        if float(em0) < 0:
            raise ValueError("辅助精通须为非负数（可为 0）。")
        if float(dmg0) <= 0:
            raise ValueError("主C伤害须为正数。")
        if _em_single_use_other_branch(payload):
            r_val = safe_eval_number(payload.other_ratio_r)
            b_val = safe_eval_number(payload.other_base_b)
            if not abs(float(r_val)) > 1e-12:
                raise ValueError("「其他倍率介入」模式下，主C攻击倍率 R 须为非零有效数值。")
            result = solve_em_single_group_with_other(
                target, k_main, em0, dmg0, atk0, float(r_val), float(b_val)
            )
        else:
            result = solve_em_single_group(target, k_main, em0, dmg0, atk0)
    return CalcResult(
        target=target,
        required=result.required_em,
        attr_per_damage=result.em_per_damage,
        damage_per_attr=(1 / result.em_per_damage if result.em_per_damage else 0.0),
        note=result.note,
    )
