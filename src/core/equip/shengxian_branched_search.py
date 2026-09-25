"""圣显分支搜索通用循环：与生命 `run_shengxian_hp_search` 同一条 DFS + 进度链路。"""

from __future__ import annotations

from typing import Any, Callable

from core.equip.branched_search_runner import run_branched_hp_dfs, run_branched_layer_dfs
from core.equip.bnb_prune import intervals_intersect
from core.equip.progress_stop import ProgressState, attach_search_best
from core.equip.search_engine import _LEGACY_PROGRESS_INTERVAL, _stop_reason_zh
from core.equip.set_branch_plan import StatMode


def run_shengxian_branched_search(
    *,
    state: ProgressState,
    pos_map: dict[str, list[Any]],
    positions: list[str],
    slot_lists: list[list[Any]],
    slot_min: list[float],
    slot_max: list[float],
    stat_mode: StatMode,
    target: float,
    tolerance: float,
    base_stat: float,
    base_panel: float,
    bounds_fn: Callable[[Any], tuple[float, float]],
    process_leaf: Callable[[tuple[Any, ...]], bool],
    use_bnb: bool,
    pool_globally_unreachable: bool,
    total_unique_combinations: int,
    process_logs: list[str],
    push_progress: Callable[[dict[str, Any]], None],
    should_cancel: Callable[[], bool] | None,
) -> tuple[int, bool, str]:
    """执行与生命相同的分支 DFS / 纯枚举 DFS，并写入过程日志与 progress meta。"""
    truncated = False
    stop_reason = "no_match"
    next_milestone = _LEGACY_PROGRESS_INTERVAL
    n = len(slot_lists)

    def _emit_progress() -> None:
        nonlocal next_milestone
        enum_prog = min(1.0, state.tried / max(total_unique_combinations, 1))
        line = f"已处理 {state.tried} / {total_unique_combinations}"
        push_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": state.tried,
                "process_log_line": line,
            }
        )
        process_logs.append(line)
        next_milestone += _LEGACY_PROGRESS_INTERVAL

    def _on_branched_trial(tried: int, total_est: int) -> None:
        del total_est
        state.tried = tried
        _emit_progress()

    def _on_leaf_begin(tried: int, total_est: int) -> None:
        del total_est
        state.tried = tried

    def _wrapped_process_leaf(combo: tuple[Any, ...]) -> bool:
        result = process_leaf(combo)
        if state.tried >= next_milestone:
            _emit_progress()
        return result

    def _run_branched() -> None:
        nonlocal truncated, stop_reason
        if stat_mode == "hp":
            branch_out = run_branched_hp_dfs(
                pos_map=pos_map,
                positions=positions,
                target=float(target),
                tolerance=float(tolerance),
                base_stat=base_stat,
                base_hp=float(base_panel),
                bounds_fn=bounds_fn,
                process_leaf=_wrapped_process_leaf,
                should_cancel=should_cancel,
                on_progress=push_progress,
                progress_interval=_LEGACY_PROGRESS_INTERVAL,
                on_trial=_on_branched_trial,
                on_leaf_begin=_on_leaf_begin,
            )
        else:
            branch_out = run_branched_layer_dfs(
                pos_map=pos_map,
                positions=positions,
                stat_mode=stat_mode,
                target=float(target),
                tolerance=float(tolerance),
                base_stat=base_stat,
                base_panel=float(base_panel),
                bounds_fn=bounds_fn,
                process_leaf=_wrapped_process_leaf,
                should_cancel=should_cancel,
                on_progress=push_progress,
                progress_interval=_LEGACY_PROGRESS_INTERVAL,
                on_trial=_on_branched_trial,
                on_leaf_begin=_on_leaf_begin,
            )
        state.tried = branch_out.tried
        stop_reason = branch_out.stop
        truncated = branch_out.truncated
        process_logs.extend(branch_out.branch_logs)
        process_logs.append(
            f"套装分支: 运行 {branch_out.branches_run}，跳过 {branch_out.branches_skipped}"
        )

    def _run_brute_force_dfs() -> None:
        nonlocal truncated, stop_reason
        prune_layers = stat_mode == "hp"

        def dfs(depth: int, partial: list[Any], partial_lo: float, partial_hi: float) -> bool:
            nonlocal truncated, stop_reason

            if callable(should_cancel) and should_cancel():
                truncated = True
                stop_reason = "manual_cancel"
                return True

            if depth == n:
                state.tried += 1
                if _wrapped_process_leaf(tuple(partial)):
                    stop_reason = "first_match_found"
                    return True
                return False

            if prune_layers:
                rem_lo = sum(slot_min[depth:])
                rem_hi = sum(slot_max[depth:])
                cur_lo = base_stat + partial_lo + rem_lo
                cur_hi = base_stat + partial_hi + rem_hi
                if not intervals_intersect(cur_lo, cur_hi, target, tolerance):
                    return False

            for art in slot_lists[depth]:
                lo, hi = bounds_fn(art)
                partial.append(art)
                if dfs(depth + 1, partial, partial_lo + lo, partial_hi + hi):
                    partial.pop()
                    return True
                partial.pop()
                if stop_reason == "manual_cancel":
                    return True
            return False

        dfs(0, [], 0.0, 0.0)

    if use_bnb:
        if not pool_globally_unreachable:
            _run_branched()
        else:
            process_logs.append("目标超出整池可达范围，不返回最近组合")
    else:
        _run_brute_force_dfs()

    return state.tried, truncated, stop_reason


def finalize_shengxian_progress(
    *,
    tried: int,
    total_unique_combinations: int,
    stop_reason: str,
    hit_count: int,
    target: float | None = None,
    found_total: float | None = None,
    closest_diff: float,
    closest_total: float | None,
    process_logs: list[str],
    on_progress: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    """与生命搜索一致的最终 progress meta 与停止日志。"""
    final_dc = min(tried, total_unique_combinations)
    enum_prog = min(1.0, final_dc / max(total_unique_combinations, 1))
    progress_meta: dict[str, Any] = {
        "enumeration_progress": enum_prog,
        "tried": tried,
        "display_count": final_dc,
        "unique_hits": hit_count,
    }
    if found_total is not None and target is not None:
        progress_meta["best_total"] = float(found_total)
        progress_meta["best_diff"] = abs(float(found_total) - float(target))
    else:
        attach_search_best(
            progress_meta,
            closest_diff=closest_diff,
            closest_total=closest_total,
        )
    reason_txt = _stop_reason_zh(stop_reason)
    process_logs.append(
        f"搜索停止原因: {reason_txt}\n"
        f"已处理 {final_dc} / {total_unique_combinations} 个组合，找到 {hit_count} 条结果。"
    )
    if callable(on_progress):
        on_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": tried,
                "process_log_line": process_logs[-1] if process_logs else "",
            }
        )
    return progress_meta
