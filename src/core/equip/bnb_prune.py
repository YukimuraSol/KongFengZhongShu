"""区间分支定界：判断部分组合能否落入 target±tolerance（无损剪枝）。"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


def intervals_intersect(
    low: float,
    high: float,
    target: float,
    tolerance: float,
) -> bool:
    """[low, high] 与 [target-tol, target+tol] 是否有交集。"""
    band_lo = float(target) - float(tolerance)
    band_hi = float(target) + float(tolerance)
    return high >= band_lo and low <= band_hi


def min_dist_to_value(low: float, high: float, target: float) -> float:
    """[low, high] 到 target 的最小距离（用于最近邻剪枝）。"""
    lo = float(low)
    hi = float(high)
    tgt = float(target)
    if lo <= tgt <= hi:
        return 0.0
    if hi < tgt:
        return tgt - hi
    return lo - tgt


def sort_by_target_proximity(
    items: Sequence[T],
    score_fn: Callable[[T], float],
    target: float,
) -> list[T]:
    """按单点估计值与目标的距离排序（兼容旧调用）。"""
    return sorted(items, key=lambda x: abs(score_fn(x) - float(target)))


def sort_by_interval_proximity(
    items: Sequence[T],
    bounds_fn: Callable[[T], tuple[float, float]],
    target: float,
) -> list[T]:
    """按条目贡献区间与目标的距离排序；区间覆盖目标者优先、更窄者优先。"""

    def key(x: T) -> tuple[float, float, float]:
        lo, hi = bounds_fn(x)
        d = min_dist_to_value(lo, hi, float(target))
        if d == 0.0:
            return (0.0, hi - lo, lo)
        return (1.0, d, hi - lo)

    return sorted(items, key=key)


def min_max_scores(
    items: Sequence[T],
    score_fn: Callable[[T], float],
) -> tuple[float, float]:
    if not items:
        return 0.0, 0.0
    scores = [score_fn(x) for x in items]
    return min(scores), max(scores)


def bounds_list_span(bounds: Sequence[tuple[float, float]]) -> float:
    """单部位所有条目贡献区间的宽度 max-min。"""
    if not bounds:
        return 0.0
    return max(b[1] for b in bounds) - min(b[0] for b in bounds)


def sort_positions_wide_to_narrow(
    positions: Sequence[str],
    *,
    width_by_pos: dict[str, float],
    count_by_pos: dict[str, int] | None = None,
) -> list[str]:
    """按部位区间宽度降序；同宽时件数升序（宽→窄）。"""

    def key(p: str) -> tuple[float, int]:
        count = int(count_by_pos.get(p, 0)) if count_by_pos else 0
        return (-float(width_by_pos.get(p, 0.0)), count)

    return sorted(positions, key=key)


def branch_contrib_bounds(
    *,
    base_stat: float,
    partial_lo: float,
    partial_hi: float,
    rem_lo: float,
    rem_hi: float,
    set_bonus_lo: float = 0.0,
    set_bonus_hi: float = 0.0,
) -> tuple[float, float]:
    """partial_lo/hi + 剩余槽区间 + 套装加成 → 可达 [cur_lo, cur_hi]（与生命 DFS 口径一致）。"""
    cur_lo = float(base_stat) + float(partial_lo) + float(rem_lo) + float(set_bonus_lo)
    cur_hi = float(base_stat) + float(partial_hi) + float(rem_hi) + float(set_bonus_hi)
    return cur_lo, cur_hi
