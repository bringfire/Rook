from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "minimal_intent_worker_real_compile_smoke.py"
_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_PRE_DOCUMENT_ID = "pre-document"
_POST_DOCUMENT_ID = "post-document"
_COMPONENT_GUID = "real-compile-smoke-test-component"
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKER_BODY = "A = 42.0;"
_TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist "
    "in the current context."
)


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "minimal_intent_worker_real_compile_smoke",
        _SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke()


def _planner_payload() -> dict[str, Any]:
    return {
        "goal": _INTENT,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


def _worker_payload(body: str = _WORKER_BODY) -> dict[str, Any]:
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Provide one bounded replacement body.",
        "input": {"code": body, "mode": "body"},
    }


class _RawTransport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self._raw


class _ScriptedDispatcher:
    def __init__(self, *, port: int, local_tools: dict[str, Any]) -> None:
        self.port = port
        self.local_tools = local_tools
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((name, captured))
        index = len(self.calls)
        if index == 1 and name == "gh_status" and captured == {}:
            return _status(_PRE_DOCUMENT_ID)
        if index == 2 and name == "gh_document_new" and captured == {}:
            return {"success": True, "data": {"Created": True}}
        if index == 3 and name == "gh_status" and captured == {}:
            return _status(_POST_DOCUMENT_ID)
        if index == 4 and name == "gh_create_csharp_script":
            assert captured == {
                "code": _INITIAL_BODY,
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalRepairHandoff",
                "x": 375,
                "y": 1080,
            }
            return _created_with_errors(captured["code"])
        if index == 5 and name == "gh_update_script":
            assert captured == {
                "guid": _COMPONENT_GUID,
                "code": _WORKER_BODY,
                "mode": "body",
                "language": "csharp",
            }
            return _updated_clean(captured["guid"])
        raise AssertionError(f"unexpected scripted dispatch {index}: {name}")


def _status(document_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "available": True,
            "ready_for_edit": True,
            "has_active_document": True,
            "document_id": document_id,
            "object_count": 0,
            "document_path": "",
        },
    }


def _created_with_errors(received_body: object) -> dict[str, Any]:
    assert received_body == _INITIAL_BODY
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
                    "target_errors": [_TARGET_DIAGNOSTIC],
                },
            }
        },
    }


def _updated_clean(received_guid: object) -> dict[str, Any]:
    assert received_guid == _COMPONENT_GUID
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


@pytest.mark.asyncio
async def test_no_contact_walking_vertical_reaches_native_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_dispatchers: list[_ScriptedDispatcher] = []

    def make_dispatcher(*, port: int, local_tools: dict[str, Any]):
        dispatcher = _ScriptedDispatcher(port=port, local_tools=local_tools)
        created_dispatchers.append(dispatcher)
        return dispatcher

    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    transports = iter((planner_transport, worker_transport))
    monkeypatch.setattr(SMOKE, "ToolDispatcher", make_dispatcher)
    monkeypatch.setattr(
        SMOKE,
        "build_local_tools",
        lambda: {
            "gh_create_csharp_script": object(),
            "gh_update_script": object(),
        },
    )
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )

    roles = SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base=None,
    )
    live_run = await SMOKE._run_live_once(
        roles,
        SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
    )

    assert live_run.result.terminal_stage == "terminal"
    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert live_run.preparation.state == "fresh_document_verified"
    assert live_run.preparation.tool_calls == 3
    assert live_run.executor.call_names == (
        "gh_create_csharp_script",
        "gh_update_script",
    )
    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert len(created_dispatchers) == 1
    assert created_dispatchers[0].port == 9877
    assert created_dispatchers[0].calls == [
        ("gh_status", {}),
        ("gh_document_new", {}),
        ("gh_status", {}),
        (
            "gh_create_csharp_script",
            {
                "code": _INITIAL_BODY,
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalRepairHandoff",
                "x": 375,
                "y": 1080,
            },
        ),
        (
            "gh_update_script",
            {
                "guid": _COMPONENT_GUID,
                "code": _WORKER_BODY,
                "mode": "body",
                "language": "csharp",
            },
        ),
    ]
    assert SMOKE._summary_from_result(roles, live_run) == {
        "operator_status": "completed",
        "operator_reason": "native_terminal",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "rooknative_process_id": 4001,
        "rooknative_port": 9877,
        "document_preparation_status": "fresh_document_verified",
        "preparation_tool_calls": 3,
        "planner_calls": 1,
        "worker_calls": 1,
        "execution_tool_calls": 2,
        "terminal_stage": "terminal",
        "terminal_reason": "terminal_node_selected:done",
        "planner_adapter_status": "decoded",
        "worker_adapter_status": "response_loaded",
    }
