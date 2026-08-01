"""Tests for the thin Planner-to-initial-body handoff integration."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from rook.agent.minimal_intent_worker_integration import (
    MinimalPlannerDraftAdapter,
    run_minimal_intent_worker_initial_body_integration,
)


_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_BODY = "A = 42.0;"
_GUID = "initial-body-integration-guid"


def _draft_payload(goal: str = _INTENT) -> dict[str, Any]:
    return {
        "goal": goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


class _PlannerTransport:
    def __init__(self, payload: object) -> None:
        self.raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt)))
        return self.raw


class _FailingPlannerTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt)))
        raise RuntimeError("declared Planner failure")


class _AdapterSubclass(MinimalPlannerDraftAdapter):
    pass


class _WorkerTransport:
    def __init__(self, payload: object | None = None) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt)))
        payload = self.payload or {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_create_body",
            "rationale": "Draft the initial body.",
            "input": {"code": _BODY},
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )


class _CreateExecutor:
    def __init__(self, *, compile_error: bool = False) -> None:
        self.compile_error = compile_error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((tool_name, captured))
        assert tool_name == "gh_create_csharp_script"
        assert captured == {
            "pins_in": (),
            "pins_out": ("A:double",),
            "name": "RookMinimalInitialBodyHandoff",
            "x": 375,
            "y": 1080,
            "code": _BODY,
        }
        errors = ["CS0103: Missing symbol"] if self.compile_error else []
        return {
            "success": not errors,
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": (
                        "created_with_errors" if errors else "usable"
                    ),
                    "mutation": {"status": "created", "component_guid": _GUID},
                    "verification": {
                        "status": "failed" if errors else "passed",
                        "target_error_count": len(errors),
                    },
                    "repair_anchor": {
                        "component_guid": _GUID,
                        "language": "csharp",
                        "target_errors": errors,
                    },
                }
            },
        }


@pytest.mark.asyncio
async def test_exact_intent_reaches_the_native_initial_body_result() -> None:
    planner = _PlannerTransport(_draft_payload())
    worker = _WorkerTransport()
    executor = _CreateExecutor()

    result = await run_minimal_intent_worker_initial_body_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.intent == _INTENT
    assert len(planner.calls) == 1
    assert result.planner_adapter_record.status == "decoded"
    assert result.validated_draft.goal == _INTENT
    assert result.handoff_result.terminal_stage == "terminal"
    assert result.terminal_stage == result.handoff_result.terminal_stage
    assert result.terminal_reason == result.handoff_result.terminal_reason
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_create_csharp_script"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("planner_transport", "expected_reason"),
    [
        (_FailingPlannerTransport(), "transport_failed"),
        (
            _PlannerTransport({**_draft_payload(), "extra": True}),
            "draft_payload_rejected",
        ),
        (_PlannerTransport(_draft_payload("Different intent")), "goal_mismatch"),
    ],
    ids=("planner_failure", "draft_rejected", "goal_mismatch"),
)
async def test_planner_stops_before_worker_and_tool(
    planner_transport: object,
    expected_reason: str,
) -> None:
    worker = _WorkerTransport()
    executor = _CreateExecutor()

    result = await run_minimal_intent_worker_initial_body_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.terminal_reason == expected_reason
    assert result.validated_draft is None
    assert result.handoff_result is None
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_worker_refusal_is_delegated_without_create() -> None:
    worker = _WorkerTransport(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "refusal",
            "category": "unsupported_action",
            "reason": "Cannot author this body.",
        }
    )
    executor = _CreateExecutor()

    result = await run_minimal_intent_worker_initial_body_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(
            _PlannerTransport(_draft_payload())
        ),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.terminal_stage == result.handoff_result.terminal_stage
    assert result.terminal_stage == "worker_disposition"
    assert len(worker.calls) == 1
    assert executor.calls == []


@pytest.mark.asyncio
async def test_compile_failure_is_delegated_without_repair() -> None:
    executor = _CreateExecutor(compile_error=True)
    result = await run_minimal_intent_worker_initial_body_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(
            _PlannerTransport(_draft_payload())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=executor,
    )

    assert result.terminal_stage == result.handoff_result.terminal_stage
    assert result.terminal_stage == "verify_create"
    assert [name for name, _ in executor.calls] == ["gh_create_csharp_script"]


@pytest.mark.asyncio
async def test_adapter_subclass_is_rejected_before_any_contact() -> None:
    planner = _PlannerTransport(_draft_payload())
    worker = _WorkerTransport()
    executor = _CreateExecutor()

    with pytest.raises(TypeError, match="exact MinimalPlannerDraftAdapter"):
        await run_minimal_intent_worker_initial_body_integration(
            _INTENT,
            planner_adapter=_AdapterSubclass(planner),
            worker_transport=worker,
            tool_executor=executor,
        )

    assert planner.calls == []
    assert worker.calls == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_result_rejects_immediate_goal_and_presence_mismatches() -> None:
    result = await run_minimal_intent_worker_initial_body_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(
            _PlannerTransport(_draft_payload())
        ),
        worker_transport=_WorkerTransport(),
        tool_executor=_CreateExecutor(),
    )

    with pytest.raises(ValueError, match="goal differs"):
        replace(result, intent="Different intent")
    with pytest.raises(TypeError, match="handoff_result"):
        replace(result, handoff_result=None)
