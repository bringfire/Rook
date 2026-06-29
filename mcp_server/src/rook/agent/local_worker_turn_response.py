"""LM5B local-worker response contract.

Defines what a future local/internal worker may say back after receiving an
LM5A LocalWorkerTurnContext, and records whether that response is structurally
admissible. This module does not call providers, parse worker text, execute
tools, mutate graphs, continue streams, or accept actions as execution
permission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Callable, Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext

WorkerResponseKind = Literal[
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]
WorkerRefusalCategory = Literal[
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
]
WorkerResponseValidationFailure = Literal[
    "payload_invalid",
    "unknown_action_id",
    "action_input_invalid",
]

__all__ = (
    "LocalWorkerTurnResponse",
    "LocalWorkerTurnAttemptRecord",
    "WorkerActionRequest",
    "WorkerClarificationRequest",
    "WorkerRefusal",
    "WorkerObservation",
    "WorkerResponseKind",
    "WorkerRefusalCategory",
    "WorkerResponseValidationFailure",
    "validate_local_worker_turn_response",
)

_REFUSAL_CATEGORIES = frozenset(
    {
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    }
)
_RESPONSE_KINDS = frozenset(
    {
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    }
)
_VALIDATION_FAILURES = frozenset(
    {
        "payload_invalid",
        "unknown_action_id",
        "action_input_invalid",
    }
)


@dataclass(frozen=True)
class WorkerActionRequest:
    action_id: str
    rationale: str
    input: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.action_id, "action_id")
        _require_non_empty_str(self.rationale, "rationale")
        object.__setattr__(
            self,
            "input",
            _freeze_json_mapping(self.input, "input"),
        )


@dataclass(frozen=True)
class WorkerClarificationRequest:
    question: str
    rationale: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str(self.question, "question")
        _require_optional_str(self.rationale, "rationale")


@dataclass(frozen=True)
class WorkerRefusal:
    category: WorkerRefusalCategory
    reason: str

    def __post_init__(self) -> None:
        category = _require_str(self.category, "category")
        if category not in _REFUSAL_CATEGORIES:
            raise ValueError(f"unknown refusal category: {category!r}")
        _require_non_empty_str(self.reason, "reason")


@dataclass(frozen=True)
class WorkerObservation:
    message: str
    data: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str(self.message, "message")
        if self.data is not None:
            object.__setattr__(
                self,
                "data",
                _freeze_json_mapping(self.data, "data"),
            )


WorkerResponsePayload = (
    WorkerActionRequest
    | WorkerClarificationRequest
    | WorkerRefusal
    | WorkerObservation
)
_PAYLOAD_TYPES = (
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerRefusal,
    WorkerObservation,
)


@dataclass(frozen=True)
class LocalWorkerTurnResponse:
    payload: WorkerResponsePayload

    def __post_init__(self) -> None:
        if type(self.payload) not in _PAYLOAD_TYPES:
            raise TypeError("payload must be a closed worker response payload")


@dataclass(frozen=True)
class LocalWorkerTurnAttemptRecord:
    valid: bool
    response_kind: WorkerResponseKind | None
    failure: WorkerResponseValidationFailure | None
    reason: str
    action_id: str | None
    context_workflow_id: str
    context_contract_fingerprint: str

    def __post_init__(self) -> None:
        _require_bool(self.valid, "valid")
        _require_optional_choice(self.response_kind, _RESPONSE_KINDS, "response_kind")
        _require_optional_choice(self.failure, _VALIDATION_FAILURES, "failure")
        _require_non_empty_str(self.reason, "reason")
        _require_optional_str(self.action_id, "action_id")
        _require_non_empty_str(self.context_workflow_id, "context_workflow_id")
        _require_non_empty_str(
            self.context_contract_fingerprint,
            "context_contract_fingerprint",
        )
        _validate_attempt_record_coherence(self)


def validate_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnAttemptRecord:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")
    if not isinstance(response, LocalWorkerTurnResponse):
        raise TypeError("response must be LocalWorkerTurnResponse")

    payload = response.payload
    if type(payload) not in _PAYLOAD_TYPES:
        return _record(
            context,
            valid=False,
            response_kind=None,
            failure="payload_invalid",
            reason="payload_invalid:closed_payload_required",
            action_id=None,
        )

    if type(payload) is WorkerActionRequest:
        return _validate_action_request(context, payload)
    if type(payload) is WorkerClarificationRequest:
        failure_reason = _payload_failure_reason(
            payload,
            _validate_clarification_payload,
            "clarification_request",
        )
        if failure_reason is not None:
            return _payload_invalid_record(context, failure_reason)
        return _record(
            context,
            valid=True,
            response_kind="clarification_request",
            failure=None,
            reason="valid_clarification_request",
            action_id=None,
        )
    if type(payload) is WorkerRefusal:
        failure_reason = _payload_failure_reason(
            payload,
            _validate_refusal_payload,
            "refusal",
        )
        if failure_reason is not None:
            return _payload_invalid_record(context, failure_reason)
        return _record(
            context,
            valid=True,
            response_kind="refusal",
            failure=None,
            reason="valid_refusal",
            action_id=None,
        )

    failure_reason = _payload_failure_reason(
        payload,
        _validate_observation_payload,
        "observation",
    )
    if failure_reason is not None:
        return _payload_invalid_record(context, failure_reason)
    return _record(
        context,
        valid=True,
        response_kind="observation",
        failure=None,
        reason="valid_observation",
        action_id=None,
    )


def _validate_action_request(
    context: LocalWorkerTurnContext,
    payload: WorkerActionRequest,
) -> LocalWorkerTurnAttemptRecord:
    payload_failure = _payload_failure_reason(
        payload,
        _validate_action_payload_except_input,
        "action_request",
    )
    if payload_failure is not None:
        return _payload_invalid_record(context, payload_failure)

    action_id = payload.action_id if isinstance(payload.action_id, str) else None
    input_failure = _action_input_failure_reason(payload.input)
    if input_failure is not None:
        return _record(
            context,
            valid=False,
            response_kind="action_request",
            failure="action_input_invalid",
            reason=input_failure,
            action_id=action_id,
        )

    allowed_action_ids = {action.action_id for action in context.allowed_actions}
    if payload.action_id not in allowed_action_ids:
        return _record(
            context,
            valid=False,
            response_kind="action_request",
            failure="unknown_action_id",
            reason=f"unknown_action_id:{payload.action_id}",
            action_id=payload.action_id,
        )

    return _record(
        context,
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id=payload.action_id,
    )


def _payload_invalid_record(
    context: LocalWorkerTurnContext,
    reason: str,
) -> LocalWorkerTurnAttemptRecord:
    return _record(
        context,
        valid=False,
        response_kind=None,
        failure="payload_invalid",
        reason=reason,
        action_id=None,
    )


def _payload_failure_reason(
    payload: object,
    validator: Callable[[object], None],
    response_kind: str,
) -> str | None:
    try:
        validator(payload)
    except (TypeError, ValueError):
        return f"payload_invalid:{response_kind}_invalid"
    return None


def _validate_action_payload_except_input(payload: object) -> None:
    if type(payload) is not WorkerActionRequest:
        raise TypeError("payload must be WorkerActionRequest")
    _require_non_empty_str(payload.action_id, "action_id")
    _require_non_empty_str(payload.rationale, "rationale")


def _validate_clarification_payload(payload: object) -> None:
    if type(payload) is not WorkerClarificationRequest:
        raise TypeError("payload must be WorkerClarificationRequest")
    _require_non_empty_str(payload.question, "question")
    _require_optional_str(payload.rationale, "rationale")


def _validate_refusal_payload(payload: object) -> None:
    if type(payload) is not WorkerRefusal:
        raise TypeError("payload must be WorkerRefusal")
    category = _require_str(payload.category, "category")
    if category not in _REFUSAL_CATEGORIES:
        raise ValueError(f"unknown refusal category: {category!r}")
    _require_non_empty_str(payload.reason, "reason")


def _validate_observation_payload(payload: object) -> None:
    if type(payload) is not WorkerObservation:
        raise TypeError("payload must be WorkerObservation")
    _require_non_empty_str(payload.message, "message")
    if payload.data is not None:
        _require_frozen_json_mapping(payload.data, "data")


def _action_input_failure_reason(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return "action_input_invalid:input_not_mapping"
    try:
        _require_frozen_json_mapping(value, "input")
    except TypeError:
        return "action_input_invalid:input_malformed"
    return None


def _record(
    context: LocalWorkerTurnContext,
    *,
    valid: bool,
    response_kind: WorkerResponseKind | None,
    failure: WorkerResponseValidationFailure | None,
    reason: str,
    action_id: str | None,
) -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=valid,
        response_kind=response_kind,
        failure=failure,
        reason=reason,
        action_id=action_id,
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _freeze_json_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    frozen = _freeze_json_value(value, field_name)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return frozen


def _require_frozen_json_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, MappingProxyType):
        raise TypeError(f"{field_name} must be a frozen mapping")
    _require_frozen_json_value(value, field_name)


def _require_frozen_json_value(value: object, field_name: str) -> None:
    if isinstance(value, MappingProxyType):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be strings")
            _require_frozen_json_value(item, f"{field_name}.{key}")
        return
    if isinstance(value, tuple):
        for item in value:
            _require_frozen_json_value(item, f"{field_name}[]")
        return
    if isinstance(value, list) or isinstance(value, Mapping):
        raise TypeError(f"{field_name} contains mutable JSON value")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{field_name} float values must be finite")
        return
    raise TypeError(f"{field_name} contains unsupported JSON value")


def _freeze_json_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be strings")
            copied[key] = _freeze_json_value(item, f"{field_name}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(item, f"{field_name}[]")
            for item in value
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{field_name} float values must be finite")
        return value
    raise TypeError(f"{field_name} contains unsupported JSON value")


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_optional_choice(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    if value not in allowed:
        raise ValueError(f"{field_name} has unknown value: {value!r}")
    return value


def _validate_attempt_record_coherence(
    record: LocalWorkerTurnAttemptRecord,
) -> None:
    if record.valid:
        _validate_valid_attempt_record(record)
        return
    if record.failure is None:
        raise ValueError("invalid attempt records require failure")


def _validate_valid_attempt_record(record: LocalWorkerTurnAttemptRecord) -> None:
    if record.failure is not None:
        raise ValueError("valid attempt records require failure to be None")
    if record.response_kind is None:
        raise ValueError("valid attempt records require response_kind")

    expected_reason_by_kind = {
        "action_request": "valid_action_request",
        "clarification_request": "valid_clarification_request",
        "refusal": "valid_refusal",
        "observation": "valid_observation",
    }
    if record.reason != expected_reason_by_kind[record.response_kind]:
        raise ValueError("valid attempt record reason does not match response_kind")

    if record.response_kind == "action_request":
        if not isinstance(record.action_id, str) or record.action_id == "":
            raise ValueError("valid action records require non-empty action_id")
        return
    if record.action_id is not None:
        raise ValueError("valid non-action records require action_id to be None")
