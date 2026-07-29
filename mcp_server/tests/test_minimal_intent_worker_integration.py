from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.minimal_intent_worker_integration as integration
from rook.agent.minimal_intent_worker_integration import (
    MAX_INTENT_UTF8_BYTES,
    MAX_PLANNER_RESPONSE_UTF8_BYTES,
    MinimalPlannerDraftAdapter,
    MinimalPlannerDraftAdapterRecord,
    MinimalPlannerPromptSnapshot,
)


_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_COMPONENT_GUID = "minimal-intent-component-guid"
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKER_BODY = "A = 42.0;"
_TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the "
    "current context."
)


def _planner_payload(goal: str = _INTENT) -> dict[str, Any]:
    return {
        "goal": goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


class _RecordingPlannerTransport:
    def __init__(self, raw_response: object) -> None:
        self.raw_response = raw_response
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self.raw_response  # type: ignore[return-value]


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True

    def __str__(self) -> str:
        return _INTENT


class _StringSubclass(str):
    pass


class _RaisingPlannerTransport:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        raise self.error


class _AdapterSubclass(MinimalPlannerDraftAdapter):
    pass


class _SubstituteProducer:
    def produce(self, intent: str) -> MinimalPlannerDraftAdapterRecord:
        raise AssertionError("substitute producer must not be invoked")


class _IntegrationWorkerTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        captured = copy.deepcopy(dict(prompt_artifact))
        self.calls.append(captured)
        assert len(self.calls) == 1
        user_message = captured["messages"][1]
        assert user_message["role"] == "user"
        worker_request = json.loads(user_message["content"])
        assert _TARGET_DIAGNOSTIC in set(_iter_strings(worker_request))
        return json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_repair_params",
                "rationale": (
                    "Author a complete replacement body for the declared "
                    "A:double interface."
                ),
                "input": {"code": _WORKER_BODY, "mode": "body"},
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class _CausalToolExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((tool_name, captured))
        if len(self.calls) == 1:
            assert tool_name == "gh_create_csharp_script"
            assert captured == {
                "code": _INITIAL_BODY,
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalRepairHandoff",
                "x": 375,
                "y": 1080,
            }
            return _created_with_errors(captured["code"])
        if len(self.calls) == 2:
            assert tool_name == "gh_update_script"
            assert captured == {
                "guid": _COMPONENT_GUID,
                "code": _WORKER_BODY,
                "mode": "body",
                "language": "csharp",
            }
            return _updated_clean()
        raise AssertionError("unexpected extra typed-tool call")


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


def _updated_clean() -> dict[str, Any]:
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
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


@pytest.mark.asyncio
async def test_exact_intent_walks_real_handoff_to_native_terminal() -> None:
    planner_transport = _RecordingPlannerTransport(
        json.dumps(
            _planner_payload(_INTENT),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    worker_transport = _IntegrationWorkerTransport()
    tool_executor = _CausalToolExecutor()

    result = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )

    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert [name for name, _ in tool_executor.calls] == [
        "gh_create_csharp_script",
        "gh_update_script",
    ]
    assert result.intent == _INTENT
    assert result.planner_adapter_record.raw_response == (
        planner_transport.raw_response
    )
    assert result.validated_draft == result.handoff_result.draft
    assert result.validated_draft.goal == _INTENT
    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert result.terminal_stage == result.handoff_result.terminal_stage
    assert result.terminal_reason == result.handoff_result.terminal_reason
    assert result.handoff_result.final_graph.nodes["done"].status == "ready"


@pytest.mark.parametrize("adapter_kind", ["subclass", "substitute"])
@pytest.mark.asyncio
async def test_runner_requires_exact_concrete_planner_adapter_before_calls(
    adapter_kind: str,
) -> None:
    planner_transport = _RecordingPlannerTransport(
        json.dumps(_planner_payload(), sort_keys=True, separators=(",", ":"))
    )
    planner_adapter: object
    if adapter_kind == "subclass":
        planner_adapter = _AdapterSubclass(planner_transport)
    else:
        planner_adapter = _SubstituteProducer()
    worker_transport = _IntegrationWorkerTransport()
    tool_executor = _CausalToolExecutor()

    with pytest.raises(TypeError, match="exact MinimalPlannerDraftAdapter"):
        await integration.run_minimal_intent_worker_integration(
            _INTENT,
            planner_adapter=planner_adapter,  # type: ignore[arg-type]
            worker_transport=worker_transport,
            tool_executor=tool_executor,
        )

    assert planner_transport.calls == []
    assert worker_transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.parametrize("invalid_boundary", ["worker_transport", "tool_executor"])
@pytest.mark.asyncio
async def test_runner_validates_all_capability_boundaries_before_planner_call(
    invalid_boundary: str,
) -> None:
    planner_transport = _RecordingPlannerTransport(json.dumps(_planner_payload()))
    worker_transport: object = _IntegrationWorkerTransport()
    tool_executor: object = _CausalToolExecutor()
    if invalid_boundary == "worker_transport":
        worker_transport = object()
    else:
        tool_executor = object()

    with pytest.raises(TypeError):
        await integration.run_minimal_intent_worker_integration(
            _INTENT,
            planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
            worker_transport=worker_transport,  # type: ignore[arg-type]
            tool_executor=tool_executor,  # type: ignore[arg-type]
        )

    assert planner_transport.calls == []
    if isinstance(worker_transport, _IntegrationWorkerTransport):
        assert worker_transport.calls == []
    if isinstance(tool_executor, _CausalToolExecutor):
        assert tool_executor.calls == []


@pytest.mark.asyncio
async def test_transport_failure_returns_native_adapter_stop() -> None:
    planner_transport = _RaisingPlannerTransport(RuntimeError("planner unavailable"))
    worker_transport = _IntegrationWorkerTransport()
    tool_executor = _CausalToolExecutor()

    result = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )

    assert len(planner_transport.calls) == 1
    assert result.validated_draft is None
    assert result.handoff_result is None
    assert result.terminal_stage == "planner_adapter"
    assert result.terminal_reason == "transport_failed"
    assert worker_transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.asyncio
async def test_extra_planner_field_returns_draft_payload_rejected() -> None:
    payload = _planner_payload()
    payload["code"] = "A = 42.0;"
    planner_transport = _RecordingPlannerTransport(
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    worker_transport = _IntegrationWorkerTransport()
    tool_executor = _CausalToolExecutor()

    result = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )

    assert len(planner_transport.calls) == 1
    assert result.validated_draft is None
    assert result.handoff_result is None
    assert result.terminal_stage == "draft_admission"
    assert result.terminal_reason == "draft_payload_rejected"
    assert worker_transport.calls == []
    assert tool_executor.calls == []


@pytest.mark.parametrize(
    "planner_goal",
    [_INTENT + " ", chr(0xD800)],
    ids=["changed_whitespace", "escaped_lone_surrogate"],
)
@pytest.mark.asyncio
async def test_changed_planner_goal_returns_goal_mismatch_without_encoding(
    planner_goal: str,
) -> None:
    planner_transport = _RecordingPlannerTransport(
        json.dumps(
            _planner_payload(planner_goal),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )
    worker_transport = _IntegrationWorkerTransport()
    tool_executor = _CausalToolExecutor()

    result = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )

    assert len(planner_transport.calls) == 1
    assert result.validated_draft is None
    assert result.handoff_result is None
    assert result.terminal_stage == "draft_admission"
    assert result.terminal_reason == "goal_mismatch"
    assert worker_transport.calls == []
    assert tool_executor.calls == []


def test_planner_prompt_contains_only_intent_and_closed_draft_vocabulary() -> None:
    planner_transport = _RecordingPlannerTransport(json.dumps(_planner_payload()))

    record = MinimalPlannerDraftAdapter(planner_transport).produce(_INTENT)

    assert json.loads(record.prompt_snapshot.user_content) == {
        "user_intent": _INTENT
    }
    assert record.prompt_snapshot.materialize() == planner_transport.calls[0]
    prompt_strings = tuple(
        _iter_strings(
            {
                "system": record.prompt_snapshot.system_content,
                "user": record.prompt_snapshot.user_content,
                "materialized": record.prompt_snapshot.materialize(),
            }
        )
    )
    for prohibited in (
        _INITIAL_BODY,
        _WORKER_BODY,
        "repair_same_component",
        "draft_repair_params",
        "gh_create_csharp_script",
        "gh_update_script",
        _COMPONENT_GUID,
        "CS0103",
    ):
        assert all(prohibited not in value for value in prompt_strings)
    for vocabulary in (
        "goal",
        "capability",
        "interface",
        "acceptance",
        "grasshopper_csharp_component",
        "inputs",
        "outputs",
        "A",
        "double",
        "clean_compile_receipt",
    ):
        assert vocabulary in record.prompt_snapshot.system_content
    assert "{" not in record.prompt_snapshot.system_content
    assert "}" not in record.prompt_snapshot.system_content
    assert "properties" not in record.prompt_snapshot.user_content
    assert "required" not in record.prompt_snapshot.user_content


@pytest.mark.asyncio
async def test_integration_result_rejects_cross_stage_substitutions() -> None:
    success_planner = _RecordingPlannerTransport(json.dumps(_planner_payload()))
    success = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(success_planner),
        worker_transport=_IntegrationWorkerTransport(),
        tool_executor=_CausalToolExecutor(),
    )
    adapter_stop = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(
            _RaisingPlannerTransport(RuntimeError("planner unavailable"))
        ),
        worker_transport=_IntegrationWorkerTransport(),
        tool_executor=_CausalToolExecutor(),
    )
    invalid_payload = _planner_payload()
    invalid_payload["code"] = "not admitted"
    draft_stop = await integration.run_minimal_intent_worker_integration(
        _INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(
            _RecordingPlannerTransport(json.dumps(invalid_payload))
        ),
        worker_transport=_IntegrationWorkerTransport(),
        tool_executor=_CausalToolExecutor(),
    )

    with pytest.raises((TypeError, ValueError)):
        replace(success, terminal_stage="draft_admission")
    with pytest.raises((TypeError, ValueError)):
        replace(success, validated_draft=None)
    with pytest.raises((TypeError, ValueError)):
        replace(adapter_stop, terminal_reason="goal_mismatch")
    with pytest.raises((TypeError, ValueError)):
        replace(adapter_stop, validated_draft=success.validated_draft)
    with pytest.raises((TypeError, ValueError)):
        replace(draft_stop, terminal_reason="not_a_draft_stop")
    with pytest.raises((TypeError, ValueError)):
        replace(draft_stop, handoff_result=success.handoff_result)


def test_concrete_adapter_owns_prompt_and_exactly_one_transport_call() -> None:
    raw = json.dumps(
        _planner_payload(),
        sort_keys=True,
        separators=(",", ":"),
    )
    transport = _RecordingPlannerTransport(raw)
    adapter = MinimalPlannerDraftAdapter(transport)

    record = adapter.produce(_INTENT)

    assert record.status == "decoded"
    assert record.raw_response == raw
    assert record.decoded_object == _planner_payload()
    assert record.failure_reason is None
    assert record.transport_error_type is None
    assert len(transport.calls) == 1
    assert transport.calls[0] == record.prompt_snapshot.materialize()
    assert json.loads(transport.calls[0]["messages"][1]["content"]) == {
        "user_intent": _INTENT
    }
    assert integration.build_minimal_planner_draft_response_schema() == {
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


def test_response_schema_is_fresh_for_transport_configuration() -> None:
    first = integration.build_minimal_planner_draft_response_schema()
    second = integration.build_minimal_planner_draft_response_schema()

    assert first == second
    assert first is not second
    first["properties"]["goal"]["type"] = "integer"
    assert second["properties"]["goal"] == {"type": "string"}


@pytest.mark.parametrize(
    ("raw_response", "failure_reason", "retained_raw"),
    [
        (42, "response_not_string", None),
        (_StringSubclass("{}"), "response_not_string", None),
        (chr(0xD800), "response_not_utf8", None),
        (
            "x" * (MAX_PLANNER_RESPONSE_UTF8_BYTES + 1),
            "response_too_large",
            None,
        ),
        ("not json", "response_invalid_json", "not json"),
        ('{"a":1,"a":2}', "response_duplicate_key", '{"a":1,"a":2}'),
        (
            '{"outer":{"a":1,"a":2}}',
            "response_duplicate_key",
            '{"outer":{"a":1,"a":2}}',
        ),
        ('{"value":NaN}', "response_nonfinite_number", '{"value":NaN}'),
        (
            '{"value":Infinity}',
            "response_nonfinite_number",
            '{"value":Infinity}',
        ),
        (
            '{"value":-Infinity}',
            "response_nonfinite_number",
            '{"value":-Infinity}',
        ),
        (
            '{"value":1e400}',
            "response_nonfinite_number",
            '{"value":1e400}',
        ),
        (
            '{"value":-1e400}',
            "response_nonfinite_number",
            '{"value":-1e400}',
        ),
        (
            '{"value":' + ("9" * 5_000) + "}",
            "response_invalid_json",
            '{"value":' + ("9" * 5_000) + "}",
        ),
        ("{} {}", "response_trailing_content", "{} {}"),
        ("[]", "response_not_object", "[]"),
        ("```json\n{}\n```", "response_invalid_json", "```json\n{}\n```"),
    ],
    ids=[
        "non_string",
        "string_subclass",
        "non_utf8",
        "oversized",
        "invalid_json",
        "duplicate_root",
        "duplicate_nested",
        "nan",
        "positive_infinity",
        "negative_infinity",
        "positive_exponent_overflow",
        "negative_exponent_overflow",
        "over_limit_integer_token",
        "trailing_content",
        "non_object_root",
        "markdown",
    ],
)
def test_adapter_returns_closed_response_invalid_records(
    raw_response: object,
    failure_reason: str,
    retained_raw: str | None,
) -> None:
    transport = _RecordingPlannerTransport(raw_response)

    record = MinimalPlannerDraftAdapter(transport).produce(_INTENT)

    assert len(transport.calls) == 1
    assert record.status == "response_invalid"
    assert record.failure_reason == failure_reason
    assert record.raw_response == retained_raw
    assert record.decoded_object is None
    assert record.transport_error_type is None


def _exact_size_json_object(size: int) -> str:
    prefix = '{"padding":"'
    suffix = '"}'
    padding = size - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
    assert padding >= 0
    value = prefix + ("x" * padding) + suffix
    assert len(value.encode("utf-8")) == size
    return value


def test_response_byte_limit_is_exact_before_retention() -> None:
    exact = _RecordingPlannerTransport(
        _exact_size_json_object(MAX_PLANNER_RESPONSE_UTF8_BYTES)
    )
    oversized = _RecordingPlannerTransport(
        _exact_size_json_object(MAX_PLANNER_RESPONSE_UTF8_BYTES + 1)
    )

    exact_record = MinimalPlannerDraftAdapter(exact).produce(_INTENT)
    oversized_record = MinimalPlannerDraftAdapter(oversized).produce(_INTENT)

    assert exact_record.status == "decoded"
    assert exact_record.raw_response is not None
    assert oversized_record.status == "response_invalid"
    assert oversized_record.failure_reason == "response_too_large"
    assert oversized_record.raw_response is None


def test_transport_exception_becomes_typed_failure_without_response() -> None:
    transport = _RaisingPlannerTransport(RuntimeError("declared failure"))

    record = MinimalPlannerDraftAdapter(transport).produce(_INTENT)

    assert len(transport.calls) == 1
    assert record.status == "transport_failed"
    assert record.failure_reason == "transport_failed"
    assert record.transport_error_type == "RuntimeError"
    assert record.raw_response is None
    assert record.decoded_object is None


def test_base_exception_is_not_caught() -> None:
    transport = _RaisingPlannerTransport(KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        MinimalPlannerDraftAdapter(transport).produce(_INTENT)

    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "intent",
    [7, _EqualitySpoof(), "", "   ", chr(0xD800), "é" * 8_193],
    ids=[
        "non_string",
        "equality_spoof",
        "empty",
        "whitespace",
        "non_utf8",
        "oversized",
    ],
)
def test_invalid_intent_stops_before_transport(intent: object) -> None:
    transport = _RecordingPlannerTransport(json.dumps(_planner_payload()))

    with pytest.raises((TypeError, ValueError)):
        MinimalPlannerDraftAdapter(transport).produce(intent)  # type: ignore[arg-type]

    assert transport.calls == []


def test_exact_intent_byte_limit_preserves_original_value() -> None:
    intent = "é" * 8_192
    assert len(intent.encode("utf-8")) == MAX_INTENT_UTF8_BYTES
    transport = _RecordingPlannerTransport(json.dumps({"goal": intent}))

    record = MinimalPlannerDraftAdapter(transport).produce(intent)

    assert record.status == "decoded"
    assert json.loads(record.prompt_snapshot.user_content) == {
        "user_intent": intent
    }


def test_adapter_requires_callable_transport() -> None:
    with pytest.raises(TypeError):
        MinimalPlannerDraftAdapter(object())  # type: ignore[arg-type]


def test_transport_cannot_mutate_retained_prompt_snapshot() -> None:
    expected_raw = json.dumps(_planner_payload())

    class _MutatingTransport:
        def __init__(self) -> None:
            self.before: dict[str, Any] | None = None

        def send(self, prompt_artifact: Mapping[str, Any]) -> str:
            assert isinstance(prompt_artifact, dict)
            self.before = copy.deepcopy(prompt_artifact)
            prompt_artifact["messages"][0]["content"] = "mutated"
            prompt_artifact["messages"][1]["content"] = "mutated"
            return expected_raw

    transport = _MutatingTransport()
    record = MinimalPlannerDraftAdapter(transport).produce(_INTENT)

    assert transport.before is not None
    assert record.prompt_snapshot.materialize() == transport.before


def test_adapter_record_rejects_cross_state_substitutions() -> None:
    decoded = MinimalPlannerDraftAdapter(
        _RecordingPlannerTransport(json.dumps(_planner_payload()))
    ).produce(_INTENT)

    with pytest.raises((TypeError, ValueError)):
        replace(decoded, raw_response=None)
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, failure_reason="response_invalid_json")
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, raw_response=_StringSubclass(decoded.raw_response))
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, raw_response=chr(0xD800))
    with pytest.raises((TypeError, ValueError)):
        replace(
            decoded,
            raw_response="x" * (MAX_PLANNER_RESPONSE_UTF8_BYTES + 1),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, decoded_object=type("_DictSubclass", (dict,), {})())
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, status="transport_failed")
    with pytest.raises((TypeError, ValueError)):
        replace(decoded, status="response_invalid")

    failed = MinimalPlannerDraftAdapter(
        _RaisingPlannerTransport(RuntimeError("failure"))
    ).produce(_INTENT)
    with pytest.raises((TypeError, ValueError)):
        replace(failed, raw_response="{}")
    with pytest.raises((TypeError, ValueError)):
        replace(failed, transport_error_type=None)
    with pytest.raises((TypeError, ValueError)):
        replace(failed, transport_error_type="")
    with pytest.raises((TypeError, ValueError)):
        replace(failed, decoded_object={})
    with pytest.raises((TypeError, ValueError)):
        replace(failed, status="decoded")
    with pytest.raises((TypeError, ValueError)):
        replace(failed, status="response_invalid")

    invalid = MinimalPlannerDraftAdapter(
        _RecordingPlannerTransport("not json")
    ).produce(_INTENT)
    with pytest.raises((TypeError, ValueError)):
        replace(invalid, decoded_object={})
    with pytest.raises((TypeError, ValueError)):
        replace(invalid, raw_response=None)
    with pytest.raises((TypeError, ValueError)):
        replace(invalid, transport_error_type="RuntimeError")
    with pytest.raises((TypeError, ValueError)):
        replace(invalid, status="decoded")
    with pytest.raises((TypeError, ValueError)):
        replace(invalid, status="transport_failed")

    not_string = MinimalPlannerDraftAdapter(
        _RecordingPlannerTransport(42)
    ).produce(_INTENT)
    with pytest.raises((TypeError, ValueError)):
        replace(not_string, raw_response="42")

    with pytest.raises((TypeError, ValueError)):
        replace(decoded, status=_StringSubclass("decoded"))


def test_prompt_snapshot_requires_exact_string_fields() -> None:
    with pytest.raises(TypeError):
        MinimalPlannerPromptSnapshot(  # type: ignore[arg-type]
            system_content=7,
            user_content="{}",
        )


def test_adapter_record_requires_exact_prompt_snapshot() -> None:
    class _SnapshotSubclass(MinimalPlannerPromptSnapshot):
        pass

    snapshot = _SnapshotSubclass(system_content="system", user_content="{}")
    with pytest.raises(TypeError):
        MinimalPlannerDraftAdapterRecord(
            prompt_snapshot=snapshot,
            status="decoded",
            raw_response="{}",
            decoded_object={},
            failure_reason=None,
            transport_error_type=None,
        )
