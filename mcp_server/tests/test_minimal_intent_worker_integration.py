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
