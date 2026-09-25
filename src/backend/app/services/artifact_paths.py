"""圣遗物 JSON：内置参考库（resources/reference），单档 + 星级筛选。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

BuiltinStatMode = Literal["hp", "atk", "def", "em"]
BuiltinTierMode = Literal["lite", "standard", "full"]

BUILTIN_REFERENCE_LABELS: dict[BuiltinStatMode, str] = {
    "hp": "内置生命参考库（非你的背包）",
    "atk": "内置攻击参考库（非你的背包）",
    "def": "内置防御参考库（非你的背包）",
    "em": "内置精通参考库（非你的背包）",
}

BUILTIN_TIER_LABELS: dict[BuiltinTierMode, str] = {
    "lite": "精简",
    "standard": "标准",
    "full": "完整",
}

POSITIONS = ("flower", "feather", "sand", "cup", "head")

DEFAULT_BUILTIN_STAT: BuiltinStatMode = "hp"
DEFAULT_ALLOWED_STARS = [5]
BUILTIN_PLACEHOLDER = "内置圣遗物"

_meta_cache: dict[str, Any] | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def reference_dir() -> Path:
    return project_root() / "resources" / "reference"


def normalize_builtin_stat(stat: str | None) -> BuiltinStatMode:
    key = str(stat or "").strip().lower()
    if key in BUILTIN_REFERENCE_LABELS:
        return key  # type: ignore[return-value]
    return DEFAULT_BUILTIN_STAT


def normalize_builtin_tier(tier: str | None) -> BuiltinTierMode | None:
    key = str(tier or "").strip().lower()
    if key in BUILTIN_TIER_LABELS:
        return key  # type: ignore[return-value]
    return None


def _load_meta_file() -> dict[str, Any] | None:
    global _meta_cache
    if _meta_cache is not None:
        return _meta_cache
    meta_path = reference_dir() / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        _meta_cache = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _meta_cache


def count_pieces_in_json(data: dict[str, Any]) -> int:
    return sum(len(data.get(p) or []) for p in POSITIONS)


def stars_in_json(data: dict[str, Any]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for pos in POSITIONS:
        for piece in data.get(pos) or []:
            star = int(piece.get("star") or 5)
            counts[star] = counts.get(star, 0) + 1
    return dict(sorted(counts.items(), reverse=True))


def bundled_reference_filename(
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> str:
    """默认单档 {stat}_reference.json；缺失时自动 fallback 旧三档 full→standard→lite→v1。"""
    mode = normalize_builtin_stat(stat if isinstance(stat, str) else (stat or DEFAULT_BUILTIN_STAT))
    ref = reference_dir()
    unified = f"{mode}_reference.json"
    if (ref / unified).is_file():
        return unified
    t = normalize_builtin_tier(tier if isinstance(tier, str) else tier)
    if t is not None:
        legacy = f"{mode}_reference_{t}.json"
        if (ref / legacy).is_file():
            return legacy
    for lt in ("full", "standard", "lite"):
        legacy = f"{mode}_reference_{lt}.json"
        if (ref / legacy).is_file():
            return legacy
    v1 = f"{mode}_reference_v1.json"
    if (ref / v1).is_file():
        return v1
    return unified


def bundled_reference_path(
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> Path:
    return reference_dir() / bundled_reference_filename(stat, tier)


def bundled_reference_exists(
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> bool:
    return bundled_reference_path(stat, tier).is_file()


def resolve_artifact_json_path(
    user_path: str | None,
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> Path | None:
    """用户路径非空时返回 None（由调用方读用户文件）；空则返回内置路径（若存在）。"""
    if str(user_path or "").strip():
        return None
    p = bundled_reference_path(stat, tier)
    return p if p.is_file() else None


def load_reference_json(
    path: Path | None = None,
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> dict[str, Any]:
    p = path or bundled_reference_path(stat, tier)
    if not p.is_file():
        raise FileNotFoundError(f"未找到内置参考库: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or isinstance(raw, list):
        raise ValueError("内置参考库根节点须为对象。")
    return raw


def display_path_for_builtin(
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> str:
    mode = normalize_builtin_stat(stat if isinstance(stat, str) else (stat or DEFAULT_BUILTIN_STAT))
    return f"resources/reference/{bundled_reference_filename(mode, tier)}"


def piece_count_for(stat: BuiltinStatMode, tier: BuiltinTierMode | None = None) -> int:
    meta = _load_meta_file()
    if meta and stat in (meta.get("stats") or {}):
        return int(meta["stats"][stat].get("piece_count") or 0)
    path = bundled_reference_path(stat, tier)
    if path.is_file():
        return count_pieces_in_json(load_reference_json(path=path))
    return 0


def available_stars_for(stat: BuiltinStatMode) -> list[int]:
    meta = _load_meta_file()
    if meta and stat in (meta.get("stats") or {}):
        by_star = meta["stats"][stat].get("by_star") or {}
        return sorted((int(k) for k in by_star), reverse=True)
    if bundled_reference_exists(stat):
        return sorted(stars_in_json(load_reference_json(stat=stat)).keys(), reverse=True)
    return list(DEFAULT_ALLOWED_STARS)


def builtin_meta(
    stat: BuiltinStatMode | str | None = None,
    tier: BuiltinTierMode | str | None = None,
) -> dict[str, Any]:
    mode = normalize_builtin_stat(stat if isinstance(stat, str) else (stat or DEFAULT_BUILTIN_STAT))
    t = normalize_builtin_tier(tier if isinstance(tier, str) else tier)
    filename = bundled_reference_filename(mode, t)
    p = bundled_reference_path(mode, t)
    exists = p.is_file()
    stars = available_stars_for(mode) if exists else list(DEFAULT_ALLOWED_STARS)
    return {
        "ok": True,
        "stat": mode,
        "tier": t,
        "tier_label": BUILTIN_TIER_LABELS[t] if t else None,
        "tier_deprecated": True,
        "piece_count": piece_count_for(mode, t) if exists else 0,
        "bundled_filename": filename,
        "bundled_path": str(p.resolve()) if exists else str(p),
        "bundled_exists": exists,
        "display_path": display_path_for_builtin(mode, t),
        "placeholder": BUILTIN_PLACEHOLDER,
        "label": BUILTIN_REFERENCE_LABELS[mode],
        "available_stats": list(BUILTIN_REFERENCE_LABELS.keys()),
        "available_stars": stars,
        "default_allowed_stars": list(DEFAULT_ALLOWED_STARS),
    }


def list_builtin_meta() -> dict[str, Any]:
    return {
        "ok": True,
        "placeholder": BUILTIN_PLACEHOLDER,
        "default_stat": DEFAULT_BUILTIN_STAT,
        "default_allowed_stars": list(DEFAULT_ALLOWED_STARS),
        "stats": {k: builtin_meta(k) for k in BUILTIN_REFERENCE_LABELS},
    }
