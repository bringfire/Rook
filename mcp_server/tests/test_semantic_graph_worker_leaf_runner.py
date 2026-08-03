from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.semantic_graph_runner as semantic_runner
import rook.agent.semantic_graph_worker_leaf_runner as worker_leaf_runner


_INTENT = "Create one generated value connected to a point input."
_WORKER_GOAL = "Produce one numeric value."
_WORKER_BODY = "A = 7.0;"
_LEAF_GUID = "11111111-1111-1111-1111-111111111111"
_TARGET_GUID = "22222222-2222-2222-2222-222222222222"
_CONSTRUCT_POINT_GUID = "3581f42a-9592-4549-bd6b-1c0fc39d067b"
_EXPECTED_TOOLS = (
    "gh_create_csharp_script",
    "gh_snapshot",
    "gh_edit",
    "gh_connect",
)
_UNSET = object()


def _connected_raw_graph() -> str:
    return json.dumps(
        {
            "schema": "rook.gh_semantic_graph:v1",
            "nodes": [
                {
                    "id": "generated_value",
                    "primitive": "csharp_script",
                    "parameters": {
                        "goal": _WORKER_GOAL,
                        "interface": {
                            "inputs": [],
                            "outputs": [{"name": "A", "type": "double"}],
                        },
                    },
                },
                {
                    "id": "point",
                    "primitive": "construct_point",
                    "parameters": {},
                },
            ],
            "edges": [
                {
                    "from_node": "generated_value",
                    "from_pin": "A",
                    "to_node": "point",
                    "to_pin": "x",
                }
            ],
        },
        separators=(",", ":"),
    )


class _PlannerTransport:
    def __init__(self, response: str, *, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def send(self, prompt_artifact: dict[str, object]) -> str:
        self.calls.append(copy.deepcopy(prompt_artifact))
        if self.error is not None:
            raise self.error
        return self.response


class _WorkerTransport:
    def __init__(self, payload: object | None = None, *, raw: str | None = None) -> None:
        self.payload = payload
        self.raw = raw
        self.calls: list[dict[str, object]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        captured = copy.deepcopy(dict(prompt_artifact))
        self.calls.append(captured)
        request = json.loads(captured["messages"][1]["content"])
        rendered = json.dumps(request, sort_keys=True)
        assert _WORKER_GOAL in rendered
        assert "draft_create_body" in rendered
        assert _WORKER_BODY not in rendered
        assert "draft_repair_params" not in rendered
        if self.raw is not None:
            return self.raw
        payload = self.payload if self.payload is not None else {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_create_body",
            "rationale": "Draft the requested numeric body.",
            "input": {"code": _WORKER_BODY},
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )


class _CausalExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.edit_response: dict[str, object] | None = None

    def __call__(self, name: str, params: dict[str, object]) -> object:
        self.calls.append((name, copy.deepcopy(params)))
        assert name == _EXPECTED_TOOLS[len(self.calls) - 1]
        if name == "gh_create_csharp_script":
            assert params == {
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalInitialBodyHandoff",
                "x": 375,
                "y": 1080,
                "code": _WORKER_BODY,
            }
            return _clean_create_response()
        if name == "gh_snapshot":
            assert params == {"include_data": False, "max_preview_items": 0}
            return _snapshot_response()
        if name == "gh_edit":
            self.edit_response = _derive_edit_response(params)
            return self.edit_response
        assert params == {
            "sourceGuid": _LEAF_GUID,
            "sourceIndex": 1,
            "targetGuid": _TARGET_GUID,
            "targetIndex": 0,
        }
        return _connect_response()


class _FaultExecutor(_CausalExecutor):
    def __init__(
        self,
        phase: str,
        *,
        replacement: object = _UNSET,
        transform: Any = None,
        error: Exception | None = None,
        after_call: Any = None,
    ) -> None:
        super().__init__()
        self.phase = phase
        self.replacement = replacement
        self.transform = transform
        self.error = error
        self.after_call = after_call

    def __call__(self, name: str, params: dict[str, object]) -> object:
        response = super().__call__(name, params)
        if name != self.phase:
            return response
        if self.after_call is not None:
            self.after_call()
        if self.error is not None:
            raise self.error
        if self.transform is not None:
            return self.transform(copy.deepcopy(response))
        return response if self.replacement is _UNSET else self.replacement


def _connect_response(
    source_guid: str = _LEAF_GUID,
    target_guid: str = _TARGET_GUID,
    source_param: str = "A",
    source_index: int = 1,
) -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "connected": True,
            "source": {
                "guid": source_guid,
                "param": source_param,
                "index": source_index,
            },
            "target": {"guid": target_guid, "param": "X", "index": 0},
        },
    }


def _edit_failure(response: dict[str, object]) -> dict[str, object]:
    response["success"] = False
    return response


def _edit_partial(response: dict[str, object]) -> dict[str, object]:
    response["partial_success"] = True
    return response


def _edit_structural_mismatch(response: dict[str, object]) -> dict[str, object]:
    response["data"]["edit_summary"]["temp_id_map"]["T1"] = "C99"
    return response


def _create_compile_error(response: dict[str, object]) -> dict[str, object]:
    response["success"] = False
    receipt = response["data"]["script_receipt"]
    receipt["artifact_status"] = "created_with_errors"
    receipt["verification"] = {"status": "failed", "target_error_count": 1}
    receipt["repair_anchor"]["target_errors"] = ["CS0103: Missing symbol"]
    return response


def _clean_create_response() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {
                    "status": "created",
                    "component_guid": _LEAF_GUID,
                },
                "verification": {
                    "status": "passed",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": _LEAF_GUID,
                    "language": "csharp",
                    "target_errors": [],
                },
            }
        },
    }


def _snapshot_response() -> dict[str, object]:
    return {
        "success": True,
        "data": {
            "version": "1.0.0",
            "epoch": 11,
            "components": [_csharp_component_snapshot()],
            "flows": [],
            "diagnostics": {"total": 1, "errors": 0, "warnings": 0},
        },
    }


def _derive_edit_response(params: dict[str, object]) -> dict[str, object]:
    assert params.get("epoch") == 11
    create = params.get("create")
    connect = params.get("connect")
    assert type(create) is list and len(create) == 1
    assert connect == []
    instruction = create[0]
    assert type(instruction) is dict
    assert instruction == {
        "temp_id": "T1",
        "guid": _CONSTRUCT_POINT_GUID,
        "pos": [100, 100],
    }
    return {
        "success": True,
        "data": {
            "version": "1.0.0",
            "epoch": 12,
            "components": [
                _csharp_component_snapshot(),
                {
                    "id": "C2",
                    "type": "Component_ConstructPoint",
                    "componentGuid": _CONSTRUCT_POINT_GUID,
                    "pos": [100, 100],
                },
            ],
            "flows": [],
            "diagnostics": {"total": 2, "errors": 0, "warnings": 0},
            "edit_summary": {
                "created": 1,
                "deleted": 0,
                "values_set": 0,
                "connected": 0,
                "disconnected": 0,
                "errors": None,
                "temp_id_map": {"T1": "C2"},
                "instance_guids": {"T1": _TARGET_GUID},
            },
        },
    }


def _csharp_component_snapshot() -> dict[str, object]:
    return {
        "id": "C1",
        "type": "CSharpScript",
        "outputs": [
            {"idx": 0, "name": "out"},
            {"idx": 1, "name": "A"},
        ],
    }


@pytest.mark.asyncio
async def test_one_worker_leaf_composes_with_one_deterministic_region() -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.completed is True
    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == list(_EXPECTED_TOOLS)
    assert result.worker_handoff_result.terminal_stage == "terminal"
    assert (
        result.worker_handoff_result.terminal_reason
        == "terminal_node_selected:done"
    )
    assert result.deterministic_execution_result.terminal_stage == "terminal"
    assert (
        result.deterministic_execution_result.terminal_reason
        == "terminal_node_selected:done"
    )
    assert result.connect_request == executor.calls[-1][1]
    assert result.connect_request["sourceIndex"] == 1
    assert result.connect_response["data"]["source"] == {
        "guid": _LEAF_GUID,
        "param": "A",
        "index": 1,
    }
    snapshot_components = (
        result.deterministic_execution_result.snapshot_response["data"]["components"]
    )
    assert [
        (output["name"], output["idx"])
        for output in snapshot_components[0]["outputs"]
    ] == [
        ("out", 0),
        ("A", 1),
    ]


@pytest.mark.asyncio
async def test_worker_context_drift_stops_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {"port": 1111}
    planner = _PlannerTransport(_connected_raw_graph())
    executor = _CausalExecutor()

    class _DriftingWorker(_WorkerTransport):
        def send(self, prompt_artifact: Mapping[str, Any]) -> str:
            context["port"] = 2222
            return super().send(prompt_artifact)

    worker = _DriftingWorker()
    monkeypatch.setattr(
        worker_leaf_runner,
        "get_rhino_request_context",
        lambda: copy.deepcopy(context),
    )

    with pytest.raises(RuntimeError, match="Rhino context changed"):
        await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
            _INTENT,
            planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
            worker_transport=worker,
            tool_executor=executor,
        )

    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert executor.calls == []


@pytest.mark.asyncio
async def test_connect_request_requires_complete_execution_prefix() -> None:
    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=_CausalExecutor(),
    )

    with pytest.raises(ValueError, match="connect request requires clean deterministic"):
        replace(
            result,
            graph_load_result=None,
            partition_compile_result=None,
            worker_handoff_result=None,
            deterministic_execution_result=None,
            connect_response=None,
            completed=False,
        )


class _AdapterSubclass(semantic_runner.SemanticGraphPlannerAdapter):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "error_type"),
    [
        ("non_string_intent", TypeError),
        ("string_subclass_intent", TypeError),
        ("blank_intent", ValueError),
        ("surrogate_intent", ValueError),
        ("adapter_subclass", TypeError),
        ("adapter_substitute", TypeError),
        ("worker_without_send", TypeError),
        ("worker_noncallable_send", TypeError),
        ("noncallable_executor", TypeError),
    ],
)
async def test_invalid_caller_capability_stops_before_planner(
    case: str,
    error_type: type[Exception],
) -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport()
    executor = _CausalExecutor()
    intent: object = _INTENT
    adapter: object = semantic_runner.SemanticGraphPlannerAdapter(planner)
    worker_capability: object = worker
    tool_capability: object = executor

    if case == "non_string_intent":
        intent = 1
    elif case == "string_subclass_intent":
        intent = type("Intent", (str,), {})(_INTENT)
    elif case == "blank_intent":
        intent = "   "
    elif case == "surrogate_intent":
        intent = chr(0xD800)
    elif case == "adapter_subclass":
        adapter = _AdapterSubclass(planner)
    elif case == "adapter_substitute":
        adapter = object()
    elif case == "worker_without_send":
        worker_capability = object()
    elif case == "worker_noncallable_send":
        worker_capability = type("Worker", (), {"send": None})()
    elif case == "noncallable_executor":
        tool_capability = object()

    with pytest.raises(error_type):
        await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
            intent,
            planner_adapter=adapter,
            worker_transport=worker_capability,
            tool_executor=tool_capability,
        )

    assert planner.calls == []
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_planner_failure_retains_only_planner_prefix() -> None:
    planner = _PlannerTransport(
        _connected_raw_graph(),
        error=TimeoutError("provider sentinel"),
    )
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.planner_record.status == "transport_failed"
    assert result.graph_load_result is None
    assert result.partition_compile_result is None
    assert result.worker_handoff_result is None
    assert result.deterministic_execution_result is None
    assert result.connect_request is None
    assert result.connect_response is None
    assert result.completed is False
    assert len(planner.calls) == 1
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "failure", "reason"),
    [
        ("{", "response", "response_invalid_json"),
        (
            _connected_raw_graph().replace(
                '"outputs":[{"name":"A","type":"double"}]',
                '"outputs":[{"name":"B","type":"double"}]',
            ),
            "parameters",
            "invalid_csharp_interface",
        ),
    ],
    ids=("malformed_json", "invalid_interface"),
)
async def test_graph_refusal_retains_loader_reason_before_worker_or_tools(
    raw: str,
    failure: str,
    reason: str,
) -> None:
    planner = _PlannerTransport(raw)
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.graph_load_result is not None
    assert result.graph_load_result.admitted is False
    assert result.graph_load_result.failure == failure
    assert result.graph_load_result.reason == reason
    assert result.partition_compile_result is None
    assert result.worker_handoff_result is None
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_zero_worker_leaf_retains_admitted_partition_without_contact() -> None:
    raw = json.dumps(
        {
            "schema": "rook.gh_semantic_graph:v1",
            "nodes": [
                {"id": "point", "primitive": "construct_point", "parameters": {}}
            ],
            "edges": [],
        },
        separators=(",", ":"),
    )
    planner = _PlannerTransport(raw)
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.graph_load_result is not None
    assert result.graph_load_result.admitted is True
    assert result.partition_compile_result is not None
    assert result.partition_compile_result.admitted is True
    assert result.partition_compile_result.partition.unresolved_leaf is None
    assert result.worker_handoff_result is None
    assert result.completed is False
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_occupied_cross_edge_target_refuses_before_worker_or_tools() -> None:
    graph = json.loads(_connected_raw_graph())
    graph["nodes"].append(
        {
            "id": "control",
            "primitive": "number_slider",
            "parameters": {
                "label": "Control",
                "minimum": 0,
                "maximum": 10,
                "initial": 5,
            },
        }
    )
    graph["edges"].append(
        {
            "from_node": "control",
            "from_pin": "value",
            "to_node": "point",
            "to_pin": "x",
        }
    )
    planner = _PlannerTransport(json.dumps(graph, separators=(",", ":")))
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.graph_load_result is not None
    assert result.graph_load_result.admitted is True
    assert result.partition_compile_result is not None
    assert result.partition_compile_result.admitted is False
    assert result.partition_compile_result.reason == "too_many_input_connections"
    assert result.worker_handoff_result is None
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "raw", "stage", "reason"),
    [
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "Cannot author this body.",
            },
            None,
            "worker_disposition",
            "refusal_recorded",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "rationale": "Wrong action.",
                "input": {"code": _WORKER_BODY},
            },
            None,
            "worker_disposition",
            "blocked:unknown_action_id:draft_repair_params",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Extra input.",
                "input": {"code": _WORKER_BODY, "mode": "body"},
            },
            None,
            "action_apply",
            "unexpected_action_input_key",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Blank code.",
                "input": {"code": "   "},
            },
            None,
            "action_apply",
            "invalid_code",
        ),
        (None, "{", "worker_adapter", "raw_output_invalid:json_decode"),
    ],
    ids=("refusal", "wrong_action", "extra_input", "blank_code", "malformed"),
)
async def test_worker_stop_retains_native_handoff_before_tool_contact(
    payload: object | None,
    raw: str | None,
    stage: str,
    reason: str,
) -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport(payload, raw=raw)
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert executor.calls == []
    assert result.worker_handoff_result is not None
    assert result.worker_handoff_result.terminal_stage == stage
    assert result.worker_handoff_result.terminal_reason == reason
    assert result.deterministic_execution_result is None
    assert result.completed is False


class _CompileErrorExecutor(_CausalExecutor):
    def __call__(self, name: str, params: dict[str, object]) -> object:
        response = super().__call__(name, params)
        assert name == "gh_create_csharp_script"
        return _create_compile_error(copy.deepcopy(response))


@pytest.mark.asyncio
async def test_compile_error_retains_leaf_receipt_without_later_contact() -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport()
    executor = _CompileErrorExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_create_csharp_script"]
    assert result.worker_handoff_result is not None
    assert result.worker_handoff_result.terminal_stage == "verify_create"
    assert result.worker_handoff_result.terminal_reason == "selector_halt:none_ready"
    receipt = result.worker_handoff_result.final_graph.nodes["create_script"].evidence.receipt
    assert receipt["verification"]["target_error_count"] == 1
    assert result.deterministic_execution_result is None
    assert result.completed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executor", "reason", "has_response"),
    [
        (
            _FaultExecutor("gh_snapshot", error=TimeoutError("snapshot sentinel")),
            "snapshot_dispatch_failed",
            False,
        ),
        (
            _FaultExecutor(
                "gh_snapshot",
                replacement={"success": True, "data": {"epoch": "11"}},
            ),
            "snapshot_response_invalid",
            True,
        ),
    ],
    ids=("exception", "malformed"),
)
async def test_snapshot_stop_retains_completed_leaf_prefix(
    executor: _FaultExecutor,
    reason: str,
    has_response: bool,
) -> None:
    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=executor,
    )

    assert [name for name, _ in executor.calls] == [
        "gh_create_csharp_script",
        "gh_snapshot",
    ]
    assert result.worker_handoff_result.terminal_stage == "terminal"
    assert result.deterministic_execution_result is not None
    assert result.deterministic_execution_result.terminal_stage == "snapshot"
    assert result.deterministic_execution_result.terminal_reason == reason
    assert (result.deterministic_execution_result.snapshot_response is not None) is has_response
    assert result.connect_request is None
    assert result.completed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transform", "stage", "reason"),
    [
        (_edit_failure, "edit", "edit_failed"),
        (_edit_partial, "edit", "edit_partial_success"),
        (
            _edit_structural_mismatch,
            "verification",
            "mapped_component_missing_or_ambiguous",
        ),
    ],
    ids=("failed", "partial", "structural_mismatch"),
)
async def test_edit_stop_retains_both_owner_results_without_connect(
    transform: Any,
    stage: str,
    reason: str,
) -> None:
    executor = _FaultExecutor("gh_edit", transform=transform)

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=executor,
    )

    assert [name for name, _ in executor.calls] == [
        "gh_create_csharp_script",
        "gh_snapshot",
        "gh_edit",
    ]
    assert result.worker_handoff_result.terminal_stage == "terminal"
    assert result.deterministic_execution_result is not None
    assert result.deterministic_execution_result.terminal_stage == stage
    assert result.deterministic_execution_result.terminal_reason == reason
    assert result.connect_request is None
    assert result.completed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "data": {"connected": False}},
        "malformed",
        _connect_response(source_guid="33333333-3333-3333-3333-333333333333"),
        _connect_response(target_guid="44444444-4444-4444-4444-444444444444"),
        _connect_response(source_param="out", source_index=0),
    ],
    ids=(
        "failed",
        "malformed",
        "source_mismatch",
        "target_mismatch",
        "declared_output_mismatch",
    ),
)
async def test_connect_failure_retains_exact_request_and_response(
    response: object,
) -> None:
    executor = _FaultExecutor("gh_connect", replacement=response)

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=executor,
    )

    assert [name for name, _ in executor.calls] == list(_EXPECTED_TOOLS)
    assert result.connect_request == executor.calls[-1][1]
    assert result.connect_response == response
    assert result.completed is False


@pytest.mark.asyncio
async def test_connect_exception_retains_request_without_error_text() -> None:
    executor = _FaultExecutor(
        "gh_connect",
        error=RuntimeError("connect sentinel secret"),
    )

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=executor,
    )

    assert [name for name, _ in executor.calls] == list(_EXPECTED_TOOLS)
    assert result.connect_request == executor.calls[-1][1]
    assert result.connect_response is None
    assert result.completed is False
    assert "RuntimeError" not in repr(result)
    assert "sentinel" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_tools"),
    [
        ("failed_handoff", ("gh_create_csharp_script",)),
        ("raised_handoff", ("gh_create_csharp_script",)),
        ("failed_deterministic", ("gh_create_csharp_script", "gh_snapshot")),
        (
            "raised_deterministic",
            ("gh_create_csharp_script", "gh_snapshot", "gh_edit"),
        ),
        ("returned_connect", _EXPECTED_TOOLS),
        ("raised_connect", _EXPECTED_TOOLS),
    ],
)
async def test_context_drift_precedes_every_post_contact_exit(
    case: str,
    expected_tools: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {"port": 1111}

    def drift() -> None:
        context["port"] = 2222

    monkeypatch.setattr(
        worker_leaf_runner,
        "get_rhino_request_context",
        lambda: copy.deepcopy(context),
    )
    executor: _CausalExecutor
    if case == "failed_handoff":
        executor = _FaultExecutor(
            "gh_create_csharp_script",
            transform=_create_compile_error,
            after_call=drift,
        )
    elif case == "raised_handoff":
        executor = _CausalExecutor()
        original_handoff = worker_leaf_runner.run_minimal_csharp_initial_body_handoff

        async def raised_handoff(*args: Any, **kwargs: Any) -> Any:
            await original_handoff(*args, **kwargs)
            drift()
            raise ValueError("handoff sentinel")

        monkeypatch.setattr(
            worker_leaf_runner,
            "run_minimal_csharp_initial_body_handoff",
            raised_handoff,
        )
    elif case == "failed_deterministic":
        executor = _FaultExecutor(
            "gh_snapshot",
            replacement={"success": True, "data": {"epoch": "11"}},
            after_call=drift,
        )
    elif case == "raised_deterministic":
        executor = _CausalExecutor()
        original_execution = worker_leaf_runner._execute_compiled_plan

        async def raised_execution(*args: Any, **kwargs: Any) -> Any:
            await original_execution(*args, **kwargs)
            drift()
            raise ValueError("execution sentinel")

        monkeypatch.setattr(
            worker_leaf_runner,
            "_execute_compiled_plan",
            raised_execution,
        )
    elif case == "returned_connect":
        executor = _FaultExecutor(
            "gh_connect",
            replacement={"success": False, "data": {"connected": False}},
            after_call=drift,
        )
    else:
        executor = _FaultExecutor(
            "gh_connect",
            error=ValueError("connect sentinel"),
            after_call=drift,
        )
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport()

    with pytest.raises(RuntimeError, match="Rhino context changed"):
        await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
            _INTENT,
            planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
            worker_transport=worker,
            tool_executor=executor,
        )

    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert tuple(name for name, _ in executor.calls) == expected_tools


@pytest.mark.asyncio
async def test_result_rejects_only_immediate_prefix_inversions() -> None:
    success = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=_CausalExecutor(),
    )
    refused = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(
            _PlannerTransport(_connected_raw_graph())
        ),
        worker_transport=_WorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "Cannot author this body.",
            }
        ),
        tool_executor=_CausalExecutor(),
    )

    with pytest.raises(ValueError, match="completed differs"):
        replace(
            success,
            worker_handoff_result=None,
            deterministic_execution_result=None,
            connect_request=None,
            connect_response=None,
        )
    with pytest.raises(ValueError, match="connect response requires"):
        replace(success, connect_request=None, completed=False)
    with pytest.raises(ValueError, match="deterministic execution requires"):
        replace(
            success,
            worker_handoff_result=refused.worker_handoff_result,
            completed=False,
        )
    with pytest.raises(ValueError, match="Worker handoff requires"):
        replace(success, partition_compile_result=None, completed=False)


@pytest.mark.asyncio
async def test_prompt_code_identity_and_call_authority_remain_separate() -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport()
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=semantic_runner.SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    planner_prompt = json.dumps(planner.calls[0], sort_keys=True)
    assert 'inputs\\\":[]' in planner_prompt
    assert 'outputs\\\":[{\\\"name\\\":\\\"A\\\",\\\"type\\\":\\\"double\\\"}]' in planner_prompt
    for forbidden in (
        _WORKER_BODY,
        "draft_create_body",
        _LEAF_GUID,
        _TARGET_GUID,
        "pin_index",
        '"T1"',
        "layout",
        "construct_point.x",
    ):
        assert forbidden not in planner_prompt

    worker_request = json.loads(worker.calls[0]["messages"][1]["content"])
    knowledge = {
        packet["packet_id"]: packet["content"]
        for packet in worker_request["context"]["knowledge"]
    }
    assert knowledge["planner_goal_and_interface"] == {
        "goal": _WORKER_GOAL,
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
    }
    assert [
        action["action_id"] for action in worker_request["context"]["allowed_actions"]
    ] == ["draft_create_body"]
    worker_rendered = json.dumps(worker_request, sort_keys=True)
    assert "draft_repair_params" not in worker_rendered
    assert "gh_update_script" not in worker_rendered
    assert _WORKER_BODY not in worker_rendered

    handoff = result.worker_handoff_result
    assert handoff.adapter_record.response.payload.input["code"] == _WORKER_BODY
    assert executor.calls[0][1]["code"] == _WORKER_BODY
    assert _WORKER_BODY not in repr(result.partition_compile_result)
    assert _WORKER_BODY not in repr(result.connect_request)
    assert not hasattr(result, "code")

    receipt = handoff.final_graph.nodes["create_script"].evidence.receipt
    assert result.connect_request["sourceGuid"] == receipt["mutation"]["component_guid"]
    correlation = result.deterministic_execution_result.structural_correlation
    assert [row for row in correlation if row[0] == "point"] == [
        ("point", "C2", _TARGET_GUID)
    ]
    assert result.connect_request["targetGuid"] == _TARGET_GUID
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == list(_EXPECTED_TOOLS)
