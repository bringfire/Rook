"""
Tests for Phase 4: Plan Validator

Tests plan validation for gh_execute_intent.
"""

import pytest

from rook.learning.plan_validator import (
    ExecutionPlan,
    PlanValidationError,
    validate_plan,
    validate_plan_or_raise,
)


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_minimal_plan(self):
        """Plan with only required fields."""
        plan = ExecutionPlan(
            reasoning="Test reasoning",
            sub_problems=["step 1"],
            sequence=["do thing"],
            success_criteria="it works",
        )
        assert plan.reasoning == "Test reasoning"
        assert plan.sub_problems == ["step 1"]
        assert plan.sequence == ["do thing"]
        assert plan.success_criteria == "it works"
        assert plan.patterns_to_apply == []
        assert plan.constraints_checked == []
        assert plan.unknowns == []

    def test_full_plan(self):
        """Plan with all fields."""
        plan = ExecutionPlan(
            reasoning="Full test",
            sub_problems=["a", "b"],
            sequence=["1", "2", "3"],
            success_criteria="complete",
            patterns_to_apply=["pattern_1"],
            constraints_checked=["curves same direction"],
            unknowns=["not sure about X"],
        )
        assert len(plan.patterns_to_apply) == 1
        assert len(plan.constraints_checked) == 1
        assert len(plan.unknowns) == 1

    def test_to_dict_minimal(self):
        """to_dict excludes empty optional fields."""
        plan = ExecutionPlan(
            reasoning="Test",
            sub_problems=["a"],
            sequence=["b"],
            success_criteria="c",
        )
        d = plan.to_dict()
        assert "reasoning" in d
        assert "sub_problems" in d
        assert "sequence" in d
        assert "success_criteria" in d
        assert "patterns_to_apply" not in d
        assert "constraints_checked" not in d
        assert "unknowns" not in d

    def test_to_dict_full(self):
        """to_dict includes non-empty optional fields."""
        plan = ExecutionPlan(
            reasoning="Test",
            sub_problems=["a"],
            sequence=["b"],
            success_criteria="c",
            patterns_to_apply=["p1"],
            unknowns=["u1"],
        )
        d = plan.to_dict()
        assert d["patterns_to_apply"] == ["p1"]
        assert d["unknowns"] == ["u1"]
        assert "constraints_checked" not in d

    def test_from_dict_minimal(self):
        """from_dict with only required fields."""
        d = {
            "reasoning": "R",
            "sub_problems": ["S"],
            "sequence": ["Q"],
            "success_criteria": "C",
        }
        plan = ExecutionPlan.from_dict(d)
        assert plan.reasoning == "R"
        assert plan.patterns_to_apply == []

    def test_from_dict_full(self):
        """from_dict with all fields."""
        d = {
            "reasoning": "R",
            "sub_problems": ["S"],
            "sequence": ["Q"],
            "success_criteria": "C",
            "patterns_to_apply": ["P"],
            "constraints_checked": ["CC"],
            "unknowns": ["U"],
        }
        plan = ExecutionPlan.from_dict(d)
        assert plan.patterns_to_apply == ["P"]
        assert plan.constraints_checked == ["CC"]
        assert plan.unknowns == ["U"]

    def test_roundtrip(self):
        """to_dict -> from_dict preserves data."""
        original = ExecutionPlan(
            reasoning="Test roundtrip",
            sub_problems=["a", "b", "c"],
            sequence=["1", "2"],
            success_criteria="done",
            patterns_to_apply=["p1", "p2"],
            unknowns=["maybe this"],
        )
        d = original.to_dict()
        restored = ExecutionPlan.from_dict(d)
        assert restored.reasoning == original.reasoning
        assert restored.sub_problems == original.sub_problems
        assert restored.sequence == original.sequence
        assert restored.success_criteria == original.success_criteria
        assert restored.patterns_to_apply == original.patterns_to_apply
        assert restored.unknowns == original.unknowns

    def test_summary(self):
        """summary() returns brief description."""
        plan = ExecutionPlan(
            reasoning="R",
            sub_problems=["a", "b"],
            sequence=["1", "2", "3"],
            success_criteria="C",
            patterns_to_apply=["p1"],
        )
        s = plan.summary()
        assert "2 sub-problems" in s
        assert "3 steps" in s
        assert "1 patterns" in s


class TestValidatePlan:
    """Tests for validate_plan function."""

    def test_none_is_valid(self):
        """None plan is valid (planning is optional)."""
        valid, errors, plan = validate_plan(None)
        assert valid is True
        assert errors == []
        assert plan is None

    def test_valid_minimal_plan(self):
        """Valid plan with required fields."""
        d = {
            "reasoning": "My approach",
            "sub_problems": ["step 1", "step 2"],
            "sequence": ["do A", "do B"],
            "success_criteria": "Everything works",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is True
        assert errors == []
        assert plan is not None
        assert plan.reasoning == "My approach"

    def test_valid_full_plan(self):
        """Valid plan with all fields."""
        d = {
            "reasoning": "Full plan",
            "sub_problems": ["s1"],
            "sequence": ["q1"],
            "success_criteria": "Done",
            "patterns_to_apply": ["concentric_circle_arcs"],
            "constraints_checked": ["curves same direction"],
            "unknowns": ["not sure about loft vs sweep"],
        }
        valid, errors, plan = validate_plan(d)
        assert valid is True
        assert errors == []
        assert plan.patterns_to_apply == ["concentric_circle_arcs"]

    def test_missing_required_field(self):
        """Missing required field fails."""
        d = {
            "reasoning": "Missing stuff",
            "sub_problems": ["s1"],
            # missing sequence
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("sequence" in e for e in errors)
        assert plan is None

    def test_multiple_missing_fields(self):
        """Multiple missing fields reported."""
        d = {"reasoning": "Only this"}
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert len(errors) >= 3  # sub_problems, sequence, success_criteria

    def test_empty_string_field(self):
        """Empty string for required string field fails."""
        d = {
            "reasoning": "",  # empty
            "sub_problems": ["s1"],
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("reasoning" in e and "empty" in e for e in errors)

    def test_whitespace_only_string(self):
        """Whitespace-only string for required field fails."""
        d = {
            "reasoning": "   ",  # whitespace only
            "sub_problems": ["s1"],
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("reasoning" in e for e in errors)

    def test_empty_list_field(self):
        """Empty list for required list field fails."""
        d = {
            "reasoning": "Test",
            "sub_problems": [],  # empty
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("sub_problems" in e and "empty" in e for e in errors)

    def test_wrong_type_string_as_list(self):
        """String where list expected fails."""
        d = {
            "reasoning": "Test",
            "sub_problems": "not a list",  # wrong type
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("sub_problems" in e and "list" in e for e in errors)

    def test_wrong_type_list_as_string(self):
        """List where string expected fails."""
        d = {
            "reasoning": ["not", "a", "string"],  # wrong type
            "sub_problems": ["s1"],
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("reasoning" in e and "str" in e for e in errors)

    def test_list_with_non_string_items(self):
        """List containing non-strings fails."""
        d = {
            "reasoning": "Test",
            "sub_problems": ["s1", 123, "s3"],  # 123 is not string
            "sequence": ["q1"],
            "success_criteria": "Done",
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("sub_problems[1]" in e for e in errors)

    def test_non_dict_input(self):
        """Non-dict input fails."""
        valid, errors, plan = validate_plan("not a dict")
        assert valid is False
        assert any("object" in e or "dictionary" in e for e in errors)

    def test_optional_field_wrong_type(self):
        """Optional field with wrong type fails."""
        d = {
            "reasoning": "Test",
            "sub_problems": ["s1"],
            "sequence": ["q1"],
            "success_criteria": "Done",
            "patterns_to_apply": "not a list",  # wrong type
        }
        valid, errors, plan = validate_plan(d)
        assert valid is False
        assert any("patterns_to_apply" in e for e in errors)


class TestValidatePlanOrRaise:
    """Tests for validate_plan_or_raise function."""

    def test_none_returns_none(self):
        """None input returns None."""
        result = validate_plan_or_raise(None)
        assert result is None

    def test_valid_returns_plan(self):
        """Valid plan returns ExecutionPlan."""
        d = {
            "reasoning": "R",
            "sub_problems": ["s"],
            "sequence": ["q"],
            "success_criteria": "c",
        }
        result = validate_plan_or_raise(d)
        assert isinstance(result, ExecutionPlan)

    def test_invalid_raises(self):
        """Invalid plan raises PlanValidationError."""
        d = {"reasoning": "incomplete"}
        with pytest.raises(PlanValidationError) as exc_info:
            validate_plan_or_raise(d)
        assert len(exc_info.value.errors) > 0


class TestPlanValidationError:
    """Tests for PlanValidationError exception."""

    def test_error_contains_messages(self):
        """Exception contains error messages."""
        errors = ["error 1", "error 2"]
        exc = PlanValidationError(errors)
        assert exc.errors == errors
        assert "error 1" in str(exc)
        assert "error 2" in str(exc)
