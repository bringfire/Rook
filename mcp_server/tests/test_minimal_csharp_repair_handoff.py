from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.local_worker_turn_harness as worker_harness
import rook.agent.minimal_csharp_repair_handoff as handoff
from rook.agent.local_worker_adapter import TransportError
from rook.agent.minimal_csharp_repair_handoff import (
    MinimalCSharpRepairHandoffResult,
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
    run_minimal_csharp_repair_handoff,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    ProducerStepSpec,
    compile_workflow_contract,
    snapshot_workflow_contract,
)
from rook.learning.plan_graph import graph_status


_COMPONENT_GUID = "minimal-handoff-component-guid"
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKER_BODY = "A = 42.0;"
_TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


class _FakePlanner:
    def draft(self) -> dict[str, Any]:
        return {
            "goal": "Create a C# component with one double output and compile cleanly.",
            "capability": "grasshopper_csharp_component",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
            "acceptance": "clean_compile_receipt",
        }


class _EqualitySpoof:
    def __init__(self, rendered: str) -> None:
        self.rendered = rendered

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    def __str__(self) -> str:
        return self.rendered


def _valid_draft() -> ValidatedPlannerDraft:
    return load_minimal_csharp_repair_draft(_FakePlanner().draft())


def _payload_with_equality_spoof(field: str) -> dict[str, Any]:
    payload = _FakePlanner().draft()
    if field == "output name":
        payload["interface"]["outputs"][0]["name"] = _EqualitySpoof("B")
    elif field == "output type":
        payload["interface"]["outputs"][0]["type"] = _EqualitySpoof("integer")
    elif field == "capability":
        payload["capability"] = _EqualitySpoof("forged_capability")
    elif field == "acceptance":
        payload["acceptance"] = _EqualitySpoof("forged_acceptance")
    else:
        raise AssertionError(f"unknown equality-spoof field: {field}")
    return payload


def _mutate_draft_with_equality_spoof(
    draft: ValidatedPlannerDraft,
    field: str,
) -> None:
    if field == "output name":
        object.__setattr__(draft.interface.outputs[0], "name", _EqualitySpoof("B"))
    elif field == "output type":
        object.__setattr__(
            draft.interface.outputs[0],
            "type",
            _EqualitySpoof("integer"),
        )
    elif field == "capability":
        object.__setattr__(draft, "capability", _EqualitySpoof("forged_capability"))
    elif field == "acceptance":
        object.__setattr__(draft, "acceptance", _EqualitySpoof("forged_acceptance"))
    else:
        raise AssertionError(f"unknown equality-spoof field: {field}")


def _invalid_draft_payload(case: str) -> object:
    payload = _FakePlanner().draft()
    if case == "not_mapping":
        return []
    if case == "missing_goal":
        payload.pop("goal")
    elif case == "missing_capability":
        payload.pop("capability")
    elif case == "missing_interface":
        payload.pop("interface")
    elif case == "missing_acceptance":
        payload.pop("acceptance")
    elif case == "goal_empty":
        payload["goal"] = "   "
    elif case == "goal_not_string":
        payload["goal"] = 7
    elif case == "wrong_capability":
        payload["capability"] = "other"
    elif case == "interface_not_mapping":
        payload["interface"] = []
    elif case == "interface_extra":
        payload["interface"]["code"] = "A = 1.0;"
    elif case == "inputs_nonempty":
        payload["interface"]["inputs"] = [{"name": "X", "type": "double"}]
    elif case == "inputs_wrong_type":
        payload["interface"]["inputs"] = "none"
    elif case == "outputs_empty":
        payload["interface"]["outputs"] = []
    elif case == "outputs_wrong_type":
        payload["interface"]["outputs"] = "A:double"
    elif case == "outputs_duplicate":
        payload["interface"]["outputs"].append({"name": "A", "type": "double"})
    elif case == "output_not_mapping":
        payload["interface"]["outputs"] = ["A:double"]
    elif case == "output_missing_name":
        payload["interface"]["outputs"] = [{"type": "double"}]
    elif case == "output_missing_type":
        payload["interface"]["outputs"] = [{"name": "A"}]
    elif case == "output_extra":
        payload["interface"]["outputs"][0]["unit"] = None
    elif case == "output_wrong_name":
        payload["interface"]["outputs"][0]["name"] = "B"
    elif case == "output_wrong_type":
        payload["interface"]["outputs"][0]["type"] = "integer"
    elif case == "wrong_acceptance":
        payload["acceptance"] = "output_equals_constant"
    elif case in {"code", "action_id", "template", "graph", "worker"}:
        payload[case] = "not_authorized"
    else:
        raise AssertionError(f"unknown invalid draft case: {case}")
    return payload


class _RecordingWorkerTransport:
    def __init__(self, expected_diagnostic: str) -> None:
        self.expected_diagnostic = expected_diagnostic
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        captured = copy.deepcopy(dict(prompt_artifact))
        self.calls.append(captured)
        user_message = captured["messages"][1]
        assert user_message["role"] == "user"
        request_payload = json.loads(user_message["content"])
        assert self.expected_diagnostic in set(_iter_strings(request_payload))
        return json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "rationale": "Replace the invalid body while preserving A:double.",
                "input": {"code": _WORKER_BODY, "mode": "body"},
            },
            sort_keys=True,
            separators=(",", ":"),
        )


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
        raise TransportError("declared test transport stop")


class _RecordingToolExecutor:
    def __init__(self, diagnostic: str = _TARGET_DIAGNOSTIC) -> None:
        self.diagnostic = diagnostic
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((tool_name, captured))
        if tool_name == "gh_create_csharp_script":
            assert captured["code"] == _INITIAL_BODY
            assert captured["pins_in"] == ()
            assert captured["pins_out"] == ("A:double",)
            return _created_with_errors_raw(captured["code"], self.diagnostic)
        if tool_name == "gh_update_script":
            assert captured == {
                "guid": _COMPONENT_GUID,
                "code": _WORKER_BODY,
                "mode": "body",
                "language": "csharp",
            }
            return _usable_clean_raw()
        raise AssertionError(f"unexpected tool: {tool_name}")


class _ScenarioToolExecutor:
    def __init__(
        self,
        *,
        create: str = "needs_repair",
        repair: str = "clean",
    ) -> None:
        self.create = create
        self.repair = repair
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((tool_name, captured))
        if tool_name == "gh_create_csharp_script":
            return self._create(captured)
        if tool_name == "gh_update_script":
            return self._repair(captured)
        raise AssertionError(f"unexpected tool: {tool_name}")

    def _create(self, params: dict[str, Any]) -> dict[str, Any]:
        assert params["code"] == _INITIAL_BODY
        if self.create == "raises":
            raise RuntimeError("create dispatch failed")
        if self.create == "malformed":
            return {}
        if self.create == "refused":
            return {"success": False, "error": "declared refusal"}
        if self.create == "clean":
            return _created_clean_raw()
        if self.create == "needs_repair":
            return _created_with_errors_raw(params["code"], _TARGET_DIAGNOSTIC)
        raise AssertionError(f"unknown create behavior: {self.create}")

    def _repair(self, params: dict[str, Any]) -> dict[str, Any]:
        assert params == {
            "guid": _COMPONENT_GUID,
            "code": _WORKER_BODY,
            "mode": "body",
            "language": "csharp",
        }
        if self.repair == "raises":
            raise RuntimeError("repair dispatch failed")
        if self.repair == "malformed":
            return {}
        if self.repair == "still_broken":
            return _repair_with_errors_raw()
        if self.repair == "clean":
            return _usable_clean_raw()
        raise AssertionError(f"unknown repair behavior: {self.repair}")


def _created_with_errors_raw(
    received_body: object,
    diagnostic: str,
) -> dict[str, Any]:
    if received_body != _INITIAL_BODY:
        raise AssertionError("fake create diagnostic requires the invalid specimen body")
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


def _created_clean_raw() -> dict[str, Any]:
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


def _usable_clean_raw() -> dict[str, Any]:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {
                "status": "written",
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
    }


def _repair_with_errors_raw() -> dict[str, Any]:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "created_with_errors",
            "mutation": {
                "status": "written",
                "component_guid": _COMPONENT_GUID,
            },
            "verification": {
                "status": "failed",
                "target_error_count": 1,
            },
            "repair_anchor": {
                "component_guid": _COMPONENT_GUID,
                "language": "csharp",
                "target_errors": ["CS9999: repair remains invalid"],
            },
        }
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


def _action_response_payload(
    *,
    rationale: str = "Replace the invalid body while preserving A:double.",
) -> dict[str, Any]:
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": rationale,
        "input": {"code": _WORKER_BODY, "mode": "body"},
    }


def _invalid_action_response_payload(case: str) -> dict[str, Any]:
    payload = _action_response_payload()
    if case.startswith("missing_"):
        payload.pop(case.removeprefix("missing_"))
    elif case == "extra_field":
        payload["unexpected"] = True
    elif case == "wrong_schema":
        payload["schema"] = "rook.local_worker_turn_response:v999"
    elif case == "wrong_kind":
        payload["kind"] = "unsupported"
    elif case == "wrong_action":
        payload["action_id"] = "other_action"
    elif case == "malformed_input":
        payload["input"] = []
    elif case == "wrong_mode":
        payload["input"]["mode"] = "full"
    else:
        raise AssertionError(f"unknown invalid worker response case: {case}")
    return payload


async def _run_operational_case(
    case: str,
) -> tuple[
    MinimalCSharpRepairHandoffResult,
    object,
    _ScenarioToolExecutor,
]:
    tool_executor = _ScenarioToolExecutor()
    transport: object = _ScriptedWorkerTransport(_action_response_payload())

    if case.startswith("create_"):
        tool_executor = _ScenarioToolExecutor(
            create=case.removeprefix("create_")
        )
    elif case == "verify_create_clean":
        tool_executor = _ScenarioToolExecutor(create="clean")
    elif case == "transport_declared":
        transport = _DeclaredFailureTransport()
    elif case == "adapter_invalid_json":
        transport = _RawWorkerTransport("{")
    elif case == "adapter_invalid_payload":
        transport = _ScriptedWorkerTransport(
            _invalid_action_response_payload("missing_schema")
        )
    elif case == "clarification":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "clarification_request",
                "question": "Which replacement body should I author?",
                "rationale": None,
            }
        )
    elif case == "refusal":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "insufficient_context",
                "reason": "A repair cannot be determined.",
            }
        )
    elif case == "observation":
        transport = _ScriptedWorkerTransport(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "observation",
                "message": "The current component needs repair.",
                "data": None,
            }
        )
    elif case == "unknown_action":
        transport = _ScriptedWorkerTransport(
            _invalid_action_response_payload("wrong_action")
        )
    elif case in {"action_extra", "action_blank", "action_wrong_mode"}:
        payload = _action_response_payload()
        if case == "action_extra":
            payload["input"]["unexpected"] = True
        elif case == "action_blank":
            payload["input"]["code"] = "   "
        else:
            payload["input"]["mode"] = "full"
        transport = _ScriptedWorkerTransport(payload)
    elif case == "repair_raises":
        tool_executor = _ScenarioToolExecutor(repair="raises")
    elif case == "repair_malformed":
        tool_executor = _ScenarioToolExecutor(repair="malformed")
    elif case == "verify_repair_stops":
        tool_executor = _ScenarioToolExecutor(repair="still_broken")
    elif case != "terminal":
        raise AssertionError(f"unknown operational case: {case}")

    result = await run_minimal_csharp_repair_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=tool_executor,
    )
    return result, transport, tool_executor


def _json_key_paths(
    value: object,
    path: tuple[object, ...] = (),
):
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_path = path + (key,)
            yield key_path
            yield from _json_key_paths(item, key_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _json_key_paths(item, path + (index,))


@pytest.mark.asyncio
async def test_raw_draft_walks_real_repair_handoff_to_clean_terminal() -> None:
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    draft = load_minimal_csharp_repair_draft(_FakePlanner().draft())
    result = await run_minimal_csharp_repair_handoff(
        draft,
        worker_transport=transport,
        tool_executor=tool_executor,
    )

    assert isinstance(draft, ValidatedPlannerDraft)
    assert isinstance(result, MinimalCSharpRepairHandoffResult)
    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert result.final_graph.nodes["done"].status == "ready"
    assert [name for name, _params in tool_executor.calls] == [
        "gh_create_csharp_script",
        "gh_update_script",
    ]
    assert len(transport.calls) == 1
    assert result.adapter_record is not None
    assert result.adapter_record.status == "response_loaded"
    assert result.worker_record is not None
    assert result.worker_record.disposition is not None
    assert result.worker_record.disposition.disposition == "candidate_action_request"
    assert result.action_apply_result is not None
    assert result.action_apply_result.applied is True
    assert [record.accepted_node_id for record in result.step_records] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
    ]
    assert result.step_records[-1].verifier_outcome_status == "succeeded"
    assert result.supply_records[-1].decision == "HALT"
    assert result.supply_records[-1].reason == "terminal_node_selected:done"
    assert result.terminal_reason == result.supply_records[-1].reason


@pytest.mark.asyncio
async def test_worker_prompt_exactly_serializes_the_visible_request() -> None:
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    draft = _valid_draft()

    result = await run_minimal_csharp_repair_handoff(
        draft,
        worker_transport=transport,
        tool_executor=_RecordingToolExecutor(),
    )

    assert result.worker_request is not None
    expected_user = json.dumps(
        dict(result.worker_request),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert transport.calls[0]["messages"][1] == {
        "role": "user",
        "content": expected_user,
    }

    context = result.worker_request["context"]
    knowledge = {
        packet["packet_id"]: packet
        for packet in context["knowledge"]
    }
    assert knowledge["planner_goal_and_interface"]["content"] == {
        "goal": draft.goal,
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
    }
    assert knowledge["script_body_gotcha"]["content"] == {
        "body_mode": "body"
    }
    acceptance = knowledge["clean_compile_acceptance"]["content"]
    assert acceptance["schema"] == "rook.acceptance_criteria_packet:v1"
    assert acceptance["fingerprint"].startswith("sha256:")
    assert len(acceptance["fingerprint"]) == 71
    assert knowledge["current_receipt_diagnostic"]["content"] == {
        "source_class": "receipt_diagnostic",
        "source_path": (
            "create_script.receipt.script_receipt.repair_anchor.target_errors"
        ),
        "target_errors": [_TARGET_DIAGNOSTIC],
    }
    assert context["allowed_actions"] == [
        {
            "action_id": "draft_repair_params",
            "kind": "draft_repair_params",
            "description": "Draft a complete replacement C# body.",
            "input_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "mode": {"const": "body"},
                },
                "required": ["code", "mode"],
            },
        }
    ]


@pytest.mark.asyncio
async def test_worker_request_excludes_code_guid_and_topology_authority() -> None:
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    result = await run_minimal_csharp_repair_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=_RecordingToolExecutor(),
    )

    assert result.worker_request is not None
    assert len(transport.calls) == 1
    strings = tuple(_iter_strings(transport.calls[0]))
    for value in strings:
        assert _INITIAL_BODY not in value
        assert _WORKER_BODY not in value
        assert _COMPONENT_GUID not in value

    key_paths = tuple(_json_key_paths(result.worker_request))
    keys = {path[-1] for path in key_paths}
    assert "edges" not in keys
    assert "rules" not in keys
    assert EXECUTION_PARAMS_KEY not in keys
    assert not keys.intersection(
        {
            "expected_code",
            "repair_code",
            "suggested_code",
            "suggestion",
            "patch",
        }
    )
    assert [path for path in key_paths if path[-1] == "code"] == [
        (
            "context",
            "allowed_actions",
            0,
            "input_schema",
            "properties",
            "code",
        )
    ]


@pytest.mark.asyncio
async def test_convention_packet_drift_stops_before_worker_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = handoff._script_body_gotcha_packet()
    mutated = handoff.WorkerKnowledgePacket(
        packet_id=original.packet_id,
        kind=original.kind,
        title=original.title,
        content={"body_mode": "full"},
    )
    monkeypatch.setattr(
        handoff,
        "_script_body_gotcha_packet",
        lambda: mutated,
    )
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(
        RuntimeError,
        match="worker convention mode differs from acceptance source",
    ):
        await run_minimal_csharp_repair_handoff(
            _valid_draft(),
            worker_transport=transport,
            tool_executor=tool_executor,
        )

    assert transport.calls == []
    assert [name for name, _params in tool_executor.calls] == [
        "gh_create_csharp_script"
    ]


@pytest.mark.asyncio
async def test_changed_receipt_diagnostic_reaches_exact_worker_request() -> None:
    diagnostic = (
        "SENTINEL-RECEIPT: CS0103: The name 'DefinitelyMissingSymbol' "
        "does not exist in the current context."
    )
    transport = _RecordingWorkerTransport(diagnostic)

    result = await run_minimal_csharp_repair_handoff(
        load_minimal_csharp_repair_draft(_FakePlanner().draft()),
        worker_transport=transport,
        tool_executor=_RecordingToolExecutor(diagnostic),
    )

    assert result.terminal_stage == "terminal"
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("case", "terminal_stage"),
    [
        ("missing_schema", "worker_adapter"),
        ("missing_kind", "worker_adapter"),
        ("missing_action_id", "worker_adapter"),
        ("missing_rationale", "worker_adapter"),
        ("missing_input", "worker_adapter"),
        ("extra_field", "worker_adapter"),
        ("wrong_schema", "worker_adapter"),
        ("wrong_kind", "worker_adapter"),
        ("wrong_action", "worker_disposition"),
        ("malformed_input", "worker_adapter"),
        ("wrong_mode", "action_apply"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_raw_worker_response_never_reaches_repair_tool(
    case: str,
    terminal_stage: str,
) -> None:
    transport = _ScriptedWorkerTransport(
        _invalid_action_response_payload(case)
    )
    tool_executor = _RecordingToolExecutor()

    result = await run_minimal_csharp_repair_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=tool_executor,
    )

    assert result.terminal_stage == terminal_stage
    assert len(transport.calls) == 1
    assert [name for name, _params in tool_executor.calls] == [
        "gh_create_csharp_script"
    ]


@pytest.mark.asyncio
async def test_adapter_loaded_response_is_exact_one_shot_harness_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_harness = handoff.run_local_worker_turn
    original_disposition = worker_harness.dispose_local_worker_turn_response
    observed: dict[str, Any] = {
        "harness_calls": 0,
        "worker_calls": 0,
        "disposition_calls": 0,
        "disposition_responses": [],
        "responses": [],
    }

    def audited_harness(context: object, worker: object):
        observed["harness_calls"] += 1

        def audited_worker(supplied_context: object):
            observed["worker_calls"] += 1
            response = worker(supplied_context)
            observed["responses"].append(response)
            return response

        return original_harness(context, audited_worker)

    def audited_disposition(context: object, response: object):
        observed["disposition_calls"] += 1
        observed["disposition_responses"].append(response)
        return original_disposition(context, response)

    monkeypatch.setattr(handoff, "run_local_worker_turn", audited_harness)
    monkeypatch.setattr(
        worker_harness,
        "dispose_local_worker_turn_response",
        audited_disposition,
    )
    transport = _ScriptedWorkerTransport(_action_response_payload())
    result = await run_minimal_csharp_repair_handoff(
        _valid_draft(),
        worker_transport=transport,
        tool_executor=_RecordingToolExecutor(),
    )

    assert len(transport.calls) == 1
    assert observed["harness_calls"] == 1
    assert observed["worker_calls"] == 1
    assert observed["disposition_calls"] == 1
    assert result.adapter_record is not None
    assert result.worker_record is not None
    assert observed["responses"] == [result.adapter_record.response]
    assert observed["disposition_responses"] == [result.adapter_record.response]
    assert result.worker_record.response is result.adapter_record.response


@pytest.mark.parametrize(
    "rationale",
    [
        "Replace the invalid body while preserving A:double.",
        "A different non-authoritative explanation.",
    ],
)
@pytest.mark.asyncio
async def test_worker_rationale_does_not_enter_action_parameters(
    rationale: str,
) -> None:
    result = await run_minimal_csharp_repair_handoff(
        _valid_draft(),
        worker_transport=_ScriptedWorkerTransport(
            _action_response_payload(rationale=rationale)
        ),
        tool_executor=_RecordingToolExecutor(),
    )

    assert result.adapter_record is not None
    assert result.adapter_record.response is not None
    assert result.adapter_record.response.payload.rationale == rationale
    assert result.action_apply_result is not None
    assert result.action_apply_result.params_sha256 == (
        "4b5ff636e245b7eae50899fa7f0a5b5c167c01d6ed6a977174188206e1eef010"
    )
    assert result.final_graph.nodes["repair_same_component"].metadata[
        EXECUTION_PARAMS_KEY
    ] == {
        "guid": _COMPONENT_GUID,
        "code": _WORKER_BODY,
        "mode": "body",
        "language": "csharp",
    }


@pytest.mark.parametrize(
    (
        "case",
        "terminal_stage",
        "terminal_reason",
        "tool_names",
        "worker_calls",
    ),
    [
        ("create_raises", "create", "dispatch_failed", ["gh_create_csharp_script"], 0),
        (
            "create_refused",
            "create",
            "selector_halt:none_ready",
            ["gh_create_csharp_script"],
            0,
        ),
        (
            "create_malformed",
            "create",
            "selector_halt:none_ready",
            ["gh_create_csharp_script"],
            0,
        ),
        (
            "verify_create_clean",
            "verify_create",
            "executed verifier step 'verify_create'",
            ["gh_create_csharp_script"],
            0,
        ),
        (
            "transport_declared",
            "worker_adapter",
            "transport_error:declared",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "adapter_invalid_json",
            "worker_adapter",
            "raw_output_invalid:json_decode",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "adapter_invalid_payload",
            "worker_adapter",
            (
                "response_payload_invalid:local_worker_turn_response_payload_"
                "missing_required_fields____schema"
            ),
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "clarification",
            "worker_disposition",
            "clarification_needed",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "refusal",
            "worker_disposition",
            "refusal_recorded",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "observation",
            "worker_disposition",
            "observation_recorded",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "unknown_action",
            "worker_disposition",
            "blocked:unknown_action_id:other_action",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "action_extra",
            "action_apply",
            "unexpected_action_input_key",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "action_blank",
            "action_apply",
            "invalid_code",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "action_wrong_mode",
            "action_apply",
            "invalid_mode",
            ["gh_create_csharp_script"],
            1,
        ),
        (
            "repair_raises",
            "repair",
            "dispatch_failed",
            ["gh_create_csharp_script", "gh_update_script"],
            1,
        ),
        (
            "repair_malformed",
            "repair",
            "selector_halt:none_ready",
            ["gh_create_csharp_script", "gh_update_script"],
            1,
        ),
        (
            "verify_repair_stops",
            "verify_repair",
            "selector_halt:none_ready",
            ["gh_create_csharp_script", "gh_update_script"],
            1,
        ),
        (
            "terminal",
            "terminal",
            "terminal_node_selected:done",
            ["gh_create_csharp_script", "gh_update_script"],
            1,
        ),
    ],
)
@pytest.mark.asyncio
async def test_operational_stop_matrix_preserves_native_terminal_reason(
    case: str,
    terminal_stage: str,
    terminal_reason: str,
    tool_names: list[str],
    worker_calls: int,
) -> None:
    result, transport, tool_executor = await _run_operational_case(case)

    assert result.terminal_stage == terminal_stage
    assert result.terminal_reason == terminal_reason
    assert [name for name, _params in tool_executor.calls] == tool_names
    assert len(transport.calls) == worker_calls

    if terminal_stage in {"create", "verify_create"}:
        assert result.worker_request is None
        assert result.worker_context is None
        assert result.adapter_record is None
        assert result.worker_record is None
        assert result.action_apply_result is None
    elif terminal_stage == "worker_adapter":
        assert result.worker_request is not None
        assert result.worker_context is not None
        assert result.adapter_record is not None
        assert result.worker_record is None
        assert result.action_apply_result is None
    elif terminal_stage == "worker_disposition":
        assert result.adapter_record is not None
        assert result.worker_record is not None
        assert result.worker_record.disposition is not None
        assert result.action_apply_result is None
    elif terminal_stage == "action_apply":
        assert result.action_apply_result is not None
        assert result.action_apply_result.applied is False
    else:
        assert result.action_apply_result is not None
        assert result.action_apply_result.applied is True


@pytest.mark.asyncio
async def test_result_rejects_impossible_optional_record_combinations() -> None:
    create, _transport, _tool = await _run_operational_case("create_raises")
    adapter, _transport, _tool = await _run_operational_case("transport_declared")
    disposition, _transport, _tool = await _run_operational_case("clarification")
    action, _transport, _tool = await _run_operational_case("action_wrong_mode")
    success, _transport, _tool = await _run_operational_case("terminal")

    with pytest.raises(ValueError):
        replace(
            create,
            worker_request=success.worker_request,
            worker_context=success.worker_context,
        )
    with pytest.raises(ValueError):
        replace(adapter, worker_record=success.worker_record)
    with pytest.raises(ValueError):
        replace(disposition, action_apply_result=success.action_apply_result)
    with pytest.raises(ValueError):
        replace(action, action_apply_result=success.action_apply_result)
    with pytest.raises(ValueError):
        replace(success, terminal_stage="repair", action_apply_result=None)
    with pytest.raises(ValueError):
        replace(success, terminal_reason="synthetic_success")
    with pytest.raises(ValueError):
        replace(success, step_records=success.step_records[:-1])


@pytest.mark.asyncio
async def test_result_rejects_worker_request_not_rendered_from_context() -> None:
    success, _transport, _tool = await _run_operational_case("terminal")

    with pytest.raises(ValueError, match="worker_request"):
        replace(success, worker_request={"forged": True})


@pytest.mark.asyncio
async def test_result_rejects_reclosed_worker_context_outside_transaction() -> None:
    success, _transport, _tool = await _run_operational_case("terminal")
    assert success.worker_context is not None
    forged_context = replace(success.worker_context, knowledge=())
    forged_request = handoff.render_local_worker_turn_request_payload(
        forged_context
    )

    with pytest.raises(ValueError, match="worker_context"):
        replace(
            success,
            worker_context=forged_context,
            worker_request=forged_request,
        )


@pytest.mark.asyncio
async def test_result_rejects_reclosed_harness_context_identity() -> None:
    success, _transport, _tool = await _run_operational_case("terminal")
    assert success.worker_record is not None
    assert success.worker_record.disposition is not None
    disposition = success.worker_record.disposition
    forged_attempt = replace(
        disposition.attempt,
        context_workflow_id="other_workflow",
    )
    forged_disposition = replace(disposition, attempt=forged_attempt)
    forged_record = replace(
        success.worker_record,
        disposition=forged_disposition,
        context_workflow_id="other_workflow",
    )

    with pytest.raises(ValueError, match="harness.*workflow"):
        replace(success, worker_record=forged_record)


@pytest.mark.parametrize("mutation", ["reordered", "replaced"])
@pytest.mark.asyncio
async def test_result_rejects_non_native_step_record_prefix(
    mutation: str,
) -> None:
    success, _transport, _tool = await _run_operational_case("terminal")
    records = list(success.step_records)
    if mutation == "reordered":
        records[0], records[1] = records[1], records[0]
    else:
        records[1] = records[0]

    with pytest.raises(ValueError, match="native record prefix"):
        replace(success, step_records=tuple(records))


@pytest.mark.asyncio
async def test_result_rejects_final_graph_outside_native_record_lineage() -> None:
    success, _transport, _tool = await _run_operational_case("terminal")

    with pytest.raises(ValueError, match="final_graph"):
        replace(success, final_graph=success.scaffold.graph)


@pytest.mark.parametrize(
    "mutation",
    ["terminal_not_ready", "repair_receipt_absent", "reverify_not_verified"],
)
@pytest.mark.asyncio
async def test_result_rejects_incomplete_terminal_native_evidence(
    mutation: str,
) -> None:
    success, _transport, _tool = await _run_operational_case("terminal")
    if mutation == "terminal_not_ready":
        success.final_graph.nodes["done"].status = "pending"
    elif mutation == "repair_receipt_absent":
        success.final_graph.nodes["repair_same_component"].evidence = None
    else:
        evidence = success.final_graph.nodes["verify_repair"].evidence
        assert evidence is not None
        evidence.verified = False

    with pytest.raises(ValueError, match="terminal final_graph"):
        replace(success)


@pytest.mark.asyncio
async def test_contract_compilation_failure_remains_an_internal_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_compilation(contract: object):
        raise ValueError("synthetic compiler contract failure")

    monkeypatch.setattr(handoff, "compile_workflow_contract", fail_compilation)
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(ValueError, match="synthetic compiler contract failure"):
        await run_minimal_csharp_repair_handoff(
            _valid_draft(),
            worker_transport=transport,
            tool_executor=tool_executor,
        )

    assert transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.asyncio
async def test_terminal_result_preserves_native_ready_not_complete_state() -> None:
    result, _transport, _tool = await _run_operational_case("terminal")

    assert result.step_records[-1].verifier_node_id == "verify_repair"
    assert result.step_records[-1].verifier_outcome_status == "succeeded"
    assert result.supply_records[-1].decision == "HALT"
    assert result.supply_records[-1].reason == "terminal_node_selected:done"
    assert result.final_graph.nodes["done"].status == "ready"
    assert graph_status(result.final_graph) != "complete"
    assert not hasattr(result, "receipt")
    assert not hasattr(result, "diagnostic")
    assert not hasattr(result, "component_guid")
    assert not hasattr(result, "classification")


def test_private_builder_revalidates_mutated_exact_class_draft() -> None:
    draft = _valid_draft()
    object.__setattr__(draft, "capability", "forged_capability")

    with pytest.raises(ValueError, match="capability"):
        handoff._build_repair_specimen_contract(draft)


@pytest.mark.parametrize(
    ("case", "error_type"),
    [
        ("not_mapping", TypeError),
        ("missing_goal", ValueError),
        ("missing_capability", ValueError),
        ("missing_interface", ValueError),
        ("missing_acceptance", ValueError),
        ("goal_empty", ValueError),
        ("goal_not_string", TypeError),
        ("wrong_capability", ValueError),
        ("interface_not_mapping", TypeError),
        ("interface_extra", ValueError),
        ("inputs_nonempty", ValueError),
        ("inputs_wrong_type", ValueError),
        ("outputs_empty", ValueError),
        ("outputs_wrong_type", ValueError),
        ("outputs_duplicate", ValueError),
        ("output_not_mapping", TypeError),
        ("output_missing_name", ValueError),
        ("output_missing_type", ValueError),
        ("output_extra", ValueError),
        ("output_wrong_name", ValueError),
        ("output_wrong_type", ValueError),
        ("wrong_acceptance", ValueError),
        ("code", ValueError),
        ("action_id", ValueError),
        ("template", ValueError),
        ("graph", ValueError),
        ("worker", ValueError),
    ],
)
def test_strict_loader_rejects_unowned_planner_payloads(
    case: str,
    error_type: type[Exception],
) -> None:
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(error_type):
        load_minimal_csharp_repair_draft(_invalid_draft_payload(case))

    assert transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.parametrize(
    "field",
    ["output name", "output type", "capability", "acceptance"],
)
def test_strict_loader_rejects_equality_spoofed_scalars(field: str) -> None:
    with pytest.raises(
        TypeError,
        match=rf"Planner draft {field} must be an exact string",
    ):
        load_minimal_csharp_repair_draft(_payload_with_equality_spoof(field))


def test_loader_snapshots_payload_before_caller_mutation() -> None:
    payload = _FakePlanner().draft()
    draft = load_minimal_csharp_repair_draft(payload)

    payload["goal"] = "mutated"
    payload["interface"]["outputs"][0]["name"] = "B"

    assert draft.goal == (
        "Create a C# component with one double output and compile cleanly."
    )
    assert draft.interface.outputs[0].name == "A"


@pytest.mark.asyncio
async def test_compositor_refuses_raw_mapping_before_capability_calls() -> None:
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(TypeError, match="exact ValidatedPlannerDraft"):
        await run_minimal_csharp_repair_handoff(
            _FakePlanner().draft(),  # type: ignore[arg-type]
            worker_transport=transport,
            tool_executor=tool_executor,
        )

    assert transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.asyncio
async def test_compositor_revalidates_nested_frozen_draft_before_calls() -> None:
    draft = _valid_draft()
    object.__setattr__(draft.interface.outputs[0], "name", "B")
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(ValueError, match="output name"):
        await run_minimal_csharp_repair_handoff(
            draft,
            worker_transport=transport,
            tool_executor=tool_executor,
        )

    assert transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.parametrize(
    "field",
    ["output name", "output type", "capability", "acceptance"],
)
@pytest.mark.asyncio
async def test_compositor_rejects_equality_spoofed_scalars_before_calls(
    field: str,
) -> None:
    draft = _valid_draft()
    _mutate_draft_with_equality_spoof(draft, field)
    transport = _RecordingWorkerTransport(_TARGET_DIAGNOSTIC)
    tool_executor = _RecordingToolExecutor()

    with pytest.raises(
        TypeError,
        match=rf"Planner draft {field} must be an exact string",
    ):
        await run_minimal_csharp_repair_handoff(
            draft,
            worker_transport=transport,
            tool_executor=tool_executor,
        )

    assert transport.calls == []
    assert tool_executor.calls == []


def test_validated_draft_subclass_is_not_an_admitted_carrier() -> None:
    class DraftSubclass(ValidatedPlannerDraft):
        pass

    valid = _valid_draft()
    with pytest.raises(TypeError, match="exact ValidatedPlannerDraft"):
        DraftSubclass(
            goal=valid.goal,
            capability=valid.capability,
            interface=valid.interface,
            acceptance=valid.acceptance,
        )


def test_private_builder_is_goal_independent_and_compiler_owned() -> None:
    first = _valid_draft()
    second_payload = _FakePlanner().draft()
    second_payload["goal"] = "Use a completely different valid goal wording."
    second = load_minimal_csharp_repair_draft(second_payload)

    first_contract = handoff._build_repair_specimen_contract(first)
    second_contract = handoff._build_repair_specimen_contract(second)
    assert (
        snapshot_workflow_contract(first_contract).normalized_contract
        == snapshot_workflow_contract(second_contract).normalized_contract
    )

    scaffold = compile_workflow_contract(first_contract)
    assert scaffold.compile_record.selected_template_id == (
        "gh_csharp_create_verify_repair_verify"
    )
    create_params = scaffold.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    assert create_params == {
        "code": _INITIAL_BODY,
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "RookMinimalRepairHandoff",
        "x": 375,
        "y": 1080,
    }
    repair_rule = next(
        rule
        for rule in first_contract.rules
        if rule.node_id == "repair_same_component"
    )
    assert repair_rule.steps_by_seen_count == (
        ProducerStepSpec("repair_same_component"),
    )
    assert not any(
        isinstance(step, BindStepSpec)
        for step in repair_rule.steps_by_seen_count
    )
    assert (
        EXECUTION_PARAMS_KEY
        not in scaffold.graph.nodes["repair_same_component"].metadata
    )
