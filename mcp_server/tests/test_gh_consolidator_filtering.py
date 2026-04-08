# mcp_server/tests/test_gh_consolidator_filtering.py
"""Tests for GHConsolidator: deprecated filtering, UnifiedStore write-back,
observation loading, stable_key metadata, name/stable_key queries, orphan modes."""
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from rook.learning.gh_consolidator import (
    GHConsolidator,
    ComponentStructure,
    ComponentFamily,
    SimilarComponentPair,
    query_gh_structure,
)
from rook.learning.unified_store import UnifiedStore
from rook.learning.knowledge_note import KnowledgeNote


def _make_tiered_knowledge(components: dict) -> dict:
    """Create a minimal tiered_knowledge.json structure."""
    return {"components": components}


def _make_component_entry(name: str, family: str = "unknown", gotchas: list | None = None) -> dict:
    """Create a minimal tiered component entry."""
    return {
        "name": name,
        "family": family,
        "params": {"inputs": {}, "outputs": {}},
        "gotchas": gotchas or [],
    }


@pytest.fixture
def test_env():
    """Create a temp dir with tiered_knowledge + UnifiedStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        notes_dir = base / "notes"
        index_path = base / "index.json"
        knowledge_path = base / "tiered_knowledge.json"
        structure_path = base / "component_structure.json"
        observations_path = base / "component_observations.json"

        # Write observations in current format (name-keyed list)
        observations_data = {
            "version": "1.0",
            "observations": [
                {
                    "date": "2026-03-01",
                    "component": "Circle",
                    "observation": "Circle requires a plane input, not just a point",
                    "impact": "medium",
                    "resolution": "Use XY plane at desired center point",
                    "tags": ["wiring"],
                },
                {
                    "date": "2026-03-02",
                    "component": "Pipe",
                    "observation": "Cap type must be 0, 1, or 2",
                    "impact": "high",
                    "resolution": "Validate integer before passing",
                    "tags": ["enum-param"],
                },
            ],
        }
        observations_path.write_text(json.dumps(observations_data, indent=2))

        # Create UnifiedStore
        store = UnifiedStore(
            notes_dir=notes_dir,
            index_path=index_path,
            auto_save=True,
            enable_evolution=False,
        )

        # Add active component notes (with stable_key)
        for nid, guid, name, stable_key in [
            ("comp_circle", "guid-circle", "Circle", "primitives|curves|circle"),
            ("comp_pipe", "guid-pipe", "Pipe", "surface_ops|pipe"),
            ("comp_slider", "guid-slider", "Number Slider", "input|number_slider"),
        ]:
            note = KnowledgeNote(
                note_id=nid,
                note_type="component",
                name=name,
                brief=f"{name} component",
                created="2026-02-01T12:00:00Z",
                type_data={"guid": guid, "stable_key": stable_key},
            )
            store.add(note, skip_evolution=True)

        # Add deprecated component notes
        for nid, guid, name in [
            ("comp_int_old", "guid-integer-old", "Integer"),
            ("comp_grab_old", "guid-grab-old", "Grab"),
        ]:
            note = KnowledgeNote(
                note_id=nid,
                note_type="component",
                name=name,
                brief=f"Deprecated {name}",
                created="2026-02-01T12:00:00Z",
                type_data={"guid": guid},
                deprecated=True,
                deprecated_by="guid-replacement",
                deprecated_replacement_name=name,
            )
            store.add(note, skip_evolution=True)

        # Write tiered_knowledge.json with all GUIDs (including deprecated + unknown)
        tiered = _make_tiered_knowledge({
            "guid-circle": _make_component_entry("Circle", gotchas=["Needs plane input"]),
            "guid-pipe": _make_component_entry("Pipe", gotchas=["Cap type enum"]),
            "guid-slider": _make_component_entry("Number Slider"),
            "guid-integer-old": _make_component_entry("Integer"),
            "guid-grab-old": _make_component_entry("Grab"),
            "guid-orphan": _make_component_entry("Orphan Component"),  # no note
        })
        knowledge_path.write_text(json.dumps(tiered, indent=2))

        yield {
            "base": base,
            "store": store,
            "knowledge_path": knowledge_path,
            "structure_path": structure_path,
            "observations_path": observations_path,
        }


class TestLoadComponentsFiltering:
    def test_excludes_deprecated_guids(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            components = consolidator.load_components()

        assert "guid-integer-old" not in components
        assert "guid-grab-old" not in components

    def test_retains_active_guids(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            components = consolidator.load_components()

        assert "guid-circle" in components
        assert "guid-pipe" in components
        assert "guid-slider" in components

    def test_retains_unknown_guids(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            components = consolidator.load_components()

        # Orphan GUID (no note) should be retained in legacy mode
        assert "guid-orphan" in components

    def test_filter_stats_are_correct(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            consolidator.load_components()

        # 3 active from UnifiedStore + 1 orphan from tiered = 4 active
        assert consolidator.active_component_count == 4
        assert consolidator.deprecated_skipped_count == 2
        assert consolidator.unknown_guid_count == 1

    def test_graceful_fallback_when_store_unavailable(self, test_env):
        """If UnifiedStore fails to load, all components are retained."""
        with patch("rook.learning.unified_store.get_unified_store",
                    side_effect=RuntimeError("store unavailable")):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            components = consolidator.load_components()

        # All 6 components retained when store fails
        assert len(components) == 6
        assert consolidator.deprecated_skipped_count == 0


class TestObservationLoading:
    def test_loads_component_observations_format(self, test_env):
        """Observations from component_observations.json (list format) are loaded and normalized to GUID keys."""
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            observations = consolidator.load_observations()

        # Circle and Pipe should be resolved to their GUIDs
        assert "guid-circle" in observations
        assert "guid-pipe" in observations
        assert len(observations["guid-circle"]) == 1
        assert len(observations["guid-pipe"]) == 1
        assert "plane" in observations["guid-circle"][0]["observation"].lower()

    def test_handles_empty_observations(self, test_env):
        """Empty observations file returns empty dict."""
        empty_path = test_env["base"] / "empty_obs.json"
        empty_path.write_text(json.dumps({"observations": []}))

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=empty_path,
            )
            observations = consolidator.load_observations()

        assert observations == {}

    def test_handles_legacy_dict_format(self, test_env):
        """Legacy GUID-keyed dict format still works."""
        legacy_path = test_env["base"] / "legacy_obs.json"
        legacy_path.write_text(json.dumps({
            "observations": {"guid-circle": {"some": "data"}}
        }))

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=legacy_path,
            )
            observations = consolidator.load_observations()

        assert "guid-circle" in observations


class TestUnifiedStoreWriteBack:
    def test_writes_family_and_similar_to_notes(self, test_env):
        """update_tiered_knowledge() writes family and similar_to to UnifiedStore notes."""
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            # Build a minimal structure
            consolidator._structure = ComponentStructure(
                families={
                    "curves": ComponentFamily(
                        name="curves",
                        description="Curve components",
                        components=["guid-circle", "guid-pipe"],
                    ),
                },
                similar_pairs=[
                    SimilarComponentPair(
                        comp1_guid="guid-circle",
                        comp2_guid="guid-pipe",
                        similarity_score=0.8,
                        reason="Both create geometry from curves",
                    ),
                ],
            )

            updates = consolidator.update_tiered_knowledge()

        # Verify UnifiedStore notes were updated
        assert updates["unified_store_updates"] >= 2

        # Check the actual note data
        circle_note = store.get("comp_circle", track_access=False)
        assert circle_note.type_data["family"] == "curves"
        assert "guid-pipe" in circle_note.type_data["similar_to"]

        pipe_note = store.get("comp_pipe", track_access=False)
        assert pipe_note.type_data["family"] == "curves"
        assert "guid-circle" in pipe_note.type_data["similar_to"]

    def test_also_writes_tiered_knowledge(self, test_env):
        """update_tiered_knowledge() also updates tiered_knowledge.json as derived cache."""
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            consolidator._structure = ComponentStructure(
                families={
                    "curves": ComponentFamily(
                        name="curves",
                        description="Curve components",
                        components=["guid-circle"],
                    ),
                },
            )

            consolidator.update_tiered_knowledge()

        # Verify tiered_knowledge.json was also updated
        with open(test_env["knowledge_path"], "r") as f:
            tiered = json.load(f)

        assert tiered["components"]["guid-circle"]["family"] == "curves"


    def test_clears_stale_similar_to_links(self, test_env):
        """Reconsolidation clears similar_to when a component no longer has pairs."""
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )

            # First consolidation: circle and pipe are similar
            consolidator._structure = ComponentStructure(
                families={},
                similar_pairs=[
                    SimilarComponentPair(
                        comp1_guid="guid-circle",
                        comp2_guid="guid-pipe",
                        similarity_score=0.8,
                        reason="test",
                    ),
                ],
            )
            consolidator.update_tiered_knowledge()

            # Verify links were set
            circle_note = store.get("comp_circle", track_access=False)
            assert circle_note.type_data.get("similar_to") == ["guid-pipe"]

            # Second consolidation: no similar pairs at all
            consolidator._structure = ComponentStructure(
                families={},
                similar_pairs=[],
            )
            consolidator.update_tiered_knowledge()

        # Verify stale links were cleared
        circle_note = store.get("comp_circle", track_access=False)
        assert circle_note.type_data.get("similar_to") == []

        pipe_note = store.get("comp_pipe", track_access=False)
        assert pipe_note.type_data.get("similar_to") == []

        # Also verify tiered cache was cleared
        with open(test_env["knowledge_path"], "r") as f:
            tiered = json.load(f)
        assert tiered["components"]["guid-circle"].get("similar_to") == []


class TestComponentMetadata:
    def test_structure_includes_stable_key(self, test_env):
        """component_metadata in structure includes name and stable_key."""
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            consolidator.load_components()
            metadata = consolidator._build_component_metadata(consolidator._components)

        assert "guid-circle" in metadata
        assert metadata["guid-circle"]["name"] == "Circle"
        assert metadata["guid-circle"]["stable_key"] == "primitives|curves|circle"

        assert "guid-pipe" in metadata
        assert metadata["guid-pipe"]["stable_key"] == "surface_ops|pipe"

    def test_orphan_has_empty_stable_key(self, test_env):
        """Orphan GUIDs (no UnifiedStore note) get empty stable_key."""
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
            )
            consolidator.load_components()
            metadata = consolidator._build_component_metadata(consolidator._components)

        assert "guid-orphan" in metadata
        assert metadata["guid-orphan"]["stable_key"] == ""
        assert metadata["guid-orphan"]["name"] == "Orphan Component"


class TestQueryByNameAndStableKey:
    @pytest.fixture
    def structure_with_metadata(self, test_env):
        """Write a structure file with component_metadata for query tests."""
        structure = ComponentStructure(
            component_count=3,
            families={
                "primitives": ComponentFamily(
                    name="primitives",
                    description="Primitive components",
                    components=["guid-circle"],
                ),
            },
            similar_pairs=[
                SimilarComponentPair(
                    comp1_guid="guid-circle",
                    comp2_guid="guid-pipe",
                    similarity_score=0.7,
                    reason="Both geometry creators",
                ),
            ],
            component_metadata={
                "guid-circle": {"guid": "guid-circle", "name": "Circle", "stable_key": "primitives|curves|circle"},
                "guid-pipe": {"guid": "guid-pipe", "name": "Pipe", "stable_key": "surface_ops|pipe"},
                "guid-slider": {"guid": "guid-slider", "name": "Number Slider", "stable_key": "input|number_slider"},
            },
        )
        structure.save(test_env["structure_path"])
        return test_env["structure_path"]

    def test_query_by_name(self, test_env, structure_with_metadata):
        result = query_gh_structure(name="Circle", structure_path=structure_with_metadata)
        assert "component" in result
        assert result["component"]["guid"] == "guid-circle"
        assert result["component"]["name"] == "Circle"

    def test_query_by_stable_key(self, test_env, structure_with_metadata):
        result = query_gh_structure(stable_key="surface_ops|pipe", structure_path=structure_with_metadata)
        assert "component" in result
        assert result["component"]["guid"] == "guid-pipe"

    def test_query_by_name_case_insensitive(self, test_env, structure_with_metadata):
        result = query_gh_structure(name="circle", structure_path=structure_with_metadata)
        assert "component" in result
        assert result["component"]["guid"] == "guid-circle"

    def test_query_by_unknown_name_returns_error(self, test_env, structure_with_metadata):
        result = query_gh_structure(name="NonexistentComponent", structure_path=structure_with_metadata)
        assert "error" in result

    def test_similar_components_enriched_with_metadata(self, test_env, structure_with_metadata):
        result = query_gh_structure(guid="guid-circle", structure_path=structure_with_metadata)
        similar = result["component"]["similar_components"]
        assert len(similar) == 1
        assert similar[0]["name"] == "Pipe"
        assert similar[0]["stable_key"] == "surface_ops|pipe"


class TestOrphanModes:
    def test_strict_mode_rejects_orphans(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
                orphan_mode="strict",
            )
            components = consolidator.load_components()

        # Orphan should be rejected
        assert "guid-orphan" not in components
        assert consolidator.unknown_guid_count == 1

    def test_legacy_mode_retains_orphans(self, test_env):
        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=test_env["store"]):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
                orphan_mode="legacy-include",
            )
            components = consolidator.load_components()

        assert "guid-orphan" in components

    def test_repair_mode_creates_notes(self, test_env):
        store = test_env["store"]

        with patch("rook.learning.unified_store.get_unified_store",
                    return_value=store):
            consolidator = GHConsolidator(
                knowledge_path=test_env["knowledge_path"],
                structure_path=test_env["structure_path"],
                observations_path=test_env["observations_path"],
                orphan_mode="repair",
            )
            components = consolidator.load_components()

        # Orphan should be included AND a note created
        assert "guid-orphan" in components

        # Find the repaired note by scanning all notes for our orphan GUID
        repaired_note = None
        for note in store.all():
            if note.note_type == "component":
                td = note.type_data or {}
                if td.get("guid") == "guid-orphan":
                    repaired_note = note
                    break

        assert repaired_note is not None
        assert repaired_note.type_data["guid"] == "guid-orphan"
        assert repaired_note.name == "Orphan Component"
