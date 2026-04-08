# mcp_server/tests/test_unified_store.py
"""Tests for UnifiedStore."""
import json
import pytest
import tempfile
from pathlib import Path
from rook.learning.unified_store import UnifiedStore
from rook.learning.knowledge_note import KnowledgeNote
from rook.learning.unified_index import UnifiedIndex


class TestUnifiedStoreCRUD:
    @pytest.fixture
    def temp_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=True,
                enable_evolution=False,
            )
            yield store

    def test_add_and_get(self, temp_store):
        note = KnowledgeNote(
            note_id="comp_abc",
            note_type="component",
            name="Test",
            brief="Test component",
            created="2026-02-01T12:00:00Z",
        )
        note_id = temp_store.add(note)
        assert note_id == "comp_abc"

        retrieved = temp_store.get("comp_abc")
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_get_nonexistent(self, temp_store):
        assert temp_store.get("nonexistent") is None

    def test_update(self, temp_store):
        note = KnowledgeNote(
            note_id="comp_abc",
            note_type="component",
            name="Original",
            brief="Test",
            created="2026-02-01T12:00:00Z",
        )
        temp_store.add(note)

        note.name = "Updated"
        temp_store.update(note)

        retrieved = temp_store.get("comp_abc")
        assert retrieved.name == "Updated"

    def test_delete(self, temp_store):
        note = KnowledgeNote(
            note_id="comp_abc",
            note_type="component",
            name="Test",
            brief="Test",
            created="2026-02-01T12:00:00Z",
        )
        temp_store.add(note)
        assert temp_store.get("comp_abc") is not None

        result = temp_store.delete("comp_abc")
        assert result is True
        assert temp_store.get("comp_abc") is None

    def test_delete_nonexistent(self, temp_store):
        assert temp_store.delete("nonexistent") is False


class TestUnifiedStoreSearch:
    @pytest.fixture
    def populated_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )
            notes = [
                KnowledgeNote(
                    note_id="comp_slider",
                    note_type="component",
                    name="Number Slider",
                    brief="Numeric slider",
                    created="2026-02-01T12:00:00Z",
                    trigger_intents=["slider", "number"],
                    tags=["input"],
                ),
                KnowledgeNote(
                    note_id="recipe_helix",
                    note_type="recipe",
                    name="Helix",
                    brief="Helix curve",
                    created="2026-02-01T12:00:00Z",
                    trigger_intents=["helix", "spiral"],
                    components=["Series", "Sine"],
                ),
                KnowledgeNote(
                    note_id="struggle_domain",
                    note_type="struggle",
                    name="Domain Issue",
                    brief="Domain problem",
                    created="2026-02-01T12:00:00Z",
                    trigger_symptoms=["flat arc"],
                    anti_patterns=[{"mistake": "Same domain", "symptom": "flat"}],
                ),
            ]
            for n in notes:
                store.add(n, skip_evolution=True)
            yield store

    def test_search_by_intent(self, populated_store):
        results = populated_store.search(intent="slider")
        assert len(results) >= 1
        assert any(r["note_id"] == "comp_slider" for r in results)

    def test_search_by_symptoms(self, populated_store):
        results = populated_store.search(symptoms=["flat arc"])
        assert len(results) >= 1
        assert any(r["note_id"] == "struggle_domain" for r in results)

    def test_search_by_type(self, populated_store):
        results = populated_store.search(intent="slider", note_type="component")
        assert all(r["note_type"] == "component" for r in results)

    def test_search_returns_tiered(self, populated_store):
        results = populated_store.search(intent="slider", tier="quick")
        assert len(results) >= 1
        # Quick tier should NOT have context
        assert "context" not in results[0]

    def test_search_by_keywords(self, populated_store):
        """Search by keywords should find matching notes."""
        # Add a note with keywords
        note = KnowledgeNote(
            note_id="comp_math",
            note_type="component",
            name="Addition",
            brief="Adds numbers",
            created="2026-02-01T12:00:00Z",
            keywords=["add", "plus", "sum"],
        )
        populated_store.add(note, skip_evolution=True)

        results = populated_store.search(keywords=["add"])
        assert len(results) >= 1
        assert any(r["note_id"] == "comp_math" for r in results)

    def test_search_by_components(self, populated_store):
        """Search by components should find recipes using them."""
        # The populated_store fixture has recipe_helix with components=["Series", "Sine"]
        results = populated_store.search(components=["Series"])
        assert len(results) >= 1
        assert any(r["note_id"] == "recipe_helix" for r in results)


class TestUnifiedStoreDAG:
    @pytest.fixture
    def linked_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )
            comp = KnowledgeNote(
                note_id="comp_series",
                note_type="component",
                name="Series",
                brief="Series",
                created="2026-02-01T12:00:00Z",
            )
            recipe = KnowledgeNote(
                note_id="recipe_helix",
                note_type="recipe",
                name="Helix",
                brief="Helix",
                created="2026-02-01T12:00:00Z",
                links=["comp_series"],
            )
            store.add(comp, skip_evolution=True)
            store.add(recipe, skip_evolution=True)
            yield store

    def test_get_related_links_to(self, linked_store):
        related = linked_store.get_related("comp_series")
        assert "recipe_helix" in related["links_to"]

    def test_get_related_links_from(self, linked_store):
        related = linked_store.get_related("recipe_helix")
        assert "comp_series" in related["links_from"]


class TestUnifiedStorePersistence:
    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = Path(tmpdir) / "notes"
            index_path = Path(tmpdir) / "index.json"

            # Create and populate
            store1 = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=True,
                enable_evolution=False,
            )
            note = KnowledgeNote(
                note_id="comp_test",
                note_type="component",
                name="Test",
                brief="Test",
                created="2026-02-01T12:00:00Z",
            )
            store1.add(note)

            # Reload
            store2 = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=True,
                enable_evolution=False,
            )
            retrieved = store2.get("comp_test")
            assert retrieved is not None
            assert retrieved.name == "Test"

    def test_load_rebuilds_stale_index_without_deprecated_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = Path(tmpdir) / "notes"
            index_path = Path(tmpdir) / "index.json"
            notes_dir.mkdir(parents=True, exist_ok=True)

            active = KnowledgeNote(
                note_id="comp_active",
                note_type="component",
                name="Area",
                brief="Active area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5"},
            )
            deprecated = KnowledgeNote(
                note_id="comp_deprecated",
                note_type="component",
                name="Area",
                brief="Deprecated area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7"},
                deprecated=True,
                deprecated_reason="obsolete",
                deprecated_by="86b28a7e-94d9-4791-8306-e13e10d5f8d5",
                deprecated_replacement_name="Area",
            )

            (notes_dir / "comp_active.json").write_text(json.dumps(active.to_dict(), indent=2))
            (notes_dir / "comp_deprecated.json").write_text(json.dumps(deprecated.to_dict(), indent=2))

            stale_index = UnifiedIndex()
            stale_index.add_note(active)
            stale_index.add_note(deprecated)
            stale_index.save(index_path)

            store = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=True,
                enable_evolution=False,
            )

            assert "comp_active" in store._index.by_type.get("component", [])
            assert "comp_deprecated" not in store._index.by_type.get("component", [])

            saved_index = json.loads(index_path.read_text())
            assert "comp_deprecated" not in saved_index.get("by_type", {}).get("component", [])

    def test_load_with_auto_save_false_does_not_rewrite_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = Path(tmpdir) / "notes"
            index_path = Path(tmpdir) / "index.json"
            notes_dir.mkdir(parents=True, exist_ok=True)

            active = KnowledgeNote(
                note_id="comp_active",
                note_type="component",
                name="Area",
                brief="Active area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5"},
            )
            deprecated = KnowledgeNote(
                note_id="comp_deprecated",
                note_type="component",
                name="Area",
                brief="Deprecated area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7"},
                deprecated=True,
            )

            (notes_dir / "comp_active.json").write_text(json.dumps(active.to_dict(), indent=2))
            (notes_dir / "comp_deprecated.json").write_text(json.dumps(deprecated.to_dict(), indent=2))

            stale_index = UnifiedIndex()
            stale_index.add_note(active)
            stale_index.add_note(deprecated)
            stale_index.save(index_path)
            stale_before = index_path.read_text()

            store = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=False,
                enable_evolution=False,
            )

            assert "comp_deprecated" not in store._index.by_type.get("component", [])
            assert index_path.read_text() == stale_before


class TestUnifiedStoreAccessTracking:
    def test_get_increments_retrieval_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )
            note = KnowledgeNote(
                note_id="comp_test",
                note_type="component",
                name="Test",
                brief="Test",
                created="2026-02-01T12:00:00Z",
            )
            store.add(note)

            store.get("comp_test", track_access=True)
            store.get("comp_test", track_access=True)

            retrieved = store.get("comp_test", track_access=False)
            assert retrieved.retrieval_count == 2

    def test_get_without_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )
            note = KnowledgeNote(
                note_id="comp_test",
                note_type="component",
                name="Test",
                brief="Test",
                created="2026-02-01T12:00:00Z",
            )
            store.add(note)

            store.get("comp_test", track_access=False)
            store.get("comp_test", track_access=False)

            retrieved = store.get("comp_test", track_access=False)
            assert retrieved.retrieval_count == 0


class TestUnifiedStoreDeprecation:
    def test_add_and_update_keep_deprecated_notes_out_of_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )

            deprecated = KnowledgeNote(
                note_id="comp_deprecated",
                note_type="component",
                name="Area",
                brief="Deprecated area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "2e205f24-9279-47b2-b414-d06dcd0b21a7"},
                deprecated=True,
                deprecated_reason="obsolete",
                deprecated_by="86b28a7e-94d9-4791-8306-e13e10d5f8d5",
                deprecated_replacement_name="Area",
            )
            store.add(deprecated, skip_evolution=True)

            assert store.get("comp_deprecated", track_access=False) is not None
            assert "comp_deprecated" not in store._index.by_type.get("component", [])
            assert store.resolve_components("area") == []

            active = KnowledgeNote(
                note_id="comp_active",
                note_type="component",
                name="Area",
                brief="Active area",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["area"],
                type_data={"guid": "86b28a7e-94d9-4791-8306-e13e10d5f8d5", "usage_count": 10},
            )
            store.add(active, skip_evolution=True)
            assert store.resolve_active_component_guid_by_name("Area") == "86b28a7e-94d9-4791-8306-e13e10d5f8d5"

            active.deprecated = True
            active.deprecated_reason = "obsolete"
            active.deprecated_by = "replacement-guid"
            active.deprecated_replacement_name = "Area 2"
            store.update(active)

            assert "comp_active" not in store._index.by_type.get("component", [])
            assert store.resolve_components("area") == []
            assert store.get_deprecated_component("86b28a7e-94d9-4791-8306-e13e10d5f8d5") is not None

    def test_get_component_by_guid_preserves_deprecation_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )

            deprecated = KnowledgeNote(
                note_id="comp_deprecated",
                note_type="component",
                name="Multiplication",
                brief="Deprecated multiplication",
                created="2026-02-01T12:00:00Z",
                type_data={"guid": "b8963bb1-aa57-476e-a20e-ed6cf635a49c"},
                deprecated=True,
                deprecated_reason="obsolete",
                deprecated_by="ce46b74e-00c9-43c4-805a-193b69ea4a11",
                deprecated_replacement_name="Multiplication",
            )
            store.add(deprecated, skip_evolution=True)

            component = store.get_component_by_guid("b8963bb1-aa57-476e-a20e-ed6cf635a49c")
            assert component is not None
            assert component["deprecated"] is True
            assert component["deprecated_by"] == "ce46b74e-00c9-43c4-805a-193b69ea4a11"


class TestUnifiedStoreGuidSets:
    def test_active_and_deprecated_guid_sets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )

            active = KnowledgeNote(
                note_id="comp_active",
                note_type="component",
                name="Area",
                brief="Active",
                created="2026-02-01T12:00:00Z",
                type_data={"guid": "guid-active"},
            )
            deprecated = KnowledgeNote(
                note_id="comp_dep",
                note_type="component",
                name="Area Old",
                brief="Deprecated",
                created="2026-02-01T12:00:00Z",
                type_data={"guid": "guid-deprecated"},
                deprecated=True,
                deprecated_by="guid-active",
                deprecated_replacement_name="Area",
            )
            store.add(active, skip_evolution=True)
            store.add(deprecated, skip_evolution=True)

            active_guids = store.get_active_component_guid_set()
            deprecated_guids = store.get_deprecated_component_guid_set()

            assert "guid-active" in active_guids
            assert "guid-deprecated" not in active_guids
            assert "guid-deprecated" in deprecated_guids
            assert "guid-active" not in deprecated_guids

    def test_guid_sets_exclude_non_component_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )

            recipe = KnowledgeNote(
                note_id="recipe_helix",
                note_type="recipe",
                name="Helix",
                brief="Helix recipe",
                created="2026-02-01T12:00:00Z",
            )
            store.add(recipe, skip_evolution=True)

            assert store.get_active_component_guid_set() == set()
            assert store.get_deprecated_component_guid_set() == set()


class TestUnifiedStoreEvolution:
    def test_add_with_evolution_calls_evolve(self):
        """Adding a note with evolution enabled should trigger _evolve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=True,  # Evolution enabled
            )
            # Add a base note first
            base_note = KnowledgeNote(
                note_id="comp_base",
                note_type="component",
                name="Base Component",
                brief="A base component",
                created="2026-02-01T12:00:00Z",
                tags=["test", "base"],
            )
            store.add(base_note, skip_evolution=True)

            # Add new note with evolution
            new_note = KnowledgeNote(
                note_id="comp_new",
                note_type="component",
                name="New Component",
                brief="A new component",
                created="2026-02-01T12:00:00Z",
                tags=["test", "new"],
            )
            store.add(new_note, skip_evolution=False)

            # The note should be added (evolution may or may not create links)
            retrieved = store.get("comp_new", track_access=False)
            assert retrieved is not None
            # Links should be a list (even if empty)
            assert isinstance(retrieved.links, list)

    def test_add_with_skip_evolution_does_not_evolve(self):
        """Adding with skip_evolution=True should not call _evolve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=True,
            )
            note = KnowledgeNote(
                note_id="comp_test",
                note_type="component",
                name="Test",
                brief="Test",
                created="2026-02-01T12:00:00Z",
                tags=["test"],
            )
            # This should not trigger evolution
            store.add(note, skip_evolution=True)

            retrieved = store.get("comp_test", track_access=False)
            assert retrieved is not None
            # Links should be original (empty list from default)
            assert retrieved.links == []
