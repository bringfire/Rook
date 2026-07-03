#!/usr/bin/env python
"""LM5P Ollama think/format diagnostic spike scaffold.

This script is intentionally offline for Task 1: it defines deterministic
schema, mode, and request-body construction helpers without making Ollama
calls. Later LM5P tasks can layer live probing on top of this contract.
"""

from __future__ import annotations

import argparse
import copy
import sys
from typing import Any

from rook.agent.local_worker_prompt_artifact import (
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from scripts.lm5k_worker_probe import _SCENARIOS, build_probe_context

SCRIPT_SCHEMA = "rook.lm5p_ollama_think_format_spike:v1"
DEFAULT_MODELS = ("gemma4:12b-it-qat", "gemma4:12b")
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 3
DEFAULT_TEMPERATURE = 0
EXCERPT_CHARS = 2000

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
