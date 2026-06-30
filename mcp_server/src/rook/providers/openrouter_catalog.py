"""OpenRouter model catalog: curated favorites + refreshable metadata cache.

Network is confined to refresh().  load() is pure-disk.  Routing never reads
this module — a missing/stale/corrupt cache never blocks routing a configured
openrouter/ model.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

CACHE_SCHEMA_VERSION = 1
OPENROUTER_MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"
STALE_AFTER_SECONDS = 7 * 24 * 3600  # freshness is observable, never enforced on routing

_FAVORITES_PARTS = ("openrouter_favorites.json",)
_CACHE_PARTS = ("generated", "openrouter_catalog_cache.json")
_OPENROUTER_PREFIX = "openrouter/"


def to_openrouter_id(litellm_id: str) -> str:
    """``openrouter/anthropic/claude-x`` -> ``anthropic/claude-x`` (strip one prefix)."""
    if litellm_id.startswith(_OPENROUTER_PREFIX):
        return litellm_id[len(_OPENROUTER_PREFIX):]
    return litellm_id


def to_litellm_id(catalog_id: str) -> str:
    """``anthropic/claude-x`` -> ``openrouter/anthropic/claude-x`` (add one prefix)."""
    if catalog_id.startswith(_OPENROUTER_PREFIX):
        return catalog_id
    return _OPENROUTER_PREFIX + catalog_id


@dataclass(frozen=True)
class Favorite:
    id: str  # LiteLLM form, e.g. "openrouter/anthropic/claude-3.7-sonnet"
    notes: Optional[str] = None
    tags: tuple[str, ...] = ()


def load_favorites(path: Optional[Path] = None) -> list[Favorite]:
    """Read curated favorites (human-authored).  Missing/invalid file -> empty list."""
    fav_path = path or resolve_readable_knowledge_path(*_FAVORITES_PARTS)
    fav_path = Path(fav_path)
    if not fav_path.exists():
        return []
    try:
        raw = json.loads(fav_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    favorites: list[Favorite] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            favorites.append(Favorite(id=entry))
        elif isinstance(entry, dict) and entry.get("id"):
            favorites.append(Favorite(
                id=entry["id"],
                notes=entry.get("notes"),
                tags=tuple(entry.get("tags", []) or ()),
            ))
    return favorites
