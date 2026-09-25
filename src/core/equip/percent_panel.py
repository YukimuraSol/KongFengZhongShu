"""圣遗物百分比主词条：面板显示精度（1 位小数%）。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value: float, ndigits: int = 0) -> float:
    d = Decimal(str(value))
    if ndigits == 0:
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    q = Decimal("0." + "0" * (ndigits - 1) + "1")
    return float(d.quantize(q, rounding=ROUND_HALF_UP))


def percent_main_panel_fraction(raw: float) -> float:
    """主词条%：面板 1 位小数（如 46.6% → 0.466）。"""
    return round_half_up(float(raw) * 100, 1) / 100.0


_PERCENT_MAIN_TAGS = frozenset({"attackPercentage", "defendPercentage", "lifePercentage"})
_FLAT_MAIN_TAGS = frozenset({"attackStatic", "defendStatic", "lifeStatic"})


def normalize_json_main_value(main_stat_name: str, raw, *, star: int | None = None) -> float:
    """五星%主 1 位小数%；其余%主三位小数（display 回退）。"""
    if raw is None:
        return 0.0
    v = float(raw)
    if main_stat_name in _PERCENT_MAIN_TAGS:
        if star is not None and int(star) == 5:
            return percent_main_panel_fraction(v)
        return round_half_up(v, 3)
    if main_stat_name in _FLAT_MAIN_TAGS:
        return round_half_up(v, 1)
    return v
