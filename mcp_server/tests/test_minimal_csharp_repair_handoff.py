from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

import pytest

from rook.agent.minimal_csharp_repair_handoff import (
    MinimalCSharpRepairHandoffResult,
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
    run_minimal_csharp_repair_handoff,
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
