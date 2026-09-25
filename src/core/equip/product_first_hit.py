"""有序 product 枚举：首命中即停 + 可选区间剪枝。"""

from __future__ import annotations

from typing import Callable, Generic, Sequence, TypeVar

from .bnb_prune import branch_contrib_bounds, intervals_intersect

T = TypeVar("T")


def search_product_first_hit(
    slot_lists: Sequence[Sequence[T]],
    *,
    target: float,
    tolerance: float,
    evaluate: Callable[[tuple[T, ...]], float | None],
    is_valid: Callable[[tuple[T, ...]], bool] | None = None,
    score_for_sort: Callable[[T], float] | None = None,
    score_for_bounds: Callable[[T], tuple[float, float] | float] | None = None,
    use_bnb: bool = True,
    should_cancel: Callable[[], bool] | None = None,
    on_tried: Callable[[int, int], None] | None = None,
) -> tuple[tuple[T, ...] | None, int, str]:
    """
    返回 (命中组合, tried次数, stop_reason)。
    stop_reason: first_match_found | no_match | manual_cancel
    """
    lists = [list(lst) for lst in slot_lists]
    n = len(lists)
    if n == 0:
        return None, 0, "no_match"

    bounds_fn = score_for_bounds or score_for_sort
    if bounds_fn is None:
        bounds_fn = lambda x: 0.0  # type: ignore[misc, assignment]

    def entry_bounds(item: T) -> tuple[float, float]:
        raw = bounds_fn(item)
        if isinstance(raw, tuple):
            lo, hi = raw
            return float(lo), float(hi)
        v = float(raw)
        return v, v

    slot_min: list[float] = []
    slot_max: list[float] = []
    bounds_lists: list[list[tuple[float, float]]] = []
    for lst in lists:
        slot_bounds = [entry_bounds(x) for x in lst]
        bounds_lists.append(slot_bounds)
        slot_min.append(min(b[0] for b in slot_bounds))
        slot_max.append(max(b[1] for b in slot_bounds))

    tried = 0
    total_est = 1
    for lst in lists:
        total_est *= max(1, len(lst))

    def dfs(depth: int, partial: list[T], partial_lo: float, partial_hi: float) -> tuple[T, ...] | None:
        nonlocal tried
        if should_cancel and should_cancel():
            return None

        if depth == n:
            tried += 1
            if on_tried:
                on_tried(tried, total_est)
            combo = tuple(partial)
            if is_valid and not is_valid(combo):
                return None
            val = evaluate(combo)
            if val is None:
                return None
            if abs(float(val) - float(target)) <= float(tolerance):
                return combo
            return None

        if use_bnb:
            rem_lo = sum(slot_min[depth:])
            rem_hi = sum(slot_max[depth:])
            cur_lo, cur_hi = branch_contrib_bounds(
                base_stat=0.0,
                partial_lo=partial_lo,
                partial_hi=partial_hi,
                rem_lo=rem_lo,
                rem_hi=rem_hi,
            )
            if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                return None

        lst = lists[depth]
        for item, (blo, bhi) in zip(lst, bounds_lists[depth]):
            if should_cancel and should_cancel():
                return None
            new_lo = partial_lo + blo
            new_hi = partial_hi + bhi
            if use_bnb:
                rem_lo = sum(slot_min[depth + 1 :])
                rem_hi = sum(slot_max[depth + 1 :])
                cur_lo, cur_hi = branch_contrib_bounds(
                    base_stat=0.0,
                    partial_lo=new_lo,
                    partial_hi=new_hi,
                    rem_lo=rem_lo,
                    rem_hi=rem_hi,
                )
                if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                    continue
            partial.append(item)
            hit = dfs(depth + 1, partial, new_lo, new_hi)
            partial.pop()
            if hit is not None:
                return hit
        return None

    hit = dfs(0, [], 0.0, 0.0)
    if should_cancel and should_cancel():
        return None, tried, "manual_cancel"
    if hit is not None:
        return hit, tried, "first_match_found"
    return None, tried, "no_match"
