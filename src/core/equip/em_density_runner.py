"""元素精通密度评估：精通候选枚举 + 分箱（与攻防/生命密度返回形状一致）。"""

from __future__ import annotations

import copy
import itertools
from typing import Any, Callable

from core.equip.atk_def_bundle import AtkDefEquipEngine, POSITION_ORDER, has_multi_solution, int_round_half_up, round_half_up
from core.equip.atk_def_density_runner import DensityEvalResult
from core.equip.density_richness import DensityBinAccumulator, finalize_density_richness_output
from core.equip.bnb_prune import bounds_list_span, sort_positions_wide_to_narrow
from core.equip.em_equip_engine import final_total_em, process_artifacts_for_em
from core.equip.em_search_runner import _em_flat_bounds


def _piece_em_multi(a: dict[str, Any]) -> bool:
    return has_multi_solution(a.get("em_flat_candidates") or ())


def _iter_variant_totals(
    combo: tuple[Any, ...],
    no_artifact_em: float,
    extra_base_em: float,
) -> list[float]:
    cand_lists: list[list[float]] = []
    for a in combo:
        cands = tuple(a.get("em_flat_candidates") or ())
        if len(cands) > 1:
            cand_lists.append([float(x) for x in cands])
        else:
            cand_lists.append([float(a.get("em_flat") or 0.0)])
    out: list[float] = []
    for picks in itertools.product(*cand_lists):
        syn = tuple({**a, "em_flat": emv} for a, emv in zip(combo, picks))
        out.append(final_total_em(no_artifact_em, extra_base_em, syn))
    return out


def run_em_density_eval(
    *,
    artifact_json: dict[str, Any],
    no_artifact_em: float,
    extra_base_em: float,
    include_em_main: bool,
    bins_count: int,
    range_min: float,
    range_max: float,
    multi_solution_mode: str,
    positions_enabled: dict[str, bool],
    richness_step: float = 0.01,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> DensityEvalResult:
    engine = AtkDefEquipEngine()
    engine.load_database_json()

    arts, _fi = process_artifacts_for_em(
        engine,
        artifact_json,
        include_em_main=bool(include_em_main),
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
        p: bounds_list_span([_em_flat_bounds(e) for e in pos_map[p]]) for p in positions_to_calc
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
    display_offset = float(no_artifact_em)

    count = 0
    next_update = 2000
    na = float(no_artifact_em)

    for combo in itertools.product(*lists):
        if should_cancel and should_cancel():
            break
        combo_tup = tuple(combo)
        count += 1
        combo_count = 1
        has_multi = any(_piece_em_multi(a) for a in combo_tup)
        for a in combo_tup:
            combo_count *= int(a.get("count") or 1)

        if multi_mode == "exclude" and has_multi:
            continue

        if has_multi:
            for tot in _iter_variant_totals(combo_tup, float(no_artifact_em), float(extra_base_em)):
                bonus_v = round_half_up(float(tot) - na, 2)
                acc.add_bonus(bonus_v, combo_count)
        else:
            tot = final_total_em(float(no_artifact_em), float(extra_base_em), combo_tup)
            bonus_v = round_half_up(float(tot) - na, 2)
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
        stat_note=f"统计口径=总精通相对无圣遗物面板的增量；显示偏移 no_artifact_em={display_offset:.2f}",
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
