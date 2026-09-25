"""搜索进度（仅枚举进度，已移除步长饱和度收集）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProgressState:
    total: int
    tried: int = 0

    @property
    def enumeration_progress(self) -> float:
        if self.total <= 0:
            return 1.0
        return min(1.0, self.tried / self.total)


def attach_best_diff(meta: dict[str, Any], closest_diff: float) -> dict[str, Any]:
    """将阶段一记录的最小偏差写入 progress meta（供前端计算中展示）。"""
    if closest_diff != float("inf") and closest_diff >= 0:
        meta["best_diff"] = float(closest_diff)
    return meta


def attach_search_best(
    meta: dict[str, Any],
    *,
    closest_diff: float,
    closest_total: float | None = None,
) -> dict[str, Any]:
    """写入 best_diff / best_total，供前端展示带符号偏差。"""
    attach_best_diff(meta, closest_diff)
    if closest_total is not None and closest_diff != float("inf"):
        meta["best_total"] = float(closest_total)
    return meta


def finalize_search_best(
    meta: dict[str, Any],
    *,
    target: float,
    found_total: float | None = None,
    closest_diff: float = float("inf"),
    closest_total: float | None = None,
) -> dict[str, Any]:
    """搜索结束时写入 best_*：命中优先于阶段一最近邻。"""
    if found_total is not None:
        t = float(found_total)
        meta["best_total"] = t
        meta["best_diff"] = abs(t - float(target))
        return meta
    return attach_search_best(meta, closest_diff=closest_diff, closest_total=closest_total)
