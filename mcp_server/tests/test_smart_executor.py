"""Tests for SmartExecutor (P2): ExecutionPlan -> ExecutionResult."""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rook.learning.intent_runtime import (
    CapabilityRouter,
    ExecutionPlan,
    ExecutionResult,
    FailureLayer,
    RouteSpec,
)
from rook.learning.smart_executor import SmartExecutor, _tokenize_syntax


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_router():
    CapabilityRouter.reset()
    yield
    CapabilityRouter.reset()


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """I4: Eliminate asyncio.sleep in _poll_prompt so tests run instantly."""
    monkeypatch.setattr("rook.learning.smart_executor.asyncio.sleep", AsyncMock())


def make_caller(responses: dict[str, dict] | None = None):
    """Create a mock HTTP caller that returns responses keyed by endpoint."""
    default = {"success": True, "data": {"objectIds": ["guid-1"], "objectsCreated": 1}}
    resp_map = responses or {}

    async def caller(endpoint, method="POST", data=None):
        return resp_map.get(endpoint, default)

    return caller


class FakeCommandKnowledgeStore:
    def __init__(self, *, safe=True):
        self.safe = safe

    def parse_command_string(self, _command_text):
        return {
            "command": "_-Loft",
            "mode": "default",
            "syntax": "_-Loft _SelID <curve1> _SelID <curve2> _Enter",
            "parameters": {"curve1": "a", "curve2": "b"},
            "options_used": ["_SelID", "_Enter"],
            "raw_values": [],
        }

    def get_command(self, _command):
        preconditions = {"safe_non_interactive": True} if self.safe else {}
        return SimpleNamespace(
            preconditions=preconditions,
            options={
                "_Radius": "Set radius",
                "_SelID": "Select by id",
                "_Enter": "Finish command",
            },
            modes={
                "default": SimpleNamespace(
                    syntax="_-Loft _SelID <curve1> _SelID <curve2> _Enter"
                )
            },
        )


def safe_command_store():
    return FakeCommandKnowledgeStore(safe=True)


# ---------------------------------------------------------------------------
# Direct API execution
# ---------------------------------------------------------------------------

class TestDirectApiExecution:

    def test_success(self):
        caller = make_caller({
            "/create": {
                "success": True,
                "data": {"objectIds": ["guid-abc"], "objectsCreated": 1},
            },
        })
        executor = SmartExecutor(http_caller=caller)

        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))

        assert result.success is True
        assert result.route_taken == "direct_api"
        assert "guid-abc" in result.created_ids
        assert result.objects_created == 1
        assert result.failure is None

    def test_missing_params_fails(self):
        executor = SmartExecutor(http_caller=make_caller())
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0]},  # missing radius
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure is not None
        assert result.failure.layer == FailureLayer.PARAMETER_SYNTHESIS
        assert "radius" in result.failure.error_detail

    def test_http_error(self):
        async def failing_caller(endpoint, method="POST", data=None):
            raise ConnectionError("Rhino not responding")

        executor = SmartExecutor(http_caller=failing_caller)
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.COMMAND_EXECUTION
        assert "not responding" in result.failure.error_detail

    def test_no_route_spec(self):
        executor = SmartExecutor(http_caller=make_caller())
        plan = ExecutionPlan(
            intent="unknown",
            operation="nonexistent_op",
            execution_route="direct_api",
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.ROUTING

    def test_server_returns_failure(self):
        caller = make_caller({
            "/create": {"success": False, "data": {"error": "Invalid radius"}},
        })
        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": -1},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert "Invalid radius" in result.failure.error_detail

    def test_timeout_detection(self):
        caller = make_caller({
            "/create": {"success": False, "data": "Request timed out"},
        })
        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.TIMEOUT


# ---------------------------------------------------------------------------
# Known command execution
# ---------------------------------------------------------------------------

class TestKnownCommandExecution:

    def test_success(self):
        caller = make_caller({
            "/command": {
                "success": True,
                "data": {"objectIds": ["guid-1"], "objectsCreated": 1},
            },
        })
        executor = SmartExecutor(
            http_caller=caller,
            command_knowledge_store=safe_command_store(),
        )
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="known_command",
            command="_-Loft",
            syntax="_-Loft _SelID a _SelID b _Enter",
            fallbacks=[],
        )
        result = run(executor.execute(plan))

        assert result.success is True
        assert result.route_taken == "known_command"

    def test_no_syntax_fails(self):
        executor = SmartExecutor(http_caller=make_caller())
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="known_command",
            command="_-Loft",
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.PARAMETER_SYNTHESIS

    def test_stalled_command_reports_interactive_prompt(self):
        """Command that stalls at a prompt, no interactive fallback."""
        caller = make_caller({
            "/command": {
                "success": False,
                "data": {"waitingFor": "Select objects to fillet"},
            },
        })
        executor = SmartExecutor(
            http_caller=caller,
            command_knowledge_store=safe_command_store(),
        )
        plan = ExecutionPlan(
            intent="fillet edges",
            operation="command:_-FilletEdge",
            execution_route="known_command",
            command="_-FilletEdge",
            syntax="_-FilletEdge _Radius 2",
            fallbacks=[],  # No interactive fallback
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.INTERACTIVE_PROMPT
        assert "Select objects to fillet" in result.failure.error_detail

    def test_stalled_command_with_interactive_fallback_fails_without_prompt_driving(self):
        """Interactive fallback is disabled even when listed in legacy plans."""
        calls = []

        async def sequenced_caller(endpoint, method="POST", data=None):
            calls.append(endpoint)
            if endpoint == "/command":
                return {"success": False, "data": {"waitingFor": "Select rail"}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(
            http_caller=sequenced_caller,
            command_knowledge_store=safe_command_store(),
        )
        plan = ExecutionPlan(
            intent="sweep curve",
            operation="command:_-Sweep1",
            execution_route="known_command",
            command="_-Sweep1",
            syntax="_-Sweep1 _SelID curve1 _Enter",
            fallbacks=["interactive"],
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.route_taken == "known_command"
        assert result.failure.layer == FailureLayer.INTERACTIVE_PROMPT
        assert "Select rail" in result.failure.error_detail
        assert "interactive prompt driving is disabled" in result.failure.recovery_suggestion
        assert "/command/start" not in calls
        assert "/command/send" not in calls

    def test_known_command_rejects_without_safe_metadata_before_http_call(self):
        calls = []

        async def tracking_caller(endpoint, method="POST", data=None):
            calls.append(endpoint)
            return {"success": True, "data": {}}

        executor = SmartExecutor(
            http_caller=tracking_caller,
            command_knowledge_store=FakeCommandKnowledgeStore(safe=False),
        )
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="known_command",
            command="_-Loft",
            syntax="_-Loft _SelID a _SelID b _Enter",
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.ROUTING
        assert "run_script_safety_refusal" in result.failure.error_detail
        assert calls == []


# ---------------------------------------------------------------------------
# Interactive execution
# ---------------------------------------------------------------------------

class TestInteractiveExecution:

    def test_interactive_route_is_disabled_for_normal_execution(self):
        calls = []

        async def interactive_caller(endpoint, method="POST", data=None):
            calls.append(endpoint)
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=interactive_caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft _SelID a _SelID b _Enter",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.route_taken == "interactive"
        assert result.failure.layer == FailureLayer.ROUTING
        assert result.failure.attempted_route == "interactive"
        assert result.failure.operation == "command:_-Loft"
        assert result.failure.error_detail == (
            "Interactive Rhino command execution is disabled for normal execution."
        )
        assert "typed Rook tools" in result.failure.recovery_suggestion
        assert "known-safe fully scripted command" in result.failure.recovery_suggestion
        assert "rhino_command_prompt" in result.failure.recovery_suggestion
        assert "rhino_command_interactive_cancel" in result.failure.recovery_suggestion
        assert "Interactive execution route is deprecated" in result.reasoning_trace
        assert "/command/start" not in calls
        assert "/command/send" not in calls

    def test_prompt_poll_helper_reports_poll_error(self):
        async def failing_poll_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/prompt":
                raise ConnectionError("Connection reset")
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=failing_poll_caller)
        trace = []
        result = run(executor._poll_prompt(trace))

        assert result["_poll_error"] == "Connection reset"
        assert any("Prompt poll failed" in item for item in trace)

    def test_safe_cancel_helper_swallows_errors(self):
        async def failing_cancel_caller(endpoint, method="POST", data=None):
            raise RuntimeError("cancel failed")

        executor = SmartExecutor(http_caller=failing_cancel_caller)
        trace = []
        run(executor._safe_cancel(trace))

        assert trace == ["Cancel failed (non-critical): cancel failed"]


# ---------------------------------------------------------------------------
# Unknown route
# ---------------------------------------------------------------------------

class TestUnknownRoute:

    def test_unknown_route(self):
        executor = SmartExecutor(http_caller=make_caller())
        plan = ExecutionPlan(
            intent="something",
            operation="unknown",
            execution_route="unknown",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.failure.layer == FailureLayer.ROUTING


# ---------------------------------------------------------------------------
# Response parsing edge cases
# ---------------------------------------------------------------------------

class TestResponseParsing:

    def test_string_data_success(self):
        caller = make_caller({
            "/create": {"success": True, "data": "Object created successfully"},
        })
        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="create",
            operation="create_point",
            params={"location": [0, 0, 0]},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_point"),
        )
        result = run(executor.execute(plan))
        assert result.success is True

    def test_string_id_in_created_ids(self):
        """Handle case where objectIds is a single string, not list."""
        caller = make_caller({
            "/create": {"success": True, "data": {"objectIds": "single-guid", "objectsCreated": 1}},
        })
        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="create point",
            operation="create_point",
            params={"location": [0, 0, 0]},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_point"),
        )
        result = run(executor.execute(plan))
        assert result.success is True
        assert result.created_ids == ["single-guid"]

    def test_result_includes_plan_summary(self):
        executor = SmartExecutor(http_caller=make_caller({
            "/create": {"success": True, "data": {"objectIds": [], "objectsCreated": 0}},
        }))
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))
        assert "operation" in result.plan_summary
        assert result.plan_summary["operation"] == "create_sphere"

    def test_result_timing(self):
        executor = SmartExecutor(http_caller=make_caller({
            "/create": {"success": True, "data": {"objectIds": [], "objectsCreated": 0}},
        }))
        plan = ExecutionPlan(
            intent="create sphere",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=CapabilityRouter.get().route("create_sphere"),
        )
        result = run(executor.execute(plan))
        assert result.time_ms > 0


# ---------------------------------------------------------------------------
# Syntax tokenization (H2 fix)
# ---------------------------------------------------------------------------

class TestTokenizeSyntax:

    def test_simple_tokens(self):
        assert _tokenize_syntax("_-Loft _SelID a _Enter") == ["_-Loft", "_SelID", "a", "_Enter"]

    def test_quoted_path(self):
        result = _tokenize_syntax('_-Import "C:/path with spaces/file.3dm"')
        assert len(result) == 2
        assert "path with spaces" in result[1]

    def test_quoted_option(self):
        result = _tokenize_syntax('_-SetUnits "Small Objects - Millimeters"')
        assert len(result) == 2
        assert "Small Objects" in result[1]

    def test_mixed_quoted_and_plain(self):
        result = _tokenize_syntax('_-Loft _SelID "curve set A" _SelID b _Enter')
        assert result[0] == "_-Loft"
        assert "curve set A" in result[2]
        assert result[-1] == "_Enter"

    def test_empty_string(self):
        assert _tokenize_syntax("") == []

    def test_single_command(self):
        assert _tokenize_syntax("_-Loft") == ["_-Loft"]

    def test_quoted_tokens_remain_intact_for_recovery_helpers(self):
        """H2: Verify quoted command arguments are preserved by tokenizer."""
        tokens = _tokenize_syntax('_-Import "C:/My Files/model.3dm" _Enter')

        assert tokens == ["_-Import", '"C:/My Files/model.3dm"', "_Enter"]
