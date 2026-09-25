from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .character_name_map import good_location_to_mona_equip
from .main_stat_tables import main_stat_value
from .set_name_map import good_set_key_to_mona

SLOT_GOOD_TO_MONA = {
    "flower": "flower",
    "plume": "feather",
    "sands": "sand",
    "goblet": "cup",
    "circlet": "head",
}

MAIN_GOOD_TO_MONA = {
    "hp": "lifeStatic",
    "atk": "attackStatic",
    "hp_": "lifePercentage",
    "atk_": "attackPercentage",
    "def_": "defendPercentage",
    "eleMas": "elementalMastery",
    "enerRech_": "recharge",
    "heal_": "cureEffect",
    "critRate_": "critical",
    "critDMG_": "criticalDamage",
    "physical_dmg_": "physicalBonus",
    "pyro_dmg_": "fireBonus",
    "hydro_dmg_": "waterBonus",
    "electro_dmg_": "thunderBonus",
    "cryo_dmg_": "iceBonus",
    "anemo_dmg_": "windBonus",
    "geo_dmg_": "rockBonus",
    "dendro_dmg_": "dendroBonus",
}

SUB_GOOD_TO_MONA = {
    "hp": "lifeStatic",
    "atk": "attackStatic",
    "def": "defendStatic",
    "def_": "defendPercentage",
    "hp_": "lifePercentage",
    "atk_": "attackPercentage",
    "eleMas": "elementalMastery",
    "enerRech_": "recharge",
    "heal_": "cureEffect",
    "critRate_": "critical",
    "critDMG_": "criticalDamage",
    "physical_dmg_": "physicalDamage",
}

PCT_MONA = frozenset(
    {
        "lifePercentage",
        "attackPercentage",
        "defendPercentage",
        "critical",
        "criticalDamage",
        "recharge",
        "cureEffect",
        "physicalDamage",
        "physicalBonus",
        "fireBonus",
        "waterBonus",
        "thunderBonus",
        "iceBonus",
        "windBonus",
        "rockBonus",
        "dendroBonus",
    }
)


def normalize_set_name(set_key: str) -> str:
    """GOOD setKey → Mona/YAS setName（经典套装用 Mona 缩写 key，新套装保留 PascalCase）。"""
    return good_set_key_to_mona(set_key)


def _main_mon_name(artifact: dict[str, Any]) -> str:
    slot = str(artifact.get("slotKey") or "")
    key = str(artifact.get("mainStatKey") or "")
    if slot == "flower":
        return "lifeStatic"
    if slot == "plume":
        return "attackStatic"
    return MAIN_GOOD_TO_MONA.get(key, key)


def _convert_substats(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sub in artifact.get("substats") or []:
        key = str(sub.get("key") or "")
        name = SUB_GOOD_TO_MONA.get(key, key)
        val = float(sub.get("value") or 0)
        if name in PCT_MONA:
            val = round(val / 100.0, 6)
        else:
            val = float(val)
        out.append({"name": name, "value": val})
    return out


def convert_piece(artifact: dict[str, Any]) -> dict[str, Any]:
    slot = SLOT_GOOD_TO_MONA.get(str(artifact.get("slotKey") or ""), "flower")
    star = int(artifact.get("rarity") or 0)
    level = int(artifact.get("level") or 0)
    main_name = _main_mon_name(artifact)
    main_value = main_stat_value(main_name, star, level, slot)
    # Mona/YAS equip 用中文角色名；GOOD location 是英文 key（如 Shenhe）。
    equip = good_location_to_mona_equip(str(artifact.get("location") or "") or None)
    raw_set = str(artifact.get("setKey") or "")
    set_name = normalize_set_name(raw_set)
    return {
        "setName": set_name,
        "position": slot,
        "mainTag": {"name": main_name, "value": main_value},
        "normalTags": _convert_substats(artifact),
        "omit": False,
        "level": level,
        "star": star,
        "equip": equip,
    }


def good_to_mona(good_doc: dict[str, Any], *, min_star: int = 1) -> dict[str, Any]:
    min_star = max(1, min(5, int(min_star)))
    slots: dict[str, list[dict[str, Any]]] = {
        "flower": [],
        "feather": [],
        "sand": [],
        "cup": [],
        "head": [],
    }
    artifacts = good_doc.get("artifacts") or []
    for art in artifacts:
        if int(art.get("rarity") or 0) < min_star:
            continue
        try:
            piece = convert_piece(art)
        except KeyError:
            continue
        pos = piece["position"]
        if pos in slots:
            slots[pos].append(piece)
    return {"version": "1", **slots}


def convert_file(
    good_path: Path,
    out_path: Path,
    *,
    min_star: int = 1,
) -> dict[str, Any]:
    good_doc = json.loads(good_path.read_text(encoding="utf-8"))
    mona = good_to_mona(good_doc, min_star=min_star)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mona, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(mona.get(s) or []) for s in ("flower", "feather", "sand", "cup", "head"))
    return {
        "source": str(good_path),
        "output": str(out_path),
        "piece_count": total,
        "min_star": min_star,
    }


def list_good_exports(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("genshin_export_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def find_latest_good_export(directory: Path) -> Path | None:
    cands = list_good_exports(directory)
    return cands[0] if cands else None
