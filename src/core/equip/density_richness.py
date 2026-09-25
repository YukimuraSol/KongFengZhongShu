"""密度评估柱图：按可调步长统计区间内「数值丰度」（可达档位覆盖率）。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.equip.atk_def_bundle import round_half_up

DEFAULT_RICHNESS_STEP = 0.01


def normalize_richness_step(step: float) -> float:
    s = float(step)
    if not math.isfinite(s) or s <= 0:
        return DEFAULT_RICHNESS_STEP
    return float(round_half_up(max(0.001, min(10.0, s)), 6))


def quantize_bonus_step(bonus: float, richness_step: float) -> int:
    step = normalize_richness_step(richness_step)
    return int(round_half_up(float(bonus) / step, 0))


def bin_step_index_range(range_low: float, range_high: float, richness_step: float) -> tuple[int, int]:
    """区间 [range_low, range_high) 内按步长可落入的档位索引闭区间。"""
    step = normalize_richness_step(richness_step)
    min_step = int(math.ceil(float(range_low) / step - 1e-9))
    max_step = int(math.floor((float(range_high) - 1e-9) / step))
    return min_step, max_step


def bin_slot_count(range_low: float, range_high: float, richness_step: float) -> int:
    """区间 [range_low, range_high) 内按步长可落入的档位数。"""
    min_step, max_step = bin_step_index_range(range_low, range_high, richness_step)
    return max(0, max_step - min_step + 1)


class DensityRichnessTracker:
    def __init__(self, min_v: float, max_v: float, bins_count: int, bin_w: float, richness_step: float) -> None:
        self.min_v = float(min_v)
        self.max_v = float(max_v)
        self.bins_count = int(bins_count)
        self.bin_w = float(bin_w)
        self.richness_step = normalize_richness_step(richness_step)
        self._hits: list[set[int]] = [set() for _ in range(self.bins_count)]
        self._slot_totals = [
            bin_slot_count(self.min_v + i * self.bin_w, self.min_v + (i + 1) * self.bin_w, self.richness_step)
            for i in range(self.bins_count)
        ]

    def add_bonus(self, bonus: float) -> None:
        x = float(bonus)
        if x < self.min_v or x >= self.max_v:
            return
        idx = int((x - self.min_v) / self.bin_w) if self.bin_w > 0 else 0
        idx = max(0, min(self.bins_count - 1, idx))
        l = self.min_v + idx * self.bin_w
        r = self.min_v + (idx + 1) * self.bin_w
        q = quantize_bonus_step(x, self.richness_step)
        min_s, max_s = bin_step_index_range(l, r, self.richness_step)
        if min_s <= q <= max_s:
            self._hits[idx].add(q)

    def richness_chart(self) -> list[float]:
        out: list[float] = []
        for i in range(self.bins_count):
            total = self._slot_totals[i]
            if total <= 0:
                out.append(0.0)
                continue
            pct = len(self._hits[i]) / total * 100.0
            out.append(float(round_half_up(min(100.0, pct), 2)))
        return out

    def global_richness(self) -> float:
        total_slots = sum(self._slot_totals)
        if total_slots <= 0:
            return 0.0
        merged: set[int] = set()
        for bucket in self._hits:
            merged |= bucket
        return float(round_half_up(min(100.0, len(merged) / total_slots * 100.0), 2))


@dataclass
class DensityBinAccumulator:
    min_v: float
    max_v: float
    bins_count: int
    bins: list[int]
    richness: DensityRichnessTracker
    bin_w: float
    richness_step: float
    out_low: int = 0
    out_high: int = 0
    in_range_weight: int = 0

    @classmethod
    def create(cls, min_v: float, max_v: float, bins_count: int, richness_step: float = DEFAULT_RICHNESS_STEP) -> DensityBinAccumulator:
        step = normalize_richness_step(richness_step)
        bin_w = (float(max_v) - float(min_v)) / bins_count if bins_count > 0 else 1.0
        return cls(
            min_v=float(min_v),
            max_v=float(max_v),
            bins_count=bins_count,
            bins=[0 for _ in range(bins_count)],
            richness=DensityRichnessTracker(min_v, max_v, bins_count, bin_w, step),
            bin_w=bin_w,
            richness_step=step,
        )

    def add_bonus(self, bonus: float, weight: int) -> None:
        x = float(bonus)
        w = int(weight)
        if x < self.min_v:
            self.out_low += w
            return
        if x >= self.max_v:
            self.out_high += w
            return
        idx = int((x - self.min_v) / self.bin_w) if self.bin_w > 0 else 0
        idx = max(0, min(self.bins_count - 1, idx))
        self.bins[idx] += w
        self.richness.add_bonus(x)
        self.in_range_weight += w


def finalize_density_richness_output(
    *,
    acc: DensityBinAccumulator,
    bin_labels: list[str],
    display_offset: float,
    count: int,
    total: int,
    stat_note: str,
) -> tuple[list[float], str, list[str]]:
    bins_for_chart = acc.richness.richness_chart()
    global_richness = acc.richness.global_richness()
    step = acc.richness_step
    log_lines: list[str] = [
        f"枚举组合进度 {min(count, total)}/{total}（各部位候选条数乘积，未乘圣遗物 count）",
        f"区间内加权计数={acc.in_range_weight}（分箱时按每条组合的 ∏count 累加）",
        f"图表用数值丰度（采样精度 {step:g}）：柱高=区间内可达档位占比(%)，全区间丰度={global_richness:.2f}%",
        f"柱数={acc.bins_count}；区间外：低={acc.out_low} 高={acc.out_high}",
        stat_note,
    ]
    ranked = sorted(range(len(bins_for_chart)), key=lambda i: bins_for_chart[i], reverse=True)[:5]
    if any(v > 0 for v in bins_for_chart):
        log_lines.append("Top 5 区间（与柱图一致，按数值丰度 %）:")
        for idx in ranked:
            if bins_for_chart[idx] <= 0:
                continue
            l = acc.min_v + idx * acc.bin_w
            r = acc.min_v + (idx + 1) * acc.bin_w
            slots = bin_slot_count(l, r, step)
            hits = int(round(bins_for_chart[idx] * slots / 100.0)) if slots > 0 else 0
            log_lines.append(
                f"  [{l + display_offset:.2f}, {r + display_offset:.2f}] -> "
                f"丰度 {bins_for_chart[idx]:.2f}%（{hits}/{slots} 档）"
            )

    peak_label = "—"
    if bins_for_chart and max(bins_for_chart) > 0:
        peak_label = bin_labels[bins_for_chart.index(max(bins_for_chart))]
    summary = (
        f"枚举组合 {min(count, total)}/{total}；全区间数值丰度={global_richness:.2f}%（采样精度 {step:g}）；"
        f"峰值柱≈{peak_label}"
    )
    return bins_for_chart, summary, log_lines
