from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# 建表 / 运行时多解：固定副与百分比副默认阈值（与圣显 database_settings 一致）
SUB_FLAT_MAX_DIFF = 0.01
SUB_PERCENT_MAX_DIFF = 5e-5
# 写入表内 exact 的游戏精度：固定两位、百分比四位
SUB_FLAT_EXACT_PLACES = 2
SUB_PERCENT_EXACT_PLACES = 4


def quantize_exact(value: float, places: int) -> float:
    """写入表格前的精度收口（四舍五入）。"""
    quant = Decimal("1") if places <= 0 else Decimal(10) ** -places
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def rounded_span_ge(span: float, threshold: float) -> bool:
    """只对极差四舍五入再比阈值。候选本身不 round。

    固定副阈值约 0.01 → 极差 round 到 4 位（0.009999…→0.01，0.008→0.008）。
    百分比阈值约 5e-5 → 用 6 位，避免 round(_,4) 把阈值抹掉。
    """
    places = 4 if threshold >= 0.001 else 6
    return round(float(span), places) >= float(threshold)


def collapse_exact_candidates(
    exacts: list[float] | set[float] | tuple[float, ...],
    threshold: float,
) -> list[float]:
    """同一显示键下的 exact：极差不足阈值则合并为单解（保留最小一项）。"""
    vals = sorted({float(x) for x in exacts})
    if len(vals) <= 1:
        return vals
    if rounded_span_ge(max(vals) - min(vals), threshold):
        return vals
    return [vals[0]]


def finalize_exact_candidates(
    exacts: list[float] | set[float] | tuple[float, ...],
    threshold: float,
    places: int,
) -> list[float]:
    """先按原样极差判多解/合并，再按游戏精度四舍五入写入并去重。"""
    kept = collapse_exact_candidates(exacts, threshold)
    out: list[float] = []
    seen: set[float] = set()
    for v in kept:
        q = quantize_exact(v, places)
        if q not in seen:
            seen.add(q)
            out.append(q)
    if len(out) <= 1:
        return out
    if rounded_span_ge(max(out) - min(out), threshold):
        return out
    return [out[0]]


def has_multi_solution(candidates: list[float], threshold: float = 0.0001) -> bool:
    """候选按原样取极差；仅极差四舍五入后 >= threshold 才算多解。"""
    if not candidates or len(candidates) <= 1:
        return False
    vals = [float(c) for c in candidates]
    # 仅按浮点恒等去重（不 round），保留真实不同小数
    unique: list[float] = list(dict.fromkeys(vals))
    if len(unique) <= 1:
        return False
    return rounded_span_ge(max(unique) - min(unique), threshold)
