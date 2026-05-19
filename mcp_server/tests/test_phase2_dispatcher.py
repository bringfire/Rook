"""
Phase 2 ToolDispatcher Tests
=============================

Verifies:
A: Knowledge middleware (gotchas + correction detection)
B: Local tool smoke tests (4 new tools)
C: Tier 0 agent_mode check
D: Seam 3 correction_detected and attempt_number
E: Coverage re-audit
"""

import asyncio
import sys
import os
import time
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

passed = 0
failed = 0


def test(name):
    """Test decorator for tracking pass/fail."""
    def decorator(fn):
        global passed, failed
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                asyncio.get_event_loop().run_until_complete(result)
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name} — {e}")
            failed += 1
        return fn
    return decorator


# =========================================================================
# A: Knowledge middleware tests
# =========================================================================

print("\n=== A: Knowledge Middleware ===")


@test("KNOWLEDGE_WRAPPED_TOOLS has correct 4 entries")
def _():
    from rook.agent.tool_dispatcher import KNOWLEDGE_WRAPPED_TOOLS
    assert len(KNOWLEDGE_WRAPPED_TOOLS) == 4
    assert "gh_connect" in KNOWLEDGE_WRAPPED_TOOLS
    assert "gh_disconnect" in KNOWLEDGE_WRAPPED_TOOLS
    assert "gh_set_value" in KNOWLEDGE_WRAPPED_TOOLS
    assert "gh_delete" in KNOWLEDGE_WRAPPED_TOOLS


@test("Context builders produce correct keys")
def _():
    from rook.agent.tool_dispatcher import KNOWLEDGE_WRAPPED_TOOLS

    op, ctx_fn = KNOWLEDGE_WRAPPED_TOOLS["gh_connect"]
    assert op == "wire"
    ctx = ctx_fn({"sourceGuid": "a", "targetGuid": "b", "targetParam": "X"})
    assert ctx["source_guid"] == "a"
    assert ctx["target_guid"] == "b"
    assert ctx["param"] == "X"

    op, ctx_fn = KNOWLEDGE_WRAPPED_TOOLS["gh_set_value"]
    assert op == "set_value"
    ctx = ctx_fn({"guid": "c", "value": 42})
    assert ctx["target_guid"] == "c"
    assert ctx["value"] == 42

    op, ctx_fn = KNOWLEDGE_WRAPPED_TOOLS["gh_delete"]
    assert op == "delete"
    ctx = ctx_fn({"guids": ["d", "e"]})
    assert ctx["guids"] == ["d", "e"]


@test("Knowledge tier intercepts before bridge tier in dispatch()")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher

    d = ToolDispatcher()

    # Mock call_rhino and knowledge functions
    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino, \
         patch("rook.learning.gh_knowledge.gh_query_operation") as mock_op, \
         patch("rook.learning.gh_knowledge.get_gh_knowledge_store") as mock_store:

        mock_rhino.return_value = {
            "success": True,
            "data": {"success": True, "message": "connected"},
        }
        mock_op.return_value = {
            "gotchas": [{"message": "Watch out for param order"}],
        }
        mock_store_inst = MagicMock()
        mock_store.return_value = mock_store_inst

        result = await d.dispatch("gh_connect", {
            "sourceGuid": "a", "targetGuid": "b", "targetParam": "X",
        })

        assert result["data"]["gotchas"] == ["Watch out for param order"]
        assert result["data"]["correction_detected"] is False
        mock_rhino.assert_called_once()
        mock_store_inst.record_gotcha_success.assert_called_once_with("wire")


@test("Correction detection: fail then succeed triggers correction_detected=True")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher

    d = ToolDispatcher()

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino, \
         patch("rook.learning.gh_knowledge.gh_query_operation") as mock_op, \
         patch("rook.learning.gh_knowledge.get_gh_knowledge_store"):

        mock_op.return_value = {"gotchas": []}

        # First call: failure
        mock_rhino.return_value = {
            "success": False,
            "data": {"success": False, "error": "bad param"},
        }
        result1 = await d.dispatch("gh_connect", {
            "sourceGuid": "a", "targetGuid": "b", "targetParam": "X",
        })
        assert result1["data"]["correction_detected"] is False
        assert len(d._recent_failures) == 1

        # Second call: success with same context
        mock_rhino.return_value = {
            "success": True,
            "data": {"success": True, "message": "ok"},
        }
        result2 = await d.dispatch("gh_connect", {
            "sourceGuid": "a", "targetGuid": "b", "targetParam": "X",
        })
        assert result2["data"]["correction_detected"] is True
        assert len(d._recent_failures) == 0


@test("Expired failures don't trigger correction")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher

    d = ToolDispatcher()
    d._failure_expiry_seconds = 0.01  # Very short expiry

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino, \
         patch("rook.learning.gh_knowledge.gh_query_operation") as mock_op, \
         patch("rook.learning.gh_knowledge.get_gh_knowledge_store"):

        mock_op.return_value = {"gotchas": []}

        # Failure
        mock_rhino.return_value = {"success": False, "data": "error"}
        await d.dispatch("gh_set_value", {"guid": "a", "value": 1})
        assert len(d._recent_failures) == 1

        # Wait for expiry
        time.sleep(0.02)

        # Success after expiry
        mock_rhino.return_value = {"success": True, "data": {"success": True}}
        result = await d.dispatch("gh_set_value", {"guid": "a", "value": 1})
        assert result.get("correction_detected", False) is False


# =========================================================================
# B: Local tool smoke tests
# =========================================================================

print("\n=== B: Local Tool Smoke Tests ===")


@test("build_local_tools() includes 4 new tools")
def _():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    # Original 4: knowledge_query, gh_knowledge_query, rhino_instances, rhino_execute_intent
    # New 4: gh_constraints, rhino_command_select, rhino_command_queue, gh_canvas_cleanup
    new_tools = {"gh_constraints", "rhino_command_select", "rhino_command_queue", "gh_canvas_cleanup"}
    for t in new_tools:
        assert t in tools, f"Missing local tool: {t}"
    assert len(tools) >= 8, f"Expected at least 8 local tools, got {len(tools)}"


@test("gh_constraints tool returns data for no filter")
async def _():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    if "gh_constraints" not in tools:
        raise Exception("gh_constraints not available")
    result = await tools["gh_constraints"]()
    assert result["success"] is True
    assert "data" in result


@test("rhino_command_select requires intent")
async def _():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    if "rhino_command_select" not in tools:
        raise Exception("rhino_command_select not available")
    result = await tools["rhino_command_select"]()
    assert result["success"] is False


@test("rhino_command_queue returns queue data")
async def _():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    if "rhino_command_queue" not in tools:
        raise Exception("rhino_command_queue not available")
    result = await tools["rhino_command_queue"]()
    assert result["success"] is True
    assert "queue" in result["data"]


# =========================================================================
# C: Tier 0 agent_mode check
# =========================================================================

print("\n=== C: Tier 0 Agent Mode ===")


@test("AGENT_TIER_0 excludes gh_execute_intent")
def _():
    from rook.agent.tool_groups import TIER_0, AGENT_TIER_0
    assert "gh_execute_intent" in TIER_0
    assert "gh_execute_intent" not in AGENT_TIER_0
    # All other TIER_0 tools should be in AGENT_TIER_0
    for t in TIER_0:
        if t != "gh_execute_intent":
            assert t in AGENT_TIER_0, f"Missing from AGENT_TIER_0: {t}"


@test("ToolRegistry(agent_mode=True) excludes gh_execute_intent from active")
def _():
    from rook.agent.tool_registry import ToolRegistry
    # Need a catalog with gh_execute_intent for it to be activatable
    catalog = {
        "gh_execute_intent": {
            "type": "function",
            "function": {"name": "gh_execute_intent", "description": "test", "parameters": {}},
        },
        "rhino_ping": {
            "type": "function",
            "function": {"name": "rhino_ping", "description": "test", "parameters": {}},
        },
    }
    reg_normal = ToolRegistry(catalog=catalog, agent_mode=False)
    reg_agent = ToolRegistry(catalog=catalog, agent_mode=True)

    normal_names = {s["function"]["name"] for s in reg_normal.get_active_schemas()}
    agent_names = {s["function"]["name"] for s in reg_agent.get_active_schemas()}

    assert "gh_execute_intent" in normal_names
    assert "gh_execute_intent" not in agent_names
    # Both should have rhino_ping
    assert "rhino_ping" in normal_names
    assert "rhino_ping" in agent_names


@test("rhino_command_select/queue moved to command_learning group")
def _():
    from rook.agent.tool_groups import TOOL_GROUPS
    assert "rhino_command_select" not in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_queue" not in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_interactive_prompt" in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_interactive_cancel" in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_interactive_start" not in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_interactive_send" not in TOOL_GROUPS["rhino_commands"]
    assert "rhino_command_select" in TOOL_GROUPS["command_learning"]
    assert "rhino_command_queue" in TOOL_GROUPS["command_learning"]
    assert "rhino_learn_interactive" not in TOOL_GROUPS["command_learning"]
    assert "rhino_learn_variations_interactive" not in TOOL_GROUPS["command_learning"]


# =========================================================================
# D: Seam 3 correction_detected and attempt_number
# =========================================================================

print("\n=== D: Seam 3 Fixes ===")


@test("_failure_counts initializes to empty dict")
def _():
    from rook.agent.base_agent import RookAgent
    agent = RookAgent()
    assert hasattr(agent, "_failure_counts")
    assert agent._failure_counts == {}


@test("_record_observation reads correction_detected from result")
def _():
    from rook.agent.base_agent import RookAgent
    from rook.agent.config import AgentConfig

    agent = RookAgent(config=AgentConfig(observation_recording=True))

    # Mock the metrics store
    with patch("rook.agent.base_agent._get_knowledge_infra") as mock_infra:
        mock_metrics = MagicMock()
        mock_infra.return_value = {"metrics": mock_metrics}

        # Call with correction_detected in result
        result = {"success": True, "correction_detected": True}
        agent._record_observation("gh_connect", {}, result, duration_ms=10.0)

        # Verify metrics.record was called with correction_detected=True
        call_args = mock_metrics.record.call_args
        obs = call_args[0][0]
        assert obs.correction_detected is True


@test("attempt_number increments with consecutive failures")
def _():
    from rook.agent.base_agent import RookAgent
    from rook.agent.config import AgentConfig

    agent = RookAgent(config=AgentConfig(observation_recording=True))

    with patch("rook.agent.base_agent._get_knowledge_infra") as mock_infra:
        mock_metrics = MagicMock()
        mock_infra.return_value = {"metrics": mock_metrics}

        # Simulate 3 failures
        agent._failure_counts["gh_connect"] = 2

        result = {"success": False, "error": "bad"}
        agent._record_observation("gh_connect", {}, result, duration_ms=5.0)

        call_args = mock_metrics.record.call_args
        obs = call_args[0][0]
        # attempt_number = failure_count + 1 = 2 + 1 = 3
        assert obs.attempt_number == 3


@test("first failed call records attempt_number=1 (not 2)")
async def _():
    from rook.agent.base_agent import RookAgent
    from rook.agent.config import AgentConfig

    agent = RookAgent(config=AgentConfig(observation_recording=True))

    # Mock tool_executor to return failure
    agent._tool_executor = AsyncMock(return_value={"success": False, "error": "bad"})

    with patch("rook.agent.base_agent._get_knowledge_infra") as mock_infra:
        mock_metrics = MagicMock()
        mock_infra.return_value = {"metrics": mock_metrics}

        await agent._execute_tool("gh_connect", {})

        call_args = mock_metrics.record.call_args
        obs = call_args[0][0]
        # First call = attempt 1 (failure_counts was 0 at recording time)
        assert obs.attempt_number == 1, f"Expected 1, got {obs.attempt_number}"
        # After recording, failure_counts should be updated to 1
        assert agent._failure_counts["gh_connect"] == 1


@test("attempt_number resets on success (via _execute_tool flow)")
async def _():
    from rook.agent.base_agent import RookAgent
    from rook.agent.config import AgentConfig

    agent = RookAgent(config=AgentConfig(observation_recording=False))

    # Simulate existing failures
    agent._failure_counts["rhino_ping"] = 3

    # Mock tool_executor to return success
    agent._tool_executor = AsyncMock(return_value={"success": True, "data": "pong"})

    await agent._execute_tool("rhino_ping", {})

    # After success, failure count should be cleared
    assert "rhino_ping" not in agent._failure_counts


# =========================================================================
# E: Coverage re-audit
# =========================================================================

print("\n=== E: Coverage Re-audit ===")


@test("Knowledge-wrapped tools are dispatchable (no unknown tool error)")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher, KNOWLEDGE_WRAPPED_TOOLS

    d = ToolDispatcher()

    with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino, \
         patch("rook.learning.gh_knowledge.gh_query_operation") as mock_op, \
         patch("rook.learning.gh_knowledge.get_gh_knowledge_store"):

        mock_op.return_value = {"gotchas": []}
        mock_rhino.return_value = {"success": True, "data": {"success": True}}

        for tool_name in KNOWLEDGE_WRAPPED_TOOLS:
            result = await d.dispatch(tool_name, {"sourceGuid": "a", "targetGuid": "b", "targetParam": "X", "guid": "c", "guids": ["d"], "value": 1})
            assert "Unknown tool" not in str(result.get("data", "")), f"{tool_name} failed dispatch"


@test("All 8 local tools dispatchable via ToolDispatcher")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    d = ToolDispatcher()
    d.register_locals(build_local_tools())

    expected = {
        "knowledge_query", "gh_knowledge_query", "rhino_instances",
        "rhino_execute_intent", "gh_constraints", "rhino_command_select",
        "rhino_command_queue", "gh_canvas_cleanup",
    }
    for name in expected:
        if name in d._local_tools:
            pass  # It's registered
        else:
            raise AssertionError(f"Local tool {name} not registered")


# =========================================================================
# Summary
# =========================================================================

print(f"\n{'='*50}")
print(f"Phase 2 Tests: {passed} passed, {failed} failed")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
