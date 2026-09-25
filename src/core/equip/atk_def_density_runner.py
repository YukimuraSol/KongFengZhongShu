"""密度评估：枚举所有组合并按加成区间分箱（对齐参考脚本 `_run_density_impl`）。"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from typing import Any, Callable

from core.equip.atk_def_bundle import (
    ALL_STAR_RATINGS,
    AtkDefEquipEngine,
    POSITION_ORDER,
    calculate_all_final_variants,
    has_multi_solution,
    int_round_half_up,
    round_half_up,
)
from core.equip.atk_def_search_runner import _piece_contrib_bounds
from core.equip.bnb_prune import bounds_list_span, sort_positions_wide_to_narrow
from core.equip.density_richness import DensityBinAccumulator, finalize_density_richness_output


@dataclass
class DensityEvalResult:
    """bins：加权分箱（∏count）；bins_for_chart：各柱数值丰度(%)，步长 0.01。"""
    bins: list[int]
    bins_for_chart: list[float]
    bin_labels: list[str]
    summary: str
    log_lines: list[str]
    range_min: float
    range_max: float
    display_offset: float
    out_low: int
    out_high: int
    total_in_range: int


def run_density_eval(
    *,
    artifact_json: dict[str, Any],
    target_mode: str,
    base_atk: float,
    no_artifact_atk: float,
    base_def: float,
    no_artifact_def: float,
    bins_count: int,
    range_min: float,
    range_max: float,
    multi_solution_mode: str,
    positions_enabled: dict[str, bool],
    include_percent_mains: bool = True,
    richness_step: float = 0.01,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> DensityEvalResult:
    is_atk = target_mode == "atk"
    engine = AtkDefEquipEngine()
    engine.load_database_json()

    arts, _fi = engine.process_artifacts(
        artifact_json,
        base_atk if is_atk else 0.0,
        base_def if not is_atk else 0.0,
        allowed_stars=ALL_STAR_RATINGS,
        include_percent_mains=include_percent_mains,
        target_mode=target_mode,
        avoid_chars=None,
    )

    multi_mode = multi_solution_mode if multi_solution_mode in ("exclude", "skip_progress", "normal") else "exclude"
    positions_to_calc = [p for p in POSITION_ORDER if positions_enabled.get(p, True)]
    if not positions_to_calc:
        return DensityEvalResult(
            bins=[],
            bins_for_chart=[],
            bin_labels=[],
            summary="至少选一个部位",
            log_lines=["至少选一个部位。"],
            range_min=range_min,
            range_max=range_max,
            display_offset=0.0,
            out_low=0,
            out_high=0,
            total_in_range=0,
        )

    pos_map: dict[str, list] = {p: arts[p] for p in positions_to_calc}
    if multi_mode == "exclude":
        for p in positions_to_calc:
            before = pos_map[p]
            kept = [e for e in before if not bool(e.get("has_multi_solution"))]
            pos_map[p] = kept if kept else before

    width_by_pos = {
        p: bounds_list_span([_piece_contrib_bounds(e, is_atk, base_atk, base_def) for e in pos_map[p]])
        for p in positions_to_calc
    }
    count_by_pos = {p: len(pos_map[p]) for p in positions_to_calc}
    positions_to_calc = sort_positions_wide_to_narrow(
        positions_to_calc,
        width_by_pos=width_by_pos,
        count_by_pos=count_by_pos,
    )
    lists = [pos_map[p] for p in positions_to_calc]

    total = 1
    for lst in lists:
        total *= len(lst)

    bins_count = int(max(5, min(200, int_round_half_up(bins_count))))
    min_v = float(range_min)
    max_v = float(range_max)
    acc = DensityBinAccumulator.create(min_v, max_v, bins_count, richness_step)
    display_offset = float(no_artifact_atk if is_atk else no_artifact_def)

    def stat_of(combo: tuple[Any, ...]) -> float:
        if is_atk:
            return engine.final_atk(no_artifact_atk, base_atk, combo)
        return engine.final_def(no_artifact_def, base_def, combo)

    count = 0
    next_update = 2000
    no_val = no_artifact_atk if is_atk else no_artifact_def
    base_val = base_atk if is_atk else base_def

    for combo in itertools.product(*lists):
        if should_cancel and should_cancel():
            break
        v = stat_of(combo)
        count += 1
        combo_count = 1
        has_multi = False
        for a in combo:
            combo_count *= int(a.get("count") or 1)
            if (
                has_multi_solution(a.get("atk_flat_candidates") or ())
                or has_multi_solution(a.get("atk_pct_candidates") or (), is_percent=True)
                or has_multi_solution(a.get("def_flat_candidates") or ())
                or has_multi_solution(a.get("def_pct_candidates") or (), is_percent=True)
            ):
                has_multi = True
        if multi_mode == "exclude" and has_multi:
            continue
        if has_multi:
            variants = calculate_all_final_variants(
                combo,
                "atk" if is_atk else "def",
                no_val,
                base_val,
            )
            for vv in variants:
                bonus_v = round_half_up(vv - no_val, 2)
                acc.add_bonus(bonus_v, combo_count)
        else:
            bonus_v = round_half_up(v - no_val, 2)
            acc.add_bonus(bonus_v, combo_count)

        if count >= next_update or count == total:
            if on_progress:
                enum_prog = min(1.0, min(count, total) / max(total, 1))
                on_progress(
                    {
                        "enumeration_progress": enum_prog,
                        "processed": min(count, total),
                        "total": total,
                        "bins": copy.copy(acc.bins),
                        "bins_for_chart": acc.richness.richness_chart(),
                        "bin_labels": [
                            f"{(min_v + i * acc.bin_w + display_offset):.1f}-{(min_v + (i + 1) * acc.bin_w + display_offset):.1f}"
                            for i in range(bins_count)
                        ],
                        "summary": f"枚举中… {min(count, total)}/{total}",
                        "log_tail": [f"已处理 {min(count, total)} / {total}"],
                    }
                )
            next_update += 10000

    bin_labels = [
        f"{(min_v + i * acc.bin_w + display_offset):.1f}-{(min_v + (i + 1) * acc.bin_w + display_offset):.1f}"
        for i in range(bins_count)
    ]
    bins_for_chart, summary, log_lines = finalize_density_richness_output(
        acc=acc,
        bin_labels=bin_labels,
        display_offset=display_offset,
        count=count,
        total=total,
        stat_note=f"统计口径=圣遗物加成值；显示偏移 no_artifact={display_offset:.2f}",
    )

    return DensityEvalResult(
        bins=acc.bins,
        bins_for_chart=bins_for_chart,
        bin_labels=bin_labels,
        summary=summary,
        log_lines=log_lines,
        range_min=min_v,
        range_max=max_v,
        display_offset=display_offset,
        out_low=acc.out_low,
        out_high=acc.out_high,
        total_in_range=acc.in_range_weight,
    )
