from dataclasses import dataclass
from itertools import product
from typing import Literal


@dataclass
class Candidate:
    slot: str
    name: str
    score: float
    set_name: str


@dataclass
class EquipSolution:
    key: str
    total: float
    diff: float
    pieces: list[Candidate]


def merge_key(pieces: list[Candidate]) -> str:
    return "|".join(sorted(f"{p.slot}:{p.name}" for p in pieces))


def apply_set_bonus(total: float, pieces: list[Candidate], bonus_by_set: dict[str, float]) -> float:
    set_counter: dict[str, int] = {}
    for p in pieces:
        set_counter[p.set_name] = set_counter.get(p.set_name, 0) + 1
    bonus = 0.0
    for set_name, count in set_counter.items():
        if count >= 2:
            bonus += bonus_by_set.get(set_name, 0.0)
    return total + bonus


def search_solutions(
    pools: dict[str, list[Candidate]],
    target: float,
    mode: Literal["single", "all", "best-n"] = "best-n",
    best_n: int = 50,
    max_diff: float = 100.0,
    stop_after: int = 100000,
    bonus_by_set: dict[str, float] | None = None,
) -> list[EquipSolution]:
    bonus_by_set = bonus_by_set or {}
    slots = sorted(pools.keys())
    slot_lists = [pools[slot] for slot in slots]
    results: list[EquipSolution] = []
    seen_keys: set[str] = set()
    tried = 0
    for combo in product(*slot_lists):
        tried += 1
        if tried > stop_after:
            break
        pieces = list(combo)
        total = sum(p.score for p in pieces)
        total = apply_set_bonus(total, pieces, bonus_by_set)
        diff = abs(total - target)
        if diff > max_diff:
            continue
        key = merge_key(pieces)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append(EquipSolution(key=key, total=total, diff=diff, pieces=pieces))
    results.sort(key=lambda x: x.diff)
    if mode == "single":
        return results[:1]
    if mode == "best-n":
        return results[:best_n]
    return results
