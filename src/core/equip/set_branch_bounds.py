"""套装分支内精确 stat 加成上下界（替换 _SET_BONUS_PAD）。"""

from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any, Callable, Sequence

from core.equip.bnb_prune import intervals_intersect
from core.equip.set_branch_plan import SearchBranch, StatMode, discover_two_piece_sets_in_pool, entry_set_key

# 生命二件套（与 legacy bennett.calculate_set_bonus 一致）
_HP_SET_PCT20 = frozenset({"千岩套", "花海套"})
_HP_SET_FLAT1000 = frozenset({"冒险家"})


def _atk_set_pct_bonus(set_key: str) -> float:
    from core.equip.atk_def_bundle import SET_TWO_PIECE_ATK_PCT18

    return 0.18 if set_key in SET_TWO_PIECE_ATK_PCT18 else 0.0


def _def_set_bonus(set_key: str) -> tuple[float, float]:
    from core.equip.atk_def_bundle import SET_TWO_PIECE_DEF_FLAT100, SET_TWO_PIECE_DEF_PCT30

    pct = 0.30 if set_key in SET_TWO_PIECE_DEF_PCT30 else 0.0
    flat = 100.0 if set_key in SET_TWO_PIECE_DEF_FLAT100 else 0.0
    return pct, flat


def _em_set_flat_bonus(set_key: str) -> float:
    from core.equip.em_equip_engine import SET_TWO_PIECE_EM_80

    return 80.0 if set_key in SET_TWO_PIECE_EM_80 else 0.0


def set_bonus_delta(
    set_key: str,
    *,
    stat_mode: StatMode,
    base_panel: float,
) -> tuple[float, float]:
    """单套二件套对最终 stat 的固定增量 (lo=hi)。"""
    if stat_mode == "atk":
        pct = _atk_set_pct_bonus(set_key)
        v = float(base_panel) * pct
        return v, v
    if stat_mode == "def":
        pct, flat = _def_set_bonus(set_key)
        v = flat + float(base_panel) * pct
        return v, v
    if stat_mode == "em":
        v = _em_set_flat_bonus(set_key)
        return v, v
    # hp
    if set_key in _HP_SET_PCT20:
        v = float(base_panel) * 0.20
        return v, v
    if set_key in _HP_SET_FLAT1000:
        return 1000.0, 1000.0
    return 0.0, 0.0


def branch_set_bonus_interval(
    branch: SearchBranch,
    *,
    stat_mode: StatMode,
    base_panel: float,
    pos_map: dict[str, list[Any]],
) -> tuple[float, float]:
    if branch.kind == "set2" and branch.set_s1:
        # 固定 2 件 set_s1 至少触发一套二件套；其余 ANY 位最多再凑一套 → 上界取池内 top-2 之和
        bonus_lo, _ = set_bonus_delta(branch.set_s1, stat_mode=stat_mode, base_panel=base_panel)
        _, scatter_hi = scatter_set_bonus_upper(
            pos_map, stat_mode=stat_mode, base_panel=base_panel
        )
        return bonus_lo, max(bonus_lo, scatter_hi)
    if branch.kind == "set22" and branch.set_s1 and branch.set_s2:
        lo1, hi1 = set_bonus_delta(branch.set_s1, stat_mode=stat_mode, base_panel=base_panel)
        lo2, hi2 = set_bonus_delta(branch.set_s2, stat_mode=stat_mode, base_panel=base_panel)
        return lo1 + lo2, hi1 + hi2
    return scatter_set_bonus_upper(pos_map, stat_mode=stat_mode, base_panel=base_panel)


def scatter_set_bonus_upper(
    pos_map: dict[str, list[Any]],
    *,
    stat_mode: StatMode,
    base_panel: float,
) -> tuple[float, float]:
    """散件分支：下界 0；上界取池中最多 2 个二件套加成之和（5 件最多 2 套）。"""
    bonuses: list[float] = []
    for set_key in discover_two_piece_sets_in_pool(pos_map, stat_mode=stat_mode):
        _lo, hi = set_bonus_delta(set_key, stat_mode=stat_mode, base_panel=base_panel)
        if hi > 0:
            bonuses.append(hi)
    bonuses.sort(reverse=True)
    upper = sum(bonuses[:2])
    return 0.0, upper


def _set_bonus_total_from_counts(
    counts: dict[str, int],
    *,
    stat_mode: StatMode,
    base_panel: float,
) -> float:
    """5 件圣遗物最多触发 2 个二件套加成。"""
    bonuses: list[float] = []
    for set_key, n in counts.items():
        if n < 2:
            continue
        _lo, hi = set_bonus_delta(set_key, stat_mode=stat_mode, base_panel=base_panel)
        if hi > 0:
            bonuses.append(hi)
    bonuses.sort(reverse=True)
    return sum(bonuses[:2])


def partial_set_bonus_interval(
    partial: Sequence[Any],
    remaining_lists: Sequence[Sequence[Any]],
    *,
    stat_mode: StatMode,
    base_panel: float,
    branch: SearchBranch,
    pos_map: dict[str, list[Any]],
) -> tuple[float, float]:
    """按已选件 + 剩余槽候选收紧套装加成区间（避免静态上界阻止层间剪枝）。"""
    branch_lo, branch_hi = branch_set_bonus_interval(
        branch, stat_mode=stat_mode, base_panel=base_panel, pos_map=pos_map
    )
    partial_counts: dict[str, int] = defaultdict(int)
    for entry in partial:
        sk = entry_set_key(entry, stat_mode)
        if sk:
            partial_counts[sk] += 1

    bonus_lo = _set_bonus_total_from_counts(
        dict(partial_counts), stat_mode=stat_mode, base_panel=base_panel
    )
    if branch.kind in ("set2", "set22"):
        bonus_lo = max(bonus_lo, branch_lo)

    if not remaining_lists:
        return bonus_lo, min(branch_hi, bonus_lo)

    slot_options: list[tuple[str | None, ...]] = []
    for rem_list in remaining_lists:
        keys = {entry_set_key(e, stat_mode) for e in rem_list}
        keys.discard(None)
        slot_options.append((None, *tuple(sorted(keys))))

    best_hi = bonus_lo
    for picks in itertools.product(*slot_options):
        counts = dict(partial_counts)
        for sk in picks:
            if sk:
                counts[sk] = counts.get(sk, 0) + 1
        best_hi = max(
            best_hi,
            _set_bonus_total_from_counts(counts, stat_mode=stat_mode, base_panel=base_panel),
        )
    return bonus_lo, min(branch_hi, best_hi)


def pool_stat_bounds(
    pos_map: dict[str, list[Any]],
    positions: list[str],
    *,
    base_stat: float,
    stat_mode: StatMode,
    base_panel: float,
    piece_bounds_fn: Callable[[Any], tuple[float, float]],
) -> tuple[float, float]:
    """整池 stat 可达下界/上界（件贡献 min/max 之和 + 最多两套二件套加成上界）。"""
    piece_lo = 0.0
    piece_hi = 0.0
    for pos in positions:
        bounds = [piece_bounds_fn(entry) for entry in pos_map.get(pos) or []]
        if not bounds:
            continue
        piece_lo += min(b[0] for b in bounds)
        piece_hi += max(b[1] for b in bounds)
    _bonus_lo, bonus_hi = scatter_set_bonus_upper(
        pos_map, stat_mode=stat_mode, base_panel=base_panel
    )
    return float(base_stat) + piece_lo, float(base_stat) + piece_hi + float(bonus_hi)


def branch_globally_unreachable(
    *,
    base_stat: float,
    piece_lo: float,
    piece_hi: float,
    bonus_lo: float,
    bonus_hi: float,
    target: float,
    tolerance: float,
) -> bool:
    glob_lo = float(base_stat) + float(piece_lo) + float(bonus_lo)
    glob_hi = float(base_stat) + float(piece_hi) + float(bonus_hi)
    return not intervals_intersect(glob_lo, glob_hi, float(target), float(tolerance))
