"""多组数据：组数≥3 时取伤害最接近目标的两组再算。"""

from __future__ import annotations


def pick_groups_nearest_target_damage(
    target_d: float,
    groups: list[tuple[float, float]],
    *,
    min_x_span: float = 1e-12,
) -> list[tuple[float, float]]:
    """
    组数 < 3：原样返回。
    组数 ≥ 3：按 |伤害−目标| 从近到远，取属性差够开的最近一对。
    若所有对属性都挤在一起，退回全部组（交给上层报错）。
    """
    if len(groups) < 3:
        return list(groups)
    order = sorted(range(len(groups)), key=lambda i: (abs(groups[i][1] - target_d), i))
    for ai, a in enumerate(order):
        for b in order[ai + 1 :]:
            if abs(groups[a][0] - groups[b][0]) >= min_x_span:
                return [groups[a], groups[b]]
    return list(groups)
