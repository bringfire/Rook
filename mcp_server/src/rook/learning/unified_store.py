# mcp_server/src/rook/learning/unified_store.py
"""
UnifiedStore - Storage and retrieval for unified knowledge notes.

Provides CRUD operations, search, and DAG traversal for KnowledgeNote objects.
Supports A-MEM evolution when enabled.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..runtime_paths import (
    get_bundled_knowledge_root,
    resolve_readable_knowledge_path,
    resolve_writable_knowledge_path,
)
from .knowledge_note import KnowledgeNote, TierLevel
from .unified_index import UnifiedIndex

logger = logging.getLogger("rook.unified_store")

# Default paths
DEFAULT_NOTES_DIR = resolve_writable_knowledge_path("gh", "notes")
DEFAULT_INDEX_PATH = resolve_writable_knowledge_path("gh", "unified_index.json")
DEFAULT_SPARSE_INDEX_PATH = resolve_readable_knowledge_path("gh", "sparse_index.json")


def _default_bundled_notes_dir() -> Path:
    return get_bundled_knowledge_root() / "gh" / "notes"


class UnifiedStore:
    """Manages unified knowledge notes with optional A-MEM evolution."""

    def __init__(
        self,
        notes_dir: Path = DEFAULT_NOTES_DIR,
        index_path: Path = DEFAULT_INDEX_PATH,
        sparse_index_path: Path = DEFAULT_SPARSE_INDEX_PATH,
        auto_save: bool = True,
        enable_evolution: bool = True,
    ):
        self.notes_dir = notes_dir
        self.index_path = index_path
        self.sparse_index_path = sparse_index_path
        self._uses_default_notes_dir = notes_dir == DEFAULT_NOTES_DIR
        self.auto_save = auto_save
        self.enable_evolution = enable_evolution

        self._notes: dict[str, KnowledgeNote] = {}
        self._index: UnifiedIndex = UnifiedIndex()
        self._evolution = None  # Lazy loaded
        self._active_component_name_map: dict[str, dict[str, Any]] | None = None
        self._deprecated_component_guid_map: dict[str, dict[str, Any]] | None = None
        self._deprecated_component_name_map: dict[str, list[dict[str, Any]]] | None = None
        self._legacy_guid_info: dict[str, dict[str, Any]] | None = None

        self._load()

    def _load(self) -> None:
        """Load notes and index from disk."""
        # Ensure notes directory exists
        self.notes_dir.mkdir(parents=True, exist_ok=True)

        loaded_index = None
        if self.index_path.exists():
            loaded_index = UnifiedIndex.load(self.index_path)

        # Load bundled notes first, then mutable notes override by note_id.
        note_dirs: list[Path] = []
        if self._uses_default_notes_dir:
            bundled_notes_dir = _default_bundled_notes_dir()
            if bundled_notes_dir.exists() and bundled_notes_dir != self.notes_dir:
                note_dirs.append(bundled_notes_dir)
        note_dirs.append(self.notes_dir)

        for note_dir in note_dirs:
            for note_file in note_dir.glob("*.json"):
                try:
                    data = json.loads(note_file.read_text(encoding="utf-8"))
                    note = KnowledgeNote.from_dict(data)
                    self._notes[note.note_id] = note
                except Exception as e:
                    logger.warning(f"Failed to load note {note_file}: {e}")

        rebuilt_index = self._build_index_from_notes()
        self._index = rebuilt_index
        if loaded_index is None:
            if self.auto_save:
                self._save_index()
        elif self.auto_save and loaded_index.to_dict() != rebuilt_index.to_dict():
            self._save_index()

        self._invalidate_component_lookup_cache()
        logger.info(f"Loaded {len(self._notes)} notes from {self.notes_dir}")

    def _should_index(self, note: KnowledgeNote) -> bool:
        """Central rule for whether a note should participate in search."""
        return not note.deprecated

    def _build_index_from_notes(self) -> UnifiedIndex:
        """Rebuild the index from current in-memory notes."""
        fresh = UnifiedIndex()
        for note in self._notes.values():
            if self._should_index(note):
                fresh.add_note(note)
        return fresh

    def _invalidate_component_lookup_cache(self) -> None:
        """Invalidate cached name/GUID lookup maps derived from notes."""
        self._active_component_name_map = None
        self._deprecated_component_guid_map = None
        self._deprecated_component_name_map = None

    def _component_lookup_keys(self, note: KnowledgeNote) -> set[str]:
        """Return exact-match names and aliases that may identify this component."""
        keys: set[str] = set()
        if note.name:
            keys.add(note.name.lower())

        td = note.type_data or {}
        guid = td.get("guid", "")
        for field_name in ("nickName", "nickname", "nick_name"):
            value = td.get(field_name)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized:
                    keys.add(normalized)

        for field_name in ("aliases", "nickNames", "nicknames"):
            values = td.get(field_name)
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        normalized = value.strip().lower()
                        if normalized:
                            keys.add(normalized)

        if isinstance(guid, str) and guid:
            self._ensure_legacy_guid_info()
            if self._legacy_guid_info is not None:
                legacy = self._legacy_guid_info.get(guid, {})
                for field_name in ("name", "nickName"):
                    value = legacy.get(field_name)
                    if isinstance(value, str):
                        normalized = value.strip().lower()
                        if normalized:
                            keys.add(normalized)

        return keys

    def _ensure_legacy_guid_info(self) -> None:
        """Load legacy sparse index metadata used for alias fallback."""
        if self._legacy_guid_info is not None:
            return

        try:
            if self.sparse_index_path.exists():
                data = json.loads(self.sparse_index_path.read_text(encoding="utf-8"))
                self._legacy_guid_info = data.get("guid_to_info", {})
            else:
                self._legacy_guid_info = {}
        except Exception as e:
            logger.warning(f"Failed to load sparse index aliases from {self.sparse_index_path}: {e}")
            self._legacy_guid_info = {}

    def _ensure_component_lookup_cache(self) -> None:
        """Build cached component lookup maps on demand."""
        if (
            self._active_component_name_map is not None
            and self._deprecated_component_guid_map is not None
            and self._deprecated_component_name_map is not None
        ):
            return

        active_name_map: dict[str, tuple[tuple[int, str, str], dict[str, Any]]] = {}
        deprecated_guid_map: dict[str, dict[str, Any]] = {}
        deprecated_name_map: dict[str, list[dict[str, Any]]] = {}

        for note in self._notes.values():
            if note.note_type != "component":
                continue

            td = note.type_data or {}
            guid = td.get("guid", "")
            if not guid:
                continue

            detail = {
                "guid": guid,
                "name": note.name,
                "replacement_guid": note.deprecated_by,
                "replacement_name": note.deprecated_replacement_name,
                "reason": note.deprecated_reason,
            }

            if note.deprecated:
                deprecated_guid_map[guid] = detail
                for key in self._component_lookup_keys(note):
                    deprecated_name_map.setdefault(key, []).append(detail)
                continue

            rank = (
                int(td.get("usage_count", 0) or 0),
                note.name,
                note.note_id,
            )
            for key in self._component_lookup_keys(note):
                existing = active_name_map.get(key)
                if existing is None or rank > existing[0]:
                    active_name_map[key] = (rank, detail)

        self._active_component_name_map = {
            key: detail for key, (_, detail) in active_name_map.items()
        }
        self._deprecated_component_guid_map = deprecated_guid_map
        self._deprecated_component_name_map = deprecated_name_map

    def _save_note(self, note: KnowledgeNote) -> None:
        """Save a single note to disk."""
        note_path = self.notes_dir / f"{note.note_id}.json"
        temp_path = note_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(note.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(note_path)

    def _save_index(self) -> None:
        """Save index to disk."""
        self._index.save(self.index_path)

    def _delete_note_file(self, note_id: str) -> None:
        """Delete note file from disk."""
        note_path = self.notes_dir / f"{note_id}.json"
        note_path.unlink(missing_ok=True)

    # === CRUD ===

    def add(self, note: KnowledgeNote, skip_evolution: bool = False) -> str:
        """Add a note, index it, optionally evolve neighbors."""
        self._notes[note.note_id] = note
        if self._should_index(note):
            self._index.add_note(note)
        self._invalidate_component_lookup_cache()

        if self.enable_evolution and not skip_evolution:
            self._evolve(note)

        if self.auto_save:
            self._save_note(note)
            self._save_index()

        return note.note_id

    def get(self, note_id: str, track_access: bool = True) -> Optional[KnowledgeNote]:
        """Get note by ID, optionally track access."""
        note = self._notes.get(note_id)
        if note and track_access:
            note.retrieval_count += 1
            note.last_accessed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return note

    def update(self, note: KnowledgeNote) -> None:
        """Update an existing note, re-index."""
        self._index.remove_note(note.note_id)
        self._notes[note.note_id] = note
        if self._should_index(note):
            self._index.add_note(note)
        self._invalidate_component_lookup_cache()

        if self.auto_save:
            self._save_note(note)
            self._save_index()

    def delete(self, note_id: str) -> bool:
        """Delete a note."""
        if note_id not in self._notes:
            return False

        self._index.remove_note(note_id)
        del self._notes[note_id]
        self._invalidate_component_lookup_cache()

        if self.auto_save:
            self._delete_note_file(note_id)
            self._save_index()

        return True

    # === Search ===

    def search(
        self,
        intent: str = None,
        symptoms: list[str] = None,
        tags: list[str] = None,
        keywords: list[str] = None,
        components: list[str] = None,
        note_type: str = None,
        limit: int = 10,
        tier: TierLevel = "context",
    ) -> list[dict]:
        """Search notes, return at requested tier."""
        # Build query
        intents = [intent] if intent else None

        # Find candidates
        candidate_ids = self._index.find_candidates(
            intents=intents,
            symptoms=symptoms,
            tags=tags,
            keywords=keywords,
            components=components,
            limit=limit * 2,  # Get extra for type filtering
        )

        # Filter by type if requested
        if note_type:
            type_ids = set(self._index.by_type.get(note_type, []))
            candidate_ids = [c for c in candidate_ids if c in type_ids]

        # Return at requested tier
        results = []
        for note_id in candidate_ids[:limit]:
            note = self._notes.get(note_id)
            if note:
                results.append(note.to_tier(tier))

        return results

    # === Component GUID Resolution ===

    def resolve_components(self, intent: str, limit: int = 10) -> list[dict]:
        """Resolve intent to component candidates for GUID-based creation.

        Replaces GHSparseIndex.lookup_multi() in the GUID resolution path.
        Returns dicts compatible with the gh_execute_intent creation pipeline.

        Args:
            intent: Natural language intent or keyword (e.g. "sphere", "divide curve")
            limit: Maximum results to return

        Returns:
            List of dicts: [{guid, name, family, quick, params, source, note_id}, ...]
        """
        try:
            note_ids = self._index.find_component_candidates(intent, limit=limit)
            results = []
            for note_id in note_ids:
                note = self._notes.get(note_id)
                if note and note.note_type == "component" and self._should_index(note):
                    comp_dict = self._component_dict_from_note(note)
                    if comp_dict.get("guid"):
                        results.append(comp_dict)
            return results
        except Exception as e:
            logger.error(f"resolve_components failed for intent '{intent}': {e}")
            return []

    def _component_dict_from_note(self, note: "KnowledgeNote") -> dict:
        """Extract component resolution dict from a component note.

        Produces the {guid, name, family, quick, params} contract that
        GHKnowledgeStore.query() callers and DSPy GHIntentResolver expect.
        """
        td = note.type_data or {}

        # Normalize inputs/outputs: may be list[] or dict{nick: type}
        raw_inputs = td.get("inputs", {})
        raw_outputs = td.get("outputs", {})
        inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
        outputs = raw_outputs if isinstance(raw_outputs, dict) else {}

        return {
            "guid": td.get("guid", ""),
            "name": note.name,
            "family": td.get("category", note.category),
            "quick": note.brief,
            "params": {
                "inputs": inputs,
                "outputs": outputs,
            },
            "note_id": note.note_id,
            "source": "unified_store",
            "deprecated": note.deprecated,
            "deprecated_reason": note.deprecated_reason,
            "deprecated_by": note.deprecated_by,
            "deprecated_replacement_name": note.deprecated_replacement_name,
        }

    def get_component_by_guid(self, guid: str) -> Optional[dict]:
        """Get component resolution dict for a specific GUID.

        O(n) scan — acceptable for 922 component notes. Not in any hot path.

        Args:
            guid: Component creation GUID

        Returns:
            Component dict with guid, name, family, quick, params, or None
        """
        for note in self._notes.values():
            if note.note_type == "component":
                td = note.type_data or {}
                if td.get("guid") == guid:
                    return self._component_dict_from_note(note)

        return None

    def get_component_by_stable_key(self, stable_key: str) -> list[KnowledgeNote]:
        """Find component notes by stable identity key.

        Returns actual KnowledgeNote objects (not dicts) so callers can
        mutate type_data and call store.update(note).

        O(n) scan — acceptable for ~900 component notes, not in any hot path.
        """
        results = []
        for note in self._notes.values():
            if note.note_type == "component" and not note.deprecated:
                td = note.type_data or {}
                if td.get("stable_key") == stable_key:
                    results.append(note)
        return results

    def get_component_by_name_without_stable_key(self, name: str) -> list[KnowledgeNote]:
        """Find non-deprecated component notes matching name that lack stable_key.

        Used for migration: when a pre-existing note has no stable_key,
        this allows name-based matching so the stable_key can be backfilled.
        """
        results = []
        name_lower = name.lower()
        for note in self._notes.values():
            if note.note_type == "component" and not note.deprecated:
                if note.name and note.name.lower() == name_lower:
                    td = note.type_data or {}
                    if not td.get("stable_key"):
                        results.append(note)
        return results

    def resolve_active_component_guid_by_name(self, name: str) -> Optional[str]:
        """Resolve an exact component name to a non-deprecated GUID."""
        self._ensure_component_lookup_cache()
        assert self._active_component_name_map is not None

        detail = self._active_component_name_map.get(name.lower())
        if detail is None:
            return None
        return detail["guid"]

    def get_deprecated_component(self, guid: str) -> Optional[dict[str, Any]]:
        """Return deprecation metadata for a GUID, if known."""
        self._ensure_component_lookup_cache()
        assert self._deprecated_component_guid_map is not None
        return self._deprecated_component_guid_map.get(guid)

    def get_active_component_guid_set(self) -> set[str]:
        """Return the set of GUIDs for all non-deprecated component notes."""
        result: set[str] = set()
        for note in self._notes.values():
            if note.note_type == "component" and not note.deprecated:
                td = note.type_data or {}
                guid = td.get("guid")
                if guid:
                    result.add(guid)
        return result

    def get_deprecated_component_guid_set(self) -> set[str]:
        """Return the set of GUIDs for all deprecated component notes."""
        self._ensure_component_lookup_cache()
        assert self._deprecated_component_guid_map is not None
        return set(self._deprecated_component_guid_map.keys())

    def check_deprecation_warnings(self, create_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return warning payloads for deprecated GUIDs or ambiguous create-by-name entries."""
        self._ensure_component_lookup_cache()
        assert self._deprecated_component_guid_map is not None
        assert self._deprecated_component_name_map is not None

        warnings: list[dict[str, Any]] = []
        for entry in create_entries:
            temp_id = entry.get("temp_id")
            guid = entry.get("guid")
            name = entry.get("name")

            if isinstance(guid, str) and guid:
                deprecated = self._deprecated_component_guid_map.get(guid)
                if deprecated:
                    warnings.append({
                        "temp_id": temp_id,
                        "type": "deprecated_guid",
                        "guid": guid,
                        "name": deprecated["name"],
                        "replacement_guid": deprecated.get("replacement_guid"),
                        "replacement_name": deprecated.get("replacement_name"),
                        "reason": deprecated.get("reason"),
                    })
                continue

            if isinstance(name, str) and name:
                deprecated_entries = self._deprecated_component_name_map.get(name.lower(), [])
                if deprecated_entries:
                    warnings.append({
                        "temp_id": temp_id,
                        "type": "ambiguous_name",
                        "name": name,
                        "deprecated_guids": [
                            detail["guid"] for detail in deprecated_entries if detail.get("guid")
                        ],
                        "replacement_guids": [
                            detail["replacement_guid"]
                            for detail in deprecated_entries
                            if detail.get("replacement_guid")
                        ],
                        "replacement_names": [
                            detail["replacement_name"]
                            for detail in deprecated_entries
                            if detail.get("replacement_name")
                        ],
                    })

        return warnings

    # === DAG Traversal ===

    def get_related(self, note_id: str) -> dict:
        """Get notes linked to/from this note."""
        note = self.get(note_id, track_access=False)
        return {
            "links_to": self._index.get_notes_linking_to(note_id),
            "links_from": note.links if note else [],
        }

    # === Staleness Tracking (P2) ===

    def mark_used_successfully(self, note_id: str, success: bool = True) -> bool:
        """Record that a note's knowledge was injected and used.

        Increments times_used (always) and times_succeeded (on success),
        updates last_verified, and persists.

        Args:
            note_id: The note ID to update.
            success: Whether the tool call that used this hint succeeded.

        Returns:
            True if updated, False if note not found.
        """
        note = self._notes.get(note_id)
        if note is None:
            return False

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        note.times_used += 1
        if success:
            note.times_succeeded += 1
        note.last_verified = now
        note.last_accessed = now

        if self.auto_save:
            self._save_note(note)

        return True

    # === Bulk Operations ===

    def rebuild_index(self) -> None:
        """Rebuild the index from scratch using current in-memory notes.

        Use after bulk modifications (purge, enrichment, re-linking)
        to ensure the index matches the actual note data.
        """
        self._index = self._build_index_from_notes()
        if self.auto_save:
            self._save_index()
        logger.info(f"Index rebuilt: {len(self._index)} searchable notes indexed")

    def all(self) -> list[KnowledgeNote]:
        """Return all notes."""
        return list(self._notes.values())

    def save_all(self) -> None:
        """Save all notes and index."""
        for note in self._notes.values():
            self._save_note(note)
        self._save_index()

    def __len__(self) -> int:
        return len(self._notes)

    # === Evolution ===

    def _evolve(self, note: KnowledgeNote) -> None:
        """A-MEM evolution - find candidates, decide links, evolve neighbors."""
        if self._evolution is None:
            from .knowledge_evolution import get_knowledge_evolution
            self._evolution = get_knowledge_evolution()

        try:
            modified_neighbor_ids = self._evolution.evolve(
                note=note,
                store=self,
            )
            if modified_neighbor_ids:
                logger.info(
                    f"Evolution of {note.note_id} modified {len(modified_neighbor_ids)} neighbors"
                )
        except Exception as e:
            logger.warning(f"Evolution failed for {note.note_id}: {e}")


# Singleton accessor
_unified_store: Optional[UnifiedStore] = None


def get_unified_store() -> UnifiedStore:
    """Get the singleton UnifiedStore instance."""
    global _unified_store
    if _unified_store is None:
        _unified_store = UnifiedStore()
    return _unified_store


def reset_unified_store() -> None:
    """Reset the singleton (for testing)."""
    global _unified_store
    _unified_store = None
