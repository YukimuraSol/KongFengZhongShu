"""内置参考库 JSON 元数据校验（防止生命库误用于攻击搜索等）。"""

from __future__ import annotations

from typing import Any, Literal

StatMode = Literal["hp", "atk", "def", "em"]

REFERENCE_SLOT_KEYS = frozenset({"flower", "feather", "sand", "cup", "head"})

_STAT_LABEL = {
    "hp": "生命",
    "atk": "攻击",
    "def": "防御",
    "em": "精通",
}


def reference_json_stat(artifact_json: dict[str, Any] | None) -> str | None:
    """读取参考库文件顶层的 stat 字段；非参考库或无字段则返回 None。"""
    if not artifact_json:
        return None
    raw = artifact_json.get("stat")
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in _STAT_LABEL:
        return key
    return None


def validate_artifact_json_stat(
    artifact_json: dict[str, Any] | None,
    expected_stat: str,
) -> None:
    """参考库 stat 与当前配装属性不一致时抛出 ValueError（同步/异步搜索统一）。"""
    if not artifact_json:
        return
    declared = reference_json_stat(artifact_json)
    if declared is None:
        return
    want = str(expected_stat or "hp").strip().lower()
    if declared == want:
        return
    raise ValueError(
        f"圣遗物 JSON 为{_STAT_LABEL.get(declared, declared)}参考库，"
        f"与当前{_STAT_LABEL.get(want, want)}配装不一致；"
        f"请等待内置库加载完成或重新选择属性。"
    )
