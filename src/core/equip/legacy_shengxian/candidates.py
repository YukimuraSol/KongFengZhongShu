from __future__ import annotations

from typing import Any


def get_hp_static_candidates(display_value: float, star: int, database_settings: dict[int, Any]) -> list[float]:
    if star not in database_settings:
        return [float(display_value)]
    config = database_settings[star].get("hp_sub", {})
    mode = config.get("mode")
    if mode == "none":
        return [0.0]
    if mode == "display":
        return [float(display_value)]
    mapping = config.get("mapping", [])
    if not mapping:
        return [float(display_value)]
    display_precision = config.get("display_precision", 1.0)
    if display_precision >= 1:
        decimal_places = 0
    elif display_precision >= 0.1:
        decimal_places = 1
    elif display_precision >= 0.01:
        decimal_places = 2
    else:
        decimal_places = 3
    rounded_value = round(display_value, decimal_places)
    candidates: list[float] = []
    for item in mapping:
        item_display_rounded = round(item["display"], decimal_places)
        if item["enabled"] and item_display_rounded == rounded_value:
            candidates.append(item["exact"])
    return candidates


def get_hp_percent_sub_candidates(display_value: float, star: int, database_settings: dict[int, Any]) -> list[float]:
    if star not in database_settings:
        return [float(display_value)]
    config = database_settings[star].get("hp_percent_sub", {})
    mode = config.get("mode")
    if mode == "none":
        return [0.0]
    if mode == "display":
        return [float(display_value)]
    mapping = config.get("mapping", [])
    if not mapping:
        return [float(display_value)]
    display_precision = config.get("display_precision", 0.001)
    if display_precision >= 0.01:
        decimal_places = 2
    elif display_precision >= 0.001:
        decimal_places = 3
    elif display_precision >= 0.0001:
        decimal_places = 4
    else:
        decimal_places = 5
    rounded_value = round(display_value, decimal_places)
    candidates: list[float] = []
    tolerance = display_precision * 0.1
    for item in mapping:
        if item["enabled"]:
            diff = abs(item["display"] - rounded_value)
            if diff < tolerance:
                candidates.append(item["exact"])
    return candidates
