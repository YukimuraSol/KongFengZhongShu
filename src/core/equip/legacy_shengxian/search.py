from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..artifact_card_display import attach_merge_piece_meta, piece_display_fields
from ..artifact_meta import enrich_piece_card_fields
from ..closest_combo import closer
from ..atk_def_bundle import round_half_up
from ..bnb_prune import bounds_list_span, intervals_intersect, sort_by_target_proximity, sort_positions_wide_to_narrow
from ..set_branch_bounds import pool_stat_bounds
from ..shengxian_branched_search import finalize_shengxian_progress, run_shengxian_branched_search
from .bennett import calculate_all_hp_variants, calculate_bennett_hp
from .constants import JSON_TO_UI_SLOT, POSITION_TRANSLATION
from .display_format import format_artifact_info
from ..progress_stop import ProgressState, attach_search_best
from ..search_engine import _multi_mode_zh


@dataclass
class ShengxianHit:
    key: str
    hp: float
    diff: float
    total_count: int
    is_multi: bool
    set_effects: list[str]
    hp_variants: list[float]
    artifact_lines: list[str]
    pieces: list[dict[str, Any]]


@dataclass
class ShengxianSearchOutput:
    results: list[ShengxianHit]
    tried: int
    truncated: bool
    stop_reason: str
    progress_meta: dict[str, Any]
    process_logs: list[str]


def _deep_copy_combination(combination: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [copy.deepcopy(a) for a in combination]


def _pieces_for_result(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for a in artifacts:
        pos = a.get("position", "")
        slot = JSON_TO_UI_SLOT.get(pos, pos)
        piece = {
            "slot": slot,
            "name": str(a.get("merge_key", "")),
            "score": float(a.get("total_hp_contribution", 0)),
            "set_name": str(a.get("original_set", "")),
        }
        piece.update(piece_display_fields(a))
        enrich_piece_card_fields(piece, slot)
        merge_line = format_artifact_info(a, show_multi=True)
        attach_merge_piece_meta(piece, a, slot, merge_line)
        out.append(piece)
    return out


def _artifact_lines_for_result(artifacts: list[dict[str, Any]]) -> list[str]:
    position_order = ["flower", "feather", "sand", "cup", "head"]
    by_pos: dict[str, dict[str, Any]] = {}
    for art in artifacts:
        by_pos[str(art.get("position", ""))] = art
    lines: list[str] = []
    for pos in position_order:
        art = by_pos.get(pos)
        if art is None:
            continue
        lines.append(format_artifact_info(art, show_multi=True))
    return lines


def _artifact_hp_delta_bounds(art: dict[str, Any], base_hp: float) -> tuple[float, float]:
    static_base = float(art.get("hp_static_total", 0) or 0) - float(art.get("hp_static", 0) or 0)
    pct_main = float(art.get("hp_percent_main", 0) or 0)
    static_cands = list(art.get("hp_static_candidates") or [art.get("hp_static", 0) or 0])
    pct_cands = list(art.get("hp_percent_sub_candidates") or [art.get("hp_percent_sub", 0) or 0])
    lo_s = min(float(x) for x in static_cands)
    hi_s = max(float(x) for x in static_cands)
    lo_p = min(float(x) for x in pct_cands)
    hi_p = max(float(x) for x in pct_cands)
    lo = static_base + lo_s + base_hp * (pct_main + lo_p)
    hi = static_base + hi_s + base_hp * (pct_main + hi_p)
    return lo, hi


def _slot_bounds(arts: list[dict[str, Any]], base_hp: float) -> tuple[float, float]:
    if not arts:
        return 0.0, 0.0
    bounds = [_artifact_hp_delta_bounds(a, base_hp) for a in arts]
    return min(b[0] for b in bounds), max(b[1] for b in bounds)


def _combo_multi_excluded(combo: tuple[Any, ...], multi_mode: str) -> bool:
    if multi_mode != "exclude":
        return False
    for a in combo:
        if a.get("has_multi_solution", False):
            return True
    return False


def _make_hit(
    key: str,
    hp: float,
    target_hp: float,
    combo: list[dict[str, Any]],
    combo_count: int,
    is_multi: bool,
    set_effects: list[str],
    hp_variants: list[float],
) -> ShengxianHit:
    return ShengxianHit(
        key=key,
        hp=hp,
        diff=float(hp) - float(target_hp),
        total_count=combo_count,
        is_multi=is_multi,
        set_effects=list(set_effects),
        hp_variants=hp_variants,
        artifact_lines=_artifact_lines_for_result(combo),
        pieces=_pieces_for_result(combo),
    )


def run_shengxian_hp_search(
    *,
    positions_legacy: dict[str, bool],
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    base_hp: float,
    no_artifact_hp: float,
    target_hp: float,
    tolerance: float,
    hp_step: float,
    algorithm: Literal["optimized", "brute_force"],
    auto_step: float,
    multi_solution_mode: Literal["exclude", "skip_progress", "normal"],
    mode: Literal["single", "all", "best-n"],
    best_n: int,
    include_hp_percent: bool = True,
    result_precision: float = 0.01,
    on_progress: Callable[..., None] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    prelude_logs: list[str] | None = None,
) -> ShengxianSearchOutput:
    """圣显生命枚举：首命中即停 + 可选 BnB 剪枝。"""
    del hp_step, auto_step, include_hp_percent

    process_logs: list[str] = list(prelude_logs or [])
    positions_to_calculate = {
        pos: arts for pos, arts in artifacts_by_position.items() if positions_legacy.get(pos, True)
    }
    multi_mode = multi_solution_mode
    if multi_mode == "exclude":
        pre_filtered_multi = 0
        for pos, arts in list(positions_to_calculate.items()):
            kept = [a for a in arts if not bool(a.get("has_multi_solution", False))]
            pre_filtered_multi += max(0, len(arts) - len(kept))
            positions_to_calculate[pos] = kept if kept else arts
        if pre_filtered_multi > 0:
            process_logs.append(
                f"多解性部位处理=完全不采用：已在枚举前过滤 {pre_filtered_multi} 条多解条目"
            )

    width_by_pos = {
        pos: bounds_list_span([_artifact_hp_delta_bounds(a, base_hp) for a in arts])
        for pos, arts in positions_to_calculate.items()
    }
    count_by_pos = {pos: len(positions_to_calculate[pos]) for pos in positions_to_calculate}
    positions = sort_positions_wide_to_narrow(
        list(positions_to_calculate.keys()),
        width_by_pos=width_by_pos,
        count_by_pos=count_by_pos,
    )
    lists = [positions_to_calculate[pos] for pos in positions]

    total_unique_combinations = 1
    for lst in lists:
        total_unique_combinations *= len(lst)

    state = ProgressState(total=total_unique_combinations)

    rp = float(result_precision) if result_precision is not None else 0.01
    if rp <= 0:
        rp = 0.01
    precision_text = f"{rp:.10f}".rstrip("0").rstrip(".")
    if "." in precision_text:
        result_decimals = min(6, max(0, len(precision_text.split(".", 1)[1])))
    else:
        result_decimals = 0

    use_bnb = algorithm != "brute_force"
    base_stat = float(no_artifact_hp)
    need = float(target_hp) - base_stat

    slot_lists: list[list[dict[str, Any]]] = []
    slot_min: list[float] = []
    slot_max: list[float] = []
    for lst in lists:
        sorted_lst = sort_by_target_proximity(
            lst,
            lambda a: _artifact_hp_delta_bounds(a, base_hp)[0],
            need,
        )
        slot_lists.append(sorted_lst)
        lo, hi = _slot_bounds(sorted_lst, base_hp)
        slot_min.append(lo)
        slot_max.append(hi)

    process_logs.append(
        f"总唯一组合数: {total_unique_combinations}\n"
        f"多解性部位处理模式: {_multi_mode_zh(multi_solution_mode)}\n"
        f"命中条件: |生命 - {target_hp}| <= {tolerance}，首命中即停"
    )
    if algorithm == "brute_force":
        process_logs.append("算法模式: 纯枚举（遍历所有组合）")
    else:
        process_logs.append("算法模式: 优化（套装分支 + 区间剪枝）")
        process_logs.append("按散件 / 单2件套 / 2+2 分支筛池；套装加成精确计入剪枝上界")

    pool_lo, pool_hi = pool_stat_bounds(
        positions_to_calculate,
        positions,
        base_stat=base_stat,
        stat_mode="hp",
        base_panel=float(base_hp),
        piece_bounds_fn=lambda art: _artifact_hp_delta_bounds(art, base_hp),
    )
    pool_globally_unreachable = not intervals_intersect(
        pool_lo, pool_hi, float(target_hp), float(tolerance)
    )
    if use_bnb and pool_globally_unreachable:
        process_logs.append(
            f"整池可达区间约 [{pool_lo:.2f}, {pool_hi:.2f}] 与目标带无交集，跳过搜索"
        )

    if callable(on_progress):
        on_progress(
            {
                "enumeration_progress": 0.0,
                "tried": 0,
                "process_logs": list(process_logs),
            }
        )

    truncated = False
    stop_reason = "no_match"
    found_hit: ShengxianHit | None = None
    closest_hit: ShengxianHit | None = None
    closest_diff = float("inf")

    def _push_progress(meta: dict[str, Any]) -> None:
        attach_search_best(
            meta,
            closest_diff=closest_diff,
            closest_total=float(closest_hit.hp) if closest_hit is not None else None,
        )
        if callable(on_progress):
            on_progress(meta)

    def _record_first_match(combo: tuple[Any, ...], hp: float, set_effects: list[str], *, emit: bool = True) -> ShengxianHit:
        combo_count = 1
        has_multi = False
        for artifact in combo:
            combo_count *= int(artifact.get("count", 1))
            if artifact.get("has_multi_solution", False):
                has_multi = True

        hp_actual = round_half_up(float(hp), result_decimals)
        if has_multi:
            all_variants = calculate_all_hp_variants(list(combo), base_hp, no_artifact_hp)
            chosen_hp = hp
            for variant_hp in all_variants:
                if abs(variant_hp - target_hp) <= tolerance:
                    chosen_hp = variant_hp
                    break
            hp_actual = round_half_up(float(chosen_hp), result_decimals)
            key = f"multi_{hp_actual}"
            variants = sorted({round(v, 2) for v in all_variants})
            combo_copy = _deep_copy_combination(combo)
        else:
            key = f"single_{hp_actual}"
            variants = [round(float(hp), 2)]
            combo_copy = _deep_copy_combination(combo)

        hit = _make_hit(
            key,
            float(chosen_hp if has_multi else hp),
            target_hp,
            combo_copy,
            combo_count,
            has_multi,
            set_effects,
            variants,
        )
        if emit and callable(on_result):
            on_result(
                {
                    "key": hit.key,
                    "total": hit.hp,
                    "diff": hit.diff,
                    "total_count": hit.total_count,
                    "is_multi": hit.is_multi,
                    "set_effects": hit.set_effects,
                    "hp_variants": hit.hp_variants,
                    "artifact_lines": hit.artifact_lines,
                    "pieces": hit.pieces,
                }
            )
        return hit

    def _process_leaf(combo: tuple[Any, ...]) -> bool:
        nonlocal truncated, stop_reason, found_hit, closest_hit, closest_diff

        if _combo_multi_excluded(combo, multi_mode):
            return False

        hp, set_effects = calculate_bennett_hp(combo, base_hp, no_artifact_hp)
        if abs(hp - target_hp) <= tolerance:
            found_hit = _record_first_match(combo, hp, list(set_effects or []))
            stop_reason = "first_match_found"
            return True

        d = abs(float(hp) - float(target_hp))
        if closer(d, closest_diff):
            closest_diff = d
            closest_hit = _record_first_match(combo, hp, list(set_effects or []), emit=False)
            if callable(on_progress):
                _push_progress({"tried": state.tried})

        return False

    state.tried, truncated, stop_reason = run_shengxian_branched_search(
        state=state,
        pos_map=positions_to_calculate,
        positions=positions,
        slot_lists=slot_lists,
        slot_min=slot_min,
        slot_max=slot_max,
        stat_mode="hp",
        target=float(target_hp),
        tolerance=float(tolerance),
        base_stat=base_stat,
        base_panel=float(base_hp),
        bounds_fn=lambda a: _artifact_hp_delta_bounds(a, base_hp),
        process_leaf=_process_leaf,
        use_bnb=use_bnb,
        pool_globally_unreachable=pool_globally_unreachable,
        total_unique_combinations=total_unique_combinations,
        process_logs=process_logs,
        push_progress=_push_progress,
        should_cancel=should_cancel,
    )

    if use_bnb and not pool_globally_unreachable and found_hit is None and not truncated:
        if closest_hit is not None:
            process_logs.append("容差内未命中，沿用阶段一记录的最近组合")
        else:
            process_logs.append("容差内未命中，阶段一未记录最近组合")

    hits: list[ShengxianHit] = []
    if found_hit is not None:
        hits = [found_hit]
    elif closest_hit is not None:
        hits = [closest_hit]
    if mode == "single":
        hits = hits[:1]
    elif mode == "best-n":
        hits = hits[:best_n]

    progress_meta = finalize_shengxian_progress(
        tried=state.tried,
        total_unique_combinations=total_unique_combinations,
        stop_reason=stop_reason,
        hit_count=len(hits),
        target=float(target_hp),
        found_total=float(found_hit.hp) if found_hit is not None else None,
        closest_diff=closest_diff,
        closest_total=float(closest_hit.hp) if closest_hit is not None else None,
        process_logs=process_logs,
        on_progress=on_progress,
    )

    return ShengxianSearchOutput(
        results=hits,
        tried=state.tried,
        truncated=truncated,
        stop_reason=stop_reason,
        progress_meta=progress_meta,
        process_logs=process_logs,
    )


def build_prelude_logs_from_process(
    artifacts_by_position: dict[str, list[dict[str, Any]]],
    positions_to_calc: list[str],
    filter_info: dict[str, Any],
) -> list[str]:
    """合并后条目预览（简化版，对齐圣显结构）。"""
    lines: list[str] = []
    if filter_info.get("filtered_chars"):
        lines.append("\n=== 角色过滤信息 ===")
        lines.append(f"回避角色: {', '.join(filter_info['filtered_chars'])}")
        lines.append(f"被过滤的圣遗物数量: {filter_info['filtered_count']}")
    lines.append(f"要计算的部位: {positions_to_calc}")
    lines.append("\n=== 合并后的圣遗物条目 ===")
    for pos in positions_to_calc:
        arts = artifacts_by_position.get(pos, [])
        pos_cn = POSITION_TRANSLATION.get(pos, pos)
        lines.append(f"\n【{pos_cn}】共 {len(arts)} 个唯一条目:")
        for art in arts[:15]:
            if art.get("main_type") == "empty":
                lines.append(f"  - (空)")
                continue
            st = art.get("original_set", "")
            lv = art.get("level", 0)
            ct = art.get("count", 1)
            lines.append(f"  - {st} Lv{lv} merge={art.get('merge_key','')} x{ct}")
        if len(arts) > 15:
            lines.append(f"  ... 还有 {len(arts) - 15} 个")
    return lines
