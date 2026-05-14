"""
Phase 4: Planning Flow - Integration Tests

Tests the complete planning flow:
1. gh_execute_intent accepts plan parameter
2. Plans are validated before execution
3. Invalid plans are rejected with clear errors
4. Valid plans are recorded in session history
5. Existing behavior preserved when no plan
"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from rook.learning.plan_validator import ExecutionPlan, validate_plan
from rook.learning.gh_session_history import SessionEntry, GHToolResult, Session


class TestSessionEntryWithPlan:
    """Test SessionEntry plan field."""

    def test_entry_with_plan(self):
        """SessionEntry stores plan correctly."""
        plan = {
            "reasoning": "Test approach",
            "sub_problems": ["step 1", "step 2"],
            "sequence": ["do A", "do B"],
            "success_criteria": "Works correctly",
        }
        entry = SessionEntry(
            entry_id=1,
            timestamp=datetime.utcnow().isoformat() + "Z",
            action="gh_execute_intent",
            params={"intent": "test intent", "plan": plan},
            outcome="success",
            plan=plan,
        )
        assert entry.plan == plan
        assert entry.plan["reasoning"] == "Test approach"

    def test_entry_without_plan(self):
        """SessionEntry works without plan."""
        entry = SessionEntry(
            entry_id=1,
            timestamp=datetime.utcnow().isoformat() + "Z",
            action="gh_connect",
            params={"source": "a", "target": "b"},
            outcome="success",
        )
        assert entry.plan is None

    def test_entry_to_dict_includes_plan(self):
        """to_dict includes plan when present."""
        plan = {
            "reasoning": "R",
            "sub_problems": ["s"],
            "sequence": ["q"],
            "success_criteria": "c",
        }
        entry = SessionEntry(
            entry_id=1,
            timestamp="2026-01-31T10:00:00Z",
            action="gh_execute_intent",
            params={"intent": "test"},
            outcome="success",
            plan=plan,
        )
        d = entry.to_dict()
        assert "plan" in d
        assert d["plan"]["reasoning"] == "R"

    def test_entry_to_dict_excludes_none_plan(self):
        """to_dict excludes plan when None."""
        entry = SessionEntry(
            entry_id=1,
            timestamp="2026-01-31T10:00:00Z",
            action="gh_connect",
            params={},
            outcome="success",
        )
        d = entry.to_dict()
        assert "plan" not in d

    def test_entry_from_dict_with_plan(self):
        """from_dict restores plan."""
        d = {
            "entry_id": 1,
            "timestamp": "2026-01-31T10:00:00Z",
            "action": "gh_execute_intent",
            "params": {"intent": "test"},
            "outcome": "success",
            "plan": {
                "reasoning": "R",
                "sub_problems": ["s"],
                "sequence": ["q"],
                "success_criteria": "c",
            },
        }
        entry = SessionEntry.from_dict(d)
        assert entry.plan is not None
        assert entry.plan["reasoning"] == "R"

    def test_entry_from_dict_without_plan(self):
        """from_dict handles missing plan."""
        d = {
            "entry_id": 1,
            "timestamp": "2026-01-31T10:00:00Z",
            "action": "gh_connect",
            "params": {},
            "outcome": "success",
        }
        entry = SessionEntry.from_dict(d)
        assert entry.plan is None

    def test_partial_metadata_roundtrips_through_session_serialization(self):
        """Session serialization preserves strict partial gh_edit metadata."""
        session = Session(
            session_id="test_session",
            started=datetime.utcnow().isoformat() + "Z",
            document="test.gh",
            document_path="/test/test.gh",
        )
        result = GHToolResult(
            success=False,
            outcome="partial",
            data={
                "partial_success": True,
                "verified": False,
                "verification_note": "Grasshopper edit partially applied.",
            },
            errors=["connect failed"],
        )

        entry = session.add_entry("gh_edit", {"epoch": 7}, result)
        serialized = session.to_dict()
        restored = Session.from_dict(serialized)

        assert entry.metadata == {
            "partial_success": True,
            "verified": False,
            "verification_note": "Grasshopper edit partially applied.",
        }
        restored_entry = restored.entries[0]
        assert restored_entry.metadata["partial_success"] is True
        assert restored_entry.metadata["verified"] is False
        assert restored_entry.metadata["verification_note"] == "Grasshopper edit partially applied."


class TestSessionAddEntryWithPlan:
    """Test Session.add_entry extracts plan from params."""

    def test_add_entry_extracts_plan(self):
        """add_entry extracts plan from params."""
        session = Session(
            session_id="test_session",
            started=datetime.utcnow().isoformat() + "Z",
            document="test.gh",
            document_path="/test/test.gh",
        )

        plan = {
            "reasoning": "Test",
            "sub_problems": ["a"],
            "sequence": ["b"],
            "success_criteria": "c",
        }
        params = {"intent": "test", "plan": plan}
        result = GHToolResult(success=True, outcome="success")

        entry = session.add_entry("gh_execute_intent", params, result)

        assert entry.plan == plan
        assert entry.params["plan"] == plan

    def test_add_entry_no_plan(self):
        """add_entry works without plan in params."""
        session = Session(
            session_id="test_session",
            started=datetime.utcnow().isoformat() + "Z",
            document="test.gh",
            document_path="/test/test.gh",
        )

        params = {"source": "a", "target": "b"}
        result = GHToolResult(success=True, outcome="success")

        entry = session.add_entry("gh_connect", params, result)

        assert entry.plan is None


class TestPlanValidationInContext:
    """Test plan validation in realistic scenarios."""

    def test_complex_plan_valid(self):
        """Complex real-world plan validates correctly."""
        plan = {
            "reasoning": "Need concentric circles with radius-scaled domains for wedge shapes. "
                        "The key insight is that circles use arc-length parameterization.",
            "sub_problems": [
                "Create inner and outer circles with same center",
                "Extract arcs that span the same angle from each circle",
                "Create surface between arcs for tread geometry",
            ],
            "sequence": [
                "Create inner circle with radius from inner_radius slider",
                "Create outer circle with radius from outer_radius slider",
                "Apply radius-scaled domains per concentric_circle_arcs pattern",
                "Use SubCurve to extract arcs",
                "Loft between resulting arcs",
            ],
            "success_criteria": "Wedge-shaped treads that respond to tread_depth slider",
            "patterns_to_apply": ["concentric_circle_arcs"],
            "constraints_checked": [
                "Circles must be concentric (same center point)",
                "Loft requires curves in same direction",
            ],
            "unknowns": [
                "Not sure if Loft or Ruled Surface is better for tread",
            ],
        }

        valid, errors, validated = validate_plan(plan)

        assert valid is True
        assert errors == []
        assert validated is not None
        assert len(validated.sub_problems) == 3
        assert len(validated.sequence) == 5
        assert validated.patterns_to_apply == ["concentric_circle_arcs"]

    def test_minimal_valid_plan(self):
        """Minimal plan with only required fields."""
        plan = {
            "reasoning": "Simple approach",
            "sub_problems": ["do the thing"],
            "sequence": ["step 1"],
            "success_criteria": "done",
        }

        valid, errors, validated = validate_plan(plan)

        assert valid is True
        assert validated.unknowns == []
        assert validated.patterns_to_apply == []

    def test_plan_with_encouraged_unknowns(self):
        """Acknowledging unknowns is valid and encouraged."""
        plan = {
            "reasoning": "Uncertain approach",
            "sub_problems": ["explore"],
            "sequence": ["try"],
            "success_criteria": "learn something",
            "unknowns": [
                "Not sure about best component",
                "May need different wiring",
                "Performance unknown",
            ],
        }

        valid, errors, validated = validate_plan(plan)

        assert valid is True
        assert len(validated.unknowns) == 3


class TestPlanRejectionScenarios:
    """Test that invalid plans are properly rejected."""

    def test_empty_reasoning_rejected(self):
        """Empty reasoning string rejected."""
        plan = {
            "reasoning": "",
            "sub_problems": ["a"],
            "sequence": ["b"],
            "success_criteria": "c",
        }
        valid, errors, _ = validate_plan(plan)
        assert valid is False
        assert any("reasoning" in e for e in errors)

    def test_empty_sequence_rejected(self):
        """Empty sequence list rejected."""
        plan = {
            "reasoning": "R",
            "sub_problems": ["a"],
            "sequence": [],
            "success_criteria": "c",
        }
        valid, errors, _ = validate_plan(plan)
        assert valid is False
        assert any("sequence" in e for e in errors)

    def test_wrong_types_rejected(self):
        """Wrong types in plan fields rejected."""
        plan = {
            "reasoning": 123,  # should be string
            "sub_problems": "not a list",  # should be list
            "sequence": ["ok"],
            "success_criteria": ["not", "string"],  # should be string
        }
        valid, errors, _ = validate_plan(plan)
        assert valid is False
        assert len(errors) >= 3


class TestExecutionPlanMethods:
    """Test ExecutionPlan dataclass methods."""

    def test_summary_format(self):
        """summary() returns readable format."""
        plan = ExecutionPlan(
            reasoning="R",
            sub_problems=["a", "b", "c"],
            sequence=["1", "2"],
            success_criteria="done",
            patterns_to_apply=["p1", "p2"],
        )
        s = plan.summary()
        assert "3 sub-problems" in s
        assert "2 steps" in s
        assert "2 patterns" in s

    def test_to_dict_from_dict_roundtrip(self):
        """Full roundtrip preserves all data."""
        plan = ExecutionPlan(
            reasoning="Full test reasoning",
            sub_problems=["sub1", "sub2"],
            sequence=["seq1", "seq2", "seq3"],
            success_criteria="All tests pass",
            patterns_to_apply=["pattern1"],
            constraints_checked=["constraint1", "constraint2"],
            unknowns=["unknown1"],
        )
        d = plan.to_dict()
        restored = ExecutionPlan.from_dict(d)

        assert restored.reasoning == plan.reasoning
        assert restored.sub_problems == plan.sub_problems
        assert restored.sequence == plan.sequence
        assert restored.success_criteria == plan.success_criteria
        assert restored.patterns_to_apply == plan.patterns_to_apply
        assert restored.constraints_checked == plan.constraints_checked
        assert restored.unknowns == plan.unknowns
