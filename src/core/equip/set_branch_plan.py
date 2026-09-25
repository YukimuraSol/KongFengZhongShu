"""按套装结构枚举搜索分支（2 件套 / 2+2 / 散件），与莫娜 cutoff_algo2 set_mask 对齐。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator, Literal

from core.equip.atk_def_bundle import (
    POSITION_ORDER,
    get_set_type,
    normalize_set_name_for_bonus,
)
from core.equip.set_display_category import _named_two_piece_set_ids

StatMode = Literal["hp", "atk", "def", "em"]

# 与莫娜 iter_set2 一致：mask=1 表示该位必须穿套装 S
SET2_MASKS: tuple[tuple[int, ...], ...] = (
    (1, 1, 0, 0, 0),
    (1, 0, 1, 0, 0),
    (1, 0, 0, 1, 0),
    (1, 0, 0, 0, 1),
    (0, 1, 1, 0, 0),
    (0, 1, 0, 1, 0),
    (0, 1, 0, 0, 1),
    (0, 0, 1, 1, 0),
    (0, 0, 1, 0, 1),
    (0, 0, 0, 1, 1),
)

# 与莫娜 iter_set22 一致：1=套装 S1，2=套装 S2，0=散件
SET22_MASKS: tuple[tuple[int, ...], ...] = (
    (0, 1, 1, 2, 2),
    (0, 1, 2, 1, 2),
    (0, 1, 2, 2, 1),
    (0, 2, 1, 1, 2),
    (0, 2, 1, 2, 1),
    (0, 2, 2, 1, 1),
    (1, 0, 1, 2, 2),
    (1, 0, 2, 1, 2),
    (1, 0, 2, 2, 1),
    (2, 0, 1, 1, 2),
    (2, 0, 1, 2, 1),
    (2, 0, 2, 1, 1),
    (1, 1, 0, 2, 2),
    (1, 2, 0, 1, 2),
    (1, 2, 0, 2, 1),
    (2, 1, 0, 1, 2),
    (2, 1, 0, 2, 1),
    (2, 2, 0, 1, 1),
    (1, 1, 2, 0, 2),
    (1, 2, 1, 0, 2),
    (1, 2, 2, 0, 1),
    (2, 1, 1, 0, 2),
    (2, 1, 2, 0, 1),
    (2, 2, 1, 0, 1),
    (1, 1, 2, 2, 0),
    (1, 2, 1, 2, 0),
    (1, 2, 2, 1, 0),
    (2, 1, 1, 2, 0),
    (2, 1, 2, 1, 0),
    (2, 2, 1, 1, 0),
)

HP_TWO_PIECE_SET_TYPES = frozenset({"千岩套", "花海套", "冒险家"})


class SlotSetKind(str, Enum):
    ANY = "any"
    REQUIRE = "require"


@dataclass(frozen=True)
class SlotSetSpec:
    kind: SlotSetKind
    set_key: str = ""

    @staticmethod
    def any_slot() -> SlotSetSpec:
        return SlotSetSpec(SlotSetKind.ANY)

    @staticmethod
    def require(set_key: str) -> SlotSetSpec:
        return SlotSetSpec(SlotSetKind.REQUIRE, set_key)


@dataclass(frozen=True)
class SearchBranch:
    kind: Literal["scatter", "set2", "set22"]
    mask: tuple[int, ...]
    set_s1: str | None
    set_s2: str | None
    positions: tuple[str, ...]

    def label(self) -> str:
        if self.kind == "scatter":
            return "散件"
        if self.kind == "set2":
            return f"2件套 {self.set_s1} mask={list(self.mask)}"
        return f"2+2 {self.set_s1}+{self.set_s2} mask={list(self.mask)}"

    def slot_specs(self) -> tuple[SlotSetSpec, ...]:
        specs: list[SlotSetSpec] = []
        for m in self.mask:
            if m == 0:
                specs.append(SlotSetSpec.any_slot())
            elif m == 1:
                assert self.set_s1
                specs.append(SlotSetSpec.require(self.set_s1))
            else:
                assert self.set_s2
                specs.append(SlotSetSpec.require(self.set_s2))
        return tuple(specs)


def _valid_named_sets(stat_mode: StatMode) -> frozenset[str]:
    if stat_mode == "hp":
        return HP_TWO_PIECE_SET_TYPES
    return _named_two_piece_set_ids(stat_mode)


def entry_set_key(entry: dict[str, Any], stat_mode: StatMode) -> str | None:
    if stat_mode == "hp":
        st = str(entry.get("set_type") or "").strip()
        if st in HP_TWO_PIECE_SET_TYPES:
            return st
        derived = get_set_type(str(entry.get("original_set") or entry.get("setName") or ""))
        if derived in HP_TWO_PIECE_SET_TYPES:
            return derived
        return None
    raw = str(entry.get("original_set") or entry.get("setName") or "")
    sn = normalize_set_name_for_bonus(raw)
    if not sn or sn == "empty":
        return None
    if sn in _valid_named_sets(stat_mode):
        return sn
    return None


def discover_two_piece_sets_in_pool(
    pos_map: dict[str, list[Any]],
    *,
    stat_mode: StatMode,
) -> list[str]:
    found: set[str] = set()
    for arts in pos_map.values():
        for entry in arts:
            key = entry_set_key(entry, stat_mode)
            if key:
                found.add(key)
    return sorted(found)


def _mask_to_specs(mask: tuple[int, ...], s1: str, s2: str | None) -> tuple[SlotSetSpec, ...]:
    specs: list[SlotSetSpec] = []
    for m in mask:
        if m == 0:
            specs.append(SlotSetSpec.any_slot())
        elif m == 1:
            specs.append(SlotSetSpec.require(s1))
        else:
            assert s2 is not None
            specs.append(SlotSetSpec.require(s2))
    return tuple(specs)


def filter_pos_map_by_specs(
    pos_map: dict[str, list[Any]],
    positions: list[str],
    specs: tuple[SlotSetSpec, ...],
    *,
    stat_mode: StatMode,
) -> dict[str, list[Any]] | None:
    if len(positions) != len(specs):
        return None
    out: dict[str, list[Any]] = {}
    for pos, spec in zip(positions, specs):
        src = pos_map.get(pos) or []
        if spec.kind == SlotSetKind.ANY:
            if not src:
                return None
            out[pos] = list(src)
            continue
        filtered = [e for e in src if entry_set_key(e, stat_mode) == spec.set_key]
        if not filtered:
            return None
        out[pos] = filtered
    return out


def iter_search_branches(
    pos_map: dict[str, list[Any]],
    positions: list[str],
    *,
    stat_mode: StatMode,
) -> Iterator[SearchBranch]:
    n = len(positions)
    if n == 0:
        return

    pad = (0,) * n
    pos_tuple = tuple(positions)
    sets_in_pool = discover_two_piece_sets_in_pool(pos_map, stat_mode=stat_mode)

    scatter = SearchBranch(kind="scatter", mask=pad, set_s1=None, set_s2=None, positions=pos_tuple)

    for s1 in sets_in_pool:
        for raw_mask in SET2_MASKS:
            if len(raw_mask) != n:
                continue
            mask = tuple(raw_mask[:n])
            yield SearchBranch(kind="set2", mask=mask, set_s1=s1, set_s2=None, positions=pos_tuple)

    for i, s1 in enumerate(sets_in_pool):
        for s2 in sets_in_pool[i:]:
            for raw_mask in SET22_MASKS:
                if len(raw_mask) != n:
                    continue
                mask = tuple(raw_mask[:n])
                if 2 not in mask:
                    continue
                yield SearchBranch(
                    kind="set22",
                    mask=mask,
                    set_s1=s1,
                    set_s2=s2,
                    positions=pos_tuple,
                )

    # 散件全池组合数最大，放最后：先搜 2 件套 / 2+2 更快出最近邻与命中
    yield scatter


def ordered_positions_subset(positions_enabled: dict[str, bool]) -> list[str]:
    return [p for p in POSITION_ORDER if positions_enabled.get(p, True)]
