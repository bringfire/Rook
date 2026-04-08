"""
Phase 5: Reflection - Tests

Tests for struggle detection, reflection analysis, and draft pattern creation.
"""

import pytest
from datetime import datetime

from rook.learning.gh_session_history import SessionEntry
from rook.learning.reflection import (
    StruggleSequence,
    ReflectionResult,
    DraftPattern,
    detect_struggles,
    build_pattern_from_reflection,
    create_draft_pattern,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def failure_entry():
    """A single failure entry."""
    return SessionEntry(
        entry_id=1,
        timestamp="2026-01-31T10:00:00Z",
        action="gh_connect",
        params={"source": "a", "target": "b"},
        outcome="failure",
        errors=["Connection failed: incompatible types"],
    )


@pytest.fixture
def success_entry():
    """A single success entry."""
    return SessionEntry(
        entry_id=4,
        timestamp="2026-01-31T10:03:00Z",
        action="gh_connect",
        params={"source": "a", "target": "c"},
        outcome="success",
    )


@pytest.fixture
def intent_failure_entry():
    """A failure entry for gh_execute_intent."""
    return SessionEntry(
        entry_id=1,
        timestamp="2026-01-31T10:00:00Z",
        action="gh_execute_intent",
        params={"intent": "create wedge shape"},
        outcome="failure",
        errors=["No components created"],
    )


@pytest.fixture
def intent_success_entry():
    """A success entry for gh_execute_intent."""
    return SessionEntry(
        entry_id=4,
        timestamp="2026-01-31T10:03:00Z",
        action="gh_execute_intent",
        params={"intent": "create wedge shape"},
        outcome="success",
    )


@pytest.fixture
def sample_reflection():
    """A sample ReflectionResult."""
    return ReflectionResult(
        is_hard_won=True,
        hard_won_reason="3 failed attempts before discovering the issue",
        breakthrough="Changed domain scaling to account for arc-length parameterization",
        breakthrough_insight="Circles use arc-length parameterization, not angular",
        is_generalizable=True,
        generalization_scope="Any operation involving concentric circles and domains",
        trigger_intents=["wedge shape", "pie slice", "arc from circles"],
        trigger_symptoms=["microscopic slider changes", "same domain different angles"],
        solution_brief="Scale domain by radius for concentric circles",
        solution_principle="Arc-length parameterization means domain values are absolute, not angular",
        preconditions=["Circles must be concentric", "Circles must be in same plane"],
        postconditions=["Arcs span equal angles", "Arcs suitable for lofting"],
        anti_patterns=[
            {
                "mistake": "Using same domain for both circles",
                "symptom": "Inner and outer arcs span different angles",
                "why_wrong": "Arc-length parameterization means same domain ≠ same angle",
            }
        ],
        recommendation="approve",
        recommendation_reason="Clear breakthrough with generalizable insight",
    )


# =============================================================================
# StruggleSequence Tests
# =============================================================================

class TestStruggleSequence:
    """Tests for StruggleSequence dataclass."""

    def test_basic_struggle(self, failure_entry, success_entry):
        """Create a basic struggle sequence."""
        # Create additional failure entries
        failure2 = SessionEntry(
            entry_id=2,
            timestamp="2026-01-31T10:01:00Z",
            action="gh_connect",
            params={"source": "a", "target": "b2"},
            outcome="failure",
            errors=["Still failing"],
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        assert struggle.failure_count == 2
        assert struggle.duration_entries == 3
        assert struggle.entry_ids == [1, 2, 4]

    def test_requires_at_least_one_failure(self, success_entry):
        """StruggleSequence requires at least one failure."""
        with pytest.raises(ValueError, match="at least one failure"):
            StruggleSequence(
                failures=[],
                success=success_entry,
                common_action="gh_connect",
            )

    def test_get_error_messages(self, failure_entry, success_entry):
        """Extract unique error messages from failures."""
        failure2 = SessionEntry(
            entry_id=2,
            timestamp="2026-01-31T10:01:00Z",
            action="gh_connect",
            params={},
            outcome="failure",
            errors=["Connection failed: incompatible types", "Another error"],
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        errors = struggle.get_error_messages()
        assert "Connection failed: incompatible types" in errors
        assert "Another error" in errors
        assert len(errors) == 2  # Deduplicated

    def test_describe(self, failure_entry, success_entry):
        """describe() returns human-readable string."""
        failure2 = SessionEntry(
            entry_id=2,
            timestamp="2026-01-31T10:01:00Z",
            action="gh_connect",
            params={},
            outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        desc = struggle.describe()
        assert "2 failed attempts" in desc
        assert "gh_connect" in desc
        assert "1-4" in desc


# =============================================================================
# detect_struggles Tests
# =============================================================================

class TestDetectStruggles:
    """Tests for struggle detection algorithm."""

    def test_detect_basic_struggle(self):
        """Detect a simple failure-failure-success pattern."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure", errors=["err1"]),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="failure", errors=["err2"]),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_connect",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)

        assert len(struggles) == 1
        assert struggles[0].failure_count == 2
        assert struggles[0].success.entry_id == 3

    def test_skip_single_failure(self):
        """Skip sequences with only one failure."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)

        assert len(struggles) == 0

    def test_detect_with_min_failures_1(self):
        """Detect with min_failures=1."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=1)

        assert len(struggles) == 1

    def test_detect_multiple_struggles(self):
        """Detect multiple struggle sequences."""
        entries = [
            # First struggle
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_connect",
                        params={}, outcome="success"),
            # Second struggle
            SessionEntry(entry_id=4, timestamp="T4", action="gh_set_value",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=5, timestamp="T5", action="gh_set_value",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=6, timestamp="T6", action="gh_set_value",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)

        assert len(struggles) == 2
        assert struggles[0].common_action == "gh_connect"
        assert struggles[1].common_action == "gh_set_value"

    def test_group_by_intent(self):
        """Group execute_intent entries by intent."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="failure"),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2, group_by_intent=True)

        assert len(struggles) == 1
        assert struggles[0].common_intent == "create sphere"

    def test_different_intents_separate(self):
        """Different intents don't combine."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_execute_intent",
                        params={"intent": "create box"}, outcome="failure"),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_execute_intent",
                        params={"intent": "create box"}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)

        # Only one failure for "create sphere" before switching to "create box"
        # So no struggle detected for sphere, and only 1 failure for box
        assert len(struggles) == 0

    def test_empty_entries(self):
        """Empty entries returns empty list."""
        assert detect_struggles([]) == []

    def test_all_successes(self):
        """All successes returns no struggles."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="success"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="success"),
        ]

        assert detect_struggles(entries) == []

    def test_partial_counts_as_failure(self):
        """Partial outcomes count as failures."""
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="partial"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_connect",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)

        assert len(struggles) == 1


# =============================================================================
# ReflectionResult Tests
# =============================================================================

class TestReflectionResult:
    """Tests for ReflectionResult dataclass."""

    def test_to_dict(self, sample_reflection):
        """to_dict includes all fields."""
        d = sample_reflection.to_dict()

        assert d["is_hard_won"] is True
        assert d["breakthrough"] == "Changed domain scaling to account for arc-length parameterization"
        assert d["is_generalizable"] is True
        assert len(d["trigger_intents"]) == 3
        assert len(d["anti_patterns"]) == 1
        assert d["recommendation"] == "approve"


# =============================================================================
# DraftPattern Tests
# =============================================================================

class TestDraftPattern:
    """Tests for DraftPattern dataclass."""

    def test_create_draft(self, failure_entry, success_entry, sample_reflection):
        """Create a draft pattern."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        pattern = build_pattern_from_reflection(
            "test_session",
            struggle,
            sample_reflection,
        )

        draft = DraftPattern.create(
            session_id="test_session",
            struggle=struggle,
            reflection=sample_reflection,
            pattern=pattern,
        )

        assert draft.draft_id.startswith("draft_")
        assert draft.session_id == "test_session"
        assert draft.from_entries == [1, 2, 4]
        assert draft.pattern.solution_brief == sample_reflection.solution_brief

    def test_to_dict(self, failure_entry, success_entry, sample_reflection):
        """to_dict returns MCP-ready format."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        draft = create_draft_pattern(
            "test_session",
            struggle,
            sample_reflection,
        )

        d = draft.to_dict()

        assert "draft_id" in d
        assert "pattern" in d
        assert "recommendation" in d
        assert d["recommendation"] == "approve"


# =============================================================================
# build_pattern_from_reflection Tests
# =============================================================================

class TestBuildPatternFromReflection:
    """Tests for pattern building from reflection."""

    def test_builds_pattern_with_citations(self, failure_entry, success_entry, sample_reflection):
        """Pattern includes citations to source session."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        pattern = build_pattern_from_reflection(
            "test_session_123",
            struggle,
            sample_reflection,
        )

        assert len(pattern.citations) == 1
        assert pattern.citations[0]["session_id"] == "test_session_123"
        assert pattern.citations[0]["entry_range"] == [1, 4]

    def test_builds_pattern_with_triggers(self, failure_entry, success_entry, sample_reflection):
        """Pattern includes trigger intents and symptoms."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        pattern = build_pattern_from_reflection(
            "test_session",
            struggle,
            sample_reflection,
        )

        assert pattern.trigger_intents == sample_reflection.trigger_intents
        assert pattern.trigger_symptoms == sample_reflection.trigger_symptoms

    def test_builds_pattern_with_anti_patterns(self, failure_entry, success_entry, sample_reflection):
        """Pattern includes anti-patterns from reflection."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        pattern = build_pattern_from_reflection(
            "test_session",
            struggle,
            sample_reflection,
        )

        assert len(pattern.anti_patterns) == 1
        assert pattern.anti_patterns[0]["mistake"] == "Using same domain for both circles"

    def test_initial_confidence(self, failure_entry, success_entry, sample_reflection):
        """Pattern starts with initial confidence values."""
        failure2 = SessionEntry(
            entry_id=2, timestamp="T2", action="gh_connect",
            params={}, outcome="failure",
        )

        struggle = StruggleSequence(
            failures=[failure_entry, failure2],
            success=success_entry,
            common_action="gh_connect",
        )

        pattern = build_pattern_from_reflection(
            "test_session",
            struggle,
            sample_reflection,
        )

        assert pattern.times_used == 1
        assert pattern.times_succeeded == 1
        assert pattern.success_rate() == 1.0


# =============================================================================
# Heuristic Analysis Tests
# =============================================================================

class TestAnalyzeStruggleHeuristic:
    """Tests for heuristic-based struggle analysis."""

    def test_heuristic_analysis_basic(self):
        """Heuristic analysis produces valid ReflectionResult."""
        from rook.learning.reflection import analyze_struggle_heuristic

        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={"source": "a"}, outcome="failure", errors=["Error 1"]),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={"source": "b"}, outcome="failure", errors=["Error 2"]),
        ]
        success = SessionEntry(
            entry_id=3, timestamp="T3", action="gh_connect",
            params={"source": "c"}, outcome="success"
        )

        struggle = StruggleSequence(
            failures=entries,
            success=success,
            common_action="gh_connect",
        )

        result = analyze_struggle_heuristic(struggle)

        assert result.is_hard_won is True  # 2 failures
        assert "2 failures" in result.hard_won_reason
        assert result.recommendation == "review"  # Heuristics always need review

    def test_heuristic_extracts_errors(self):
        """Heuristic analysis uses errors as symptoms."""
        from rook.learning.reflection import analyze_struggle_heuristic

        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_set_value",
                        params={}, outcome="failure", errors=["Value out of range"]),
        ]
        success = SessionEntry(entry_id=2, timestamp="T2", action="gh_set_value",
                              params={}, outcome="success")

        struggle = StruggleSequence(
            failures=entries,
            success=success,
            common_action="gh_set_value",
        )

        result = analyze_struggle_heuristic(struggle)

        assert "Value out of range" in result.trigger_symptoms

    def test_heuristic_generalizable_threshold(self):
        """More failures = more likely generalizable."""
        from rook.learning.reflection import analyze_struggle_heuristic

        # 2 failures - not generalizable
        entries_2 = [
            SessionEntry(entry_id=i, timestamp=f"T{i}", action="gh_test",
                        params={}, outcome="failure")
            for i in range(1, 3)
        ]
        success = SessionEntry(entry_id=3, timestamp="T3", action="gh_test",
                              params={}, outcome="success")
        struggle_2 = StruggleSequence(failures=entries_2, success=success, common_action="gh_test")
        result_2 = analyze_struggle_heuristic(struggle_2)
        assert result_2.is_generalizable is False

        # 3 failures - generalizable
        entries_3 = [
            SessionEntry(entry_id=i, timestamp=f"T{i}", action="gh_test",
                        params={}, outcome="failure")
            for i in range(1, 4)
        ]
        success_3 = SessionEntry(entry_id=4, timestamp="T4", action="gh_test",
                                params={}, outcome="success")
        struggle_3 = StruggleSequence(failures=entries_3, success=success_3, common_action="gh_test")
        result_3 = analyze_struggle_heuristic(struggle_3)
        assert result_3.is_generalizable is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestReflectionIntegration:
    """Integration tests for the full reflection flow."""

    def test_full_flow_detect_to_draft(self):
        """Full flow: detect struggles -> analyze -> create draft."""
        from rook.learning.reflection import (
            detect_struggles,
            analyze_struggle,
            create_draft_pattern,
        )

        # Create a session with a struggle sequence
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="failure",
                        errors=["Component not found"]),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="failure",
                        errors=["Still failing"]),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_execute_intent",
                        params={"intent": "create sphere"}, outcome="success"),
        ]

        # Step 1: Detect struggles
        struggles = detect_struggles(entries, min_failures=2)
        assert len(struggles) == 1

        # Step 2: Analyze (heuristic fallback)
        reflection = analyze_struggle(struggles[0], use_dspy=False)
        assert reflection.is_hard_won is True
        assert reflection.recommendation == "review"

        # Step 3: Create draft
        draft = create_draft_pattern("test_session", struggles[0], reflection)
        assert draft.draft_id.startswith("draft_")
        assert draft.from_entries == [1, 2, 3]
        assert draft.pattern is not None
        assert len(draft.pattern.citations) == 1
        assert draft.pattern.citations[0]["session_id"] == "test_session"

    def test_multiple_struggles_in_session(self):
        """Detect multiple struggles in same session."""
        from rook.learning.reflection import detect_struggles, create_draft_pattern, analyze_struggle

        entries = [
            # First struggle: connect
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_connect",
                        params={}, outcome="success"),
            # Second struggle: set_value
            SessionEntry(entry_id=4, timestamp="T4", action="gh_set_value",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=5, timestamp="T5", action="gh_set_value",
                        params={}, outcome="failure"),
            SessionEntry(entry_id=6, timestamp="T6", action="gh_set_value",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)
        assert len(struggles) == 2

        # Create drafts for each
        drafts = []
        for struggle in struggles:
            reflection = analyze_struggle(struggle, use_dspy=False)
            draft = create_draft_pattern("multi_session", struggle, reflection)
            drafts.append(draft)

        assert len(drafts) == 2
        assert drafts[0].pattern.tags == ["gh_connect"]
        assert drafts[1].pattern.tags == ["gh_set_value"]

    def test_no_struggles_returns_empty(self):
        """No struggles in session returns empty list."""
        from rook.learning.reflection import detect_struggles

        # All successes
        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="success"),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_set_value",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries)
        assert struggles == []

    def test_draft_pattern_has_correct_fields(self):
        """Draft patterns have all required PatternNote fields."""
        from rook.learning.reflection import (
            detect_struggles,
            analyze_struggle,
            create_draft_pattern,
        )

        entries = [
            SessionEntry(entry_id=1, timestamp="T1", action="gh_connect",
                        params={}, outcome="failure", errors=["Error A"]),
            SessionEntry(entry_id=2, timestamp="T2", action="gh_connect",
                        params={}, outcome="failure", errors=["Error B"]),
            SessionEntry(entry_id=3, timestamp="T3", action="gh_connect",
                        params={}, outcome="success"),
        ]

        struggles = detect_struggles(entries, min_failures=2)
        reflection = analyze_struggle(struggles[0], use_dspy=False)
        draft = create_draft_pattern("field_test", struggles[0], reflection)

        pattern = draft.pattern
        # Required PatternNote fields
        assert pattern.pattern_id is not None
        assert pattern.name is not None
        assert pattern.solution_brief is not None
        assert pattern.solution_principle is not None
        assert pattern.trigger_intents is not None
        assert pattern.trigger_symptoms is not None
        assert pattern.preconditions is not None
        assert pattern.postconditions is not None
        assert pattern.anti_patterns is not None
        assert pattern.citations is not None
        assert pattern.tags is not None
        # Confidence fields
        assert pattern.times_used == 1
        assert pattern.times_succeeded == 1
