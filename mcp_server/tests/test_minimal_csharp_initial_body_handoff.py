"""Tests for the Worker-authored initial C# body handoff."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from rook.agent.minimal_csharp_initial_body_handoff import (
    _build_initial_body_contract,
    run_minimal_csharp_initial_body_handoff,
)
from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    VerifierStepSpec,
    compile_workflow_contract,
)


_WORKER_BODY = "A = 42.0;"
_COMPONENT_GUID = "initial-body-component-guid"


class _WorkerTransport:
    def __init__(self, payload: object | None = None) -> None:
        self.payload = payload if payload is not None else {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_create_body",
            "rationale": "Draft the initial body.",
            "input": {"code": _WORKER_BODY},
        }
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        captured = copy.deepcopy(dict(prompt_artifact))
        self.calls.append(captured)
        request = json.loads(captured["messages"][1]["content"])
        rendered = json.dumps(request, sort_keys=True)
        assert _valid_draft().goal in rendered
        assert "draft_create_body" in rendered
        assert _WORKER_BODY not in rendered
        assert "draft_repair_params" not in rendered
        assert "gh_update_script" not in rendered
        assert "component_guid" not in rendered
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":"))


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
            "code": _WORKER_BODY,
        }
        errors = ["CS0103: Missing symbol"] if self.compile_error else []
        return {
            "success": not self.compile_error,
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": (
                        "created_with_errors" if errors else "usable"
                    ),
                    "mutation": {
                        "status": "created",
                        "component_guid": _COMPONENT_GUID,
                    },
                    "verification": {
                        "status": "failed" if errors else "passed",
                        "target_error_count": len(errors),
                    },
                    "repair_anchor": {
                        "component_guid": _COMPONENT_GUID,
                        "language": "csharp",
                        "target_errors": errors,
                    },
                }
            },
        }


def _valid_draft(
    goal: str = "Create a C# component with one double output and compile cleanly.",
) -> ValidatedPlannerDraft:
    return load_minimal_csharp_repair_draft(
        {
            "goal": goal,
            "capability": "grasshopper_csharp_component",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
            "acceptance": "clean_compile_receipt",
        }
    )


@pytest.mark.asyncio
async def test_worker_request_requires_body_statements_not_plugin_source() -> None:
    worker = _WorkerTransport()

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=worker,
        tool_executor=_CreateExecutor(),
    )

    request = json.loads(worker.calls[0]["messages"][1]["content"])
    knowledge = {
        packet["packet_id"]: packet["content"]
        for packet in request["context"]["knowledge"]
    }
    assert knowledge["script_body_gotcha"] == {
        "body_mode": "body",
        "instructions": [
            "Author only executable C# statements for the script body.",
            (
                "The component and declared output variables already exist; "
                "assign to them directly."
            ),
            (
                "Do not return a class, GH_Component, Script_Instance, a "
                "RunScript method, a namespace, using directives, a component "
                "GUID, pin registration, or markdown fences."
            ),
        ],
    }
    assert result.terminal_stage == "terminal"


def test_builder_compiles_exact_incomplete_create_verify_scaffold():
    contract = _build_initial_body_contract(_valid_draft())
    scaffold = compile_workflow_contract(contract)

    assert scaffold.compile_record.expected_template_id == "gh_csharp_create_verify"
    assert scaffold.compile_record.selected_template_id == "gh_csharp_create_verify"
    assert scaffold.max_steps == 4
    assert tuple(scaffold.graph.nodes) == (
        "create_script",
        "verify_create",
        "done",
    )
    params = scaffold.graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    assert params == {
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "RookMinimalInitialBodyHandoff",
        "x": 375,
        "y": 1080,
    }
    assert scaffold.compile_record.expected_refs == (
        ("create_script", "gh_create_csharp_script:v1"),
    )
    assert scaffold.compile_record.step_kinds_by_rule == (
        ("create_script", ("producer",)),
        ("verify_create", ("verifier",)),
    )
    assert all(
        not isinstance(step, BindStepSpec)
        for rule in contract.rules
        for step in rule.steps_by_seen_count
    )
    assert tuple(rule.node_id for rule in contract.rules) == (
        "create_script",
        "verify_create",
    )
    verify_steps = contract.rules[1].steps_by_seen_count
    assert len(verify_steps) == 1
    assert type(verify_steps[0]) is VerifierStepSpec
    assert verify_steps[0].verifier_node_id == "verify_create"
    assert verify_steps[0].source_node_id == "create_script"
    assert verify_steps[0].expected_outcome == "succeeded"


def test_different_goals_do_not_move_compiler_owned_contract_fields():
    first = _build_initial_body_contract(_valid_draft("First goal"))
    second = _build_initial_body_contract(_valid_draft("Second goal"))

    assert first.template == second.template
    assert first.initial_params == second.initial_params
    assert first.rules == second.rules
    assert first.terminal_node_ids == second.terminal_node_ids
    assert first.expected_refs == second.expected_refs
    assert first.max_steps == second.max_steps
    assert first.metadata == second.metadata


@pytest.mark.asyncio
async def test_one_worker_body_creates_and_verifies_once() -> None:
    worker = _WorkerTransport()
    executor = _CreateExecutor()

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_create_csharp_script"]
    assert [record.accepted_node_id for record in result.step_records] == [
        "create_script",
        "verify_create",
    ]
    assert result.step_records[-1].verifier_outcome_status == "succeeded"
    assert result.final_graph.nodes["done"].status == "ready"
    original_params = result.scaffold.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    assert "code" not in original_params
    assert result.action_apply_result.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]["code"] == _WORKER_BODY
    assert not hasattr(result, "code")


@pytest.mark.asyncio
async def test_compile_error_stops_without_repair_or_update() -> None:
    worker = _WorkerTransport()
    executor = _CreateExecutor(compile_error=True)

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.terminal_stage == "verify_create"
    assert result.terminal_reason == "selector_halt:none_ready"
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_create_csharp_script"]
    assert result.step_records[-1].verifier_outcome_status == "needs_repair"
    assert result.final_graph.nodes["done"].status == "pending"
    receipt = result.final_graph.nodes["create_script"].evidence.receipt
    assert receipt["repair_anchor"]["target_errors"] == [
        "CS0103: Missing symbol"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_stage"),
    [
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "Cannot author this body.",
            },
            "worker_disposition",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "rationale": "Wrong action.",
                "input": {"code": _WORKER_BODY},
            },
            "worker_disposition",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Extra field.",
                "input": {"code": _WORKER_BODY, "mode": "body"},
            },
            "action_apply",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Blank body.",
                "input": {"code": "   "},
            },
            "action_apply",
        ),
    ],
    ids=("refusal", "wrong_action", "extra_input", "blank_code"),
)
async def test_worker_stops_before_create(
    payload: object,
    expected_stage: str,
) -> None:
    worker = _WorkerTransport(payload)
    executor = _CreateExecutor()

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.terminal_stage == expected_stage
    assert len(worker.calls) == 1
    assert executor.calls == []


@pytest.mark.asyncio
async def test_action_apply_stage_rejects_an_applied_action() -> None:
    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=_WorkerTransport(),
        tool_executor=_CreateExecutor(),
    )

    with pytest.raises(ValueError, match="action state"):
        replace(
            result,
            final_graph=result.scaffold.graph,
            supply_records=(),
            step_records=(),
            terminal_stage="action_apply",
            terminal_reason="invalid_action_stage",
        )


@pytest.mark.asyncio
async def test_create_stage_rejects_a_rejected_action() -> None:
    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=_WorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Blank body.",
                "input": {"code": "   "},
            }
        ),
        tool_executor=_CreateExecutor(),
    )
    assert result.terminal_stage == "action_apply"

    with pytest.raises(ValueError, match="action state"):
        replace(result, terminal_stage="create")
