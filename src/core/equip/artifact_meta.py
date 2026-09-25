"""圣遗物套装元数据（由 scripts/import_mona_artifact_meta.py 生成）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_META_PATH = Path(__file__).resolve().parents[2] / "resources" / "artifact_meta.json"


@lru_cache(maxsize=1)
def _load_meta() -> dict:
    if not _META_PATH.is_file():
        return {"sets": {}, "chs_by_eng": {}, "chs_by_key": {}}
    return json.loads(_META_PATH.read_text(encoding="utf-8"))


def get_set_chs(set_name: str) -> str:
    """按 eng/key/中文名查找套装中文名。"""
    if not set_name:
        return ""
    meta = _load_meta()
    chs_by_eng = meta.get("chs_by_eng") or {}
    chs_by_key = meta.get("chs_by_key") or {}
    if set_name in chs_by_key:
        return chs_by_key[set_name]
    if set_name in chs_by_eng:
        return chs_by_eng[set_name]
    for key, entry in (meta.get("sets") or {}).items():
        if entry.get("chs") == set_name or entry.get("eng") == set_name:
            return entry.get("chs") or set_name
    return set_name


def get_slot_meta(set_name: str, ui_slot: str) -> dict:
    """返回 {chs, icon_url}；ui_slot 为 flower/plume/sands/goblet/circlet。"""
    meta = _load_meta()
    sets = meta.get("sets") or {}
    entry = None
    for key, val in sets.items():
        if key == set_name or val.get("eng") == set_name or val.get("chs") == set_name:
            entry = val
            break
    if entry is None:
        return {"chs": "", "icon_url": None}
    slots = entry.get("slots") or {}
    slot_info = slots.get(ui_slot) or {}
    return {
        "chs": slot_info.get("chs") or "",
        "icon_url": slot_info.get("icon_url"),
        "set_chs": entry.get("chs") or set_name,
    }


_SUPPLEMENTAL_CHS: dict[str, str] = {
    "goldenTroupe": "黄金剧团",
    "GoldenTroupe": "黄金剧团",
    "wanderersTroupe": "流浪大地的乐团",
    "gladiatorFinale": "角斗士的终幕礼",
    "tenacityOfTheMillelith": "千岩牢固",
    "vourukashasGlow": "花海甘露之光",
    "echoesOfAnOffering": "来歆余响",
    "EchoesOfAnOffering": "来歆余响",
    "vermillionHereafter": "辰砂往生录",
    "empty": "空",
}


def resolve_meta_set_key(set_name: str) -> str:
    """将 JSON/中文/eng 套装名解析为 artifact_meta.sets 的 canonical key。"""
    raw = (set_name or "").strip()
    if not raw:
        return raw
    meta = _load_meta()
    sets = meta.get("sets") or {}
    if raw in sets:
        return raw
    for key, entry in sets.items():
        if entry.get("eng") == raw or entry.get("chs") == raw:
            return key
    chs_by_eng = meta.get("chs_by_eng") or {}
    chs_by_key = meta.get("chs_by_key") or {}
    if raw in chs_by_key:
        return raw
    if raw in chs_by_eng:
        for key, entry in sets.items():
            if entry.get("eng") == raw:
                return key
    return raw


def enrich_piece_card_fields(piece: dict, ui_slot: str) -> dict:
    """补全卡片展示：canonical set_name + icon_url。"""
    set_name = str(piece.get("set_name") or "")
    meta_key = resolve_meta_set_key(set_name)
    if meta_key:
        piece["set_name"] = meta_key
    slot_meta = get_slot_meta(meta_key or set_name, ui_slot)
    if slot_meta.get("icon_url"):
        piece["icon_url"] = slot_meta["icon_url"]
    if slot_meta.get("set_chs"):
        piece["set_chs"] = slot_meta["set_chs"]
    return piece


def set_name_translation_dict() -> dict[str, str]:
    """兼容旧 SET_NAME_TRANSLATION：eng/chs 双向 + key。"""
    meta = _load_meta()
    out: dict[str, str] = dict(_SUPPLEMENTAL_CHS)
    for key, entry in (meta.get("sets") or {}).items():
        chs = entry.get("chs") or key
        eng = entry.get("eng") or key
        out[key] = chs
        out[eng] = chs
        out[chs] = chs
    out.setdefault("empty", "空")
    return out
