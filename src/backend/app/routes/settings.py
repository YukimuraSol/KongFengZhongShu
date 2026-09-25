from fastapi import APIRouter

from ..services.database_service import (
    get_equip_settings,
    load_database_settings,
    save_database_settings,
    save_equip_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/database")
def database_info() -> dict:
    data = load_database_settings()
    return {
        "version": data.get("version", "unknown"),
        "keys": sorted(list(data.keys())),
        "raw": data,
    }


@router.put("/database")
def update_database(payload: dict) -> dict:
    saved = save_database_settings(payload)
    return {"ok": True, "version": saved.get("version", "unknown")}


@router.get("/equip")
def equip_settings() -> dict:
    return {"ok": True, "settings": get_equip_settings()}


@router.put("/equip")
def update_equip_settings(payload: dict) -> dict:
    saved = save_equip_settings(payload)
    return {"ok": True, "settings": saved}
