"""
Grasshopper Knowledge System for Rook.

Provides tiered knowledge lookup for GH components:
- Sparse index for O(1) intent → GUID lookup (no LLM)
- Tiered knowledge (quick/context/errors) for token-aware responses
- Facade class that combines both for unified queries

Architecture mirrors the Rhino DSPy knowledge system.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger("rook.gh_knowledge")


def _gh_read_path(*parts: str) -> Path:
    return resolve_readable_knowledge_path("gh", *parts)


def _gh_write_path(*parts: str) -> Path:
    return resolve_writable_knowledge_path("gh", *parts)


SPARSE_INDEX_READ_PATH = _gh_read_path("sparse_index.json")
SPARSE_INDEX_WRITE_PATH = _gh_write_path("sparse_index.json")
TIERED_KNOWLEDGE_READ_PATH = _gh_read_path("tiered_knowledge.json")
TIERED_KNOWLEDGE_WRITE_PATH = _gh_write_path("tiered_knowledge.json")
COMPONENT_CATALOG_PATH = _gh_read_path("component_catalog.json")
OBSERVATIONS_READ_PATH = _gh_read_path("component_observations.json")
OBSERVATIONS_WRITE_PATH = _gh_write_path("component_observations.json")
OPERATIONS_READ_PATH = _gh_read_path("operations_knowledge.json")
OPERATIONS_WRITE_PATH = _gh_write_path("operations_knowledge.json")

# Tier type
TierLevel = Literal["quick", "context", "errors", "raw"]


def compute_stable_key(category: str, sub_category: str, name: str) -> Optional[str]:
    """Compute a normalized stable identity key for component dedup.

    Returns None if any of the three parts is missing or empty.
    """
    cat = (category or "").strip().lower()
    sub = (sub_category or "").strip().lower()
    n = (name or "").strip().lower()
    if not cat or not sub or not n:
        return None
    return f"{cat}|{sub}|{n}"

# Token estimates per tier
TIER_TOKEN_ESTIMATES = {
    "quick": 20,
    "context": 50,
    "errors": 30,
    "raw": 300,
}


class GHSparseIndex:
    """DEPRECATED: Superseded by UnifiedStore.resolve_components().

    GHKnowledgeStore.query() now delegates to UnifiedStore for GUID resolution
    (922 component notes with phrase-priority scoring via UnifiedIndex).
    This class is retained for backward compat with GHKnowledgeBuilder.ensure_sparse_entry()
    which writes to sparse_index.json. Do not use for new code.

    Original purpose: Sparse index for O(1) component lookup without LLM calls.
    Maps intent keywords to component GUIDs for fast resolution.
    """

    def __init__(self, path: Optional[Path] = None):
        self._uses_default_path = path is None
        self.path = Path(path) if path is not None else SPARSE_INDEX_WRITE_PATH
        self._intent_to_guids: dict[str, list[str]] = {}
        self._guid_to_info: dict[str, dict] = {}
        self._family_to_guids: dict[str, list[str]] = {}
        self._loaded = False

    def _read_path(self) -> Path:
        if not self._uses_default_path:
            return self.path
        return self.path if self.path.exists() else SPARSE_INDEX_READ_PATH

    def _ensure_loaded(self) -> None:
        """Lazy load the sparse index."""
        if self._loaded:
            return

        read_path = self._read_path()
        if not read_path.exists():
            logger.warning(f"Sparse index not found at {read_path}")
            self._loaded = True
            return

        try:
            with open(read_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._intent_to_guids = data.get("intent_to_guids", {})
            self._guid_to_info = data.get("guid_to_info", {})
            self._family_to_guids = data.get("family_to_guids", {})
            self._loaded = True

            logger.info(f"Loaded sparse index: {len(self._intent_to_guids)} intents, {len(self._guid_to_info)} components")

        except Exception as e:
            logger.error(f"Failed to load sparse index: {e}")
            self._loaded = True

    def reload(self) -> int:
        """Force reload from disk. Returns count of intents loaded."""
        self._loaded = False
        self._intent_to_guids = {}
        self._guid_to_info = {}
        self._family_to_guids = {}
        self._ensure_loaded()
        return len(self._intent_to_guids)

    def lookup(self, intent: str) -> list[str]:
        """Look up GUIDs for an intent keyword.

        Args:
            intent: A keyword like "sphere", "add", "slider"

        Returns:
            List of matching component GUIDs (may be empty)
        """
        self._ensure_loaded()

        # Normalize: lowercase, strip
        key = intent.lower().strip()

        # Direct match
        if key in self._intent_to_guids:
            return self._intent_to_guids[key]

        # Try without common prefixes/suffixes
        for variant in [key.rstrip("s"), f"{key}s", key.replace("-", " "), key.replace("_", " ")]:
            if variant in self._intent_to_guids:
                return self._intent_to_guids[variant]

        return []

    def lookup_multi(self, intent: str) -> list[str]:
        """Look up GUIDs for a multi-word intent, prioritizing phrase matches.

        Args:
            intent: A phrase like "divide curve" or "create sphere with slider"

        Returns:
            List of unique matching GUIDs, with phrase matches first
        """
        self._ensure_loaded()

        normalized = intent.lower().strip()
        words = re.split(r'\s+', normalized)
        guids = []
        seen = set()

        # 1. Try full phrase match first
        for guid in self.lookup(normalized):
            if guid not in seen:
                guids.append(guid)
                seen.add(guid)

        # 2. Try progressively smaller phrases (2+ words)
        if len(words) > 1:
            for phrase_len in range(len(words) - 1, 1, -1):
                for i in range(len(words) - phrase_len + 1):
                    phrase = " ".join(words[i:i + phrase_len])
                    for guid in self.lookup(phrase):
                        if guid not in seen:
                            guids.append(guid)
                            seen.add(guid)

        # 3. Fall back to individual words
        for word in words:
            for guid in self.lookup(word):
                if guid not in seen:
                    guids.append(guid)
                    seen.add(guid)

        return guids

    def get_info(self, guid: str) -> Optional[dict]:
        """Get basic info for a component GUID.

        Args:
            guid: Component GUID

        Returns:
            Dict with name, family, nickName or None if not found
        """
        self._ensure_loaded()
        return self._guid_to_info.get(guid)

    def get_family(self, family: str) -> list[str]:
        """Get all GUIDs in a component family.

        Args:
            family: Family name like "primitives", "math", "input"

        Returns:
            List of GUIDs in that family
        """
        self._ensure_loaded()
        return self._family_to_guids.get(family, [])

    def all_intents(self) -> list[str]:
        """Get all known intent keywords."""
        self._ensure_loaded()
        return list(self._intent_to_guids.keys())


class GHTieredKnowledge:
    """Component-level gotcha and error data store (tiered_knowledge.json).

    NOTE: GUID resolution and component discovery are now handled by
    UnifiedStore.resolve_components(). This class is retained for curated
    error/gotcha data keyed by GUID. The get(), get_params(), and
    get_wiring_pattern() methods are no longer called by GHKnowledgeStore
    for primary queries — only get_gotchas() is still active.

    Original tiered depths:
    - quick: ~20 tokens, essential syntax
    - context: ~50 tokens, mode-specific rules
    - errors: ~30 tokens, what fails and why
    - raw: full component info from catalog
    """

    def __init__(self, tiered_path: Optional[Path] = None, catalog_path: Optional[Path] = None):
        self._uses_default_tiered_path = tiered_path is None
        self.tiered_path = Path(tiered_path) if tiered_path is not None else TIERED_KNOWLEDGE_WRITE_PATH
        self.catalog_path = Path(catalog_path) if catalog_path is not None else COMPONENT_CATALOG_PATH
        self._components: dict[str, dict] = {}
        self._wiring_patterns: dict[str, dict] = {}
        self._global_gotchas: list[dict] = []
        self._catalog: dict = {}
        self._loaded = False
        self._catalog_loaded = False

    def _read_path(self) -> Path:
        if not self._uses_default_tiered_path:
            return self.tiered_path
        return self.tiered_path if self.tiered_path.exists() else TIERED_KNOWLEDGE_READ_PATH

    def _ensure_loaded(self) -> None:
        """Lazy load the tiered knowledge."""
        if self._loaded:
            return

        read_path = self._read_path()
        if not read_path.exists():
            logger.warning(f"Tiered knowledge not found at {read_path}")
            self._loaded = True
            return

        try:
            with open(read_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._components = data.get("components", {})
            self._wiring_patterns = data.get("wiring_patterns", {})
            self._global_gotchas = data.get("global_gotchas", [])
            self._loaded = True

            logger.info(f"Loaded tiered knowledge: {len(self._components)} components")

        except Exception as e:
            logger.error(f"Failed to load tiered knowledge: {e}")
            self._loaded = True

    def _ensure_catalog_loaded(self) -> None:
        """Lazy load the full component catalog for raw tier."""
        if self._catalog_loaded:
            return

        if not self.catalog_path.exists():
            logger.warning(f"Component catalog not found at {self.catalog_path}")
            self._catalog_loaded = True
            return

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self._catalog = json.load(f)
            self._catalog_loaded = True

        except Exception as e:
            logger.error(f"Failed to load component catalog: {e}")
            self._catalog_loaded = True

    def reload(self) -> int:
        """Force reload from disk. Returns count of components loaded."""
        self._loaded = False
        self._catalog_loaded = False
        self._components = {}
        self._wiring_patterns = {}
        self._global_gotchas = []
        self._catalog = {}
        self._ensure_loaded()
        return len(self._components)

    def get(self, guid: str, tier: TierLevel = "context") -> Optional[dict]:
        """Get tiered knowledge for a component.

        Args:
            guid: Component GUID
            tier: Depth level (quick, context, errors, raw)

        Returns:
            Dict with requested tier data, or None if not found
        """
        self._ensure_loaded()

        component = self._components.get(guid)
        if not component:
            # Fall back to catalog for raw tier
            if tier == "raw":
                return self._get_from_catalog(guid)
            return None

        if tier == "quick":
            return {
                "guid": guid,
                "name": component.get("name"),
                "quick": component.get("quick"),
            }
        elif tier == "context":
            return {
                "guid": guid,
                "name": component.get("name"),
                "family": component.get("family"),
                "quick": component.get("quick"),
                "contexts": component.get("contexts", {}),
                "params": component.get("params", {}),
            }
        elif tier == "errors":
            return {
                "guid": guid,
                "name": component.get("name"),
                "errors": component.get("errors"),
            }
        elif tier == "raw":
            # Combine tiered data with catalog data
            catalog_data = self._get_from_catalog(guid) or {}
            return {
                **catalog_data,
                **component,
                "guid": guid,
            }

        return None

    def _get_from_catalog(self, guid: str) -> Optional[dict]:
        """Get component from full catalog."""
        self._ensure_catalog_loaded()

        # Search through catalog sections
        core = self._catalog.get("core_components", {})
        for section_name, section in core.items():
            if isinstance(section, dict):
                for comp_name, comp_data in section.items():
                    if isinstance(comp_data, dict) and comp_data.get("guid") == guid:
                        return {
                            "guid": guid,
                            "name": comp_name,
                            "section": section_name,
                            **comp_data,
                        }

        return None

    def get_params(self, guid: str) -> Optional[dict]:
        """Get input/output params for a component.

        Args:
            guid: Component GUID (creation GUID)

        Returns:
            Dict with inputs and outputs, or None
        """
        self._ensure_loaded()

        component = self._components.get(guid)
        if component:
            return component.get("params")
        return None

    def get_gotchas(self, guid: str) -> list[str]:
        """Get gotchas/warnings for a component.

        Args:
            guid: Component GUID (creation GUID)

        Returns:
            List of warning strings
        """
        self._ensure_loaded()

        gotchas = []

        # Component-specific errors
        component = self._components.get(guid)
        if component and component.get("errors"):
            gotchas.append(component["errors"])

        # Global gotchas that apply to this component
        if component:
            name = component.get("name", "")
            for gotcha in self._global_gotchas:
                if name in gotcha.get("applies_to", []):
                    gotchas.append(gotcha["text"])

        return gotchas

    def get_wiring_pattern(self, pattern_name: str) -> Optional[dict]:
        """Get a predefined wiring pattern.

        Args:
            pattern_name: Pattern name like "parametric_sphere"

        Returns:
            Pattern dict with components and connections
        """
        self._ensure_loaded()
        return self._wiring_patterns.get(pattern_name)

    def all_components(self) -> list[str]:
        """Get all component GUIDs with tiered knowledge."""
        self._ensure_loaded()
        return list(self._components.keys())


# Trigger evaluation rules for operations_knowledge.json gotchas.
# Maps trigger name → lambda that checks context dict.
# Add new triggers here; no need to edit query_operation().
_TRIGGER_RULES: dict[str, callable] = {
    "target_is_slider": lambda c: c.get("target_type") == "slider",
    "target_is_integer_slider": lambda c: c.get("target_type") == "integer_slider",
    "contains_list_component": lambda c: c.get("involves_list"),
    "target_in_group": lambda c: c.get("in_group"),
    "target_has_expression": lambda c: c.get("has_expression"),
    "component_from_plugin": lambda c: c.get("from_plugin"),
    "param_has_multiple_sources": lambda c: c.get("multiple_sources"),
    "data_structure_mismatch": lambda c: c.get("data_mismatch"),
}


def _evaluate_trigger(trigger: str, context: dict) -> bool:
    """Evaluate whether a gotcha trigger matches the current context."""
    if trigger == "always":
        return True
    evaluator = _TRIGGER_RULES.get(trigger)
    return bool(evaluator(context)) if evaluator else False


class GHKnowledgeStore:
    """Facade for GH knowledge queries.

    Component GUID resolution delegates to UnifiedStore (922 component notes
    with full I/O, descriptions, families, and A-MEM links). GHTieredKnowledge
    is retained for component-specific gotcha/error data. Operation-level
    knowledge (gotchas, common mistakes) reads from operations_knowledge.json.

    History:
        Previously combined GHSparseIndex (flat keyword→GUID map) with
        GHTieredKnowledge (component details keyed by GUID). GHSparseIndex
        had ~250 keywords; UnifiedStore has 922 component notes with
        multi-dimensional index (intents, keywords, tags, components).
        GHSparseIndex is now deprecated — see class definition above.
    """

    def __init__(self):
        # GHTieredKnowledge retained for gotcha/error data only.
        # GUID resolution now goes through UnifiedStore.resolve_components().
        self.tiered_knowledge = GHTieredKnowledge()
        self._operations_knowledge: Optional[dict] = None
        self._operations_path = OPERATIONS_WRITE_PATH

    def _ensure_operations_loaded(self) -> None:
        """Load operations knowledge if not already loaded."""
        if self._operations_knowledge is not None:
            return

        operations_read_path = self._operations_path if self._operations_path.exists() else OPERATIONS_READ_PATH
        if operations_read_path.exists():
            try:
                with open(operations_read_path) as f:
                    self._operations_knowledge = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load operations knowledge: {e}")
                self._operations_knowledge = {"operations": {}}
        else:
            self._operations_knowledge = {"operations": {}}

    def query(self, intent: str, depth: TierLevel = "context") -> dict[str, Any]:
        """Query knowledge for an intent.

        Resolves component GUIDs via UnifiedStore (922 component notes with
        phrase-priority scoring). Collects gotchas from GHTieredKnowledge.

        Args:
            intent: Natural language intent or keyword
            depth: Tier to return (quick, context, errors, raw)

        Returns:
            {
                "tier": "context",
                "source": "unified_store" or "none",
                "guids": ["dabc854d-...", ...],
                "components": [{guid, name, family, quick, params, source, note_id}, ...],
                "available_tiers": ["quick", "context", "errors", "raw"],
                "token_estimates": {"quick": 20, "context": 50, ...},
                "gotchas": ["Warning about...", ...],
                "hint": "Suggestion for next action"
            }
        """
        from .unified_store import get_unified_store

        try:
            unified = get_unified_store()
            components = unified.resolve_components(intent, limit=10)
        except Exception as e:
            logger.error(f"GHKnowledgeStore.query: UnifiedStore resolution failed: {e}")
            components = []

        guids = [c["guid"] for c in components]

        # Collect gotchas from GHTieredKnowledge (has curated component error data)
        all_gotchas = []
        for guid in guids:
            all_gotchas.extend(self.tiered_knowledge.get_gotchas(guid))

        source = "unified_store" if components else "none"

        result = {
            "tier": depth,
            "source": source,
            "guids": guids,
            "components": components,
            "available_tiers": ["quick", "context", "errors", "raw"],
            "token_estimates": TIER_TOKEN_ESTIMATES.copy(),
            "gotchas": list(set(all_gotchas)),
        }

        if not guids:
            result["hint"] = (
                f"No components found for '{intent}'. "
                "Try specific names like 'sphere', 'slider', 'addition'."
            )
        elif depth == "quick" and components:
            result["hint"] = "For wiring info, try depth='context'. For troubleshooting, try depth='errors'."
        elif depth == "errors":
            result["hint"] = "If still failing, check gh_library to verify component exists."

        return result

    def resolve_components(self, intent: str) -> list[dict]:
        """Resolve intent to component candidates with full info.

        Delegates to UnifiedStore for GUID resolution.

        Args:
            intent: Natural language intent

        Returns:
            List of component dicts with guid, name, family, quick, params.
        """
        from .unified_store import get_unified_store
        return get_unified_store().resolve_components(intent)

    def get_component(self, guid: str, depth: TierLevel = "context") -> Optional[dict]:
        """Get knowledge for a specific component by GUID.

        Delegates to UnifiedStore for GUID-based lookup.

        Args:
            guid: Component GUID
            depth: Tier level (unused — returns creation-pipeline format)

        Returns:
            Component dict with guid, name, family, quick, params, or None
        """
        from .unified_store import get_unified_store
        return get_unified_store().get_component_by_guid(guid)

    def get_wiring_pattern(self, pattern_name: str) -> Optional[dict]:
        """Get a predefined wiring pattern.

        Note: Wiring patterns are now in PatternStore/UnifiedStore recipes.
        This method is retained for backward compatibility but returns None.
        """
        return None

    def query_operation(self, operation: str, context: Optional[dict] = None) -> dict:
        """Query operation-level knowledge (gotchas, common mistakes).

        This provides micro-tool level knowledge separate from component knowledge.
        Used by both dedicated wrappers (4 tools) and the universal injector (all GH tools).

        Args:
            operation: Operation type (wire, set_value, delete, disconnect, create, move,
                      group, query, explore, reference, document, inspect_output,
                      investigate, canvas_cleanup)
            context: Optional context dict for trigger matching. Supported keys:
                     target_type, involves_list, in_group, has_expression,
                     from_plugin, multiple_sources, data_mismatch

        Returns:
            {
                "operation": "wire",
                "gotchas": [{"id": "...", "message": "...", "severity": "warning"}, ...],
                "common_mistakes": [...],
                "hint": "..."
            }
        """
        self._ensure_operations_loaded()
        context = context or {}

        # Normalize operation name (handle aliases)
        op_key = operation.lower()
        ops = self._operations_knowledge.get("operations", {})

        # Find matching operation (check aliases)
        op_data = None
        for key, data in ops.items():
            if key == op_key or op_key in data.get("aliases", []):
                op_data = data
                op_key = key
                break

        if not op_data:
            known = ", ".join(ops.keys())
            return {
                "operation": operation,
                "gotchas": [],
                "common_mistakes": [],
                "hint": f"No operation knowledge for '{operation}'. Known operations: {known}"
            }

        # Filter gotchas based on triggers and context
        applicable_gotchas = [
            gotcha for gotcha in op_data.get("gotchas", [])
            if _evaluate_trigger(gotcha.get("trigger", "always"), context)
        ]

        return {
            "operation": op_key,
            "gotchas": applicable_gotchas,
            "common_mistakes": op_data.get("common_mistakes", []),
            "hint": f"For {op_key} operations: {op_data.get('description', '')}"
        }

    def record_operation_mistake(self, operation: str, pattern: str, correction: str) -> bool:
        """Record a common mistake pattern learned from correction detection.

        Args:
            operation: Operation type (wire, set_value, etc.)
            pattern: Description of the mistake pattern
            correction: How to correct it

        Returns:
            True if recorded successfully
        """
        self._ensure_operations_loaded()

        op_key = operation.lower()
        ops = self._operations_knowledge.get("operations", {})

        # Find operation
        for key, data in ops.items():
            if key == op_key or op_key in data.get("aliases", []):
                mistakes = data.setdefault("common_mistakes", [])
                # Check if pattern already exists
                for mistake in mistakes:
                    if mistake.get("pattern") == pattern:
                        mistake["observed_count"] = mistake.get("observed_count", 0) + 1
                        break
                else:
                    mistakes.append({
                        "pattern": pattern,
                        "correction": correction,
                        "observed_count": 1
                    })

                # Save back to disk
                try:
                    self._operations_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self._operations_path, "w") as f:
                        json.dump(self._operations_knowledge, f, indent=2)
                    return True
                except Exception as e:
                    logger.error(f"Failed to save operation mistake: {e}")
                    return False

        return False

    def record_gotcha_success(self, operation: str, gotcha_id: str | None = None) -> bool:
        """Record that a gotcha was injected and the tool succeeded.

        Updates times_used and last_verified on the matching gotcha entry
        in operations_knowledge.json. If gotcha_id is None, updates the
        first gotcha for the operation.

        Args:
            operation: Operation type (wire, set_value, etc.)
            gotcha_id: Optional specific gotcha ID to update

        Returns:
            True if updated successfully
        """
        self._ensure_operations_loaded()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        op_key = operation.lower()
        ops = self._operations_knowledge.get("operations", {})

        for key, data in ops.items():
            if key == op_key or op_key in data.get("aliases", []):
                gotchas = data.get("gotchas", [])
                updated = False
                for gotcha in gotchas:
                    if gotcha_id and gotcha.get("id") != gotcha_id:
                        continue
                    gotcha["times_used"] = gotcha.get("times_used", 0) + 1
                    gotcha["last_verified"] = now
                    updated = True
                    if gotcha_id:
                        break  # Found the specific one
                    else:
                        break  # Update first gotcha only

                if updated:
                    try:
                        self._operations_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self._operations_path, "w") as f:
                            json.dump(self._operations_knowledge, f, indent=2)
                        return True
                    except Exception as e:
                        logger.error(f"Failed to save gotcha staleness: {e}")
                        return False
                return False

        return False

    def reload(self) -> dict:
        """Force reload knowledge from disk.

        Component GUID resolution uses UnifiedStore (loads from notes/ on init).
        This reload refreshes GHTieredKnowledge (gotcha data), SparseIndex
        (intent→GUID mappings), and resets the operations knowledge cache.

        Returns:
            Dict with reload stats
        """
        from .unified_store import get_unified_store, reset_unified_store

        # Reload gotcha data
        component_count = self.tiered_knowledge.reload()

        # Reset operations knowledge so it reloads on next access
        self._operations_knowledge = None

        # Reset UnifiedStore singleton so it reloads notes from disk
        reset_unified_store()
        unified = get_unified_store()
        unified_components = len(unified._index.by_type.get("component", []))

        return {
            "intents_loaded": unified_components,
            "components_loaded": component_count,
            "operations_reset": True,
            "note": f"GUID resolution via UnifiedStore ({unified_components} component notes). Gotcha data: {component_count} entries.",
        }


# Global instance for module-level access
_gh_knowledge_store: Optional[GHKnowledgeStore] = None


def get_gh_knowledge_store() -> GHKnowledgeStore:
    """Get or create the global GH knowledge store."""
    global _gh_knowledge_store
    if _gh_knowledge_store is None:
        _gh_knowledge_store = GHKnowledgeStore()
    return _gh_knowledge_store


def gh_query_knowledge(intent: str, depth: TierLevel = "context") -> dict[str, Any]:
    """Query GH knowledge for an intent.

    Module-level convenience function.

    Args:
        intent: Natural language intent or keyword
        depth: Tier level (quick, context, errors, raw)

    Returns:
        Knowledge query result dict
    """
    return get_gh_knowledge_store().query(intent, depth)


def gh_reload_knowledge() -> dict[str, Any]:
    """Reload GH knowledge from disk.

    Call after editing the knowledge JSON files.

    Returns:
        Dict with reload stats
    """
    return get_gh_knowledge_store().reload()


def gh_query_operation(operation: str, context: Optional[dict] = None) -> dict[str, Any]:
    """Query operation-level knowledge for GH micro-tools.

    Module-level convenience function for querying gotchas and common mistakes
    for wire, set_value, delete, disconnect operations.

    Args:
        operation: Operation type (wire, connect, set_value, delete, disconnect)
        context: Optional context for trigger matching

    Returns:
        Operation knowledge dict with gotchas and common_mistakes
    """
    return get_gh_knowledge_store().query_operation(operation, context)


# =============================================================================
# Knowledge Builder - Converts exploration results to tiered knowledge
# =============================================================================

class GHKnowledgeBuilder:
    """Builds tiered knowledge entries from component exploration data.

    Converts raw component information into structured tiered knowledge
    that can be queried at different depth levels.
    """

    def __init__(self, tiered_path: Optional[Path] = None, sparse_path: Optional[Path] = None):
        self._uses_default_tiered_path = tiered_path is None
        self._uses_default_sparse_path = sparse_path is None
        self.tiered_path = Path(tiered_path) if tiered_path is not None else TIERED_KNOWLEDGE_WRITE_PATH
        self.sparse_path = Path(sparse_path) if sparse_path is not None else SPARSE_INDEX_WRITE_PATH

    def _tiered_read_path(self) -> Path:
        if not self._uses_default_tiered_path:
            return self.tiered_path
        return self.tiered_path if self.tiered_path.exists() else TIERED_KNOWLEDGE_READ_PATH

    def _sparse_read_path(self) -> Path:
        if not self._uses_default_sparse_path:
            return self.sparse_path
        return self.sparse_path if self.sparse_path.exists() else SPARSE_INDEX_READ_PATH

    def build_entry(
        self,
        guid: str,
        name: str,
        family: str,
        params: dict,
        *,
        quick: Optional[str] = None,
        contexts: Optional[dict[str, str]] = None,
        errors: Optional[str] = None,
    ) -> dict:
        """Build a tiered knowledge entry from exploration data.

        Args:
            guid: Component GUID
            name: Component name
            family: Component family (primitives, math, etc.)
            params: Dict with 'inputs' and 'outputs' from gh_snapshot
            quick: One-liner description (~20 tokens)
            contexts: Dict of context_name -> context-specific info
            errors: Common failure modes and gotchas

        Returns:
            Tiered knowledge entry ready for saving
        """
        # Auto-generate quick if not provided
        if not quick:
            input_names = list(params.get("inputs", {}).keys())
            output_names = list(params.get("outputs", {}).keys())
            inputs_str = ", ".join(input_names[:3]) if input_names else "no inputs"
            outputs_str = output_names[0] if output_names else "output"
            quick = f"{name} | Inputs: {inputs_str} → {outputs_str}"

        entry = {
            "name": name,
            "family": family,
            "quick": quick,
            "params": params,
        }

        if contexts:
            entry["contexts"] = contexts
        if errors:
            entry["errors"] = errors

        return entry

    def build_from_component_info(self, component_info: dict, component_guid: Optional[str] = None) -> dict:
        """Build tiered entry from gh_snapshot component response.

        Args:
            component_info: Response from gh_snapshot tool
            component_guid: Original component GUID (since response only has instance GUID)

        Returns:
            Tiered knowledge entry
        """
        # Extract params - handle nested structure from gh_snapshot
        inputs = {}
        outputs = {}

        params_data = component_info.get("params", {})
        input_list = params_data.get("inputs", []) if isinstance(params_data, dict) else []
        output_list = params_data.get("outputs", []) if isinstance(params_data, dict) else []

        for param in input_list:
            name = param.get("name", param.get("nickName", "?"))
            nick = param.get("nickName", name)
            type_name = param.get("typeName", "")
            inputs[nick] = type_name or name

        for param in output_list:
            name = param.get("name", param.get("nickName", "?"))
            nick = param.get("nickName", name)
            type_name = param.get("typeName", "")
            outputs[nick] = type_name or name

        params = {"inputs": inputs, "outputs": outputs}

        # Use SDK category if available (from batch-component-info enrichment),
        # otherwise fall back to heuristic family detection from type name
        sdk_category = component_info.get("sdk_category", "")
        if sdk_category:
            family = sdk_category.lower().replace(" ", "_")
        else:
            comp_type = component_info.get("type", "").lower()

            if "sphere" in comp_type or "cylinder" in comp_type or "cone" in comp_type or "box" in comp_type:
                family = "primitives"
            elif "slider" in comp_type or "panel" in comp_type or "toggle" in comp_type:
                family = "input"
            elif "addition" in comp_type or "subtraction" in comp_type or "multiplication" in comp_type or "division" in comp_type:
                family = "math"
            elif "curve" in comp_type or "line" in comp_type or "circle" in comp_type:
                family = "curves"
            elif "loft" in comp_type or "sweep" in comp_type or "extrude" in comp_type:
                family = "surface_ops"
            elif "graft" in comp_type or "flatten" in comp_type or "tree" in comp_type:
                family = "tree_operations"
            elif "series" in comp_type or "range" in comp_type:
                family = "sequence"
            else:
                family = "unknown"

        # Capture SDK description if available
        description = component_info.get("description", "")

        entry = self.build_entry(
            guid=component_guid or "",
            name=component_info.get("name", "Unknown"),
            family=family,
            params=params,
        )

        if description:
            entry["description"] = description

        return entry

    def save_entry(self, guid: str, entry: dict) -> bool:
        """Save a tiered knowledge entry to disk.

        Args:
            guid: Component GUID (key in components dict)
            entry: Tiered knowledge entry

        Returns:
            True if saved successfully
        """
        try:
            # Load current tiered knowledge
            read_path = self._tiered_read_path()
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"components": {}}

            # Add or update entry
            if "components" not in data:
                data["components"] = {}
            data["components"][guid] = entry

            # Save back
            self.tiered_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tiered_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved tiered knowledge for {entry.get('name')} ({guid})")
            return True

        except Exception as e:
            logger.error(f"Failed to save tiered knowledge: {e}")
            return False

    def rekey_tiered_entry(self, old_guid: str, new_guid: str) -> bool:
        """Move a tiered knowledge entry from old GUID key to new GUID key.

        Always removes old_guid entry. If new_guid already has an entry,
        the old_guid entry is discarded (not clobbered over new_guid).
        No-op if old_guid is absent.
        """
        try:
            read_path = self._tiered_read_path()
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"components": {}}

            components = data.get("components", {})
            if old_guid not in components:
                return True  # no-op

            entry = components.pop(old_guid)
            if new_guid in components:
                logger.info(
                    f"Tiered re-key: removed old {old_guid[:12]}..., "
                    f"kept existing {new_guid[:12]}..."
                )
            else:
                components[new_guid] = entry
                logger.info(f"Re-keyed tiered entry: {old_guid[:12]}... -> {new_guid[:12]}...")

            self.tiered_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tiered_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to re-key tiered entry: {e}")
            return False

    def rekey_sparse_entry(self, old_guid: str, new_guid: str) -> bool:
        """Atomically move sparse index ownership from old GUID to new GUID.

        Moves guid_to_info metadata, replaces old GUID with new GUID in all
        intent_to_guids lists and family_to_guids lists. Deduplicates new_guid
        if it already exists. No-op if old_guid is absent.
        """
        try:
            read_path = self._sparse_read_path()
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}

            guid_to_info = data.get("guid_to_info", {})
            if old_guid not in guid_to_info:
                return True  # no-op

            # Move guid_to_info entry
            info = guid_to_info.pop(old_guid)
            guid_to_info[new_guid] = info

            # Replace in intent_to_guids lists, prune empty buckets
            intent_map = data.get("intent_to_guids", {})
            empty_intents = []
            for intent_key, guid_list in intent_map.items():
                if old_guid in guid_list:
                    guid_list.remove(old_guid)
                    if new_guid not in guid_list:
                        guid_list.append(new_guid)
                    if not guid_list:
                        empty_intents.append(intent_key)
            for k in empty_intents:
                del intent_map[k]

            # Replace in family_to_guids lists, prune empty buckets
            family_map = data.get("family_to_guids", {})
            empty_families = []
            for family, guid_list in family_map.items():
                if old_guid in guid_list:
                    guid_list.remove(old_guid)
                    if new_guid not in guid_list:
                        guid_list.append(new_guid)
                    if not guid_list:
                        empty_families.append(family)
            for k in empty_families:
                del family_map[k]

            self.sparse_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.sparse_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Re-keyed sparse entry: {old_guid[:12]}... -> {new_guid[:12]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to re-key sparse entry: {e}")
            return False

    @staticmethod
    def _generate_sparse_intents(name: str, nickName: str) -> list[str]:
        """Generate natural-language intent keys for sparse_index.

        Produces multiple search-friendly intents from a component name:
        - Verbatim lowercase: "wasp_connection from direction"
        - Underscore→space: "wasp connection from direction"
        - Individual words (>2 chars): "wasp", "connection", "from", "direction"
        - Bigrams: "wasp connection", "connection from", "from direction"
        - NickName if different: "conndir"
        """
        intents = [name.lower()]

        # Underscore → space
        spacified = name.lower().replace("_", " ")
        if spacified != intents[0]:
            intents.append(spacified)

        # Words (>2 chars)
        words = [w for w in spacified.split() if len(w) > 2]
        for w in words:
            if w not in intents:
                intents.append(w)

        # Bigrams
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if bigram not in intents:
                intents.append(bigram)

        # NickName if different
        if nickName and nickName.lower() not in intents:
            intents.append(nickName.lower())

        return intents

    def ensure_sparse_entry(self, guid: str, name: str, family: str, nickName: str) -> bool:
        """Ensure component is in sparse index with rich intent mappings.

        Always enriches intent mappings even if GUID already exists, so
        re-exploring a component repairs its sparse lookup coverage.

        Args:
            guid: Component GUID
            name: Component name
            family: Component family
            nickName: Short nickname

        Returns:
            True if entry was written successfully
        """
        try:
            read_path = self._sparse_read_path()
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}

            dirty = False

            # Add or refresh guid_to_info metadata
            if "guid_to_info" not in data:
                data["guid_to_info"] = {}
            old_info = data["guid_to_info"].get(guid)
            new_info = {"name": name, "family": family, "nickName": nickName}
            if old_info != new_info:
                # Remove GUID from old family bucket if family changed
                if old_info and old_info.get("family") != family:
                    old_family = old_info["family"]
                    old_bucket = data.get("family_to_guids", {}).get(old_family, [])
                    if guid in old_bucket:
                        old_bucket.remove(guid)
                        dirty = True
                data["guid_to_info"][guid] = new_info
                dirty = True

            # Add to family_to_guids
            if "family_to_guids" not in data:
                data["family_to_guids"] = {}
            if family not in data["family_to_guids"]:
                data["family_to_guids"][family] = []
            if guid not in data["family_to_guids"][family]:
                data["family_to_guids"][family].append(guid)
                dirty = True

            # Always enrich intent mappings (even for existing GUIDs)
            if "intent_to_guids" not in data:
                data["intent_to_guids"] = {}
            intent_keys = self._generate_sparse_intents(name, nickName)
            new_intents = 0
            for intent_key in intent_keys:
                if intent_key not in data["intent_to_guids"]:
                    data["intent_to_guids"][intent_key] = [guid]
                    dirty = True
                    new_intents += 1
                elif guid not in data["intent_to_guids"][intent_key]:
                    data["intent_to_guids"][intent_key].append(guid)
                    dirty = True
                    new_intents += 1

            # Only write if something changed
            if dirty:
                self.sparse_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.sparse_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Updated sparse entry for {name} ({guid}): {new_intents} new intents added")
            else:
                logger.debug(f"Sparse entry for {name} ({guid}) already complete")

            return True

        except Exception as e:
            logger.error(f"Failed to update sparse index: {e}")
            return False


def generate_intents_from_name(name: str) -> list[str]:
    """Generate trigger intents from a component/recipe name.

    Splits camelCase, spaces, and underscores into individual words,
    returning the full lowercase name plus any word longer than 2 chars.
    """
    intents = [name.lower()]
    # Split camelCase and spaces
    words = []
    current = ""
    for char in name:
        if char.isupper() and current:
            words.append(current.lower())
            current = char
        elif char == " " or char == "_":
            if current:
                words.append(current.lower())
            current = ""
        else:
            current += char
    if current:
        words.append(current.lower())

    # Add individual words as intents
    for word in words:
        if len(word) > 2 and word not in intents:
            intents.append(word)

    return intents


# Global knowledge builder instance
_knowledge_builder: Optional[GHKnowledgeBuilder] = None


def _create_unified_note(
    store, entry: dict, creation_guid: str,
    nickName: str, stable_key: Optional[str],
) -> dict[str, Any]:
    """Create a new UnifiedStore component note. Returns result fields to merge."""
    from .knowledge_note import KnowledgeNote

    comp_name = entry.get("name", "Unknown")
    params = entry.get("params", {})
    description = entry.get("description", "")
    family = entry.get("family", "")

    input_names = list(params.get("inputs", {}).keys())
    output_names = list(params.get("outputs", {}).keys())
    inputs_str = ", ".join(input_names) if input_names else "none"
    outputs_str = ", ".join(output_names) if output_names else "output"
    brief = f"{comp_name} | Inputs: {inputs_str} \u2192 {outputs_str}"

    intents = generate_intents_from_name(comp_name)
    if nickName and nickName.lower() not in intents:
        intents.append(nickName.lower())

    type_data: dict[str, Any] = {
        "guid": creation_guid,
        "category": family,
        "inputs": params.get("inputs", {}),
        "outputs": params.get("outputs", {}),
        "similar_to": [],
        "usage_count": 0,
    }
    if stable_key:
        type_data["stable_key"] = stable_key

    note = KnowledgeNote(
        note_id=KnowledgeNote.generate_id("component"),
        note_type="component",
        name=comp_name,
        brief=brief,
        created=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        context=f"Grasshopper component: {comp_name}. {description}",
        category=family,
        keywords=[comp_name.lower(), family] + [
            w for w in comp_name.lower().replace("_", " ").split() if len(w) > 2
        ],
        trigger_intents=intents,
        components=[comp_name],
        solution_principle=description or brief,
        type_data=type_data,
        created_from="exploration",
    )
    store.add(note, skip_evolution=True)
    logger.info(f"Created UnifiedStore note {note.note_id} for {comp_name} ({creation_guid})")
    return {
        "saved_unified": True,
        "unified_note_id": note.note_id,
    }


def get_knowledge_builder() -> GHKnowledgeBuilder:
    """Get or create the global knowledge builder."""
    global _knowledge_builder
    if _knowledge_builder is None:
        _knowledge_builder = GHKnowledgeBuilder()
    return _knowledge_builder


def gh_build_knowledge(component_info: dict, *, component_guid: Optional[str] = None,
                       proxy_guid: Optional[str] = None, save: bool = True) -> dict[str, Any]:
    """Build and optionally save tiered knowledge from component info.

    Writes to ALL THREE stores:
    1. tiered_knowledge.json (via save_entry)
    2. sparse_index.json (via ensure_sparse_entry with rich intents)
    3. UnifiedStore notes/ (via KnowledgeNote + store.add)

    Args:
        component_info: Response from gh_snapshot tool
        component_guid: Component GUID (ComponentGuid from snapshot)
        proxy_guid: Proxy GUID for GhPython components (from gh_library validation
                    in canvas_learner). When present, this is the canonical creation GUID.
        save: Whether to save to disk immediately

    Returns:
        Dict with entry and save status
    """
    # Canonical rule: proxy GUID is the creation identity for GhPython components
    creation_guid = proxy_guid or component_guid or ""

    builder = get_knowledge_builder()
    entry = builder.build_from_component_info(component_info, creation_guid)

    result = {
        "guid": creation_guid,
        "entry": entry,
        "saved": False,
        "saved_tiered": False,
        "saved_sparse": False,
        "saved_unified": False,
        "unified_note_id": None,
    }

    if save and creation_guid:
        nickName = component_info.get("nickName", entry.get("name", "")[:6])
        comp_name = entry.get("name", "Unknown")
        family = entry.get("family", "")

        # Compute stable_key from live component data
        # Prefer snapshot category/subCategory; fall back to SDK proxy values
        category_raw = component_info.get("category", "") or component_info.get("sdk_category", family)
        sub_category_raw = component_info.get("subCategory", "") or component_info.get("sdk_subcategory", "")
        stable_key = compute_stable_key(category_raw, sub_category_raw, comp_name)

        try:
            from .unified_store import get_unified_store
            from .knowledge_note import KnowledgeNote

            store = get_unified_store()

            # === 5-step resolution order ===

            # Step 1: GUID match
            existing_dict = store.get_component_by_guid(creation_guid)
            if existing_dict:
                result["saved_tiered"] = builder.save_entry(creation_guid, entry)
                result["saved_sparse"] = builder.ensure_sparse_entry(
                    guid=creation_guid, name=comp_name, family=family, nickName=nickName,
                )
                # Backfill stable_key if computable and missing
                if stable_key:
                    for note in store._notes.values():
                        if note.note_type == "component":
                            td = note.type_data or {}
                            if td.get("guid") == creation_guid and not td.get("stable_key"):
                                td["stable_key"] = stable_key
                                store.update(note)
                                logger.info(f"Backfilled stable_key on {comp_name}: {stable_key}")
                                break
                result["saved_unified"] = True
                logger.info(f"GUID match for {comp_name} ({creation_guid}), updated in place")

            # Step 2: Missing subCategory — no stable_key dedup possible
            elif not stable_key:
                result["saved_tiered"] = builder.save_entry(creation_guid, entry)
                result["saved_sparse"] = builder.ensure_sparse_entry(
                    guid=creation_guid, name=comp_name, family=family, nickName=nickName,
                )
                result.update(_create_unified_note(
                    store, entry, creation_guid, nickName, stable_key=None,
                ))
                logger.info(f"No subCategory for {comp_name}, created new entry (no stable_key)")

            else:
                # Steps 3-5: stable_key resolution
                matches = store.get_component_by_stable_key(stable_key)

                # Fallback: if no stable_key match, check for pre-migration notes
                # that match by name but lack stable_key (one-time lazy migration).
                if len(matches) == 0:
                    legacy = store.get_component_by_name_without_stable_key(comp_name)
                    if len(legacy) == 1:
                        matches = legacy
                        logger.info(
                            f"stable_key migration: matched {comp_name} by name "
                            f"(note {legacy[0].note_id} has no stable_key)"
                        )

                if len(matches) == 1:
                    # Step 3: Unique match — merge into existing note
                    #
                    # Order: re-key tiered/sparse FIRST, then mutate unified.
                    # If re-key fails, unified stays unchanged (old GUID) and
                    # the caller sees saved=False. This prevents the stores
                    # from diverging on partial failure.
                    merge_note = matches[0]
                    old_guid = (merge_note.type_data or {}).get("guid", "")

                    # Re-key tiered and sparse (old GUID -> new GUID)
                    tiered_rekeyed = builder.rekey_tiered_entry(old_guid, creation_guid)
                    sparse_rekeyed = builder.rekey_sparse_entry(old_guid, creation_guid)

                    if not tiered_rekeyed or not sparse_rekeyed:
                        failed = []
                        if not tiered_rekeyed:
                            failed.append("tiered")
                        if not sparse_rekeyed:
                            failed.append("sparse")
                        logger.error(
                            f"stable_key merge aborted — re-key failed: {failed}. "
                            f"Unified note NOT updated to preserve consistency."
                        )
                        result["saved_tiered"] = False
                        result["saved_sparse"] = False
                        result["saved_unified"] = False
                    else:
                        # Re-keys succeeded — now safe to update unified note
                        merge_note.type_data["guid"] = creation_guid
                        merge_note.type_data["stable_key"] = stable_key
                        store.update(merge_note)

                        # Save fresh tiered/sparse content under new GUID
                        result["saved_tiered"] = builder.save_entry(creation_guid, entry)
                        result["saved_sparse"] = builder.ensure_sparse_entry(
                            guid=creation_guid, name=comp_name, family=family, nickName=nickName,
                        )
                        result["saved_unified"] = True
                        result["unified_note_id"] = merge_note.note_id
                        result["merged"] = True
                        logger.info(
                            f"stable_key merge: {stable_key} -- "
                            f"GUID {old_guid[:12]}... -> {creation_guid[:12]}..."
                        )

                elif len(matches) > 1:
                    # Step 4: Ambiguous — log warning, create new entry
                    logger.warning(
                        f"stable_key ambiguous: {stable_key} matches "
                        f"{len(matches)} notes -- skipping auto-merge"
                    )
                    result["saved_tiered"] = builder.save_entry(creation_guid, entry)
                    result["saved_sparse"] = builder.ensure_sparse_entry(
                        guid=creation_guid, name=comp_name, family=family, nickName=nickName,
                    )
                    result.update(_create_unified_note(
                        store, entry, creation_guid, nickName, stable_key=stable_key,
                    ))

                else:
                    # Step 5: No match — create new entry with stable_key
                    result["saved_tiered"] = builder.save_entry(creation_guid, entry)
                    result["saved_sparse"] = builder.ensure_sparse_entry(
                        guid=creation_guid, name=comp_name, family=family, nickName=nickName,
                    )
                    result.update(_create_unified_note(
                        store, entry, creation_guid, nickName, stable_key=stable_key,
                    ))

        except Exception as e:
            result["saved_unified"] = False
            logger.error(f"Failed in stable-key resolution for {creation_guid}: {e}")

        # "saved" is True only if ALL three stores were written
        result["saved"] = all([
            result["saved_tiered"],
            result["saved_sparse"],
            result["saved_unified"],
        ])
        if not result["saved"]:
            failed = [s for s in ("tiered", "sparse", "unified") if not result[f"saved_{s}"]]
            logger.warning(f"Partial write for {creation_guid}: failed stores = {failed}")

    return result


# =============================================================================
# Observation Recording System
# =============================================================================

class GHObservationRecorder:
    """Records observations during exploration for knowledge capture.

    Auto-appends to component_observations.json with timestamps and session tracking.
    Designed to capture learnings without interrupting workflow.
    """

    def __init__(self, path: Optional[Path] = None):
        self._uses_default_path = path is None
        self.path = Path(path) if path is not None else OBSERVATIONS_WRITE_PATH
        self._session_id: Optional[str] = None
        self._observation_count = 0

    def _read_path(self) -> Path:
        if not self._uses_default_path:
            return self.path
        return self.path if self.path.exists() else OBSERVATIONS_READ_PATH

    def start_session(self, session_name: str) -> str:
        """Start a new exploration session.

        Args:
            session_name: Descriptive name like "data_tree_exploration"

        Returns:
            Session ID for tracking
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_id = f"{session_name}_{timestamp}"
        self._observation_count = 0

        logger.info(f"Started exploration session: {self._session_id}")
        return self._session_id

    def record(
        self,
        component: str,
        observation: str,
        *,
        impact: str = "info",
        resolution: Optional[str] = None,
        tags: Optional[list[str]] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """Record an observation during exploration.

        Args:
            component: Component name/GUID or general topic
            observation: What was observed
            impact: Severity - "info", "low", "medium", "high"
            resolution: How to handle this (if known)
            tags: Categorization tags
            context: Additional context data (inputs used, outputs seen, etc.)

        Returns:
            The recorded observation dict
        """
        from datetime import datetime

        obs = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "session": self._session_id or "adhoc",
            "component": component,
            "observation": observation,
            "impact": impact,
            "resolution": resolution,
            "tags": tags or [],
        }

        if context:
            obs["context"] = context

        # Append to file
        self._append_observation(obs)
        self._observation_count += 1

        logger.info(f"Recorded observation #{self._observation_count}: {component} - {observation[:50]}...")

        return obs

    def record_success(
        self,
        component: str,
        action: str,
        *,
        inputs: Optional[dict] = None,
        outputs: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Record a successful operation - lightweight, for pattern building.

        Args:
            component: Component name/GUID
            action: What was done (e.g., "wired slider to radius")
            inputs: Input values/connections used
            outputs: Output structure observed
            tags: Categorization tags
        """
        return self.record(
            component=component,
            observation=f"SUCCESS: {action}",
            impact="info",
            tags=["success"] + (tags or []),
            context={"inputs": inputs, "outputs": outputs} if (inputs or outputs) else None,
        )

    def record_failure(
        self,
        component: str,
        action: str,
        error: str,
        *,
        inputs: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Record a failed operation - important for gotcha discovery.

        Args:
            component: Component name/GUID
            action: What was attempted
            error: Error message or observed failure
            inputs: Input values that caused the failure
            tags: Categorization tags
        """
        return self.record(
            component=component,
            observation=f"FAILURE: {action} - {error}",
            impact="medium",
            tags=["failure"] + (tags or []),
            context={"inputs": inputs, "error": error} if inputs else None,
        )

    def record_discovery(
        self,
        component: str,
        discovery: str,
        *,
        impact: str = "medium",
        resolution: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Record a new discovery/insight about a component.

        Args:
            component: Component name/GUID
            discovery: What was discovered
            impact: How important is this
            resolution: Recommended action based on discovery
            tags: Categorization tags
        """
        return self.record(
            component=component,
            observation=f"DISCOVERY: {discovery}",
            impact=impact,
            resolution=resolution,
            tags=["discovery"] + (tags or []),
        )

    def record_data_structure(
        self,
        component: str,
        param_name: str,
        structure: dict,
        *,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Record data structure observation (trees, lists, branches).

        Args:
            component: Component name/GUID
            param_name: Which param was observed (input or output name)
            structure: Structure info (tree paths, list lengths, data types)
            tags: Additional tags
        """
        return self.record(
            component=component,
            observation=f"DATA_STRUCTURE on {param_name}: {structure.get('type', 'unknown')}",
            impact="info",
            tags=["data_structure"] + (tags or []),
            context={"param": param_name, "structure": structure},
        )

    def _append_observation(self, obs: dict) -> None:
        """Append observation to the JSON file."""
        try:
            # Load existing
            read_path = self._read_path()
            if read_path.exists():
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {
                    "version": "1.0",
                    "description": "Raw observations about GH component behavior - will be consolidated into catalog",
                    "observations": []
                }

            # Append
            data["observations"].append(obs)

            # Write back
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to append observation: {e}")

    def end_session(self) -> dict:
        """End the current session and return summary.

        Returns:
            Summary with session ID and observation count
        """
        summary = {
            "session_id": self._session_id,
            "observations_recorded": self._observation_count,
        }

        logger.info(f"Ended session {self._session_id} with {self._observation_count} observations")

        self._session_id = None
        self._observation_count = 0

        return summary


class GHObservationQuery:
    """Query past observations for pattern discovery.

    Enables filtering observations by:
    - Operation type (wire, set_value, delete, disconnect)
    - Component (name or GUID)
    - Outcome (success, failure)
    - Time window
    - Tags
    """

    def __init__(self, path: Optional[Path] = None):
        self._uses_default_path = path is None
        self.path = Path(path) if path is not None else OBSERVATIONS_WRITE_PATH
        self._cache: Optional[list[dict]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)

    def _read_path(self) -> Path:
        if not self._uses_default_path:
            return self.path
        return self.path if self.path.exists() else OBSERVATIONS_READ_PATH

    def _load_observations(self) -> list[dict]:
        """Load observations from disk with caching."""
        now = datetime.now()

        # Check cache
        if self._cache is not None and self._cache_time is not None:
            if now - self._cache_time < self._cache_ttl:
                return self._cache

        # Load from disk
        read_path = self._read_path()
        if not read_path.exists():
            self._cache = []
            self._cache_time = now
            return []

        try:
            with open(read_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data.get("observations", [])
            self._cache_time = now
            return self._cache
        except Exception as e:
            logger.error(f"Failed to load observations: {e}")
            return []

    def by_operation(self, operation: str, limit: int = 20) -> list[dict]:
        """Get observations for a specific operation type.

        Args:
            operation: Operation type (wire, connect, set_value, delete, disconnect)
            limit: Maximum results to return

        Returns:
            List of matching observations, most recent first
        """
        obs = self._load_observations()
        op_lower = operation.lower()

        # Match by tags or observation text
        matches = []
        for o in obs:
            tags = [t.lower() for t in o.get("tags", [])]
            text = o.get("observation", "").lower()

            if op_lower in tags or f"_{op_lower}" in text:
                matches.append(o)
            elif op_lower == "wire" and ("connect" in tags or "wire" in text):
                matches.append(o)
            elif op_lower == "connect" and ("wire" in tags or "wire" in text):
                matches.append(o)

        # Sort by timestamp, most recent first
        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def by_component(self, component: str, limit: int = 20) -> list[dict]:
        """Get observations for a specific component.

        Args:
            component: Component name or GUID (partial match)
            limit: Maximum results

        Returns:
            List of matching observations
        """
        obs = self._load_observations()
        comp_lower = component.lower()

        matches = [
            o for o in obs
            if comp_lower in o.get("component", "").lower()
        ]

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def successes(self, limit: int = 20) -> list[dict]:
        """Get successful observations.

        Returns:
            List of success observations
        """
        obs = self._load_observations()

        matches = [
            o for o in obs
            if "success" in [t.lower() for t in o.get("tags", [])]
            or o.get("observation", "").startswith("SUCCESS:")
        ]

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def failures(self, limit: int = 20) -> list[dict]:
        """Get failure observations.

        Returns:
            List of failure observations
        """
        obs = self._load_observations()

        matches = [
            o for o in obs
            if "failure" in [t.lower() for t in o.get("tags", [])]
            or o.get("observation", "").startswith("FAILURE:")
        ]

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def corrections(self, limit: int = 20) -> list[dict]:
        """Get observations that were corrections of previous failures.

        Returns:
            List of correction observations
        """
        obs = self._load_observations()

        matches = [
            o for o in obs
            if "correction" in [t.lower() for t in o.get("tags", [])]
            or o.get("context", {}).get("correction_of")
        ]

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def recent(self, hours: int = 24, limit: int = 50) -> list[dict]:
        """Get recent observations within a time window.

        Args:
            hours: How many hours back to look
            limit: Maximum results

        Returns:
            List of recent observations
        """
        obs = self._load_observations()
        cutoff = datetime.now() - timedelta(hours=hours)

        matches = []
        for o in obs:
            try:
                ts = datetime.fromisoformat(o.get("timestamp", ""))
                if ts >= cutoff:
                    matches.append(o)
            except (ValueError, TypeError):
                pass

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across observations.

        Args:
            query: Search query (fuzzy match on observation text, component, tags)
            limit: Maximum results

        Returns:
            Matching observations
        """
        obs = self._load_observations()
        q_lower = query.lower()

        matches = []
        for o in obs:
            text = o.get("observation", "").lower()
            comp = o.get("component", "").lower()
            tags = " ".join(o.get("tags", [])).lower()
            context_str = json.dumps(o.get("context", {})).lower()

            if q_lower in text or q_lower in comp or q_lower in tags or q_lower in context_str:
                matches.append(o)

        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return matches[:limit]

    def summary(self) -> dict:
        """Get summary statistics of observations.

        Returns:
            Dict with counts by type, component, etc.
        """
        obs = self._load_observations()

        summary = {
            "total": len(obs),
            "successes": 0,
            "failures": 0,
            "corrections": 0,
            "by_operation": {},
            "recent_24h": 0,
        }

        cutoff = datetime.now() - timedelta(hours=24)

        for o in obs:
            tags = [t.lower() for t in o.get("tags", [])]

            if "success" in tags:
                summary["successes"] += 1
            if "failure" in tags:
                summary["failures"] += 1
            if "correction" in tags:
                summary["corrections"] += 1

            # Count by operation type
            for op in ["wire", "connect", "set_value", "delete", "disconnect"]:
                if op in tags:
                    summary["by_operation"][op] = summary["by_operation"].get(op, 0) + 1

            # Count recent
            try:
                ts = datetime.fromisoformat(o.get("timestamp", ""))
                if ts >= cutoff:
                    summary["recent_24h"] += 1
            except (ValueError, TypeError):
                pass

        return summary


# Global query instance
_observation_query: Optional[GHObservationQuery] = None


def get_observation_query() -> GHObservationQuery:
    """Get or create the global observation query instance."""
    global _observation_query
    if _observation_query is None:
        _observation_query = GHObservationQuery()
    return _observation_query


def gh_query_observations(
    operation: Optional[str] = None,
    component: Optional[str] = None,
    outcome: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20
) -> dict:
    """Query past GH observations.

    Module-level convenience function for observation queries.

    Args:
        operation: Filter by operation type (wire, set_value, delete, disconnect)
        component: Filter by component name/GUID
        outcome: Filter by outcome (success, failure, correction)
        search: Full-text search query
        limit: Maximum results

    Returns:
        Dict with matching observations and summary
    """
    query = get_observation_query()

    # Apply filters in order of specificity
    if search:
        results = query.search(search, limit)
    elif component:
        results = query.by_component(component, limit)
    elif operation:
        results = query.by_operation(operation, limit)
    elif outcome == "success":
        results = query.successes(limit)
    elif outcome == "failure":
        results = query.failures(limit)
    elif outcome == "correction":
        results = query.corrections(limit)
    else:
        results = query.recent(hours=24, limit=limit)

    return {
        "observations": results,
        "count": len(results),
        "summary": query.summary() if not search else None,
    }


# Global recorder instance
_observation_recorder: Optional[GHObservationRecorder] = None


def get_observation_recorder() -> GHObservationRecorder:
    """Get or create the global observation recorder."""
    global _observation_recorder
    if _observation_recorder is None:
        _observation_recorder = GHObservationRecorder()
    return _observation_recorder


def start_exploration_session(session_name: str) -> str:
    """Start a new exploration session for knowledge capture.

    Args:
        session_name: Descriptive session name

    Returns:
        Session ID
    """
    return get_observation_recorder().start_session(session_name)


def record_observation(
    component: str,
    observation: str,
    **kwargs
) -> dict:
    """Record an observation during exploration.

    See GHObservationRecorder.record() for full args.
    """
    return get_observation_recorder().record(component, observation, **kwargs)
