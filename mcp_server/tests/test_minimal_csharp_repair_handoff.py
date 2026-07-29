from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

import pytest

import rook.agent.minimal_csharp_repair_handoff as handoff
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
