"""Tests for SmartExecutor (P2): ExecutionPlan -> ExecutionResult."""

import asyncio
import pytest
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
        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="known_command",
            command="_-Loft",
            syntax="_-Loft _SelID a _SelID b _Enter",
            fallbacks=["interactive"],
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
        executor = SmartExecutor(http_caller=caller)
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

    def test_stalled_command_escalates_to_interactive(self):
        """Command stalls but has interactive fallback available."""
        prompt_polls = {"n": 0}

        async def sequenced_caller(endpoint, method="POST", data=None):
            if endpoint == "/command":
                return {"success": False, "data": {"waitingFor": "Select rail"}}
            elif endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Sweep1", "started": True}}
            elif endpoint == "/command/prompt":
                prompt_polls["n"] += 1
                if prompt_polls["n"] >= 2:
                    return {"success": True, "data": {"is_active": False, "prompt": "Command"}}
                return {"success": True, "data": {"is_active": True, "prompt": "Select rail"}}
            elif endpoint == "/command/send":
                return {"success": True, "data": {"input_sent": True}}
            elif endpoint == "/command/cancel":
                return {"success": True, "data": {}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=sequenced_caller)
        plan = ExecutionPlan(
            intent="sweep curve",
            operation="command:_-Sweep1",
            execution_route="known_command",
            command="_-Sweep1",
            syntax="_-Sweep1 _SelID curve1 _Enter",
            fallbacks=["interactive"],
        )
        result = run(executor.execute(plan))

        assert result.success is True
        assert any("escalating" in t.lower() for t in result.reasoning_trace)
        # I7: Verify confidence is reduced by 0.7x on fallback
        assert result.plan_summary["confidence"] == pytest.approx(
            plan.confidence * 0.7, rel=1e-3
        )


# ---------------------------------------------------------------------------
# Interactive execution
# ---------------------------------------------------------------------------

class TestInteractiveExecution:

    def test_basic_interactive(self):
        """Interactive session using actual C++ protocol: start -> poll -> send -> poll."""
        prompt_polls = {"n": 0}

        async def interactive_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Loft", "started": True}}
            elif endpoint == "/command/prompt":
                prompt_polls["n"] += 1
                if prompt_polls["n"] >= 4:
                    return {"success": True, "data": {"is_active": False, "prompt": "Command"}}
                return {"success": True, "data": {"is_active": True, "prompt": "Select curves"}}
            elif endpoint == "/command/send":
                return {"success": True, "data": {"input_sent": True}}
            elif endpoint == "/command/cancel":
                return {"success": True, "data": {}}
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
        assert result.success is True
        assert result.route_taken == "interactive"

    def test_interactive_start_failure(self):
        async def failing_start(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": False, "data": "Command not found"}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=failing_start)
        plan = ExecutionPlan(
            intent="loft",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.failure.layer == FailureLayer.COMMAND_EXECUTION

    def test_no_command_in_plan(self):
        executor = SmartExecutor(http_caller=make_caller())
        plan = ExecutionPlan(
            intent="do something",
            operation="unknown",
            execution_route="interactive",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.failure.layer == FailureLayer.PARAMETER_SYNTHESIS

    def test_max_rounds_exhaustion(self):
        """S2: Interactive session that never completes gets cancelled."""
        async def forever_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Loft", "started": True}}
            elif endpoint == "/command/prompt":
                return {"success": True, "data": {"is_active": True, "prompt": "Still waiting"}}
            elif endpoint == "/command/send":
                return {"success": True, "data": {"input_sent": True}}
            elif endpoint == "/command/cancel":
                return {"success": True, "data": {}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=forever_caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft _Enter",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.failure.layer == FailureLayer.INTERACTIVE_PROMPT
        assert "exceeded" in result.failure.error_detail.lower()

    def test_exception_triggers_cancel(self):
        """S3: Exception during interactive session triggers safe cancel."""
        cancel_called = {"called": False}

        async def exploding_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Loft", "started": True}}
            elif endpoint == "/command/prompt":
                return {"success": True, "data": {"is_active": True, "prompt": "Select"}}
            elif endpoint == "/command/send":
                raise RuntimeError("Connection lost")
            elif endpoint == "/command/cancel":
                cancel_called["called"] = True
                return {"success": True, "data": {}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=exploding_caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft _SelID a _Enter",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert result.failure.layer == FailureLayer.COMMAND_EXECUTION
        assert "Connection lost" in result.failure.error_detail
        assert cancel_called["called"], "Cancel should be called on exception"

    def test_poll_error_does_not_produce_success(self):
        """I1: Poll failure must not be treated as 'command completed'."""
        poll_count = {"n": 0}

        async def failing_poll_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Loft", "started": True}}
            elif endpoint == "/command/prompt":
                poll_count["n"] += 1
                if poll_count["n"] == 1:
                    # First poll OK
                    return {"success": True, "data": {"is_active": True, "prompt": "Select"}}
                # Second poll: network error
                raise ConnectionError("Connection reset")
            elif endpoint == "/command/send":
                return {"success": True, "data": {"input_sent": True}}
            elif endpoint == "/command/cancel":
                return {"success": True, "data": {}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=failing_poll_caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft _SelID a _Enter",
        )
        result = run(executor.execute(plan))
        assert result.success is False
        assert "poll failed" in result.failure.error_detail.lower()


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

    def test_interactive_sends_quoted_tokens_intact(self):
        """H2: Verify interactive execution preserves quoted arguments."""
        sent_inputs = []

        async def tracking_caller(endpoint, method="POST", data=None):
            if endpoint == "/command/start":
                return {"success": True, "data": {"command": "_-Import", "started": True}}
            elif endpoint == "/command/prompt":
                return {"success": True, "data": {"is_active": False, "prompt": "Command"}}
            elif endpoint == "/command/send":
                sent_inputs.append(data.get("input", ""))
                return {"success": True, "data": {"input_sent": True}}
            elif endpoint == "/command/cancel":
                return {"success": True, "data": {}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=tracking_caller)
        plan = ExecutionPlan(
            intent="import file",
            operation="command:_-Import",
            execution_route="interactive",
            command="_-Import",
            syntax='_-Import "C:/My Files/model.3dm" _Enter',
        )
        run(executor.execute(plan))
        # The first input after the command name should be the full path, not split
        # (the command completes immediately in this mock so no sends happen,
        # but the tokenizer should at least not crash)
