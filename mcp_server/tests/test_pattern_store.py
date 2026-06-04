"""
Tests for Pattern Store (Phase 2, Task 3)

Tests:
- CRUD operations (add, get, update, delete)
- Search functionality
- Link operations
- Confidence tracking
- Persistence (save/load)
- Statistics
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from rook.learning.pattern_memory import PatternNote, PatternIndex
from rook.learning.pattern_store import PatternStore


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_knowledge_dir(tmp_path):
    """Create a temporary knowledge directory for testing."""
    knowledge_dir = tmp_path / "knowledge" / "gh"
    patterns_dir = knowledge_dir / "patterns"
    patterns_dir.mkdir(parents=True)
    return knowledge_dir


@pytest.fixture
def store(temp_knowledge_dir, monkeypatch):
    """Create a PatternStore with temporary storage."""
    # Patch the storage paths to use temp directory
    monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_PATTERNS_DIR", temp_knowledge_dir / "patterns")
    monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

    # Disable evolution for unit tests - evolution uses DSPy and adds unpredictable links
    return PatternStore(auto_save=True, enable_evolution=False)


@pytest.fixture
def sample_pattern():
    """Create a sample pattern for testing."""
    return PatternNote(
        pattern_id="test001",
        name="Test Pattern",
        solution_brief="This is a test pattern",
        solution_principle="Testing the pattern store",
        trigger_intents=["test intent", "another intent"],
        trigger_symptoms=["test symptom"],
        tags=["test", "sample"],
        components_needed=["TestComponent"],
    )


@pytest.fixture
def another_pattern():
    """Create another sample pattern for testing."""
    return PatternNote(
        pattern_id="test002",
        name="Another Pattern",
        solution_brief="This is another pattern",
        trigger_intents=["different intent"],
        trigger_symptoms=["different symptom", "test symptom"],
        tags=["test", "different"],
        components_needed=["OtherComponent"],
    )


@pytest.fixture(autouse=True)
def _isolate_bundled_patterns(tmp_path, monkeypatch):
    """Neutralize the read-only bundled-patterns source so unit tests see
    only their temp store.

    PatternStore._load_all() merges patterns from _bundled_patterns_dir()
    (the shipped knowledge/gh/patterns, ~520 notes) in addition to the
    writable dir. Without this, the count/stats/search assertions below
    would be polluted by shipped patterns. Point the bundled dir at a
    non-existent path so the .exists() guard in _load_all skips it.
    """
    monkeypatch.setattr(
        "rook.learning.pattern_store._bundled_patterns_dir",
        lambda: tmp_path / "_no_bundled_source",
    )


# =============================================================================
# CRUD Tests
# =============================================================================

class TestPatternStoreCRUD:
    """Tests for CRUD operations."""

    def test_add_pattern(self, store, sample_pattern):
        """Adding a pattern stores it and indexes it."""
        result = store.add(sample_pattern)

        assert result.pattern_id == "test001"
        assert store.get("test001") is not None
        assert "test001" in store
        assert len(store) == 1

    def test_add_duplicate_raises(self, store, sample_pattern):
        """Adding a pattern with existing ID raises ValueError."""
        store.add(sample_pattern)

        with pytest.raises(ValueError, match="already exists"):
            store.add(sample_pattern)

    def test_get_returns_pattern(self, store, sample_pattern):
        """Get returns the stored pattern."""
        store.add(sample_pattern)
        result = store.get("test001")

        assert result is not None
        assert result.name == "Test Pattern"

    def test_get_missing_returns_none(self, store):
        """Get returns None for missing pattern."""
        assert store.get("nonexistent") is None

    def test_update_pattern(self, store, sample_pattern):
        """Updating a pattern persists changes."""
        store.add(sample_pattern)

        sample_pattern.name = "Updated Name"
        sample_pattern.tags.append("updated")
        store.update(sample_pattern)

        result = store.get("test001")
        assert result.name == "Updated Name"
        assert "updated" in result.tags

    def test_update_missing_raises(self, store, sample_pattern):
        """Updating a non-existent pattern raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            store.update(sample_pattern)

    def test_delete_pattern(self, store, sample_pattern):
        """Deleting a pattern removes it from store and index."""
        store.add(sample_pattern)
        assert len(store) == 1

        result = store.delete("test001")

        assert result is True
        assert store.get("test001") is None
        assert "test001" not in store
        assert len(store) == 0

    def test_delete_missing_returns_false(self, store):
        """Deleting a non-existent pattern returns False."""
        assert store.delete("nonexistent") is False

    def test_exists(self, store, sample_pattern):
        """Exists correctly reports pattern presence."""
        assert store.exists("test001") is False

        store.add(sample_pattern)

        assert store.exists("test001") is True
        assert store.exists("nonexistent") is False

    def test_get_all(self, store, sample_pattern, another_pattern):
        """Get all returns all stored patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        all_patterns = store.get_all()

        assert len(all_patterns) == 2
        pattern_ids = [p.pattern_id for p in all_patterns]
        assert "test001" in pattern_ids
        assert "test002" in pattern_ids


# =============================================================================
# Search Tests
# =============================================================================

class TestPatternStoreSearch:
    """Tests for search functionality."""

    def test_search_by_symptom(self, store, sample_pattern, another_pattern):
        """Search by symptom returns matching patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        # Both patterns have "test symptom"
        results = store.search(symptoms=["test symptom"])

        assert len(results) == 2

    def test_search_by_intent(self, store, sample_pattern, another_pattern):
        """Search by intent returns matching patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        results = store.search(intent="test intent")

        # Only sample_pattern has "test intent"
        assert len(results) >= 1
        assert any(p.pattern_id == "test001" for p in results)

    def test_search_by_tag(self, store, sample_pattern, another_pattern):
        """Search by tag returns matching patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        results = store.search(tags=["sample"])

        assert len(results) == 1
        assert results[0].pattern_id == "test001"

    def test_search_by_component(self, store, sample_pattern, another_pattern):
        """Search by component returns matching patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        results = store.search(components=["TestComponent"])

        assert len(results) == 1
        assert results[0].pattern_id == "test001"

    def test_search_combined(self, store, sample_pattern, another_pattern):
        """Search with multiple criteria uses combined scoring."""
        store.add(sample_pattern)
        store.add(another_pattern)

        # Search for symptoms both have + tag only sample_pattern has
        results = store.search(
            symptoms=["test symptom"],
            tags=["sample"],
        )

        # sample_pattern should rank higher (symptom + tag)
        assert len(results) >= 1
        assert results[0].pattern_id == "test001"

    def test_search_respects_limit(self, store):
        """Search limit caps results."""
        # Add many patterns
        for i in range(10):
            pattern = PatternNote(
                pattern_id=f"p{i}",
                name=f"Pattern {i}",
                trigger_symptoms=["common symptom"],
            )
            store.add(pattern)

        results = store.search(symptoms=["common symptom"], limit=3)

        assert len(results) == 3

    def test_search_sorts_by_success_rate(self, store):
        """Search results are sorted by success rate."""
        # Pattern with high success rate
        high_success = PatternNote(
            pattern_id="high",
            name="High Success",
            trigger_symptoms=["shared symptom"],
            times_used=10,
            times_succeeded=9,
        )
        # Pattern with low success rate
        low_success = PatternNote(
            pattern_id="low",
            name="Low Success",
            trigger_symptoms=["shared symptom"],
            times_used=10,
            times_succeeded=2,
        )

        store.add(low_success)
        store.add(high_success)

        results = store.search(symptoms=["shared symptom"])

        assert results[0].pattern_id == "high"
        assert results[1].pattern_id == "low"

    def test_search_no_results(self, store, sample_pattern):
        """Search with no matches returns empty list."""
        store.add(sample_pattern)

        results = store.search(symptoms=["nonexistent symptom"])

        assert results == []

    def test_get_by_tag(self, store, sample_pattern, another_pattern):
        """Get by tag returns all patterns with tag."""
        store.add(sample_pattern)
        store.add(another_pattern)

        results = store.get_by_tag("test")

        assert len(results) == 2

    def test_get_by_component(self, store, sample_pattern, another_pattern):
        """Get by component returns all patterns using component."""
        store.add(sample_pattern)
        store.add(another_pattern)

        results = store.get_by_component("TestComponent")

        assert len(results) == 1
        assert results[0].pattern_id == "test001"


# =============================================================================
# Link Tests
# =============================================================================

class TestPatternStoreLinks:
    """Tests for link operations."""

    def test_get_neighbors_empty(self, store, sample_pattern):
        """Get neighbors returns empty list when no links."""
        store.add(sample_pattern)

        neighbors = store.get_neighbors("test001")

        assert neighbors == []

    def test_add_link_bidirectional(self, store, sample_pattern, another_pattern):
        """Add link creates bidirectional connection."""
        store.add(sample_pattern)
        store.add(another_pattern)

        result = store.add_link("test001", "test002")

        assert result is True

        # Check forward link
        p1 = store.get("test001")
        assert "test002" in p1.links

        # Check reverse link
        p2 = store.get("test002")
        assert "test001" in p2.links

    def test_add_link_unidirectional(self, store, sample_pattern, another_pattern):
        """Add link with bidirectional=False creates one-way link."""
        store.add(sample_pattern)
        store.add(another_pattern)

        store.add_link("test001", "test002", bidirectional=False)

        p1 = store.get("test001")
        p2 = store.get("test002")

        assert "test002" in p1.links
        assert "test001" not in p2.links

    def test_add_link_missing_pattern(self, store, sample_pattern):
        """Add link returns False if pattern not found."""
        store.add(sample_pattern)

        result = store.add_link("test001", "nonexistent")

        assert result is False

    def test_get_neighbors_with_links(self, store, sample_pattern, another_pattern):
        """Get neighbors returns linked patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)
        store.add_link("test001", "test002")

        neighbors = store.get_neighbors("test001")

        assert len(neighbors) == 1
        assert neighbors[0].pattern_id == "test002"

    def test_remove_link_bidirectional(self, store, sample_pattern, another_pattern):
        """Remove link removes bidirectional connection."""
        store.add(sample_pattern)
        store.add(another_pattern)
        store.add_link("test001", "test002")

        result = store.remove_link("test001", "test002")

        assert result is True

        p1 = store.get("test001")
        p2 = store.get("test002")

        assert "test002" not in p1.links
        assert "test001" not in p2.links

    def test_delete_cleans_up_stale_links(self, store, sample_pattern, another_pattern):
        """Deleting a pattern removes links from other patterns pointing to it."""
        store.add(sample_pattern)
        store.add(another_pattern)
        store.add_link("test001", "test002")

        # Verify links exist
        assert "test002" in store.get("test001").links
        assert "test001" in store.get("test002").links

        # Delete test002
        store.delete("test002")

        # test001 should no longer have link to deleted pattern
        p1 = store.get("test001")
        assert "test002" not in p1.links


# =============================================================================
# Confidence Tracking Tests
# =============================================================================

class TestPatternStoreConfidence:
    """Tests for confidence tracking."""

    def test_record_use_success(self, store, sample_pattern):
        """Recording successful use updates confidence."""
        store.add(sample_pattern)

        store.record_use("test001", success=True)

        pattern = store.get("test001")
        assert pattern.times_used == 1
        assert pattern.times_succeeded == 1
        assert pattern.last_used is not None
        assert pattern.last_verified is not None

    def test_record_use_failure(self, store, sample_pattern):
        """Recording failed use updates times_used but not succeeded."""
        store.add(sample_pattern)

        store.record_use("test001", success=False)

        pattern = store.get("test001")
        assert pattern.times_used == 1
        assert pattern.times_succeeded == 0
        assert pattern.last_used is not None
        assert pattern.last_verified is None  # Not verified on failure

    def test_record_use_with_session(self, store, sample_pattern):
        """Recording use with session adds citation."""
        store.add(sample_pattern)

        store.record_use("test001", success=True, session_id="session_123", notes="Worked well")

        pattern = store.get("test001")
        assert len(pattern.citations) == 1
        assert pattern.citations[0]["session_id"] == "session_123"
        assert pattern.citations[0]["outcome"] == "success"
        assert pattern.citations[0]["notes"] == "Worked well"

    def test_record_use_missing_pattern(self, store):
        """Recording use for missing pattern returns None."""
        result = store.record_use("nonexistent", success=True)
        assert result is None

    def test_success_rate_updates(self, store, sample_pattern):
        """Success rate reflects usage history."""
        store.add(sample_pattern)

        store.record_use("test001", success=True)
        store.record_use("test001", success=True)
        store.record_use("test001", success=False)
        store.record_use("test001", success=True)

        pattern = store.get("test001")
        assert pattern.times_used == 4
        assert pattern.times_succeeded == 3
        assert pattern.success_rate() == 0.75


# =============================================================================
# Persistence Tests
# =============================================================================

class TestPatternStorePersistence:
    """Tests for save/load functionality."""

    def test_pattern_persisted_on_add(self, store, sample_pattern, temp_knowledge_dir):
        """Adding a pattern saves it to disk."""
        store.add(sample_pattern)

        pattern_file = temp_knowledge_dir / "patterns" / "test001.json"
        assert pattern_file.exists()

        with open(pattern_file) as f:
            data = json.load(f)
        assert data["pattern_id"] == "test001"
        assert data["name"] == "Test Pattern"

    def test_index_persisted_on_add(self, store, sample_pattern, temp_knowledge_dir):
        """Adding a pattern saves the index."""
        store.add(sample_pattern)

        index_file = temp_knowledge_dir / "pattern_index.json"
        assert index_file.exists()

        with open(index_file) as f:
            data = json.load(f)
        assert "test001" in data["all_patterns"]

    def test_pattern_loaded_on_init(self, temp_knowledge_dir, monkeypatch):
        """Patterns are loaded from disk on initialization."""
        # Create a pattern file
        patterns_dir = temp_knowledge_dir / "patterns"
        patterns_dir.mkdir(parents=True, exist_ok=True)

        pattern_data = PatternNote(
            pattern_id="preexisting",
            name="Pre-existing Pattern",
        ).to_dict()

        with open(patterns_dir / "preexisting.json", "w") as f:
            json.dump(pattern_data, f)

        # Patch and create store
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_PATTERNS_DIR", patterns_dir)
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

        store = PatternStore()

        assert "preexisting" in store
        assert store.get("preexisting").name == "Pre-existing Pattern"

    def test_delete_removes_file(self, store, sample_pattern, temp_knowledge_dir):
        """Deleting a pattern removes its file."""
        store.add(sample_pattern)
        pattern_file = temp_knowledge_dir / "patterns" / "test001.json"
        assert pattern_file.exists()

        store.delete("test001")

        assert not pattern_file.exists()

    def test_manual_save(self, temp_knowledge_dir, monkeypatch, sample_pattern, another_pattern):
        """Manual save persists all patterns."""
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_PATTERNS_DIR", temp_knowledge_dir / "patterns")
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

        store = PatternStore(auto_save=False)
        store.add(sample_pattern)
        store.add(another_pattern)

        # Files shouldn't exist yet
        assert not (temp_knowledge_dir / "patterns" / "test001.json").exists()

        store.save()

        # Now they should exist
        assert (temp_knowledge_dir / "patterns" / "test001.json").exists()
        assert (temp_knowledge_dir / "patterns" / "test002.json").exists()

    def test_rebuild_index(self, store, sample_pattern, another_pattern):
        """Rebuild index recreates index from patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        # Corrupt the index
        store.index = PatternIndex()
        assert len(store.index) == 0

        # Rebuild
        store.rebuild_index()

        assert len(store.index) == 2
        assert "test001" in store.index.all_patterns


# =============================================================================
# Statistics Tests
# =============================================================================

class TestPatternStoreStats:
    """Tests for statistics."""

    def test_stats_empty_store(self, store):
        """Stats work on empty store."""
        stats = store.stats()

        assert stats["total_patterns"] == 0
        assert stats["overall_success_rate"] == 0.0

    def test_stats_with_patterns(self, store, sample_pattern, another_pattern):
        """Stats reflect stored patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)

        stats = store.stats()

        assert stats["total_patterns"] == 2
        assert stats["total_tags"] > 0

    def test_stats_verified_patterns(self, store, sample_pattern):
        """Stats count verified patterns."""
        store.add(sample_pattern)
        store.record_use("test001", success=True)

        stats = store.stats()

        assert stats["verified_patterns"] == 1

    def test_stats_linked_patterns(self, store, sample_pattern, another_pattern):
        """Stats count linked patterns."""
        store.add(sample_pattern)
        store.add(another_pattern)
        store.add_link("test001", "test002")

        stats = store.stats()

        assert stats["linked_patterns"] == 2  # Both are linked


# =============================================================================
# Edge Cases
# =============================================================================

class TestPatternStoreEdgeCases:
    """Tests for edge cases."""

    def test_repr(self, store, sample_pattern):
        """Repr includes useful info."""
        store.add(sample_pattern)
        repr_str = repr(store)

        assert "PatternStore" in repr_str
        assert "patterns=1" in repr_str

    def test_contains(self, store, sample_pattern):
        """Contains operator works."""
        store.add(sample_pattern)

        assert "test001" in store
        assert "nonexistent" not in store

    def test_len(self, store, sample_pattern, another_pattern):
        """Len returns pattern count."""
        assert len(store) == 0

        store.add(sample_pattern)
        assert len(store) == 1

        store.add(another_pattern)
        assert len(store) == 2

    def test_update_reindexes(self, store, sample_pattern):
        """Updating a pattern re-indexes it correctly."""
        store.add(sample_pattern)

        # Original tag
        results = store.get_by_tag("sample")
        assert len(results) == 1

        # Update tags
        sample_pattern.tags = ["new-tag"]
        store.update(sample_pattern)

        # Old tag should not find it
        results = store.get_by_tag("sample")
        assert len(results) == 0

        # New tag should find it
        results = store.get_by_tag("new-tag")
        assert len(results) == 1


# =============================================================================
# V2 Recipe Round-Trip Tests
# =============================================================================

class TestPatternStoreV2Recipes:
    """Tests for v2 recipe format round-trip through PatternStore."""

    def test_v2_recipe_roundtrip_through_store(self, store, temp_knowledge_dir, monkeypatch):
        """V2 recipe with graph field survives add -> save -> reload cycle."""
        v2_pattern = PatternNote(
            pattern_id="v2test01",
            name="V2 Round-Trip Test",
            pattern_type="recipe",
            schema_version="2.0",
            tags=["test", "v2"],
            components_needed=["Hexagonal", "Pipe"],
            trigger_intents=["hexagonal pipe grid"],
            graph={
                "components": [
                    {"id": "R1", "type": "Hexagonal", "guid": "125dc0e2-41d5-4651-af2d-8a3e0be0a4d8", "pos": [100, 100]},
                    {"id": "R2", "type": "Pipe", "guid": "d4ff5c72-c7e7-4e2f-9e20-8d3a82e8e437", "pos": [400, 100]},
                ],
                "flows": ["R1.O0>R2.I0"],
                "subgraphs": [
                    {
                        "id": "S1",
                        "role": "pattern_source",
                        "nick": "hex_grid",
                        "members": ["R1"],
                        "inputs": [],
                        "outputs": ["R1.O0"],
                    }
                ],
            },
            wiring=[],
            input_structure={},
            output_type="brep",
            source_definition="test_v2.ghx",
        )

        # Add to store (persists to disk)
        store.add(v2_pattern)

        # Verify file was written
        pattern_file = temp_knowledge_dir / "patterns" / "v2test01.json"
        assert pattern_file.exists()

        # Verify JSON on disk has v2 fields
        with open(pattern_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["recipe"]["schema_version"] == "2.0"
        assert data["recipe"]["graph"] is not None
        assert len(data["recipe"]["graph"]["components"]) == 2
        assert data["recipe"]["graph"]["flows"] == ["R1.O0>R2.I0"]
        assert len(data["recipe"]["graph"]["subgraphs"]) == 1

        # Create a fresh store that loads from disk
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_PATTERNS_DIR", temp_knowledge_dir / "patterns")
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

        fresh_store = PatternStore(enable_evolution=False)

        # Verify the reloaded pattern has v2 fields intact
        reloaded = fresh_store.get("v2test01")
        assert reloaded is not None
        assert reloaded.schema_version == "2.0"
        assert reloaded.graph is not None
        assert len(reloaded.graph["components"]) == 2
        assert reloaded.graph["components"][0]["id"] == "R1"
        assert reloaded.graph["components"][0]["type"] == "Hexagonal"
        assert reloaded.graph["flows"] == ["R1.O0>R2.I0"]
        assert len(reloaded.graph["subgraphs"]) == 1
        assert reloaded.graph["subgraphs"][0]["role"] == "pattern_source"

        # Verify other fields survived too
        assert reloaded.name == "V2 Round-Trip Test"
        assert reloaded.pattern_type == "recipe"
        assert reloaded.output_type == "brep"

    def test_v1_pattern_loads_with_default_schema_version(self, store, temp_knowledge_dir, monkeypatch):
        """V1 pattern (no schema_version in JSON) loads with schema_version='1.0' and graph=None."""
        # Write a v1-style JSON file directly (no schema_version key in recipe)
        v1_data = {
            "pattern_id": "v1legacy",
            "name": "Legacy V1 Pattern",
            "version": "1.0",
            "created": "2026-01-15T10:00:00Z",
            "solution": {"brief": "A legacy pattern", "principle": "", "components_needed": ["Sphere"]},
            "triggers": {"intents": ["create sphere"], "symptoms": []},
            "scope": {"global": True, "project_types": [], "workflow_types": []},
            "anti_patterns": [],
            "constraints": {"preconditions": [], "postconditions": []},
            "verification": {"test": "", "expected": ""},
            "citations": [],
            "confidence": {"times_used": 0, "times_succeeded": 0, "last_used": None, "last_verified": None},
            "links": [],
            "tags": ["legacy"],
            "evolution": {"created_from": "manual", "last_evolved": None, "evolved_by": [], "evolution_history": []},
            "recipe": {
                "pattern_type": "recipe",
                "wiring": [{"from": "a", "from_param": "out", "to": "b", "to_param": "R"}],
                "input_structure": {"sliders": []},
                "output_type": "surface",
                "source_definition": "old.ghx",
                # Note: no "schema_version" or "graph" keys
            },
        }

        patterns_dir = temp_knowledge_dir / "patterns"
        with open(patterns_dir / "v1legacy.json", "w", encoding="utf-8") as f:
            json.dump(v1_data, f)

        # Create store that loads from disk
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_PATTERNS_DIR", patterns_dir)
        monkeypatch.setattr("rook.learning.pattern_store.DEFAULT_INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

        fresh_store = PatternStore(enable_evolution=False)

        loaded = fresh_store.get("v1legacy")
        assert loaded is not None
        assert loaded.schema_version == "1.0"
        assert loaded.graph is None
        assert loaded.wiring == [{"from": "a", "from_param": "out", "to": "b", "to_param": "R"}]

    def test_v2_recipe_in_stats(self, store):
        """Stats correctly count v1 vs v2 recipes."""
        # Add a v1 recipe
        v1 = PatternNote(
            pattern_id="v1rec",
            name="V1 Recipe",
            pattern_type="recipe",
            schema_version="1.0",
        )
        store.add(v1)

        # Add a v2 recipe
        v2 = PatternNote(
            pattern_id="v2rec",
            name="V2 Recipe",
            pattern_type="recipe",
            schema_version="2.0",
            graph={"components": [], "flows": []},
        )
        store.add(v2)

        # Add a struggle (not a recipe)
        struggle = PatternNote(
            pattern_id="strug1",
            name="A Struggle",
            pattern_type="struggle",
        )
        store.add(struggle)

        stats = store.stats()
        assert stats["v2_recipes"] == 1
        assert stats["v1_recipes"] == 1
        assert stats["total_patterns"] == 3

    def test_v2_recipe_searchable_by_components(self, store):
        """V2 recipes are searchable by their components_needed just like v1."""
        v2 = PatternNote(
            pattern_id="v2search",
            name="Searchable V2",
            pattern_type="recipe",
            schema_version="2.0",
            components_needed=["Hexagonal", "Pipe"],
            graph={"components": [{"id": "R1", "type": "Hexagonal"}], "flows": []},
        )
        store.add(v2)

        results = store.search(components=["Hexagonal"])
        assert len(results) == 1
        assert results[0].pattern_id == "v2search"
        assert results[0].schema_version == "2.0"
