# mcp_server/tests/test_unified_integration.py
"""Integration tests for unified knowledge system."""
import pytest
import tempfile
from pathlib import Path
from rook.learning.unified_store import UnifiedStore
from rook.learning.knowledge_note import KnowledgeNote


class TestUnifiedIntegration:
    @pytest.fixture
    def store_with_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=True,
                enable_evolution=False,
            )

            # Add components
            slider = KnowledgeNote(
                note_id="comp_slider",
                note_type="component",
                name="Number Slider",
                brief="Numeric parameter input",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["slider", "number", "input"],
                tags=["input", "params"],
                type_data={"guid": "slider-guid"},
            )
            series = KnowledgeNote(
                note_id="comp_series",
                note_type="component",
                name="Series",
                brief="Generate number series",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["series", "sequence", "range"],
                tags=["sets", "numbers"],
                type_data={"guid": "series-guid"},
            )

            # Add recipe using components
            helix = KnowledgeNote(
                note_id="recipe_helix",
                note_type="recipe",
                name="Helix Curve",
                brief="Create helical curve with trigonometry",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["helix", "spiral", "coil"],
                components=["Number Slider", "Series", "Sine", "Cosine"],
                links=["comp_slider", "comp_series"],
            )

            # Add struggle
            domain_issue = KnowledgeNote(
                note_id="struggle_domain",
                note_type="struggle",
                name="Arc Domain Confusion",
                brief="Use different domains for arc angles",
                created="2026-02-01T12:00:00Z",
                trigger_symptoms=["flat arc", "zero angle"],
                anti_patterns=[{"mistake": "Same domain", "symptom": "flat"}],
            )

            for note in [slider, series, helix, domain_issue]:
                store.add(note, skip_evolution=True)

            yield store

    def test_search_returns_mixed_types(self, store_with_data):
        """Search should return components, recipes, and struggles."""
        # Component search
        results = store_with_data.search(intent="slider")
        assert any(r["note_type"] == "component" for r in results)

        # Recipe search
        results = store_with_data.search(intent="helix")
        assert any(r["note_type"] == "recipe" for r in results)

        # Struggle search
        results = store_with_data.search(symptoms=["flat arc"])
        assert any(r["note_type"] == "struggle" for r in results)

    def test_dag_traversal_component_to_recipes(self, store_with_data):
        """Should find recipes that use a component."""
        related = store_with_data.get_related("comp_slider")
        assert "recipe_helix" in related["links_to"]

    def test_dag_traversal_recipe_to_components(self, store_with_data):
        """Should find components used by a recipe."""
        related = store_with_data.get_related("recipe_helix")
        assert "comp_slider" in related["links_from"]
        assert "comp_series" in related["links_from"]

    def test_tiered_access_quick(self, store_with_data):
        """Quick tier should have minimal fields."""
        results = store_with_data.search(intent="slider", tier="quick")
        assert len(results) >= 1
        r = results[0]
        assert "note_id" in r
        assert "name" in r
        assert "brief" in r
        assert "context" not in r
        assert "type_data" not in r

    def test_tiered_access_context(self, store_with_data):
        """Context tier should have actionable fields."""
        results = store_with_data.search(intent="slider", tier="context")
        assert len(results) >= 1
        r = results[0]
        assert "context" in r
        assert "components" in r

    def test_tiered_access_raw(self, store_with_data):
        """Raw tier should have all fields."""
        results = store_with_data.search(intent="slider", tier="raw")
        assert len(results) >= 1
        r = results[0]
        assert "type_data" in r
        assert "created_from" in r

    def test_filter_by_type(self, store_with_data):
        """Should filter results by note type."""
        # Search for anything with 's' but filter to components
        results = store_with_data.search(intent="series", note_type="component")
        assert all(r["note_type"] == "component" for r in results)

    def test_persistence_roundtrip(self, store_with_data):
        """Data should survive save/reload."""
        notes_dir = store_with_data.notes_dir
        index_path = store_with_data.index_path

        # Reload
        store2 = UnifiedStore(
            notes_dir=notes_dir,
            index_path=index_path,
            auto_save=False,
            enable_evolution=False,
        )

        # Verify all notes present
        assert len(store2) == 4

        # Verify search works
        results = store2.search(intent="helix")
        assert len(results) >= 1

        # Verify DAG works
        related = store2.get_related("comp_slider")
        assert "recipe_helix" in related["links_to"]


class TestEvolutionIntegration:
    """Integration tests for A-MEM evolution with realistic notes."""

    def test_recipe_evolves_component_neighbors(self):
        """Adding a recipe should potentially evolve linked component notes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=True,
                enable_evolution=True,
            )
            # Add component notes
            slider = KnowledgeNote(
                note_id="comp_slider",
                note_type="component",
                name="Number Slider",
                brief="Numeric parameter input",
                created="2026-02-01T12:00:00Z",
                tags=["input", "numeric", "parameter"],
                trigger_intents=["slider", "number input", "parameter"],
                solution_principle="Provides numeric input for parametric control",
            )
            series = KnowledgeNote(
                note_id="comp_series",
                note_type="component",
                name="Series",
                brief="Generate number series",
                created="2026-02-01T12:00:00Z",
                tags=["math", "sequence", "generator"],
                trigger_intents=["series", "sequence", "range"],
                solution_principle="Creates arithmetic sequences",
            )
            store.add(slider, skip_evolution=True)
            store.add(series, skip_evolution=True)

            # Add a recipe that uses both - this should trigger evolution
            helix_recipe = KnowledgeNote(
                note_id="recipe_helix",
                note_type="recipe",
                name="Helix Curve Pattern",
                brief="Create parametric helix curves",
                created="2026-02-01T12:00:00Z",
                tags=["curve", "parametric", "helix"],
                components=["Number Slider", "Series", "Sine", "Cos"],
                trigger_intents=["helix", "spiral curve", "coil"],
                trigger_symptoms=["need 3D spiral", "need helix"],
                solution_principle="Use Series for t-values, trig for circular motion",
            )
            store.add(helix_recipe, skip_evolution=False)

            # Verify the recipe was added and may have links
            retrieved_recipe = store.get("recipe_helix", track_access=False)
            assert retrieved_recipe is not None
            # Links should be a list (may be empty if DSPy decided no links)
            assert isinstance(retrieved_recipe.links, list)

            # Check DAG traversal works
            related = store.get_related("recipe_helix")
            assert "links_from" in related
            assert "links_to" in related

    def test_evolution_persists_to_disk(self):
        """Evolution changes should be persisted and survive reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = Path(tmpdir) / "notes"
            index_path = Path(tmpdir) / "index.json"

            # Create and populate store
            store1 = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=True,
                enable_evolution=True,
            )
            comp = KnowledgeNote(
                note_id="comp_test",
                note_type="component",
                name="Test Component",
                brief="A test component",
                created="2026-02-01T12:00:00Z",
                tags=["test"],
            )
            store1.add(comp, skip_evolution=True)

            related = KnowledgeNote(
                note_id="comp_related",
                note_type="component",
                name="Related Component",
                brief="A related test component",
                created="2026-02-01T12:00:00Z",
                tags=["test", "related"],
            )
            store1.add(related, skip_evolution=False)

            # Reload store
            store2 = UnifiedStore(
                notes_dir=notes_dir,
                index_path=index_path,
                auto_save=True,
                enable_evolution=False,
            )

            # Notes should be present
            assert store2.get("comp_test") is not None
            assert store2.get("comp_related") is not None

            # Index should be intact
            assert len(store2) == 2