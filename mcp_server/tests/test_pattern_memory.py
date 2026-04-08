"""
Tests for Pattern Memory data classes (Phase 2, Task 1)

Tests:
- PatternNote serialization (to_dict / from_dict)
- PatternNote success_rate calculation
- PatternIndex add/remove operations
- PatternIndex find_candidates scoring
"""

import pytest
from rook.learning.pattern_memory import PatternNote, PatternIndex


# =============================================================================
# PatternNote Tests
# =============================================================================

class TestPatternNoteSerialization:
    """Tests for PatternNote to_dict and from_dict."""

    def test_empty_pattern_roundtrip(self):
        """Empty pattern survives serialization roundtrip."""
        pattern = PatternNote()
        data = pattern.to_dict()
        restored = PatternNote.from_dict(data)

        assert restored.pattern_id == pattern.pattern_id
        assert restored.name == ""
        assert restored.solution_brief == ""
        assert restored.links == []
        assert restored.tags == []

    def test_full_pattern_roundtrip(self):
        """Fully populated pattern survives serialization roundtrip."""
        pattern = PatternNote(
            pattern_id="test123",
            name="Concentric Circle Arcs",
            version="1.1",
            created="2026-01-30T10:00:00",
            solution_brief="Scale domain by radius",
            solution_principle="Circles use arc-length parameterization",
            components_needed=["Circle", "SubCurve", "Domain"],
            trigger_intents=["wedge shape", "pie slice"],
            trigger_symptoms=["microscopic changes", "wrong angles"],
            scope_global=True,
            scope_project_types=["architectural"],
            scope_workflow_types=["parametric"],
            anti_patterns=[
                {"mistake": "Same domain", "symptom": "Different angles", "why_wrong": "Arc-length param"}
            ],
            preconditions=["Circles concentric"],
            postconditions=["Equal angles"],
            verification_test="Set angle to 45deg",
            verification_expected="Both arcs span 45deg",
            citations=[
                {"session_id": "sess_001", "entry_range": [5, 10], "outcome": "success"}
            ],
            times_used=5,
            times_succeeded=4,
            last_used="2026-01-30T12:00:00",
            last_verified="2026-01-30T12:00:00",
            links=["pattern_abc", "pattern_def"],
            tags=["domain-math", "curves"],
            created_from="reflection",
            last_evolved="2026-01-30T11:00:00",
            evolved_by=["pattern_xyz"],
            evolution_history=[
                {"date": "2026-01-30", "trigger": "New pattern", "changes": "Added tag"}
            ],
        )

        data = pattern.to_dict()
        restored = PatternNote.from_dict(data)

        # Core identity
        assert restored.pattern_id == "test123"
        assert restored.name == "Concentric Circle Arcs"
        assert restored.version == "1.1"

        # Solution
        assert restored.solution_brief == "Scale domain by radius"
        assert restored.solution_principle == "Circles use arc-length parameterization"
        assert restored.components_needed == ["Circle", "SubCurve", "Domain"]

        # Triggers
        assert restored.trigger_intents == ["wedge shape", "pie slice"]
        assert restored.trigger_symptoms == ["microscopic changes", "wrong angles"]

        # Scope
        assert restored.scope_global is True
        assert restored.scope_project_types == ["architectural"]

        # Anti-patterns
        assert len(restored.anti_patterns) == 1
        assert restored.anti_patterns[0]["mistake"] == "Same domain"

        # Constraints
        assert restored.preconditions == ["Circles concentric"]
        assert restored.postconditions == ["Equal angles"]

        # Verification
        assert restored.verification_test == "Set angle to 45deg"

        # Citations
        assert len(restored.citations) == 1
        assert restored.citations[0]["session_id"] == "sess_001"

        # Confidence
        assert restored.times_used == 5
        assert restored.times_succeeded == 4

        # Links & tags
        assert restored.links == ["pattern_abc", "pattern_def"]
        assert restored.tags == ["domain-math", "curves"]

        # Evolution
        assert restored.created_from == "reflection"
        assert restored.evolved_by == ["pattern_xyz"]
        assert len(restored.evolution_history) == 1

    def test_missing_nested_fields(self):
        """from_dict handles missing nested fields gracefully."""
        minimal_data = {
            "pattern_id": "min123",
            "name": "Minimal Pattern",
        }

        pattern = PatternNote.from_dict(minimal_data)

        assert pattern.pattern_id == "min123"
        assert pattern.name == "Minimal Pattern"
        assert pattern.solution_brief == ""
        assert pattern.trigger_intents == []
        assert pattern.citations == []
        assert pattern.times_used == 0


class TestPatternNoteSuccessRate:
    """Tests for PatternNote.success_rate()."""

    def test_neutral_prior_when_unused(self):
        """Unused pattern returns 0.5 (neutral prior)."""
        pattern = PatternNote()
        assert pattern.success_rate() == 0.5

    def test_perfect_success_rate(self):
        """All successes returns 1.0."""
        pattern = PatternNote(times_used=10, times_succeeded=10)
        assert pattern.success_rate() == 1.0

    def test_zero_success_rate(self):
        """No successes returns 0.0."""
        pattern = PatternNote(times_used=5, times_succeeded=0)
        assert pattern.success_rate() == 0.0

    def test_partial_success_rate(self):
        """Partial success calculates correctly."""
        pattern = PatternNote(times_used=8, times_succeeded=6)
        assert pattern.success_rate() == 0.75


class TestPatternNoteProperties:
    """Tests for PatternNote convenience properties."""

    def test_learned_from_returns_first_success(self):
        """learned_from returns session_id of first successful citation."""
        pattern = PatternNote(
            citations=[
                {"session_id": "sess_fail", "outcome": "failure"},
                {"session_id": "sess_success", "outcome": "success"},
                {"session_id": "sess_later", "outcome": "success"},
            ]
        )
        assert pattern.learned_from == "sess_success"

    def test_learned_from_none_when_no_citations(self):
        """learned_from returns None when no citations."""
        pattern = PatternNote()
        assert pattern.learned_from is None

    def test_learned_from_none_when_no_success(self):
        """learned_from returns None when no successful citations."""
        pattern = PatternNote(
            citations=[
                {"session_id": "sess_1", "outcome": "failure"},
                {"session_id": "sess_2", "outcome": "partial"},
            ]
        )
        assert pattern.learned_from is None

    def test_is_verified_true_when_set(self):
        """is_verified returns True when last_verified is set."""
        pattern = PatternNote(last_verified="2026-01-30T10:00:00")
        assert pattern.is_verified is True

    def test_is_verified_false_when_none(self):
        """is_verified returns False when last_verified is None."""
        pattern = PatternNote()
        assert pattern.is_verified is False

    def test_citation_count(self):
        """citation_count returns number of citations."""
        pattern = PatternNote(
            citations=[
                {"session_id": "a", "outcome": "success"},
                {"session_id": "b", "outcome": "success"},
            ]
        )
        assert pattern.citation_count == 2

    def test_citation_count_zero(self):
        """citation_count returns 0 when no citations."""
        pattern = PatternNote()
        assert pattern.citation_count == 0


class TestPatternNoteRepr:
    """Tests for PatternNote.__repr__."""

    def test_repr_includes_key_info(self):
        """repr includes id, name, and success rate."""
        pattern = PatternNote(
            pattern_id="abc123",
            name="Test Pattern",
            times_used=4,
            times_succeeded=3,
        )
        repr_str = repr(pattern)

        assert "abc123" in repr_str
        assert "Test Pattern" in repr_str
        assert "0.75" in repr_str


# =============================================================================
# PatternIndex Tests
# =============================================================================

class TestPatternIndexAddRemove:
    """Tests for PatternIndex add_pattern and remove_pattern."""

    def test_add_pattern_indexes_symptoms(self):
        """add_pattern indexes symptoms correctly."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p1",
            trigger_symptoms=["microscopic changes", "wrong angles"],
        )

        index.add_pattern(pattern)

        assert "p1" in index.by_symptom.get("microscopic changes", [])
        assert "p1" in index.by_symptom.get("wrong angles", [])
        assert "p1" in index.all_patterns

    def test_add_pattern_indexes_intents(self):
        """add_pattern indexes intent keywords."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p2",
            trigger_intents=["create wedge shape", "pie slice extraction"],
        )

        index.add_pattern(pattern)

        # Keywords are split and indexed
        assert "p2" in index.by_intent.get("wedge", [])
        assert "p2" in index.by_intent.get("shape", [])
        assert "p2" in index.by_intent.get("slice", [])
        # Short words (<= 2 chars) should be skipped
        assert "p2" not in index.by_intent.get("a", [])

    def test_add_pattern_indexes_tags(self):
        """add_pattern indexes tags."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p3",
            tags=["domain-math", "curves", "parameterization"],
        )

        index.add_pattern(pattern)

        assert "p3" in index.by_tag.get("domain-math", [])
        assert "p3" in index.by_tag.get("curves", [])
        assert "p3" in index.by_tag.get("parameterization", [])

    def test_add_pattern_indexes_components(self):
        """add_pattern indexes components."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p4",
            components_needed=["Circle", "SubCurve", "Domain"],
        )

        index.add_pattern(pattern)

        assert "p4" in index.by_component.get("circle", [])
        assert "p4" in index.by_component.get("subcurve", [])
        assert "p4" in index.by_component.get("domain", [])

    def test_add_pattern_no_duplicates(self):
        """add_pattern doesn't create duplicate entries."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p5",
            trigger_symptoms=["same symptom"],
        )

        # Add twice
        index.add_pattern(pattern)
        index.add_pattern(pattern)

        assert index.by_symptom.get("same symptom", []).count("p5") == 1
        assert index.all_patterns.count("p5") == 1

    def test_remove_pattern_cleans_all_indices(self):
        """remove_pattern removes from all indices."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p6",
            trigger_symptoms=["test symptom"],
            trigger_intents=["test intent"],
            tags=["test-tag"],
            components_needed=["TestComp"],
        )

        index.add_pattern(pattern)
        assert len(index) == 1

        index.remove_pattern("p6")

        assert len(index) == 0
        assert "p6" not in index.by_symptom.get("test symptom", [])
        assert "p6" not in index.all_patterns
        # Empty lists should be cleaned up
        assert "test symptom" not in index.by_symptom

    def test_remove_nonexistent_pattern(self):
        """remove_pattern handles missing pattern gracefully."""
        index = PatternIndex()
        # Should not raise
        index.remove_pattern("nonexistent")
        assert len(index) == 0


class TestPatternIndexFindCandidates:
    """Tests for PatternIndex.find_candidates scoring."""

    @pytest.fixture
    def populated_index(self) -> PatternIndex:
        """Create an index with test patterns."""
        index = PatternIndex()

        # Pattern 1: Matches symptoms and tags
        p1 = PatternNote(
            pattern_id="p1",
            trigger_symptoms=["microscopic changes"],
            tags=["domain-math"],
        )

        # Pattern 2: Matches intents only
        p2 = PatternNote(
            pattern_id="p2",
            trigger_intents=["create wedge shape"],
        )

        # Pattern 3: Matches symptoms and components
        p3 = PatternNote(
            pattern_id="p3",
            trigger_symptoms=["microscopic changes", "wrong angles"],
            components_needed=["Circle"],
        )

        index.add_pattern(p1)
        index.add_pattern(p2)
        index.add_pattern(p3)

        return index

    def test_symptom_matching(self, populated_index: PatternIndex):
        """Symptom matching returns correct patterns."""
        results = populated_index.find_candidates(
            symptoms=["microscopic changes"],
        )

        # Both p1 and p3 have this symptom
        assert "p1" in results
        assert "p3" in results
        assert "p2" not in results

    def test_symptom_weighted_higher(self, populated_index: PatternIndex):
        """Symptoms weighted 2x, so patterns with more symptoms rank higher."""
        results = populated_index.find_candidates(
            symptoms=["microscopic changes", "wrong angles"],
        )

        # p3 has both symptoms (score 4), p1 has one (score 2)
        assert results[0] == "p3"
        assert results[1] == "p1"

    def test_intent_matching(self, populated_index: PatternIndex):
        """Intent keyword matching works."""
        results = populated_index.find_candidates(
            intents=["wedge shape"],
        )

        assert "p2" in results

    def test_combined_scoring(self, populated_index: PatternIndex):
        """Combined criteria scores correctly."""
        results = populated_index.find_candidates(
            symptoms=["microscopic changes"],
            tags=["domain-math"],
        )

        # p1 has symptom (2) + tag (1) = 3
        # p3 has symptom (2) = 2
        assert results[0] == "p1"

    def test_limit_respected(self, populated_index: PatternIndex):
        """limit parameter caps results."""
        results = populated_index.find_candidates(
            symptoms=["microscopic changes"],
            limit=1,
        )

        assert len(results) == 1

    def test_no_matches_returns_empty(self, populated_index: PatternIndex):
        """No matches returns empty list."""
        results = populated_index.find_candidates(
            symptoms=["nonexistent symptom"],
        )

        assert results == []

    def test_empty_criteria_returns_empty(self, populated_index: PatternIndex):
        """No criteria returns empty list (not all patterns)."""
        results = populated_index.find_candidates()
        assert results == []


class TestPatternIndexSerialization:
    """Tests for PatternIndex to_dict and from_dict."""

    def test_index_roundtrip(self):
        """Index survives serialization roundtrip."""
        index = PatternIndex()
        pattern = PatternNote(
            pattern_id="p1",
            trigger_symptoms=["symptom one"],
            trigger_intents=["intent phrase"],
            tags=["tag-a"],
            components_needed=["CompA"],
        )
        index.add_pattern(pattern)

        data = index.to_dict()
        restored = PatternIndex.from_dict(data)

        assert restored.all_patterns == ["p1"]
        assert "symptom one" in restored.by_symptom
        assert "p1" in restored.by_symptom["symptom one"]

    def test_empty_index_roundtrip(self):
        """Empty index survives roundtrip."""
        index = PatternIndex()
        data = index.to_dict()
        restored = PatternIndex.from_dict(data)

        assert len(restored) == 0
        assert restored.all_patterns == []


class TestPatternIndexRepr:
    """Tests for PatternIndex.__repr__ and __len__."""

    def test_len_returns_pattern_count(self):
        """len() returns number of patterns."""
        index = PatternIndex()
        assert len(index) == 0

        index.add_pattern(PatternNote(pattern_id="p1"))
        assert len(index) == 1

        index.add_pattern(PatternNote(pattern_id="p2"))
        assert len(index) == 2

    def test_repr_includes_counts(self):
        """repr includes pattern and index counts."""
        index = PatternIndex()
        index.add_pattern(PatternNote(
            pattern_id="p1",
            trigger_symptoms=["s1", "s2"],
            tags=["t1"],
        ))

        repr_str = repr(index)
        assert "patterns=1" in repr_str
        assert "symptoms=2" in repr_str
        assert "tags=1" in repr_str


# =============================================================================
# Recipe Fields Tests
# =============================================================================

class TestRecipeFields:
    """Tests for recipe-specific PatternNote fields."""

    def test_pattern_type_defaults_to_struggle(self):
        """New patterns default to 'struggle' type for backward compatibility."""
        pattern = PatternNote(name="Test")
        assert pattern.pattern_type == "struggle"

    def test_recipe_pattern_type(self):
        """Can create recipe-type patterns."""
        pattern = PatternNote(
            name="Trigonometric Helix",
            pattern_type="recipe",
            wiring=[{"from": "a", "from_param": "out", "to": "b", "to_param": "R"}],
            input_structure={"sliders": [{"role": "amplitude", "min": 0, "max": 100}]},
            output_type="brep",
            source_definition="Trigometry Pipe.ghx",
        )
        assert pattern.pattern_type == "recipe"
        assert len(pattern.wiring) == 1
        assert pattern.output_type == "brep"

    def test_recipe_roundtrip_serialization(self):
        """Recipe fields survive to_dict/from_dict roundtrip."""
        pattern = PatternNote(
            pattern_id="recipe001",
            name="Test Recipe",
            pattern_type="recipe",
            wiring=[{"from": "slider1", "from_param": "out", "to": "sphere", "to_param": "R"}],
            input_structure={
                "sliders": [{"guid": "slider1", "role": "radius", "min": 0, "max": 50}],
                "panels": []
            },
            output_type="surface",
            source_definition="test.ghx",
        )
        data = pattern.to_dict()
        restored = PatternNote.from_dict(data)

        assert restored.pattern_type == "recipe"
        assert restored.wiring == pattern.wiring
        assert restored.input_structure == pattern.input_structure
        assert restored.output_type == "surface"
        assert restored.source_definition == "test.ghx"

    def test_v2_recipe_roundtrip_serialization(self):
        """V2 recipe with graph field survives to_dict/from_dict roundtrip."""
        pattern = PatternNote(
            pattern_id="recipe_v2",
            name="V2 Graph Recipe",
            pattern_type="recipe",
            schema_version="2.0",
            graph={
                "components": [
                    {"id": "R1", "type": "Hexagonal", "guid": "125dc0e2-41d5-4651-af2d-8a3e0be0a4d8", "pos": [100, 100]},
                    {"id": "R2", "type": "Pipe", "guid": "d4ff5c72-c7e7-4e2f-9e20-8d3a82e8e437", "pos": [400, 100]},
                ],
                "flows": ["R1.O0>R2.I0"],
                "subgraphs": [
                    {"id": "S1", "role": "pattern_source", "nick": "hex_grid", "members": ["R1"], "inputs": [], "outputs": ["R1.O0"]}
                ],
            },
            wiring=[],
            input_structure={},
            output_type="brep",
            source_definition="v2_test.ghx",
        )
        data = pattern.to_dict()
        restored = PatternNote.from_dict(data)

        assert restored.schema_version == "2.0"
        assert restored.graph is not None
        assert len(restored.graph["components"]) == 2
        assert restored.graph["components"][0]["id"] == "R1"
        assert restored.graph["flows"] == ["R1.O0>R2.I0"]
        assert len(restored.graph["subgraphs"]) == 1
        assert restored.graph["subgraphs"][0]["role"] == "pattern_source"

    def test_v2_recipe_graph_not_in_dict_when_none(self):
        """V1 recipe omits graph key from serialized dict when graph is None."""
        pattern = PatternNote(
            pattern_id="recipe_v1",
            name="V1 Recipe",
            pattern_type="recipe",
            schema_version="1.0",
            graph=None,
        )
        data = pattern.to_dict()

        assert "graph" not in data["recipe"]
        assert data["recipe"]["schema_version"] == "1.0"

    def test_v1_defaults_when_no_schema_version_in_data(self):
        """Loading a JSON dict without schema_version defaults to '1.0' and graph=None."""
        data = {
            "pattern_id": "old_recipe",
            "name": "Old Format",
            "recipe": {
                "pattern_type": "recipe",
                "wiring": [],
                "input_structure": {},
                "output_type": "curve",
                "source_definition": "old.ghx",
            },
        }
        restored = PatternNote.from_dict(data)

        assert restored.schema_version == "1.0"
        assert restored.graph is None
