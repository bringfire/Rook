# mcp_server/tests/test_unified_index.py
"""Tests for UnifiedIndex."""
import pytest
import tempfile
from pathlib import Path
from rook.learning.unified_index import UnifiedIndex
from rook.learning.knowledge_note import KnowledgeNote


class TestUnifiedIndexAddNote:
    def test_add_note_to_all_notes(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z"
        )
        index.add_note(note)
        assert "comp_abc" in index.all_notes
        assert index.note_count == 1

    def test_add_note_indexes_by_type(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="recipe_xyz", note_type="recipe", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z"
        )
        index.add_note(note)
        assert "recipe_xyz" in index.by_type.get("recipe", [])

    def test_add_note_indexes_by_intent(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Number Slider",
            brief="Test", created="2026-02-01T12:00:00Z",
            trigger_intents=["slider", "number input"]
        )
        index.add_note(note)
        assert "comp_abc" in index.by_intent.get("slider", [])
        assert "comp_abc" in index.by_intent.get("number", [])
        assert "comp_abc" in index.by_intent.get("input", [])

    def test_add_note_indexes_by_tag(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z",
            tags=["params", "input"]
        )
        index.add_note(note)
        assert "comp_abc" in index.by_tag.get("params", [])
        assert "comp_abc" in index.by_tag.get("input", [])

    def test_add_note_indexes_by_component(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="recipe_xyz", note_type="recipe", name="Helix",
            brief="Test", created="2026-02-01T12:00:00Z",
            components=["Series", "Sine"]
        )
        index.add_note(note)
        assert "recipe_xyz" in index.by_component.get("series", [])
        assert "recipe_xyz" in index.by_component.get("sine", [])


class TestUnifiedIndexReverseLinks:
    def test_add_note_tracks_reverse_links(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="recipe_xyz", note_type="recipe", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z",
            links=["comp_abc", "comp_def"]
        )
        index.add_note(note)
        assert "recipe_xyz" in index.links_to.get("comp_abc", [])
        assert "recipe_xyz" in index.links_to.get("comp_def", [])

    def test_get_notes_linking_to(self):
        index = UnifiedIndex()
        note1 = KnowledgeNote(
            note_id="recipe_1", note_type="recipe", name="R1",
            brief="Test", created="2026-02-01T12:00:00Z",
            links=["comp_abc"]
        )
        note2 = KnowledgeNote(
            note_id="recipe_2", note_type="recipe", name="R2",
            brief="Test", created="2026-02-01T12:00:00Z",
            links=["comp_abc"]
        )
        index.add_note(note1)
        index.add_note(note2)
        linking = index.get_notes_linking_to("comp_abc")
        assert "recipe_1" in linking
        assert "recipe_2" in linking


class TestUnifiedIndexRemoveNote:
    def test_remove_note_from_all_notes(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z",
            tags=["test"]
        )
        index.add_note(note)
        assert "comp_abc" in index.all_notes

        index.remove_note("comp_abc")
        assert "comp_abc" not in index.all_notes
        assert "comp_abc" not in index.by_type.get("component", [])
        assert "comp_abc" not in index.by_tag.get("test", [])


class TestUnifiedIndexFindCandidates:
    @pytest.fixture
    def populated_index(self):
        index = UnifiedIndex()
        notes = [
            KnowledgeNote(
                note_id="comp_slider", note_type="component", name="Number Slider",
                brief="Slider", created="2026-02-01T12:00:00Z",
                trigger_intents=["slider", "number"], tags=["input"]
            ),
            KnowledgeNote(
                note_id="recipe_helix", note_type="recipe", name="Helix",
                brief="Helix curve", created="2026-02-01T12:00:00Z",
                trigger_intents=["helix", "spiral"], tags=["curve"],
                components=["Series", "Sine"]
            ),
            KnowledgeNote(
                note_id="struggle_domain", note_type="struggle", name="Domain Issue",
                brief="Domain problem", created="2026-02-01T12:00:00Z",
                trigger_symptoms=["flat arc", "zero length"],
                tags=["domain"]
            ),
        ]
        for n in notes:
            index.add_note(n)
        return index

    def test_find_by_intent(self, populated_index):
        results = populated_index.find_candidates(intents=["slider"])
        assert "comp_slider" in results

    def test_find_by_symptom(self, populated_index):
        results = populated_index.find_candidates(symptoms=["flat arc"])
        assert "struggle_domain" in results

    def test_find_by_component(self, populated_index):
        results = populated_index.find_candidates(components=["series"])
        assert "recipe_helix" in results


class TestUnifiedIndexSerialization:
    def test_to_dict(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z", tags=["test"]
        )
        index.add_note(note)
        d = index.to_dict()
        assert "comp_abc" in d["all_notes"]
        assert "comp_abc" in d["by_tag"]["test"]

    def test_from_dict(self):
        data = {
            "all_notes": ["comp_abc"],
            "note_count": 1,
            "by_type": {"component": ["comp_abc"]},
            "by_intent": {},
            "by_symptom": {},
            "by_tag": {"test": ["comp_abc"]},
            "by_keyword": {},
            "by_component": {},
            "by_category": {},
            "links_to": {},
        }
        index = UnifiedIndex.from_dict(data)
        assert "comp_abc" in index.all_notes
        assert index.note_count == 1

    def test_atomic_save(self):
        index = UnifiedIndex()
        note = KnowledgeNote(
            note_id="comp_abc", note_type="component", name="Test",
            brief="Test", created="2026-02-01T12:00:00Z"
        )
        index.add_note(note)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_index.json"
            index.save(path)
            assert path.exists()

            loaded = UnifiedIndex.load(path)
            assert "comp_abc" in loaded.all_notes


class TestUnifiedIndexRebuild:
    def test_rebuild_from_notes(self):
        notes = [
            KnowledgeNote(
                note_id="comp_a", note_type="component", name="A",
                brief="A", created="2026-02-01T12:00:00Z", tags=["tag1"]
            ),
            KnowledgeNote(
                note_id="recipe_b", note_type="recipe", name="B",
                brief="B", created="2026-02-01T12:00:00Z",
                components=["A"], links=["comp_a"]
            ),
        ]
        index = UnifiedIndex()
        rebuilt = index.rebuild_from_notes(notes)

        assert "comp_a" in rebuilt.all_notes
        assert "recipe_b" in rebuilt.all_notes
        assert "recipe_b" in rebuilt.links_to.get("comp_a", [])
        assert rebuilt.note_count == 2


class TestUnifiedIndexFindComponentCandidates:
    def test_strips_punctuation_from_query_terms(self):
        index = UnifiedIndex()
        notes = [
            KnowledgeNote(
                note_id="comp_circle",
                note_type="component",
                name="Circle",
                brief="Circle",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["circle"],
                keywords=["circle", "curves"],
                components=["Circle"],
            ),
            KnowledgeNote(
                note_id="comp_extrude",
                note_type="component",
                name="Extrude",
                brief="Extrude",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["extrude"],
                keywords=["extrude"],
                components=["Extrude"],
            ),
            KnowledgeNote(
                note_id="comp_slider",
                note_type="component",
                name="Number Slider",
                brief="Slider",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["number slider", "slider"],
                keywords=["number slider", "slider"],
                components=["Number Slider"],
            ),
        ]
        for note in notes:
            index.add_note(note)

        results = index.find_component_candidates(
            "create a circle, extrude it with a height slider",
            limit=10,
        )

        assert "comp_circle" in results
        assert "comp_extrude" in results
        assert "comp_slider" in results

    @pytest.mark.parametrize(
        ("intent", "expected_ids"),
        [
            (
                "create a number slider, then construct point.",
                {"comp_number_slider", "comp_construct_point"},
            ),
            (
                "deconstruct brep; line sdl",
                {"comp_deconstruct_brep", "comp_line_sdl"},
            ),
            (
                "construct point: number slider",
                {"comp_number_slider", "comp_construct_point"},
            ),
        ],
    )
    def test_handles_punctuation_with_multiword_components(self, intent, expected_ids):
        index = UnifiedIndex()
        notes = [
            KnowledgeNote(
                note_id="comp_number_slider",
                note_type="component",
                name="Number Slider",
                brief="Slider",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["number slider", "slider"],
                keywords=["number slider", "slider"],
                components=["Number Slider"],
            ),
            KnowledgeNote(
                note_id="comp_construct_point",
                note_type="component",
                name="Construct Point",
                brief="Point",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["construct point", "point"],
                keywords=["construct point", "point"],
                components=["Construct Point"],
            ),
            KnowledgeNote(
                note_id="comp_deconstruct_brep",
                note_type="component",
                name="Deconstruct Brep",
                brief="Brep",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["deconstruct brep", "brep"],
                keywords=["deconstruct brep", "brep"],
                components=["Deconstruct Brep"],
            ),
            KnowledgeNote(
                note_id="comp_line_sdl",
                note_type="component",
                name="Line SDL",
                brief="Line",
                created="2026-02-01T12:00:00Z",
                trigger_intents=["line sdl", "line"],
                keywords=["line sdl", "line"],
                components=["Line SDL"],
            ),
        ]
        for note in notes:
            index.add_note(note)

        results = set(index.find_component_candidates(intent, limit=10))
        assert expected_ids.issubset(results)
