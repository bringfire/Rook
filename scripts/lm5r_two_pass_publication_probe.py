#!/usr/bin/env python
"""LM5R direct Ollama two-pass worker publication probe.

Manual live diagnostic only. It renders real LM5N request envelopes, asks
Ollama/Gemma for a free worker decision, then asks the same model to publish
that decision through a single-kind LM5 response schema.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rook.agent.local_worker_prompt_artifact import (
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)
from lm5k_worker_probe import _SCENARIOS, build_probe_context


SCRIPT_SCHEMA = "rook.lm5r_two_pass_publication_probe:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 5
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
EXCERPT_CHARS = 500

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

_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
}

_PASS1_DECISION_INSTRUCTION = """\
Return a small decision JSON object for this worker turn.

The object must contain kind. Required per kind:
- action_request: action_id
- clarification_request: question
- refusal: category and reason
- observation: message

Optional fields: rationale, intent, action_input_intent, known_inputs,
data_intent.

Do not return a strict LM5 response envelope in this pass. This pass decides
only. The next pass will publish the chosen kind.
"""


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5R two-pass worker publication probe."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        choices=SCENARIO_NAMES,
        default=None,
    )
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument(
        "--excerpt-chars",
        type=_positive_int,
        default=EXCERPT_CHARS,
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    if args.scenarios is None:
        args.scenarios = list(SCENARIO_NAMES)
    return args


def _pass1_messages_for_scenario(
    scenario_name: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    try:
        probe_scenario_name = _SCENARIO_MAP[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5R scenario: {scenario_name}") from exc

    context = build_probe_context(_SCENARIOS[probe_scenario_name])
    request_payload = render_local_worker_turn_request_payload(context)
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    messages = [dict(message) for message in prompt_artifact["messages"]]
    messages.append({"role": "user", "content": _PASS1_DECISION_INSTRUCTION})
    return messages, request_payload


def _excerpt(value: str | None, excerpt_chars: int = EXCERPT_CHARS) -> str | None:
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


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
