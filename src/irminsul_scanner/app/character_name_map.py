"""GOOD/Irminsul location (PascalCase) → Mona/YAS equip（角色中文名）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_MAP_PATH = Path(__file__).with_name("character_name_map.json")

# ponytail: 仅作缺口补丁；完整表由 scripts/extract_mona_char_map_from_local.py 从本机莫娜 YAS 生成。
_EXTRA: dict[str, str] = {}


@lru_cache(maxsize=1)
def _load() -> dict[str, str]:
    out: dict[str, str] = {}
    if _MAP_PATH.is_file():
        raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        mapping = raw.get("good_location_to_mona_equip") or raw
        out.update({str(k): str(v) for k, v in mapping.items()})
    out.update(_EXTRA)  # 新角色覆盖/补全
    return out


def good_location_to_mona_equip(location: str | None) -> str | None:
    """English GOOD location → Chinese equip; unknown keys pass through."""
    key = (location or "").strip()
    if not key:
        return None
    return _load().get(key, key)
