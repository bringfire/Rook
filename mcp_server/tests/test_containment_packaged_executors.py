from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from rook.bootstrap import executor as bootstrap_executor_module
from rook.bootstrap import runner as bootstrap_runner_module
from rook.bootstrap.runner import (
    BootstrapRunner,
    TestOutcome as BootstrapOutcome,
    TestResult as BootstrapResult,
)
from rook.bootstrap.test_matrix import ExpectedOutcome as BootstrapExpected
from rook.explorer import executor as explorer_executor_module
from rook.explorer.executor import (
    ExecutionResult as ExplorerExecutionResult,
    HttpExecutor as ExplorerHttpExecutor,
    MockExecutor as ExplorerMockExecutor,
)
from rook.learning import agent as learning_agent_module
from rook.learning import hybrid_investigator as hybrid_module
from rook.learning import investigator as investigator_module
from rook.learning.hybrid_investigator import (
    HybridInvestigationResult,
    HybridInvestigator,
)
from rook.learning.investigator import (
    ExperimentResult,
    InvestigationResult,
    Investigator,
)
from rook.learning.schema import ErrorCategory
from rook.learning.session import LearningSession
from rook.tool_lifecycle import (
    DispatchOrigin,
    containment_envelope,
    resolve_contained_identity,
)
from rook import tool_lifecycle_runtime


EXPECTED_RED = "EXPECTED_RED:T4:PACKAGED_EXECUTORS"
CONTAINED_NAMES = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
PACKAGED_BOUNDARY_SEAMS = (
    "bootstrap_runner_run_test",
    "bootstrap_runner_mock_executor",
    "bootstrap_http_executor",
    "bootstrap_mock_callable",
    "learning_agent_callable",
    "investigator_tool",
    "investigator_gap",
    "investigator_workflow",
    "investigator_experiment",
    "hybrid_tool",
    "hybrid_gap",
    "learning_session_basic",
    "learning_session_hybrid",
    "explorer_http_async",
    "explorer_mock_async",
    "explorer_http_sync",
    "explorer_mock_sync",
)
PACKAGED_BOUNDARY_CASES = tuple(
    (seam, name)
    for seam in PACKAGED_BOUNDARY_SEAMS
    for name in CONTAINED_NAMES
)


def _entry(name: str):
    entry = resolve_contained_identity(name)
    assert entry is not None, EXPECTED_RED
    return entry


def _expected_envelope(name: str) -> dict[str, object]:
    return containment_envelope(_entry(name))


def _snapshot_delta(
    before: dict[str, object],
    after: dict[str, object],
) -> list[dict[str, str]]:
    assert before["process_id"] == after["process_id"], EXPECTED_RED
    assert (
        before["process_start_token"] == after["process_start_token"]
    ), EXPECTED_RED
    before_events = before["events"]
    after_events = after["events"]
    assert isinstance(before_events, list), EXPECTED_RED
    assert isinstance(after_events, list), EXPECTED_RED
    assert len(before_events) < 50, EXPECTED_RED
    assert after_events[: len(before_events)] == before_events, EXPECTED_RED
    return after_events[len(before_events):]


def _telemetry_probe(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    attempts: list[tuple[str, str]] = []
    real_recorder = tool_lifecycle_runtime._record_containment_denial

    def recording_spy(entry, origin):
        attempts.append((entry.name, origin.value))
        return real_recorder(entry, origin)

    monkeypatch.setattr(
        tool_lifecycle_runtime,
        "_record_containment_denial",
        recording_spy,
    )
    return store, attempts


def _assert_one_internal_denial(
    store,
    attempts: list[tuple[str, str]],
    before: dict[str, object],
    *,
    name: str,
) -> None:
    assert attempts == [
        (name, DispatchOrigin.INTERNAL_HANDLER.value)
    ], EXPECTED_RED
    added = _snapshot_delta(
        before,
        store.get_containment_denials_snapshot(),
    )
    assert len(added) == 1, EXPECTED_RED
    event = added[0]
    assert set(event) == {
        "tool",
        "disposition",
        "origin",
        "timestamp",
    }, EXPECTED_RED
    assert event["tool"] == name, EXPECTED_RED
    assert event["disposition"] == _entry(name).disposition.value, EXPECTED_RED
    assert event["origin"] == DispatchOrigin.INTERNAL_HANDLER.value, EXPECTED_RED


class _Poison:
    def __init__(self, events: list[str], label: str):
        object.__setattr__(self, "_events", events)
        object.__setattr__(self, "_label", label)

    def _fail(self, action: str):
        self._events.append(f"{self._label}:{action}")
        raise AssertionError(
            f"{EXPECTED_RED} {self._label} was accessed via {action}"
        )

    def __getattr__(self, name: str):
        return self._fail(f"getattr:{name}")

    def __setattr__(self, name: str, value: object) -> None:
        self._fail(f"setattr:{name}")

    def __call__(self, *args, **kwargs):
        return self._fail("call")

    def __bool__(self) -> bool:
        return self._fail("bool")

    def __iter__(self) -> Iterator[object]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def __getitem__(self, key: object):
        return self._fail(f"getitem:{key}")

    def __str__(self) -> str:
        return self._fail("str")

    def __format__(self, format_spec: str) -> str:
        return self._fail("format")


class _PoisonMapping(Mapping[str, object]):
    def __init__(self, events: list[str], label: str = "params"):
        self._events = events
        self._label = label

    def _fail(self, action: str):
        self._events.append(f"{self._label}:{action}")
        raise AssertionError(
            f"{EXPECTED_RED} {self._label} was accessed via {action}"
        )

    def __getitem__(self, key: str) -> object:
        return self._fail(f"getitem:{key}")

    def __iter__(self) -> Iterator[str]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def __bool__(self) -> bool:
        return self._fail("bool")

    def get(self, key: str, default: object = None) -> object:
        return self._fail(f"get:{key}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def copy(self):
        return self._fail("copy")


class _ToolOnlyTestCase:
    def __init__(self, name: str, events: list[str]):
        self._name = name
        self._events = events

    @property
    def tool(self) -> str:
        self._events.append("test:tool")
        return self._name

    def __getattr__(self, name: str):
        self._events.append(f"test:{name}")
        raise AssertionError(
            f"{EXPECTED_RED} TestCase.{name} was accessed after tool"
        )


class _ToolOnlyGap:
    def __init__(self, name: str, events: list[str]):
        self._name = name
        self._events = events

    @property
    def tool(self) -> str:
        self._events.append("gap:tool")
        return self._name

    def __getattr__(self, name: str):
        self._events.append(f"gap:{name}")
        raise AssertionError(
            f"{EXPECTED_RED} Gap.{name} was accessed after tool"
        )


class _WorkflowStep:
    def __init__(
        self,
        name: str,
        params: Mapping[str, object],
        identity_events: list[str],
    ):
        self._name = name
        self._params = params
        self._identity_events = identity_events

    def __getitem__(self, index: int):
        if index == 0:
            self._identity_events.append(f"workflow:{self._name}:name")
            return self._name
        raise AssertionError(
            f"{EXPECTED_RED} workflow parameter tuple index {index} was read"
        )

    def __iter__(self):
        yield self._name
        yield self._params


class _PoisonTimer:
    def __init__(self, events: list[str], label: str):
        self._events = events
        self._label = label

    def time(self) -> float:
        self._events.append(f"{self._label}:time")
        raise AssertionError(f"{EXPECTED_RED} {self._label} timer was read")


def _new_bootstrap_runner(events: list[str]) -> BootstrapRunner:
    runner = object.__new__(BootstrapRunner)
    runner.tool_executor = _Poison(events, "bootstrap-tool-executor")
    runner.completed_tests = set()
    return runner


def _new_investigator(events: list[str]) -> Investigator:
    investigator = object.__new__(Investigator)
    investigator.kg = _Poison(events, "knowledge-graph")
    investigator.executor = _Poison(events, "investigator-executor")
    investigator.context = _Poison(events, "exploration-context")
    investigator._current_phase = _Poison(events, "investigation-phase")
    return investigator


def _new_hybrid(events: list[str]) -> HybridInvestigator:
    investigator = object.__new__(HybridInvestigator)
    investigator.kg = _Poison(events, "hybrid-knowledge-graph")
    investigator.executor = _Poison(events, "hybrid-executor")
    investigator.use_dspy = True
    investigator.use_visual_verification = True
    investigator.verifier = _Poison(events, "viewport-verifier")
    investigator._geometry_ids = _PoisonMapping(events, "geometry-ids")
    investigator._init_dspy_modules = _Poison(events, "dspy-initializer")
    investigator.hypothesis_selector = _Poison(events, "hypothesis-selector")
    investigator.fix_selector = _Poison(events, "fix-selector")
    investigator.training_buffer = _Poison(events, "training-buffer")
    return investigator


def _new_session(events: list[str], *, use_hybrid: bool) -> LearningSession:
    session = object.__new__(LearningSession)
    session.use_hybrid = use_hybrid
    session.progress = _Poison(events, "session-progress")
    session.reporter = _Poison(events, "session-reporter")
    session.investigator = _Poison(events, "session-basic-investigator")
    session.hybrid_investigator = _Poison(
        events,
        "session-hybrid-investigator",
    )
    session.kg = _Poison(events, "session-knowledge-graph")
    return session


def _assert_bootstrap_result(
    result: object,
    name: str,
    envelope: dict[str, object],
) -> None:
    assert type(result) is BootstrapResult, EXPECTED_RED
    assert result.test_id == f"containment:{name}", EXPECTED_RED
    assert result.tool == name, EXPECTED_RED
    assert result.params == {}, EXPECTED_RED
    assert result.expected is BootstrapExpected.EITHER, EXPECTED_RED
    assert result.actual is BootstrapOutcome.ERROR, EXPECTED_RED
    assert result.response == envelope, EXPECTED_RED
    assert result.error_message == "legacy_semantic_tool_contained", EXPECTED_RED
    assert result.duration_ms == 0.0, EXPECTED_RED
    assert result.created_object_ids == [], EXPECTED_RED
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",
        result.timestamp,
    ), EXPECTED_RED
    parsed = datetime.fromisoformat(result.timestamp[:-1] + "+00:00")
    assert parsed.tzinfo == timezone.utc, EXPECTED_RED


def _assert_explorer_result(
    result: object,
    name: str,
    envelope: dict[str, object],
) -> None:
    assert type(result) is ExplorerExecutionResult, EXPECTED_RED
    assert result.tool_name == name, EXPECTED_RED
    assert result.params == {}, EXPECTED_RED
    assert result.success is False, EXPECTED_RED
    assert result.response == envelope, EXPECTED_RED
    assert result.error == "legacy_semantic_tool_contained", EXPECTED_RED
    assert result.duration_ms == 0.0, EXPECTED_RED
    assert not hasattr(result, "refusal_detail"), EXPECTED_RED


def _assert_experiment_result(
    result: object,
    name: str,
    envelope: dict[str, object],
) -> None:
    assert type(result) is ExperimentResult, EXPECTED_RED
    assert result.tool == name, EXPECTED_RED
    assert result.params == {}, EXPECTED_RED
    assert result.success is False, EXPECTED_RED
    assert result.response == envelope, EXPECTED_RED
    assert result.error == "legacy_semantic_tool_contained", EXPECTED_RED
    assert result.error_category == ErrorCategory.UNKNOWN.value, EXPECTED_RED
    assert result.execution_time_ms == 0, EXPECTED_RED


def _assert_basic_result(
    result: object,
    name: str,
    envelope: dict[str, object],
) -> None:
    assert type(result) is InvestigationResult, EXPECTED_RED
    assert set(result.__dict__) == {
        "gap_id",
        "tool",
        "patterns_discovered",
        "antipatterns_discovered",
        "experiments",
        "gap_resolved",
        "resolution",
        "new_gaps",
        "insights",
        "containment_denial",
    }, EXPECTED_RED
    assert result.gap_id is None, EXPECTED_RED
    assert result.tool == name, EXPECTED_RED
    assert result.patterns_discovered == [], EXPECTED_RED
    assert result.antipatterns_discovered == [], EXPECTED_RED
    assert result.experiments == [], EXPECTED_RED
    assert result.gap_resolved is False, EXPECTED_RED
    assert result.resolution is None, EXPECTED_RED
    assert result.new_gaps == [], EXPECTED_RED
    assert result.insights == [], EXPECTED_RED
    assert result.containment_denial == envelope, EXPECTED_RED


def _assert_hybrid_result(
    result: object,
    name: str,
    envelope: dict[str, object],
) -> None:
    assert type(result) is HybridInvestigationResult, EXPECTED_RED
    assert result.tool == name, EXPECTED_RED
    assert result.success is False, EXPECTED_RED
    assert result.hypotheses_generated == [], EXPECTED_RED
    assert result.diagnosis is None, EXPECTED_RED
    assert result.reasoning_trace == [], EXPECTED_RED
    assert result.hypothesis_selected is None, EXPECTED_RED
    assert result.fix_selected is None, EXPECTED_RED
    assert result.patterns_discovered == [], EXPECTED_RED
    assert result.antipatterns_discovered == [], EXPECTED_RED
    assert result.insights == [], EXPECTED_RED
    assert result.consolidation_action is None, EXPECTED_RED
    assert result.workflow_detected is None, EXPECTED_RED
    assert result.nuanced_reward is None, EXPECTED_RED
    assert result.visually_verified is False, EXPECTED_RED
    assert result.visual_description is None, EXPECTED_RED
    assert result.viewport_hash_before is None, EXPECTED_RED
    assert result.viewport_hash_after is None, EXPECTED_RED
    assert result.gap_id is None, EXPECTED_RED
    assert result.gap_resolved is False, EXPECTED_RED
    assert result.resolution is None, EXPECTED_RED
    assert result.new_gaps == [], EXPECTED_RED
    assert result.attempts == 0, EXPECTED_RED
    assert result.time_ms == 0, EXPECTED_RED
    assert result.containment_denial == envelope, EXPECTED_RED
    serialized = result.to_dict()
    assert serialized["containment_denial"] == envelope, EXPECTED_RED


def test_packaged_boundary_matrix_keyset_and_all_six_cardinality_are_pinned():
    expected = {
        (seam, name)
        for seam in PACKAGED_BOUNDARY_SEAMS
        for name in CONTAINED_NAMES
    }
    assert set(PACKAGED_BOUNDARY_CASES) == expected
    assert len(PACKAGED_BOUNDARY_CASES) == 102
    counts = Counter(seam for seam, _name in PACKAGED_BOUNDARY_CASES)
    assert counts == Counter({
        seam: len(CONTAINED_NAMES)
        for seam in PACKAGED_BOUNDARY_SEAMS
    })
    for seam in PACKAGED_BOUNDARY_SEAMS:
        assert {
            name
            for candidate_seam, name in PACKAGED_BOUNDARY_CASES
            if candidate_seam == seam
        } == set(CONTAINED_NAMES)


def test_learning_result_types_declare_containment_denial_and_hybrid_serializes():
    assert (
        "containment_denial" in InvestigationResult.__dataclass_fields__
    ), EXPECTED_RED
    assert (
        "containment_denial" in HybridInvestigationResult.__dataclass_fields__
    ), EXPECTED_RED
    basic = InvestigationResult()
    hybrid = HybridInvestigationResult(tool="rhino_ping", success=False)
    assert basic.containment_denial is None, EXPECTED_RED
    assert hybrid.containment_denial is None, EXPECTED_RED
    assert "containment_denial" in hybrid.to_dict(), EXPECTED_RED
    assert hybrid.to_dict()["containment_denial"] is None, EXPECTED_RED


@pytest.mark.asyncio
@pytest.mark.parametrize(("seam", "name"), PACKAGED_BOUNDARY_CASES)
async def test_packaged_boundary_denials_are_typed_early_and_exact_once(
    monkeypatch,
    tmp_path,
    seam: str,
    name: str,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    identity_events: list[str] = []
    params = _PoisonMapping(events)
    envelope = _expected_envelope(name)
    before = store.get_containment_denials_snapshot()

    monkeypatch.setattr(
        bootstrap_runner_module,
        "record_knowledge",
        _Poison(events, "bootstrap-knowledge-recorder"),
    )
    monkeypatch.setattr(
        investigator_module,
        "get_tool_schema",
        _Poison(events, "basic-schema-lookup"),
    )
    monkeypatch.setattr(
        investigator_module,
        "generate_params_for_tool",
        _Poison(events, "basic-param-generator"),
    )
    monkeypatch.setattr(
        hybrid_module,
        "get_tool_schema",
        _Poison(events, "hybrid-schema-lookup"),
    )
    monkeypatch.setattr(
        hybrid_module,
        "generate_params_for_tool",
        _Poison(events, "hybrid-param-generator"),
    )

    if seam == "bootstrap_runner_run_test":
        runner = _new_bootstrap_runner(events)
        result = runner.run_test(_ToolOnlyTestCase(name, identity_events))
        _assert_bootstrap_result(result, name, envelope)
        assert runner.completed_tests == set(), EXPECTED_RED
        expected_identity_events = ["test:tool"]
    elif seam == "bootstrap_runner_mock_executor":
        runner = _new_bootstrap_runner(events)
        monkeypatch.setattr(
            bootstrap_runner_module.logger,
            "warning",
            _Poison(events, "bootstrap-mock-log"),
        )
        result = runner._mock_executor(name, params)
        assert result == envelope, EXPECTED_RED
        expected_identity_events = []
    elif seam == "bootstrap_http_executor":
        executor = object.__new__(bootstrap_executor_module.HttpExecutor)
        executor.base_url = _Poison(events, "bootstrap-base-url")
        executor._get_curve_endpoint = _Poison(
            events,
            "bootstrap-curve-endpoint",
        )
        executor._get_document_ops_endpoint = _Poison(
            events,
            "bootstrap-document-endpoint",
        )
        executor._get_material_endpoint = _Poison(
            events,
            "bootstrap-material-endpoint",
        )
        monkeypatch.setattr(
            bootstrap_executor_module.urllib.request,
            "urlopen",
            _Poison(events, "bootstrap-http-client"),
        )
        result = executor.execute(name, params)
        assert result == envelope, EXPECTED_RED
        expected_identity_events = []
    elif seam == "bootstrap_mock_callable":
        executor = bootstrap_executor_module.create_mock_executor()
        result = executor(name, params)
        assert result == envelope, EXPECTED_RED
        expected_identity_events = []
    elif seam == "learning_agent_callable":
        monkeypatch.setattr(
            learning_agent_module,
            "call_rhino",
            _Poison(events, "learning-agent-host"),
        )
        executor = await learning_agent_module.create_tool_executor()
        result = await executor(name, params)
        assert result == envelope, EXPECTED_RED
        expected_identity_events = []
    elif seam == "investigator_tool":
        investigator = _new_investigator(events)
        result = await investigator.investigate_tool(name)
        _assert_basic_result(result, name, envelope)
        expected_identity_events = []
    elif seam == "investigator_gap":
        investigator = _new_investigator(events)
        result = await investigator.investigate_gap(
            _ToolOnlyGap(name, identity_events)
        )
        _assert_basic_result(result, name, envelope)
        expected_identity_events = ["gap:tool"]
    elif seam == "investigator_workflow":
        investigator = _new_investigator(events)
        workflow = [
            _WorkflowStep("rhino_ping", params, identity_events),
            _WorkflowStep(name, params, identity_events),
        ]
        result = await investigator.investigate_workflow(
            workflow,
            "supported step must not run before contained-name preflight",
        )
        _assert_basic_result(result, name, envelope)
        expected_identity_events = [
            "workflow:rhino_ping:name",
            f"workflow:{name}:name",
        ]
    elif seam == "investigator_experiment":
        investigator = _new_investigator(events)
        result = await investigator._run_experiment(name, params)
        _assert_experiment_result(result, name, envelope)
        expected_identity_events = []
    elif seam == "hybrid_tool":
        investigator = _new_hybrid(events)
        monkeypatch.setattr(
            hybrid_module,
            "time",
            _PoisonTimer(events, "hybrid"),
        )
        result = await investigator.investigate_tool(name)
        _assert_hybrid_result(result, name, envelope)
        expected_identity_events = []
    elif seam == "hybrid_gap":
        investigator = _new_hybrid(events)
        result = await investigator.investigate_gap(
            _ToolOnlyGap(name, identity_events)
        )
        _assert_hybrid_result(result, name, envelope)
        expected_identity_events = ["gap:tool"]
    elif seam in {
        "learning_session_basic",
        "learning_session_hybrid",
    }:
        use_hybrid = seam == "learning_session_hybrid"
        session = _new_session(events, use_hybrid=use_hybrid)
        result = await session.run_investigation_cycle(f"tool:{name}")
        if use_hybrid:
            _assert_hybrid_result(result, name, envelope)
        else:
            _assert_basic_result(result, name, envelope)
        expected_identity_events = []
    elif seam in {
        "explorer_http_async",
        "explorer_http_sync",
    }:
        executor = object.__new__(ExplorerHttpExecutor)
        executor.base_url = _Poison(events, "explorer-base-url")
        executor._get_endpoint = _Poison(events, "explorer-endpoint")
        monkeypatch.setattr(
            explorer_executor_module.httpx,
            "AsyncClient",
            _Poison(events, "explorer-http-client"),
        )
        if seam == "explorer_http_async":
            result = await executor.execute(name, params)
        else:
            result = await asyncio.to_thread(
                executor.execute_sync,
                name,
                params,
            )
        _assert_explorer_result(result, name, envelope)
        expected_identity_events = []
    elif seam in {
        "explorer_mock_async",
        "explorer_mock_sync",
    }:
        executor = ExplorerMockExecutor()
        if seam == "explorer_mock_async":
            result = await executor.execute(name, params)
        else:
            result = await asyncio.to_thread(
                executor.execute_sync,
                name,
                params,
            )
        _assert_explorer_result(result, name, envelope)
        expected_identity_events = []
    else:  # pragma: no cover - keyset assertion pins every seam.
        raise AssertionError(f"{EXPECTED_RED} unknown seam: {seam}")

    _assert_one_internal_denial(
        store,
        attempts,
        before,
        name=name,
    )
    assert identity_events == expected_identity_events, EXPECTED_RED
    assert events == [], EXPECTED_RED


@pytest.mark.parametrize(
    "executor_type",
    (ExplorerHttpExecutor, ExplorerMockExecutor),
)
def test_explorer_sync_methods_are_delegates_only(
    monkeypatch,
    executor_type,
) -> None:
    events: list[str] = []
    executor = object.__new__(executor_type)
    params = _PoisonMapping(events)
    expected = object()
    async_execute = AsyncMock(return_value=expected)
    monkeypatch.setattr(executor, "execute", async_execute)

    result = executor.execute_sync("spawn_agent", params)

    assert result is expected
    async_execute.assert_awaited_once_with("spawn_agent", params)
    assert events == []
