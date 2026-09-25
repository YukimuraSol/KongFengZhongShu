"""《圣显之钥》配生命：数据库、process_artifacts、面板生命与枚举（严格对齐参考实现）。"""

from .bennett import calculate_all_hp_variants, calculate_bennett_hp, calculate_set_bonus
from .db import get_merged_hp_database, init_default_hp_database
from .display_format import format_artifact_info
from .process_artifacts import process_artifacts

__all__ = [
    "calculate_all_hp_variants",
    "calculate_bennett_hp",
    "calculate_set_bonus",
    "get_merged_hp_database",
    "init_default_hp_database",
    "format_artifact_info",
    "process_artifacts",
]
