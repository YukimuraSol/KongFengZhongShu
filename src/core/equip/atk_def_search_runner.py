"""攻防线性配装枚举：首命中即停 + 可选 BnB 剪枝。"""

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
    calculate_all_final_variants,
    calculate_atk_def_set_bonus,
    format_atk_def_artifact_line,
    has_multi_solution,
    round_half_up,
    sort_combo_by_position_order,
    _build_piece_candidates_for_mode,
)
from core.equip.bnb_prune import (
    bounds_list_span,
    intervals_intersect,
    sort_by_target_proximity,
    sort_positions_wide_to_narrow,
)
from core.equip.set_branch_bounds import pool_stat_bounds
from core.equip.progress_stop import ProgressState, attach_search_best
from core.equip.shengxian_branched_search import finalize_shengxian_progress, run_shengxian_branched_search
from core.equip.search_engine import _multi_mode_zh


def stat_compare_decimals(result_decimals: int) -> int:
    """与圣显 calculate_bennett_hp 的 round(..., 2) 一致，至少保留 2 位再比命中。"""
    return max(int(result_decimals), 2)


def normalize_stat_for_compare(value: float, result_decimals: int) -> float:
    return round_half_up(float(value), stat_compare_decimals(result_decimals))


def stat_within_tolerance(
    actual: float,
    target: float,
    tolerance: float,
    result_decimals: int,
) -> bool:
    a = normalize_stat_for_compare(actual, result_decimals)
    t = normalize_stat_for_compare(target, result_decimals)
    return abs(a - t) <= float(tolerance)


from core.equip.disable_filter import filter_artifacts_by_disable


@dataclass
class AtkDefSearchRow:
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


def _pieces_from_combo(
    combo: tuple[Any, ...],
    is_atk: bool,
    base_atk: float,
    base_def: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in sort_combo_by_position_order(combo):
        pos = str(e.get("position") or "flower")
        slot = _slot_ui(pos)
        if is_atk:
            score = float(e.get("atk_flat", 0)) + float(base_atk) * float(e.get("atk_pct", 0))
        else:
            score = float(e.get("def_flat", 0)) + float(base_def) * float(e.get("def_pct", 0))
        name = str(e.get("merge_key") or "artifact")[:120]
        set_name = str(e.get("original_set") or "")
        piece = {"slot": slot, "name": name, "score": float(score), "set_name": set_name}
        piece.update(piece_display_fields(e))
        enrich_piece_card_fields(piece, slot)
        merge_line = format_atk_def_artifact_line(e, is_atk, show_multi=True)
        attach_merge_piece_meta(piece, e, slot, merge_line)
        out.append(piece)
    return out


def _lines_from_combo(combo: tuple[Any, ...], is_atk: bool) -> list[str]:
    return [f"  {format_atk_def_artifact_line(e, is_atk, show_multi=True)}" for e in sort_combo_by_position_order(combo)]


def _piece_contrib_bounds(entry: Any, is_atk: bool, base_atk: float, base_def: float) -> tuple[float, float]:
    """单件对最终攻/防的贡献区间（与 _build_piece_candidates_for_mode 多解展开一致）。"""
    mode = "atk" if is_atk else "def"
    base_panel = float(base_atk if is_atk else base_def)
    pairs = _build_piece_candidates_for_mode(entry, mode)
    contribs = [float(f) + base_panel * float(p) for f, p in pairs]
    if not contribs:
        return 0.0, 0.0
    return min(contribs), max(contribs)


def _piece_contrib_point(entry: Any, is_atk: bool, base_atk: float, base_def: float) -> float:
    """已选定条目：按合并后的确定值计贡献（多解在叶子再展开）。"""
    if is_atk:
        return float(entry.get("atk_flat") or 0) + float(base_atk) * float(entry.get("atk_pct") or 0)
    return float(entry.get("def_flat") or 0) + float(base_def) * float(entry.get("def_pct") or 0)


def _combo_has_multi(combo: tuple[Any, ...]) -> bool:
    for a in combo:
        if (
            has_multi_solution(a.get("atk_flat_candidates") or ())
            or has_multi_solution(a.get("atk_pct_candidates") or (), is_percent=True)
            or has_multi_solution(a.get("def_flat_candidates") or ())
            or has_multi_solution(a.get("def_pct_candidates") or (), is_percent=True)
        ):
            return True
    return False


def _atk_def_item_to_full_payload(
    k: str,
    item: dict[str, Any],
    is_atk: bool,
    base_atk: float,
    base_def: float,
    result_decimals: int,
) -> dict[str, Any]:
    combo = item["combo"]
    val = float(item["val"])
    variants = [float(x) for x in (item.get("variants") or [val])]
    variants_sorted = sorted({round_half_up(v, result_decimals) for v in variants})
    lines = _lines_from_combo(combo, is_atk)
    pieces = _pieces_from_combo(combo, is_atk, base_atk, base_def)
    _a, _b, _c, set_lines = calculate_atk_def_set_bonus(combo, "atk" if is_atk else "def")
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


def run_atk_def_equip_search(
    *,
    artifact_json: dict[str, Any],
    target: float,
    base_atk: float,
    no_artifact_atk: float,
    base_def: float,
    no_artifact_def: float,
    target_mode: str,
    tolerance: float,
    hp_step: float,
    result_precision: float,
    target_percent: float = 90.0,
    algorithm: str,
    multi_solution_mode: str,
    positions_enabled: dict[str, bool],
    best_n: int,
    auto_step: float = 0.5,
    include_percent_mains: bool = True,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    disabled_artifacts: list[str] | None = None,
    disabled_loose_pieces: list[str] | None = None,
    allowed_stars: frozenset[int] | None = None,
) -> tuple[list[AtkDefSearchRow], int, bool, str, dict[str, Any], list[str]]:
    del hp_step, target_percent, auto_step, best_n

    is_atk = target_mode == "atk"
    is_bf = algorithm == "brute_force"
    use_bnb = not is_bf
    engine = AtkDefEquipEngine()
    engine.load_database_json()
    stars = allowed_stars if allowed_stars is not None else ALL_STAR_RATINGS

    arts, _finfo = engine.process_artifacts(
        artifact_json,
        base_atk if is_atk else 0.0,
        base_def if not is_atk else 0.0,
        allowed_stars=stars,
        include_percent_mains=include_percent_mains,
        target_mode=target_mode,
        avoid_chars=None,
    )
    arts = filter_artifacts_by_disable(
        arts,
        disabled_artifacts=disabled_artifacts,
        disabled_loose_pieces=disabled_loose_pieces,
        format_line=lambda art: format_atk_def_artifact_line(art, is_atk, show_multi=True),
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

    no_val = no_artifact_atk if is_atk else no_artifact_def
    base_val = base_atk if is_atk else base_def

    slot_bounds_by_pos: dict[str, list[tuple[float, float]]] = {
        p: [_piece_contrib_bounds(e, is_atk, base_atk, base_def) for e in pos_map[p]]
        for p in positions_to_calc
    }
    width_by_pos = {p: bounds_list_span(slot_bounds_by_pos[p]) for p in positions_to_calc}
    count_by_pos = {p: len(pos_map[p]) for p in positions_to_calc}
    positions_to_calc = sort_positions_wide_to_narrow(
        positions_to_calc,
        width_by_pos=width_by_pos,
        count_by_pos=count_by_pos,
    )

    lists = [list(pos_map[p]) for p in positions_to_calc]
    bounds_lists = [slot_bounds_by_pos[p] for p in positions_to_calc]
    bounds_by_id: dict[int, tuple[float, float]] = {}
    for slot_idx, slot_bounds in enumerate(bounds_lists):
        for entry, bounds in zip(lists[slot_idx], slot_bounds):
            bounds_by_id[id(entry)] = bounds

    total = 1
    for lst in lists:
        total *= len(lst)
    total_unique_combinations = total
    state = ProgressState(total=total_unique_combinations)
    need = float(target) - float(no_val)
    slot_lists: list[list[Any]] = []
    slot_min: list[float] = []
    slot_max: list[float] = []
    for lst in lists:
        sorted_lst = sort_by_target_proximity(
            lst,
            lambda e: _piece_contrib_bounds(e, is_atk, base_atk, base_def)[0],
            need,
        )
        slot_lists.append(sorted_lst)
        piece_bounds = [_piece_contrib_bounds(e, is_atk, base_atk, base_def) for e in sorted_lst]
        slot_min.append(min(b[0] for b in piece_bounds))
        slot_max.append(max(b[1] for b in piece_bounds))

    precision_text = f"{result_precision:.10f}".rstrip("0").rstrip(".")
    if "." in precision_text:
        result_decimals = min(6, max(0, len(precision_text.split(".", 1)[1])))
    else:
        result_decimals = 0

    stat_label = "攻击" if is_atk else "防御"
    process_logs: list[str] = [
        f"总唯一组合数: {total_unique_combinations}\n"
        f"多解性部位处理模式: {_multi_mode_zh(multi_solution_mode)}\n"
        f"命中条件: |{stat_label} - {target}| <= {tolerance}，首命中即停",
    ]
    if algorithm == "brute_force":
        process_logs.append("算法模式: 纯枚举（遍历所有组合）")
    else:
        process_logs.append("算法模式: 优化（套装分支 + 区间剪枝）")
        process_logs.append("按散件 / 单2件套 / 2+2 分支筛池；套装加成精确计入剪枝上界")

    stat_mode = "atk" if is_atk else "def"
    pool_lo, pool_hi = pool_stat_bounds(
        pos_map,
        positions_to_calc,
        base_stat=float(no_val),
        stat_mode=stat_mode,
        base_panel=float(base_val),
        piece_bounds_fn=lambda e: _piece_contrib_bounds(e, is_atk, base_atk, base_def),
    )
    pool_globally_unreachable = not intervals_intersect(
        pool_lo, pool_hi, float(target), float(tolerance)
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
    stop = "no_match"
    found_item: dict[str, Any] | None = None
    closest_item: dict[str, Any] | None = None
    closest_diff = float("inf")

    target_cmp = normalize_stat_for_compare(float(target), result_decimals)
    tol = float(tolerance)

    def _push_progress(meta: dict[str, Any]) -> None:
        attach_search_best(
            meta,
            closest_diff=closest_diff,
            closest_total=float(closest_item["val"]) if closest_item else None,
        )
        if callable(on_progress):
            on_progress(meta)

    def _record_closest_value(combo: tuple[Any, ...], v_cmp: float) -> None:
        nonlocal closest_item, closest_diff
        d = abs(v_cmp - target_cmp)
        if not closer(d, closest_diff):
            return
        combo_count = 1
        for a in combo:
            combo_count *= int(a.get("count") or 1)
        has_multi = _combo_has_multi(combo)
        closest_diff = d
        closest_item = make_closest_payload(
            key_prefix="closest_multi_" if has_multi else "closest_single_",
            val=float(v_cmp),
            diff=float(v_cmp) - target_cmp,
            combo=tuple(combo),
            combo_count=combo_count,
            has_multi=has_multi,
            variants=[float(v_cmp)],
        )
        if callable(on_progress):
            _push_progress({"tried": state.tried})

    def _accept_hit(combo: tuple[Any, ...], v_cmp: float, *, has_multi: bool, variants: list[float]) -> bool:
        nonlocal found_item, stop
        combo_count = 1
        for a in combo:
            combo_count *= int(a.get("count") or 1)
        key = (
            f"multi_{round_half_up(v_cmp, result_decimals)}"
            if has_multi
            else f"single_{round_half_up(v_cmp, result_decimals)}"
        )
        found_item = {
            "val": float(v_cmp),
            "combo": tuple(copy.deepcopy(x) for x in combo),
            "count": combo_count,
            "diff": float(v_cmp) - target_cmp,
            "variants": variants,
            "has_multi_solution": has_multi,
        }
        stop = "first_match_found"
        if callable(on_result):
            on_result(
                _atk_def_item_to_full_payload(
                    key, found_item, is_atk, base_atk, base_def, result_decimals
                )
            )
        return True

    def _combo_piece_bounds(combo: tuple[Any, ...]) -> tuple[float, float]:
        lo = 0.0
        hi = 0.0
        for entry in combo:
            blo, bhi = bounds_by_id[id(entry)]
            lo += blo
            hi += bhi
        return lo, hi

    def _process_leaf(combo: tuple[Any, ...]) -> bool:
        nonlocal stop
        if multi_mode == "exclude" and _combo_has_multi(combo):
            return False

        if is_atk:
            raw = engine.final_atk(no_artifact_atk, base_atk, combo)
        else:
            raw = engine.final_def(no_artifact_def, base_def, combo)

        has_multi = _combo_has_multi(combo)
        if has_multi:
            blo, bhi = _combo_piece_bounds(combo)
            if is_atk:
                b_atk, _, _, _ = calculate_atk_def_set_bonus(combo, "atk")
                set_delta = float(base_atk) * float(b_atk)
            else:
                _, b_def, b_dflat, _ = calculate_atk_def_set_bonus(combo, "def")
                set_delta = float(b_dflat) + float(base_def) * float(b_def)
            if not intervals_intersect(
                float(no_val) + blo + set_delta,
                float(no_val) + bhi + set_delta,
                float(target),
                tol,
            ):
                return False
            mode = "atk" if is_atk else "def"
            uniq_variants = calculate_all_final_variants(combo, mode, no_val, base_val)
            for vv in uniq_variants:
                vv_cmp = normalize_stat_for_compare(float(vv), result_decimals)
                if abs(vv_cmp - target_cmp) <= tol:
                    return _accept_hit(combo, vv_cmp, has_multi=True, variants=list(uniq_variants))
                d = abs(vv_cmp - target_cmp)
                if closer(d, closest_diff):
                    _record_closest_value(combo, vv_cmp)
            return False

        v_cmp = normalize_stat_for_compare(raw, result_decimals)
        if abs(v_cmp - target_cmp) <= tol:
            return _accept_hit(combo, v_cmp, has_multi=False, variants=[v_cmp])
        d = abs(v_cmp - target_cmp)
        if closer(d, closest_diff):
            _record_closest_value(combo, v_cmp)
        return False

    state.tried, truncated, stop = run_shengxian_branched_search(
        state=state,
        pos_map=pos_map,
        positions=positions_to_calc,
        slot_lists=slot_lists,
        slot_min=slot_min,
        slot_max=slot_max,
        stat_mode=stat_mode,
        target=float(target),
        tolerance=float(tolerance),
        base_stat=float(no_val),
        base_panel=float(base_val),
        bounds_fn=lambda e: _piece_contrib_bounds(e, is_atk, base_atk, base_def),
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

    def _resolve_closest_variants(item: dict[str, Any]) -> dict[str, Any]:
        if not item.get("has_multi_solution"):
            return item
        combo = item["combo"]
        mode = "atk" if is_atk else "def"
        variants = calculate_all_final_variants(combo, mode, no_val, base_val)
        if not variants:
            return item
        t_cmp = normalize_stat_for_compare(float(target), result_decimals)
        best_v = min(
            variants,
            key=lambda v: abs(normalize_stat_for_compare(float(v), result_decimals) - t_cmp),
        )
        best_cmp = normalize_stat_for_compare(float(best_v), result_decimals)
        resolved = dict(item)
        resolved["val"] = float(best_cmp)
        resolved["diff"] = float(best_cmp) - float(t_cmp)
        resolved["variants"] = list(variants)
        return resolved

    rows: list[AtkDefSearchRow] = []
    if found_item:
        k = (
            f"multi_{round_half_up(float(found_item['val']), result_decimals)}"
            if found_item.get("has_multi_solution")
            else f"single_{round_half_up(float(found_item['val']), result_decimals)}"
        )
        combo = found_item["combo"]
        val = float(found_item["val"])
        variants_sorted = sorted(
            {round_half_up(float(x), result_decimals) for x in (found_item.get("variants") or [val])}
        )
        lines = _lines_from_combo(combo, is_atk)
        pieces = _pieces_from_combo(combo, is_atk, base_atk, base_def)
        _a, _b, _c, set_lines = calculate_atk_def_set_bonus(combo, "atk" if is_atk else "def")
        rows.append(
            AtkDefSearchRow(
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
        closest_item = _resolve_closest_variants(closest_item)
        k = f"closest_{round_half_up(float(closest_item['val']), result_decimals)}"
        combo = tuple(copy.deepcopy(x) for x in closest_item["combo"])
        val = float(closest_item["val"])
        variants_sorted = sorted(
            {round_half_up(float(x), result_decimals) for x in (closest_item.get("variants") or [val])}
        )
        lines = _lines_from_combo(combo, is_atk)
        pieces = _pieces_from_combo(combo, is_atk, base_atk, base_def)
        _a, _b, _c, set_lines = calculate_atk_def_set_bonus(combo, "atk" if is_atk else "def")
        rows.append(
            AtkDefSearchRow(
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
