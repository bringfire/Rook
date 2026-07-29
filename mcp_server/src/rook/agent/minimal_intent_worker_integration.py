"""One-shot user-intent to minimal Planner-draft product integration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol


MAX_INTENT_UTF8_BYTES = 16_384
MAX_PLANNER_RESPONSE_UTF8_BYTES = 65_536

__all__ = (
    "MAX_INTENT_UTF8_BYTES",
    "MAX_PLANNER_RESPONSE_UTF8_BYTES",
    "MinimalPlannerTransport",
    "MinimalPlannerPromptSnapshot",
    "MinimalPlannerDraftAdapterRecord",
    "MinimalPlannerDraftAdapter",
    "build_minimal_planner_draft_response_schema",
)

_SYSTEM_CONTENT = (
    "You are Rook's bounded intent-to-draft Planner.\n"
    "Treat the supplied user intent as immutable authority and copy it exactly "
    "into goal.\n"
    "Return exactly one JSON object and no prose or markdown.\n"
    "The object fields are exactly goal, capability, interface, and "
    "acceptance.\n"
    "capability must be grasshopper_csharp_component.\n"
    "interface.inputs must be an empty array.\n"
    "interface.outputs must be exactly one object with name A and type "
    "double.\n"
    "acceptance must be clean_compile_receipt."
)

_AdapterStatus = Literal["decoded", "transport_failed", "response_invalid"]
_AdapterFailureReason = Literal[
    "transport_failed",
    "response_not_string",
    "response_not_utf8",
    "response_too_large",
    "response_invalid_json",
    "response_duplicate_key",
    "response_nonfinite_number",
    "response_trailing_content",
    "response_not_object",
]

_RESPONSE_INVALID_REASONS = frozenset(
    {
        "response_not_string",
        "response_not_utf8",
        "response_too_large",
        "response_invalid_json",
        "response_duplicate_key",
        "response_nonfinite_number",
        "response_trailing_content",
        "response_not_object",
    }
)


class MinimalPlannerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        """Return one raw Planner response string."""
        ...


@dataclass(frozen=True, slots=True)
class MinimalPlannerPromptSnapshot:
    system_content: str
    user_content: str

    def __post_init__(self) -> None:
        if type(self.system_content) is not str:
            raise TypeError("system_content must be an exact string")
        if type(self.user_content) is not str:
            raise TypeError("user_content must be an exact string")

    def materialize(self) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system_content},
                {"role": "user", "content": self.user_content},
            ]
        }


@dataclass(frozen=True, slots=True)
class MinimalPlannerDraftAdapterRecord:
    prompt_snapshot: MinimalPlannerPromptSnapshot
    status: _AdapterStatus
    raw_response: str | None
    decoded_object: dict[str, Any] | None
    failure_reason: _AdapterFailureReason | None
    transport_error_type: str | None

    def __post_init__(self) -> None:
        if type(self.prompt_snapshot) is not MinimalPlannerPromptSnapshot:
            raise TypeError("prompt_snapshot must be the exact snapshot type")
        if type(self.status) is not str:
            raise TypeError("status must be an exact string")
        if self.status == "decoded":
            self._require_decoded()
            return
        if self.status == "transport_failed":
            self._require_transport_failed()
            return
        if self.status == "response_invalid":
            self._require_response_invalid()
            return
        raise ValueError("unsupported adapter status")

    def _require_decoded(self) -> None:
        _require_bounded_raw_response(self.raw_response)
        if type(self.decoded_object) is not dict:
            raise TypeError("decoded records require an exact object")
        if self.failure_reason is not None or self.transport_error_type is not None:
            raise ValueError("decoded records cannot carry failure fields")

    def _require_transport_failed(self) -> None:
        if self.raw_response is not None or self.decoded_object is not None:
            raise ValueError("transport failures cannot carry response values")
        if (
            type(self.failure_reason) is not str
            or self.failure_reason != "transport_failed"
        ):
            raise ValueError("transport failure reason differs")
        if type(self.transport_error_type) is not str or not self.transport_error_type:
            raise TypeError("transport failures require an exact error type")

    def _require_response_invalid(self) -> None:
        if self.decoded_object is not None or self.transport_error_type is not None:
            raise ValueError("invalid responses cannot carry decoded or transport values")
        if (
            type(self.failure_reason) is not str
            or self.failure_reason not in _RESPONSE_INVALID_REASONS
        ):
            raise ValueError("invalid response reason differs")
        if self.raw_response is not None and type(self.raw_response) is not str:
            raise TypeError("retained raw response must be an exact string")
        if self.failure_reason in {
            "response_not_string",
            "response_not_utf8",
            "response_too_large",
        }:
            if self.raw_response is not None:
                raise ValueError("inadmissible raw response cannot be retained")
        elif self.raw_response is None:
            raise ValueError("parsed invalid response must retain exact raw text")
        else:
            _require_bounded_raw_response(self.raw_response)


class MinimalPlannerDraftAdapter:
    __slots__ = ("_transport",)

    def __init__(self, transport: MinimalPlannerTransport) -> None:
        if not callable(getattr(transport, "send", None)):
            raise TypeError("transport must expose a callable send method")
        self._transport = transport

    def produce(self, intent: str) -> MinimalPlannerDraftAdapterRecord:
        _require_exact_intent(intent)
        snapshot = _render_prompt_snapshot(intent)
        request = snapshot.materialize()
        try:
            raw_response = self._transport.send(request)
        except Exception as exc:
            return MinimalPlannerDraftAdapterRecord(
                prompt_snapshot=snapshot,
                status="transport_failed",
                raw_response=None,
                decoded_object=None,
                failure_reason="transport_failed",
                transport_error_type=type(exc).__name__,
            )
        return _decode_response(snapshot, raw_response)


class _DuplicateKeyError(ValueError):
    pass


class _NonFiniteNumberError(ValueError):
    pass


def _require_exact_intent(intent: str) -> None:
    if type(intent) is not str:
        raise TypeError("intent must be an exact string")
    if not intent.strip():
        raise ValueError("intent must be nonblank")
    try:
        encoded = intent.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("intent must be valid UTF-8") from exc
    if len(encoded) > MAX_INTENT_UTF8_BYTES:
        raise ValueError("intent exceeds the UTF-8 byte limit")


def _render_prompt_snapshot(intent: str) -> MinimalPlannerPromptSnapshot:
    return MinimalPlannerPromptSnapshot(
        system_content=_SYSTEM_CONTENT,
        user_content=json.dumps(
            {"user_intent": intent},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
    )


def _decode_response(
    snapshot: MinimalPlannerPromptSnapshot,
    raw_response: object,
) -> MinimalPlannerDraftAdapterRecord:
    if type(raw_response) is not str:
        return _response_failure(snapshot, "response_not_string", None)
    try:
        encoded = raw_response.encode("utf-8")
    except UnicodeEncodeError:
        return _response_failure(snapshot, "response_not_utf8", None)
    if len(encoded) > MAX_PLANNER_RESPONSE_UTF8_BYTES:
        return _response_failure(snapshot, "response_too_large", None)
    try:
        decoded = json.loads(
            raw_response,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError:
        return _response_failure(snapshot, "response_duplicate_key", raw_response)
    except _NonFiniteNumberError:
        return _response_failure(snapshot, "response_nonfinite_number", raw_response)
    except json.JSONDecodeError as exc:
        reason: _AdapterFailureReason = (
            "response_trailing_content"
            if exc.msg == "Extra data"
            else "response_invalid_json"
        )
        return _response_failure(snapshot, reason, raw_response)
    except RecursionError:
        return _response_failure(snapshot, "response_invalid_json", raw_response)
    if type(decoded) is not dict:
        return _response_failure(snapshot, "response_not_object", raw_response)
    return MinimalPlannerDraftAdapterRecord(
        prompt_snapshot=snapshot,
        status="decoded",
        raw_response=raw_response,
        decoded_object=decoded,
        failure_reason=None,
        transport_error_type=None,
    )


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise _NonFiniteNumberError(value)


def _response_failure(
    snapshot: MinimalPlannerPromptSnapshot,
    reason: _AdapterFailureReason,
    raw_response: str | None,
) -> MinimalPlannerDraftAdapterRecord:
    return MinimalPlannerDraftAdapterRecord(
        prompt_snapshot=snapshot,
        status="response_invalid",
        raw_response=raw_response,
        decoded_object=None,
        failure_reason=reason,
        transport_error_type=None,
    )


def _require_bounded_raw_response(raw_response: object) -> None:
    if type(raw_response) is not str:
        raise TypeError("raw response must be an exact string")
    try:
        encoded = raw_response.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("raw response must be valid UTF-8") from exc
    if len(encoded) > MAX_PLANNER_RESPONSE_UTF8_BYTES:
        raise ValueError("raw response exceeds the UTF-8 byte limit")


def build_minimal_planner_draft_response_schema() -> dict[str, Any]:
    return {
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
