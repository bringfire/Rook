#!/usr/bin/env python
"""Shared direct-Ollama two-pass worker publication helper."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rook.agent.local_worker_prompt_artifact import (  # noqa: E402
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_response import (  # noqa: E402
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)


STATUSES = (
    "pass1_provider_error",
    "pass1_decision_invalid",
    "pass2_provider_error",
    "pass2_lm5g_invalid",
    "pass2_invariant_violation",
    "published",
)

RESPONSE_KINDS = (
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
)

PASS1_DECISION_INSTRUCTION_VERSION = "lm5s.pass1_decision_instruction:v2"

_PASS1_DECISION_INSTRUCTION = """\
Return a small decision JSON object for this worker turn.

The object must contain kind. Choose the kind by these generic semantics:
- action_request: choose only when visible context is sufficient to author the
  required action input.
- clarification_request: choose when required information is missing.
- refusal: choose when the request is unsafe, unsupported, or out of scope.
- observation: choose only to report visible state or evidence.

Do not use observation to choose, suggest, imply, or carry an action.
Do not put action identity or action choice in observation.message or
observation.data.

Required fields per kind:
- action_request: action_id
- clarification_request: question
- refusal: category and reason
- observation: message

Optional fields: rationale, intent, action_input_intent, known_inputs,
data_intent.

Do not return a strict LM5 response envelope in this pass. This pass decides
only. The next pass will publish the chosen kind.
"""


@dataclass(frozen=True)
class TwoPassPublicationResult:
    row: dict[str, Any]
    response_payload: dict[str, Any] | None


def _empty_publication_row(*, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "status": None,
        "failure_reason": None,
        "pass1_provider_status": None,
        "pass1_kind": None,
        "pass1_action_id": None,
        "pass1_refusal_category": None,
        "pass1_decision_sha256": None,
        "pass1_content_excerpt": None,
        "pass1_content_sha256": None,
        "pass1_thinking_present": False,
        "pass1_thinking_chars": 0,
        "pass1_thinking_sha256": None,
        "pass1_prompt_eval_count": None,
        "pass1_eval_count": None,
        "pass2_provider_status": None,
        "pass2_schema_kind": None,
        "pass2_response_kind": None,
        "pass2_action_id": None,
        "pass2_refusal_category": None,
        "pass2_content_excerpt": None,
        "pass2_content_sha256": None,
        "pass2_prompt_eval_count": None,
        "pass2_eval_count": None,
        "kind_preserved": None,
        "action_id_preserved": None,
        "refusal_category_preserved": None,
        "lm5g_loadable": False,
        "pass1_observation_action_intent_anomaly": False,
        "pass1_observation_action_intent_reasons": [],
        "pass2_observation_action_intent_anomaly": False,
        "pass2_observation_action_intent_reasons": [],
        "observation_action_intent_anomaly": False,
        "observation_action_intent_reasons": [],
    }


def _excerpt(value: str | None, excerpt_chars: int) -> str | None:
    if value is None:
        return None
    return value[:excerpt_chars]


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _optional_string(decision: Mapping[str, Any], key: str) -> bool:
    return key not in decision or isinstance(decision[key], str)


def _optional_mapping_or_string(decision: Mapping[str, Any], key: str) -> bool:
    return (
        key not in decision
        or isinstance(decision[key], str)
        or isinstance(decision[key], Mapping)
    )


def _optional_mapping(decision: Mapping[str, Any], key: str) -> bool:
    return key not in decision or isinstance(decision[key], Mapping)


def _parse_pass1_decision(content: str) -> tuple[dict[str, Any] | None, str | None]:
    object_text = _extract_first_json_object(content)
    if object_text is None:
        return None, "pass1_no_json_object"

    try:
        parsed = json.loads(object_text)
    except (json.JSONDecodeError, RecursionError) as exc:
        return None, f"pass1_json_invalid:{type(exc).__name__}"

    if not isinstance(parsed, Mapping):
        return None, "pass1_decision_not_mapping"

    decision = dict(parsed)
    kind = decision.get("kind")
    if not isinstance(kind, str) or kind not in RESPONSE_KINDS:
        return None, "pass1_unknown_kind"

    if kind == "action_request" and not isinstance(decision.get("action_id"), str):
        return None, "pass1_missing_action_id"
    if kind == "clarification_request" and not isinstance(decision.get("question"), str):
        return None, "pass1_missing_question"
    if kind == "refusal":
        if not isinstance(decision.get("category"), str):
            return None, "pass1_missing_refusal_category"
        if not isinstance(decision.get("reason"), str):
            return None, "pass1_missing_refusal_reason"
    if kind == "observation" and not isinstance(decision.get("message"), str):
        return None, "pass1_missing_observation_message"

    if not _optional_string(decision, "rationale"):
        return None, "pass1_optional_rationale_type_invalid"
    if not _optional_string(decision, "intent"):
        return None, "pass1_optional_intent_type_invalid"
    if not _optional_mapping_or_string(decision, "action_input_intent"):
        return None, "pass1_optional_action_input_intent_type_invalid"
    if not _optional_mapping(decision, "known_inputs"):
        return None, "pass1_optional_known_inputs_type_invalid"
    if not _optional_mapping_or_string(decision, "data_intent"):
        return None, "pass1_optional_data_intent_type_invalid"

    return decision, None


def _json_value_contains_allowed_action_id(
    value: Any,
    allowed_action_ids: Collection[str],
    *,
    skip_action_id_value: bool = False,
) -> bool:
    if isinstance(value, str):
        return any(action_id in value for action_id in allowed_action_ids)

    if isinstance(value, Mapping):
        return any(
            _json_value_contains_allowed_action_id(
                item_value,
                allowed_action_ids,
                skip_action_id_value=False,
            )
            for item_key, item_value in value.items()
            if not (skip_action_id_value and item_key == "action_id")
        )

    if isinstance(value, (list, tuple)):
        return any(
            _json_value_contains_allowed_action_id(
                item,
                allowed_action_ids,
                skip_action_id_value=False,
            )
            for item in value
        )

    return False


def _observation_action_intent_reasons(
    *,
    payload: Mapping[str, Any],
    allowed_action_ids: Collection[str],
) -> tuple[str, ...]:
    if payload.get("kind") != "observation":
        return ()

    reasons: set[str] = set()
    data = payload.get("data")
    if isinstance(data, Mapping):
        action_id = data.get("action_id")
        if isinstance(action_id, str) and action_id in allowed_action_ids:
            reasons.add("observation_data_action_id_allowed")
    if data is not None and _json_value_contains_allowed_action_id(
        data,
        allowed_action_ids,
        skip_action_id_value=(
            isinstance(data, Mapping)
            and isinstance(data.get("action_id"), str)
            and data.get("action_id") in allowed_action_ids
        ),
    ):
        reasons.add("observation_data_mentions_allowed_action_id")

    data_intent = payload.get("data_intent")
    if data_intent is not None and _json_value_contains_allowed_action_id(
        data_intent,
        allowed_action_ids,
    ):
        reasons.add("observation_data_intent_mentions_allowed_action_id")

    message = payload.get("message")
    if isinstance(message, str) and any(
        action_id in message for action_id in allowed_action_ids
    ):
        reasons.add("observation_message_mentions_allowed_action_id")

    return tuple(sorted(reasons))


def _allowed_action_ids_from_request(request_payload: Mapping[str, Any]) -> tuple[str, ...]:
    context = request_payload.get("context")
    if not isinstance(context, Mapping):
        return ()

    allowed_actions = context.get("allowed_actions")
    if not isinstance(allowed_actions, list):
        return ()

    action_ids = {
        action.get("action_id")
        for action in allowed_actions
        if isinstance(action, Mapping)
        and isinstance(action.get("action_id"), str)
        and action.get("action_id")
    }
    return tuple(sorted(action_ids))


def _set_combined_observation_anomaly(row: dict[str, Any]) -> None:
    reasons = sorted(
        set(row["pass1_observation_action_intent_reasons"])
        | set(row["pass2_observation_action_intent_reasons"])
    )
    row["observation_action_intent_reasons"] = reasons
    row["observation_action_intent_anomaly"] = bool(reasons)


def _schema_const_prop() -> dict[str, str]:
    return {"const": LOCAL_WORKER_TURN_RESPONSE_SCHEMA}


def _single_kind_response_schema(decision: Mapping[str, Any]) -> dict[str, Any]:
    kind = decision["kind"]
    base: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": _schema_const_prop(),
            "kind": {"const": kind},
        },
    }

    if kind == "action_request":
        base["required"] = ["schema", "kind", "action_id", "rationale", "input"]
        base["properties"].update(
            {
                "action_id": {"const": decision["action_id"]},
                "rationale": {"type": "string"},
                "input": {"type": "object"},
            }
        )
        return base

    if kind == "clarification_request":
        base["required"] = ["schema", "kind", "question", "rationale"]
        base["properties"].update(
            {
                "question": {"type": "string"},
                "rationale": {"type": ["string", "null"]},
            }
        )
        return base

    if kind == "refusal":
        base["required"] = ["schema", "kind", "category", "reason"]
        base["properties"].update(
            {
                "category": {"const": decision["category"]},
                "reason": {"type": "string"},
            }
        )
        return base

    if kind == "observation":
        base["required"] = ["schema", "kind", "message", "data"]
        base["properties"].update(
            {
                "message": {"type": "string"},
                "data": {"type": ["object", "null"]},
            }
        )
        return base

    raise ValueError(f"unknown decision kind for schema: {kind}")


_FORMATTER_SYSTEM_TEXT = """\
You are formatting an already-made Rook worker decision.
Do not change the decision kind.
Do not change action_id.
Return exactly one JSON object matching the provided single-kind schema.
Use the original request envelope only to fill fields needed by the chosen decision.
If required information is missing, preserve the chosen kind and express that
within the chosen envelope where possible; do not switch kinds.
"""


def _formatter_messages(
    request_payload: Mapping[str, Any],
    decision: Mapping[str, Any],
    single_kind_schema: Mapping[str, Any],
) -> list[dict[str, str]]:
    payload = {
        "request_envelope": request_payload,
        "decision": decision,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": decision["kind"],
        "single_kind_schema": single_kind_schema,
    }
    return [
        {"role": "system", "content": _FORMATTER_SYSTEM_TEXT},
        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
    ]


def _build_pass1_body(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": True,
        "options": {"temperature": temperature},
    }


def _build_pass2_body(
    *,
    model: str,
    request_payload: Mapping[str, Any],
    decision: Mapping[str, Any],
    single_kind_schema: Mapping[str, Any],
    temperature: float,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": _formatter_messages(request_payload, decision, single_kind_schema),
        "stream": False,
        "format": copy.deepcopy(single_kind_schema),
        "think": False,
        "options": {"temperature": temperature},
    }


def _post_ollama_chat(endpoint: str, body: dict[str, Any], timeout_s: float) -> str:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8")


def _provider_message_fields(
    provider_text: str,
    *,
    prefix: str,
    excerpt_chars: int,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        provider_payload = json.loads(provider_text)
    except (json.JSONDecodeError, RecursionError) as exc:
        return None, f"{prefix}_provider_json_invalid:{type(exc).__name__}"

    if not isinstance(provider_payload, Mapping):
        return None, f"{prefix}_provider_json_invalid:not_mapping"

    message = provider_payload.get("message")
    if not isinstance(message, Mapping):
        return None, f"{prefix}_message_missing"

    content = message.get("content")
    if not isinstance(content, str) or not content:
        return None, f"{prefix}_content_missing"

    thinking = message.get("thinking")
    fields = {
        "content": content,
        "content_excerpt": _excerpt(content, excerpt_chars),
        "content_sha256": _sha256_text(content),
        "thinking_present": isinstance(thinking, str) and bool(thinking),
        "thinking_chars": len(thinking) if isinstance(thinking, str) else 0,
        "thinking_sha256": _sha256_text(thinking) if isinstance(thinking, str) else None,
        "prompt_eval_count": provider_payload.get("prompt_eval_count"),
        "eval_count": provider_payload.get("eval_count"),
    }
    return fields, None


def _pass1_messages_from_request(
    request_payload: Mapping[str, Any],
) -> list[dict[str, str]]:
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    messages = [dict(message) for message in prompt_artifact["messages"]]
    messages.append({"role": "user", "content": _PASS1_DECISION_INSTRUCTION})
    return messages


def _mark_pass1_success(row: dict[str, Any], fields: Mapping[str, Any]) -> None:
    row["pass1_provider_status"] = "ok"
    row["pass1_content_excerpt"] = fields["content_excerpt"]
    row["pass1_content_sha256"] = fields["content_sha256"]
    row["pass1_thinking_present"] = fields["thinking_present"]
    row["pass1_thinking_chars"] = fields["thinking_chars"]
    row["pass1_thinking_sha256"] = fields["thinking_sha256"]
    row["pass1_prompt_eval_count"] = fields["prompt_eval_count"]
    row["pass1_eval_count"] = fields["eval_count"]


def _mark_pass2_success(row: dict[str, Any], fields: Mapping[str, Any]) -> None:
    row["pass2_provider_status"] = "ok"
    row["pass2_content_excerpt"] = fields["content_excerpt"]
    row["pass2_content_sha256"] = fields["content_sha256"]
    row["pass2_prompt_eval_count"] = fields["prompt_eval_count"]
    row["pass2_eval_count"] = fields["eval_count"]


def _result(
    row: dict[str, Any],
    response_payload: dict[str, Any] | None = None,
) -> TwoPassPublicationResult:
    return TwoPassPublicationResult(row=row, response_payload=response_payload)


def run_two_pass_worker_publication(
    request_payload: Mapping[str, Any],
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    post_chat: Callable[[str, dict[str, Any], float], str] = _post_ollama_chat,
) -> TwoPassPublicationResult:
    row = _empty_publication_row(model=model)
    pass1_body = _build_pass1_body(
        model=model,
        messages=_pass1_messages_from_request(request_payload),
        temperature=temperature,
    )

    try:
        pass1_text = post_chat(endpoint, pass1_body, timeout_s)
    except urllib.error.HTTPError as exc:
        row["status"] = "pass1_provider_error"
        row["failure_reason"] = f"pass1_http_error:{exc.code}"
        row["pass1_provider_status"] = "error"
        return _result(row)
    except Exception as exc:
        row["status"] = "pass1_provider_error"
        row["failure_reason"] = f"pass1_provider_error:{type(exc).__name__}"
        row["pass1_provider_status"] = "error"
        return _result(row)

    pass1_fields, pass1_failure = _provider_message_fields(
        pass1_text,
        prefix="pass1",
        excerpt_chars=excerpt_chars,
    )
    if pass1_fields is None:
        row["status"] = "pass1_decision_invalid"
        row["failure_reason"] = pass1_failure
        row["pass1_provider_status"] = "ok"
        return _result(row)

    _mark_pass1_success(row, pass1_fields)
    decision, decision_failure = _parse_pass1_decision(pass1_fields["content"])
    if decision is None:
        row["status"] = "pass1_decision_invalid"
        row["failure_reason"] = decision_failure
        return _result(row)

    decision_text = json.dumps(decision, sort_keys=True)
    row["pass1_decision_sha256"] = _sha256_text(decision_text)
    row["pass1_kind"] = decision["kind"]
    row["pass1_action_id"] = decision.get("action_id")
    row["pass1_refusal_category"] = decision.get("category")
    allowed_action_ids = _allowed_action_ids_from_request(request_payload)
    pass1_observation_reasons = list(
        _observation_action_intent_reasons(
            payload=decision,
            allowed_action_ids=allowed_action_ids,
        )
    )
    row["pass1_observation_action_intent_reasons"] = pass1_observation_reasons
    row["pass1_observation_action_intent_anomaly"] = bool(pass1_observation_reasons)
    _set_combined_observation_anomaly(row)

    single_kind_schema = _single_kind_response_schema(decision)
    row["pass2_schema_kind"] = decision["kind"]
    pass2_body = _build_pass2_body(
        model=model,
        request_payload=request_payload,
        decision=decision,
        single_kind_schema=single_kind_schema,
        temperature=temperature,
    )

    try:
        pass2_text = post_chat(endpoint, pass2_body, timeout_s)
    except urllib.error.HTTPError as exc:
        row["status"] = "pass2_provider_error"
        row["failure_reason"] = f"pass2_http_error:{exc.code}"
        row["pass2_provider_status"] = "error"
        return _result(row)
    except Exception as exc:
        row["status"] = "pass2_provider_error"
        row["failure_reason"] = f"pass2_provider_error:{type(exc).__name__}"
        row["pass2_provider_status"] = "error"
        return _result(row)

    pass2_fields, pass2_failure = _provider_message_fields(
        pass2_text,
        prefix="pass2",
        excerpt_chars=excerpt_chars,
    )
    if pass2_fields is None:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = pass2_failure
        row["pass2_provider_status"] = "ok"
        return _result(row)

    _mark_pass2_success(row, pass2_fields)
    try:
        parsed_response = json.loads(pass2_fields["content"])
    except (json.JSONDecodeError, RecursionError) as exc:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = f"pass2_content_json_invalid:{type(exc).__name__}"
        return _result(row)

    if not isinstance(parsed_response, Mapping):
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = "pass2_content_not_mapping"
        return _result(row)

    parsed_response = dict(parsed_response)
    row["pass2_response_kind"] = parsed_response.get("kind")
    row["pass2_action_id"] = parsed_response.get("action_id")
    row["pass2_refusal_category"] = parsed_response.get("category")

    try:
        load_local_worker_turn_response_payload(parsed_response)
    except (TypeError, ValueError) as exc:
        row["status"] = "pass2_lm5g_invalid"
        row["failure_reason"] = f"pass2_lm5g_load_failed:{type(exc).__name__}"
        return _result(row)

    pass2_observation_reasons = list(
        _observation_action_intent_reasons(
            payload=parsed_response,
            allowed_action_ids=allowed_action_ids,
        )
    )
    row["pass2_observation_action_intent_reasons"] = pass2_observation_reasons
    row["pass2_observation_action_intent_anomaly"] = bool(pass2_observation_reasons)
    _set_combined_observation_anomaly(row)
    row["lm5g_loadable"] = True
    row["kind_preserved"] = row["pass2_response_kind"] == row["pass1_kind"]
    row["action_id_preserved"] = (
        row["pass2_action_id"] == row["pass1_action_id"]
        if row["pass1_kind"] == "action_request"
        else None
    )
    row["refusal_category_preserved"] = (
        row["pass2_refusal_category"] == row["pass1_refusal_category"]
        if row["pass1_kind"] == "refusal"
        else None
    )

    if row["kind_preserved"] is not True:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_kind_changed"
        return _result(row)
    if row["action_id_preserved"] is False:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_action_id_changed"
        return _result(row)
    if row["refusal_category_preserved"] is False:
        row["status"] = "pass2_invariant_violation"
        row["failure_reason"] = "pass2_refusal_category_changed"
        return _result(row)

    row["status"] = "published"
    row["failure_reason"] = None
    return _result(row, response_payload=parsed_response)


__all__ = (
    "PASS1_DECISION_INSTRUCTION_VERSION",
    "STATUSES",
    "TwoPassPublicationResult",
    "run_two_pass_worker_publication",
)
