#!/usr/bin/env python
"""LM5P Ollama think/format diagnostic spike scaffold.

This script is intentionally offline for Task 1: it defines deterministic
schema, mode, and request-body construction helpers without making Ollama
calls. Later LM5P tasks can layer live probing on top of this contract.
"""

from __future__ import annotations

import argparse
import hashlib
import copy
import json
import sys
from collections.abc import Mapping
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
from rook.agent.local_worker_turn_response import (
    load_local_worker_turn_response_payload,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from lm5k_worker_probe import _SCENARIOS, build_probe_context

SCRIPT_SCHEMA = "rook.lm5p_ollama_think_format_spike:v1"
DEFAULT_MODELS = ("gemma4:12b-it-qat", "gemma4:12b")
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 3
DEFAULT_TEMPERATURE = 0
EXCERPT_CHARS = 500

_MODES = {
    "free_default": {"format": False, "think": "omitted"},
    "free_think_true": {"format": False, "think": True},
    "format_default": {"format": True, "think": "omitted"},
    "format_think_true": {"format": True, "think": True},
    "format_think_false": {"format": True, "think": False},
}

_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
}


def _response_union_schema() -> dict[str, Any]:
    def schema_prop() -> dict[str, str]:
        return {"const": "rook.local_worker_turn_response:v1"}

    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "action_id", "rationale", "input"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "action_request"},
                    "action_id": {"type": "string"},
                    "rationale": {"type": "string"},
                    "input": {"type": "object"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "question", "rationale"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "clarification_request"},
                    "question": {"type": "string"},
                    "rationale": {"type": ["string", "null"]},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "category", "reason"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "refusal"},
                    "category": {
                        "enum": [
                            "unsafe",
                            "insufficient_context",
                            "unsupported_action",
                            "out_of_scope",
                        ]
                    },
                    "reason": {"type": "string"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "message", "data"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "observation"},
                    "message": {"type": "string"},
                    "data": {"type": ["object", "null"]},
                },
            },
        ]
    }


def _build_request_body(
    model: str,
    messages: list[dict[str, Any]],
    mode_name: str,
    temperature: float,
) -> dict[str, Any]:
    try:
        mode = _MODES[mode_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P mode: {mode_name}") from exc

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if mode["format"]:
        body["format"] = copy.deepcopy(_response_union_schema())
    if mode["think"] != "omitted":
        body["think"] = mode["think"]
    return body


def _messages_for_scenario(scenario_name: str) -> list[dict[str, str]]:
    try:
        probe_scenario_name = _SCENARIO_MAP[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P scenario: {scenario_name}") from exc

    context = build_probe_context(_SCENARIOS[probe_scenario_name])
    request_payload = render_local_worker_turn_request_payload(context)
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    return [dict(message) for message in prompt_artifact["messages"]]


def _excerpt(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:EXCERPT_CHARS]


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _empty_result_fields() -> dict[str, Any]:
    return {
        "provider_status": "ok",
        "provider_json_valid": False,
        "content_json_valid": False,
        "content_is_mapping": False,
        "schema_literal": None,
        "lm5g_loadable": False,
        "response_kind": None,
        "message_content_excerpt": None,
        "message_content_sha256": None,
        "thinking_present": False,
        "thinking_chars": 0,
        "thinking_excerpt": None,
        "thinking_sha256": None,
        "prompt_eval_count": None,
        "eval_count": None,
        "total_duration": None,
        "load_duration": None,
        "prompt_eval_duration": None,
        "eval_duration": None,
        "done_reason": None,
        "failure_reason": None,
    }


def _classify_provider_text(
    provider_text: str,
    base_row: Mapping[str, Any],
) -> dict[str, Any]:
    row = {**base_row, **_empty_result_fields()}
    try:
        provider_payload = json.loads(provider_text)
    except json.JSONDecodeError as exc:
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = f"provider_json_invalid:{type(exc).__name__}"
        return row

    if not isinstance(provider_payload, Mapping):
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = "provider_json_invalid:not_mapping"
        return row

    row["provider_json_valid"] = True
    message = provider_payload.get("message")
    if not isinstance(message, Mapping):
        row["failure_reason"] = "message_missing"
        return row

    content = message.get("content")
    if isinstance(content, str):
        row["message_content_excerpt"] = _excerpt(content)
        row["message_content_sha256"] = _sha256_text(content)

    thinking = message.get("thinking")
    if isinstance(thinking, str) and thinking:
        row["thinking_present"] = True
        row["thinking_chars"] = len(thinking)
        row["thinking_excerpt"] = _excerpt(thinking)
        row["thinking_sha256"] = _sha256_text(thinking)

    for key in (
        "prompt_eval_count",
        "eval_count",
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
        "done_reason",
    ):
        row[key] = provider_payload.get(key)

    if not isinstance(content, str) or not content:
        row["failure_reason"] = "content_missing"
        return row

    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as exc:
        row["content_json_valid"] = False
        row["failure_reason"] = f"content_json_invalid:{type(exc).__name__}"
        return row

    row["content_json_valid"] = True
    row["content_is_mapping"] = isinstance(parsed_content, Mapping)
    if not isinstance(parsed_content, Mapping):
        row["failure_reason"] = "content_json_not_mapping"
        return row

    schema_literal = parsed_content.get("schema")
    row["schema_literal"] = schema_literal if isinstance(schema_literal, str) else None
    response_kind = parsed_content.get("kind")
    row["response_kind"] = response_kind if isinstance(response_kind, str) else None

    try:
        load_local_worker_turn_response_payload(parsed_content)
    except (TypeError, ValueError) as exc:
        row["failure_reason"] = f"lm5g_load_failed:{type(exc).__name__}"
        return row

    row["lm5g_loadable"] = True
    row["failure_reason"] = None
    return row


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5P Ollama think/format diagnostic spike scaffold."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", action="append", dest="models", default=None)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args(argv)
    if args.models is None:
        args.models = list(DEFAULT_MODELS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    print(
        "LM5P Ollama think/format spike scaffold: "
        f"schema={SCRIPT_SCHEMA} endpoint={args.endpoint} "
        f"models={','.join(args.models)} attempts={args.attempts}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
