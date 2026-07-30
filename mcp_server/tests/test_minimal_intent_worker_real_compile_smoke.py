from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
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


class _EqualitySpoof:
    def __eq__(self, _other: object) -> bool:
        return True


class _DictSubclass(dict):
    pass


class _SequenceDispatcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(params)))
        response = self._responses[len(self.calls) - 1]
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


def _models(
    planner: object = "anthropic/claude-opus-4-6",
    worker: object = "ollama_chat/qwen3-coder:30b-a3b-q8_0",
) -> SimpleNamespace:
    return SimpleNamespace(planner=planner, worker=worker, api_base=None)


def _native_row(
    *,
    process_id: object = 4001,
    port: object = 9877,
) -> dict[str, object]:
    return {
        "pluginType": "native",
        "processId": process_id,
        "port": port,
    }


def _fail_if_reached(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("unexpected downstream capability construction")


def _invoke_main(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> tuple[int, dict[str, Any]]:
    exit_code = SMOKE.main(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert type(parsed) is dict
    return exit_code, parsed


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "live_execution_not_requested"),
        (["--execute-live"], "execute_live"),
        (["--unknown"], "invalid_arguments"),
        (["--execute-live", "extra"], "invalid_arguments"),
        (["--execute-live", "--execute-live"], "invalid_arguments"),
        ([_EqualitySpoof()], "invalid_arguments"),
    ],
)
def test_argument_classifier_is_closed(argv: list[str], expected: str) -> None:
    assert SMOKE._classify_arguments(argv) == expected


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_reason"),
    [
        ([], 0, "live_execution_not_requested"),
        (["--unknown"], 1, "invalid_arguments"),
        (["--execute-live", "extra"], 1, "invalid_arguments"),
    ],
)
def test_argument_refusal_precedes_every_capability(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    expected_code: int,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, argv)

    assert exit_code == expected_code
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == expected_reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0


@pytest.mark.parametrize(
    ("planner", "worker", "reason"),
    [
        (object(), "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_identity_invalid"),
        ("anthropic/claude-opus-4-6", object(), "profile_identity_invalid"),
        ("anthropic/claude-sonnet", "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_role_mismatch"),
        ("anthropic/claude-opus-4-6", "ollama_chat/other", "profile_role_mismatch"),
    ],
)
def test_profile_refusal_precedes_discovery_and_transport_construction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    planner: object,
    worker: object,
    reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models(planner, worker))
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0


def test_profile_load_exception_is_safe_and_precedes_discovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_profile(_profile: str) -> None:
        raise RuntimeError("PROFILE_LOAD_SENTINEL")

    monkeypatch.setattr(SMOKE, "get_models", raise_profile)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "operator_internal_error"
    assert "PROFILE_LOAD_SENTINEL" not in json.dumps(summary)
    assert summary["document_preparation_status"] == "not_started"
    assert summary["planner_calls"] is None
    assert summary["worker_calls"] is None


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([], "rooknative_instance_absent"),
        ([{"pluginType": "roadcreator", "processId": 1, "port": 2}], "rooknative_instance_absent"),
        ([_native_row(), _native_row(process_id=4002, port=9878)], "rooknative_instance_ambiguous"),
        (
            [{"pluginType": "native", "port": 9877}],
            "rooknative_identity_invalid",
        ),
        ([_native_row(process_id=True)], "rooknative_identity_invalid"),
        ([_native_row(process_id=0)], "rooknative_identity_invalid"),
        ([_native_row(process_id=-1)], "rooknative_identity_invalid"),
        ([_native_row(process_id="4001")], "rooknative_identity_invalid"),
        ([_native_row(process_id=_EqualitySpoof())], "rooknative_identity_invalid"),
        (
            [{"pluginType": "native", "processId": 4001}],
            "rooknative_identity_invalid",
        ),
        ([_native_row(port=True)], "rooknative_identity_invalid"),
        ([_native_row(port=0)], "rooknative_identity_invalid"),
        ([_native_row(port=-1)], "rooknative_identity_invalid"),
        ([_native_row(port="9877")], "rooknative_identity_invalid"),
        ([_native_row(port=_EqualitySpoof())], "rooknative_identity_invalid"),
    ],
)
def test_discovery_refusal_precedes_dispatcher_and_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: list[dict[str, object]],
    reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: copy.deepcopy(rows))
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0


def test_discovery_freezes_the_only_exact_native_identity() -> None:
    assert SMOKE._resolve_single_rhino_target(
        [
            {"pluginType": "roadcreator", "processId": 99, "port": 9999},
            _native_row(),
        ]
    ) == SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877)


def test_equality_spoof_plugin_type_does_not_become_native() -> None:
    with pytest.raises(SMOKE._TargetRefusal) as caught:
        SMOKE._resolve_single_rhino_target(
            [{"pluginType": _EqualitySpoof(), "processId": 4001, "port": 9877}]
        )
    assert caught.value.reason == "rooknative_instance_absent"


_STATUS_MUTATIONS = (
    "result_subclass",
    "result_not_dict",
    "success_missing",
    "success_false",
    "success_spoof",
    "data_missing",
    "data_subclass",
    "data_not_dict",
    "available_missing",
    "available_false",
    "available_spoof",
    "ready_missing",
    "ready_false",
    "ready_spoof",
    "active_missing",
    "active_false",
    "active_spoof",
    "document_id_missing",
    "document_id_empty",
    "document_id_spaces",
    "document_id_whitespace",
    "document_id_not_string",
    "document_id_spoof",
    "object_count_missing",
    "object_count_false",
    "object_count_true",
    "object_count_negative",
    "object_count_positive",
    "object_count_float",
    "object_count_string",
    "object_count_spoof",
    "document_path_missing",
    "document_path_not_string",
    "document_path_saved",
    "document_path_spoof",
)


def _mutated_status(case: str, document_id: str) -> object:
    row = _status(document_id)
    if case == "result_subclass":
        return _DictSubclass(row)
    if case == "result_not_dict":
        return []
    if case == "success_missing":
        row.pop("success")
    elif case == "success_false":
        row["success"] = False
    elif case == "success_spoof":
        row["success"] = _EqualitySpoof()
    elif case == "data_missing":
        row.pop("data")
    elif case == "data_subclass":
        row["data"] = _DictSubclass(row["data"])
    elif case == "data_not_dict":
        row["data"] = []
    else:
        data = row["data"]
        assert type(data) is dict
        mutations: dict[str, tuple[str, object]] = {
            "available_missing": ("available", None),
            "available_false": ("available", False),
            "available_spoof": ("available", _EqualitySpoof()),
            "ready_missing": ("ready_for_edit", None),
            "ready_false": ("ready_for_edit", False),
            "ready_spoof": ("ready_for_edit", _EqualitySpoof()),
            "active_missing": ("has_active_document", None),
            "active_false": ("has_active_document", False),
            "active_spoof": ("has_active_document", _EqualitySpoof()),
            "document_id_missing": ("document_id", None),
            "document_id_empty": ("document_id", ""),
            "document_id_spaces": ("document_id", "   "),
            "document_id_whitespace": ("document_id", "\t\r\n"),
            "document_id_not_string": ("document_id", 7),
            "document_id_spoof": ("document_id", _EqualitySpoof()),
            "object_count_missing": ("object_count", None),
            "object_count_false": ("object_count", False),
            "object_count_true": ("object_count", True),
            "object_count_negative": ("object_count", -1),
            "object_count_positive": ("object_count", 1),
            "object_count_float": ("object_count", 0.0),
            "object_count_string": ("object_count", "0"),
            "object_count_spoof": ("object_count", _EqualitySpoof()),
            "document_path_missing": ("document_path", None),
            "document_path_not_string": ("document_path", 7),
            "document_path_saved": ("document_path", "C:/saved.gh"),
            "document_path_spoof": ("document_path", _EqualitySpoof()),
        }
        key, value = mutations[case]
        if case.endswith("_missing"):
            data.pop(key)
        else:
            data[key] = value
    return row


def _patch_dispatcher_prefix(
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: _SequenceDispatcher,
) -> list[dict[str, Any]]:
    model_constructions: list[dict[str, Any]] = []

    def make_model(**kwargs: Any) -> None:
        model_constructions.append(copy.deepcopy(kwargs))
        raise AssertionError("model construction reached")

    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", make_model)
    return model_constructions


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["pre", "post"])
@pytest.mark.parametrize("case", _STATUS_MUTATIONS)
async def test_status_equations_refuse_before_model_construction(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    case: str,
) -> None:
    responses = (
        [_mutated_status(case, _PRE_DOCUMENT_ID)]
        if phase == "pre"
        else [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"Created": True}},
            _mutated_status(case, _POST_DOCUMENT_ID),
        ]
    )
    dispatcher = _SequenceDispatcher(responses)
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        )

    expected_calls = 1 if phase == "pre" else 3
    expected_state = "status_rejected" if phase == "pre" else "document_new_started"
    assert caught.value.state == expected_state
    assert caught.value.tool_calls == expected_calls
    assert len(dispatcher.calls) == expected_calls
    assert model_constructions == []


@pytest.mark.asyncio
async def test_post_status_requires_a_different_document_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _SequenceDispatcher(
        [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"Created": True}},
            _status(_PRE_DOCUMENT_ID),
        ]
    )
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        )

    assert caught.value.reason == "post_status_rejected"
    assert caught.value.state == "document_new_started"
    assert caught.value.tool_calls == 3
    assert model_constructions == []


_DOCUMENT_NEW_MUTATIONS = (
    "result_subclass",
    "result_not_dict",
    "success_missing",
    "success_false",
    "success_spoof",
    "data_missing",
    "data_subclass",
    "data_not_dict",
    "created_missing",
    "created_false",
    "created_spoof",
)


def _mutated_document_new(case: str) -> object:
    row: dict[str, Any] = {"success": True, "data": {"Created": True}}
    if case == "result_subclass":
        return _DictSubclass(row)
    if case == "result_not_dict":
        return []
    if case == "success_missing":
        row.pop("success")
    elif case == "success_false":
        row["success"] = False
    elif case == "success_spoof":
        row["success"] = _EqualitySpoof()
    elif case == "data_missing":
        row.pop("data")
    elif case == "data_subclass":
        row["data"] = _DictSubclass(row["data"])
    elif case == "data_not_dict":
        row["data"] = []
    else:
        data = row["data"]
        assert type(data) is dict
        if case == "created_missing":
            data.pop("Created")
        elif case == "created_false":
            data["Created"] = False
        elif case == "created_spoof":
            data["Created"] = _EqualitySpoof()
        else:
            raise AssertionError(f"unknown document-new mutation: {case}")
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _DOCUMENT_NEW_MUTATIONS)
async def test_document_new_equations_preserve_mutation_truth(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    dispatcher = _SequenceDispatcher(
        [_status(_PRE_DOCUMENT_ID), _mutated_document_new(case)]
    )
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        )

    assert caught.value.reason == "document_new_rejected"
    assert caught.value.state == "document_new_started"
    assert caught.value.tool_calls == 2
    assert len(dispatcher.calls) == 2
    assert model_constructions == []


def _patch_main_preparation(
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: _SequenceDispatcher,
) -> list[dict[str, Any]]:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    return _patch_dispatcher_prefix(monkeypatch, dispatcher)


@pytest.mark.parametrize("exception_type", [RuntimeError, TimeoutError])
@pytest.mark.parametrize(
    ("locus", "expected_reason", "expected_state", "expected_calls"),
    [
        ("pre", "pre_status_exception", "status_rejected", 1),
        (
            "document_new",
            "document_new_exception",
            "document_new_started",
            2,
        ),
        ("post", "post_status_exception", "document_new_started", 3),
    ],
)
def test_preparation_exceptions_are_bounded_and_construct_no_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception_type: type[Exception],
    locus: str,
    expected_reason: str,
    expected_state: str,
    expected_calls: int,
) -> None:
    failure = exception_type("PREPARATION_SENTINEL")
    responses_by_locus = {
        "pre": [failure],
        "document_new": [_status(_PRE_DOCUMENT_ID), failure],
        "post": [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"Created": True}},
            failure,
        ],
    }
    dispatcher = _SequenceDispatcher(responses_by_locus[locus])
    model_constructions = _patch_main_preparation(monkeypatch, dispatcher)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "preparation_failed"
    assert summary["operator_reason"] == expected_reason
    assert summary["document_preparation_status"] == expected_state
    assert summary["preparation_tool_calls"] == expected_calls
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert "PREPARATION_SENTINEL" not in json.dumps(summary)
    assert len(dispatcher.calls) == expected_calls
    assert model_constructions == []


@pytest.mark.parametrize(
    "locus",
    ["first_transport", "second_transport", "planner_adapter", "integration"],
)
def test_post_preparation_exception_retains_verified_document_state(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    locus: str,
) -> None:
    dispatcher = _SequenceDispatcher(
        [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"Created": True}},
            _status(_POST_DOCUMENT_ID),
        ]
    )
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    transports = [_RawTransport(_planner_payload()), _RawTransport(_worker_payload())]
    constructor_calls: list[dict[str, Any]] = []

    def make_transport(**kwargs: Any) -> _RawTransport:
        constructor_calls.append(copy.deepcopy(kwargs))
        index = len(constructor_calls)
        if locus == "first_transport" and index == 1:
            raise RuntimeError("POST_PREPARATION_SENTINEL")
        if locus == "second_transport" and index == 2:
            raise RuntimeError("POST_PREPARATION_SENTINEL")
        return transports[index - 1]

    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", make_transport)
    if locus == "planner_adapter":
        monkeypatch.setattr(
            SMOKE,
            "MinimalPlannerDraftAdapter",
            lambda _transport: (_ for _ in ()).throw(
                RuntimeError("POST_PREPARATION_SENTINEL")
            ),
        )
    if locus == "integration":
        async def raise_integration(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("POST_PREPARATION_SENTINEL")

        monkeypatch.setattr(
            SMOKE,
            "run_minimal_intent_worker_integration",
            raise_integration,
        )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "operator_internal_error"
    assert summary["rooknative_process_id"] == 4001
    assert summary["rooknative_port"] == 9877
    assert summary["document_preparation_status"] == "fresh_document_verified"
    assert summary["preparation_tool_calls"] == 3
    assert summary["planner_calls"] is None
    assert summary["worker_calls"] is None
    assert summary["execution_tool_calls"] is None
    assert summary["terminal_stage"] is None
    assert summary["terminal_reason"] is None
    assert summary["planner_adapter_status"] is None
    assert summary["worker_adapter_status"] is None
    assert "POST_PREPARATION_SENTINEL" not in json.dumps(summary)
    assert len(dispatcher.calls) == 3
