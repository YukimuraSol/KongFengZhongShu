from __future__ import annotations

from core.equip.artifact_meta import set_name_translation_dict
from .constants import POSITION_TRANSLATION

SET_NAME_TRANSLATION = set_name_translation_dict()


def should_show_set_name(set_name: str) -> bool:
    """参考库等占位套装（无/空）不在展示行中输出套装段。"""
    s = (set_name or "").strip()
    return s not in ("", "无", "空", "empty")


def append_set_suffix(line: str, set_name: str) -> str:
    if not should_show_set_name(set_name):
        return line
    return f"{line},套装:{set_name}"


def get_stat_name(stat_key: str) -> str:
    stat_names = {
        "lifeStatic": "生命值",
        "attackStatic": "攻击力",
        "defendStatic": "防御力",
        "defenseStatic": "防御力",
        "lifePercentage": "生命值",
        "attackPercentage": "攻击力%",
        "defendPercentage": "防御力%",
        "defensePercentage": "防御力%",
        "critical": "暴击率",
        "criticalDamage": "暴击伤害",
        "elementalMastery": "元素精通",
        "chargeEfficiency": "元素充能效率",
        "cureEffect": "治疗加成",
        "thunderBonus": "雷元素伤害",
        "fireBonus": "火元素伤害",
        "iceBonus": "冰元素伤害",
        "waterBonus": "水元素伤害",
        "windBonus": "风元素伤害",
        "earthBonus": "岩元素伤害",
        "rockBonus": "岩元素伤害",
        "physicalBonus": "物理伤害",
        "dendroBonus": "草元素伤害",
        "recharge": "元素充能效率",
        "其他": "其他",
    }
    return stat_names.get(stat_key, stat_key)


def format_stat_value(value: float) -> str:
    if value < 1:
        return f"+{value * 100:.1f}%"
    return f"+{int(round(value))}"


def format_artifact_info(artifact: dict, show_multi: bool = False, include_set: bool = True) -> str:
    position_cn = POSITION_TRANSLATION.get(artifact.get("position", ""), artifact.get("position", ""))
    if artifact.get("main_type") == "empty":
        return f"{position_cn}:空"

    star = int(artifact.get("star", 0))
    star_str = "★" * star
    full_artifact = artifact.get("full_artifact")
    if not full_artifact:
        hp_static = float(artifact.get("hp_static", 0) or 0)
        hp_text = f"生命值副词条:+{hp_static:.2f}" if hp_static > 0 else "生命值副词条:无"
        base = f"{position_cn}: {star_str} {artifact.get('level', 0)}级, {hp_text}"
        if include_set:
            return append_set_suffix(base, artifact.get("original_set", ""))
        return base

    main_tag = full_artifact.get("mainTag", {})
    main_tag_name_raw = main_tag.get("name", "")
    if main_tag_name_raw == "其他":
        main_part = "主词条:其他"
    else:
        main_tag_name = get_stat_name(main_tag_name_raw)
        main_tag_value = format_stat_value(float(main_tag.get("value", 0) or 0))
        if main_tag.get("name") == "lifePercentage":
            precise_percent = float(artifact.get("hp_percent_main", 0) or 0) * 100
            main_tag_value = f"+{precise_percent:.1f}%"
        elif main_tag.get("name") == "lifeStatic":
            main_tag_value = f"+{int(round(float(main_tag.get('value', 0) or 0)))}"
        main_part = f"主词条:{main_tag_name}{main_tag_value}"

    hp_substats: list[str] = []
    static_candidates = artifact.get("hp_static_candidates")
    percent_candidates = artifact.get("hp_percent_sub_candidates")
    static_multi_suffix = (
        f"({len(static_candidates)}多解)"
        if show_multi and isinstance(static_candidates, list) and len(static_candidates) > 1
        else ""
    )
    percent_multi_suffix = (
        f"({len(percent_candidates)}多解)"
        if show_multi and isinstance(percent_candidates, list) and len(percent_candidates) > 1
        else ""
    )
    normal_tags = full_artifact.get("normalTags")
    if isinstance(normal_tags, list):
        for tag in normal_tags:
            if tag.get("name") == "lifeStatic":
                tag_value = int(round(float(tag.get("value", 0) or 0)))
                hp_substats.append(f"生命值+{tag_value}{static_multi_suffix}")
            elif tag.get("name") == "lifePercentage":
                tag_value = float(tag.get("value", 0) or 0) * 100
                hp_substats.append(f"生命值+{tag_value:.1f}%{percent_multi_suffix}")

    hp_values: list[str] = []
    for substat in hp_substats:
        if "生命值+" in substat:
            hp_values.append(substat.replace("生命值", ""))
    hp_text = f"生命值副词条:{'、'.join(hp_values)}" if hp_values else "生命值副词条:无"

    original_set_name = artifact.get("original_set", "")
    translated_set_name = SET_NAME_TRANSLATION.get(original_set_name, original_set_name)
    base = (
        f"{position_cn}:{star_str} {artifact.get('level', 0)}级,{main_part},"
        f"{hp_text}"
    )
    if include_set:
        return append_set_suffix(base, translated_set_name)
    return base
