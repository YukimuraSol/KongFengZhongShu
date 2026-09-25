"""按套装分支调度优化搜索：首命中即停 + 精确套装区间剪枝。"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

from core.equip.bnb_prune import bounds_list_span, branch_contrib_bounds, intervals_intersect, min_dist_to_value, sort_positions_wide_to_narrow
from core.equip.set_branch_bounds import branch_globally_unreachable, branch_set_bonus_interval, partial_set_bonus_interval
from core.equip.set_branch_plan import SearchBranch, StatMode, filter_pos_map_by_specs, iter_search_branches

_LEGACY_PROGRESS_INTERVAL = 10000
_TRIED_SYNC_INTERVAL = 1000

TrialHook = Callable[[int, int], None]
LeafBeginHook = Callable[[int, int], None]


def _notify_leaf_progress(
    count: int,
    total_est: int,
    *,
    on_progress: Callable[[dict[str, Any]], None] | None,
    on_trial: TrialHook | None,
    progress_interval: int,
    emit_logged_progress: Callable[[], None] | None = None,
) -> None:
    """首叶与每 1000 组同步 tried；每 10000 组写过程日志。"""
    if callable(on_progress) and (count == 1 or count % _TRIED_SYNC_INTERVAL == 0):
        on_progress(
            {
                "enumeration_progress": min(1.0, count / max(total_est, 1)),
                "tried": count,
            }
        )
    if count == 1 or count % progress_interval == 0:
        if on_trial:
            on_trial(count, total_est)
        elif emit_logged_progress:
            emit_logged_progress()


@dataclass
class BranchedSearchOutcome:
    found: bool
    stop: str
    truncated: bool
    tried: int
    total_est: int
    branches_run: int
    branches_skipped: int
    branch_logs: list[str] = field(default_factory=list)


def scan_product_leaves(
    lists: list[list[Any]],
    *,
    process_leaf: Callable[[tuple[Any, ...]], bool],
    should_cancel: Callable[[], bool] | None = None,
    on_trial: TrialHook | None = None,
    on_leaf_begin: LeafBeginHook | None = None,
    progress_interval: int = _LEGACY_PROGRESS_INTERVAL,
    total_hint: int | None = None,
) -> int:
    """全池 product 扫描（无容差层剪枝），用于最近邻兜底与纯枚举。"""
    total = total_hint if total_hint is not None else 1
    if total_hint is None:
        for lst in lists:
            total *= max(1, len(lst))
    count = 0
    for combo in itertools.product(*lists):
        if should_cancel and should_cancel():
            break
        count += 1
        if on_leaf_begin:
            on_leaf_begin(count, total)
        _notify_leaf_progress(
            count,
            total,
            on_progress=None,
            on_trial=on_trial,
            progress_interval=progress_interval,
        )
        if process_leaf(combo):
            break
    if on_trial and count > 0 and count != 1 and count % progress_interval != 0:
        on_trial(count, total)
    return count


def run_branched_linear_dfs(
    *,
    pos_map: dict[str, list[Any]],
    positions: list[str],
    stat_mode: StatMode,
    target: float,
    tolerance: float,
    base_stat: float,
    base_panel: float,
    piece_bounds_fn: Callable[[Any], tuple[float, float]],
    piece_point_fn: Callable[[Any], float],
    process_leaf: Callable[[tuple[Any, ...]], bool],
    should_cancel: Callable[[], bool] | None,
    on_progress: Callable[[dict[str, Any]], None] | None,
    progress_interval: int = _LEGACY_PROGRESS_INTERVAL,
    on_trial: TrialHook | None = None,
    on_leaf_begin: LeafBeginHook | None = None,
    prune_to_tolerance: bool = True,
    skip_global_unreachable: bool = False,
    stop_on_first_match: bool = True,
) -> BranchedSearchOutcome:
    count = 0
    total_est = 0
    truncated = False
    stop = "no_match"
    branches_run = 0
    branches_skipped = 0
    branch_logs: list[str] = []
    found = False

    def _emit_progress(force: bool = False) -> None:
        if not callable(on_progress):
            return
        if count <= 0:
            return
        if not force and count % progress_interval != 0 and count > 0:
            return
        enum_prog = min(1.0, count / max(total_est, 1))
        line = f"已处理 {count} / {total_est}"
        on_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": count,
                "process_log_line": line,
            }
        )

    for branch in iter_search_branches(pos_map, positions, stat_mode=stat_mode):
        specs = branch.slot_specs()
        filtered = filter_pos_map_by_specs(pos_map, positions, specs, stat_mode=stat_mode)
        if filtered is None:
            branches_skipped += 1
            continue

        bonus_lo, bonus_hi = branch_set_bonus_interval(
            branch,
            stat_mode=stat_mode,
            base_panel=base_panel,
            pos_map=pos_map,
        )

        slot_bounds_by_pos = {
            p: [piece_bounds_fn(e) for e in filtered[p]] for p in positions
        }
        width_by_pos = {p: bounds_list_span(slot_bounds_by_pos[p]) for p in positions}
        count_by_pos = {p: len(filtered[p]) for p in positions}
        ordered = sort_positions_wide_to_narrow(
            list(positions),
            width_by_pos=width_by_pos,
            count_by_pos=count_by_pos,
        )

        lists = [filtered[p] for p in ordered]
        bounds_lists = [slot_bounds_by_pos[p] for p in ordered]
        slot_min = [min(b[0] for b in bs) for bs in bounds_lists]
        slot_max = [max(b[1] for b in bs) for bs in bounds_lists]

        branch_total = 1
        for lst in lists:
            branch_total *= max(1, len(lst))
        total_est += branch_total

        piece_lo = sum(slot_min)
        piece_hi = sum(slot_max)
        if (
            not skip_global_unreachable
            and branch_globally_unreachable(
                base_stat=base_stat,
                piece_lo=piece_lo,
                piece_hi=piece_hi,
                bonus_lo=bonus_lo,
                bonus_hi=bonus_hi,
                target=target,
                tolerance=tolerance,
            )
        ):
            branches_skipped += 1
            branch_logs.append(f"跳过（全局不可达）: {branch.label()}")
            continue

        suffix_lo = [0.0] * (len(lists) + 1)
        suffix_hi = [0.0] * (len(lists) + 1)
        for i in range(len(lists) - 1, -1, -1):
            suffix_lo[i] = suffix_lo[i + 1] + slot_min[i]
            suffix_hi[i] = suffix_hi[i + 1] + slot_max[i]

        branches_run += 1
        branch_line = f"搜索分支: {branch.label()} 组合≈{branch_total}"
        branch_logs.append(branch_line)

        n = len(lists)

        def _bonus_bounds(partial: list[Any], depth: int) -> tuple[float, float]:
            return partial_set_bonus_interval(
                partial,
                lists[depth:],
                stat_mode=stat_mode,
                base_panel=base_panel,
                branch=branch,
                pos_map=pos_map,
            )

        def dfs(depth: int, partial: list[Any], partial_lo: float, partial_hi: float) -> bool:
            nonlocal stop, truncated, count, found

            if should_cancel and should_cancel():
                truncated = True
                stop = "manual_cancel"
                return True

            if depth == n:
                count += 1
                if on_leaf_begin:
                    on_leaf_begin(count, total_est)
                _notify_leaf_progress(
                    count,
                    total_est,
                    on_progress=on_progress,
                    on_trial=on_trial,
                    progress_interval=progress_interval,
                    emit_logged_progress=_emit_progress,
                )
                if process_leaf(tuple(partial)):
                    found = stop_on_first_match
                    if stop_on_first_match:
                        stop = "first_match_found"
                        return True
                return False

            bonus_lo, bonus_hi = _bonus_bounds(partial, depth)
            if prune_to_tolerance:
                rem_lo = suffix_lo[depth]
                rem_hi = suffix_hi[depth]
                cur_lo, cur_hi = branch_contrib_bounds(
                    base_stat=base_stat,
                    partial_lo=partial_lo,
                    partial_hi=partial_hi,
                    rem_lo=rem_lo,
                    rem_hi=rem_hi,
                    set_bonus_lo=bonus_lo,
                    set_bonus_hi=bonus_hi,
                )
                if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                    return False

            for entry, (pt_lo, pt_hi) in zip(lists[depth], bounds_lists[depth]):
                new_lo = partial_lo + pt_lo
                new_hi = partial_hi + pt_hi
                partial.append(entry)
                bonus_lo, bonus_hi = _bonus_bounds(partial, depth + 1)
                if prune_to_tolerance:
                    cur_lo, cur_hi = branch_contrib_bounds(
                        base_stat=base_stat,
                        partial_lo=new_lo,
                        partial_hi=new_hi,
                        rem_lo=suffix_lo[depth + 1],
                        rem_hi=suffix_hi[depth + 1],
                        set_bonus_lo=bonus_lo,
                        set_bonus_hi=bonus_hi,
                    )
                    if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                        partial.pop()
                        continue
                if dfs(depth + 1, partial, new_lo, new_hi):
                    partial.pop()
                    return True
                partial.pop()
                if stop == "manual_cancel":
                    return True
            return False

        if dfs(0, [], 0.0, 0.0):
            break

    if callable(on_progress):
        _emit_progress(force=True)
    if on_trial and count > 0 and count != 1 and count % progress_interval != 0:
        on_trial(count, total_est)

    return BranchedSearchOutcome(
        found=found,
        stop=stop,
        truncated=truncated,
        tried=count,
        total_est=total_est,
        branches_run=branches_run,
        branches_skipped=branches_skipped,
        branch_logs=branch_logs,
    )


def run_branched_linear_closest(
    *,
    pos_map: dict[str, list[Any]],
    positions: list[str],
    stat_mode: StatMode,
    target: float,
    base_stat: float,
    base_panel: float,
    piece_bounds_fn: Callable[[Any], tuple[float, float]],
    process_leaf: Callable[[tuple[Any, ...]], bool],
    should_cancel: Callable[[], bool] | None,
    on_progress: Callable[[dict[str, Any]], None] | None,
    progress_interval: int = _LEGACY_PROGRESS_INTERVAL,
    on_trial: TrialHook | None = None,
    on_leaf_begin: LeafBeginHook | None = None,
    get_closest_diff: Callable[[], float],
    skip_global_unreachable: bool = False,
) -> BranchedSearchOutcome:
    """套装分支 + 区间 BnB 找最近邻（按 min_dist 剪枝，替代无剪枝全池 product）。"""
    count = 0
    total_est = 0
    truncated = False
    stop = "no_match"
    branches_run = 0
    branches_skipped = 0
    branch_logs: list[str] = []
    found = False

    def _emit_progress(force: bool = False) -> None:
        if not callable(on_progress):
            return
        if count <= 0:
            return
        if not force and count % progress_interval != 0 and count > 0:
            return
        enum_prog = min(1.0, count / max(total_est, 1))
        line = f"已处理 {count} / {total_est}"
        on_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": count,
                "process_log_line": line,
            }
        )

    for branch in iter_search_branches(pos_map, positions, stat_mode=stat_mode):
        specs = branch.slot_specs()
        filtered = filter_pos_map_by_specs(pos_map, positions, specs, stat_mode=stat_mode)
        if filtered is None:
            branches_skipped += 1
            continue

        bonus_lo, bonus_hi = branch_set_bonus_interval(
            branch,
            stat_mode=stat_mode,
            base_panel=base_panel,
            pos_map=pos_map,
        )

        slot_bounds_by_pos = {
            p: [piece_bounds_fn(e) for e in filtered[p]] for p in positions
        }
        width_by_pos = {p: bounds_list_span(slot_bounds_by_pos[p]) for p in positions}
        count_by_pos = {p: len(filtered[p]) for p in positions}
        ordered = sort_positions_wide_to_narrow(
            list(positions),
            width_by_pos=width_by_pos,
            count_by_pos=count_by_pos,
        )

        lists = [filtered[p] for p in ordered]
        bounds_lists = [slot_bounds_by_pos[p] for p in ordered]
        slot_min = [min(b[0] for b in bs) for bs in bounds_lists]
        slot_max = [max(b[1] for b in bs) for bs in bounds_lists]

        branch_total = 1
        for lst in lists:
            branch_total *= max(1, len(lst))
        total_est += branch_total

        piece_lo = sum(slot_min)
        piece_hi = sum(slot_max)
        if (
            not skip_global_unreachable
            and branch_globally_unreachable(
                base_stat=base_stat,
                piece_lo=piece_lo,
                piece_hi=piece_hi,
                bonus_lo=bonus_lo,
                bonus_hi=bonus_hi,
                target=target,
                tolerance=0.0,
            )
        ):
            branches_skipped += 1
            branch_logs.append(f"跳过（全局不可达）: {branch.label()}")
            continue

        suffix_lo = [0.0] * (len(lists) + 1)
        suffix_hi = [0.0] * (len(lists) + 1)
        for i in range(len(lists) - 1, -1, -1):
            suffix_lo[i] = suffix_lo[i + 1] + slot_min[i]
            suffix_hi[i] = suffix_hi[i + 1] + slot_max[i]

        branches_run += 1
        branch_logs.append(f"最近邻分支: {branch.label()} 组合≈{branch_total}")
        n = len(lists)

        def _bonus_bounds(partial: list[Any], depth: int) -> tuple[float, float]:
            return partial_set_bonus_interval(
                partial,
                lists[depth:],
                stat_mode=stat_mode,
                base_panel=base_panel,
                branch=branch,
                pos_map=pos_map,
            )

        def dfs(depth: int, partial: list[Any], partial_lo: float, partial_hi: float) -> bool:
            nonlocal stop, truncated, count, found

            if should_cancel and should_cancel():
                truncated = True
                stop = "manual_cancel"
                return True

            if depth == n:
                count += 1
                if on_leaf_begin:
                    on_leaf_begin(count, total_est)
                _notify_leaf_progress(
                    count,
                    total_est,
                    on_progress=on_progress,
                    on_trial=on_trial,
                    progress_interval=progress_interval,
                    emit_logged_progress=_emit_progress,
                )
                process_leaf(tuple(partial))
                return False

            bonus_lo, bonus_hi = _bonus_bounds(partial, depth)
            rem_lo = suffix_lo[depth]
            rem_hi = suffix_hi[depth]
            cur_lo, cur_hi = branch_contrib_bounds(
                base_stat=base_stat,
                partial_lo=partial_lo,
                partial_hi=partial_hi,
                rem_lo=rem_lo,
                rem_hi=rem_hi,
                set_bonus_lo=bonus_lo,
                set_bonus_hi=bonus_hi,
            )
            if min_dist_to_value(cur_lo, cur_hi, target) >= get_closest_diff():
                return False

            for entry, (pt_lo, pt_hi) in zip(lists[depth], bounds_lists[depth]):
                new_lo = partial_lo + pt_lo
                new_hi = partial_hi + pt_hi
                partial.append(entry)
                bonus_lo, bonus_hi = _bonus_bounds(partial, depth + 1)
                cur_lo, cur_hi = branch_contrib_bounds(
                    base_stat=base_stat,
                    partial_lo=new_lo,
                    partial_hi=new_hi,
                    rem_lo=suffix_lo[depth + 1],
                    rem_hi=suffix_hi[depth + 1],
                    set_bonus_lo=bonus_lo,
                    set_bonus_hi=bonus_hi,
                )
                if min_dist_to_value(cur_lo, cur_hi, target) >= get_closest_diff():
                    partial.pop()
                    continue
                if dfs(depth + 1, partial, new_lo, new_hi):
                    partial.pop()
                    return True
                partial.pop()
                if stop == "manual_cancel":
                    return True
            return False

        dfs(0, [], 0.0, 0.0)

    if callable(on_progress):
        _emit_progress(force=True)
    if on_trial and count > 0 and count != 1 and count % progress_interval != 0:
        on_trial(count, total_est)

    return BranchedSearchOutcome(
        found=found,
        stop=stop,
        truncated=truncated,
        tried=count,
        total_est=total_est,
        branches_run=branches_run,
        branches_skipped=branches_skipped,
        branch_logs=branch_logs,
    )


def run_branched_layer_dfs(
    *,
    pos_map: dict[str, list[Any]],
    positions: list[str],
    stat_mode: StatMode,
    target: float,
    tolerance: float,
    base_stat: float,
    base_panel: float,
    bounds_fn: Callable[[dict[str, Any]], tuple[float, float]],
    process_leaf: Callable[[tuple[Any, ...]], bool],
    should_cancel: Callable[[], bool] | None,
    on_progress: Callable[[dict[str, Any]], None] | None,
    progress_interval: int = _LEGACY_PROGRESS_INTERVAL,
    on_trial: TrialHook | None = None,
    on_leaf_begin: LeafBeginHook | None = None,
    prune_to_tolerance: bool = True,
    skip_global_unreachable: bool = False,
    stop_on_first_match: bool = True,
) -> BranchedSearchOutcome:
    count = 0
    total_est = 0
    truncated = False
    stop = "no_match"
    branches_run = 0
    branches_skipped = 0
    branch_logs: list[str] = []
    found = False

    def _emit_progress(force: bool = False) -> None:
        if not callable(on_progress):
            return
        if count <= 0:
            return
        if not force and count % progress_interval != 0 and count > 0:
            return
        enum_prog = min(1.0, count / max(total_est, 1))
        line = f"已处理 {count} / {total_est}"
        on_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": count,
                "process_log_line": line,
            }
        )

    for branch in iter_search_branches(pos_map, positions, stat_mode=stat_mode):
        specs = branch.slot_specs()
        filtered = filter_pos_map_by_specs(pos_map, positions, specs, stat_mode=stat_mode)
        if filtered is None:
            branches_skipped += 1
            continue

        bonus_lo, bonus_hi = branch_set_bonus_interval(
            branch,
            stat_mode=stat_mode,
            base_panel=base_panel,
            pos_map=pos_map,
        )

        slot_bounds_by_pos = {p: [bounds_fn(a) for a in filtered[p]] for p in positions}
        width_by_pos = {p: bounds_list_span(slot_bounds_by_pos[p]) for p in positions}
        count_by_pos = {p: len(filtered[p]) for p in positions}
        ordered = sort_positions_wide_to_narrow(
            list(positions),
            width_by_pos=width_by_pos,
            count_by_pos=count_by_pos,
        )

        lists = [filtered[p] for p in ordered]
        slot_min = [min(b[0] for b in slot_bounds_by_pos[p]) for p in ordered]
        slot_max = [max(b[1] for b in slot_bounds_by_pos[p]) for p in ordered]

        branch_total = 1
        for lst in lists:
            branch_total *= max(1, len(lst))
        total_est += branch_total

        piece_lo = sum(slot_min)
        piece_hi = sum(slot_max)
        if (
            not skip_global_unreachable
            and branch_globally_unreachable(
                base_stat=base_stat,
                piece_lo=piece_lo,
                piece_hi=piece_hi,
                bonus_lo=bonus_lo,
                bonus_hi=bonus_hi,
                target=target,
                tolerance=tolerance,
            )
        ):
            branches_skipped += 1
            branch_logs.append(f"跳过（全局不可达）: {branch.label()}")
            continue

        branches_run += 1
        branch_logs.append(f"搜索分支: {branch.label()} 组合≈{branch_total}")
        n = len(lists)

        def dfs(depth: int, partial: list[Any], partial_lo: float, partial_hi: float) -> bool:
            nonlocal stop, truncated, count, found

            if should_cancel and should_cancel():
                truncated = True
                stop = "manual_cancel"
                return True

            if depth == n:
                count += 1
                if on_leaf_begin:
                    on_leaf_begin(count, total_est)
                _notify_leaf_progress(
                    count,
                    total_est,
                    on_progress=on_progress,
                    on_trial=on_trial,
                    progress_interval=progress_interval,
                    emit_logged_progress=_emit_progress,
                )
                if process_leaf(tuple(partial)):
                    found = stop_on_first_match
                    if stop_on_first_match:
                        stop = "first_match_found"
                        return True
                return False

            if prune_to_tolerance:
                rem_lo = sum(slot_min[depth:])
                rem_hi = sum(slot_max[depth:])
                cur_lo, cur_hi = branch_contrib_bounds(
                    base_stat=base_stat,
                    partial_lo=partial_lo,
                    partial_hi=partial_hi,
                    rem_lo=rem_lo,
                    rem_hi=rem_hi,
                    set_bonus_lo=bonus_lo,
                    set_bonus_hi=bonus_hi,
                )
                if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                    return False

            for art in lists[depth]:
                lo, hi = bounds_fn(art)
                partial.append(art)
                if dfs(depth + 1, partial, partial_lo + lo, partial_hi + hi):
                    partial.pop()
                    return True
                partial.pop()
                if stop == "manual_cancel":
                    return True
            return False

        if dfs(0, [], 0.0, 0.0):
            break

    if callable(on_progress):
        _emit_progress(force=True)
    if on_trial and count > 0 and count != 1 and count % progress_interval != 0:
        on_trial(count, total_est)

    return BranchedSearchOutcome(
        found=found,
        stop=stop,
        truncated=truncated,
        tried=count,
        total_est=total_est,
        branches_run=branches_run,
        branches_skipped=branches_skipped,
        branch_logs=branch_logs,
    )


def run_branched_hp_dfs(
    *,
    pos_map: dict[str, list[Any]],
    positions: list[str],
    target: float,
    tolerance: float,
    base_stat: float,
    base_hp: float,
    bounds_fn: Callable[[dict[str, Any]], tuple[float, float]],
    process_leaf: Callable[[tuple[Any, ...]], bool],
    should_cancel: Callable[[], bool] | None,
    on_progress: Callable[[dict[str, Any]], None] | None,
    progress_interval: int = _LEGACY_PROGRESS_INTERVAL,
    on_trial: TrialHook | None = None,
    on_leaf_begin: LeafBeginHook | None = None,
    prune_to_tolerance: bool = True,
    skip_global_unreachable: bool = False,
    stop_on_first_match: bool = True,
) -> BranchedSearchOutcome:
    return run_branched_layer_dfs(
        pos_map=pos_map,
        positions=positions,
        stat_mode="hp",
        target=target,
        tolerance=tolerance,
        base_stat=base_stat,
        base_panel=base_hp,
        bounds_fn=bounds_fn,
        process_leaf=process_leaf,
        should_cancel=should_cancel,
        on_progress=on_progress,
        progress_interval=progress_interval,
        on_trial=on_trial,
        on_leaf_begin=on_leaf_begin,
        prune_to_tolerance=prune_to_tolerance,
        skip_global_unreachable=skip_global_unreachable,
        stop_on_first_match=stop_on_first_match,
    )
