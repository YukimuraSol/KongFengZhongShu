from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = APP_DIR / "resources"
DEFAULT_SCANNER = RESOURCES_DIR / "irminsul_kfzs.exe"
DEFAULT_OUTPUT = RESOURCES_DIR / "output"
SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "scanner_path": "",
    "output_dir": "",
    "min_star": 1,
    "delete_good_after_convert": True,
    "auto_stop_export_on_items": True,
}


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    out = dict(DEFAULTS)
    out.update({k: data[k] for k in DEFAULTS if k in data})
    out["min_star"] = max(1, min(5, int(out.get("min_star") or 1)))
    out["delete_good_after_convert"] = bool(out.get("delete_good_after_convert", True))
    out["auto_stop_export_on_items"] = bool(out.get("auto_stop_export_on_items", True))
    return out


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(DEFAULTS)
    payload.update(data)
    payload["min_star"] = max(1, min(5, int(payload.get("min_star") or 1)))
    payload["delete_good_after_convert"] = bool(payload.get("delete_good_after_convert", True))
    payload["auto_stop_export_on_items"] = bool(
        payload.get("auto_stop_export_on_items", True)
    )
    SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def resolve_scanner(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("scanner_path") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_SCANNER.resolve()


def resolve_output(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("output_dir") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_OUTPUT.resolve()
