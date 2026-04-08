"""Tests for TypedReflection (P3): ExecutionResult -> structured corrections."""

import pytest
from unittest.mock import MagicMock

from rook.learning.intent_runtime import (
    ExecutionFailure,
    ExecutionResult,
    FailureLayer,
)
from rook.learning.typed_reflection import TypedReflection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_failure_result(
    layer: FailureLayer,
    operation: str = "create_sphere",
    route: str = "direct_api",
    error: str = "Something went wrong",
    recovery: str | None = None,
    plan_summary: dict | None = None,
) -> ExecutionResult:
    """Create a failed ExecutionResult for testing."""
    return ExecutionResult(
        success=False,
        intent="create a sphere",
        route_taken=route,
        time_ms=42.0,
        plan_summary=plan_summary or {"operation": operation, "params": {"center": [0, 0, 0], "radius": 5}},
        failure=ExecutionFailure(
            layer=layer,
            operation=operation,
            attempted_route=route,
            error_detail=error,
            recovery_suggestion=recovery,
        ),
    )


def make_success_result() -> ExecutionResult:
    return ExecutionResult(
        success=True,
        intent="create a sphere",
        route_taken="direct_api",
        created_ids=["guid-1"],
        objects_created=1,
        time_ms=15.0,
        plan_summary={"operation": "create_sphere"},
    )


# ---------------------------------------------------------------------------
# Success reflection
# ---------------------------------------------------------------------------

class TestSuccessReflection:

    def test_success_returns_none(self):
        """Successes are not recorded (per CLAUDE.md: record corrections, not successes)."""
        reflector = TypedReflection()
        result = reflector.reflect(make_success_result())
        assert result is None

    def test_success_does_not_call_recorder(self):
        recorder = MagicMock()
        reflector = TypedReflection(recorder=recorder)
        reflector.reflect(make_success_result())
        recorder.assert_not_called()


# ---------------------------------------------------------------------------
# Failure reflection: each layer produces correct correction shape
# ---------------------------------------------------------------------------

class TestFailureLayerCorrections:

    def test_planning_gap(self):
        result = make_failure_result(
            FailureLayer.PLANNING,
            error="No operation matched intent",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction is not None
        assert correction["type"] == "execution_failure"
        assert correction["layer"] == "planning"
        assert correction["gap_type"] == "unmapped_intent"
        assert "planning_gap" in correction["correction_of"]["category"]

    def test_routing_gap(self):
        result = make_failure_result(
            FailureLayer.ROUTING,
            operation="loft_surface",
            error="No route spec for direct_api execution",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "routing"
        assert correction["gap_type"] == "missing_route"
        assert "loft_surface" in correction["correction_of"]["diagnosis"]

    def test_parameter_synthesis(self):
        result = make_failure_result(
            FailureLayer.PARAMETER_SYNTHESIS,
            error="Missing required parameters: ['radius']",
            recovery="Provide: radius",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "parameter_synthesis"
        assert correction["gap_type"] == "parameter_error"
        assert "radius" in correction["correction_of"]["error"]
        assert correction["recovery"] == "Provide: radius"

    def test_command_execution(self):
        result = make_failure_result(
            FailureLayer.COMMAND_EXECUTION,
            error="Rhino not responding",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "command_execution"
        assert correction["gap_type"] == "execution_error"
        assert "C++ plugin" in correction["correction_of"]["diagnosis"]

    def test_interactive_prompt(self):
        result = make_failure_result(
            FailureLayer.INTERACTIVE_PROMPT,
            operation="command:_-FilletEdge",
            error="Command stalled at prompt: Select edges",
            plan_summary={
                "operation": "command:_-FilletEdge",
                "command": "_-FilletEdge",
                "syntax": "_-FilletEdge _Radius 2",
                "params": {},
            },
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "interactive_prompt"
        assert correction["gap_type"] == "interactive_stall"
        assert "stalled" in correction["correction_of"]["diagnosis"].lower()

    def test_wrong_result(self):
        result = make_failure_result(
            FailureLayer.WRONG_RESULT,
            error="Expected 1 object, got 0",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "wrong_result"
        assert correction["gap_type"] == "wrong_result"
        assert "unexpected" in correction["correction_of"]["diagnosis"].lower()

    def test_timeout(self):
        result = make_failure_result(
            FailureLayer.TIMEOUT,
            error="30s timeout",
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction["layer"] == "timeout"
        assert correction["gap_type"] == "timeout"
        assert "modal" in correction["correction_of"]["diagnosis"].lower()


# ---------------------------------------------------------------------------
# Correction shape: all layers emit compatible knowledge_record() shape
# ---------------------------------------------------------------------------

class TestCorrectionShape:

    @pytest.mark.parametrize("layer", list(FailureLayer))
    def test_all_layers_have_required_fields(self, layer):
        """Every correction must have the fields knowledge_record() expects."""
        result = make_failure_result(layer)
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert correction is not None
        # Required by knowledge_record()
        assert "intent" in correction
        assert isinstance(correction["action"], dict)
        assert "tool" in correction["action"]
        assert isinstance(correction["correction_of"], dict)
        assert "error" in correction["correction_of"]
        # I4: category must be present for downstream antipattern classification
        assert "category" in correction["correction_of"]
        # Metadata
        assert correction["type"] == "execution_failure"
        assert correction["layer"] == layer.value
        assert "time_ms" in correction

    @pytest.mark.parametrize("layer", list(FailureLayer))
    def test_all_layers_have_diagnosis(self, layer):
        """Every correction should include a diagnosis string."""
        result = make_failure_result(layer)
        reflector = TypedReflection()
        correction = reflector.reflect(result)

        assert "diagnosis" in correction["correction_of"]
        assert len(correction["correction_of"]["diagnosis"]) > 0


# ---------------------------------------------------------------------------
# Recorder integration
# ---------------------------------------------------------------------------

class TestRecorderIntegration:

    def test_recorder_called_on_failure(self):
        recorder = MagicMock(return_value={"success": True})
        reflector = TypedReflection(recorder=recorder)

        result = make_failure_result(FailureLayer.COMMAND_EXECUTION)
        correction = reflector.reflect(result)

        recorder.assert_called_once()
        args = recorder.call_args
        assert args[0][0] == "create a sphere"  # intent
        assert args[0][2] == "failure"           # outcome
        assert correction["recorded"] is True

    def test_recorder_not_called_on_success(self):
        recorder = MagicMock()
        reflector = TypedReflection(recorder=recorder)
        reflector.reflect(make_success_result())
        recorder.assert_not_called()

    def test_recorder_exception_handled(self):
        recorder = MagicMock(side_effect=RuntimeError("DB error"))
        reflector = TypedReflection(recorder=recorder)

        result = make_failure_result(FailureLayer.COMMAND_EXECUTION)
        correction = reflector.reflect(result)

        assert correction is not None
        assert correction["recorded"] is False
        assert "DB error" in correction["record_error"]

    def test_recorder_receives_correct_shape(self):
        """Verify the exact arguments passed to knowledge_record()."""
        recorder = MagicMock(return_value={"success": True})
        reflector = TypedReflection(recorder=recorder)

        result = make_failure_result(
            FailureLayer.PARAMETER_SYNTHESIS,
            error="Missing radius",
            recovery="Provide: radius",
        )
        reflector.reflect(result)

        intent, action, outcome, correction_of = recorder.call_args[0]
        assert intent == "create a sphere"
        assert outcome == "failure"
        assert action["tool"] == "rhino_execute_intent"
        assert correction_of["error"] == "Missing radius"
        assert correction_of["category"] == "parameter_synthesis"


# ---------------------------------------------------------------------------
# build_correction (no recording)
# ---------------------------------------------------------------------------

class TestBuildCorrection:

    def test_build_without_recording(self):
        recorder = MagicMock()
        reflector = TypedReflection(recorder=recorder)

        result = make_failure_result(FailureLayer.TIMEOUT)
        correction = reflector.build_correction(result)

        assert correction is not None
        assert correction["layer"] == "timeout"
        recorder.assert_not_called()

    def test_build_returns_none_for_success(self):
        reflector = TypedReflection()
        assert reflector.build_correction(make_success_result()) is None

    def test_build_returns_none_for_no_failure(self):
        result = ExecutionResult(success=False, intent="test")
        reflector = TypedReflection()
        assert reflector.build_correction(result) is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_no_plan_summary(self):
        """Result with empty plan_summary should not crash."""
        result = ExecutionResult(
            success=False,
            intent="test",
            failure=ExecutionFailure(
                layer=FailureLayer.COMMAND_EXECUTION,
                operation="create_sphere",
                attempted_route="direct_api",
                error_detail="Error",
            ),
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)
        assert correction is not None

    def test_no_recovery_suggestion(self):
        result = make_failure_result(
            FailureLayer.COMMAND_EXECUTION,
            recovery=None,
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)
        assert correction["recovery"] is None

    def test_timeout_provides_default_recovery(self):
        """Timeout layer provides a default recovery even if none given."""
        result = make_failure_result(
            FailureLayer.TIMEOUT,
            recovery=None,
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)
        assert correction["recovery"] is not None
        assert "modal" in correction["recovery"].lower()

    def test_route_taken_from_failure_when_missing(self):
        """If route_taken is None, should use failure.attempted_route."""
        result = ExecutionResult(
            success=False,
            intent="test",
            route_taken=None,
            failure=ExecutionFailure(
                layer=FailureLayer.ROUTING,
                operation="loft",
                attempted_route="direct_api",
                error_detail="No route",
            ),
        )
        reflector = TypedReflection()
        correction = reflector.reflect(result)
        assert correction["route_taken"] == "direct_api"
