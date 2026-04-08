"""Tests for IntentOrchestrator (P4): end-to-end intent -> legacy result shape."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from rook.learning.intent_runtime import CapabilityRouter
from rook.learning.intent_orchestrator import IntentOrchestrator


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_router():
    CapabilityRouter.reset()
    yield
    CapabilityRouter.reset()


def make_caller(responses: dict[str, dict] | None = None):
    """Create a mock HTTP caller that returns responses keyed by endpoint."""
    default = {"success": True, "data": {"objectIds": ["guid-1"], "objectsCreated": 1}}
    resp_map = responses or {}

    async def caller(endpoint, method="POST", data=None):
        return resp_map.get(endpoint, default)

    return caller


# ---------------------------------------------------------------------------
# Legacy shape contract
# ---------------------------------------------------------------------------

class TestLegacyShape:
    """Verify the result shape matches old CommandExecutionResult.to_dict()."""

    def test_success_has_all_fields(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-abc"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        # All fields from old CommandExecutionResult.to_dict()
        assert "intent" in result
        assert "command" in result
        assert "mode" in result
        assert "success" in result
        assert "objects_created" in result
        assert "error" in result
        assert "reasoning_trace" in result
        assert "time_ms" in result

    def test_success_field_types(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-abc"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert isinstance(result["intent"], str)
        assert isinstance(result["command"], str)
        assert isinstance(result["mode"], str)
        assert isinstance(result["success"], bool)
        assert isinstance(result["objects_created"], int)
        assert isinstance(result["reasoning_trace"], list)
        assert isinstance(result["time_ms"], float)

    def test_success_values(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-abc"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert result["success"] is True
        assert result["objects_created"] == 1
        assert result["error"] is None
        assert result["time_ms"] > 0

    def test_failure_has_error_string(self):
        async def failing_caller(endpoint, method="POST", data=None):
            raise ConnectionError("Rhino not responding")

        orchestrator = IntentOrchestrator(http_caller=failing_caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert result["success"] is False
        assert result["error"] is not None
        assert "not responding" in result["error"]


# ---------------------------------------------------------------------------
# End-to-end flow
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_direct_api_sphere(self):
        """Full pipeline: intent -> plan -> execute -> result."""
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-123"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert result["success"] is True
        assert result["objects_created"] == 1
        assert result["execution_route"] == "direct_api"
        assert "guid-123" in result["created_ids"]

    def test_direct_api_box(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-box"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a box at 0,0,0 10 by 8 by 6"))

        assert result["success"] is True
        assert result["execution_route"] == "direct_api"

    def test_unknown_intent_without_knowledge_store(self):
        """Intent not matched by regex or knowledge store."""
        orchestrator = IntentOrchestrator(http_caller=make_caller())
        result = run(orchestrator.run("loft through these curves"))

        assert result["success"] is False
        assert "error" in result
        assert result["error"] is not None

    def test_reasoning_trace_includes_plan_and_execution(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": [], "objectsCreated": 0},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        trace = result["reasoning_trace"]
        assert len(trace) > 0
        # Should include execution trace from SmartExecutor
        assert any("Direct API" in t or "direct" in t.lower() for t in trace)


# ---------------------------------------------------------------------------
# Reflection integration
# ---------------------------------------------------------------------------

class TestReflection:

    def test_recorder_called_on_failure(self):
        recorder = MagicMock(return_value={"success": True})

        async def failing_caller(endpoint, method="POST", data=None):
            raise ConnectionError("Connection refused")

        orchestrator = IntentOrchestrator(
            http_caller=failing_caller,
            recorder=recorder,
        )
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert result["success"] is False
        recorder.assert_called_once()

    def test_recorder_not_called_on_success(self):
        recorder = MagicMock()
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["g"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller, recorder=recorder)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        assert result["success"] is True
        recorder.assert_not_called()

    def test_recorder_failure_does_not_crash_pipeline(self):
        recorder = MagicMock(side_effect=RuntimeError("DB down"))

        async def failing_caller(endpoint, method="POST", data=None):
            raise ConnectionError("Connection refused")

        orchestrator = IntentOrchestrator(
            http_caller=failing_caller,
            recorder=recorder,
        )
        # Should not raise despite recorder failure
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))
        assert result["success"] is False


# ---------------------------------------------------------------------------
# run_typed API
# ---------------------------------------------------------------------------

class TestRunTyped:

    def test_returns_execution_result(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-1"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run_typed("create a sphere at 0,0,0 with radius 5"))

        from rook.learning.intent_runtime import ExecutionResult
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.created_ids == ["guid-1"]


# ---------------------------------------------------------------------------
# Backward compatibility guarantees
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_result_can_be_wrapped_in_mcp_response(self):
        """The MCP handler wraps in {"success": ..., "data": result}.

        Verify the result is JSON-serializable and has the right fields.
        """
        import json

        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-1"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))

        mcp_response = {"success": result["success"], "data": result}
        # Must be JSON-serializable
        serialized = json.dumps(mcp_response)
        deserialized = json.loads(serialized)
        assert deserialized["data"]["success"] is True

    def test_mode_defaults_to_default(self):
        """Direct API plans don't have a mode, but legacy shape requires it."""
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": [], "objectsCreated": 0},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))
        assert result["mode"] == "default"

    def test_command_field_populated_for_direct_api(self):
        """Direct API plans should populate command from operation name."""
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": [], "objectsCreated": 0},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5"))
        assert result["command"] != ""

    def test_internal_error_returns_legacy_shape(self):
        """I1: Internal errors must return dict, not propagate exception."""
        from unittest.mock import patch

        caller = make_caller()
        orchestrator = IntentOrchestrator(http_caller=caller)

        # Force an internal error by breaking the planner
        with patch.object(orchestrator._planner, "plan", side_effect=RuntimeError("bug")):
            result = run(orchestrator.run("create a sphere"))

        # Must still return legacy-shape dict
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "bug" in result["error"]
        assert result["objects_created"] == 0
        assert result["mode"] == "default"
        assert result["time_ms"] > 0


# ---------------------------------------------------------------------------
# run_typed trace merging
# ---------------------------------------------------------------------------

class TestRunTypedTrace:

    def test_run_typed_includes_planner_trace(self):
        """I4: run_typed must include planner's reasoning trace."""
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["g"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run_typed("create a sphere at 0,0,0 with radius 5"))

        # The trace should include entries from both planner and executor
        assert len(result.reasoning_trace) > 0


# ---------------------------------------------------------------------------
# Geometry context threading (M1)
# ---------------------------------------------------------------------------

class TestGeometryContext:

    def test_context_threaded_to_planner(self):
        """M1: run() passes context to planner, enabling ID injection."""
        caller = make_caller({
            "/transform": {
                "success": True,
                "data": {"objectIds": ["guid-a"], "objectsCreated": 0},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        ctx = {"selected_ids": ["guid-a", "guid-b"]}
        result = run(orchestrator.run("move by 10, 0, 0", context=ctx))

        assert result["success"] is True
        # The trace should show that selected objects were used
        assert any("selected" in t.lower() for t in result["reasoning_trace"])

    def test_run_typed_with_context(self):
        """M1: run_typed() also accepts context."""
        caller = make_caller({
            "/transform": {
                "success": True,
                "data": {"objectIds": [], "objectsCreated": 0},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        ctx = {"selected_ids": ["guid-1"]}
        result = run(orchestrator.run_typed("move by 5, 0, 0", context=ctx))

        from rook.learning.intent_runtime import ExecutionResult
        assert isinstance(result, ExecutionResult)

    def test_none_context_is_safe(self):
        """M1: None context should work (backward compatible)."""
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["g"], "objectsCreated": 1},
            },
        })
        orchestrator = IntentOrchestrator(http_caller=caller)
        result = run(orchestrator.run("create a sphere at 0,0,0 with radius 5", context=None))
        assert result["success"] is True
