"""
Tests for Agent Orchestration Gaps
===================================

Tests for result carriage, postcondition checkpoints, and ask() escalation.
Covers Phases 1-3 of the orchestration gaps plan.
"""

import asyncio
import json
import pytest
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

from rook.agent.events import (
    AgentEvent,
    TOOL_EXEC_END,
    CHECKPOINT_PASS,
    CHECKPOINT_FAIL,
    AGENT_ASK,
)
from rook.agent.spawn import SpawnResult, SwarmResult
from rook.agent.base_agent import _RHINO_CREATION_TOOLS


# =============================================================================
# Phase 1: Result Carriage
# =============================================================================

class TestSpawnResultExtensions:
    """SpawnResult now carries created_ids and phase_context."""

    def test_default_fields(self):
        """New fields default to empty."""
        r = SpawnResult(task_id="t1", status="success", task="test")
        assert r.created_ids == []
        assert r.phase_context == {}

    def test_with_created_ids(self):
        """Explicit created_ids are preserved."""
        r = SpawnResult(
            task_id="t1",
            status="success",
            task="test",
            created_ids=["guid-1", "guid-2"],
        )
        assert r.created_ids == ["guid-1", "guid-2"]

    def test_serialization_includes_new_fields(self):
        """to_dict includes created_ids and phase_context via asdict."""
        r = SpawnResult(
            task_id="t1",
            status="success",
            task="test",
            created_ids=["guid-abc"],
            phase_context={"checkpoint_warnings": ["missing object"]},
        )
        d = r.to_dict()
        assert d["created_ids"] == ["guid-abc"]
        assert d["phase_context"]["checkpoint_warnings"] == ["missing object"]
        # Verify JSON serializable
        json.dumps(d)

    def test_to_json_round_trip(self):
        """to_json produces valid JSON with new fields."""
        r = SpawnResult(
            task_id="t1",
            status="success",
            task="test",
            created_ids=["a", "b"],
        )
        parsed = json.loads(r.to_json())
        assert parsed["created_ids"] == ["a", "b"]

    def test_backward_compatible(self):
        """Existing code that doesn't pass new fields still works."""
        r = SpawnResult(task_id="t1", status="error", task="old_task")
        d = r.to_dict()
        assert "created_ids" in d
        assert d["created_ids"] == []


class TestRhinoCreationTools:
    """_RHINO_CREATION_TOOLS frozenset in base_agent.py."""

    def test_is_frozenset(self):
        assert isinstance(_RHINO_CREATION_TOOLS, frozenset)

    def test_contains_expected_tools(self):
        expected = {"rhino_create", "rhino_boolean", "rhino_loft", "rhino_sweep", "rhino_extrude"}
        assert _RHINO_CREATION_TOOLS == expected

    def test_excludes_read_tools(self):
        """Read endpoints must NOT be in creation tools."""
        for tool in ["rhino_objects", "rhino_geometry", "rhino_layers", "rhino_document"]:
            assert tool not in _RHINO_CREATION_TOOLS

    def test_excludes_gh_tools(self):
        """GH tools use a different ID namespace — never in creation tools."""
        for tool in ["gh_edit", "gh_snapshot", "gh_execute_intent"]:
            assert tool not in _RHINO_CREATION_TOOLS


class TestFormatPriorResults:
    """Planner._format_prior_results static method."""

    def test_empty_results(self):
        from rook.agent.planner import Planner
        assert Planner._format_prior_results([]) == ""

    def test_single_result(self):
        from rook.agent.planner import Planner
        r = SpawnResult(
            task_id="t1",
            status="success",
            task="test",
            summary="Created 3 walls",
            created_ids=["guid-1"],
        )
        text = Planner._format_prior_results([r])
        assert "## Prior Task Results" in text
        assert "t1" in text
        assert "success" in text
        assert "guid-1" in text

    def test_with_checkpoint_warnings(self):
        from rook.agent.planner import Planner
        r = SpawnResult(
            task_id="t2",
            status="error",
            task="test",
            summary="Failed",
            phase_context={"checkpoint_warnings": ["missing geometry"]},
        )
        text = Planner._format_prior_results([r])
        assert "checkpoint_warnings" in text.lower() or "Checkpoint warnings" in text
        assert "missing geometry" in text

    def test_summary_truncation(self):
        """Summaries are capped at 300 chars."""
        from rook.agent.planner import Planner
        r = SpawnResult(
            task_id="t3",
            status="success",
            task="test",
            summary="x" * 500,
        )
        text = Planner._format_prior_results([r])
        # The summary in the output should not contain the full 500 chars
        assert len(text) < 600

    def test_created_ids_capped_at_20(self):
        """At most 20 created IDs are shown."""
        from rook.agent.planner import Planner
        r = SpawnResult(
            task_id="t4",
            status="success",
            task="test",
            created_ids=[f"guid-{i}" for i in range(30)],
        )
        text = Planner._format_prior_results([r])
        # guid-20 through guid-29 should NOT appear
        assert "guid-20" not in text


# =============================================================================
# Phase 2: Postcondition Checkpoints
# =============================================================================

class TestCheckpointResult:
    """CheckpointResult dataclass."""

    def test_construction(self):
        from rook.agent.planner import CheckpointResult
        cr = CheckpointResult(group_index=0, passed=True)
        assert cr.group_index == 0
        assert cr.passed is True
        assert cr.checks == []
        assert cr.warnings == []

    def test_with_warnings(self):
        from rook.agent.planner import CheckpointResult
        cr = CheckpointResult(
            group_index=1,
            passed=False,
            checks=[{"type": "objects_exist", "passed": False}],
            warnings=["t1: created object guid-1 not found"],
        )
        assert not cr.passed
        assert len(cr.warnings) == 1


class TestEvaluatePostcondition:
    """Planner._evaluate_postcondition with mocked bridge calls."""

    @pytest.fixture
    def planner(self):
        from rook.agent.planner import Planner
        from rook.agent.config import PlannerConfig
        config = PlannerConfig()
        return Planner(config)

    @pytest.mark.asyncio
    async def test_objects_on_layer_pass(self, planner):
        """Uses real /objects shape: data.totalCount + data.objects."""
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {
                "success": True,
                "data": {
                    "totalCount": 3,
                    "count": 3,
                    "offset": 0,
                    "limit": 100,
                    "objects": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                },
            }
            result = await planner._evaluate_postcondition(
                {"type": "objects_on_layer", "layer": "Walls", "min_count": 2},
                [],
            )
            assert result["passed"] is True
            assert "3" in result["detail"]

    @pytest.mark.asyncio
    async def test_objects_on_layer_fail(self, planner):
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {
                "success": True,
                "data": {
                    "totalCount": 1,
                    "count": 1,
                    "offset": 0,
                    "limit": 100,
                    "objects": [{"id": "a"}],
                },
            }
            result = await planner._evaluate_postcondition(
                {"type": "objects_on_layer", "layer": "Walls", "min_count": 3},
                [],
            )
            assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_objects_exist_pass(self, planner):
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {"success": True, "data": {"id": "guid-1"}}
            result = await planner._evaluate_postcondition(
                {"type": "objects_exist"},
                ["guid-1"],
            )
            assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_objects_exist_fail(self, planner):
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {"success": False, "data": "Not found"}
            result = await planner._evaluate_postcondition(
                {"type": "objects_exist"},
                ["guid-missing"],
            )
            assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_objects_exist_empty(self, planner):
        """No IDs to verify → passes."""
        result = await planner._evaluate_postcondition(
            {"type": "objects_exist"},
            [],
        )
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_no_gh_errors_pass(self, planner):
        """Uses real /gh/errors shape: data.ErrorCount."""
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {
                "success": True,
                "data": {
                    "TotalComponents": 5,
                    "ErrorCount": 0,
                    "WarningCount": 0,
                    "Errors": [],
                    "Warnings": [],
                },
            }
            result = await planner._evaluate_postcondition(
                {"type": "no_gh_errors"},
                [],
            )
            assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_no_gh_errors_fail(self, planner):
        """Uses real /gh/errors shape: ErrorCount > 0 means failure."""
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {
                "success": True,
                "data": {
                    "TotalComponents": 5,
                    "ErrorCount": 2,
                    "WarningCount": 1,
                    "Errors": [
                        {"Name": "MeshBrep", "Errors": ["Input is null"]},
                        {"Name": "BoolUnion", "Errors": ["No valid input"]},
                    ],
                    "Warnings": [{"Name": "Panel", "Warnings": ["Unused"]}],
                },
            }
            result = await planner._evaluate_postcondition(
                {"type": "no_gh_errors"},
                [],
            )
            assert result["passed"] is False
            assert "2" in result["detail"]

    @pytest.mark.asyncio
    async def test_no_gh_errors_endpoint_failure(self, planner):
        """GH errors endpoint failure → check FAILS (not passes)."""
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.return_value = {"success": False, "data": "endpoint error"}
            result = await planner._evaluate_postcondition(
                {"type": "no_gh_errors"},
                [],
            )
            assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_unknown_type_passes(self, planner):
        """Unknown postcondition types pass gracefully."""
        result = await planner._evaluate_postcondition(
            {"type": "something_new"},
            [],
        )
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_bridge_error_fails_check(self, planner):
        """Bridge errors FAIL the check — verification exists to catch problems."""
        with patch("rook.bridge.call_rhino", new_callable=AsyncMock) as mock_bridge:
            mock_bridge.side_effect = ConnectionError("bridge down")
            result = await planner._evaluate_postcondition(
                {"type": "objects_on_layer", "layer": "X"},
                [],
            )
            assert result["passed"] is False
            assert "bridge down" in result["detail"]


class TestTaskSpecPostconditions:
    """TaskSpec now includes postconditions."""

    def test_default_empty(self):
        from rook.agent.planner import TaskSpec
        ts = TaskSpec(task_id="t1", description="do thing")
        assert ts.postconditions == []

    def test_with_postconditions(self):
        from rook.agent.planner import TaskSpec
        ts = TaskSpec(
            task_id="t1",
            description="create walls",
            postconditions=[
                {"type": "objects_on_layer", "layer": "Walls", "min_count": 4},
                {"type": "no_gh_errors"},
            ],
        )
        assert len(ts.postconditions) == 2
        assert ts.postconditions[0]["type"] == "objects_on_layer"


# =============================================================================
# Phase 3: ask() Escalation
# =============================================================================

class TestAskHuman:
    """RookAgent.ask_human / resolve_ask / pending_ask."""

    @pytest.fixture
    def agent(self):
        from rook.agent.base_agent import RookAgent
        from rook.agent.config import AgentConfig
        config = AgentConfig()
        return RookAgent(config=config)

    def test_initial_state(self, agent):
        """No pending ask at startup."""
        assert agent.pending_ask is None

    @pytest.mark.asyncio
    async def test_ask_and_resolve(self, agent):
        """ask_human blocks until resolve_ask delivers an answer."""
        async def _answer_later():
            await asyncio.sleep(0.05)
            assert agent.pending_ask is not None
            assert "which layer" in agent.pending_ask["question"]
            agent.resolve_ask("Use Layer::Walls")

        task = asyncio.create_task(_answer_later())
        answer = await agent.ask_human("which layer?", context="creating walls")
        await task
        assert answer == "Use Layer::Walls"
        assert agent.pending_ask is None

    @pytest.mark.asyncio
    async def test_ask_timeout(self, agent):
        """ask_human returns timeout fallback when no answer arrives."""
        agent._ask_timeout = 0.1  # 100ms for test speed
        answer = await agent.ask_human("will this time out?")
        assert "No human response" in answer
        assert agent.pending_ask is None

    def test_resolve_with_no_pending(self, agent):
        """resolve_ask returns False when nothing is pending."""
        assert agent.resolve_ask("unsolicited") is False

    @pytest.mark.asyncio
    async def test_ask_emits_event(self, agent):
        """ask_human emits an AGENT_ASK event."""
        events = []
        agent.subscribe(lambda e: events.append(e))
        agent._ask_timeout = 0.05

        await agent.ask_human("test question")

        ask_events = [e for e in events if e.type == AGENT_ASK]
        assert len(ask_events) == 1
        assert ask_events[0].data["question"] == "test question"


class TestAgentAnswer:
    """_handle_agent_answer in server.py."""

    def test_missing_params(self):
        from rook.server import _handle_agent_answer
        result = _handle_agent_answer({"agent_id": "", "answer": ""})
        assert result["success"] is False

    def test_unknown_agent(self):
        from rook.server import _handle_agent_answer
        result = _handle_agent_answer({"agent_id": "nonexistent", "answer": "hello"})
        assert result["success"] is False
        assert "Unknown" in result["data"]

    def test_agent_without_ask_support(self):
        """Agent object that doesn't have resolve_ask."""
        import rook.server as srv
        old_agents = srv._active_agents.copy()
        try:
            srv._active_agents["test_agent"] = {
                "agent": object(),  # Plain object, no resolve_ask
                "status": "running",
            }
            result = srv._handle_agent_answer({"agent_id": "test_agent", "answer": "hi"})
            assert result["success"] is False
        finally:
            srv._active_agents = old_agents

    def test_no_pending_question(self):
        """Agent with resolve_ask but no pending question."""
        import rook.server as srv
        old_agents = srv._active_agents.copy()
        try:
            mock_agent = MagicMock()
            mock_agent.resolve_ask.return_value = False
            srv._active_agents["test_agent"] = {
                "agent": mock_agent,
                "status": "running",
            }
            result = srv._handle_agent_answer({"agent_id": "test_agent", "answer": "hi"})
            assert result["success"] is False
            assert "no pending" in result["data"].lower()
        finally:
            srv._active_agents = old_agents

    def test_successful_answer(self):
        """Agent receives the answer successfully."""
        import rook.server as srv
        old_agents = srv._active_agents.copy()
        try:
            mock_agent = MagicMock()
            mock_agent.resolve_ask.return_value = True
            srv._active_agents["test_agent"] = {
                "agent": mock_agent,
                "status": "running",
            }
            result = srv._handle_agent_answer({"agent_id": "test_agent", "answer": "do X"})
            assert result["success"] is True
            mock_agent.resolve_ask.assert_called_once_with("do X")
        finally:
            srv._active_agents = old_agents


# =============================================================================
# Phase 2 + 1 Integration: Checkpoint on post-retry results
# =============================================================================

class TestExecuteLoopWithCheckpoint:
    """Verify the execute loop runs checkpoint AFTER retry."""

    @pytest.mark.asyncio
    async def test_checkpoint_runs_on_final_results(self):
        """When a task fails then succeeds on retry, checkpoint sees success."""
        from rook.agent.planner import Planner, Plan, TaskSpec, CheckpointResult
        from rook.agent.config import PlannerConfig

        config = PlannerConfig(auto_retry=True)
        planner = Planner(config)

        # Track checkpoint calls
        checkpoint_calls = []

        async def mock_checkpoint(gi, results, tasks):
            statuses = [r.status for r in results]
            checkpoint_calls.append({"group": gi, "statuses": statuses})
            return CheckpointResult(group_index=gi, passed=True)

        planner._run_checkpoint = mock_checkpoint

        # Mock _execute_group: first call returns failure, retry returns success
        call_count = [0]

        async def mock_execute_group(tasks, prior_results=None, on_agent_created=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return [SpawnResult(task_id="t1", status="error", task="fail first")]
            else:
                return [SpawnResult(task_id="t1", status="success", task="succeed retry")]

        planner._execute_group = mock_execute_group

        plan = Plan(
            goal="test",
            tasks=[TaskSpec(task_id="t1", description="do thing", retry_on_failure=True)],
            execution_groups=[["t1"]],
        )

        result = await planner.execute(plan)

        # Checkpoint should see the post-retry success, not the initial failure
        assert len(checkpoint_calls) == 1
        assert checkpoint_calls[0]["statuses"] == ["success"]


class TestCreatedIdExtraction:
    """Verify typed ID extraction: only Rhino write tools produce created_ids."""

    def _make_event(self, tool_name, result_data):
        """Simulate what base_agent does at TOOL_EXEC_END."""
        _created_ids = []
        if tool_name in _RHINO_CREATION_TOOLS and isinstance(result_data, dict):
            _data = result_data.get("data", {})
            if isinstance(_data, dict):
                _oid = _data.get("id")
                if _oid and isinstance(_oid, str):
                    _created_ids.append(_oid)
        return _created_ids

    def test_rhino_create_produces_id(self):
        ids = self._make_event("rhino_create", {"success": True, "data": {"id": "guid-abc"}})
        assert ids == ["guid-abc"]

    def test_rhino_boolean_produces_id(self):
        ids = self._make_event("rhino_boolean", {"success": True, "data": {"id": "guid-bool"}})
        assert ids == ["guid-bool"]

    def test_rhino_objects_does_not_produce_id(self):
        """Read endpoint returns id but must NOT be tracked."""
        ids = self._make_event("rhino_objects", {"success": True, "data": {"id": "guid-read"}})
        assert ids == []

    def test_rhino_geometry_does_not_produce_id(self):
        ids = self._make_event("rhino_geometry", {"success": True, "data": {"id": "guid-geo"}})
        assert ids == []

    def test_gh_edit_does_not_produce_id(self):
        """GH tools use different ID namespace — never in created_ids."""
        ids = self._make_event("gh_edit", {"success": True, "data": {"Guid": "gh-guid"}})
        assert ids == []

    def test_missing_data_id(self):
        """Tool in allowlist but result missing data.id → no ID."""
        ids = self._make_event("rhino_create", {"success": True, "data": {}})
        assert ids == []

    def test_non_dict_result(self):
        """Non-dict result → no crash."""
        ids = self._make_event("rhino_create", "some string")
        assert ids == []


class TestRunSwarmOnAgentCreated:
    """run_swarm fans out on_agent_created to both Conductor and external callback."""

    @pytest.mark.asyncio
    async def test_external_callback_called(self):
        """on_agent_created parameter receives (tid, agent) for each worker."""
        from rook.agent.spawn import run_swarm

        external_calls = []

        def _external_cb(tid, agent):
            external_calls.append(tid)

        # Mock run_task to avoid actually running agents
        async def mock_run_task(task, **kwargs):
            # Simulate on_agent_created being called
            cb = kwargs.get("on_agent_created")
            if cb:
                cb(kwargs.get("task_id", "?"), MagicMock())
            return SpawnResult(
                task_id=kwargs.get("task_id", "?"),
                status="success",
                task=task,
            )

        with patch("rook.agent.spawn.run_task", side_effect=mock_run_task):
            with patch("rook.agent.spawn.Conductor") as MockConductor:
                mock_conductor = MockConductor.return_value
                mock_conductor.start = AsyncMock()
                mock_conductor.stop = AsyncMock()
                mock_conductor.register_agent = MagicMock()
                mock_conductor.add_result = MagicMock()
                mock_conductor.report.return_value = MagicMock(to_dict=lambda: {})

                result = await run_swarm(
                    [
                        {"task": "task A", "task_id": "tA"},
                        {"task": "task B", "task_id": "tB"},
                    ],
                    on_agent_created=_external_cb,
                )

                # Both external and conductor should receive callbacks
                assert "tA" in external_calls
                assert "tB" in external_calls
                assert mock_conductor.register_agent.call_count == 2


# =============================================================================
# Event type constants
# =============================================================================

class TestChildWorkerCompletion:
    """plan_and_execute child workers must transition to final status."""

    def test_child_workers_get_result_and_status(self):
        """After planner finishes, child workers in _active_agents have final status."""
        import rook.server as srv

        old_agents = srv._active_agents.copy()
        old_results = srv._agent_results.copy()
        try:
            # Simulate: plan registered child workers via _on_worker_created
            srv._active_agents["worker_1"] = {
                "status": "running",
                "agent": MagicMock(),
                "prompt": "",
                "parent": "plan_abc",
            }
            srv._active_agents["worker_2"] = {
                "status": "running",
                "agent": MagicMock(),
                "prompt": "",
                "parent": "plan_abc",
            }

            # Simulate: plan_result.task_results contains final SpawnResults
            r1 = SpawnResult(task_id="worker_1", status="success", task="task 1")
            r2 = SpawnResult(task_id="worker_2", status="error", task="task 2")

            # Simulate the post-run transition code from _run_planner
            task_results = [r1, r2]
            for tr in task_results:
                tid = getattr(tr, "task_id", None)
                if tid and tid in srv._active_agents:
                    srv._active_agents[tid]["status"] = getattr(tr, "status", "completed")
                    srv._agent_results[tid] = tr

            # Verify
            assert srv._active_agents["worker_1"]["status"] == "success"
            assert srv._active_agents["worker_2"]["status"] == "error"
            assert srv._agent_results["worker_1"].task_id == "worker_1"
            assert srv._agent_results["worker_2"].task_id == "worker_2"
        finally:
            srv._active_agents = old_agents
            srv._agent_results = old_results


class TestEventConstants:
    """New event type constants exist."""

    def test_checkpoint_events(self):
        assert CHECKPOINT_PASS == "checkpoint_pass"
        assert CHECKPOINT_FAIL == "checkpoint_fail"

    def test_agent_ask_event(self):
        assert AGENT_ASK == "agent_ask"
