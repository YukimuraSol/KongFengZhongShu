"""搜索未命中时保留距目标最近的组合（供结果区展示）。"""

from __future__ import annotations

from typing import Any


def closer(diff: float, best: float) -> bool:
    return diff < best


def make_closest_payload(
    *,
    key_prefix: str,
    val: float,
    diff: float,
    combo: tuple[Any, ...],
    combo_count: int,
    has_multi: bool,
    variants: list[float],
) -> dict[str, Any]:
    return {
        "key": f"{key_prefix}{val}",
        "val": float(val),
        "diff": float(diff),
        "combo": combo,
        "count": int(combo_count),
        "variants": list(variants),
        "has_multi_solution": bool(has_multi),
    }
