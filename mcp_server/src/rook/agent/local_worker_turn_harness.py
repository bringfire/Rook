"""LM5D deterministic one-turn local-worker harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext
from rook.agent.local_worker_turn_disposition import (
    LocalWorkerTurnDispositionRecord,
    dispose_local_worker_turn_response,
)
from rook.agent.local_worker_turn_response import LocalWorkerTurnResponse

HarnessStatus = Literal[
    "completed",
    "invalid_response",
    "worker_error",
]
LocalWorkerTurnWorker = Callable[
    [LocalWorkerTurnContext],
    LocalWorkerTurnResponse,
]

__all__ = (
    "HarnessStatus",
    "LocalWorkerTurnWorker",
    "LocalWorkerTurnHarnessRecord",
    "run_local_worker_turn",
)

_STATUSES = frozenset(
    {
        "completed",
        "invalid_response",
        "worker_error",
    }
)


@dataclass(frozen=True)
class LocalWorkerTurnHarnessRecord:
    status: HarnessStatus
    response: LocalWorkerTurnResponse | None
    disposition: LocalWorkerTurnDispositionRecord | None
    failure: str | None
    reason: str
    context_workflow_id: str
    context_contract_fingerprint: str

    def __post_init__(self) -> None:
        status = _require_str(self.status, "status")
        _require_optional_response(self.response, "response")
        _require_optional_disposition(self.disposition, "disposition")
        _require_optional_str(self.failure, "failure")
        reason = _require_non_empty_str(self.reason, "reason")
        workflow_id = _require_non_empty_str(
            self.context_workflow_id,
            "context_workflow_id",
        )
        contract_fingerprint = _require_non_empty_str(
            self.context_contract_fingerprint,
            "context_contract_fingerprint",
        )

        if status not in _STATUSES:
            raise ValueError(f"unknown harness status: {status!r}")

        if status == "completed":
            _validate_completed_record(
                record=self,
                reason=reason,
                workflow_id=workflow_id,
                contract_fingerprint=contract_fingerprint,
            )
            return
        if status == "invalid_response":
            _validate_invalid_response_record(self, reason=reason)
            return

        _validate_worker_error_record(self, reason=reason)


def run_local_worker_turn(
    context: LocalWorkerTurnContext,
    worker: LocalWorkerTurnWorker,
) -> LocalWorkerTurnHarnessRecord:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")
    if not callable(worker):
        raise TypeError("worker must be callable")

    workflow_id = context.workflow.workflow_id
    contract_fingerprint = context.workflow.contract_fingerprint

    try:
        response = worker(context)
    except Exception as exc:
        return LocalWorkerTurnHarnessRecord(
            status="worker_error",
            response=None,
            disposition=None,
            failure="worker_exception",
            reason=(
                "worker_exception:"
                f"{_safe_reason_payload(type(exc).__name__, 'unknown_exception')}"
            ),
            context_workflow_id=workflow_id,
            context_contract_fingerprint=contract_fingerprint,
        )

    if not isinstance(response, LocalWorkerTurnResponse):
        return LocalWorkerTurnHarnessRecord(
            status="invalid_response",
            response=None,
            disposition=None,
            failure="response_type_invalid",
            reason=(
                "response_type_invalid:"
                f"{_safe_reason_payload(type(response).__name__, 'unknown_type')}"
            ),
            context_workflow_id=workflow_id,
            context_contract_fingerprint=contract_fingerprint,
        )

    disposition = dispose_local_worker_turn_response(context, response)
    return LocalWorkerTurnHarnessRecord(
        status="completed",
        response=response,
        disposition=disposition,
        failure=None,
        reason=f"completed:{disposition.disposition}",
        context_workflow_id=workflow_id,
        context_contract_fingerprint=contract_fingerprint,
    )


def _validate_completed_record(
    *,
    record: LocalWorkerTurnHarnessRecord,
    reason: str,
    workflow_id: str,
    contract_fingerprint: str,
) -> None:
    if record.response is None:
        raise ValueError("completed harness records require response")
    if record.disposition is None:
        raise ValueError("completed harness records require disposition")
    if record.failure is not None:
        raise ValueError("completed harness records require failure to be None")
    if reason != f"completed:{record.disposition.disposition}":
        raise ValueError("completed reason must match disposition")
    attempt = record.disposition.attempt
    if attempt.context_workflow_id != workflow_id:
        raise ValueError("completed workflow_id must match disposition attempt")
    if attempt.context_contract_fingerprint != contract_fingerprint:
        raise ValueError(
            "completed contract fingerprint must match disposition attempt"
        )


def _validate_invalid_response_record(
    record: LocalWorkerTurnHarnessRecord,
    *,
    reason: str,
) -> None:
    if record.response is not None:
        raise ValueError("invalid_response records require response to be None")
    if record.disposition is not None:
        raise ValueError("invalid_response records require disposition to be None")
    if record.failure != "response_type_invalid":
        raise ValueError("invalid_response records require response_type_invalid")
    _require_exact_reason_payload(reason, "response_type_invalid")


def _validate_worker_error_record(
    record: LocalWorkerTurnHarnessRecord,
    *,
    reason: str,
) -> None:
    if record.response is not None:
        raise ValueError("worker_error records require response to be None")
    if record.disposition is not None:
        raise ValueError("worker_error records require disposition to be None")
    if record.failure != "worker_exception":
        raise ValueError("worker_error records require worker_exception")
    _require_exact_reason_payload(reason, "worker_exception")


def _require_exact_reason_payload(reason: str, prefix: str) -> str:
    expected_prefix = f"{prefix}:"
    if not reason.startswith(expected_prefix):
        raise ValueError(f"reason must start with {expected_prefix!r}")
    payload = reason.removeprefix(expected_prefix)
    if not _is_safe_reason_payload(payload):
        raise ValueError(f"reason must be exactly {prefix}:<Name>")
    return payload


def _safe_reason_payload(value: str, replacement: str) -> str:
    if _is_safe_reason_payload(value):
        return value
    return replacement


def _is_safe_reason_payload(value: str) -> bool:
    if value == "":
        return False
    return all(_is_ascii_alnum_or_underscore(char) for char in value)


def _is_ascii_alnum_or_underscore(char: str) -> bool:
    return (
        char == "_"
        or "0" <= char <= "9"
        or "A" <= char <= "Z"
        or "a" <= char <= "z"
    )


def _require_optional_response(
    value: object,
    field_name: str,
) -> LocalWorkerTurnResponse | None:
    if value is None:
        return None
    if not isinstance(value, LocalWorkerTurnResponse):
        raise TypeError(f"{field_name} must be LocalWorkerTurnResponse or None")
    return value


def _require_optional_disposition(
    value: object,
    field_name: str,
) -> LocalWorkerTurnDispositionRecord | None:
    if value is None:
        return None
    if not isinstance(value, LocalWorkerTurnDispositionRecord):
        raise TypeError(
            f"{field_name} must be LocalWorkerTurnDispositionRecord or None"
        )
    return value


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
