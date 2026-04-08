"""Tests for KnowledgeEvolution A-MEM implementation."""
import pytest
import tempfile
from pathlib import Path
from rook.learning.unified_store import UnifiedStore
from rook.learning.knowledge_note import KnowledgeNote
from rook.learning.knowledge_evolution import KnowledgeEvolution


class TestFindEvolutionCandidates:
    @pytest.fixture
    def evolution(self):
        return KnowledgeEvolution()

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
                    brief="Numeric slider for parameters",
                    created="2026-02-01T12:00:00Z",
                    tags=["input", "params"],
                    trigger_intents=["slider", "number input"],
                ),
                KnowledgeNote(
                    note_id="comp_panel",
                    note_type="component",
                    name="Panel",
                    brief="Text panel for display",
                    created="2026-02-01T12:00:00Z",
                    tags=["output", "display"],
                    trigger_intents=["panel", "text output"],
                ),
                KnowledgeNote(
                    note_id="recipe_helix",
                    note_type="recipe",
                    name="Helix Pattern",
                    brief="Create helix curves",
                    created="2026-02-01T12:00:00Z",
                    tags=["curve", "params"],
                    components=["Series", "Sine"],
                    trigger_symptoms=["need spiral"],
                ),
            ]
            for n in notes:
                store.add(n, skip_evolution=True)
            yield store

    def test_find_candidates_by_tags(self, evolution, populated_store):
        """Should find notes with overlapping tags."""
        new_note = KnowledgeNote(
            note_id="comp_new",
            note_type="component",
            name="New Component",
            brief="New input component",
            created="2026-02-01T12:00:00Z",
            tags=["input", "params"],
        )
        candidates = evolution.find_evolution_candidates(
            note=new_note,
            store=populated_store,
            limit=5,
        )
        # Should find comp_slider (tags: input, params) and recipe_helix (tags: params)
        assert "comp_slider" in candidates
        assert "comp_new" not in candidates  # Should not include self

    def test_find_candidates_empty_store(self, evolution):
        """Should return empty list when store is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,
            )
            new_note = KnowledgeNote(
                note_id="comp_new",
                note_type="component",
                name="New",
                brief="New component",
                created="2026-02-01T12:00:00Z",
                tags=["test"],
            )
            candidates = evolution.find_evolution_candidates(
                note=new_note,
                store=empty_store,
                limit=5,
            )
            assert candidates == []

    def test_find_candidates_no_matches(self, evolution, populated_store):
        """Should return empty list when no tags/components/symptoms match."""
        new_note = KnowledgeNote(
            note_id="comp_unique",
            note_type="component",
            name="Unique",
            brief="Unique component",
            created="2026-02-01T12:00:00Z",
            tags=["completely_unique_tag_xyz"],
        )
        candidates = evolution.find_evolution_candidates(
            note=new_note,
            store=populated_store,
            limit=5,
        )
        assert candidates == []


class TestDecideLinks:
    @pytest.fixture
    def evolution(self):
        return KnowledgeEvolution()

    def test_decide_links_empty_candidates(self, evolution):
        """Should return empty lists when no candidates."""
        new_note = KnowledgeNote(
            note_id="comp_new",
            note_type="component",
            name="New Component",
            brief="A new component",
            created="2026-02-01T12:00:00Z",
            tags=["test"],
        )
        links, rationales, updated_tags = evolution.decide_links(
            new_note=new_note,
            candidate_notes=[],
        )
        assert links == []
        assert rationales == []
        assert updated_tags == ["test"]  # Original tags preserved

    def test_decide_links_returns_valid_structure(self, evolution):
        """Should return tuple of (links, rationales, updated_tags)."""
        new_note = KnowledgeNote(
            note_id="comp_new",
            note_type="component",
            name="Number Input",
            brief="Numeric input component",
            created="2026-02-01T12:00:00Z",
            tags=["input"],
        )
        candidate = KnowledgeNote(
            note_id="comp_slider",
            note_type="component",
            name="Number Slider",
            brief="Slider for numeric input",
            created="2026-02-01T12:00:00Z",
            tags=["input", "slider"],
        )
        links, rationales, updated_tags = evolution.decide_links(
            new_note=new_note,
            candidate_notes=[candidate],
        )
        # Structure validation
        assert isinstance(links, list)
        assert isinstance(rationales, list)
        assert isinstance(updated_tags, list)
        # Links should only contain valid candidate IDs
        for link_id in links:
            assert link_id in ["comp_slider"]


class TestEvolveNeighbors:
    @pytest.fixture
    def evolution(self):
        return KnowledgeEvolution()

    def test_evolve_neighbors_empty(self, evolution):
        """Should return empty list when no neighbors."""
        new_note = KnowledgeNote(
            note_id="comp_new",
            note_type="component",
            name="New",
            brief="New component",
            created="2026-02-01T12:00:00Z",
        )
        updates = evolution.evolve_neighbors(
            new_note=new_note,
            neighbor_notes=[],
        )
        assert updates == []

    def test_evolve_neighbors_returns_valid_structure(self, evolution):
        """Should return list of update dicts with valid IDs."""
        new_note = KnowledgeNote(
            note_id="comp_new",
            note_type="component",
            name="Advanced Slider",
            brief="Enhanced slider with presets",
            created="2026-02-01T12:00:00Z",
            tags=["input", "advanced"],
            solution_principle="Presets improve workflow",
        )
        neighbor = KnowledgeNote(
            note_id="comp_slider",
            note_type="component",
            name="Number Slider",
            brief="Basic numeric slider",
            created="2026-02-01T12:00:00Z",
            tags=["input"],
            context="Standard input component",
        )
        updates = evolution.evolve_neighbors(
            new_note=new_note,
            neighbor_notes=[neighbor],
        )
        # Structure validation
        assert isinstance(updates, list)
        for update in updates:
            assert "id" in update
            assert update["id"] in ["comp_slider"]  # Only valid neighbor IDs


class TestApplyNeighborUpdates:
    @pytest.fixture
    def evolution(self):
        return KnowledgeEvolution()

    @pytest.fixture
    def sample_notes(self):
        return {
            "comp_slider": KnowledgeNote(
                note_id="comp_slider",
                note_type="component",
                name="Number Slider",
                brief="Numeric slider",
                created="2026-02-01T12:00:00Z",
                tags=["input"],
                solution_principle="Basic input mechanism",
            ),
            "comp_panel": KnowledgeNote(
                note_id="comp_panel",
                note_type="component",
                name="Panel",
                brief="Text display",
                created="2026-02-01T12:00:00Z",
                tags=["output"],
                solution_principle="Basic output mechanism",
            ),
        }

    def test_apply_updates_merges_tags(self, evolution, sample_notes):
        """Should merge new tags without duplicates."""
        updates = [
            {
                "id": "comp_slider",
                "new_tags": ["advanced", "input"],  # "input" already exists
                "context_addition": "",
                "rationale": "Extended classification",
            }
        ]
        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_notes=sample_notes,
            triggering_note_id="comp_new",
        )
        assert "comp_slider" in modified
        slider = sample_notes["comp_slider"]
        assert "advanced" in slider.tags
        assert slider.tags.count("input") == 1  # No duplicates

    def test_apply_updates_appends_context(self, evolution, sample_notes):
        """Should append context addition to solution_principle."""
        updates = [
            {
                "id": "comp_slider",
                "new_tags": [],
                "context_addition": "Can be used with presets",
                "rationale": "New usage pattern discovered",
            }
        ]
        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_notes=sample_notes,
            triggering_note_id="comp_new",
        )
        assert "comp_slider" in modified
        slider = sample_notes["comp_slider"]
        assert "Can be used with presets" in slider.solution_principle

    def test_apply_updates_tracks_evolution_history(self, evolution, sample_notes):
        """Should record evolution metadata."""
        updates = [
            {
                "id": "comp_slider",
                "new_tags": ["enhanced"],
                "context_addition": "",
                "rationale": "Classification expanded",
            }
        ]
        evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_notes=sample_notes,
            triggering_note_id="comp_new",
        )
        slider = sample_notes["comp_slider"]
        assert slider.last_evolved is not None
        assert "comp_new" in slider.evolved_by
        assert len(slider.evolution_history) == 1
        assert "comp_new" in slider.evolution_history[0]["trigger"]

    def test_apply_updates_skips_invalid_ids(self, evolution, sample_notes):
        """Should skip updates for nonexistent notes."""
        updates = [
            {
                "id": "nonexistent",
                "new_tags": ["test"],
                "context_addition": "",
                "rationale": "Test",
            }
        ]
        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_notes=sample_notes,
            triggering_note_id="comp_new",
        )
        assert modified == []


class TestFullEvolution:
    @pytest.fixture
    def populated_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = UnifiedStore(
                notes_dir=Path(tmpdir) / "notes",
                index_path=Path(tmpdir) / "index.json",
                auto_save=False,
                enable_evolution=False,  # We'll test evolution manually
            )
            notes = [
                KnowledgeNote(
                    note_id="comp_slider",
                    note_type="component",
                    name="Number Slider",
                    brief="Numeric slider for input",
                    created="2026-02-01T12:00:00Z",
                    tags=["input", "numeric"],
                    trigger_intents=["slider", "number"],
                ),
                KnowledgeNote(
                    note_id="recipe_params",
                    note_type="recipe",
                    name="Parametric Setup",
                    brief="Standard parametric setup",
                    created="2026-02-01T12:00:00Z",
                    tags=["parametric", "input"],
                    components=["Number Slider", "Panel"],
                ),
            ]
            for n in notes:
                store.add(n, skip_evolution=True)
            yield store

    def test_evolve_creates_links(self, populated_store):
        """Full evolution should create links to related notes."""
        from rook.learning.knowledge_evolution import get_knowledge_evolution

        evolution = get_knowledge_evolution()
        new_note = KnowledgeNote(
            note_id="comp_new_input",
            note_type="component",
            name="Preset Slider",
            brief="Slider with preset values",
            created="2026-02-01T12:00:00Z",
            tags=["input", "presets"],
        )

        # Add without evolution first
        populated_store.add(new_note, skip_evolution=True)

        # Run evolution manually
        modified_neighbors = evolution.evolve(
            note=new_note,
            store=populated_store,
        )

        # Should have found candidates and potentially linked/evolved
        # The note should now have links (if DSPy decided any)
        assert isinstance(new_note.links, list)
        assert isinstance(modified_neighbors, list)


class TestSingleton:
    def test_get_knowledge_evolution_returns_same_instance(self):
        """Should return singleton instance."""
        from rook.learning.knowledge_evolution import (
            get_knowledge_evolution,
            reset_knowledge_evolution,
        )
        reset_knowledge_evolution()

        instance1 = get_knowledge_evolution()
        instance2 = get_knowledge_evolution()
        assert instance1 is instance2