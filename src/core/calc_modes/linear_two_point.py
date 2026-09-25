from core.common.models import LinearInput, LinearResult
from core.calc_modes.nearest_target_pair import pick_groups_nearest_target_damage


def solve_linear_two_point(data: LinearInput) -> LinearResult:
    if abs(data.x2 - data.x1) < 1e-12:
        raise ValueError("两组属性值不能相同。")
    slope = (data.d2 - data.d1) / (data.x2 - data.x1)
    if abs(slope) < 1e-12:
        raise ValueError("斜率接近 0，无法反推属性值。")
    intercept = data.d1 - slope * data.x1
    required = (data.target_d - intercept) / slope
    return LinearResult(slope=slope, intercept=intercept, required_x=required)


def solve_linear_regression(target_d: float, groups: list[tuple[float, float]]) -> LinearResult:
    if len(groups) < 2:
        raise ValueError("线性模型至少需要2组数据。")
    groups = pick_groups_nearest_target_damage(target_d, groups)
    n = len(groups)
    sum_x = sum(x for x, _ in groups)
    sum_y = sum(y for _, y in groups)
    sum_xy = sum(x * y for x, y in groups)
    sum_x2 = sum(x * x for x, _ in groups)
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        raise ValueError("所有属性值相同，无法线性拟合。")
    slope = (n * sum_xy - sum_x * sum_y) / denom
    if abs(slope) < 1e-12:
        raise ValueError("斜率接近 0，无法反推属性值。")
    intercept = (sum_y - slope * sum_x) / n
    required = (target_d - intercept) / slope
    return LinearResult(slope=slope, intercept=intercept, required_x=required)
