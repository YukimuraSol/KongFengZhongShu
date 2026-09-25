from dataclasses import dataclass
from typing import Literal

from .bnb_prune import sort_by_target_proximity
from .progress_stop import ProgressState
from .solver import Candidate, EquipSolution, apply_set_bonus, merge_key

_LEGACY_PROGRESS_INTERVAL = 10000

_MULTI_MODE_ZH = {
    "exclude": "完全不采用（跳过多解性组合）",
    "skip_progress": "采用但不记录进度",
    "normal": "正常采用（计入进度）",
}

_SLOT_ZH = {
    "flower": "花",
    "plume": "羽",
    "sands": "沙",
    "goblet": "杯",
    "circlet": "头",
}

_STOP_REASON_ZH = {
    "finished": "完成所有组合",
    "manual_cancel": "用户手动停止",
    "first_match_found": "已找到容差内组合",
    "no_match": "容差内未找到组合",
}


def _format_slot_counts(slot_counts: dict[str, int]) -> str:
    parts = []
    for k in sorted(slot_counts.keys()):
        zh = _SLOT_ZH.get(k, k)
        parts.append(f"{zh}:{slot_counts[k]}")
    return "，".join(parts) if parts else ""


def _stop_reason_zh(code: str) -> str:
    return _STOP_REASON_ZH.get(code, code)


def _multi_mode_zh(mode: str) -> str:
    return _MULTI_MODE_ZH.get(mode, mode)


def _max_set_bonus_upper(bonus_by_set: dict[str, float], n_slots: int) -> float:
    if not bonus_by_set:
        return 0.0
    # 五件最多 2 个两件套加成（保守上界）
    vals = sorted(bonus_by_set.values(), reverse=True)
    pairs = max(0, n_slots // 2)
    return sum(vals[:pairs])


@dataclass
class SearchOutput:
    results: list[EquipSolution]
    tried: int
    truncated: bool
    stop_reason: str
    progress_meta: dict
    process_logs: list[str]


def run_search(
    pools: dict[str, list[Candidate]],
    target: float,
    mode: Literal["single", "all", "best-n"],
    best_n: int,
    max_diff: float,
    bonus_by_set: dict[str, float],
    algorithm: Literal["optimized", "brute_force"] = "optimized",
    step: float = 1.0,
    target_percent: float = 90.0,
    auto_step: float = 0.5,
    multi_solution_mode: Literal["exclude", "skip_progress", "normal"] = "normal",
    on_progress=None,
    should_cancel=None,
) -> SearchOutput:
    del step, target_percent, auto_step  # 已废弃，保留参数兼容旧调用

    slots = sorted(pools.keys())
    use_bnb = algorithm == "optimized"
    slot_lists: list[list[Candidate]] = []
    for s in slots:
        lst = list(pools[s])
        if use_bnb:
            lst = sort_by_target_proximity(lst, lambda c: c.score, target)
        slot_lists.append(lst)

    total = 1
    for items in slot_lists:
        total *= max(1, len(items))

    process_logs: list[str] = [
        f"总组合数: {total}",
        f"多解性部位处理模式: {_multi_mode_zh(multi_solution_mode)}",
        "算法模式: 优化（排序+剪枝）" if use_bnb else "算法模式: 纯枚举",
        f"命中条件: |属性值 - {target}| <= {max_diff}，首命中即停",
    ]

    state = ProgressState(total=total)
    truncated = False
    stop_reason = "no_match"
    results: list[EquipSolution] = []
    max_bonus_pad = _max_set_bonus_upper(bonus_by_set, len(slots))

    slot_min = []
    slot_max = []
    for lst in slot_lists:
        if lst:
            slot_min.append(min(c.score for c in lst))
            slot_max.append(max(c.score for c in lst))
        else:
            slot_min.append(0.0)
            slot_max.append(0.0)

    if callable(on_progress):
        on_progress(
            {
                "enumeration_progress": 0.0,
                "tried": 0,
                "process_logs": list(process_logs),
            }
        )

    n = len(slot_lists)
    next_milestone = _LEGACY_PROGRESS_INTERVAL

    def dfs(depth: int, partial: list[Candidate], partial_score: float) -> EquipSolution | None:
        nonlocal truncated, stop_reason, next_milestone

        if callable(should_cancel) and should_cancel():
            truncated = True
            stop_reason = "manual_cancel"
            return None

        if depth == n:
            state.tried += 1
            if state.tried >= next_milestone:
                enum_prog = min(1.0, state.tried / max(total, 1))
                if callable(on_progress):
                    on_progress(
                        {
                            "enumeration_progress": enum_prog,
                            "tried": state.tried,
                            "process_log_line": f"已处理 {state.tried} / {total}",
                        }
                    )
                while next_milestone <= state.tried:
                    next_milestone += _LEGACY_PROGRESS_INTERVAL
            pieces = list(partial)
            if multi_solution_mode == "exclude" and any(
                getattr(p, "has_multi", False) for p in pieces
            ):
                return None
            total_score = apply_set_bonus(sum(p.score for p in pieces), pieces, bonus_by_set)
            diff = abs(total_score - target)
            if diff > max_diff:
                return None
            key = merge_key(pieces)
            sol = EquipSolution(key=key, total=total_score, diff=diff, pieces=pieces)
            stop_reason = "first_match_found"
            return sol

        if use_bnb:
            rem_lo = sum(slot_min[depth:])
            rem_hi = sum(slot_max[depth:]) + max_bonus_pad
            from .bnb_prune import intervals_intersect

            if not intervals_intersect(
                partial_score + rem_lo,
                partial_score + rem_hi,
                target,
                max_diff,
            ):
                return None

        for cand in slot_lists[depth]:
            partial.append(cand)
            hit = dfs(depth + 1, partial, partial_score + cand.score)
            partial.pop()
            if hit is not None:
                return hit
            if stop_reason == "manual_cancel":
                return None

        return None

    hit = dfs(0, [], 0.0)
    if hit is not None:
        results = [hit]
    elif stop_reason != "manual_cancel":
        stop_reason = "no_match"

    if mode == "single":
        results = results[:1]
    elif mode == "best-n":
        results = results[:best_n]

    enum_prog = min(1.0, state.tried / max(total, 1))
    progress_meta = {
        "enumeration_progress": enum_prog,
        "tried": state.tried,
        "display_count": min(state.tried, total),
        "unique_hits": len(results),
    }
    reason_txt = _stop_reason_zh(stop_reason)
    process_logs.append(
        f"搜索停止原因: {reason_txt}\n"
        f"已处理 {state.tried} / {total} 个组合，找到 {len(results)} 条结果。"
    )
    if callable(on_progress):
        on_progress(
            {
                "enumeration_progress": enum_prog,
                "tried": state.tried,
                "process_log_line": process_logs[-1],
            }
        )
    return SearchOutput(
        results=results,
        tried=state.tried,
        truncated=truncated,
        stop_reason=stop_reason,
        progress_meta=progress_meta,
        process_logs=process_logs,
    )
