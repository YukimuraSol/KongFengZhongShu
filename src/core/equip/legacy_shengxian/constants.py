"""与 圣显之钥_v27.0 一致的常量与套装分类。"""

from __future__ import annotations

HP_PERCENT_POSITIONS = frozenset({"sand", "cup", "head"})

# 各星级最大强化次数（与参考文件一致）
MAX_UPGRADES = {5: 5, 4: 4, 3: 3, 2: 1, 1: 1}

HP_PERCENT_MAIN_STATS_2STAR = [0.042, 0.054, 0.066, 0.078, 0.090]
HP_PERCENT_MAIN_STATS_1STAR = [0.031, 0.043, 0.055, 0.067, 0.079]

# 防御%主词条（各星独立，高于同级生命%/攻击%）。
# 来源：Fandom Artifact/Scaling（面板 1 位小数%）；与物伤杯同档。
DEF_PERCENT_MAIN_STATS_1STAR = [0.039, 0.054, 0.069, 0.084, 0.099]
DEF_PERCENT_MAIN_STATS_2STAR = [0.052, 0.067, 0.082, 0.097, 0.112]
DEF_PERCENT_MAIN_STATS_3STAR = [
    0.066,
    0.084,
    0.103,
    0.121,
    0.140,
    0.158,
    0.177,
    0.196,
    0.214,
    0.233,
    0.251,
    0.270,
    0.288,
]
DEF_PERCENT_MAIN_STATS_4STAR = [
    0.079,
    0.101,
    0.123,
    0.146,
    0.168,
    0.190,
    0.212,
    0.235,
    0.257,
    0.279,
    0.302,
    0.324,
    0.346,
    0.368,
    0.391,
    0.413,
    0.435,
]

# 主词条百分比：面板显示值（1 位小数%，无副词条那种内部精确小数）。
# 来源：B站 Wiki「圣遗物全等级主词条的具体属性数值」生命%/攻击%列。
HP_ATK_PERCENT_MAIN_DISPLAY_5STAR = [
    0.07,
    0.09,
    0.11,
    0.129,
    0.149,
    0.169,
    0.189,
    0.209,
    0.228,
    0.248,
    0.268,
    0.288,
    0.308,
    0.328,
    0.347,
    0.367,
    0.387,
    0.407,
    0.427,
    0.446,
    0.466,
]

# 防御%主词条单独一档（满级 58.3%，非 46.6%）。
DEF_PERCENT_MAIN_DISPLAY_5STAR = [
    0.087,
    0.112,
    0.137,
    0.162,
    0.186,
    0.211,
    0.236,
    0.261,
    0.286,
    0.31,
    0.335,
    0.36,
    0.385,
    0.409,
    0.434,
    0.459,
    0.484,
    0.508,
    0.533,
    0.558,
    0.583,
]

HP_PERCENT_MAIN_STATS_5STAR = [
    0.0700001613,
    0.0900000538,
    0.1100002151,
    0.1290001667,
    0.1490003280,
    0.1690002205,
    0.1890001129,
    0.2090002743,
    0.2280002259,
    0.2480001183,
    0.2680002796,
    0.2880001721,
    0.3080003334,
    0.3280002259,
    0.3470001775,
    0.3670003388,
    0.3870002312,
    0.4070003926,
    0.4270002850,
    0.4460002366,
    0.4660003979,
]

HP_PERCENT_MAIN_STATS_4STAR = [
    0.0630003065,
    0.0810003173,
    0.0990000592,
    0.1160001291,
    0.1340001398,
    0.1520001506,
    0.1700001613,
    0.1880001721,
    0.2060004517,
    0.2230003872,
    0.2410002635,
    0.2590002743,
    0.2770002850,
    0.2950002958,
    0.3130003065,
    0.3300001075,
    0.3480003872,
]

HP_PERCENT_MAIN_STATS_3STAR = [
    0.0520006815,
    0.0670006488,
    0.0819995466,
    0.0970001103,
    0.1120004291,
    0.1270004489,
    0.1420001152,
    0.1559998321,
    0.1709999115,
    0.1860004202,
    0.2010003665,
    0.2160006376,
    0.2310002385,
]

POSITION_TRANSLATION = {
    "flower": "生之花",
    "feather": "死之羽",
    "sand": "时之沙",
    "cup": "空之杯",
    "head": "理之冠",
}

# 前端 plume/sands/goblet/circlet → JSON 键
UI_TO_JSON_POSITION = {
    "flower": "flower",
    "plume": "feather",
    "feather": "feather",
    "sands": "sand",
    "sand": "sand",
    "goblet": "cup",
    "cup": "cup",
    "circlet": "head",
    "head": "head",
}

JSON_TO_UI_SLOT = {
    "flower": "flower",
    "feather": "plume",
    "sand": "sands",
    "cup": "goblet",
    "head": "circlet",
}


def ui_positions_to_legacy_positions(ui: dict[str, bool] | None) -> dict[str, bool]:
    """前端 plume/sands/... → JSON 花羽沙杯头 五键。"""
    legacy = {p: True for p in ["flower", "feather", "sand", "cup", "head"]}
    if not ui:
        return legacy
    for ui_k, en in ui.items():
        jk = UI_TO_JSON_POSITION.get(ui_k)
        if jk is not None:
            legacy[jk] = bool(en)
    return legacy


def get_set_type(original_set_name: str) -> str:
    target_sets_mapping = {
        "tenacityOfTheMillelith": "千岩套",
        "VourukashasGlow": "花海套",
        "vourukashasGlow": "花海套",
        "adventurer": "冒险家",
    }
    return target_sets_mapping.get(original_set_name, "其他")
