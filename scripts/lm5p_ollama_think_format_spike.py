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


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5P Ollama think/format diagnostic spike scaffold."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", action="append", default=list(DEFAULT_MODELS))
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    print(
        "LM5P Ollama think/format spike scaffold: "
        f"schema={SCRIPT_SCHEMA} endpoint={args.endpoint} "
        f"models={','.join(args.model)} attempts={args.attempts}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
