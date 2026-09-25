from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_MAP_PATH = Path(__file__).with_name("set_name_map.json")
_CATALOG_FALLBACK = (
    Path(__file__).resolve().parents[2]
    / "控分中枢"
    / "resources"
    / "artifact_set_catalog.json"
)


@lru_cache(maxsize=1)
def _load_map() -> tuple[dict[str, str], dict[str, str]]:
    raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    if "good_setKey_to_mona_setName" in raw:
        mapping = {str(k): str(v) for k, v in raw["good_setKey_to_mona_setName"].items()}
    else:
        mapping = {str(k): str(v) for k, v in (raw.get("from_mona_name2") or {}).items()}
    aliases = {str(k): str(v) for k, v in (raw.get("irminsul_aliases") or {}).items()}
    for k, v in aliases.items():
        mapping[k] = v
    return mapping, aliases


def good_set_key_to_mona(set_key: str) -> str:
    """Map GOOD/Irminsul setKey to Mona/YAS setName."""
    s = str(set_key or "").strip()
    if not s:
        return s

    mapping, _ = _load_map()
    if s in mapping:
        return mapping[s]

    logger.warning("unknown GOOD setKey %r — passthrough unchanged", s)
    return s


def reload_map() -> None:
    _load_map.cache_clear()
