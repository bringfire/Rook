"""LM5I local-worker request envelope renderer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
)

LOCAL_WORKER_TURN_REQUEST_SCHEMA = "rook.local_worker_turn_request:v1"

__all__ = (
    "LOCAL_WORKER_TURN_REQUEST_SCHEMA",
    "render_local_worker_turn_request_payload",
)

_RESPONSE_KINDS = (
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
)
_RESPONSE_FIELD_SETS = {
    "action_request": ("schema", "kind", "action_id", "rationale", "input"),
    "clarification_request": ("schema", "kind", "question", "rationale"),
    "refusal": ("schema", "kind", "category", "reason"),
    "observation": ("schema", "kind", "message", "data"),
}
_REQUIRED_NULLABLE_FIELDS = {
    "clarification_request": ("rationale",),
    "observation": ("data",),
}
_REFUSAL_CATEGORIES = (
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
)


def render_local_worker_turn_request_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")

    context_payload = render_local_worker_turn_context_payload(context)
    return {
        "schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
        "context": context_payload,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "response_contract": _render_response_contract(),
    }


def _render_response_contract() -> dict[str, Any]:
    return {
        "kinds": list(_RESPONSE_KINDS),
        "field_sets": {
            kind: list(fields) for kind, fields in _RESPONSE_FIELD_SETS.items()
        },
        "required_nullable_fields": {
            kind: list(fields) for kind, fields in _REQUIRED_NULLABLE_FIELDS.items()
        },
        "refusal_categories": list(_REFUSAL_CATEGORIES),
    }
