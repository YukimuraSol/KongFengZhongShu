import json
from pathlib import Path
from typing import Any

from core.equip.legacy_shengxian.db import get_merged_hp_database

DEFAULT_EQUIP_SETTINGS: dict[str, Any] = {
    "positions": {"flower": True, "plume": True, "sands": True, "goblet": True, "circlet": True},
    "tolerance": 0.0,
    "algorithm": "optimized",
    "step": 0.0,
    "target_percent": 90.0,
    "auto_step": 0.0,
    "multi_solution_mode": "exclude",
    "result_precision": 0.01,
    "result_precision_hp": 0.01,
    "result_precision_atk": 0.01,
    "result_precision_def": 0.01,
    "result_precision_em": 0.01,
}
DEFAULT_YAS_SETTINGS: dict[str, Any] = {
    "scanner_path": "",
    "output_dir": "",
    "min_star": 1,
    "max_row": "",
}
DEFAULT_IRM_SETTINGS: dict[str, Any] = {
    "output_dir": "",
    "min_star": 1,
    "auto_stop_export_on_items": True,
    # Always on; not shown in UI.
    "delete_good_after_convert": True,
}


def _db_path() -> Path:
    return Path(__file__).resolve().parents[3] / "resources" / "database_settings.json"


def load_database_settings() -> dict:
    with _db_path().open("r", encoding="utf-8") as f:
        return json.load(f)


def save_database_settings(payload: dict) -> dict:
    with _db_path().open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def get_equip_rules() -> dict:
    data = load_database_settings()
    return data.get("equip_rules", {})


def get_hp_equip_database() -> dict[int, dict[str, Any]]:
    """圣显配生命：内置默认星级表 + database_settings.json 中 database_settings 覆盖。"""
    try:
        data = load_database_settings()
    except (OSError, json.JSONDecodeError):
        data = {}
    frag = data.get("database_settings")
    if not isinstance(frag, dict):
        frag = None
    return get_merged_hp_database(frag)


def get_equip_settings() -> dict:
    data = load_database_settings()
    raw = data.get("equip_settings")
    if not isinstance(raw, dict):
        return dict(DEFAULT_EQUIP_SETTINGS)

    merged = dict(DEFAULT_EQUIP_SETTINGS)
    merged.update(raw)

    positions = raw.get("positions")
    if isinstance(positions, dict):
        base_positions = dict(DEFAULT_EQUIP_SETTINGS["positions"])
        for k in base_positions.keys():
            if k in positions:
                base_positions[k] = bool(positions[k])
        merged["positions"] = base_positions
    else:
        merged["positions"] = dict(DEFAULT_EQUIP_SETTINGS["positions"])

    if merged.get("algorithm") not in {"optimized", "brute_force"}:
        merged["algorithm"] = DEFAULT_EQUIP_SETTINGS["algorithm"]
    if merged.get("multi_solution_mode") not in {"exclude", "skip_progress", "normal"}:
        merged["multi_solution_mode"] = DEFAULT_EQUIP_SETTINGS["multi_solution_mode"]

    try:
        legacy_rp = float(merged.get("result_precision", DEFAULT_EQUIP_SETTINGS["result_precision"]))
    except (TypeError, ValueError):
        legacy_rp = float(DEFAULT_EQUIP_SETTINGS["result_precision"])
    if "result_precision_hp" not in raw:
        merged["result_precision_hp"] = legacy_rp
    else:
        try:
            merged["result_precision_hp"] = float(raw["result_precision_hp"])
        except (TypeError, ValueError):
            merged["result_precision_hp"] = legacy_rp
    if "result_precision_atk" not in raw:
        merged["result_precision_atk"] = legacy_rp
    else:
        try:
            merged["result_precision_atk"] = float(raw["result_precision_atk"])
        except (TypeError, ValueError):
            merged["result_precision_atk"] = legacy_rp
    if "result_precision_def" not in raw:
        merged["result_precision_def"] = legacy_rp
    else:
        try:
            merged["result_precision_def"] = float(raw["result_precision_def"])
        except (TypeError, ValueError):
            merged["result_precision_def"] = legacy_rp
    if "result_precision_em" not in raw:
        merged["result_precision_em"] = legacy_rp
    else:
        try:
            merged["result_precision_em"] = float(raw["result_precision_em"])
        except (TypeError, ValueError):
            merged["result_precision_em"] = legacy_rp
    merged["result_precision"] = legacy_rp

    return merged


def save_equip_settings(payload: dict) -> dict:
    data = load_database_settings()
    merged = dict(DEFAULT_EQUIP_SETTINGS)
    if isinstance(payload, dict):
        merged.update(payload)
    merged.pop("avoid_characters", None)
    data["equip_settings"] = merged
    save_database_settings(data)
    return merged


def reset_equip_settings_to_default() -> dict:
    data = load_database_settings()
    data["equip_settings"] = dict(DEFAULT_EQUIP_SETTINGS)
    save_database_settings(data)
    return data["equip_settings"]


def get_yas_settings() -> dict:
    data = load_database_settings()
    raw = data.get("yas_settings")
    if not isinstance(raw, dict):
        return dict(DEFAULT_YAS_SETTINGS)
    merged = dict(DEFAULT_YAS_SETTINGS)
    merged.update(raw)
    try:
        merged["min_star"] = max(1, min(5, int(merged.get("min_star", 1))))
    except (TypeError, ValueError):
        merged["min_star"] = 1
    merged["scanner_path"] = str(merged.get("scanner_path", "")).strip()
    merged["output_dir"] = str(merged.get("output_dir", "")).strip()
    merged["max_row"] = str(merged.get("max_row", "")).strip()
    return merged


def save_yas_settings(payload: dict) -> dict:
    data = load_database_settings()
    merged = dict(DEFAULT_YAS_SETTINGS)
    if isinstance(payload, dict):
        merged.update(payload)
    try:
        merged["min_star"] = max(1, min(5, int(merged.get("min_star", 1))))
    except (TypeError, ValueError):
        merged["min_star"] = 1
    merged["scanner_path"] = str(merged.get("scanner_path", "")).strip()
    merged["output_dir"] = str(merged.get("output_dir", "")).strip()
    merged["max_row"] = str(merged.get("max_row", "")).strip()
    data["yas_settings"] = merged
    save_database_settings(data)
    return merged


def get_irm_settings() -> dict:
    data = load_database_settings()
    raw = data.get("irm_settings")
    if not isinstance(raw, dict):
        return dict(DEFAULT_IRM_SETTINGS)
    merged = dict(DEFAULT_IRM_SETTINGS)
    merged.update(raw)
    try:
        merged["min_star"] = max(1, min(5, int(merged.get("min_star", 1))))
    except (TypeError, ValueError):
        merged["min_star"] = 1
    merged["output_dir"] = str(merged.get("output_dir", "")).strip()
    merged["auto_stop_export_on_items"] = bool(merged.get("auto_stop_export_on_items", True))
    merged["delete_good_after_convert"] = True
    return merged


def save_irm_settings(payload: dict) -> dict:
    data = load_database_settings()
    merged = dict(DEFAULT_IRM_SETTINGS)
    if isinstance(payload, dict):
        merged.update(payload)
    try:
        merged["min_star"] = max(1, min(5, int(merged.get("min_star", 1))))
    except (TypeError, ValueError):
        merged["min_star"] = 1
    merged["output_dir"] = str(merged.get("output_dir", "")).strip()
    merged["auto_stop_export_on_items"] = bool(merged.get("auto_stop_export_on_items", True))
    merged["delete_good_after_convert"] = True
    data["irm_settings"] = merged
    save_database_settings(data)
    return merged
