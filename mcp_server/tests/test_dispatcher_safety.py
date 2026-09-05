"""Tests for ToolDispatcher script safety — compile() pre-check and post-dispatch verification.

Covers:
  1. _transform_execute: syntax validation via compile() before Rhino dispatch
  2. ToolDispatcher.dispatch: post-dispatch verification for all needs_verification() tools
  3. Integration: chat and agent paths both get verification through the dispatcher
"""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

from rook.agent.tool_dispatcher import (
    _transform_execute,
    ToolDispatcher,
    BRIDGE_ROUTES,
    TRANSFORM_FUNCTIONS,
)
from rook.agent.chat.execution_policy import (
    CREATION_TOOLS,
    MODAL_RISK_TOOLS,
    needs_verification,
    annotate_result,
)


def _safe_line_knowledge_store():
    return SimpleNamespace(
        parse_command_string=lambda _cmd: {
            "command": "-Line",
            "mode": "default",
            "syntax": "_Line <start> <end>",
            "parameters": {"start": "0,0,0", "end": "1,1,1"},
            "options_used": [],
        },
        get_command=lambda _cmd: SimpleNamespace(
            options={},
            modes={"default": SimpleNamespace(syntax="_Line <start> <end>")},
            preconditions={"safe_non_interactive": True},
        ),
    )


# =============================================================================
# _transform_execute: compile() pre-check
# =============================================================================

class TestTransformExecuteSyntaxCheck:
    """Layer 1: compile() catches syntax errors before Rhino."""

    def test_valid_code_passes_through(self):
        """Valid Python should pass through unchanged after compile() succeeds."""
        endpoint, method, data = _transform_execute({"code": "x = 1 + 2"})
        assert endpoint == "/execute"
        assert method == "POST"
        assert data["code"] == "x = 1 + 2"

    def test_syntax_error_returns_error_dict(self):
        """Syntax errors should return an error dict, not reach Rhino."""
        endpoint, method, data = _transform_execute({"code": "def foo(:"})
        assert endpoint is None
        assert method is None
        assert data["success"] is False
        assert "syntax error" in data["data"].lower()
        assert "NOT sent to Rhino" in data["data"]

    def test_syntax_error_includes_line_number(self):
        """The error message should include the line number from compile()."""
        code = "x = 1\ny = 2\nfor in range(5):\n    pass"
        _, _, data = _transform_execute({"code": code})
        assert data["success"] is False
        assert "line" in data["data"].lower()

    def test_empty_code_passes_through(self):
        """Empty code should not trigger compile() — just pass through."""
        endpoint, method, data = _transform_execute({"code": ""})
        assert endpoint == "/execute"
        assert method == "POST"

    def test_no_code_key_passes_through(self):
        """Missing code key should not crash."""
        endpoint, method, data = _transform_execute({})
        assert endpoint == "/execute"
        assert method == "POST"

    def test_multiline_valid_code(self):
        """Multi-line valid Python should compile and pass through unchanged."""
        code = "import rhinoscriptsyntax as rs\nids = rs.AllObjects()\nfor i in ids:\n    print(i)"
        endpoint, method, data = _transform_execute({"code": code})
        assert endpoint == "/execute"
        assert data["code"] == code

    def test_indentation_error_caught(self):
        """IndentationError (subclass of SyntaxError) should be caught."""
        code = "if True:\nx = 1"
        endpoint, method, data = _transform_execute({"code": code})
        assert endpoint is None
        assert data["success"] is False

    def test_interactive_rs_call_rejected_pre_dispatch(self):
        """Blocking rhinoscriptsyntax Get* calls should never reach Rhino."""
        code = "import rhinoscriptsyntax as rs\nrs.GetPoint('Pick a point')"
        endpoint, method, data = _transform_execute({"code": code})
        assert endpoint is None
        assert method is None
        assert data["success"] is False
        assert "not sent to rhino" in data["data"].lower()
        assert "interactive rhino input call" in data["data"].lower()

    def test_interactive_direct_import_rejected_pre_dispatch(self):
        """Directly imported blocking rhinoscriptsyntax calls should be caught."""
        code = "from rhinoscriptsyntax import GetObject\nGetObject('Select object')"
        endpoint, method, data = _transform_execute({"code": code})
        assert endpoint is None
        assert method is None
        assert data["success"] is False
        assert "getobject()" in data["data"].lower()

    def test_extra_args_preserved(self):
        """Non-code args should pass through unchanged."""
        endpoint, method, data = _transform_execute({"code": "x = 1", "timeout": 5000})
        assert endpoint == "/execute"
        assert data.get("timeout") == 5000


# =============================================================================
# ToolDispatcher.dispatch: post-dispatch verification
# =============================================================================

class TestDispatcherVerification:
    """Post-dispatch verification runs for all needs_verification() tools."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_creation_tool_gets_verified(self, dispatcher):
        """rhino_create results should be annotated with verified field."""
        mock_result = {"success": True, "data": {"id": "abc", "objectsCreated": 1}}
        prompt_idle = {"success": True, "data": {"is_active": False, "prompt": ""}}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            # First call: /create, second call: /command/prompt
            mock_rhino.side_effect = [mock_result, prompt_idle]
            result = await dispatcher.dispatch("rhino_create", {"type": "BOX"})

        assert "verified" in result
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_creation_tool_zero_objects_unverified(self, dispatcher):
        """rhino_create with objectsCreated=0 should be marked unverified."""
        mock_result = {"success": True, "data": {"objectsCreated": 0}}
        prompt_idle = {"success": True, "data": {"is_active": False, "prompt": ""}}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.side_effect = [mock_result, prompt_idle]
            result = await dispatcher.dispatch("rhino_create", {"type": "BOX"})

        assert result["verified"] is False
        assert "objectsCreated=0" in result.get("verification_note", "")

    @pytest.mark.asyncio
    async def test_modal_risk_tool_blocked_prompt(self, dispatcher):
        """rhino_execute with active prompt should be marked unverified."""
        mock_result = {"success": True, "data": {"output": "ok"}}
        prompt_active = {"success": True, "data": {"is_active": True, "prompt": "Enter value"}}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            # Transform wraps code, so we need compile to pass first
            mock_rhino.side_effect = [mock_result, prompt_active]
            result = await dispatcher.dispatch("rhino_execute", {"code": "x = 1"})

        assert result["verified"] is False
        assert "waiting for input" in result.get("verification_note", "").lower()

    @pytest.mark.asyncio
    async def test_syntax_error_never_calls_rhino(self, dispatcher):
        """Syntax errors should short-circuit — no HTTP calls to Rhino."""
        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            result = await dispatcher.dispatch("rhino_execute", {"code": "def foo(:"})

        # call_rhino should never be called
        mock_rhino.assert_not_called()
        assert result["success"] is False
        assert "syntax error" in result["data"].lower()

    @pytest.mark.asyncio
    async def test_syntax_error_no_misleading_annotation(self, dispatcher):
        """Pre-dispatch compile failures must NOT get modal-risk annotation.

        Regression test: without the _pre_dispatch_failure signal, annotate_result
        would add a post-execution reminder — misleading because the script never
        reached Rhino.
        """
        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            result = await dispatcher.dispatch("rhino_execute", {"code": "def foo(:"})

        mock_rhino.assert_not_called()
        # Must NOT have verification_note from the modal-risk annotator
        assert "verified" not in result
        assert "verification_note" not in result
        # The _pre_dispatch_failure tag must be consumed (popped), not leaked
        assert "_pre_dispatch_failure" not in result

    @pytest.mark.asyncio
    async def test_bridge_tool_no_verification(self, dispatcher):
        """rhino_ping should NOT get verification annotation."""
        mock_result = {"success": True, "data": "pong"}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("rhino_ping", {})

        assert "verified" not in result

    @pytest.mark.asyncio
    async def test_gh_connect_uses_shared_bridge_route_and_frozen_port(self):
        dispatcher = ToolDispatcher(port=9950)
        params = {
            "sourceGuid": "source-guid",
            "sourceIndex": 0,
            "targetGuid": "target-guid",
            "targetIndex": 1,
        }
        response = {
            "success": True,
            "data": {
                "connected": True,
                "source": {"guid": "source-guid", "index": 0},
                "target": {"guid": "target-guid", "index": 1},
            },
        }

        with patch(
            "rook.agent.tool_dispatcher.call_rhino",
            new_callable=AsyncMock,
            return_value=response,
        ) as mock_rhino:
            result = await dispatcher.dispatch("gh_connect", params)

        mock_rhino.assert_awaited_once_with("/gh/connect", "POST", params, 9950)
        assert result is response

    @pytest.mark.asyncio
    async def test_gh_status_normalizes_managed_camel_case(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "available": True,
                "assemblyVersion": "8.0.0.0",
                "hasActiveCanvas": True,
                "canvasVisible": False,
                "visibilityUnknown": False,
                "hasActiveDocument": True,
                "documentId": "doc-1",
                "documentName": "example.gh",
                "documentPath": r"C:\tmp\example.gh",
                "readyForEdit": False,
                "objectCount": 4,
                "warnings": [],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("gh_status", {})

        assert result["success"] is True
        assert result["data"]["ready_for_edit"] is False
        assert result["data"]["has_active_canvas"] is True
        assert result["data"]["canvas_visible"] is False
        assert "readyForEdit" not in result["data"]

    @pytest.mark.asyncio
    async def test_gh_snapshot_not_ready_hoists_verification_for_chat(self, dispatcher):
        mock_result = {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "errors": ["No active Grasshopper canvas"],
                "message": "No active Grasshopper canvas",
                "ready_for_edit": False,
                "verified": False,
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("gh_snapshot", {})

        assert result["success"] is False
        assert result["verified"] is False
        assert result["verification_note"] == "No active Grasshopper canvas"
        assert result["data"]["verified"] is False

    @pytest.mark.asyncio
    async def test_gh_edit_not_ready_hoists_verification_without_edit_summary(self, dispatcher):
        mock_result = {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "errors": ["No active Grasshopper document"],
                "message": "No active Grasshopper document",
                "ready_for_edit": False,
                "verified": False,
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("gh_edit", {"epoch": 9})

        assert result["success"] is False
        assert result["verified"] is False
        assert result["verification_note"] == "No active Grasshopper document"
        assert result["data"]["verified"] is False
        assert "partial_success" not in result

    @pytest.mark.asyncio
    async def test_gh_edit_no_mutation_errors_are_not_success(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 0,
                    "deleted": 0,
                    "values_set": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "errors": ["Create failed: Centre Box not found"],
                }
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("gh_edit", {"epoch": 9, "create": []})

        assert mock_rhino.call_count == 1
        assert result["success"] is False
        assert result["verified"] is False
        assert result["errors"] == ["Create failed: Centre Box not found"]
        assert "partial_success" not in result

    @pytest.mark.asyncio
    async def test_gh_edit_partial_errors_are_strict_failures_for_chat_agents(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 1,
                    "errors": ["connect: param not found for 'T19.O0>T20.I2'"],
                    "instance_guids": {"T19": "guid-19"},
                }
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("gh_edit", {"epoch": 9, "connect": []})

        assert mock_rhino.call_count == 1
        assert result["success"] is False
        assert result["partial_success"] is True
        assert result["verified"] is False
        assert result["errors"] == ["connect: param not found for 'T19.O0>T20.I2'"]
        assert result["data"]["partial_success"] is True
        assert result["data"]["errors"] == ["connect: param not found for 'T19.O0>T20.I2'"]
        assert result["data"]["warnings"] == ["connect: param not found for 'T19.O0>T20.I2'"]
        assert result["data"]["verified"] is False
        assert "verification_note" in result

    @pytest.mark.asyncio
    async def test_rhino_boolean_gets_verified(self, dispatcher):
        """rhino_boolean (transform tier + CREATION_TOOLS) should be verified."""
        mock_result = {"success": True, "data": {"id": "xyz", "objectsCreated": 1}}
        prompt_idle = {"success": True, "data": {"is_active": False, "prompt": ""}}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.side_effect = [mock_result, prompt_idle]
            result = await dispatcher.dispatch("rhino_boolean", {
                "operation": "union", "ids": ["a", "b"]
            })

        assert "verified" in result

    @pytest.mark.asyncio
    async def test_rhino_command_gets_verified(self, dispatcher):
        """rhino_command (transform tier + MODAL_RISK_TOOLS) should be verified."""
        mock_result = {"success": True, "data": {"output": "ok", "objectsCreated": 0}}
        prompt_idle = {"success": True, "data": {"is_active": False, "prompt": ""}}

        with (
            patch("rook.server.command_learner") as command_learner,
            patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino,
        ):
            command_learner.knowledge_store = _safe_line_knowledge_store()
            mock_rhino.side_effect = [mock_result, prompt_idle]
            result = await dispatcher.dispatch("rhino_command", {"command": "_Line 0,0,0 1,1,1"})

        assert "verified" in result

    @pytest.mark.asyncio
    async def test_prompt_poll_failure_marks_unverified(self, dispatcher):
        """If prompt poll raises an exception, modal-risk tools should be unverified."""
        mock_result = {"success": True, "data": {"output": "ok"}}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            # First call succeeds (the tool), second call raises (prompt poll)
            mock_rhino.side_effect = [mock_result, ConnectionError("Rhino unreachable")]
            result = await dispatcher.dispatch("rhino_execute", {"code": "x = 1"})

        assert result["verified"] is False
        assert "could not verify" in result.get("verification_note", "").lower()

    @pytest.mark.asyncio
    async def test_failed_tool_skips_prompt_poll(self, dispatcher):
        """If the tool itself returned success=False, skip the prompt poll entirely."""
        mock_result = {"success": False, "data": "Command failed"}

        with (
            patch("rook.server.command_learner") as command_learner,
            patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino,
        ):
            command_learner.knowledge_store = _safe_line_knowledge_store()
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("rhino_command", {"command": "_Line 0,0,0 1,1,1"})

        # Only 1 call (the tool itself), no prompt poll
        assert mock_rhino.call_count == 1


# =============================================================================
# rhino_execute_intent route-based verification
# =============================================================================

class TestExecuteIntentVerification:
    """rhino_execute_intent is verified when substrate is known_command or interactive."""

    @pytest.fixture
    def dispatcher(self):
        d = ToolDispatcher(port=9950)
        # Register a mock rhino_execute_intent as local tool
        async def mock_intent(intent="", **kwargs):
            return {
                "success": True,
                "data": {
                    "route_taken": "known_command",
                    "objectsCreated": 1,
                },
            }
        d.register_local("rhino_execute_intent", mock_intent)
        return d

    @pytest.mark.asyncio
    async def test_retired_intent_path_is_contained(self, dispatcher):
        """The legacy semantic entry point never reaches verification or Rhino."""
        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            result = await dispatcher.dispatch("rhino_execute_intent", {"intent": "create a box"})

        assert result["success"] is False
        assert result["data"]["code"] == "legacy_semantic_tool_contained"
        mock_rhino.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_direct_api_substrate_not_verified(self):
        """rhino_execute_intent with direct_api substrate should NOT be verified."""
        d = ToolDispatcher(port=9950)

        async def mock_intent(intent="", **kwargs):
            return {
                "success": True,
                "data": {
                    "route_taken": "direct_api",
                    "objectsCreated": 1,
                },
            }
        d.register_local("rhino_execute_intent", mock_intent)

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            result = await d.dispatch("rhino_execute_intent", {"intent": "create a box"})

        # direct_api does not need verification — no RunScript, no modal risk
        assert "verified" not in result
        mock_rhino.assert_not_called()


# =============================================================================
# Coverage: all CREATION_TOOLS and MODAL_RISK_TOOLS are dispatchable
# =============================================================================

class TestVerificationCoverage:
    """Every tool in needs_verification() must be reachable by the dispatcher."""

    def test_all_creation_tools_are_dispatchable(self):
        """Every CREATION_TOOL must be in BRIDGE_ROUTES or TRANSFORM_FUNCTIONS."""
        for tool in CREATION_TOOLS:
            assert tool in BRIDGE_ROUTES or tool in TRANSFORM_FUNCTIONS, (
                f"{tool} is in CREATION_TOOLS but not dispatchable"
            )

    def test_all_modal_risk_tools_are_dispatchable(self):
        """Every MODAL_RISK_TOOL must be in BRIDGE_ROUTES or TRANSFORM_FUNCTIONS."""
        for tool in MODAL_RISK_TOOLS:
            assert tool in BRIDGE_ROUTES or tool in TRANSFORM_FUNCTIONS, (
                f"{tool} is in MODAL_RISK_TOOLS but not dispatchable"
            )

    def test_rhino_execute_in_transform_not_bridge(self):
        """rhino_execute must go through transform (for compile + try/except), not bridge."""
        assert "rhino_execute" in TRANSFORM_FUNCTIONS
        assert "rhino_execute" not in BRIDGE_ROUTES


def test_gh_query_not_exposed_to_agent_dispatch_surfaces():
    """Legacy /gh/query remains native HTTP compatibility only."""
    from rook.agent import tool_dispatcher
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "gh_query" not in tool_dispatcher.BRIDGE_ROUTES
    assert "gh_query" not in tool_dispatcher.TRANSFORM_FUNCTIONS
    assert hasattr(tool_dispatcher, "GH_READINESS_HOIST_TOOLS")
    assert "gh_query" not in tool_dispatcher.GH_READINESS_HOIST_TOOLS

    exposed_groups = [
        group_name
        for group_name, tools in TOOL_GROUPS.items()
        if "gh_query" in tools
    ]
    assert exposed_groups == []


@pytest.mark.asyncio
async def test_interactive_start_send_not_exposed_to_agent_bridge_or_public_mcp(monkeypatch):
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    public_names = {tool.name for tool in await server.list_tools()}

    assert "rhino_command_interactive_start" not in BRIDGE_ROUTES
    assert "rhino_command_interactive_send" not in BRIDGE_ROUTES
    assert "rhino_command_interactive_start" not in public_names
    assert "rhino_command_interactive_send" not in public_names
    assert "rhino_command_experiment" not in public_names
    assert "rhino_learn_next" not in public_names
    assert "rhino_command_interactive_prompt" in BRIDGE_ROUTES
    assert "rhino_command_interactive_cancel" in BRIDGE_ROUTES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("rhino_command_interactive_start", {"command": "_-Box"}),
        ("rhino_command_interactive_send", {"input": "0,0,0"}),
        ("rhino_command_experiment", {"command": "_-Box", "variations": ["_-Box 0,0,0 1,1,1"]}),
        ("rhino_learn_interactive", {"command": "_-Box", "inputs": ["0,0,0"]}),
        ("rhino_learn_next", {}),
        (
            "rhino_learn_variations_interactive",
            {"command": "_-Box", "input_sequences": [["0,0,0"]]},
        ),
        ("rhino_prepare_geometry", {"geometry_type": "curve"}),
    ],
)
async def test_deprecated_interactive_tools_refuse_agent_dispatch(tool_name, params):
    dispatcher = ToolDispatcher(port=9950)

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
        result = await dispatcher.dispatch(tool_name, params)

    assert result["success"] is False
    assert result["data"]["error"] == "interactive_command_deprecated"
    assert result["data"]["tool"] == tool_name
    assert result["data"]["verified"] is False
    mock_rhino.assert_not_called()


def test_gh_legacy_not_ready_result_hoists_nested_verification_fields():
    from rook.agent.tool_dispatcher import _hoist_nested_verification_fields

    result = {
        "success": False,
        "data": {
            "error": "grasshopper_not_ready",
            "verified": False,
            "message": "No active Grasshopper document.",
            "verification_note": "Call gh_status to inspect readiness.",
        },
    }

    hoisted = _hoist_nested_verification_fields(result)

    assert hoisted["verified"] is False
    assert hoisted["verification_note"] == "Call gh_status to inspect readiness."
