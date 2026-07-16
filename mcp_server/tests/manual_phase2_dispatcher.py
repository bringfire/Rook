"""
Phase 2 ToolDispatcher Tests
=============================

Verifies:
A: Knowledge middleware retirement compatibility
B: Local tool smoke tests
C: Tier 0 agent_mode check
D: Seam 3 correction_detected and attempt_number
E: Coverage re-audit

NOTE: Legacy standalone script, NOT a pytest module. The `@test(...)`
decorator runs each check at import and the module calls `sys.exit()` on
failure, which aborts pytest collection. Renamed `manual_*` (not `test_*`)
so pytest does not collect it. Run directly: `python manual_phase2_dispatcher.py`.
"""

import asyncio
import sys
import os
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


@test("KNOWLEDGE_WRAPPED_TOOLS remains empty after gh_edit consolidation")
def _():
    from rook.agent.tool_dispatcher import KNOWLEDGE_WRAPPED_TOOLS
    assert KNOWLEDGE_WRAPPED_TOOLS == {}


@test("No legacy knowledge-wrapper context builders remain")
def _():
    from rook.agent.tool_dispatcher import KNOWLEDGE_WRAPPED_TOOLS
    assert list(KNOWLEDGE_WRAPPED_TOOLS) == []


@test("Retired legacy wrapper identities are not dispatcher-visible")
def _():
    from rook.agent.tool_dispatcher import ToolDispatcher

    d = ToolDispatcher()
    assert {"gh_connect", "gh_set_value"}.isdisjoint(d.all_known_tools)


# =========================================================================
# B: Local tool smoke tests
# =========================================================================

print("\n=== B: Local Tool Smoke Tests ===")


@test("build_local_tools() includes 4 new tools")
def _():
    from rook.agent.tool_dispatcher import build_local_tools
    tools = build_local_tools()
    new_tools = {"gh_constraints", "rhino_command_select", "rhino_command_queue", "gh_canvas_cleanup"}
    for t in new_tools:
        assert t in tools, f"Missing local tool: {t}"
    assert "rhino_execute_intent" not in tools, \
        "EXPECTED_RED:T2:MANUAL_PHASE2 build_local_tools exposes contained identity"


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


@test("AGENT_TIER_0 preserves its independent dispatch exclusions")
def _():
    from rook.agent.tool_groups import (
        AGENT_TIER_0,
        LOCAL_TIER_0_DISPATCH_EXCLUSIONS,
        TIER_0,
    )

    assert "gh_execute_intent" in TIER_0
    assert "gh_execute_intent" not in AGENT_TIER_0
    assert AGENT_TIER_0.isdisjoint(LOCAL_TIER_0_DISPATCH_EXCLUSIONS)


@test("ToolRegistry excludes contained gh_execute_intent in every agent mode")
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

    assert "gh_execute_intent" not in normal_names, \
        "EXPECTED_RED:T2:MANUAL_PHASE2 normal registry exposes contained identity"
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
    assert "rhino_command_experiment" not in TOOL_GROUPS["command_learning"]
    assert "rhino_learn_interactive" not in TOOL_GROUPS["command_learning"]
    assert "rhino_learn_next" not in TOOL_GROUPS["command_learning"]
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


@test("Supported local tools dispatchable and contained local absent")
async def _():
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    d = ToolDispatcher()
    d.register_locals(build_local_tools())

    expected = {
        "knowledge_query", "gh_knowledge_query", "rhino_instances",
        "gh_constraints", "rhino_command_select",
        "rhino_command_queue", "gh_canvas_cleanup",
    }
    for name in expected:
        if name in d._local_tools:
            pass  # It's registered
        else:
            raise AssertionError(f"Local tool {name} not registered")
    assert "rhino_execute_intent" not in d._local_tools


# =========================================================================
# Summary
# =========================================================================

print(f"\n{'='*50}")
print(f"Phase 2 Tests: {passed} passed, {failed} failed")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
