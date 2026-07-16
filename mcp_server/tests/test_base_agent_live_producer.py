from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping

from rook import tool_lifecycle_runtime
from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.tool_lifecycle import DispatchOrigin, contained_names


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
PROBE_TOOL_NAME = "lm4d_live_producer_probe"
_DECLARED_PARAMS = {"language": "csharp", "code": "// noop", "component_name": "C"}
_T5_EXPECTED_RED = "EXPECTED_RED:T5:AGENT_PROTOCOLS"


def _usable_raw() -> dict:
    return {
        "success": True,
        "data": {
            "verified": True,
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
                "repair_anchor": {"component_guid": COMPONENT_GUID},
            },
        },
    }


def _producer_graph(declared_params: dict) -> PlanGraph:
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component via RookAgent live producer method",
        execution_ref=PROBE_TOOL_NAME,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={"create_script": node})
    node.status = "ready"
    return graph


def _tool_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _schema_names(schemas: list[dict]) -> set[str]:
    return {
        schema.get("function", {}).get("name")
        for schema in schemas
        if isinstance(schema, dict)
    }


def _telemetry_store(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    return store


class _SyncSpy:
    """A plain (non-async) ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


class _AsyncSpy:
    """An async ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    async def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


class _WrapperPoisonParams(Mapping[str, object]):
    def _fail(self, action: str):
        raise AssertionError(
            f"{_T5_EXPECTED_RED} RookAgent PlanGraph wrapper accessed params via {action}"
        )

    def __getitem__(self, key: str) -> object:
        return self._fail(f"getitem:{key}")

    def __iter__(self) -> Iterator[str]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def __deepcopy__(self, memo):
        return self._fail("deepcopy")


def test_construction_does_not_invoke_executor():
    """RookAgent(tool_executor=spy) must not call the executor or build a
    dispatcher at construction -- the executor is only used when the method runs."""
    spy = _SyncSpy(_usable_raw())
    RookAgent(tool_executor=spy)
    assert spy.calls == []


def test_constructor_filters_raw_tool_schemas_without_telemetry(
    monkeypatch,
    tmp_path,
):
    store = _telemetry_store(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()
    agent = RookAgent(
        tool_executor=lambda *_args, **_kwargs: {},
        tool_schemas=[_tool_schema("safe_tool"), _tool_schema("spawn_agent")],
    )
    after = store.get_containment_denials_snapshot()

    assert (
        _schema_names(agent._tool_schemas) == {"safe_tool"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookAgent constructor admits contained schema"


def test_set_tool_schemas_filters_contained_schema_without_telemetry(
    monkeypatch,
    tmp_path,
):
    store = _telemetry_store(monkeypatch, tmp_path)
    agent = RookAgent(tool_executor=lambda *_args, **_kwargs: {})
    before = store.get_containment_denials_snapshot()
    agent.set_tool_schemas(
        [_tool_schema("safe_tool"), _tool_schema("gh_replay_recipe")]
    )
    after = store.get_containment_denials_snapshot()

    assert (
        _schema_names(agent._tool_schemas) == {"safe_tool"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookAgent schema setter admits contained schema"


def test_register_local_tools_filters_contained_keys_without_telemetry(
    monkeypatch,
    tmp_path,
):
    store = _telemetry_store(monkeypatch, tmp_path)
    agent = RookAgent(tool_executor=lambda *_args, **_kwargs: {})
    before = store.get_containment_denials_snapshot()
    agent.register_local_tools(
        {"safe_local": object(), "rhino_execute_intent": object()}
    )
    after = store.get_containment_denials_snapshot()

    assert (
        set(agent._local_tools) == {"safe_local"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookAgent local registration admits contained key"


def test_get_tool_schemas_defensively_filters_injected_registry_without_telemetry(
    monkeypatch,
    tmp_path,
):
    class DirtyRegistry:
        def get_active_schemas(self):
            return [
                _tool_schema("safe_tool"),
                _tool_schema("plan_and_execute"),
            ]

    store = _telemetry_store(monkeypatch, tmp_path)
    agent = RookAgent(
        tool_executor=lambda *_args, **_kwargs: {},
        tool_registry=DirtyRegistry(),
    )
    before = store.get_containment_denials_snapshot()
    schemas = agent._get_tool_schemas()
    after = store.get_containment_denials_snapshot()

    assert (
        _schema_names(schemas) == {"safe_tool"}
        and contained_names().isdisjoint(_schema_names(schemas))
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookAgent final projection trusts dirty registry"


def test_method_preserves_plan_graph_lifecycle_refusal_before_agent_executor(
    monkeypatch,
    tmp_path,
):
    from rook.learning import metrics_store

    executor_calls = []

    def executor(*args, **kwargs):
        executor_calls.append((args, kwargs))
        raise AssertionError(
            f"{_T5_EXPECTED_RED} RookAgent PlanGraph wrapper reached executor"
        )

    graph = _producer_graph(_WrapperPoisonParams())
    graph.nodes["create_script"].execution_ref = "gh_replay_recipe:v1"
    agent = RookAgent(tool_executor=executor)
    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    attempts = []
    real_recorder = tool_lifecycle_runtime._record_containment_denial

    def recording_spy(entry, origin):
        attempts.append((entry.name, origin.value))
        return real_recorder(entry, origin)

    monkeypatch.setattr(
        tool_lifecycle_runtime,
        "_record_containment_denial",
        recording_spy,
    )
    before = store.get_containment_denials_snapshot()

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    after = store.get_containment_denials_snapshot()
    added = after["events"][len(before["events"]):]
    assert result.graph is graph, _T5_EXPECTED_RED
    assert result.applied is False, _T5_EXPECTED_RED
    assert result.tool_name == "gh_replay_recipe", _T5_EXPECTED_RED
    assert result.outcome_status is None, _T5_EXPECTED_RED
    assert result.reason == "tool_lifecycle_denied", _T5_EXPECTED_RED
    assert executor_calls == [], _T5_EXPECTED_RED
    assert attempts == [
        ("gh_replay_recipe", DispatchOrigin.PLAN_GRAPH.value)
    ], _T5_EXPECTED_RED
    assert len(added) == 1, _T5_EXPECTED_RED
    assert added[0]["tool"] == "gh_replay_recipe", _T5_EXPECTED_RED
    assert added[0]["origin"] == DispatchOrigin.PLAN_GRAPH.value, _T5_EXPECTED_RED


def test_method_drives_node_via_sync_executor():
    spy = _SyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph
    # Proves the method reached self._tool_executor with the node's tool + params.
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_drives_node_via_async_executor():
    spy = _AsyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    assert result.graph is not graph
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_raising_executor_is_dispatch_failed():
    def executor(name, params):
        raise RuntimeError("transport down")

    agent = RookAgent(tool_executor=executor)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.outcome_status is None
    assert result.tool_name == PROBE_TOOL_NAME
    # Not-applied -> the input graph object is returned unchanged.
    assert result.graph is graph
