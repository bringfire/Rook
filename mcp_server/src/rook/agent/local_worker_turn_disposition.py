"""LM5C local-worker response disposition gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerResponseKind,
    validate_local_worker_turn_response,
)

WorkerResponseDisposition = Literal[
    "blocked",
    "candidate_action_request",
    "clarification_needed",
    "refusal_recorded",
    "observation_recorded",
]

__all__ = (
    "WorkerResponseDisposition",
    "LocalWorkerTurnDispositionRecord",
    "dispose_local_worker_turn_response",
)

_DISPOSITIONS = frozenset(
    {
        "blocked",
        "candidate_action_request",
        "clarification_needed",
        "refusal_recorded",
        "observation_recorded",
    }
)
_NON_ACTION_DISPOSITION_BY_KIND = {
    "clarification_request": "clarification_needed",
    "refusal": "refusal_recorded",
    "observation": "observation_recorded",
}


@dataclass(frozen=True)
class LocalWorkerTurnDispositionRecord:
    disposition: WorkerResponseDisposition
    attempt: LocalWorkerTurnAttemptRecord
    response_kind: WorkerResponseKind | None
    action_id: str | None
    reason: str

    def __post_init__(self) -> None:
        _require_attempt(self.attempt, "attempt")
        disposition = _require_str(self.disposition, "disposition")
        _require_optional_str(self.response_kind, "response_kind")
        _require_optional_str(self.action_id, "action_id")
        reason = _require_non_empty_str(self.reason, "reason")

        if disposition not in _DISPOSITIONS:
            raise ValueError(f"unknown disposition: {disposition!r}")
        if self.response_kind != self.attempt.response_kind:
            raise ValueError("response_kind must match attempt.response_kind")
        if self.action_id != self.attempt.action_id:
            raise ValueError("action_id must match attempt.action_id")

        _validate_disposition_coherence(
            disposition=disposition,
            attempt=self.attempt,
            reason=reason,
        )


def dispose_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnDispositionRecord:
    attempt = validate_local_worker_turn_response(context, response)
    return _disposition_from_attempt(attempt)


def _disposition_from_attempt(
    attempt: LocalWorkerTurnAttemptRecord,
) -> LocalWorkerTurnDispositionRecord:
    _require_attempt(attempt, "attempt")
    if attempt.valid is False:
        return LocalWorkerTurnDispositionRecord(
            disposition="blocked",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"blocked:{attempt.reason}",
        )

    if attempt.response_kind == "action_request":
        action_id = _valid_action_id_from_attempt(attempt)
        return LocalWorkerTurnDispositionRecord(
            disposition="candidate_action_request",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"candidate_action_request:{action_id}",
        )
    if attempt.response_kind == "clarification_request":
        return _non_action_disposition(
            attempt,
            disposition="clarification_needed",
            reason="clarification_needed",
        )
    if attempt.response_kind == "refusal":
        return _non_action_disposition(
            attempt,
            disposition="refusal_recorded",
            reason="refusal_recorded",
        )
    if attempt.response_kind == "observation":
        return _non_action_disposition(
            attempt,
            disposition="observation_recorded",
            reason="observation_recorded",
        )

    raise ValueError(f"unsupported valid response_kind: {attempt.response_kind!r}")


def _non_action_disposition(
    attempt: LocalWorkerTurnAttemptRecord,
    *,
    disposition: WorkerResponseDisposition,
    reason: str,
) -> LocalWorkerTurnDispositionRecord:
    return LocalWorkerTurnDispositionRecord(
        disposition=disposition,
        attempt=attempt,
        response_kind=attempt.response_kind,
        action_id=attempt.action_id,
        reason=reason,
    )


def _validate_disposition_coherence(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if attempt.valid is False:
        _validate_blocked_disposition(
            disposition=disposition,
            attempt=attempt,
            reason=reason,
        )
        return
    if attempt.response_kind == "action_request":
        _validate_action_disposition(
            disposition=disposition,
            attempt=attempt,
            reason=reason,
        )
        return

    _validate_non_action_disposition(
        disposition=disposition,
        attempt=attempt,
        reason=reason,
    )


def _validate_blocked_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if disposition != "blocked":
        raise ValueError("invalid attempts require blocked disposition")
    if reason != f"blocked:{attempt.reason}":
        raise ValueError("blocked disposition reason must preserve attempt reason")


def _validate_action_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if disposition != "candidate_action_request":
        raise ValueError("valid action attempts require candidate_action_request")
    action_id = _valid_action_id_from_attempt(attempt)
    if reason != f"candidate_action_request:{action_id}":
        raise ValueError("candidate action reason must include action_id")


def _validate_non_action_disposition(
    *,
    disposition: str,
    attempt: LocalWorkerTurnAttemptRecord,
    reason: str,
) -> None:
    if attempt.action_id is not None:
        raise ValueError("valid non-action dispositions require action_id to be None")

    expected_disposition = _NON_ACTION_DISPOSITION_BY_KIND.get(attempt.response_kind)
    if expected_disposition is None:
        raise ValueError(f"unsupported valid response_kind: {attempt.response_kind!r}")
    if disposition != expected_disposition:
        raise ValueError("disposition does not match attempt.response_kind")
    if reason != expected_disposition:
        raise ValueError("reason does not match attempt.response_kind")


def _valid_action_id_from_attempt(attempt: LocalWorkerTurnAttemptRecord) -> str:
    if not isinstance(attempt.action_id, str) or attempt.action_id == "":
        raise ValueError("valid action attempts require non-empty action_id")
    return attempt.action_id


def _require_attempt(
    value: object,
    field_name: str,
) -> LocalWorkerTurnAttemptRecord:
    if not isinstance(value, LocalWorkerTurnAttemptRecord):
        raise TypeError(f"{field_name} must be LocalWorkerTurnAttemptRecord")
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
