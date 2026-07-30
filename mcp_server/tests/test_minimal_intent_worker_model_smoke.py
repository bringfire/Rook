from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rook.agent.local_worker_model_transport as transport_module
from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport as RealLiteLLMWorkerTransport,
    _local_worker_response_union_schema,
)
from rook.agent.model_profiles import ModelSet


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "minimal_intent_worker_model_smoke.py"
_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_COMPONENT_GUID = "minimal-intent-model-smoke-component-guid"
_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the "
    "current context."
)
_PLANNER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["goal", "capability", "interface", "acceptance"],
    "properties": {
        "goal": {"type": "string"},
        "capability": {"const": "grasshopper_csharp_component"},
        "interface": {
            "type": "object",
            "additionalProperties": False,
            "required": ["inputs", "outputs"],
            "properties": {
                "inputs": {"type": "array", "maxItems": 0},
                "outputs": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "type"],
                        "properties": {
                            "name": {"const": "A"},
                            "type": {"const": "double"},
                        },
                    },
                },
            },
        },
        "acceptance": {"const": "clean_compile_receipt"},
    },
}
_PLANNER_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "minimal_planner_draft",
        "strict": True,
        "schema": _PLANNER_SCHEMA,
    },
}


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "minimal_intent_worker_model_smoke",
        _SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke()


class _RawTransport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self._raw


class _EqualitySpoof:
    def __init__(self, rendered: str) -> None:
        self.rendered = rendered

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    def __str__(self) -> str:
        return self.rendered


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


def _worker_payload(
    *,
    body: str = "A = 42.0;",
    rationale: str = "Provide one bounded replacement body.",
) -> dict[str, Any]:
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": rationale,
        "input": {"code": body, "mode": "body"},
    }


def _create_params() -> dict[str, Any]:
    return {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "RookMinimalRepairHandoff",
        "x": 375,
        "y": 1080,
    }


def _update_params(body: object = "A = 42.0;") -> dict[str, Any]:
    return {
        "guid": _COMPONENT_GUID,
        "code": body,
        "mode": "body",
        "language": "csharp",
    }


def _created_executor() -> tuple[object, dict[str, Any]]:
    executor = SMOKE._CausalFakeToolExecutor()
    receipt = executor("gh_create_csharp_script", _create_params())
    return executor, receipt


def _roles():
    return SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base="http://localhost:11434/v1",
    )


async def _run_with_payloads(monkeypatch, planner_payload, worker_payload):
    planner_transport = _RawTransport(planner_payload)
    worker_transport = _RawTransport(worker_payload)
    transports = [planner_transport, worker_transport]

    def build_transport(**kwargs):
        return transports.pop(0)

    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", build_transport)
    live_run = await SMOKE._run_live_once(_roles())
    return live_run, planner_transport, worker_transport


@pytest.mark.asyncio
async def test_internal_composition_reaches_native_terminal_with_exact_configs(
    monkeypatch,
) -> None:
    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    transports = [planner_transport, worker_transport]
    constructor_calls: list[dict[str, Any]] = []

    def build_transport(**kwargs):
        constructor_calls.append(copy.deepcopy(kwargs))
        return transports[len(constructor_calls) - 1]

    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", build_transport)
    roles = SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base="http://localhost:11434/v1",
    )

    live_run = await SMOKE._run_live_once(roles)

    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert live_run.result.terminal_stage == "terminal"
    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert live_run.executor.tool_call_count == 2
    assert live_run.executor.contract_failed is False
    assert _DIAGNOSTIC in json.dumps(worker_transport.calls[0])
    assert constructor_calls == [
        {
            "model": "anthropic/claude-opus-4-6",
            "profile_api_base": "http://localhost:11434/v1",
            "generation_params": {
                "temperature": 0,
                "max_tokens": 1024,
                "max_retries": 0,
                "response_format": _PLANNER_RESPONSE_FORMAT,
            },
            "structured_response_schema": None,
            "timeout_s": 120.0,
        },
        {
            "model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
            "profile_api_base": "http://localhost:11434/v1",
            "generation_params": {
                "temperature": 0,
                "max_tokens": 1024,
                "max_retries": 0,
            },
            "structured_response_schema": _local_worker_response_union_schema(),
            "timeout_s": 120.0,
        },
    ]
    assert SMOKE._summary_from_result(roles, live_run) == {
        "operator_status": "completed",
        "operator_reason": "native_terminal",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "planner_calls": 1,
        "worker_calls": 1,
        "tool_calls": 2,
        "terminal_stage": "terminal",
        "terminal_reason": "terminal_node_selected:done",
        "planner_adapter_status": "decoded",
        "worker_adapter_status": "response_loaded",
    }


def test_real_transport_materializes_provider_specific_schema_kwargs(
    monkeypatch,
) -> None:
    assert (
        transport_module.litellm.supports_response_schema(
            model="anthropic/claude-opus-4-6"
        )
        is True
    )
    supported_planner_params = transport_module.litellm.get_supported_openai_params(
        model="anthropic/claude-opus-4-6"
    )
    assert supported_planner_params is not None
    assert "response_format" in supported_planner_params

    calls: list[dict[str, Any]] = []

    def completion(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=None,
        )

    monkeypatch.setattr(transport_module.litellm, "completion", completion)
    monkeypatch.setattr(
        transport_module.litellm,
        "completion_cost",
        lambda completion_response: None,
    )
    prompt = {"messages": [{"role": "user", "content": "fixed"}]}
    planner = RealLiteLLMWorkerTransport(
        model="anthropic/claude-opus-4-6",
        profile_api_base="http://localhost:11434/v1",
        generation_params={
            "temperature": 0,
            "max_tokens": 1024,
            "max_retries": 0,
            "response_format": copy.deepcopy(_PLANNER_RESPONSE_FORMAT),
        },
        structured_response_schema=None,
        timeout_s=120.0,
    )
    worker = RealLiteLLMWorkerTransport(
        model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base="http://localhost:11434/v1",
        generation_params={
            "temperature": 0,
            "max_tokens": 1024,
            "max_retries": 0,
        },
        structured_response_schema=_local_worker_response_union_schema(),
        timeout_s=120.0,
    )

    assert planner.send(prompt) == "{}"
    assert worker.send(prompt) == "{}"

    planner_call, worker_call = calls
    assert planner_call["response_format"] == _PLANNER_RESPONSE_FORMAT
    assert planner_call["max_tokens"] == 1024
    assert planner_call["max_retries"] == 0
    assert planner_call["temperature"] == 0
    assert "format" not in planner_call
    assert worker_call["format"] == _local_worker_response_union_schema()
    assert worker_call["max_tokens"] == 1024
    assert worker_call["max_retries"] == 0
    assert worker_call["temperature"] == 0
    assert "response_format" not in worker_call


def test_argument_classifier_and_role_resolver_are_closed(monkeypatch) -> None:
    assert SMOKE._classify_arguments([]) == "live_execution_not_requested"
    assert SMOKE._classify_arguments(["--execute-live"]) == "execute_live"
    assert SMOKE._classify_arguments(["--unknown"]) == "invalid_arguments"

    monkeypatch.setattr(
        SMOKE,
        "get_models",
        lambda profile: ModelSet(
            planner="anthropic/claude-opus-4-6",
            worker="ollama_chat/qwen3-coder:30b-a3b-q8_0",
            specialist="unused",
            guardian="unused",
            dspy="unused",
            api_base="http://localhost:11434/v1",
        ),
    )
    roles = SMOKE._resolve_hybrid_roles()
    assert roles == SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base="http://localhost:11434/v1",
    )

    monkeypatch.setattr(
        SMOKE,
        "get_models",
        lambda profile: ModelSet(
            planner="anthropic/claude-opus-4-6",
            worker="anthropic/claude-sonnet-5",
            specialist="unused",
            guardian="unused",
            dspy="unused",
        ),
    )
    with pytest.raises(SMOKE._ProfileRefusal, match="profile_role_mismatch"):
        SMOKE._resolve_hybrid_roles()


def test_synthetic_tool_derives_diagnostic_and_rejects_unsafe_update() -> None:
    assert SMOKE._diagnostic_for_initial_body("A = AnotherMissingSymbol;") == (
        "CS0103: The name 'AnotherMissingSymbol' does not exist in the "
        "current context."
    )
    executor = SMOKE._CausalFakeToolExecutor()
    created = executor(
        "gh_create_csharp_script",
        {
            "code": "A = DefinitelyMissingSymbol;",
            "pins_in": (),
            "pins_out": ("A:double",),
            "name": "RookMinimalRepairHandoff",
            "x": 375,
            "y": 1080,
        },
    )
    assert created["data"]["script_receipt"]["repair_anchor"] == {
        "component_guid": _COMPONENT_GUID,
        "language": "csharp",
        "target_errors": [_DIAGNOSTIC],
    }

    with pytest.raises(
        SMOKE._SyntheticToolContractError,
        match="synthetic tool contract rejected",
    ):
        executor(
            "gh_update_script",
            {
                "guid": _COMPONENT_GUID,
                "code": "A = 1m;",
                "mode": "body",
                "language": "csharp",
            },
        )
    assert executor.contract_failed is True
    assert executor.tool_call_count == 2
    assert "A = 1m;" not in repr(vars(executor))


@pytest.mark.parametrize(
    "body",
    (
        "A = 0;",
        "A=-1;",
        "A = 999999999;",
        "A = 0.5;",
        "A = -123456789.1234567890123456D;",
        (" " * 124) + "A=0;",
    ),
)
def test_synthetic_update_accepts_only_bounded_numeric_body_grammar(body) -> None:
    executor, _receipt = _created_executor()

    updated = executor("gh_update_script", _update_params(body))

    assert updated["script_receipt"]["artifact_status"] == "usable"
    assert updated["script_receipt"]["verification"] == {
        "status": "passed",
        "target_error_count": 0,
    }
    assert executor.contract_failed is False
    assert executor.tool_call_count == 2


@pytest.mark.parametrize(
    "body",
    (
        object(),
        "A = 1m;",
        "A = 1f;",
        "A = 1000000000;",
        "A = 1e3;",
        "A = 1 + 2;",
        "A = Math.Sin(1);",
        "A = 1; B = 2;",
        "A = 1;\n",
        "A = ١;",
        (" " * 125) + "A=0;",
    ),
)
def test_synthetic_update_refuses_every_body_outside_closed_grammar(body) -> None:
    executor, _receipt = _created_executor()

    with pytest.raises(
        SMOKE._SyntheticToolContractError,
        match="synthetic tool contract rejected",
    ):
        executor("gh_update_script", _update_params(body))

    assert executor.contract_failed is True
    assert executor.tool_call_count == 2
    assert all(value is not body for value in vars(executor).values())
    if type(body) is str:
        assert body not in repr(vars(executor))


def test_synthetic_create_derives_diagnostic_and_issues_update_identity() -> None:
    assert SMOKE._INITIAL_BODY_PATTERN.fullmatch(SMOKE._INITIAL_BODY).group(
        "identifier"
    ) == "DefinitelyMissingSymbol"
    assert SMOKE._diagnostic_for_initial_body("A = MissingOne;") == (
        "CS0103: The name 'MissingOne' does not exist in the current context."
    )
    assert SMOKE._diagnostic_for_initial_body("A = MissingTwo;") == (
        "CS0103: The name 'MissingTwo' does not exist in the current context."
    )

    executor, created = _created_executor()

    assert created["data"]["script_receipt"]["repair_anchor"] == {
        "component_guid": _COMPONENT_GUID,
        "language": "csharp",
        "target_errors": [_DIAGNOSTIC],
    }
    updated = executor("gh_update_script", _update_params())
    assert updated["script_receipt"]["mutation"]["component_guid"] == (
        _COMPONENT_GUID
    )


@pytest.mark.parametrize(
    ("tool_name", "mutation"),
    (
        ("wrong_create", {}),
        (_EqualitySpoof("wrong_create"), {}),
        ("gh_create_csharp_script", {"extra": True}),
        ("gh_create_csharp_script", {"code": "A = OtherMissing;"}),
        ("gh_create_csharp_script", {"pins_in": ("X:double",)}),
        ("gh_create_csharp_script", {"pins_out": ("B:double",)}),
        (
            "gh_create_csharp_script",
            {"pins_out": (_EqualitySpoof("B:double"),)},
        ),
        ("gh_create_csharp_script", {"name": "OtherName"}),
        ("gh_create_csharp_script", {"name": _EqualitySpoof("OtherName")}),
        ("gh_create_csharp_script", {"x": 376}),
        ("gh_create_csharp_script", {"y": 1081}),
    ),
)
def test_synthetic_create_refuses_wrong_tool_or_parameter(
    tool_name,
    mutation,
) -> None:
    executor = SMOKE._CausalFakeToolExecutor()
    params = _create_params()
    params.update(mutation)

    with pytest.raises(SMOKE._SyntheticToolContractError):
        executor(tool_name, params)

    assert executor.contract_failed is True
    assert executor.tool_call_count == 1
    assert _COMPONENT_GUID not in repr(vars(executor))
    assert "DefinitelyMissingSymbol" not in repr(vars(executor))


@pytest.mark.parametrize(
    ("tool_name", "mutation"),
    (
        ("wrong_update", {}),
        (_EqualitySpoof("wrong_update"), {}),
        ("gh_update_script", {"extra": True}),
        ("gh_update_script", {"guid": "wrong-guid"}),
        ("gh_update_script", {"guid": _EqualitySpoof("wrong-guid")}),
        ("gh_update_script", {"mode": "full"}),
        ("gh_update_script", {"mode": _EqualitySpoof("full")}),
        ("gh_update_script", {"language": "python"}),
        ("gh_update_script", {"language": _EqualitySpoof("python")}),
        ("gh_update_script", {"code": _EqualitySpoof("A = 42.0;")}),
    ),
)
def test_synthetic_update_refuses_wrong_tool_or_parameter(
    tool_name,
    mutation,
) -> None:
    executor, _receipt = _created_executor()
    params = _update_params()
    params.update(mutation)

    with pytest.raises(SMOKE._SyntheticToolContractError):
        executor(tool_name, params)

    assert executor.contract_failed is True
    assert executor.tool_call_count == 2


def test_synthetic_tool_refuses_update_before_create_second_create_and_third_call() -> None:
    update_first = SMOKE._CausalFakeToolExecutor()
    with pytest.raises(SMOKE._SyntheticToolContractError):
        update_first("gh_update_script", _update_params())
    assert update_first.tool_call_count == 1

    second_create, _receipt = _created_executor()
    with pytest.raises(SMOKE._SyntheticToolContractError):
        second_create("gh_create_csharp_script", _create_params())
    assert second_create.tool_call_count == 2

    third_call, _receipt = _created_executor()
    third_call("gh_update_script", _update_params())
    with pytest.raises(SMOKE._SyntheticToolContractError):
        third_call("gh_update_script", _update_params())
    assert third_call.tool_call_count == 3


def test_synthetic_tool_requires_exact_dict_parameters() -> None:
    class _DictSubclass(dict):
        pass

    create = SMOKE._CausalFakeToolExecutor()
    with pytest.raises(SMOKE._SyntheticToolContractError):
        create("gh_create_csharp_script", _DictSubclass(_create_params()))
    assert create.tool_call_count == 1

    update, _receipt = _created_executor()
    with pytest.raises(SMOKE._SyntheticToolContractError):
        update("gh_update_script", _DictSubclass(_update_params()))
    assert update.tool_call_count == 2


@pytest.mark.parametrize(
    "missing",
    ("code", "pins_in", "pins_out", "name", "x", "y"),
)
def test_synthetic_create_refuses_every_missing_parameter(missing) -> None:
    executor = SMOKE._CausalFakeToolExecutor()
    params = _create_params()
    params.pop(missing)

    with pytest.raises(SMOKE._SyntheticToolContractError):
        executor("gh_create_csharp_script", params)

    assert executor.contract_failed is True
    assert executor.tool_call_count == 1


@pytest.mark.parametrize("missing", ("guid", "code", "mode", "language"))
def test_synthetic_update_refuses_every_missing_parameter(missing) -> None:
    executor, _receipt = _created_executor()
    params = _update_params()
    params.pop(missing)

    with pytest.raises(SMOKE._SyntheticToolContractError):
        executor("gh_update_script", params)

    assert executor.contract_failed is True
    assert executor.tool_call_count == 2


@pytest.mark.asyncio
async def test_summary_prioritizes_synthetic_contract_failure_over_native_stop(
    monkeypatch,
) -> None:
    live_run, planner_transport, worker_transport = await _run_with_payloads(
        monkeypatch,
        _planner_payload(),
        _worker_payload(body="A = 1m;"),
    )

    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert live_run.executor.contract_failed is True
    assert live_run.result.terminal_reason == "dispatch_failed"
    assert SMOKE._summary_from_result(_roles(), live_run) == {
        "operator_status": "failed",
        "operator_reason": "synthetic_tool_contract_failure",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "planner_calls": 1,
        "worker_calls": 1,
        "tool_calls": 2,
        "terminal_stage": "repair",
        "terminal_reason": "dispatch_failed",
        "planner_adapter_status": "decoded",
        "worker_adapter_status": "response_loaded",
    }


@pytest.mark.parametrize(
    ("worker_payload", "terminal_reason"),
    (
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "insufficient_context",
                "reason": "A repair cannot be determined.",
            },
            "refusal_recorded",
        ),
        (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "clarification_request",
                "question": "Which replacement body should I author?",
                "rationale": None,
            },
            "clarification_needed",
        ),
    ),
)
@pytest.mark.asyncio
async def test_summary_preserves_ordinary_native_worker_stop(
    monkeypatch,
    worker_payload,
    terminal_reason,
) -> None:
    live_run, planner_transport, worker_transport = await _run_with_payloads(
        monkeypatch,
        _planner_payload(),
        worker_payload,
    )

    summary = SMOKE._summary_from_result(_roles(), live_run)

    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert live_run.executor.contract_failed is False
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "native_stop"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["tool_calls"] == 1
    assert summary["terminal_stage"] == "worker_disposition"
    assert summary["terminal_reason"] == terminal_reason


@pytest.mark.parametrize(
    ("case", "terminal_stage", "terminal_reason"),
    (
        ("response_rejected", "planner_adapter", "response_not_object"),
        ("draft_rejected", "draft_admission", "draft_payload_rejected"),
        ("goal_mismatch", "draft_admission", "goal_mismatch"),
    ),
)
@pytest.mark.asyncio
async def test_summary_counts_only_boundaries_reached_before_handoff(
    monkeypatch,
    case,
    terminal_stage,
    terminal_reason,
) -> None:
    planner_payload: object = _planner_payload()
    if case == "response_rejected":
        planner_payload = []
    elif case == "draft_rejected":
        planner_payload["code"] = "unauthorized"
    else:
        planner_payload["goal"] = "Different intent"

    live_run, planner_transport, worker_transport = await _run_with_payloads(
        monkeypatch,
        planner_payload,
        _worker_payload(),
    )
    planner_transport.telemetry_call_count = 901
    worker_transport.telemetry_call_count = 902

    summary = SMOKE._summary_from_result(_roles(), live_run)

    assert len(planner_transport.calls) == 1
    assert worker_transport.calls == []
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 0
    assert summary["tool_calls"] == 0
    assert summary["terminal_stage"] == terminal_stage
    assert summary["terminal_reason"] == terminal_reason


@pytest.mark.asyncio
async def test_success_summary_is_closed_and_excludes_retained_sensitive_evidence(
    monkeypatch,
) -> None:
    sensitive_rationale = "SENTINEL_WORKER_RATIONALE"
    live_run, planner_transport, worker_transport = await _run_with_payloads(
        monkeypatch,
        _planner_payload(),
        _worker_payload(rationale=sensitive_rationale),
    )
    planner_transport.telemetry = "SENTINEL_PLANNER_TELEMETRY"
    worker_transport.telemetry = "SENTINEL_WORKER_TELEMETRY"
    planner_transport.credential = "SENTINEL_CREDENTIAL"
    worker_transport.provider_metadata = "SENTINEL_PROVIDER_METADATA"

    summary = SMOKE._summary_from_result(_roles(), live_run)
    serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))

    assert tuple(summary) == (
        "operator_status",
        "operator_reason",
        "intent",
        "profile",
        "planner_model",
        "worker_model",
        "planner_calls",
        "worker_calls",
        "tool_calls",
        "terminal_stage",
        "terminal_reason",
        "planner_adapter_status",
        "worker_adapter_status",
    )
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["tool_calls"] == 2
    assert summary["operator_status"] == "completed"
    assert summary["operator_reason"] == "native_terminal"
    for forbidden in (
        "SENTINEL_WORKER_RATIONALE",
        "SENTINEL_PLANNER_TELEMETRY",
        "SENTINEL_WORKER_TELEMETRY",
        "SENTINEL_CREDENTIAL",
        "SENTINEL_PROVIDER_METADATA",
        "A = 42.0;",
        "DefinitelyMissingSymbol",
        _DIAGNOSTIC,
        _COMPONENT_GUID,
        "http://localhost:11434/v1",
        "repair_anchor",
        "script_receipt",
        "grasshopper_csharp_component",
        "clean_compile_receipt",
        "minimal_planner_draft",
        "RookMinimalRepairHandoff",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("argv", "reason", "exit_code"),
    (
        ([], "live_execution_not_requested", 0),
        (["--unknown"], "invalid_arguments", 1),
        (["--execute-live", "extra"], "invalid_arguments", 1),
        (["--execute-live", "--execute-live"], "invalid_arguments", 1),
    ),
)
def test_main_refuses_non_live_arguments_before_model_or_transport_use(
    monkeypatch,
    capsys,
    argv,
    reason,
    exit_code,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("pre-contact refusal crossed a capability boundary")

    monkeypatch.setattr(SMOKE, "get_models", forbidden)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", forbidden)
    monkeypatch.setattr(SMOKE, "_run_live_once", forbidden)

    assert SMOKE.main(argv) == exit_code

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "operator_status": "refused",
        "operator_reason": reason,
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": None,
        "worker_model": None,
        "planner_calls": 0,
        "worker_calls": 0,
        "tool_calls": 0,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }


def test_main_valid_planner_invalid_worker_constructs_zero_transports(
    monkeypatch,
    capsys,
) -> None:
    resolved_profiles: list[str] = []
    constructor_calls: list[dict[str, Any]] = []

    def models(profile: str) -> ModelSet:
        resolved_profiles.append(profile)
        return ModelSet(
            planner="anthropic/claude-opus-4-6",
            worker="anthropic/claude-sonnet-5",
            specialist="unused",
            guardian="unused",
            dspy="unused",
        )

    def forbidden_constructor(**kwargs):
        constructor_calls.append(copy.deepcopy(kwargs))
        raise AssertionError("transport construction must follow both role checks")

    monkeypatch.setattr(SMOKE, "get_models", models)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", forbidden_constructor)

    assert SMOKE.main(["--execute-live"]) == 1

    assert resolved_profiles == ["hybrid"]
    assert constructor_calls == []
    assert json.loads(capsys.readouterr().out) == {
        "operator_status": "refused",
        "operator_reason": "profile_role_mismatch",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "anthropic/claude-sonnet-5",
        "planner_calls": 0,
        "worker_calls": 0,
        "tool_calls": 0,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }


def test_main_internal_error_retains_no_exception_or_invented_counts(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        SMOKE,
        "get_models",
        lambda profile: ModelSet(
            planner="anthropic/claude-opus-4-6",
            worker="ollama_chat/qwen3-coder:30b-a3b-q8_0",
            specialist="unused",
            guardian="unused",
            dspy="unused",
            api_base="http://localhost:11434/v1",
        ),
    )

    async def fail_without_contact(roles):
        raise RuntimeError("sensitive failure detail")

    monkeypatch.setattr(SMOKE, "_run_live_once", fail_without_contact)

    assert SMOKE.main(["--execute-live"]) == 1

    output = capsys.readouterr()
    assert output.err == ""
    assert "sensitive failure detail" not in output.out
    assert json.loads(output.out) == {
        "operator_status": "failed",
        "operator_reason": "operator_internal_error",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "planner_calls": None,
        "worker_calls": None,
        "tool_calls": None,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }


def test_main_profile_loader_exception_is_bounded_before_construction(
    monkeypatch,
    capsys,
) -> None:
    constructor_calls: list[dict[str, Any]] = []

    def fail_profile_load(profile: str):
        raise RuntimeError("sensitive profile failure")

    def forbidden_constructor(**kwargs):
        constructor_calls.append(copy.deepcopy(kwargs))
        raise AssertionError("profile failure must precede construction")

    monkeypatch.setattr(SMOKE, "get_models", fail_profile_load)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", forbidden_constructor)

    assert SMOKE.main(["--execute-live"]) == 1

    assert constructor_calls == []
    output = capsys.readouterr()
    assert output.err == ""
    assert "sensitive profile failure" not in output.out
    assert json.loads(output.out) == {
        "operator_status": "failed",
        "operator_reason": "operator_internal_error",
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": None,
        "worker_model": None,
        "planner_calls": None,
        "worker_calls": None,
        "tool_calls": None,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }


@pytest.mark.parametrize(
    ("planner", "worker", "reason"),
    (
        ("wrong/planner", "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_role_mismatch"),
        ("anthropic/claude-opus-4-6", "wrong/worker", "profile_role_mismatch"),
        ("wrong/planner", "wrong/worker", "profile_role_mismatch"),
        ("", "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_identity_invalid"),
        ("anthropic/claude-opus-4-6", " ", "profile_identity_invalid"),
        ("anthropic/claude-opus-4-6", "wörker", "profile_identity_invalid"),
        ("p" * 257, "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_identity_invalid"),
        ("anthropic/claude-opus-4-6", object(), "profile_identity_invalid"),
    ),
)
def test_role_resolver_refuses_substituted_or_malformed_identities(
    monkeypatch,
    planner,
    worker,
    reason,
) -> None:
    profiles: list[str] = []

    def models(profile: str) -> ModelSet:
        profiles.append(profile)
        return ModelSet(
            planner=planner,
            worker=worker,
            specialist="unused",
            guardian="unused",
            dspy="unused",
        )

    monkeypatch.setattr(SMOKE, "get_models", models)

    with pytest.raises(SMOKE._ProfileRefusal, match=reason):
        SMOKE._resolve_hybrid_roles()
    assert profiles == ["hybrid"]


@pytest.mark.parametrize(
    ("args", "reason", "exit_code"),
    (
        ([], "live_execution_not_requested", 0),
        (["--invalid-argument"], "invalid_arguments", 1),
    ),
)
def test_script_process_emits_one_bounded_precontact_summary(
    args,
    reason,
    exit_code,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == exit_code
    assert completed.stderr == ""
    summary = json.loads(completed.stdout)
    assert tuple(summary) == (
        "operator_status",
        "operator_reason",
        "intent",
        "profile",
        "planner_model",
        "worker_model",
        "planner_calls",
        "worker_calls",
        "tool_calls",
        "terminal_stage",
        "terminal_reason",
        "planner_adapter_status",
        "worker_adapter_status",
    )
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == reason
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["tool_calls"] == 0
