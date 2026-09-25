"""生命密度评估：legacy 圣遗物枚举 + 分箱（与攻防密度同一套加成值口径）。"""

from __future__ import annotations

import copy
import itertools
from typing import Any, Callable

from core.equip.atk_def_bundle import int_round_half_up, round_half_up
from core.equip.atk_def_density_runner import DensityEvalResult
from core.equip.density_richness import DensityBinAccumulator, finalize_density_richness_output
from core.equip.bnb_prune import bounds_list_span, sort_positions_wide_to_narrow
from core.equip.legacy_shengxian.bennett import calculate_all_hp_variants, calculate_bennett_hp
from core.equip.legacy_shengxian.process_artifacts import process_artifacts
from core.equip.legacy_shengxian.search import _artifact_hp_delta_bounds

_LEGACY_ORDER = ["flower", "feather", "sand", "cup", "head"]


def run_hp_density_eval(
    *,
    artifact_json: dict[str, Any],
    base_hp: float,
    no_artifact_hp: float,
    include_hp_percent: bool,
    bins_count: int,
    range_min: float,
    range_max: float,
    multi_solution_mode: str,
    positions_enabled: dict[str, bool],
    database_settings: dict[int, dict[str, Any]],
    richness_step: float = 0.01,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> DensityEvalResult:
    """positions_enabled: legacy keys flower,feather,sand,cup,head -> bool。返回与 run_density_eval 相同形状的 DensityEvalResult。"""

    arts, _fi = process_artifacts(
        artifact_json,
        float(base_hp),
        bool(include_hp_percent),
        [],
        database_settings,
    )

    multi_mode = multi_solution_mode if multi_solution_mode in ("exclude", "skip_progress", "normal") else "exclude"
    positions_to_calc = [p for p in _LEGACY_ORDER if positions_enabled.get(p, True)]
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
        p: bounds_list_span([_artifact_hp_delta_bounds(e, float(base_hp)) for e in pos_map[p]])
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
    display_offset = float(no_artifact_hp)

    count = 0
    next_update = 2000

    for combo in itertools.product(*lists):
        if should_cancel and should_cancel():
            break
        combo_tup = tuple(combo)
        count += 1
        combo_count = 1
        has_multi = False
        for a in combo_tup:
            combo_count *= int(a.get("count") or 1)
            if bool(a.get("has_multi_solution")):
                has_multi = True

        if multi_mode == "exclude" and has_multi:
            continue

        if has_multi:
            variants = calculate_all_hp_variants(list(combo_tup), float(base_hp), float(no_artifact_hp))
            for vv in variants:
                bonus_v = round_half_up(float(vv) - float(no_artifact_hp), 2)
                acc.add_bonus(bonus_v, combo_count)
        else:
            final_hp, _se = calculate_bennett_hp(combo_tup, float(base_hp), float(no_artifact_hp))
            bonus_v = round_half_up(float(final_hp) - float(no_artifact_hp), 2)
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
                        "bin_labels": _bin_labels(min_v, acc.bin_w, bins_count, display_offset),
                        "summary": f"枚举中… {min(count, total)}/{total}",
                        "log_tail": [f"已处理 {min(count, total)} / {total}"],
                    }
                )
            next_update += 10000

    bin_labels = _bin_labels(min_v, acc.bin_w, bins_count, display_offset)
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


def _bin_labels(min_v: float, bin_w: float, bins_count: int, display_offset: float) -> list[str]:
    out: list[str] = []
    for i in range(bins_count):
        l = min_v + i * bin_w
        r = min_v + (i + 1) * bin_w
        out.append(f"{(l + display_offset):.1f}-{(r + display_offset):.1f}")
    return out
