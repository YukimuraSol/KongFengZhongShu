"""禁用选择器套装段：仅展示用，不改合并键与计分。"""

from __future__ import annotations

from core.equip.atk_def_bundle import (
    SET_NAME_TRANSLATION,
    SET_TWO_PIECE_ATK_PCT18,
    SET_TWO_PIECE_DEF_FLAT100,
    SET_TWO_PIECE_DEF_PCT30,
    get_set_type,
    normalize_set_name_for_bonus,
)
from core.equip.em_equip_engine import SET_TWO_PIECE_EM_80

EquipTargetMode = str  # hp | atk | def | em


def _hp_picker_label(raw: str, sn: str) -> str:
    for key in (raw, sn):
        if key:
            label = get_set_type(key)
            if label != "其他":
                return label
    return "其他"


def _translated_set_label(raw: str, sn: str) -> str:
    return SET_NAME_TRANSLATION.get(sn) or SET_NAME_TRANSLATION.get(raw) or sn or raw or "其他"


def _named_two_piece_set_ids(target: str) -> frozenset[str]:
    mode = (target or "hp").lower()
    if mode == "atk":
        return SET_TWO_PIECE_ATK_PCT18
    if mode == "def":
        return SET_TWO_PIECE_DEF_PCT30 | SET_TWO_PIECE_DEF_FLAT100
    if mode == "em":
        return SET_TWO_PIECE_EM_80
    return frozenset()


def picker_set_label(set_name: str, *, target: str = "hp") -> str:
    """
    选择器「套装:」后缀（展示专用）：
    - 生命：千岩套、花海套、冒险家；其余「其他」（与 get_set_type 一致）
    - 攻/防/精通：有对应二件套效果的套装用中文名；其余「其他」
    """
    raw = (set_name or "").strip()
    sn = normalize_set_name_for_bonus(raw)
    if not sn or sn == "empty":
        return "其他"

    mode = (target or "hp").lower()
    if mode == "hp":
        return _hp_picker_label(raw, sn)

    if sn in _named_two_piece_set_ids(mode):
        return _translated_set_label(raw, sn)
    return "其他"


def append_picker_set_category(line_no_set: str, set_name: str, *, target: str = "hp") -> str:
    """选择器行：词条 + 套装段。"""
    base = (line_no_set or "").rstrip()
    cat = picker_set_label(set_name, target=target)
    if not base:
        return f"套装:{cat}"
    return f"{base},套装:{cat}"


two_piece_category_label = picker_set_label
