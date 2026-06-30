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


@dataclass
class ModelMetadata:
    litellm_id: str
    openrouter_id: str
    canonical_slug: Optional[str]
    supported_parameters: list[str]
    pricing: dict[str, Any]
    context_length: Optional[int]
    display_name: Optional[str]
    metadata_state: str = "known"  # "known" | "unknown" | "stale"


@dataclass
class CatalogView:
    models: list[ModelMetadata]
    fetched_at: Optional[str]
    last_refresh_attempt_at: Optional[str]
    last_refresh_error: Optional[dict]
    cache_present: bool
    stale: bool


def _cache_path(path: Optional[Path] = None) -> Path:
    return Path(path) if path is not None else resolve_writable_knowledge_path(*_CACHE_PARTS)


def _read_cache(path: Path) -> Optional[dict]:
    """Return the cache dict, or None when missing/corrupt/schema-mismatched."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    return data


def _is_stale(fetched_at: Optional[str], now: Optional[datetime] = None) -> bool:
    if not fetched_at:
        return False  # no successful fetch yet -> models are "unknown", not "stale"
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - ts).total_seconds() > STALE_AFTER_SECONDS


def load(
    favorites_path: Optional[Path] = None,
    cache_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> CatalogView:
    """Pure-disk view of curated favorites enriched with cached metadata."""
    favorites = load_favorites(favorites_path)
    cache = _read_cache(_cache_path(cache_path))
    fetched_at = cache.get("fetched_at") if cache else None
    attempt_at = cache.get("last_refresh_attempt_at") if cache else None
    last_error = cache.get("last_refresh_error") if cache else None
    models_map = (cache or {}).get("models", {}) or {}
    stale = _is_stale(fetched_at, now)

    models: list[ModelMetadata] = []
    for fav in favorites:
        entry = models_map.get(fav.id)
        if entry is None:
            models.append(ModelMetadata(
                litellm_id=fav.id, openrouter_id=to_openrouter_id(fav.id),
                canonical_slug=None, supported_parameters=[], pricing={},
                context_length=None, display_name=None, metadata_state="unknown"))
        else:
            models.append(ModelMetadata(
                litellm_id=fav.id,
                openrouter_id=entry.get("openrouter_id", to_openrouter_id(fav.id)),
                canonical_slug=entry.get("canonical_slug"),
                supported_parameters=list(entry.get("supported_parameters", []) or []),
                pricing=dict(entry.get("pricing", {}) or {}),
                context_length=entry.get("context_length"),
                display_name=entry.get("display_name"),
                metadata_state="stale" if stale else "known"))

    return CatalogView(
        models=models, fetched_at=fetched_at, last_refresh_attempt_at=attempt_at,
        last_refresh_error=last_error, cache_present=cache is not None, stale=stale)
