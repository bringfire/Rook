# mcp_server/tests/test_knowledge_note.py
"""Tests for KnowledgeNote dataclass."""
import pytest
from rook.learning.knowledge_note import KnowledgeNote, TierLevel, TIER_TOKEN_ESTIMATES


class TestKnowledgeNoteCreation:
    def test_create_component_note(self):
        note = KnowledgeNote(
            note_id="comp_abc12345",
            note_type="component",
            name="Number Slider",
            brief="Numeric input slider for parameters",
            created="2026-02-01T12:00:00Z",
        )
        assert note.note_id == "comp_abc12345"
        assert note.note_type == "component"
        assert note.name == "Number Slider"

    def test_create_recipe_note(self):
        note = KnowledgeNote(
            note_id="recipe_def67890",
            note_type="recipe",
            name="Helix Pipe",
            brief="Create a helical pipe from sine/cosine curves",
            created="2026-02-01T12:00:00Z",
            components=["Series", "Sine", "Cosine", "Construct Point"],
        )
        assert note.note_type == "recipe"
        assert len(note.components) == 4

    def test_create_struggle_note(self):
        note = KnowledgeNote(
            note_id="struggle_ghi11111",
            note_type="struggle",
            name="Arc Domain Confusion",
            brief="Use different domains for start/end angles",
            created="2026-02-01T12:00:00Z",
            trigger_symptoms=["flat wedge", "zero-length arc"],
        )
        assert note.note_type == "struggle"
        assert len(note.trigger_symptoms) == 2

    def test_default_values(self):
        note = KnowledgeNote(
            note_id="comp_test",
            note_type="component",
            name="Test",
            brief="Test component",
            created="2026-02-01T12:00:00Z",
        )
        assert note.version == "1.0"
        assert note.context == ""
        assert note.keywords == []
        assert note.tags == []
        assert note.links == []
        assert note.times_used == 0
        assert note.retrieval_count == 0
        assert note.created_from == "manual"


class TestKnowledgeNoteTiering:
    @pytest.fixture
    def sample_note(self):
        return KnowledgeNote(
            note_id="comp_abc12345",
            note_type="component",
            name="Number Slider",
            brief="Numeric input slider",
            created="2026-02-01T12:00:00Z",
            context="Grasshopper parameter input",
            keywords=["slider", "number", "input"],
            tags=["params", "input", "numeric"],
            components=["Number Slider"],
            solution_principle="Use for numeric parameter input",
            anti_patterns=[{"mistake": "Wrong range", "symptom": "Values clipped"}],
            trigger_symptoms=["need numeric input"],
        )

    def test_tier_quick(self, sample_note):
        result = sample_note.to_tier("quick")
        assert result["note_id"] == "comp_abc12345"
        assert result["name"] == "Number Slider"
        assert result["brief"] == "Numeric input slider"
        assert len(result["tags"]) <= 3
        assert "context" not in result
        assert "anti_patterns" not in result

    def test_tier_context(self, sample_note):
        result = sample_note.to_tier("context")
        assert result["note_id"] == "comp_abc12345"
        assert result["context"] == "Grasshopper parameter input"
        assert result["keywords"] == ["slider", "number", "input"]
        assert len(result["anti_patterns"]) <= 2

    def test_tier_errors(self, sample_note):
        result = sample_note.to_tier("errors")
        assert result["note_id"] == "comp_abc12345"
        assert result["trigger_symptoms"] == ["need numeric input"]
        assert "anti_patterns" in result
        assert "context" not in result

    def test_tier_raw(self, sample_note):
        result = sample_note.to_tier("raw")
        assert result["note_id"] == "comp_abc12345"
        assert result["version"] == "1.0"
        assert result["created_from"] == "manual"
        assert "type_data" in result

    def test_invalid_tier_raises(self, sample_note):
        with pytest.raises(ValueError, match="Unknown tier"):
            sample_note.to_tier("invalid")


class TestKnowledgeNoteSerialization:
    def test_to_dict(self):
        note = KnowledgeNote(
            note_id="comp_abc12345",
            note_type="component",
            name="Test",
            brief="Test component",
            created="2026-02-01T12:00:00Z",
            type_data={"guid": "abc-123"},
        )
        d = note.to_dict()
        assert d["note_id"] == "comp_abc12345"
        assert d["type_data"]["guid"] == "abc-123"

    def test_from_dict(self):
        data = {
            "note_id": "recipe_xyz",
            "note_type": "recipe",
            "name": "Test Recipe",
            "brief": "A test",
            "created": "2026-02-01T12:00:00Z",
            "components": ["A", "B"],
            "tags": ["test"],
        }
        note = KnowledgeNote.from_dict(data)
        assert note.note_id == "recipe_xyz"
        assert note.components == ["A", "B"]
        assert note.tags == ["test"]

    def test_roundtrip(self):
        original = KnowledgeNote(
            note_id="struggle_test",
            note_type="struggle",
            name="Test Struggle",
            brief="A problem",
            created="2026-02-01T12:00:00Z",
            trigger_symptoms=["symptom1", "symptom2"],
            anti_patterns=[{"mistake": "bad", "symptom": "worse"}],
        )
        restored = KnowledgeNote.from_dict(original.to_dict())
        assert restored.note_id == original.note_id
        assert restored.trigger_symptoms == original.trigger_symptoms
        assert restored.anti_patterns == original.anti_patterns

    def test_roundtrip_preserves_deprecation_fields(self):
        original = KnowledgeNote(
            note_id="comp_deprecated",
            note_type="component",
            name="Area",
            brief="Deprecated area",
            created="2026-02-01T12:00:00Z",
            deprecated=True,
            deprecated_reason="obsolete",
            deprecated_by="86b28a7e-94d9-4791-8306-e13e10d5f8d5",
            deprecated_replacement_name="Area",
        )

        restored = KnowledgeNote.from_dict(original.to_dict())
        assert restored.deprecated is True
        assert restored.deprecated_reason == "obsolete"
        assert restored.deprecated_by == "86b28a7e-94d9-4791-8306-e13e10d5f8d5"
        assert restored.deprecated_replacement_name == "Area"


class TestKnowledgeNoteConfidence:
    def test_success_rate_no_usage(self):
        note = KnowledgeNote(
            note_id="test", note_type="component", name="T", brief="T", created="2026-02-01T12:00:00Z"
        )
        assert note.success_rate() == 0.5  # Neutral prior

    def test_success_rate_with_usage(self):
        note = KnowledgeNote(
            note_id="test", note_type="component", name="T", brief="T", created="2026-02-01T12:00:00Z",
            times_used=10, times_succeeded=8,
        )
        assert note.success_rate() == 0.8
