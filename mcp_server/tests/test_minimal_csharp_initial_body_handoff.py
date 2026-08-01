"""Tests for the Worker-authored initial C# body handoff."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from rook.agent.local_worker_adapter import TransportError
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from rook.agent.minimal_csharp_initial_body_handoff import (
    _build_initial_body_contract,
    run_minimal_csharp_initial_body_handoff,
)
from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
)


_WORKER_BODY = "A = 42.0;"
_BROKEN_WORKER_BODY = "A = MissingWorkerSymbol;"
_COMPONENT_GUID = "initial-body-component-guid"


class _StringSubclass(str):
    pass


class _WorkerTransport:
    def __init__(self, body: str = _WORKER_BODY) -> None:
        self.body = body
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        captured = copy.deepcopy(dict(prompt_artifact))
        self.calls.append(captured)
        user_message = captured["messages"][1]
        assert user_message["role"] == "user"
        request = json.loads(user_message["content"])
        rendered = set(_iter_strings(request))
        assert "Create a C# component with one double output and compile cleanly." in rendered
        assert "draft_create_body" in rendered
        assert _WORKER_BODY not in rendered
        knowledge = {
            packet["packet_id"]: packet
            for packet in request["context"]["knowledge"]
        }
        assert knowledge["planner_goal_and_interface"]["content"]["interface"] == {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        }
        return json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Author the initial body for the declared interface.",
                "input": {"code": self.body},
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class _CleanCreateExecutor:
    def __init__(self, admitted_body: str = _WORKER_BODY) -> None:
        self.admitted_body = admitted_body
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
            "code": self.admitted_body,
        }
        return _clean_create_receipt(captured["code"], self.admitted_body)


class _ScriptedWorkerTransport:
    def __init__(self, payload: object) -> None:
        self.raw_output = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self.raw_output


class _RawWorkerTransport:
    def __init__(self, raw_output: str) -> None:
        self.raw_output = raw_output
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self.raw_output


class _DeclaredFailureTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        raise TransportError("declared test transport failure")


class _ScenarioCreateExecutor:
    def __init__(
        self,
        behavior: str,
        admitted_body: str = _WORKER_BODY,
    ) -> None:
        self.behavior = behavior
        self.admitted_body = admitted_body
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
            "code": self.admitted_body,
        }
        if self.behavior == "raises":
            raise RuntimeError("declared create failure")
        if self.behavior == "malformed":
            return {}
        if self.behavior == "compile_error":
            return _compile_error_create_receipt(captured["code"])
        if self.behavior == "clean":
            return _clean_create_receipt(captured["code"], self.admitted_body)
        raise AssertionError(f"unknown create behavior: {self.behavior}")


def _clean_create_receipt(
    received_body: object,
    expected_body: str = _WORKER_BODY,
) -> dict[str, Any]:
    if received_body != expected_body:
        raise AssertionError("clean fake receipt requires the admitted Worker body")
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
                    "component_guid": _COMPONENT_GUID,
                },
                "verification": {
                    "status": "passed",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": _COMPONENT_GUID,
                    "language": "csharp",
                    "target_errors": [],
                },
            }
        },
    }


def _compile_error_create_receipt(received_body: object) -> dict[str, Any]:
    if type(received_body) is not str:
        raise AssertionError("compile-error fake requires an exact Worker body")
    prefix = "A = "
    if not received_body.startswith(prefix) or not received_body.endswith(";"):
        raise AssertionError("compile-error fake requires a simple assignment")
    missing_identifier = received_body[len(prefix) : -1]
    if not missing_identifier.isidentifier():
        raise AssertionError("compile-error fake requires a missing identifier")
    diagnostic = (
        f"CS0103: The name '{missing_identifier}' does not exist in the "
        "current context."
    )
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "component_guid": _COMPONENT_GUID,
                },
                "verification": {
                    "status": "failed",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": _COMPONENT_GUID,
                    "language": "csharp",
                    "target_errors": [diagnostic],
                },
            }
        },
    }


def _action_response(
    *,
    action_id: str = "draft_create_body",
    code: str = _WORKER_BODY,
    extra_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action_input: dict[str, Any] = {"code": code}
    if extra_input is not None:
        action_input.update(extra_input)
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": action_id,
        "rationale": "Author the initial body for the declared interface.",
        "input": action_input,
    }


def _iter_strings(value: object):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _iter_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    VerifierStepSpec,
    compile_workflow_contract,
)


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
async def test_worker_draft_walks_real_create_verify_stream_to_clean_terminal():
    worker_transport = _WorkerTransport()
    tool_executor = _CleanCreateExecutor()

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )

    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert len(worker_transport.calls) == 1
    assert [name for name, _ in tool_executor.calls] == [
        "gh_create_csharp_script"
    ]
    assert [record.accepted_node_id for record in result.step_records] == [
        "create_script",
        "verify_create",
    ]
    assert result.step_records[-1].verifier_outcome_status == "succeeded"
    assert result.final_graph.nodes["done"].status == "ready"
    assert "code" not in result.scaffold.graph.nodes[
        "create_script"
    ].metadata[EXECUTION_PARAMS_KEY]
    assert result.action_apply_result.graph.nodes[
        "create_script"
    ].metadata[EXECUTION_PARAMS_KEY]["code"] == _WORKER_BODY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "case",
        "expected_stage",
        "expected_reason",
        "expected_tool_calls",
    ),
    [
        ("transport_failure", "worker_adapter", "transport_error:declared", 0),
        ("invalid_json", "worker_adapter", "raw_output_invalid:json_decode", 0),
        ("refusal", "worker_disposition", "refusal_recorded", 0),
        ("clarification", "worker_disposition", "clarification_needed", 0),
        ("observation", "worker_disposition", "observation_recorded", 0),
        (
            "wrong_action",
            "worker_disposition",
            "blocked:unknown_action_id:draft_repair_params",
            0,
        ),
        ("extra_mode", "action_apply", "unexpected_action_input_key", 0),
        ("blank_code", "action_apply", "invalid_code", 0),
        ("create_raises", "create", "dispatch_failed", 1),
        ("create_malformed", "create", "selector_halt:none_ready", 1),
        (
            "compile_error",
            "verify_create",
            "selector_halt:none_ready",
            1,
        ),
    ],
)
async def test_handoff_stops_at_the_first_native_boundary(
    case: str,
    expected_stage: str,
    expected_reason: str | None,
    expected_tool_calls: int,
):
    transport: object = _ScriptedWorkerTransport(_action_response())
    executor = _ScenarioCreateExecutor("clean")
    if case == "transport_failure":
        transport = _DeclaredFailureTransport()
    elif case == "invalid_json":
        transport = _RawWorkerTransport("{")
    elif case == "refusal":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "Cannot author the requested body.",
            }
        )
    elif case == "clarification":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "clarification_request",
                "question": "Which body should I author?",
                "rationale": "The request appears incomplete.",
            }
        )
    elif case == "observation":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "observation",
                "message": "No action taken.",
                "data": {"status": "observed"},
            }
        )
    elif case == "wrong_action":
        transport = _ScriptedWorkerTransport(
            _action_response(action_id="draft_repair_params")
        )
    elif case == "extra_mode":
        transport = _ScriptedWorkerTransport(
            _action_response(extra_input={"mode": "body"})
        )
    elif case == "blank_code":
        transport = _ScriptedWorkerTransport(_action_response(code="   "))
    elif case == "create_raises":
        executor = _ScenarioCreateExecutor("raises")
    elif case == "create_malformed":
        executor = _ScenarioCreateExecutor("malformed")
    elif case == "compile_error":
        transport = _ScriptedWorkerTransport(
            _action_response(code=_BROKEN_WORKER_BODY)
        )
        executor = _ScenarioCreateExecutor(
            "compile_error",
            admitted_body=_BROKEN_WORKER_BODY,
        )
    else:
        raise AssertionError(f"unknown handoff case: {case}")

    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=executor,
    )

    assert result.terminal_stage == expected_stage
    if expected_reason is None:
        assert type(result.terminal_reason) is str and result.terminal_reason
    else:
        assert result.terminal_reason == expected_reason
    assert len(transport.calls) == 1
    assert len(executor.calls) == expected_tool_calls
    if case == "compile_error":
        assert result.step_records[-1].verifier_outcome_status == "needs_repair"
        assert result.final_graph.nodes["done"].status == "pending"
        assert result.supply_records[-1].reason == "selector_halt:none_ready"
        receipt = result.final_graph.nodes["create_script"].evidence.receipt
        assert receipt["repair_anchor"]["target_errors"] == [
            "CS0103: The name 'MissingWorkerSymbol' does not exist in the "
            "current context."
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "worker_context",
        "adapter_record",
        "action_graph",
        "final_graph",
        "record_order",
        "supply_metadata",
        "scaffold_scalar_subclass",
    ],
)
async def test_result_rejects_cross_transaction_splices(case: str):
    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=_WorkerTransport(),
        tool_executor=_CleanCreateExecutor(),
    )

    if case == "worker_context":
        forged_context = replace(result.worker_context, knowledge=())
        mutation = {
            "worker_context": forged_context,
            "worker_request": render_local_worker_turn_request_payload(
                forged_context
            ),
        }
    elif case == "adapter_record":
        other_body = "A = 7.0;"
        other = await run_minimal_csharp_initial_body_handoff(
            _valid_draft(),
            worker_transport=_WorkerTransport(other_body),
            tool_executor=_CleanCreateExecutor(other_body),
        )
        mutation = {"adapter_record": other.adapter_record}
    elif case == "action_graph":
        assert result.action_apply_result is not None
        mutation = {
            "action_apply_result": replace(
                result.action_apply_result,
                graph=result.scaffold.graph,
            )
        }
    elif case == "final_graph":
        mutation = {"final_graph": result.scaffold.graph}
    elif case == "record_order":
        mutation = {"step_records": tuple(reversed(result.step_records))}
    elif case == "supply_metadata":
        first_supply = replace(
            result.supply_records[0],
            metadata={"provider": "forged"},
        )
        mutation = {
            "supply_records": (first_supply,) + result.supply_records[1:]
        }
    elif case == "scaffold_scalar_subclass":
        graph = copy.deepcopy(result.scaffold.graph)
        params = dict(
            graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
        )
        params["name"] = _StringSubclass(params["name"])
        graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = params
        mutation = {"scaffold": replace(result.scaffold, graph=graph)}
    else:
        raise AssertionError(f"unknown splice case: {case}")

    with pytest.raises(ValueError):
        replace(result, **mutation)


@pytest.mark.asyncio
async def test_worker_request_exposes_only_initial_body_requirements():
    transport = _WorkerTransport()
    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=_CleanCreateExecutor(),
    )

    expected_user_content = json.dumps(
        dict(result.worker_request),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert transport.calls[0]["messages"][1] == {
        "role": "user",
        "content": expected_user_content,
    }
    context = result.worker_request["context"]
    knowledge = {
        packet["packet_id"]: packet
        for packet in context["knowledge"]
    }
    assert knowledge["planner_goal_and_interface"]["content"] == {
        "goal": "Create a C# component with one double output and compile cleanly.",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
    }
    assert knowledge["script_body_gotcha"]["content"] == {
        "body_mode": "body"
    }
    assert knowledge["clean_compile_acceptance"]["content"] == {
        "verifier_node_id": "verify_create",
        "source_node_id": "create_script",
        "expected_outcome": "succeeded",
        "criterion": (
            "The initial C# body must compile cleanly for the declared interface."
        ),
    }
    assert context["allowed_actions"] == [
        {
            "action_id": "draft_create_body",
            "kind": "draft_create_body",
            "description": "Draft the complete initial C# body.",
            "input_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        }
    ]
    rendered_strings = set(_iter_strings(result.worker_request))
    rendered_keys = set(_iter_keys(result.worker_request))
    assert {
        "draft_repair_params",
        "gh_update_script",
        "DefinitelyMissingSymbol",
        _WORKER_BODY,
        _COMPONENT_GUID,
    }.isdisjoint(rendered_strings)
    assert {
        "edges",
        "rules",
        "execution_params",
        "component_guid",
        "diagnostic",
    }.isdisjoint(rendered_keys)


@pytest.mark.asyncio
async def test_worker_response_is_the_only_initial_body_authority():
    changed_body = "A = 7.0;"
    result = await run_minimal_csharp_initial_body_handoff(
        _valid_draft(),
        worker_transport=_WorkerTransport(changed_body),
        tool_executor=_CleanCreateExecutor(changed_body),
    )

    assert result.adapter_record.response is not None
    response_payload = result.adapter_record.response.payload
    assert response_payload.input == {"code": changed_body}
    assert result.worker_record is not None
    assert result.worker_record.response is result.adapter_record.response
    assert result.action_apply_result is not None
    assert result.action_apply_result.graph.nodes[
        "create_script"
    ].metadata[EXECUTION_PARAMS_KEY]["code"] == changed_body
    assert "code" not in result.scaffold.graph.nodes[
        "create_script"
    ].metadata[EXECUTION_PARAMS_KEY]
    assert not hasattr(result, "code")


def _iter_keys(value: object):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _iter_keys(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_keys(item)
