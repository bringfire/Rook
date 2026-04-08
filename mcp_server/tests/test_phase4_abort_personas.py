"""
Phase 4: Abort Wiring + Per-Task Personas
==========================================

Tests for:
- Feature 1: Guardian calls abort() at max_interventions; Conductor calls abort() on bridge-down
- Feature 2: TaskSpec.agent_type, SUBMIT_PLAN_SCHEMA, _resolve_model(), _estimate_cost(), _execute_group()

These tests are deliberately structural and integration-focused:
- They inspect actual class instances and method behavior, not mock scaffolding
- They assert exact values, field presence, and control-flow outcomes
- They cover edge cases (invalid agent_type, steering disabled, below quorum)
"""

import asyncio
import json
import sys
import time
import unittest
from dataclasses import fields as dc_fields
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, call

# --- Path setup ---
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.guardian import Guardian
from rook.agent.conductor import Conductor, ConductorReport
from rook.agent.config import GuardianConfig, ConductorConfig, PlannerConfig
from rook.agent.planner import TaskSpec, Plan, Planner, SUBMIT_PLAN_SCHEMA
from rook.agent.events import AgentEvent, GUARDIAN_INTERVENTION, TOOL_EXEC_END


# =============================================================================
# Helpers
# =============================================================================

def make_mock_agent():
    """Create a mock agent with steer(), abort(), subscribe(), emit_event()."""
    agent = MagicMock()
    agent.steer = MagicMock()
    agent.abort = MagicMock()
    agent.subscribe = MagicMock(return_value=MagicMock())  # returns unsub fn
    agent.emit_event = MagicMock()
    agent.state = "running"
    agent.metrics = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
    return agent


def make_guardian(agent, max_interventions=3, enable_steering=True):
    """Create a Guardian with controllable config."""
    config = GuardianConfig(
        check_interval=1,
        max_consecutive_failures=2,
        max_identical_calls=2,
        max_interventions=max_interventions,
        enable_steering=enable_steering,
    )
    return Guardian(agent, config=config, task_description="test task")


# =============================================================================
# A. Feature 1: Guardian abort wiring
# =============================================================================

class TestGuardianAbort(unittest.TestCase):
    """Guardian must call abort() when max_interventions reached."""

    def test_abort_called_at_max_interventions(self):
        """After max_interventions, agent.abort() must be called exactly once."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=3)

        # Fire enough failures to trigger max_interventions worth of interventions.
        # Guardian._intervene() appends to self._interventions and checks the limit.
        # We need to drive _check() which calls _intervene().
        # Simplest: call _intervene directly to simulate the guardian detecting issues.
        for i in range(3):
            guardian._intervene("stuck", f"Test issue {i}")

        agent.abort.assert_called_once()

    def test_abort_not_called_before_limit(self):
        """With interventions below max, abort() must NOT be called."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=5)

        # Only 3 interventions, limit is 5
        for i in range(3):
            guardian._intervene("stuck", f"Test issue {i}")

        agent.abort.assert_not_called()

    def test_abort_not_called_when_steering_disabled(self):
        """If enable_steering=False, neither steer() nor abort() should be called."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=2, enable_steering=False)

        for i in range(5):
            guardian._intervene("stuck", f"Test issue {i}")

        agent.steer.assert_not_called()
        agent.abort.assert_not_called()

    def test_steer_called_before_abort(self):
        """At the limit, steer() is called with ABORT message, then abort()."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=2)

        guardian._intervene("looping", "First issue")
        guardian._intervene("looping", "Second issue")

        # steer was called for both: first with a regular message, second with ABORT
        assert agent.steer.call_count >= 2, (
            f"Expected at least 2 steer calls, got {agent.steer.call_count}"
        )
        # The abort-triggering steer must contain "ABORT"
        last_steer_arg = agent.steer.call_args_list[-1][0][0]
        assert "ABORT" in last_steer_arg, (
            f"Expected 'ABORT' in steer message, got: {last_steer_arg}"
        )
        agent.abort.assert_called_once()

    def test_abort_called_exactly_at_boundary(self):
        """Abort should fire on the exact Nth intervention, not N+1."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=1)

        # First intervention should immediately hit the limit
        guardian._intervene("stuck", "Single issue")

        agent.abort.assert_called_once()
        # Only one steer call (the ABORT one)
        assert agent.steer.call_count == 1

    def test_abort_is_idempotent(self):
        """Calling abort() multiple times (interventions past limit) must not crash."""
        agent = make_mock_agent()
        guardian = make_guardian(agent, max_interventions=2)

        # Fire 5 interventions — guardian silently drops after max,
        # but abort() should only be called once (at the limit).
        for i in range(5):
            guardian._intervene("stuck", f"Issue {i}")

        # abort() is called exactly once — at intervention #2 (the limit).
        # Subsequent _intervene calls return early due to the >= max guard.
        agent.abort.assert_called_once()


# =============================================================================
# B. Feature 1: Conductor abort wiring
# =============================================================================

class TestConductorAbort(unittest.TestCase):
    """Conductor must call abort() on systemic bridge failure."""

    def test_abort_on_bridge_failure_quorum(self):
        """When 2+ agents are stuck, Conductor aborts all stuck agents."""
        config = ConductorConfig(bridge_failure_quorum=2, dedup_window_seconds=0)
        conductor = Conductor(config=config)

        agent1 = make_mock_agent()
        agent2 = make_mock_agent()
        agent3 = make_mock_agent()

        conductor.register_agent("t1", agent1)
        conductor.register_agent("t2", agent2)
        conductor.register_agent("t3", agent3)

        now = time.time()
        # Inject stuck interventions for agents 1 and 2
        conductor._interventions.extend([
            {"task_id": "t1", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now},
            {"task_id": "t2", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now},
        ])

        conductor._check_systemic_bridge_failure()

        # Agents 1 and 2 should be aborted
        agent1.steer.assert_called_once()
        agent1.abort.assert_called_once()
        agent2.steer.assert_called_once()
        agent2.abort.assert_called_once()
        # Agent 3 was not stuck, should not be touched
        agent3.steer.assert_not_called()
        agent3.abort.assert_not_called()

    def test_no_abort_below_quorum(self):
        """With only 1 stuck agent (quorum=2), no abort should fire."""
        config = ConductorConfig(bridge_failure_quorum=2, dedup_window_seconds=0)
        conductor = Conductor(config=config)

        agent1 = make_mock_agent()
        conductor.register_agent("t1", agent1)

        now = time.time()
        conductor._interventions.append(
            {"task_id": "t1", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now}
        )

        conductor._check_systemic_bridge_failure()

        agent1.abort.assert_not_called()

    def test_abort_only_stuck_not_looping(self):
        """Conductor checks 'stuck' and 'looping' types for bridge failure."""
        config = ConductorConfig(bridge_failure_quorum=2, dedup_window_seconds=0)
        conductor = Conductor(config=config)

        agent1 = make_mock_agent()
        agent2 = make_mock_agent()
        conductor.register_agent("t1", agent1)
        conductor.register_agent("t2", agent2)

        now = time.time()
        conductor._interventions.extend([
            {"task_id": "t1", "type": "looping", "message": "loop", "tool": "", "timestamp": now},
            {"task_id": "t2", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now},
        ])

        conductor._check_systemic_bridge_failure()

        # Both 'stuck' and 'looping' count toward bridge failure detection
        agent1.abort.assert_called_once()
        agent2.abort.assert_called_once()

    def test_stale_interventions_ignored(self):
        """Interventions older than 30s lookback should not trigger abort."""
        config = ConductorConfig(bridge_failure_quorum=2, dedup_window_seconds=0)
        conductor = Conductor(config=config)

        agent1 = make_mock_agent()
        agent2 = make_mock_agent()
        conductor.register_agent("t1", agent1)
        conductor.register_agent("t2", agent2)

        old = time.time() - 60  # 60 seconds ago, beyond 30s lookback
        conductor._interventions.extend([
            {"task_id": "t1", "type": "stuck", "message": "stuck", "tool": "", "timestamp": old},
            {"task_id": "t2", "type": "stuck", "message": "stuck", "tool": "", "timestamp": old},
        ])

        conductor._check_systemic_bridge_failure()

        agent1.abort.assert_not_called()
        agent2.abort.assert_not_called()

    def test_dedup_prevents_double_abort(self):
        """Within dedup window, a second bridge failure should NOT re-abort."""
        config = ConductorConfig(bridge_failure_quorum=2, dedup_window_seconds=120)
        conductor = Conductor(config=config)

        agent1 = make_mock_agent()
        agent2 = make_mock_agent()
        conductor.register_agent("t1", agent1)
        conductor.register_agent("t2", agent2)

        now = time.time()
        conductor._interventions.extend([
            {"task_id": "t1", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now},
            {"task_id": "t2", "type": "stuck", "message": "stuck", "tool": "", "timestamp": now},
        ])

        # First check triggers abort
        conductor._check_systemic_bridge_failure()
        assert agent1.abort.call_count == 1
        assert agent2.abort.call_count == 1

        # Reset mocks to track new calls only
        agent1.abort.reset_mock()
        agent2.abort.reset_mock()

        # Second check within dedup window should NOT re-abort
        conductor._check_systemic_bridge_failure()
        agent1.abort.assert_not_called()
        agent2.abort.assert_not_called()


# =============================================================================
# C. Feature 2: TaskSpec agent_type field
# =============================================================================

class TestTaskSpecAgentType(unittest.TestCase):
    """TaskSpec must have agent_type field with correct default."""

    def test_default_agent_type_is_worker(self):
        spec = TaskSpec(task_id="t1", description="test")
        assert spec.agent_type == "worker"

    def test_explicit_specialist(self):
        spec = TaskSpec(task_id="t1", description="test", agent_type="specialist")
        assert spec.agent_type == "specialist"

    def test_agent_type_is_dataclass_field(self):
        field_names = {f.name for f in dc_fields(TaskSpec)}
        assert "agent_type" in field_names


# =============================================================================
# D. Feature 2: SUBMIT_PLAN_SCHEMA contains agent_type
# =============================================================================

class TestSchemaAgentType(unittest.TestCase):
    """SUBMIT_PLAN_SCHEMA must include agent_type with enum, not required."""

    def _get_task_properties(self):
        """Navigate schema to task item properties."""
        return (
            SUBMIT_PLAN_SCHEMA["function"]["parameters"]["properties"]["tasks"]
            ["items"]["properties"]
        )

    def test_agent_type_in_schema(self):
        props = self._get_task_properties()
        assert "agent_type" in props, (
            f"agent_type missing from schema. Keys: {list(props.keys())}"
        )

    def test_agent_type_enum_values(self):
        props = self._get_task_properties()
        assert props["agent_type"]["enum"] == ["worker", "specialist", "scripter", "explorer"]

    def test_agent_type_not_required(self):
        required = (
            SUBMIT_PLAN_SCHEMA["function"]["parameters"]["properties"]["tasks"]
            ["items"]["required"]
        )
        assert "agent_type" not in required

    def test_agent_type_is_string_type(self):
        props = self._get_task_properties()
        assert props["agent_type"]["type"] == "string"


# =============================================================================
# E. Feature 2: _resolve_model()
# =============================================================================

class TestResolveModel(unittest.TestCase):
    """Planner._resolve_model() must map agent types to correct models."""

    def _make_planner(self):
        config = PlannerConfig(
            planner_model="sonnet-for-test",
            worker_model="haiku-for-test",
        )
        return Planner(config=config, tool_executor=MagicMock())

    def test_worker_returns_worker_model(self):
        """Worker uses fast path — returns config.worker_model directly."""
        planner = self._make_planner()
        assert planner._resolve_model("worker") == "haiku-for-test"

    def test_specialist_resolves_via_persona(self):
        """Specialist resolves through persona→profile to Sonnet."""
        planner = self._make_planner()
        result = planner._resolve_model("specialist")
        # With real persona files: specialist→model_role "specialist"→
        # get_models()→ModelSet.specialist = Sonnet (FALLBACK_MODELS)
        from rook.agent.model_profiles import FALLBACK_MODELS
        assert result == FALLBACK_MODELS["specialist"]

    def test_unknown_type_degrades_to_worker_role(self):
        """Unknown/garbage agent_type degrades to worker role via persona defaults."""
        planner = self._make_planner()
        from rook.agent.model_profiles import FALLBACK_MODELS
        for bad in ["garbage", "", "totally_nonexistent_xyz"]:
            result = planner._resolve_model(bad)
            # Persona defaults: model_role="worker" → profile worker model
            assert result == FALLBACK_MODELS["worker"], (
                f"Expected FALLBACK worker for {bad!r}, got {result}"
            )


# =============================================================================
# F. Feature 2: _parse_plan() extracts agent_type
# =============================================================================

class TestParsePlanAgentType(unittest.TestCase):
    """_parse_plan must extract, validate, and default agent_type."""

    def _make_planner(self):
        config = PlannerConfig()
        return Planner(config=config, tool_executor=MagicMock())

    def _make_plan_data(self, agent_type=None):
        td = {
            "task_id": "t1",
            "description": "Test task",
        }
        if agent_type is not None:
            td["agent_type"] = agent_type
        return {
            "goal": "Test",
            "tasks": [td],
            "execution_groups": [["t1"]],
        }

    def test_default_when_absent(self):
        planner = self._make_planner()
        plan = planner._parse_plan(self._make_plan_data())
        assert plan.tasks[0].agent_type == "worker"

    def test_explicit_specialist(self):
        planner = self._make_planner()
        plan = planner._parse_plan(self._make_plan_data(agent_type="specialist"))
        assert plan.tasks[0].agent_type == "specialist"

    def test_explicit_worker(self):
        planner = self._make_planner()
        plan = planner._parse_plan(self._make_plan_data(agent_type="worker"))
        assert plan.tasks[0].agent_type == "worker"

    def test_invalid_sanitized_to_worker(self):
        """Invalid agent_type values get sanitized to 'worker'."""
        planner = self._make_planner()
        # Infrastructure personas (planner, guardian) are not assignable
        for bad_value in ["expert", "SPECIALIST", "haiku", 123, None, "",
                          "planner", "guardian"]:
            plan = planner._parse_plan(self._make_plan_data(agent_type=bad_value))
            assert plan.tasks[0].agent_type == "worker", (
                f"Expected 'worker' for agent_type={bad_value!r}, "
                f"got '{plan.tasks[0].agent_type}'"
            )

    def test_mixed_agent_types_in_plan(self):
        """Plan with multiple tasks: each preserves its own agent_type."""
        planner = self._make_planner()
        data = {
            "goal": "Mixed",
            "tasks": [
                {"task_id": "t1", "description": "Simple", "agent_type": "worker"},
                {"task_id": "t2", "description": "Complex", "agent_type": "specialist"},
                {"task_id": "t3", "description": "Default"},
            ],
            "execution_groups": [["t1", "t2"], ["t3"]],
        }
        plan = planner._parse_plan(data)
        assert plan.tasks[0].agent_type == "worker"
        assert plan.tasks[1].agent_type == "specialist"
        assert plan.tasks[2].agent_type == "worker"  # default


# =============================================================================
# G. Feature 2: _estimate_cost() differential pricing
# =============================================================================

class TestEstimateCostDifferential(unittest.TestCase):
    """Cost estimation must charge more for specialist tasks."""

    def _make_planner(self):
        config = PlannerConfig()
        return Planner(config=config, tool_executor=MagicMock())

    def test_worker_cost_haiku_pricing(self):
        """Worker task uses Haiku pricing: $0.80/M input, $4.00/M output."""
        planner = self._make_planner()
        plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="test", estimated_turns=10)],
        )
        cost = planner._estimate_cost(plan)
        # 10 turns * 1000 tokens * $0.80/M = $0.008 input
        # 10 turns * 200 tokens * $4.00/M = $0.008 output
        expected = round(0.008 + 0.008, 6)
        assert cost == expected, f"Worker cost {cost} != expected {expected}"

    def test_specialist_cost_sonnet_pricing(self):
        """Specialist task uses Sonnet pricing: $3.00/M input, $15.00/M output."""
        planner = self._make_planner()
        plan = Plan(
            goal="test",
            tasks=[TaskSpec(
                task_id="t1", description="test",
                estimated_turns=10, agent_type="specialist",
            )],
        )
        cost = planner._estimate_cost(plan)
        # 10 turns * 1000 tokens * $3.00/M = $0.03 input
        # 10 turns * 200 tokens * $15.00/M = $0.03 output
        expected = round(0.03 + 0.03, 6)
        assert cost == expected, f"Specialist cost {cost} != expected {expected}"

    def test_specialist_costs_more_than_worker(self):
        """Same turns, specialist should cost strictly more."""
        planner = self._make_planner()
        worker_plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="test", estimated_turns=15)],
        )
        specialist_plan = Plan(
            goal="test",
            tasks=[TaskSpec(
                task_id="t1", description="test",
                estimated_turns=15, agent_type="specialist",
            )],
        )
        worker_cost = planner._estimate_cost(worker_plan)
        specialist_cost = planner._estimate_cost(specialist_plan)
        assert specialist_cost > worker_cost, (
            f"Specialist ({specialist_cost}) should cost more than worker ({worker_cost})"
        )

    def test_mixed_plan_cost(self):
        """Plan with worker + specialist: total equals sum of individual costs."""
        planner = self._make_planner()
        mixed_plan = Plan(
            goal="test",
            tasks=[
                TaskSpec(task_id="t1", description="w", estimated_turns=10),
                TaskSpec(task_id="t2", description="s", estimated_turns=10, agent_type="specialist"),
            ],
        )
        worker_only = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="w", estimated_turns=10)],
        )
        specialist_only = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t2", description="s", estimated_turns=10, agent_type="specialist")],
        )
        mixed_cost = planner._estimate_cost(mixed_plan)
        sum_cost = round(
            planner._estimate_cost(worker_only) + planner._estimate_cost(specialist_only), 6
        )
        assert mixed_cost == sum_cost, (
            f"Mixed ({mixed_cost}) != sum ({sum_cost})"
        )


# =============================================================================
# H. Feature 2: _execute_group() model resolution
# =============================================================================

class TestExecuteGroupModel(unittest.TestCase):
    """_execute_group passes resolved model per task."""

    def _make_planner(self):
        config = PlannerConfig(
            planner_model="sonnet-test",
            worker_model="haiku-test",
        )
        planner = Planner(config=config, tool_executor=MagicMock())
        # Override _resolve_model to return predictable test values
        # (isolates from persona/profile system for unit testing)
        planner._resolve_model = lambda at: (
            "haiku-test" if at == "worker" else "sonnet-test"
        )
        return planner

    def test_single_worker_task_uses_worker_model(self):
        """Single worker task: run_task gets worker_model and agent_type."""
        planner = self._make_planner()
        task = TaskSpec(task_id="t1", description="test", agent_type="worker")

        with patch("rook.agent.spawn.run_task", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock()
            asyncio.run(planner._execute_group([task]))
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs["model"] == "haiku-test", (
                f"Expected haiku-test, got {kwargs['model']}"
            )
            assert kwargs["agent_type"] == "worker"

    def test_single_specialist_task_uses_planner_model(self):
        """Single specialist task: run_task gets planner_model."""
        planner = self._make_planner()
        task = TaskSpec(task_id="t1", description="test", agent_type="specialist")

        with patch("rook.agent.spawn.run_task", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MagicMock()
            asyncio.run(planner._execute_group([task]))
            _, kwargs = mock_run.call_args
            assert kwargs["model"] == "sonnet-test", (
                f"Expected sonnet-test, got {kwargs['model']}"
            )
            assert kwargs["agent_type"] == "specialist"

    def test_swarm_per_task_model_in_dicts(self):
        """Swarm path: each task dict must have 'model' matching its agent_type."""
        planner = self._make_planner()
        tasks = [
            TaskSpec(task_id="t1", description="simple", agent_type="worker"),
            TaskSpec(task_id="t2", description="complex", agent_type="specialist"),
        ]

        with patch("rook.agent.spawn.run_swarm", new_callable=AsyncMock) as mock_swarm:
            mock_result = MagicMock()
            mock_result.results = [MagicMock(), MagicMock()]
            mock_swarm.return_value = mock_result

            asyncio.run(planner._execute_group(tasks))

            mock_swarm.assert_called_once()
            task_dicts = mock_swarm.call_args[0][0]  # first positional arg

            assert len(task_dicts) == 2
            assert task_dicts[0]["model"] == "haiku-test", (
                f"Worker task model: {task_dicts[0]['model']}"
            )
            assert task_dicts[1]["model"] == "sonnet-test", (
                f"Specialist task model: {task_dicts[1]['model']}"
            )
            assert task_dicts[0]["agent_type"] == "worker"
            assert task_dicts[1]["agent_type"] == "specialist"

    def test_swarm_fallback_model_is_worker(self):
        """Swarm path: the global model= kwarg to run_swarm is worker_model."""
        planner = self._make_planner()
        tasks = [
            TaskSpec(task_id="t1", description="a", agent_type="worker"),
            TaskSpec(task_id="t2", description="b", agent_type="specialist"),
        ]

        with patch("rook.agent.spawn.run_swarm", new_callable=AsyncMock) as mock_swarm:
            mock_result = MagicMock()
            mock_result.results = [MagicMock(), MagicMock()]
            mock_swarm.return_value = mock_result

            asyncio.run(planner._execute_group(tasks))

            _, kwargs = mock_swarm.call_args
            assert kwargs["model"] == "haiku-test", (
                f"Expected fallback model=haiku-test, got {kwargs['model']}"
            )


# =============================================================================
# I. PLANNER.md Agent Types section
# =============================================================================

class TestPlannerMdAgentTypes(unittest.TestCase):
    """PLANNER.md must have Agent Types section in correct position."""

    @classmethod
    def setUpClass(cls):
        md_path = REPO / "src" / "rook" / "agent" / "prompts" / "PLANNER.md"
        cls.content = md_path.read_text(encoding="utf-8")
        cls.lines = cls.content.split("\n")

    def test_agent_types_section_exists(self):
        assert "## Agent Types" in self.content

    def test_section_order(self):
        """Agent Types must come after Tool Groups and before Workspace Assets."""
        tool_groups_idx = None
        agent_types_idx = None
        workspace_idx = None
        for i, line in enumerate(self.lines):
            if line.strip().startswith("## Tool Groups"):
                tool_groups_idx = i
            elif line.strip().startswith("## Agent Types"):
                agent_types_idx = i
            elif line.strip().startswith("## Workspace Assets"):
                workspace_idx = i

        assert tool_groups_idx is not None, "Missing '## Tool Groups'"
        assert agent_types_idx is not None, "Missing '## Agent Types'"
        assert workspace_idx is not None, "Missing '## Workspace Assets'"
        assert tool_groups_idx < agent_types_idx < workspace_idx, (
            f"Order wrong: Tool Groups={tool_groups_idx}, "
            f"Agent Types={agent_types_idx}, Workspace Assets={workspace_idx}"
        )

    def test_table_has_all_agent_types(self):
        """The table must list all 4 assignable agent type rows."""
        assert "| `worker`" in self.content
        assert "| `specialist`" in self.content
        assert "| `scripter`" in self.content
        assert "| `explorer`" in self.content

    def test_table_mentions_models(self):
        """Table should reference Haiku and Sonnet."""
        assert "Haiku" in self.content
        assert "Sonnet" in self.content


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
