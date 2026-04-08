"""
Phase 6: Geometric Constraints - Tests

Tests for constraint loading, checking, and warning generation.
"""

import json
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from rook.learning.constraints import (
    Precondition,
    Postcondition,
    ComponentConstraints,
    ConstraintWarning,
    ConstraintChecker,
    get_constraint_checker,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_precondition():
    """A sample precondition."""
    return Precondition(
        type="min_inputs",
        param="C",
        min_count=2,
        description="Loft requires at least 2 curves",
        severity="error",
        fix_suggestion="Add more curves",
    )


@pytest.fixture
def sample_postcondition():
    """A sample postcondition."""
    return Postcondition(
        type="output_exists",
        param="L",
        description="Loft should produce a surface",
    )


@pytest.fixture
def sample_constraints():
    """Sample ComponentConstraints."""
    return ComponentConstraints(
        component_name="Loft",
        category="surface_ops",
        component_guid="abc123",
        preconditions=[
            Precondition(
                type="min_inputs",
                param="C",
                min_count=2,
                description="Loft requires at least 2 curves",
                severity="error",
                fix_suggestion="Add more curves",
            ),
            Precondition(
                type="curve_direction",
                param="C",
                description="Curves should have same direction",
                severity="warning",
                fix_suggestion="Use Flip Curve",
            ),
        ],
        postconditions=[
            Postcondition(
                type="output_exists",
                param="L",
                description="Loft should produce output",
            ),
        ],
    )


@pytest.fixture
def temp_constraints_file():
    """Create a temporary constraints file."""
    data = {
        "version": "1.0",
        "constraints": {
            "TestComponent": {
                "category": "test",
                "component_guid": "test-guid",
                "preconditions": [
                    {
                        "type": "min_inputs",
                        "param": "A",
                        "min_count": 1,
                        "description": "Input A required",
                        "severity": "error",
                        "fix_suggestion": "Add input A",
                    }
                ],
                "postconditions": [
                    {
                        "type": "output_exists",
                        "param": "R",
                        "description": "Output should exist",
                    }
                ],
            },
            "AnotherComponent": {
                "category": "test",
                "preconditions": [
                    {
                        "type": "some_check",
                        "description": "Some warning",
                        "severity": "warning",
                        "fix_suggestion": "Fix it",
                    }
                ],
                "postconditions": [],
            },
            "RelationshipComponent": {
                "category": "test",
                "preconditions": [
                    {
                        "type": "intersection_exists",
                        "params": ["A", "B"],
                        "description": "Objects must intersect",
                        "severity": "warning",
                        "fix_suggestion": "Move objects to overlap",
                    }
                ],
                "postconditions": [],
            },
        },
    }

    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


@pytest.fixture
def temp_constraints_with_aliases():
    """Create a constraints file with aliases."""
    data = {
        "version": "1.1",
        "constraints": {
            "Solid Difference": {
                "category": "solid_ops",
                "aliases": ["Boolean Difference", "BooleanDiff", "SDiff"],
                "preconditions": [
                    {
                        "type": "solid_closed",
                        "param": "A",
                        "description": "First input must be closed",
                        "severity": "error",
                        "fix_suggestion": "Cap holes",
                    }
                ],
                "postconditions": [],
            },
            "Sweep1": {
                "category": "surface_ops",
                "aliases": ["Sweep", "Sweep 1"],
                "preconditions": [
                    {
                        "type": "input_required",
                        "param": "R",
                        "description": "Rail curve required",
                        "severity": "error",
                        "fix_suggestion": "Add rail",
                    }
                ],
                "postconditions": [],
            },
        },
    }

    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        return Path(f.name)


# =============================================================================
# Precondition Tests
# =============================================================================

class TestPrecondition:
    """Tests for Precondition dataclass."""

    def test_basic_precondition(self, sample_precondition):
        """Create basic precondition."""
        assert sample_precondition.type == "min_inputs"
        assert sample_precondition.param == "C"
        assert sample_precondition.min_count == 2
        assert sample_precondition.severity == "error"

    def test_to_dict(self, sample_precondition):
        """to_dict includes all fields."""
        d = sample_precondition.to_dict()
        assert d["type"] == "min_inputs"
        assert d["param"] == "C"
        assert d["min_count"] == 2
        assert d["severity"] == "error"
        assert d["fix_suggestion"] == "Add more curves"

    def test_from_dict(self):
        """from_dict creates precondition."""
        d = {
            "type": "curve_direction",
            "param": "C",
            "description": "Same direction",
            "severity": "warning",
            "fix_suggestion": "Flip curve",
        }
        pre = Precondition.from_dict(d)
        assert pre.type == "curve_direction"
        assert pre.severity == "warning"

    def test_from_dict_defaults(self):
        """from_dict uses defaults for missing fields."""
        d = {
            "type": "test",
            "description": "Test",
        }
        pre = Precondition.from_dict(d)
        assert pre.severity == "warning"  # default
        assert pre.fix_suggestion == ""  # default


# =============================================================================
# Postcondition Tests
# =============================================================================

class TestPostcondition:
    """Tests for Postcondition dataclass."""

    def test_basic_postcondition(self, sample_postcondition):
        """Create basic postcondition."""
        assert sample_postcondition.type == "output_exists"
        assert sample_postcondition.param == "L"

    def test_to_dict(self, sample_postcondition):
        """to_dict includes all fields."""
        d = sample_postcondition.to_dict()
        assert d["type"] == "output_exists"
        assert d["param"] == "L"
        assert "description" in d

    def test_from_dict(self):
        """from_dict creates postcondition."""
        d = {
            "type": "output_valid",
            "param": "R",
            "description": "Valid output",
        }
        post = Postcondition.from_dict(d)
        assert post.type == "output_valid"
        assert post.param == "R"


# =============================================================================
# ComponentConstraints Tests
# =============================================================================

class TestComponentConstraints:
    """Tests for ComponentConstraints dataclass."""

    def test_basic_constraints(self, sample_constraints):
        """Create component constraints."""
        assert sample_constraints.component_name == "Loft"
        assert sample_constraints.category == "surface_ops"
        assert len(sample_constraints.preconditions) == 2
        assert len(sample_constraints.postconditions) == 1

    def test_get_errors(self, sample_constraints):
        """get_errors returns only error severity."""
        errors = sample_constraints.get_errors()
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_get_warnings(self, sample_constraints):
        """get_warnings returns only warning severity."""
        warnings = sample_constraints.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"

    def test_to_dict(self, sample_constraints):
        """to_dict serializes correctly."""
        d = sample_constraints.to_dict()
        assert d["category"] == "surface_ops"
        assert d["component_guid"] == "abc123"
        assert len(d["preconditions"]) == 2
        assert len(d["postconditions"]) == 1

    def test_from_dict(self):
        """from_dict creates constraints."""
        d = {
            "category": "solid_ops",
            "component_guid": "xyz789",
            "preconditions": [
                {"type": "solid_closed", "param": "A", "description": "Closed", "severity": "error", "fix_suggestion": "Cap"}
            ],
            "postconditions": [],
        }
        c = ComponentConstraints.from_dict("BooleanDiff", d)
        assert c.component_name == "BooleanDiff"
        assert c.category == "solid_ops"
        assert len(c.preconditions) == 1


# =============================================================================
# ConstraintWarning Tests
# =============================================================================

class TestConstraintWarning:
    """Tests for ConstraintWarning dataclass."""

    def test_basic_warning(self):
        """Create constraint warning."""
        warning = ConstraintWarning(
            component="Loft",
            constraint_type="curve_direction",
            severity="warning",
            description="Curves should align",
            fix_suggestion="Use Flip Curve",
            param="C",
        )
        assert warning.component == "Loft"
        assert warning.severity == "warning"

    def test_to_dict(self):
        """to_dict for MCP response."""
        warning = ConstraintWarning(
            component="Boolean",
            constraint_type="solid_closed",
            severity="error",
            description="Must be solid",
            fix_suggestion="Cap holes",
        )
        d = warning.to_dict()
        assert d["component"] == "Boolean"
        assert d["type"] == "solid_closed"
        assert d["severity"] == "error"
        assert "param" not in d  # None omitted
        assert "params" not in d  # None omitted

    def test_to_dict_with_params(self):
        """to_dict includes params for relationship constraints."""
        warning = ConstraintWarning(
            component="Solid Difference",
            constraint_type="intersection_exists",
            severity="warning",
            description="Objects should intersect",
            fix_suggestion="Verify overlap",
            params=["A", "B"],
        )
        d = warning.to_dict()
        assert d["component"] == "Solid Difference"
        assert d["type"] == "intersection_exists"
        assert d["params"] == ["A", "B"]
        assert "param" not in d  # None omitted


# =============================================================================
# ConstraintChecker Tests
# =============================================================================

class TestConstraintChecker:
    """Tests for ConstraintChecker class."""

    def test_load_from_file(self, temp_constraints_file):
        """Load constraints from file."""
        checker = ConstraintChecker(temp_constraints_file)
        assert len(checker) == 3
        assert "testcomponent" in checker

    def test_get_constraints(self, temp_constraints_file):
        """Get constraints by name."""
        checker = ConstraintChecker(temp_constraints_file)
        c = checker.get_constraints("TestComponent")
        assert c is not None
        assert c.component_name == "TestComponent"
        assert c.category == "test"

    def test_get_constraints_case_insensitive(self, temp_constraints_file):
        """Name lookup is case-insensitive."""
        checker = ConstraintChecker(temp_constraints_file)
        c1 = checker.get_constraints("testcomponent")
        c2 = checker.get_constraints("TESTCOMPONENT")
        assert c1 is not None
        assert c2 is not None

    def test_get_constraints_not_found(self, temp_constraints_file):
        """Returns None for unknown component."""
        checker = ConstraintChecker(temp_constraints_file)
        assert checker.get_constraints("Unknown") is None

    def test_get_all_constrained_components(self, temp_constraints_file):
        """List all components with constraints."""
        checker = ConstraintChecker(temp_constraints_file)
        names = checker.get_all_constrained_components()
        assert len(names) == 3
        assert "TestComponent" in names
        assert "AnotherComponent" in names
        assert "RelationshipComponent" in names

    def test_get_warnings_for_components(self, temp_constraints_file):
        """Get warnings for component list."""
        checker = ConstraintChecker(temp_constraints_file)
        warnings = checker.get_warnings_for_components(["TestComponent", "AnotherComponent"])
        assert len(warnings) == 2  # 1 error + 1 warning

    def test_get_warnings_includes_params(self, temp_constraints_file):
        """Warnings include params for relationship constraints."""
        checker = ConstraintChecker(temp_constraints_file)
        warnings = checker.get_warnings_for_components(["RelationshipComponent"])
        assert len(warnings) == 1
        assert warnings[0].params == ["A", "B"]
        d = warnings[0].to_dict()
        assert d["params"] == ["A", "B"]

    def test_get_warnings_errors_only(self, temp_constraints_file):
        """Filter to errors only."""
        checker = ConstraintChecker(temp_constraints_file)
        warnings = checker.get_warnings_for_components(
            ["TestComponent", "AnotherComponent"],
            include_warnings=False,
            include_errors=True,
        )
        assert len(warnings) == 1
        assert warnings[0].severity == "error"

    def test_get_warnings_warnings_only(self, temp_constraints_file):
        """Filter to warnings only."""
        checker = ConstraintChecker(temp_constraints_file)
        warnings = checker.get_warnings_for_components(
            ["TestComponent", "AnotherComponent"],
            include_warnings=True,
            include_errors=False,
        )
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"

    def test_check_component_inputs_pass(self, temp_constraints_file):
        """Check inputs that pass constraints."""
        checker = ConstraintChecker(temp_constraints_file)
        violations = checker.check_component_inputs("TestComponent", {"A": 1})
        assert len(violations) == 0

    def test_check_component_inputs_fail(self, temp_constraints_file):
        """Check inputs that fail constraints."""
        checker = ConstraintChecker(temp_constraints_file)
        violations = checker.check_component_inputs("TestComponent", {"A": 0})
        assert len(violations) == 1
        assert "got 0" in violations[0].description

    def test_get_constraint_summary(self, temp_constraints_file):
        """Get summary for component."""
        checker = ConstraintChecker(temp_constraints_file)
        summary = checker.get_constraint_summary("TestComponent")
        assert summary is not None
        assert summary["component"] == "TestComponent"
        assert summary["error_count"] == 1
        assert summary["warning_count"] == 0

    def test_reload(self, temp_constraints_file):
        """Reload constraints from disk."""
        checker = ConstraintChecker(temp_constraints_file)
        assert len(checker) == 3
        count = checker.reload()
        assert count == 3

    def test_missing_file(self, tmp_path):
        """Handle missing file gracefully."""
        checker = ConstraintChecker(tmp_path / "nonexistent.json")
        assert len(checker) == 0

    def test_contains(self, temp_constraints_file):
        """Test __contains__."""
        checker = ConstraintChecker(temp_constraints_file)
        assert "testcomponent" in checker
        assert "unknown" not in checker


# =============================================================================
# Alias Tests
# =============================================================================

class TestConstraintAliases:
    """Tests for component name aliases."""

    def test_lookup_by_alias(self, temp_constraints_with_aliases):
        """Can look up constraints using alias."""
        checker = ConstraintChecker(temp_constraints_with_aliases)

        # Primary name lookup
        c1 = checker.get_constraints("Solid Difference")
        assert c1 is not None
        assert c1.component_name == "Solid Difference"

        # Alias lookup - should return same constraints
        c2 = checker.get_constraints("Boolean Difference")
        assert c2 is not None
        assert c2.component_name == "Solid Difference"  # Returns primary name

        # Another alias
        c3 = checker.get_constraints("BooleanDiff")
        assert c3 is not None
        assert c3.component_name == "Solid Difference"

    def test_alias_case_insensitive(self, temp_constraints_with_aliases):
        """Alias lookup is case-insensitive."""
        checker = ConstraintChecker(temp_constraints_with_aliases)

        c1 = checker.get_constraints("boolean difference")
        c2 = checker.get_constraints("BOOLEAN DIFFERENCE")
        c3 = checker.get_constraints("Boolean Difference")

        assert c1 is not None
        assert c2 is not None
        assert c3 is not None
        assert c1.component_name == c2.component_name == c3.component_name

    def test_sweep_alias(self, temp_constraints_with_aliases):
        """Sweep1 can be looked up as Sweep."""
        checker = ConstraintChecker(temp_constraints_with_aliases)

        c1 = checker.get_constraints("Sweep1")
        c2 = checker.get_constraints("Sweep")
        c3 = checker.get_constraints("Sweep 1")

        assert c1 is not None
        assert c2 is not None
        assert c3 is not None
        assert c1.component_name == "Sweep1"
        assert c2.component_name == "Sweep1"

    def test_warnings_via_alias(self, temp_constraints_with_aliases):
        """Get warnings using alias name."""
        checker = ConstraintChecker(temp_constraints_with_aliases)

        # Using alias should still get warnings
        warnings = checker.get_warnings_for_components(["Boolean Difference"])
        assert len(warnings) == 1
        assert warnings[0].constraint_type == "solid_closed"

    def test_aliases_in_component_constraints(self, temp_constraints_with_aliases):
        """Aliases are stored in ComponentConstraints."""
        checker = ConstraintChecker(temp_constraints_with_aliases)
        c = checker.get_constraints("Solid Difference")
        assert c is not None
        assert "Boolean Difference" in c.aliases
        assert "BooleanDiff" in c.aliases

    def test_to_dict_includes_aliases(self, temp_constraints_with_aliases):
        """to_dict includes aliases field."""
        checker = ConstraintChecker(temp_constraints_with_aliases)
        c = checker.get_constraints("Solid Difference")
        d = c.to_dict()
        assert "aliases" in d
        assert "Boolean Difference" in d["aliases"]


# =============================================================================
# Production Constraints Tests
# =============================================================================

class TestProductionConstraints:
    """Tests using the actual constraints.json file."""

    def test_load_production_constraints(self):
        """Load actual constraints file."""
        checker = get_constraint_checker()
        # Should have loaded some constraints
        assert len(checker) > 0

    def test_loft_constraints(self):
        """Loft has expected constraints."""
        checker = get_constraint_checker()
        loft = checker.get_constraints("Loft")
        if loft:  # Only test if constraints file exists
            assert loft.category == "surface_ops"
            assert len(loft.preconditions) >= 1
            # Should have min_inputs constraint
            min_input_types = [p.type for p in loft.preconditions]
            assert "min_inputs" in min_input_types

    def test_boolean_constraints(self):
        """Boolean operations have solid_closed constraints."""
        checker = get_constraint_checker()
        diff = checker.get_constraints("Solid Difference")
        if diff:
            types = [p.type for p in diff.preconditions]
            assert "solid_closed" in types

    def test_production_aliases(self):
        """Production aliases work correctly."""
        checker = get_constraint_checker()

        # Solid Difference should be accessible via Boolean Difference
        sd = checker.get_constraints("Solid Difference")
        bd = checker.get_constraints("Boolean Difference")
        if sd:
            assert bd is not None
            assert bd.component_name == "Solid Difference"

        # Sweep1 should be accessible via Sweep
        s1 = checker.get_constraints("Sweep1")
        s = checker.get_constraints("Sweep")
        if s1:
            assert s is not None
            assert s.component_name == "Sweep1"

        # Loft should be accessible via Loft Options
        loft = checker.get_constraints("Loft")
        lopt = checker.get_constraints("Loft Options")
        if loft:
            assert lopt is not None
            assert lopt.component_name == "Loft"

    def test_get_warnings_for_intent(self):
        """Get warnings for surface operations."""
        checker = get_constraint_checker()
        if len(checker) > 0:
            warnings = checker.get_warnings_for_components(["Loft", "Extrude"])
            # Should get some warnings
            assert isinstance(warnings, list)


# =============================================================================
# Integration Tests
# =============================================================================

class TestConstraintIntegration:
    """Integration tests for constraint system."""

    def test_full_workflow(self, temp_constraints_file):
        """Full workflow: load -> check -> get warnings."""
        # Load
        checker = ConstraintChecker(temp_constraints_file)
        assert len(checker) > 0

        # Get constraints
        c = checker.get_constraints("TestComponent")
        assert c is not None

        # Check inputs
        violations = checker.check_component_inputs("TestComponent", {"A": 0})
        assert len(violations) == 1

        # Get summary
        summary = checker.get_constraint_summary("TestComponent")
        assert summary["error_count"] == 1

    def test_warning_to_dict_for_mcp(self, temp_constraints_file):
        """Warnings serialize correctly for MCP response."""
        checker = ConstraintChecker(temp_constraints_file)
        warnings = checker.get_warnings_for_components(["TestComponent"])

        # Should be serializable
        for w in warnings:
            d = w.to_dict()
            assert "component" in d
            assert "type" in d
            assert "severity" in d
            assert "description" in d
            assert "fix_suggestion" in d
