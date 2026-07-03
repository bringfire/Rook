"""LM5J local-worker prompt artifact renderer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from rook.agent.local_worker_turn_request import LOCAL_WORKER_TURN_REQUEST_SCHEMA

LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA = "rook.local_worker_prompt_artifact:v1"
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5m.prompt_text:v2"

__all__ = (
    "LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA",
    "LOCAL_WORKER_PROMPT_TEXT_VERSION",
    "render_local_worker_prompt_artifact",
)

_TOP_LEVEL_KEYS = frozenset(
    {"schema", "context", "response_schema", "response_contract"}
)
_CONTRACT_KEYS = frozenset(
    {"kinds", "field_sets", "required_nullable_fields", "refusal_categories"}
)

_INSTRUCTION_TEXT = (
    "You are a bounded Rook worker resolving exactly one workflow node.\n"
    "The user content is a request envelope as JSON: the workflow context\n"
    "you may rely on and the contract your reply must follow.\n"
    "For an allowed action, its input_schema describes the shape of the\n"
    "action input object you may author from visible context. It is not a list of hidden values\n"
    "Rook is withholding. If visible context is sufficient,\n"
    "author that input object yourself. If not, use\n"
    "clarification or refusal.\n"
    "Return exactly one JSON object matching the response contract. Do not use markdown fences,\n"
    "backticks, language labels, or explanatory text\n"
    "before or after the JSON object.\n"
    "The object must follow exactly one of the allowed reply envelopes\n"
    "listed below, using exactly the listed entries."
)


def render_local_worker_prompt_artifact(
    request_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = _require_request_envelope(request_payload)
    contract = _require_response_contract(payload["response_contract"])
    response_schema = payload["response_schema"]
    if not isinstance(response_schema, str) or not response_schema:
        raise ValueError(
            "request payload response_schema must be a non-empty string"
        )
    system_text = (
        _INSTRUCTION_TEXT + "\n\n" + _render_contract_text(response_schema, contract)
    )
    user_text = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return {
        "schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    }


def _require_request_envelope(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("request payload must be a mapping")
    for key in value.keys():
        if not isinstance(key, str):
            raise TypeError("request payload keys must be strings")
    if set(value.keys()) != _TOP_LEVEL_KEYS:
        raise ValueError(
            f"request payload keys must be exactly {sorted(_TOP_LEVEL_KEYS)!r}"
        )
    schema = value["schema"]
    if not isinstance(schema, str):
        raise TypeError("request payload schema must be a string")
    if schema != LOCAL_WORKER_TURN_REQUEST_SCHEMA:
        raise ValueError(f"unsupported request payload schema: {schema!r}")
    return value


def _require_response_contract(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("response_contract must be a mapping")
    if set(value.keys()) != _CONTRACT_KEYS:
        raise ValueError(
            f"response_contract keys must be exactly {sorted(_CONTRACT_KEYS)!r}"
        )
    kinds = _require_str_sequence(value["kinds"], "response_contract kinds")
    field_sets = value["field_sets"]
    if not isinstance(field_sets, Mapping):
        raise TypeError("response_contract field_sets must be a mapping")
    if set(field_sets.keys()) != set(kinds):
        raise ValueError(
            "response_contract field_sets keys must exactly cover kinds"
        )
    for kind in kinds:
        _require_str_sequence(
            field_sets[kind], f"response_contract field_sets[{kind!r}]"
        )
    nullable = value["required_nullable_fields"]
    if not isinstance(nullable, Mapping):
        raise TypeError(
            "response_contract required_nullable_fields must be a mapping"
        )
    for kind, fields in nullable.items():
        if not isinstance(kind, str) or kind not in kinds:
            raise ValueError(
                "response_contract required_nullable_fields keys must be kinds"
            )
        _require_str_sequence(
            fields, f"response_contract required_nullable_fields[{kind!r}]"
        )
    _require_str_sequence(
        value["refusal_categories"], "response_contract refusal_categories"
    )
    return value


def _require_str_sequence(value: object, context: str) -> Sequence[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{context} must be a sequence of strings")
    if not value:
        raise ValueError(f"{context} must be non-empty")
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{context} entries must be non-empty strings")
    return value


def _render_contract_text(
    response_schema: str, contract: Mapping[str, Any]
) -> str:
    kinds = contract["kinds"]
    lines = [
        "Declared reply schema value: " + response_schema,
        "Allowed reply kinds: " + ", ".join(kinds),
    ]
    for kind in kinds:
        lines.append(
            "Fields for " + kind + ": " + ", ".join(contract["field_sets"][kind])
        )
    nullable = contract["required_nullable_fields"]
    for kind in kinds:
        if kind in nullable:
            lines.append(
                "Required but nullable for "
                + kind
                + ": "
                + ", ".join(nullable[kind])
            )
    lines.append(
        "Refusal categories: " + ", ".join(contract["refusal_categories"])
    )
    return "\n".join(lines)
