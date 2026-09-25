import copy
import gc
import itertools
import json
import os
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from core.equip.artifact_main_level import percent_main_table_value, yas_level4_main_mismatch
from core.equip.percent_panel import normalize_json_main_value, percent_main_panel_fraction
from core.equip.artifact_meta import set_name_translation_dict
from core.equip.legacy_shengxian.display_format import append_set_suffix
from core.equip.piece_identity import append_entry_source_piece, init_entry_source_pieces
from core.equip.em_wanderer_tables import get_sub_em_candidates

# ---------- 常量：部位与 JSON 字段（与 YAS / 圣显之钥一致）----------

POSITION_ORDER = ["flower", "feather", "sand", "cup", "head"]
POSITION_CN = {
    "flower": "生之花",
    "feather": "死之羽",
    "sand": "时之沙",
    "cup": "空之杯",
    "head": "理之冠",
}

SET_NAME_TRANSLATION = set_name_translation_dict()

STAT_NAME_CN = {
    "lifeStatic": "生命值",
    "attackStatic": "攻击力",
    "defendStatic": "防御力",
    "lifePercentage": "生命值",
    "attackPercentage": "攻击力%",
    "defendPercentage": "防御力%",
    "critical": "暴击率",
    "criticalDamage": "暴击伤害",
    "elementalMastery": "元素精通",
    "chargeEfficiency": "元素充能效率",
    "recharge": "元素充能效率",
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
    "其他": "其他",
}

PERCENT_DISPLAY_STAT_TAGS = frozenset(
    {
        "lifePercentage",
        "attackPercentage",
        "defendPercentage",
        "critical",
        "criticalDamage",
        "chargeEfficiency",
        "recharge",
        "cureEffect",
        "thunderBonus",
        "fireBonus",
        "iceBonus",
        "waterBonus",
        "windBonus",
        "earthBonus",
        "rockBonus",
        "physicalBonus",
        "dendroBonus",
    }
)

PERCENT_MAIN_POSITIONS = frozenset({"sand", "cup", "head"})
ALL_STAR_RATINGS = frozenset({1, 2, 3, 4, 5})

# 五星副词条「精确」滚动值（小数点后两位）；与生命值% 同步的攻击力% 档位；防御力% 单独一档
# 运行时 / full 参考库：最多反推 3 次强化（相对旧版 5 次降 2 层），避免副词条% 上界虚高
BUILTIN_SUB_MAX_UPGRADES = 3
SUB_ROLLS_5 = {
    "lifeStatic": (209.13, 239.00, 268.88, 298.75),
    "attackStatic": (13.62, 15.56, 17.51, 19.45),
    "defendStatic": (16.20, 18.52, 20.83, 23.15),
    # 以下为小数形式（0.0408 = 4.08%）
    "lifePercentage": (0.0408, 0.0466, 0.0525, 0.0583),
    "attackPercentage": (0.0408, 0.0466, 0.0525, 0.0583),
    "defendPercentage": (0.0510, 0.0583, 0.0656, 0.0729),
    "elementalMastery": (16.32, 18.65, 20.98, 23.31),
    "chargeEfficiency": (0.0453, 0.0518, 0.0583, 0.0648),
    "critical": (0.0272, 0.0311, 0.0350, 0.0389),
    "criticalDamage": (0.0544, 0.0622, 0.0699, 0.0777),
}

MULTI_SOLUTION_CHOICES = [
    ("exclude", "完全不采用（跳过多解）"),
    ("skip_progress", "采用但不记录进度"),
    ("normal", "正常采用（计入进度）"),
]
MULTI_LABEL_TO_KEY = {t[1]: t[0] for t in MULTI_SOLUTION_CHOICES}
def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def safe_eval(s):
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    try:
        return float(eval(t, {"__builtins__": {}}, {}))
    except Exception:
        return None


def round_half_up(value, ndigits=0):
    """传统四舍五入（5 进），避免 Python round 的银行家舍入。"""
    quant = Decimal("1") if ndigits == 0 else Decimal(f"1e-{ndigits}")
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def int_round_half_up(value):
    return int(round_half_up(value, 0))


def has_multi_solution(candidates, threshold=None, *, is_percent=False):
    """多解判定：候选原样取极差，四舍五入后 >= 阈值才算多解。

    默认固定副 0.01、百分比副 5e-5（与建表 max_diff 一致）。
    """
    from core.equip.legacy_shengxian.multi_util import (
        SUB_FLAT_MAX_DIFF,
        SUB_PERCENT_MAX_DIFF,
        has_multi_solution as _span_multi,
    )

    vals = []
    for x in candidates or ():
        try:
            vals.append(float(x))
        except (TypeError, ValueError):
            continue
    if threshold is None:
        threshold = SUB_PERCENT_MAX_DIFF if is_percent else SUB_FLAT_MAX_DIFF
    return _span_multi(vals, threshold)


def match_roll_candidates(display_value, rolls, is_percent=False):
    """将面板显示值匹配到精确档位列表；若无匹配则返回 [原值]。"""
    if display_value is None:
        return [0.0]
    dv = float(display_value)
    if is_percent:
        rounded = round_half_up(dv, 4)
        tol = 0.00015
    else:
        rounded = round_half_up(dv, 2)
        tol = 0.015
    hits = [r for r in rolls if abs(r - rounded) <= tol]
    if not hits:
        hits = [r for r in rolls if abs(r - dv) <= tol * 3]
    return hits if hits else [dv]


def linear_two_point(x1, d1, x2, d2, target_d):
    """两点定线：D = a*X + b，求 target_d 对应的 X。"""
    if abs(x2 - x1) < 1e-12:
        raise ValueError("两组属性数值不能相同，否则无法确定直线。")
    a = (d2 - d1) / (x2 - x1)
    b = d1 - a * x1
    if abs(a) < 1e-12:
        raise ValueError("斜率接近 0，无法用目标伤害反推属性。")
    need_x = (target_d - b) / a
    return a, b, need_x


def get_set_type(original_set_name):
    """与圣显之钥一致：合并键用套装分类（千岩/花海/冒险家等），其余归为「其他」。"""
    if not original_set_name or original_set_name == "empty":
        return "其他"
    target_sets_mapping = {
        "tenacityOfTheMillelith": "千岩套",
        "VourukashasGlow": "花海套",
        "vourukashasGlow": "花海套",
        "adventurer": "冒险家",
    }
    return target_sets_mapping.get(original_set_name, "其他")


# ---------- JSON 词条名 / 套装名别名（Mona 等与 defend/defense 混写时归一）----------

STAT_TAG_ALIASES = {
    "defenseStatic": "defendStatic",
    "defensePercentage": "defendPercentage",
}


def normalize_stat_tag_name(name):
    if not name:
        return name
    return STAT_TAG_ALIASES.get(name, name)


SET_NAME_CANONICAL = {
    "defendersWill": "defenderWill",
    "echoesOfAnOffering": "EchoesOfAnOffering",
    # Irm/GOOD 导出 HeavensGift；莫娜 meta / 文档用 CelestialGift
    "HeavensGift": "CelestialGift",
    "heavensGift": "CelestialGift",
    "celestialGift": "CelestialGift",
}


def normalize_set_name_for_bonus(set_name):
    if not set_name:
        return ""
    return SET_NAME_CANONICAL.get(set_name, set_name)


SET_TWO_PIECE_ATK_PCT18 = frozenset(
    {
        "gladiatorFinale",
        "shimenawaReminiscence",
        "EchoesOfAnOffering",
        "fragmentOfHarmonicWhimsy",
        "ADayCarvedFromRisingWinds",
    }
)
SET_TWO_PIECE_DEF_PCT30 = frozenset({"huskOfOpulentDreams", "defenderWill"})
SET_TWO_PIECE_DEF_FLAT100 = frozenset({"luckyDog"})


def calculate_atk_def_set_bonus(combo, target_mode="atk"):
    """
    按组合内 original_set 计数，每 canonical 套件数≥2 时各触发一次二件套（与圣显之钥 calculate_set_bonus 同在组合层加算）。
    target_mode 为 atk 时只累计/列出攻向二件套；为 def 时只累计/列出防向二件套（与配装目标一致）。
    返回 (atk_pct_bonus, def_pct_bonus, def_flat_bonus, effect_lines)。
    """
    cnt = defaultdict(int)
    for a in combo:
        sn = a.get("original_set") or ""
        if not sn or sn == "empty":
            continue
        cnt[normalize_set_name_for_bonus(sn)] += 1

    atk_pct_bonus = 0.0
    def_pct_bonus = 0.0
    def_flat_bonus = 0.0
    lines = []

    for sname, n in cnt.items():
        if n < 2:
            continue
        cn = SET_NAME_TRANSLATION.get(sname, sname)
        if target_mode == "atk":
            if sname in SET_TWO_PIECE_ATK_PCT18:
                atk_pct_bonus += 0.18
                lines.append(f"{cn} 二件套: +18% 攻击力")
        elif target_mode == "def":
            if sname in SET_TWO_PIECE_DEF_PCT30:
                def_pct_bonus += 0.30
                lines.append(f"{cn} 二件套: +30% 防御力")
            if sname in SET_TWO_PIECE_DEF_FLAT100:
                def_flat_bonus += 100.0
                lines.append(f"{cn} 二件套: +100 防御力")

    return atk_pct_bonus, def_pct_bonus, def_flat_bonus, lines


def merge_set_segment_for_key(set_name):
    """
    合并键中的套装段（与流浪晚星 process_artifacts 一致）：仅按 get_set_type 分类。
    「其他」类不拼具体套装名，使同攻/防数值的不同套装能合并为一条，减少枚举条数；同键多条原件合并时保留先插入条目的 original_set/full_artifact。
    """
    if not set_name or set_name == "empty":
        return "空"
    return get_set_type(set_name)


def build_merge_key_atk_def(atk_flat, atk_pct, def_flat, def_pct, star, set_name):
    """全量四维合并键（调试用）；实际配装合并请用 build_merge_key_for_target。"""
    af = int_round_half_up(atk_flat)
    df = int_round_half_up(def_flat)
    ap = int_round_half_up(atk_pct * 1000000)
    dp = int_round_half_up(def_pct * 1000000)
    return f"{af}_{ap}_{df}_{dp}_{star}_{merge_set_segment_for_key(set_name)}"


def build_merge_key_for_target(target_mode, atk_flat, atk_pct, def_flat, def_pct, star, set_name):
    """
    配攻击：合并键只含 atk_flat、atk_pct、星级、套装类（不把防御带进 key）。
    配防御：只含 def_flat、def_pct、星级、套装类。
    """
    seg = merge_set_segment_for_key(set_name)
    if target_mode == "atk":
        af = int_round_half_up(atk_flat)
        ap = int_round_half_up(atk_pct * 1000000)
        return f"atk_{af}_{ap}_{star}_{seg}"
    if target_mode == "def":
        df = int_round_half_up(def_flat)
        dp = int_round_half_up(def_pct * 1000000)
        return f"def_{df}_{dp}_{star}_{seg}"
    return build_merge_key_atk_def(atk_flat, atk_pct, def_flat, def_pct, star, set_name)


def sort_combo_by_position_order(combo):
    order = {p: i for i, p in enumerate(POSITION_ORDER)}
    return sorted(combo, key=lambda a: order.get(a.get("position"), 99))


def format_enum_sample_atk_breakdown(no_art, base_atk, combo, v, enum_index):
    """枚举抽样：当前组合的最终攻击力分项与公式（与 final_atk / stat_of 一致）。"""
    b_atk, _, _, set_lines = calculate_atk_def_set_bonus(combo, "atk")
    s_flat = sum(a["atk_flat"] for a in combo)
    s_pct = sum(a["atk_pct"] for a in combo)
    pct_sum = s_pct + b_atk
    flat_part = no_art + s_flat
    pct_part = base_atk * pct_sum
    final = flat_part + pct_part
    lines = [
        "",
        "=" * 58,
        f"[枚举抽样 #{enum_index}] 当前组合的最终攻击力",
        f"  无圣遗物攻击力 no_art = {no_art}",
        f"  Σ 圣遗物攻击固定 Σatk_flat = {s_flat:.6f}",
        f"  Σ 圣遗物攻击%（主+副）Σatk_pct = {s_pct:.6f}",
        f"  二件套攻击%（攻向）Σ2pc_atk = {b_atk:.6f}",
        f"  基础攻击力（用于百分比）base_atk = {base_atk}",
        "  公式: final_atk = no_art + Σatk_flat + base_atk × (Σatk_pct + Σ2pc_atk)",
        f"       = {no_art} + {s_flat:.6f} + {base_atk} × ({s_pct:.6f} + {b_atk:.6f})",
        f"       = {flat_part:.6f} + {pct_part:.6f} = {final:.6f}",
        f"  本步枚举返回值 v = {v:.6f}（应与上式一致）",
    ]
    if set_lines:
        lines.append("  本组合触发的攻向二件套:")
        for ln in set_lines:
            lines.append(f"    {ln}")
    else:
        lines.append("  （本组合无攻向二件套）")
    lines.append("=" * 58)
    return "\n".join(lines)


def format_enum_sample_def_breakdown(no_def, base_def, combo, v, enum_index):
    """枚举抽样：当前组合的最终防御力分项与公式（与 final_def / stat_of 一致）。"""
    _, b_def, b_dflat, set_lines = calculate_atk_def_set_bonus(combo, "def")
    s_flat = sum(a["def_flat"] for a in combo)
    s_pct = sum(a["def_pct"] for a in combo)
    pct_sum = s_pct + b_def
    flat_part = no_def + s_flat + b_dflat
    pct_part = base_def * pct_sum
    final = flat_part + pct_part
    lines = [
        "",
        "=" * 58,
        f"[枚举抽样 #{enum_index}] 当前组合的最终防御力",
        f"  无圣遗物防御力 no_def = {no_def}",
        f"  Σ 圣遗物防御固定 Σdef_flat = {s_flat:.6f}",
        f"  二件套防御固定（防向）Σ2pc_def_flat = {b_dflat:.6f}",
        f"  Σ 圣遗物防御%（主+副）Σdef_pct = {s_pct:.6f}",
        f"  二件套防御%（防向）Σ2pc_def_pct = {b_def:.6f}",
        f"  基础防御力（用于百分比）base_def = {base_def}",
        "  公式: final_def = no_def + Σdef_flat + Σ2pc_def_flat + base_def × (Σdef_pct + Σ2pc_def_pct)",
        f"       = {no_def} + {s_flat:.6f} + {b_dflat:.6f} + {base_def} × ({s_pct:.6f} + {b_def:.6f})",
        f"       = {flat_part:.6f} + {pct_part:.6f} = {final:.6f}",
        f"  本步枚举返回值 v = {v:.6f}（应与上式一致）",
    ]
    if set_lines:
        lines.append("  本组合触发的防向二件套:")
        for ln in set_lines:
            lines.append(f"    {ln}")
    else:
        lines.append("  （本组合无防向二件套）")
    lines.append("=" * 58)
    return "\n".join(lines)


def _build_piece_candidates_for_mode(entry, mode):
    """
    为多解性展开准备：每件圣遗物提供若干 (flat, pct) 候选。
    mode='atk' 使用 atk_flat_candidates/atk_pct_candidates；mode='def' 使用 def_*。
    """
    if mode == "atk":
        base_flat = float(entry.get("atk_flat_main") or 0.0)
        base_pct = float(entry.get("atk_pct_main") or 0.0)
        sub_flats = entry.get("atk_flat_candidates")
        sub_pcts = entry.get("atk_pct_candidates")
        if sub_flats:
            flats = tuple(base_flat + float(x) for x in sub_flats)
        else:
            flats = (float(entry.get("atk_flat") or 0.0),)
        if sub_pcts:
            pcts = tuple(base_pct + float(x) for x in sub_pcts)
        else:
            pcts = (float(entry.get("atk_pct") or 0.0),)
    else:
        base_flat = float(entry.get("def_flat_main") or 0.0)
        base_pct = float(entry.get("def_pct_main") or 0.0)
        sub_flats = entry.get("def_flat_candidates")
        sub_pcts = entry.get("def_pct_candidates")
        if sub_flats:
            flats = tuple(base_flat + float(x) for x in sub_flats)
        else:
            flats = (float(entry.get("def_flat") or 0.0),)
        if sub_pcts:
            pcts = tuple(base_pct + float(x) for x in sub_pcts)
        else:
            pcts = (float(entry.get("def_pct") or 0.0),)
    out = []
    for f in flats:
        for p in pcts:
            out.append((float(f), float(p)))
    return out or [(0.0, 0.0)]


def calculate_all_final_variants(combo, mode, no_val, base_val):
    """
    计算该组合在多解性下的所有最终攻/防值变体（类似圣显之钥 calculate_all_hp_variants）。
    返回两位小数去重后的有序列表（与圣显之钥 calculate_all_hp_variants 口径一致）。
    """
    if mode == "atk":
        b_atk, _, _, _ = calculate_atk_def_set_bonus(combo, "atk")
        b_def_flat = 0.0
        b_pct = b_atk
    else:
        _, b_def, b_def_flat, _ = calculate_atk_def_set_bonus(combo, "def")
        b_pct = b_def
        b_def_flat = b_def_flat

    per_piece = [_build_piece_candidates_for_mode(a, mode) for a in combo]
    rounded_variants = set()
    for pick in itertools.product(*per_piece):
        s_flat = sum(x[0] for x in pick)
        s_pct = sum(x[1] for x in pick)
        if mode == "atk":
            final = float(no_val) + s_flat + float(base_val) * (s_pct + b_pct)
        else:
            final = float(no_val) + s_flat + float(b_def_flat) + float(base_val) * (s_pct + b_pct)
        rounded_variants.add(round_half_up(final, 2))
    out = sorted(rounded_variants)
    return out


def format_json_percent_display(raw):
    """
    与流浪晚星一致：JSON 多为比例小数（0.466 → 46.6%），只乘一次 100。
    若数值已明显为「人读百分数」（|x|>1），则不再乘 100，避免 46.6 → 4660%。
    """
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return "0.0%"
    if abs(x) <= 1.000001:
        return f"{x * 100:.1f}%"
    return f"{x:.1f}%"


def format_stat_value_for_display(stat_name, raw_value):
    """面板显示：百分比类用 format_json_percent_display，其余尽量按游戏面板习惯展示。"""
    if stat_name in PERCENT_DISPLAY_STAT_TAGS:
        return format_json_percent_display(raw_value)
    if stat_name == "elementalMastery":
        try:
            return str(int_round_half_up(float(raw_value or 0)))
        except (TypeError, ValueError):
            return "0"
    try:
        v = float(raw_value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return str(int_round_half_up(v))


def format_atk_def_artifact_line(entry, is_atk_mode, show_multi=False, include_set: bool = True):
    """输出格式对齐圣显之钥：{部位}:{星级} {等级}级,主词条:{名}{+值},{攻/防副词条:...},套装:{中文}。"""
    pos = entry.get("position", "")
    pos_cn = POSITION_CN.get(pos, pos)
    star = int(entry.get("star") or 0)
    if star == 0 and entry.get("main_type") == "empty":
        return f"{pos_cn}:空"

    level = int(entry.get("level") or 0)
    star_str = "★" * star
    orig_set = entry.get("original_set") or ""
    cn_set = SET_NAME_TRANSLATION.get(orig_set) or SET_NAME_TRANSLATION.get(
        normalize_set_name_for_bonus(orig_set), orig_set or SET_NAME_TRANSLATION.get("empty", "空")
    )

    full = entry.get("full_artifact")
    if not full:
        base = f"{pos_cn}: {star_str} {level}级"
        return append_set_suffix(base, cn_set) if include_set else base

    main_tag = full.get("mainTag") or {}
    mn = normalize_stat_tag_name(main_tag.get("name"))
    mv = main_tag.get("value")

    main_cn = STAT_NAME_CN.get(mn, mn)
    if mn == "其他" or (main_tag.get("name") == "其他"):
        main_part = "主词条:其他"
    else:
        main_display = format_stat_value_for_display(mn, mv)
        # 圣显之钥风格：主词条名后直接跟 +数值（不带空格）
        main_part = f"主词条:{main_cn}+{main_display}"

    if is_atk_mode:
        sub_parts = []
        for tag in full.get("normalTags") or []:
            tn = normalize_stat_tag_name(tag.get("name"))
            if tn not in ("attackStatic", "attackPercentage"):
                continue
            if tn == "attackPercentage":
                v = format_json_percent_display(tag.get("value"))
                suffix = ""
                cands = entry.get("atk_pct_candidates") or ()
                if show_multi and isinstance(cands, (list, tuple)) and len(cands) > 1:
                    suffix = f"({len(cands)}多解)"
                sub_parts.append(f"+{v}{suffix}")
            else:
                try:
                    v = int_round_half_up(float(tag.get("value") or 0))
                except (TypeError, ValueError):
                    v = 0
                suffix = ""
                cands = entry.get("atk_flat_candidates") or ()
                if show_multi and isinstance(cands, (list, tuple)) and len(cands) > 1:
                    suffix = f"({len(cands)}多解)"
                sub_parts.append(f"+{v}{suffix}")
        sub_line = f"攻击力副词条:{'、'.join(sub_parts)}" if sub_parts else "攻击力副词条:无"
    else:
        sub_parts = []
        for tag in full.get("normalTags") or []:
            tn = normalize_stat_tag_name(tag.get("name"))
            if tn not in ("defendStatic", "defendPercentage"):
                continue
            if tn == "defendPercentage":
                v = format_json_percent_display(tag.get("value"))
                suffix = ""
                cands = entry.get("def_pct_candidates") or ()
                if show_multi and isinstance(cands, (list, tuple)) and len(cands) > 1:
                    suffix = f"({len(cands)}多解)"
                sub_parts.append(f"+{v}{suffix}")
            else:
                try:
                    v = int_round_half_up(float(tag.get("value") or 0))
                except (TypeError, ValueError):
                    v = 0
                suffix = ""
                cands = entry.get("def_flat_candidates") or ()
                if show_multi and isinstance(cands, (list, tuple)) and len(cands) > 1:
                    suffix = f"({len(cands)}多解)"
                sub_parts.append(f"+{v}{suffix}")
        sub_line = f"防御力副词条:{'、'.join(sub_parts)}" if sub_parts else "防御力副词条:无"

    line = f"{pos_cn}:{star_str} {level}级,{main_part},{sub_line}"
    return append_set_suffix(line, cn_set) if include_set else line


def builtin_sub_tag_is_percent(tag_name):
    """与 match_roll_candidates / SUB_ROLLS_5 一致：百分比副词条名判定。"""
    if not tag_name:
        return False
    if "Percentage" in tag_name:
        return True
    return tag_name in ("chargeEfficiency", "critical", "criticalDamage")


def build_sub_candidate_maps_from_rolls(rolls_by_tag, max_up=5):
    """rolls_by_tag: tag -> tiers；展开 + finalize。"""
    from core.equip.legacy_shengxian.multi_util import (
        SUB_FLAT_EXACT_PLACES,
        SUB_FLAT_MAX_DIFF,
        SUB_PERCENT_EXACT_PLACES,
        SUB_PERCENT_MAX_DIFF,
        finalize_exact_candidates,
    )

    out = {}
    for tag_name, tiers in (rolls_by_tag or {}).items():
        if not tiers:
            continue
        is_pct = builtin_sub_tag_is_percent(tag_name)
        max_diff = SUB_PERCENT_MAX_DIFF if is_pct else SUB_FLAT_MAX_DIFF
        places = SUB_PERCENT_EXACT_PLACES if is_pct else SUB_FLAT_EXACT_PLACES
        m = defaultdict(set)
        for init in tiers:
            for up_count in range(max_up + 1):
                for combo in itertools.product(tiers, repeat=up_count):
                    exact_raw = init + sum(combo)
                    if is_pct:
                        disp_key = round_half_up(float(f"{exact_raw:.4f}") * 100, 1)
                    else:
                        disp_key = int_round_half_up(float(f"{exact_raw:.2f}"))
                    m[disp_key].add(exact_raw)
        out[tag_name] = {
            k: finalize_exact_candidates(vs, max_diff, places) for k, vs in m.items()
        }
    return out


def build_builtin_sub_candidate_maps(max_up=5):
    """五星内置表（兼容旧名）。"""
    return build_sub_candidate_maps_from_rolls(SUB_ROLLS_5, max_up=max_up)


BUILTIN_SUB_CANDIDATE_MAPS = build_builtin_sub_candidate_maps(max_up=BUILTIN_SUB_MAX_UPGRADES)

_STAR_SUB_CANDIDATE_MAPS: dict[int, dict] = {}


def get_star_sub_candidate_maps(star: int):
    """按星级展开的副词条显示→exact 表。5★ 用 BUILTIN_SUB_MAX_UPGRADES；低星用 MAX_UPGRADES。"""
    star = int(star)
    if star in _STAR_SUB_CANDIDATE_MAPS:
        return _STAR_SUB_CANDIDATE_MAPS[star]
    from core.equip.legacy_shengxian.constants import MAX_UPGRADES
    from core.equip.sub_rolls_tables import SUB_ROLLS_BY_STAR

    rolls = SUB_ROLLS_BY_STAR.get(star) or {}
    if star == 5:
        # 与历史五星内置一致
        _STAR_SUB_CANDIDATE_MAPS[star] = BUILTIN_SUB_CANDIDATE_MAPS
    else:
        max_up = MAX_UPGRADES.get(star, 3)
        _STAR_SUB_CANDIDATE_MAPS[star] = build_sub_candidate_maps_from_rolls(rolls, max_up=max_up)
    return _STAR_SUB_CANDIDATE_MAPS[star]


def lookup_star_sub_candidates(tag_json_name, display_value, star: int):
    m = get_star_sub_candidate_maps(star).get(tag_json_name)
    if not m:
        return []
    try:
        dv = float(display_value)
    except (TypeError, ValueError):
        return []
    if builtin_sub_tag_is_percent(tag_json_name):
        k = round_half_up(dv * 100, 1)
    else:
        k = int_round_half_up(dv)
    return list(m.get(k, ()))


def lookup_builtin_sub_candidates(tag_json_name, display_value):
    """五星内置表查找（兼容旧调用）。"""
    return lookup_star_sub_candidates(tag_json_name, display_value, 5)



class AtkDefEquipEngine:
    """圣遗物解析与最终攻/防聚合（单目标：配攻击力 或 配防御力）。"""

    def __init__(self):
        self.database_settings = {}
        self._filter_stats = {
            "skipped_low_star_life_pct": 0,
            "skipped_no_candidates": 0,
            "skipped_zero_target_contrib": 0,
        }

    def load_database_json(self):
        from core.equip.legacy_shengxian.db import get_merged_hp_database

        frag = None
        path = os.path.join(get_app_base_dir(), "数据库配置.json")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "database_settings" in data:
                    frag = {int(k): v for k, v in data["database_settings"].items()}
            except Exception:
                frag = None
        self.database_settings = get_merged_hp_database(frag)

    def _sub_mode(self, star, key):
        if star in self.database_settings:
            return self.database_settings[star].get(key, {}).get("mode", "display")
        return "display"

    # ----- 以下两段与圣显之钥 v25 get_hp_static_candidates / get_hp_percent_sub_candidates 逻辑一致（仅配置键可变）-----

    def get_flat_sub_candidates(self, display_value, star, config_key):
        """固定值副词条：与圣显之钥 hp_sub 相同规则。"""
        if star not in self.database_settings:
            return [float(display_value)]

        config = self.database_settings[star].get(config_key, {})
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

        rounded_value = round_half_up(display_value, decimal_places)
        candidates = []
        for item in mapping:
            item_display_rounded = round_half_up(item["display"], decimal_places)
            if item["enabled"] and item_display_rounded == rounded_value:
                candidates.append(item["exact"])
        return candidates

    def get_percent_sub_candidates(self, display_value, star, config_key):
        """百分比副词条：与圣显之钥 hp_percent_sub 相同规则。"""
        if star not in self.database_settings:
            return [float(display_value)]

        config = self.database_settings[star].get(config_key, {})
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

        rounded_value = round_half_up(display_value, decimal_places)
        candidates = []
        tolerance = display_precision * 0.1
        for item in mapping:
            if item["enabled"]:
                diff = abs(item["display"] - rounded_value)
                if diff < tolerance:
                    candidates.append(item["exact"])
        return candidates

    def _hp_percent_sub_strict_low_star(self, star):
        """五星以下：生命%副词条须 hp_percent_sub 为 custom 且有 mapping。"""
        if star >= 5:
            return True
        cfg = self.database_settings.get(star, {}).get("hp_percent_sub", {})
        return cfg.get("mode") == "custom" and len(cfg.get("mapping") or []) > 0

    def _atk_def_sub_has_custom_table(self, star, config_key):
        """五星以下攻防副词条：仅当该星级该键为 custom 且带 mapping 才认为可精确解析（不用 SUB_ROLLS_5）。"""
        if star >= 5:
            return True
        cfg = self._cfg(star, self.database_settings, config_key)
        return cfg.get("mode") == "custom" and len(cfg.get("mapping") or []) > 0

    @staticmethod
    def _cfg(star, database_settings, key):
        return (database_settings.get(star) or {}).get(key, {})

    def _snap_star5_builtin(self, tag_json_name, display_value):
        """五星且无圣显之钥 custom 时，攻击力/防御力副词条用内置四档（与用户提供表一致）。"""
        rolls = SUB_ROLLS_5.get(tag_json_name)
        if not rolls:
            return None
        is_pct = "Percentage" in tag_json_name or tag_json_name in (
            "chargeEfficiency",
            "critical",
            "criticalDamage",
        )
        return match_roll_candidates(float(display_value), rolls, is_percent=is_pct)

    def resolve_sub_candidates(self, tag_json_name, display_value, star):
        """
        副词条用 JSON 原始显示值。
        custom mapping 优先；否则按星级 SUB_ROLLS_BY_STAR 展开表；最后回退 display。
        """
        try:
            dv = float(display_value)
        except (TypeError, ValueError):
            dv = 0.0

        key_flat = {
            "lifeStatic": "hp_sub",
            "attackStatic": "atk_sub",
            "defendStatic": "def_sub",
        }
        key_pct = {
            "lifePercentage": "hp_percent_sub",
            "attackPercentage": "atk_percent_sub",
            "defendPercentage": "def_percent_sub",
        }

        if tag_json_name in key_flat:
            ck = key_flat[tag_json_name]
            cfg = self._cfg(star, self.database_settings, ck)

            use_custom = (
                star in self.database_settings
                and cfg.get("mode") == "custom"
                and len(cfg.get("mapping") or []) > 0
            )
            if use_custom:
                cands = self.get_flat_sub_candidates(dv, star, ck)
                if cands:
                    return cands

            built = lookup_star_sub_candidates(tag_json_name, dv, star)
            if built:
                return built

            if star == 5 and tag_json_name in SUB_ROLLS_5:
                snapped = self._snap_star5_builtin(tag_json_name, dv)
                if snapped:
                    return snapped

            if star in self.database_settings:
                cands = self.get_flat_sub_candidates(dv, star, ck)
                if cands:
                    return cands
            return [dv] if dv else [0.0]

        if tag_json_name in key_pct:
            ck = key_pct[tag_json_name]
            cfg = self._cfg(star, self.database_settings, ck)

            use_custom = (
                star in self.database_settings
                and cfg.get("mode") == "custom"
                and len(cfg.get("mapping") or []) > 0
            )
            if use_custom:
                cands = self.get_percent_sub_candidates(dv, star, ck)
                if cands:
                    return cands

            built = lookup_star_sub_candidates(tag_json_name, dv, star)
            if built:
                return built

            if star == 5 and tag_json_name in SUB_ROLLS_5:
                snapped = self._snap_star5_builtin(tag_json_name, dv)
                if snapped:
                    return snapped

            if star in self.database_settings:
                cands = self.get_percent_sub_candidates(dv, star, ck)
                if cands:
                    return cands
            return [dv] if dv else [0.0]

        if tag_json_name == "elementalMastery":
            return get_sub_em_candidates(dv, star)

        # 暴击/暴伤/充能等：走星级 rolls 表
        built = lookup_star_sub_candidates(tag_json_name, dv, star)
        if built:
            return built
        return [dv] if dv else [0.0]

    def _percent_main_db_key(self, main_stat_name: str, star: int) -> str:
        # 防% 全星级独立表（高于同级生%/攻%）；生%/攻% 仍用 hp_percent_main
        if normalize_stat_tag_name(main_stat_name) == "defendPercentage":
            return "def_percent_main"
        return "hp_percent_main"

    def _main_percent_from_db(self, star, main_key, level, main_tag, main_stat_name):
        """百分比主词条：低星与备份一致（精确表按 level）；仅五星改显示表/YAS/防%分表。"""
        raw_display = main_tag.get("value")
        star_i = int(star)

        if star_i == 5 and yas_level4_main_mismatch(main_stat_name, star_i, level, raw_display):
            anchored = percent_main_table_value(main_stat_name, star_i, 4)
            if anchored is not None:
                return anchored

        db_key = self._percent_main_db_key(main_stat_name, star_i)
        if star_i in self.database_settings and db_key in self.database_settings[star_i]:
            cfg = self.database_settings[star_i][db_key]
            mode = cfg.get("mode", "display")
            if mode == "none":
                return 0.0
            if mode == "custom":
                vals = cfg.get("values") or []
                if level < len(vals):
                    return float(vals[level])
                return 0.0
            if mode == "display":
                return normalize_json_main_value(main_stat_name, raw_display, star=star_i)

        if star_i not in self.database_settings or main_key not in (self.database_settings.get(star_i) or {}):
            return normalize_json_main_value(main_stat_name, raw_display, star=star_i)

        fallback = percent_main_table_value(main_stat_name, star_i, level)
        if fallback is not None and star_i == 5:
            return fallback
        return normalize_json_main_value(main_stat_name, raw_display, star=star_i)

    def _sub_max_diff(self, star, config_key):
        cfg = self._cfg(star, self.database_settings, config_key)
        if "percent" in config_key:
            return float(cfg.get("max_diff", 0.0001))
        return float(cfg.get("max_diff", 0.01))

    def _main_flat_from_db(self, star, main_key, level, main_tag, main_stat_name):
        if star not in self.database_settings:
            return normalize_json_main_value(main_stat_name, main_tag.get("value"))
        if main_key not in self.database_settings[star]:
            return normalize_json_main_value(main_stat_name, main_tag.get("value"))
        cfg = self.database_settings[star][main_key]
        mode = cfg.get("mode", "display")
        if mode == "none":
            return 0.0
        if mode == "display":
            return normalize_json_main_value(main_stat_name, main_tag.get("value"))
        if mode == "custom":
            vals = cfg.get("values") or []
            if level < len(vals):
                return float(vals[level])
        return 0.0

    def process_artifacts(
        self,
        json_data,
        base_atk,
        base_def,
        allowed_stars=None,
        include_percent_mains=True,
        target_mode="atk",
        avoid_chars=None,
    ):
        """
        allowed_stars: 参与配装的星级集合，默认 1–5 星；仅五星则传入 frozenset({5})。
        target_mode: 「atk」时筛掉对攻击力无贡献的实件；「def」时筛掉对防御力无贡献的实件（与圣显之钥思路一致，缩小枚举）。
        返回 (artifacts_by_position, filter_info)，合并键与套装分类对齐圣显之钥 process_artifacts。
        """
        if allowed_stars is None:
            allowed_stars = ALL_STAR_RATINGS
        self._filter_stats = {
            "skipped_low_star_life_pct": 0,
            "skipped_no_candidates": 0,
            "skipped_zero_target_contrib": 0,
        }
        filter_info = {"filtered_chars": set(), "filtered_count": 0, "skipped_star_not_in_db": 0}
        has_db = bool(self.database_settings)

        artifacts_by_position = {p: [] for p in POSITION_ORDER}

        def empty_entry(pos):
            mk = build_merge_key_for_target(target_mode, 0.0, 0.0, 0.0, 0.0, 0, "empty")
            return {
                "merge_key": mk,
                "position": pos,
                "star": 0,
                "level": 0,
                "main_type": "empty",
                "count": 1,
                "full_artifact": None,
                "atk_flat": 0.0,
                "atk_pct": 0.0,
                "def_flat": 0.0,
                "def_pct": 0.0,
                "atk_flat_candidates": (0.0,),
                "atk_pct_candidates": (0.0,),
                "def_flat_candidates": (0.0,),
                "def_pct_candidates": (0.0,),
                "has_multi_solution": False,
                "is_non_contributing": True,
                "set_type": "其他",
                "original_set": "empty",
            }

        for pos in POSITION_ORDER:
            artifacts_by_position[pos].append(empty_entry(pos))

        for position in POSITION_ORDER:
            if position not in json_data:
                continue
            for artifact in json_data[position]:
                char_name = artifact.get("equip") or artifact.get("equippedCharacter")
                if avoid_chars and char_name and char_name in avoid_chars:
                    filter_info["filtered_chars"].add(char_name)
                    filter_info["filtered_count"] += 1
                    continue

                star = artifact.get("star", 0)
                if star not in allowed_stars:
                    continue
                if has_db and star not in self.database_settings:
                    filter_info["skipped_star_not_in_db"] += 1
                    continue

                main_tag = artifact.get("mainTag") or {}
                main_name = normalize_stat_tag_name(main_tag.get("name"))
                level = int(artifact.get("level") or 0)
                normal_tags = artifact.get("normalTags") or []
                set_name = normalize_set_name_for_bonus(artifact.get("setName"))

                if (
                    main_name in ("attackPercentage", "defendPercentage", "lifePercentage")
                    and position in PERCENT_MAIN_POSITIONS
                ):
                    if not include_percent_mains:
                        continue
                    if star in self.database_settings:
                        if self.database_settings[star].get("hp_percent_main", {}).get("mode") == "none":
                            continue

                if main_name == "lifeStatic" and star in self.database_settings:
                    if self.database_settings[star].get("hp_main", {}).get("mode", "display") == "none":
                        continue

                reject = False
                if star < 5:
                    for tag in normal_tags:
                        if normalize_stat_tag_name(tag.get("name")) != "lifePercentage":
                            continue
                        # 有 custom mapping 或星级 rolls 表则可解析；否则整件过滤
                        if self._hp_percent_sub_strict_low_star(star):
                            continue
                        from core.equip.sub_rolls_tables import rolls_for

                        if rolls_for(star, "lifePercentage"):
                            continue
                        self._filter_stats["skipped_low_star_life_pct"] += 1
                        reject = True
                        break
                if reject:
                    continue

                atk_flat_m = atk_pct_m = def_flat_m = def_pct_m = 0.0

                if main_name == "attackStatic":
                    if "atk_main" in (self.database_settings.get(star) or {}):
                        atk_flat_m += self._main_flat_from_db(star, "atk_main", level, main_tag, main_name)
                    else:
                        atk_flat_m += normalize_json_main_value(main_name, main_tag.get("value"))
                elif main_name == "defendStatic":
                    if "def_main" in (self.database_settings.get(star) or {}):
                        def_flat_m += self._main_flat_from_db(star, "def_main", level, main_tag, main_name)
                    else:
                        def_flat_m += normalize_json_main_value(main_name, main_tag.get("value"))
                elif main_name == "lifeStatic":
                    pass
                elif main_name == "attackPercentage" and position in PERCENT_MAIN_POSITIONS:
                    atk_pct_m += self._main_percent_from_db(star, "hp_percent_main", level, main_tag, main_name)
                elif main_name == "defendPercentage" and position in PERCENT_MAIN_POSITIONS:
                    def_pct_m += self._main_percent_from_db(star, "hp_percent_main", level, main_tag, main_name)
                elif main_name == "lifePercentage" and position in PERCENT_MAIN_POSITIONS:
                    pass

                hp_sub_mode = (
                    self.database_settings.get(star, {}).get("hp_sub", {}).get("mode", "display")
                    if star in self.database_settings
                    else "display"
                )
                hp_percent_sub_mode = (
                    self.database_settings.get(star, {}).get("hp_percent_sub", {}).get("mode", "display")
                    if star in self.database_settings
                    else "display"
                )

                sub_atk_flat_c = [0.0]
                sub_atk_pct_c = [0.0]
                sub_def_flat_c = [0.0]
                sub_def_pct_c = [0.0]

                for tag in normal_tags:
                    tn = normalize_stat_tag_name(tag.get("name"))
                    if tn == "lifeStatic":
                        if hp_sub_mode == "none":
                            filter_info["filtered_count"] += 1
                            reject = True
                            break
                        try:
                            lv = float(tag.get("value"))
                        except (TypeError, ValueError):
                            lv = 0.0
                        if lv > 2000:
                            filter_info["filtered_count"] += 1
                            reject = True
                            break
                        c = self.resolve_sub_candidates("lifeStatic", tag.get("value"), star)
                        if not c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break
                        continue
                    if tn == "lifePercentage":
                        if hp_percent_sub_mode == "none":
                            filter_info["filtered_count"] += 1
                            reject = True
                            break
                        c = self.resolve_sub_candidates("lifePercentage", tag.get("value"), star)
                        if not c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break
                        continue
                    if tn == "attackStatic":
                        sub_atk_flat_c = self.resolve_sub_candidates("attackStatic", tag.get("value"), star)
                        if not sub_atk_flat_c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break
                    elif tn == "attackPercentage":
                        sub_atk_pct_c = self.resolve_sub_candidates("attackPercentage", tag.get("value"), star)
                        if not sub_atk_pct_c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break
                    elif tn == "defendStatic":
                        sub_def_flat_c = self.resolve_sub_candidates("defendStatic", tag.get("value"), star)
                        if not sub_def_flat_c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break
                    elif tn == "defendPercentage":
                        sub_def_pct_c = self.resolve_sub_candidates("defendPercentage", tag.get("value"), star)
                        if not sub_def_pct_c:
                            self._filter_stats["skipped_no_candidates"] += 1
                            reject = True
                            break

                if reject:
                    continue

                combined = []
                for a_f in sub_atk_flat_c:
                    for a_p in sub_atk_pct_c:
                        for d_f in sub_def_flat_c:
                            for d_p in sub_def_pct_c:
                                combined.append((a_f, a_p, d_f, d_p))

                for af, ap, df, dp in combined:
                    atk_flat = atk_flat_m + af
                    atk_pct = atk_pct_m + ap
                    def_flat = def_flat_m + df
                    def_pct = def_pct_m + dp

                    if star > 0:
                        if target_mode == "atk" and atk_flat == 0 and atk_pct == 0:
                            self._filter_stats["skipped_zero_target_contrib"] += 1
                            continue
                        if target_mode == "def" and def_flat == 0 and def_pct == 0:
                            self._filter_stats["skipped_zero_target_contrib"] += 1
                            continue

                    key = build_merge_key_for_target(
                        target_mode, atk_flat, atk_pct, def_flat, def_pct, star, set_name
                    )
                    has_multi = (
                        has_multi_solution(sub_atk_flat_c)
                        or has_multi_solution(sub_atk_pct_c, is_percent=True)
                        or has_multi_solution(sub_def_flat_c)
                        or has_multi_solution(sub_def_pct_c, is_percent=True)
                    )

                    entry = {
                        "merge_key": key,
                        "position": position,
                        "star": star,
                        "level": level,
                        "main_type": main_name or "",
                        "count": 1,
                        "full_artifact": artifact,
                        "atk_flat": atk_flat,
                        "atk_pct": atk_pct,
                        "def_flat": def_flat,
                        "def_pct": def_pct,
                        # 主词条（与固定来源）贡献，用于多解展开时与副词条候选正确组合
                        "atk_flat_main": atk_flat_m,
                        "atk_pct_main": atk_pct_m,
                        "def_flat_main": def_flat_m,
                        "def_pct_main": def_pct_m,
                        "atk_flat_candidates": tuple(sub_atk_flat_c),
                        "atk_pct_candidates": tuple(sub_atk_pct_c),
                        "def_flat_candidates": tuple(sub_def_flat_c),
                        "def_pct_candidates": tuple(sub_def_pct_c),
                        "has_multi_solution": has_multi,
                        "is_non_contributing": (
                            atk_flat == 0 and atk_pct == 0 and def_flat == 0 and def_pct == 0
                        ),
                        "set_type": get_set_type(set_name),
                        "original_set": set_name or "",
                    }
                    dup = False
                    for ex in artifacts_by_position[position]:
                        if ex.get("merge_key") == key:
                            append_entry_source_piece(ex, artifact, position)
                            dup = True
                            break
                    if not dup:
                        init_entry_source_pieces(entry, artifact, position)
                        artifacts_by_position[position].append(entry)

        filter_info["filtered_chars"] = list(filter_info["filtered_chars"])
        return artifacts_by_position, filter_info

    @staticmethod
    def final_atk(no_art, base_atk, combo):
        b_atk, _b_def, _b_dflat, _ = calculate_atk_def_set_bonus(combo, "atk")
        s_flat = sum(a["atk_flat"] for a in combo)
        s_pct = sum(a["atk_pct"] for a in combo)
        return no_art + s_flat + base_atk * (s_pct + b_atk)

    @staticmethod
    def final_def(no_art, base_def, combo):
        _b_atk, b_def, b_dflat, _ = calculate_atk_def_set_bonus(combo, "def")
        s_flat = sum(a["def_flat"] for a in combo)
        s_pct = sum(a["def_pct"] for a in combo)
        return no_art + s_flat + b_dflat + base_def * (s_pct + b_def)
