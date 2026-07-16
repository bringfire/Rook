"""
Tool Registry
=============

Progressive tool disclosure for Rook's ~211 MCP tools.

Three tiers:
  Tier 0: Always loaded (~10 tools, ~1500 tokens)
  Tier 1: Named groups loaded via ``request_tools``
  Tier 2: Individual tools found via ``search_tools``

Catalog source: MCP Tool objects from server.py's list_tools(),
converted to LiteLLM format at startup.

Adapted from Engram's ToolRegistry for the Rhino/GH domain.
"""

import inspect
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from ..runtime_paths import resolve_writable_knowledge_path
from ..tool_lifecycle import (
    filter_litellm_catalog,
    filter_litellm_schemas,
    filter_mcp_records,
    lifecycle_fingerprint,
)

from .chat.tool_contracts import normalize_catalog, normalize_litellm_tool_schema
from .tool_groups import (
    TIER_0,
    AGENT_TIER_0,
    TOOL_GROUPS,
    MCP_ONLY_GROUPS,
)

logger = logging.getLogger(__name__)


def mcp_tool_to_litellm(tool) -> dict:
    """Convert an MCP Tool object to LiteLLM tool schema format.

    MCP format:
        Tool(name="...", description="...", inputSchema={...})

    LiteLLM format:
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
    return normalize_litellm_tool_schema({
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or tool.name.replace("_", " "),
            "parameters": input_schema or {
                "type": "object",
                "properties": {},
            },
        },
    })


def build_catalog_from_mcp_tools(tools: list) -> Dict[str, dict]:
    """Convert a list of MCP Tool objects to a LiteLLM catalog dict.

    Args:
        tools: List of MCP Tool objects from list_tools().

    Returns:
        Dict mapping tool_name -> LiteLLM schema.
    """
    catalog = {}
    for tool in filter_mcp_records(tools):
        schema = mcp_tool_to_litellm(tool)
        catalog[tool.name] = schema
    logger.info(f"Built catalog with {len(catalog)} tools from MCP")
    return catalog


def get_catalog_cache_path() -> Path:
    """Return the canonical path to the catalog cache file."""
    return resolve_writable_knowledge_path("agent_tool_catalog.json")


@dataclass(frozen=True)
class CatalogCacheState:
    catalog: dict[str, dict] | None
    refresh_requested: bool
    source: Literal[
        "current",
        "legacy",
        "fingerprint_mismatch",
        "missing",
        "unreadable",
    ]


@dataclass(frozen=True)
class CatalogStartupResult:
    catalog: dict[str, dict] | None
    status: Literal["fresh", "degraded_cache", "degraded_fallback", "unavailable"]
    persisted: bool
    refresh_requested: bool


def _safe_normalized_catalog(
    raw_catalog: Mapping[object, object],
) -> dict[str, dict] | None:
    """Lifecycle-filter and normalize a catalog, rejecting empty/malformed data."""
    try:
        admitted = filter_litellm_catalog(raw_catalog)
        if not admitted:
            return None
        if not all(
            isinstance(name, str) and isinstance(schema, dict)
            for name, schema in admitted.items()
        ):
            return None
        normalized = normalize_catalog(dict(admitted))
        return normalized or None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def load_catalog_cache_state(path: Optional[Path] = None) -> CatalogCacheState:
    """Load, lifecycle-revalidate, and classify the catalog cache."""
    cache_path = path or get_catalog_cache_path()
    if not cache_path.exists():
        return CatalogCacheState(
            catalog=None,
            refresh_requested=True,
            source="missing",
        )

    try:
        with open(cache_path, encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except (json.JSONDecodeError, OSError, UnicodeError):
        logger.warning("Cache corrupted or unreadable, will rebuild")
        return CatalogCacheState(
            catalog=None,
            refresh_requested=True,
            source="unreadable",
        )

    if not isinstance(payload, Mapping) or not payload:
        return CatalogCacheState(
            catalog=None,
            refresh_requested=True,
            source="unreadable",
        )

    envelope_keys = {"lifecycle_fingerprint", "catalog"}
    if set(payload) == envelope_keys:
        raw_fingerprint = payload.get("lifecycle_fingerprint")
        raw_catalog = payload.get("catalog")
        if not isinstance(raw_fingerprint, str) or not isinstance(raw_catalog, Mapping):
            return CatalogCacheState(
                catalog=None,
                refresh_requested=True,
                source="unreadable",
            )
        if raw_fingerprint == lifecycle_fingerprint():
            source: Literal["current", "fingerprint_mismatch"] = "current"
            refresh_requested = False
        else:
            source = "fingerprint_mismatch"
            refresh_requested = True
    elif envelope_keys & set(payload):
        return CatalogCacheState(
            catalog=None,
            refresh_requested=True,
            source="unreadable",
        )
    else:
        raw_catalog = payload
        source = "legacy"
        refresh_requested = True

    catalog = _safe_normalized_catalog(raw_catalog)
    if catalog is None:
        return CatalogCacheState(
            catalog=None,
            refresh_requested=True,
            source="unreadable",
        )

    logger.info(
        "Loaded %d safe schemas from cache: %s (%s)",
        len(catalog),
        cache_path.name,
        source,
    )
    return CatalogCacheState(
        catalog=catalog,
        refresh_requested=refresh_requested,
        source=source,
    )


def load_catalog_from_cache(path: Optional[Path] = None) -> Optional[Dict[str, dict]]:
    """Compatibility wrapper returning only a safely revalidated catalog."""
    return load_catalog_cache_state(path).catalog


def save_catalog_to_cache(catalog: Mapping[str, dict], path: Path) -> bool:
    """Lifecycle-filter and atomically persist the canonical cache envelope."""
    cache_path = path
    admitted = filter_litellm_catalog(catalog)
    envelope = {
        "lifecycle_fingerprint": lifecycle_fingerprint(),
        "catalog": admitted,
    }
    try:
        serialized = json.dumps(envelope, indent=2)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{cache_path.name}.",
            suffix=".tmp",
            dir=cache_path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as cache_file:
                cache_file.write(serialized)
                cache_file.flush()
                os.fsync(cache_file.fileno())
            os.replace(tmp_name, cache_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        logger.info(f"Cached {len(admitted)} schemas to {cache_path.name}")
        return True
    except Exception as e:
        logger.warning(f"Could not cache schemas: {e}")
        return False


async def refresh_catalog_at_startup(
    tool_loader,
    *,
    cache_path: Path | None = None,
    fallback: Mapping[str, dict] | None = None,
) -> CatalogStartupResult:
    """Build a fresh unprofiled catalog while retaining only safe fallbacks."""
    resolved_cache_path = cache_path or get_catalog_cache_path()
    old_state = load_catalog_cache_state(resolved_cache_path)

    try:
        loaded_tools = tool_loader()
        if inspect.isawaitable(loaded_tools):
            loaded_tools = await loaded_tools
        fresh_catalog = build_catalog_from_mcp_tools(list(loaded_tools))
        if not fresh_catalog:
            raise ValueError("fresh catalog is empty")
    except Exception as exc:
        logger.warning("Catalog refresh construction failed: %s", exc)
        if old_state.catalog is not None:
            return CatalogStartupResult(
                catalog=old_state.catalog,
                status="degraded_cache",
                persisted=False,
                refresh_requested=True,
            )
        safe_fallback = (
            _safe_normalized_catalog(fallback)
            if isinstance(fallback, Mapping)
            else None
        )
        if safe_fallback is not None:
            return CatalogStartupResult(
                catalog=safe_fallback,
                status="degraded_fallback",
                persisted=False,
                refresh_requested=True,
            )
        return CatalogStartupResult(
            catalog=None,
            status="unavailable",
            persisted=False,
            refresh_requested=True,
        )

    persisted = save_catalog_to_cache(fresh_catalog, resolved_cache_path)
    return CatalogStartupResult(
        catalog=fresh_catalog,
        status="fresh" if persisted else "degraded_cache",
        persisted=persisted,
        refresh_requested=not persisted,
    )


class ToolRegistry:
    """Progressive tool disclosure. Manages which tools the model can see.

    Usage:
        # From MCP tools
        tools = await list_tools()
        catalog = build_catalog_from_mcp_tools(tools)
        registry = ToolRegistry(catalog=catalog)

        # Or from cache
        registry = ToolRegistry(catalog=load_catalog_from_cache(path))

        # Get schemas for LLM
        schemas = registry.get_active_schemas()

        # Load a group
        result = registry.request_group("gh_canvas", turn=1)

        # Search for tools
        result = registry.search("boolean", turn=2)
    """

    def __init__(
        self,
        catalog: Optional[Dict[str, dict]] = None,
        max_active: int = 64,
        tier0: Optional[Set[str]] = None,
        allowed_groups: Optional[Set[str]] = None,
        agent_mode: bool = False,
    ):
        """Initialize with a tool catalog.

        Args:
            catalog: Dict of tool_name -> LiteLLM schema.
            max_active: Hard cap on simultaneously active tools.
            tier0: Custom Tier 0 tool set. If None, uses default TIER_0.
            allowed_groups: If set, only these groups can be loaded.
                          Used by planner to enforce read-only access.
            agent_mode: If True, uses AGENT_TIER_0 (excludes gh_execute_intent).
        """
        raw_catalog = {} if catalog is None else catalog
        self._catalog: Dict[str, dict] = normalize_catalog(
            filter_litellm_catalog(raw_catalog)
        )
        self._max_active = max_active
        if tier0 is not None:
            self._tier0 = tier0
        elif agent_mode:
            self._tier0 = AGENT_TIER_0
        else:
            self._tier0 = TIER_0
        self._allowed_groups = allowed_groups
        self._locally_registered: Set[str] = set()

        # Index descriptions for search
        self._descriptions: Dict[str, str] = {}
        for name, schema in self._catalog.items():
            func = schema.get("function", {})
            self._descriptions[name] = func.get("description", "")

        # Build groups from TOOL_GROUPS (only include tools in catalog)
        self._groups = self._build_groups()

        # Meta-tool schemas
        self._meta_schemas = self._build_meta_schemas()

        # Active state
        self._active: Set[str] = set()
        self._always_active: Set[str] = set()
        self._initialize_tier0()

        # Staleness tracking
        self._last_used: Dict[str, int] = {}
        self._current_turn: int = 0

        logger.info(
            f"ToolRegistry: {len(self._catalog)} tools in catalog, "
            f"{len(self._groups)} groups, "
            f"{len(self._active)} active (Tier 0)"
        )

    def _build_groups(self) -> Dict[str, List[str]]:
        """Build groups from TOOL_GROUPS, filtering to tools in catalog."""
        groups: Dict[str, List[str]] = {}
        for group_name, tools in TOOL_GROUPS.items():
            valid = [t for t in tools if t in self._catalog]
            if valid:
                groups[group_name] = valid
        return groups

    def _build_meta_schemas(self) -> Dict[str, dict]:
        """Build schemas for request_tools and search_tools."""
        # Exclude MCP-only groups from the listing — agents can't load them
        group_names = sorted(
            g for g in self._groups.keys() if g not in MCP_ONLY_GROUPS
        )
        group_list = ", ".join(group_names) if group_names else "(no groups)"

        schemas = {
            "request_tools": {
                "type": "function",
                "function": {
                    "name": "request_tools",
                    "description": (
                        f"Load a group of related tools by name. "
                        f"Available groups: {group_list}"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "group": {
                                "type": "string",
                                "description": "Tool group name",
                            }
                        },
                        "required": ["group"],
                        "additionalProperties": False,
                    },
                },
            },
            "search_tools": {
                "type": "function",
                "function": {
                    "name": "search_tools",
                    "description": (
                        "Search for tools by description. Returns matching "
                        "tools and loads them into the active set."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What you need to do",
                            }
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
        }
        return normalize_catalog(schemas)

    def _initialize_tier0(self) -> None:
        """Activate Tier 0 tools."""
        for name in self._tier0:
            if name in self._catalog or name in self._meta_schemas:
                self._active.add(name)
                self._always_active.add(name)

    # ================================================================
    # Public API
    # ================================================================

    def get_active_schemas(self) -> List[dict]:
        """Get LiteLLM-format tool schemas for all active tools."""
        schemas = []
        for name in sorted(self._active):
            if name in self._meta_schemas:
                schemas.append(normalize_litellm_tool_schema(self._meta_schemas[name]))
            elif name in self._catalog:
                schemas.append(normalize_litellm_tool_schema(self._catalog[name]))
        return filter_litellm_schemas(schemas)

    def get_active_count(self) -> int:
        """Number of currently active tools."""
        return len(self._active)

    def get_group_names(self) -> List[str]:
        """Available group names for request_tools (excludes MCP-only)."""
        return sorted(g for g in self._groups.keys() if g not in MCP_ONLY_GROUPS)

    def is_meta_tool(self, name: str) -> bool:
        """Check if a tool is a meta-tool (handled internally)."""
        return name in self._meta_schemas

    def request_group(self, group_name: str, turn: Optional[int] = None) -> dict:
        """Load a Tier 1 tool group.

        Args:
            group_name: Name of the tool group to load.
            turn: Current agent turn (for staleness tracking).

        Returns:
            Dict with loaded/already_active lists and counts.
        """
        # Block MCP-only groups unless locally registered
        if group_name in MCP_ONLY_GROUPS:
            group_tools = self._groups.get(group_name, [])
            all_local = group_tools and all(
                t in self._locally_registered for t in group_tools
            )
            if not all_local:
                return {
                    "success": False,
                    "error": (
                        f"Group '{group_name}' contains MCP-only tools not "
                        f"available through the bridge."
                    ),
                }

        # Check allowed groups restriction
        if self._allowed_groups is not None and group_name not in self._allowed_groups:
            allowed = sorted(self._allowed_groups)
            return {
                "success": False,
                "error": (
                    f"Group '{group_name}' is not available in this context. "
                    f"Allowed: {', '.join(allowed)}"
                ),
            }

        if group_name not in self._groups:
            available = sorted(self._groups.keys())
            return {
                "success": False,
                "error": (
                    f"Unknown group '{group_name}'. "
                    f"Available: {', '.join(available)}"
                ),
            }

        use_turn = turn if turn is not None else self._current_turn
        tools = self._groups[group_name]
        loaded = []
        already_active = []
        capped = []

        for name in tools:
            if name in self._active:
                already_active.append(name)
            elif name in self._catalog:
                if len(self._active) >= self._max_active:
                    # Try evicting stale tools before giving up
                    freed = self._evict_lru(1)
                    if freed == 0:
                        capped.append(name)
                        continue
                self._active.add(name)
                self._last_used[name] = use_turn
                loaded.append(name)

        result = {
            "success": True,
            "group": group_name,
            "loaded": loaded,
            "already_active": already_active,
            "active_count": len(self._active),
        }
        if capped:
            result["capped"] = capped
            result["cap_warning"] = (
                f"Hit max_active_tools ({self._max_active}). "
                f"{len(capped)} tools not loaded."
            )

        logger.info(
            f"request_tools('{group_name}'): loaded {len(loaded)}, "
            f"already active {len(already_active)}, "
            f"total active {len(self._active)}"
        )
        return result

    def search(self, query: str, top_k: int = 5, turn: Optional[int] = None) -> dict:
        """Tier 2: Keyword search across all tool descriptions.

        Matches query words against tool names and descriptions.
        Auto-loads matching tools into the active set.
        """
        use_turn = turn if turn is not None else self._current_turn
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scores: List[Tuple[str, int, str]] = []

        for name, desc in self._descriptions.items():
            text = f"{name} {desc}".lower()
            score = sum(1 for w in query_words if w in text)
            # Bonus for exact name match
            if query_lower.replace(" ", "_") in name:
                score += 3
            if score > 0:
                scores.append((name, score, desc[:120]))

        scores.sort(key=lambda x: (-x[1], x[0]))
        results = scores[:top_k]

        # Build MCP-only tool set. A tool shared with a non-MCP-only group remains
        # bridgeable through that group and should not be blocked from search.
        non_mcp_group_tools: Set[str] = set()
        for g, tools in self._groups.items():
            if g not in MCP_ONLY_GROUPS:
                non_mcp_group_tools.update(tools)

        mcp_only_tools: Set[str] = set()
        for g in MCP_ONLY_GROUPS:
            if g in self._groups:
                for t in self._groups[g]:
                    if (
                        t not in self._locally_registered
                        and t not in non_mcp_group_tools
                    ):
                        mcp_only_tools.add(t)

        # Build allowlist if group restrictions are set
        allowed_tool_set: Optional[Set[str]] = None
        if self._allowed_groups is not None:
            allowed_tool_set = set(self._always_active)
            for g in self._allowed_groups:
                if g in self._groups:
                    allowed_tool_set.update(self._groups[g])

        # Auto-load found tools
        loaded = []
        for name, _, _ in results:
            if name not in self._active and name in self._catalog:
                if name in mcp_only_tools:
                    continue
                if allowed_tool_set is not None and name not in allowed_tool_set:
                    continue
                if len(self._active) >= self._max_active:
                    freed = self._evict_lru(1)
                    if freed == 0:
                        break
                self._active.add(name)
                self._last_used[name] = use_turn
                loaded.append(name)

        logger.info(
            f"search_tools('{query}'): {len(results)} matches, loaded {len(loaded)}"
        )
        return {
            "success": True,
            "results": [
                {"name": n, "relevance": s, "description": d}
                for n, s, d in results
            ],
            "loaded": loaded,
            "active_count": len(self._active),
        }

    def mark_used(self, tool_names: Set[str], turn: int) -> None:
        """Record that tools were used on a given turn."""
        self._current_turn = max(self._current_turn, turn)
        for name in tool_names:
            self._last_used[name] = turn

    def deactivate_stale(self, max_stale_turns: int = 5) -> List[str]:
        """Remove tools unused for N turns. Never touches Tier 0."""
        if self._current_turn < max_stale_turns:
            return []

        threshold = self._current_turn - max_stale_turns
        to_remove = [
            name
            for name in self._active
            if name not in self._always_active
            and self._last_used.get(name, 0) < threshold
        ]

        for name in to_remove:
            self._active.discard(name)
            self._last_used.pop(name, None)

        if to_remove:
            logger.info(
                f"Deactivated {len(to_remove)} stale tools: "
                f"{to_remove[:5]}{'...' if len(to_remove) > 5 else ''}"
            )
        return to_remove

    def _evict_lru(self, needed: int) -> int:
        """Evict least-recently-used non-Tier-0 tools to free slots.

        Called when the active set is at capacity and new tools need loading.

        Args:
            needed: Number of slots to free.

        Returns:
            Number of slots actually freed.
        """
        if needed <= 0:
            return 0

        # Candidates: active tools that aren't always-active (Tier 0 / meta)
        candidates = [
            (name, self._last_used.get(name, 0))
            for name in self._active
            if name not in self._always_active
        ]
        # Oldest-used first
        candidates.sort(key=lambda x: x[1])

        freed = 0
        for name, _ in candidates:
            if freed >= needed:
                break
            self._active.discard(name)
            self._last_used.pop(name, None)
            freed += 1

        if freed > 0:
            evicted_names = [c[0] for c in candidates[:freed]]
            logger.info(
                f"LRU evicted {freed} tools to make room: "
                f"{evicted_names[:5]}{'...' if freed > 5 else ''}"
            )
        return freed

    def register_local_catalog(self, catalog: Dict[str, dict]) -> None:
        """Register additional tool schemas (e.g., local Python tools).

        Merges into the existing catalog and rebuilds groups/descriptions.
        """
        admitted_catalog = filter_litellm_catalog(catalog)
        normalized_catalog = normalize_catalog(admitted_catalog)
        self._catalog.update(normalized_catalog)
        for name, schema in normalized_catalog.items():
            func = schema.get("function", {})
            self._descriptions[name] = func.get("description", "")
            self._locally_registered.add(name)
        self._groups = self._build_groups()
        self._meta_schemas = self._build_meta_schemas()
        self._initialize_tier0()
        logger.info(
            f"Registered {len(normalized_catalog)} local tools: "
            f"{list(normalized_catalog.keys())}"
        )

    def reset(self) -> None:
        """Reset to Tier 0 only."""
        self._active = set(self._always_active)
        self._last_used.clear()
        self._current_turn = 0
