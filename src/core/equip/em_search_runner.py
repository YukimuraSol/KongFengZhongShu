"""元素精通配装枚举（加和模型）：首命中即停 + 可选 BnB 剪枝。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Optional

from core.equip.artifact_card_display import attach_merge_piece_meta, piece_display_fields
from core.equip.artifact_meta import enrich_piece_card_fields
from core.equip.closest_combo import closer, make_closest_payload
from core.equip.atk_def_bundle import (
    ALL_STAR_RATINGS,
    AtkDefEquipEngine,
    POSITION_CN,
    POSITION_ORDER,
    has_multi_solution,
    round_half_up,
    sort_combo_by_position_order,
)
from core.equip.bnb_prune import (
    bounds_list_span,
    intervals_intersect,
    sort_by_target_proximity,
    sort_positions_wide_to_narrow,
)
from core.equip.set_branch_bounds import scatter_set_bonus_upper
from core.equip.progress_stop import ProgressState, attach_search_best
from core.equip.shengxian_branched_search import finalize_shengxian_progress, run_shengxian_branched_search
from core.equip.search_engine import _multi_mode_zh
from core.equip.em_equip_engine import (
    SET_TWO_PIECE_EM_80,
    calculate_em_set_bonus,
    final_total_em,
    format_em_artifact_line,
    process_artifacts_for_em,
)

from core.equip.disable_filter import filter_artifacts_by_disable


@dataclass
class EmSearchRow:
    key: str
    total: float
    diff: float
    total_count: int
    is_multi: bool
    hp_variants: list[float]
    artifact_lines: list[str]
    pieces: list[dict[str, Any]]
    set_effects: list[str]


def _slot_ui(pos: str) -> str:
    return {
        "flower": "flower",
        "feather": "plume",
        "sand": "sands",
        "cup": "goblet",
        "head": "circlet",
    }.get(pos, "flower")


def _pieces_from_combo_em(combo: tuple[Any, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in sort_combo_by_position_order(combo):
        pos = str(e.get("position") or "flower")
        slot = _slot_ui(pos)
        score = float(e.get("em_flat", 0))
        name = str(e.get("merge_key") or "artifact")[:120]
        set_name = str(e.get("original_set") or "")
        piece = {"slot": slot, "name": name, "score": score, "set_name": set_name}
        piece.update(piece_display_fields(e))
        enrich_piece_card_fields(piece, slot)
        merge_line = format_em_artifact_line(e, show_multi=True)
        attach_merge_piece_meta(piece, e, slot, merge_line)
        out.append(piece)
    return out


def _lines_from_combo_em(combo: tuple[Any, ...]) -> list[str]:
    return [f"  {format_em_artifact_line(e, show_multi=True)}" for e in sort_combo_by_position_order(combo)]


def _em_flat_bounds(entry: Any) -> tuple[float, float]:
    cands = entry.get("em_flat_candidates") or ()
    if cands:
        vals = [float(x) for x in cands]
        return min(vals), max(vals)
    v = float(entry.get("em_flat") or 0)
    return v, v


def _em_flat_point(entry: Any) -> float:
    return float(entry.get("em_flat") or 0)


def _pool_em_stat_bounds(
    pos_map: dict[str, list[Any]],
    positions: list[str],
    base_stat: float,
) -> tuple[float, float]:
    """整池精通可达下界/上界（含最多两套精通二件套 flat 加成）。"""
    piece_lo = sum(min(_em_flat_bounds(e)[0] for e in pos_map[p]) for p in positions)
    piece_hi = sum(max(_em_flat_bounds(e)[1] for e in pos_map[p]) for p in positions)
    _bonus_lo, bonus_hi = scatter_set_bonus_upper(pos_map, stat_mode="em", base_panel=0.0)
    return float(base_stat) + piece_lo, float(base_stat) + piece_hi + bonus_hi


def _combo_multi_excluded(combo: tuple[Any, ...], multi_mode: str) -> bool:
    if multi_mode != "exclude":
        return False
    for a in combo:
        if has_multi_solution(a.get("em_flat_candidates") or ()):
            return True
    return False


def _em_item_to_full_payload(k: str, item: dict[str, Any], result_decimals: int) -> dict[str, Any]:
    combo = item["combo"]
    val = float(item["val"])
    variants = [float(x) for x in (item.get("variants") or [val])]
    variants_sorted = sorted({round_half_up(v, result_decimals) for v in variants})
    lines = _lines_from_combo_em(combo)
    pieces = _pieces_from_combo_em(combo)
    _set_em, set_lines = calculate_em_set_bonus(combo)
    return {
        "key": k,
        "total": val,
        "diff": float(item.get("diff") or 0),
        "total_count": int(item.get("count") or 1),
        "is_multi": bool(item.get("has_multi_solution")),
        "hp_variants": variants_sorted,
        "artifact_lines": lines,
        "pieces": pieces,
        "set_effects": list(set_lines),
    }


def run_em_equip_search(
    *,
    artifact_json: dict[str, Any],
    target: float,
    no_artifact_em: float,
    extra_base_em: float,
    tolerance: float,
    hp_step: float,
    result_precision: float,
    target_percent: float = 90.0,
    algorithm: str,
    multi_solution_mode: str,
    positions_enabled: dict[str, bool],
    best_n: int,
    auto_step: float = 0.5,
    include_em_main: bool = True,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    disabled_artifacts: list[str] | None = None,
    disabled_loose_pieces: list[str] | None = None,
    allowed_stars: frozenset[int] | None = None,
) -> tuple[list[EmSearchRow], int, bool, str, dict[str, Any], list[str]]:
    del hp_step, target_percent, auto_step, best_n

    is_bf = algorithm == "brute_force"
    use_bnb = not is_bf
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    stars = allowed_stars if allowed_stars is not None else ALL_STAR_RATINGS

    arts, _finfo = process_artifacts_for_em(
        engine,
        artifact_json,
        allowed_stars=stars,
        include_em_main=include_em_main,
    )
    arts = filter_artifacts_by_disable(
        arts,
        disabled_artifacts=disabled_artifacts,
        disabled_loose_pieces=disabled_loose_pieces,
        format_line=lambda art: format_em_artifact_line(art, show_multi=True),
    )

    multi_mode = multi_solution_mode if multi_solution_mode in ("exclude", "skip_progress", "normal") else "exclude"
    positions_to_calc = [p for p in POSITION_ORDER if positions_enabled.get(p, True)]
    if not positions_to_calc:
        return [], 0, False, "no_positions", {"enumeration_progress": 1.0, "tried": 0}, ["至少选一个部位。"]

    pos_map: dict[str, list] = {p: arts[p] for p in positions_to_calc}
    if multi_mode == "exclude":
        for p in positions_to_calc:
            before = pos_map[p]
            kept = [e for e in before if not bool(e.get("has_multi_solution"))]
            pos_map[p] = kept if kept else before

    base_stat = float(no_artifact_em) + float(extra_base_em)

    slot_bounds_by_pos: dict[str, list[tuple[float, float]]] = {
        p: [_em_flat_bounds(e) for e in pos_map[p]] for p in positions_to_calc
    }
    width_by_pos = {p: bounds_list_span(slot_bounds_by_pos[p]) for p in positions_to_calc}
    count_by_pos = {p: len(pos_map[p]) for p in positions_to_calc}
    positions_to_calc = sort_positions_wide_to_narrow(
        positions_to_calc,
        width_by_pos=width_by_pos,
        count_by_pos=count_by_pos,
    )

    lists = [list(pos_map[p]) for p in positions_to_calc]

    total = 1
    for lst in lists:
        total *= len(lst)
    total_unique_combinations = total
    state = ProgressState(total=total_unique_combinations)
    need = float(target) - base_stat
    slot_lists: list[list[Any]] = []
    slot_min: list[float] = []
    slot_max: list[float] = []
    for lst in lists:
        sorted_lst = sort_by_target_proximity(lst, lambda e: _em_flat_bounds(e)[0], need)
        slot_lists.append(sorted_lst)
        piece_bounds = [_em_flat_bounds(e) for e in sorted_lst]
        slot_min.append(min(b[0] for b in piece_bounds))
        slot_max.append(max(b[1] for b in piece_bounds))

    pool_lo, pool_hi = _pool_em_stat_bounds(pos_map, positions_to_calc, base_stat)
    pool_globally_unreachable = not intervals_intersect(
        pool_lo, pool_hi, float(target), float(tolerance)
    )

    precision_text = f"{result_precision:.10f}".rstrip("0").rstrip(".")
    if "." in precision_text:
        result_decimals = min(6, max(0, len(precision_text.split(".", 1)[1])))
    else:
        result_decimals = 0

    process_logs: list[str] = [
        f"总唯一组合数: {total_unique_combinations}\n"
        f"多解性部位处理模式: {_multi_mode_zh(multi_solution_mode)}\n"
        f"命中条件: |精通 - {target}| <= {tolerance}，首命中即停",
    ]
    if algorithm == "brute_force":
        process_logs.append("算法模式: 纯枚举（遍历所有组合）")
    else:
        process_logs.append("算法模式: 优化（套装分支 + 区间剪枝）")
        process_logs.append("按散件 / 单2件套 / 2+2 分支筛池；套装加成精确计入剪枝上界")
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
    stop = "no_match"
    found_item: dict[str, Any] | None = None
    closest_item: dict[str, Any] | None = None
    closest_diff = float("inf")

    def _push_progress(meta: dict[str, Any]) -> None:
        attach_search_best(
            meta,
            closest_diff=closest_diff,
            closest_total=float(closest_item["val"]) if closest_item else None,
        )
        if callable(on_progress):
            on_progress(meta)

    def _record_closest_value(combo: tuple[Any, ...], v: float) -> None:
        nonlocal closest_item, closest_diff
        combo_count = 1
        has_multi = False
        for a in combo:
            combo_count *= int(a.get("count") or 1)
            if has_multi_solution(a.get("em_flat_candidates") or ()):
                has_multi = True
        d = abs(v - float(target))
        if not closer(d, closest_diff):
            return
        closest_diff = d
        closest_item = make_closest_payload(
            key_prefix="closest_em_",
            val=float(v),
            diff=float(v) - float(target),
            combo=tuple(combo),
            combo_count=combo_count,
            has_multi=has_multi,
            variants=[float(v)],
        )
        if callable(on_progress):
            _push_progress({"tried": state.tried})

    def stat_of(combo: tuple[Any, ...]) -> float:
        return final_total_em(no_artifact_em, extra_base_em, combo)

    def consider_closest(combo: tuple[Any, ...], v: float) -> None:
        if _combo_multi_excluded(combo, multi_mode):
            return
        _record_closest_value(combo, v)

    def _process_leaf(combo: tuple[Any, ...]) -> bool:
        nonlocal stop, found_item
        if _combo_multi_excluded(combo, multi_mode):
            return False
        v = stat_of(combo)
        if abs(v - float(target)) <= float(tolerance):
            combo_count = 1
            has_multi = False
            for a in combo:
                combo_count *= int(a.get("count") or 1)
                if has_multi_solution(a.get("em_flat_candidates") or ()):
                    has_multi = True
            sk = round_half_up(v, result_decimals)
            key = f"em_{sk}"
            found_item = {
                "val": v,
                "combo": tuple(copy.deepcopy(x) for x in combo),
                "count": combo_count,
                "diff": float(v) - float(target),
                "variants": [v],
                "has_multi_solution": has_multi,
            }
            stop = "first_match_found"
            if callable(on_result):
                on_result(_em_item_to_full_payload(key, found_item, result_decimals))
            return True
        consider_closest(combo, v)
        return False

    state.tried, truncated, stop = run_shengxian_branched_search(
        state=state,
        pos_map=pos_map,
        positions=positions_to_calc,
        slot_lists=slot_lists,
        slot_min=slot_min,
        slot_max=slot_max,
        stat_mode="em",
        target=float(target),
        tolerance=float(tolerance),
        base_stat=base_stat,
        base_panel=0.0,
        bounds_fn=_em_flat_bounds,
        process_leaf=_process_leaf,
        use_bnb=use_bnb,
        pool_globally_unreachable=pool_globally_unreachable,
        total_unique_combinations=total_unique_combinations,
        process_logs=process_logs,
        push_progress=_push_progress,
        should_cancel=should_cancel,
    )

    if use_bnb and not pool_globally_unreachable and not found_item and not truncated:
        if closest_item is not None:
            process_logs.append("容差内未命中，沿用阶段一记录的最近组合")
        else:
            process_logs.append("容差内未命中，阶段一未记录最近组合")

    rows: list[EmSearchRow] = []
    if found_item:
        k = f"em_{round_half_up(float(found_item['val']), result_decimals)}"
        combo = found_item["combo"]
        val = float(found_item["val"])
        variants_sorted = sorted({round_half_up(val, result_decimals)})
        lines = _lines_from_combo_em(combo)
        pieces = _pieces_from_combo_em(combo)
        _set_em, set_lines = calculate_em_set_bonus(combo)
        rows.append(
            EmSearchRow(
                key=k,
                total=val,
                diff=float(found_item.get("diff") or 0),
                total_count=int(found_item.get("count") or 1),
                is_multi=bool(found_item.get("has_multi_solution")),
                hp_variants=variants_sorted,
                artifact_lines=lines,
                pieces=pieces,
                set_effects=list(set_lines),
            )
        )
    elif closest_item:
        k = f"closest_em_{round_half_up(float(closest_item['val']), result_decimals)}"
        combo = tuple(copy.deepcopy(x) for x in closest_item["combo"])
        val = float(closest_item["val"])
        variants_sorted = sorted({round_half_up(val, result_decimals)})
        lines = _lines_from_combo_em(combo)
        pieces = _pieces_from_combo_em(combo)
        _set_em, set_lines = calculate_em_set_bonus(combo)
        rows.append(
            EmSearchRow(
                key=k,
                total=val,
                diff=float(closest_item.get("diff") or 0),
                total_count=int(closest_item.get("count") or 1),
                is_multi=bool(closest_item.get("has_multi_solution")),
                hp_variants=variants_sorted,
                artifact_lines=lines,
                pieces=pieces,
                set_effects=list(set_lines),
            )
        )

    meta = finalize_shengxian_progress(
        tried=state.tried,
        total_unique_combinations=total_unique_combinations,
        stop_reason=stop,
        hit_count=len(rows),
        target=float(target),
        found_total=float(found_item["val"]) if found_item else None,
        closest_diff=closest_diff,
        closest_total=float(closest_item["val"]) if closest_item else None,
        process_logs=process_logs,
        on_progress=on_progress,
    )
    return rows, state.tried, truncated, stop, meta, process_logs
