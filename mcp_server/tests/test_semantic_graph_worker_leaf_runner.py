from __future__ import annotations

import copy
import json
from collections.abc import Mapping
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
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def send(self, prompt_artifact: dict[str, object]) -> str:
        self.calls.append(copy.deepcopy(prompt_artifact))
        return self.response


class _WorkerTransport:
    def __init__(self) -> None:
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
        return json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Draft the requested numeric body.",
                "input": {"code": _WORKER_BODY},
            },
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
            "sourceIndex": 0,
            "targetGuid": _TARGET_GUID,
            "targetIndex": 0,
        }
        return {
            "success": True,
            "data": {
                "connected": True,
                "source": {"guid": _LEAF_GUID, "param": "A", "index": 0},
                "target": {"guid": _TARGET_GUID, "param": "X", "index": 0},
            },
        }


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
            "components": [{"id": "C1", "type": "CSharpScript"}],
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
                {"id": "C1", "type": "CSharpScript"},
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
    assert result.connect_response["data"]["connected"] is True


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
