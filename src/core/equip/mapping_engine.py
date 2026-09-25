from dataclasses import dataclass

from core.equip.legacy_shengxian.multi_util import rounded_span_ge


@dataclass
class MappingRule:
    mode: str
    display_precision: float = 0.01
    max_diff: float = 0.01
    mapping: list[dict] | None = None


def resolve_candidates(display_value: float, rule: MappingRule) -> list[float]:
    if rule.mode == "none":
        return []
    if rule.mode == "display":
        return [display_value]
    candidates: list[float] = []
    for item in rule.mapping or []:
        if abs(float(item.get("display", 0.0)) - display_value) <= rule.display_precision:
            candidates.append(float(item.get("exact", display_value)))
    if not candidates:
        return [display_value]
    return sorted(set(candidates))


def has_multi_solution(candidates: list[float], max_diff: float) -> bool:
    if len(candidates) <= 1:
        return False
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if rounded_span_ge(abs(candidates[i] - candidates[j]), max_diff):
                return True
    return False
