#!/usr/bin/env python
"""LM5O structured-output spike for LiteLLM -> Ollama -> Gemma.

This is a manual feasibility probe, not CI. It asks whether Ollama structured
output can constrain the LM5 response envelope while preserving response-kind
choice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from typing import Any

import litellm

from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)


ABSENT_PROMPT = """You are a bounded local worker.

Return exactly one JSON object matching the provided schema. The visible context
does not include enough repair evidence to author an action input responsibly.
Choose the valid response kind that best fits restraint.
"""


PRESENT_PROMPT = """You are a bounded local worker.

Return exactly one JSON object matching the provided schema. The visible context
includes bounded repair evidence:
- allowed action id: draft_repair_params
- current code: A = DefinitelyMissingSymbol;
- recommended mode: body
- failure count: 1
Choose the valid response kind that best fits this evidence.
"""


def _response_union_schema() -> dict[str, Any]:
    def schema_prop() -> dict[str, str]:
        return {"const": LOCAL_WORKER_TURN_RESPONSE_SCHEMA}

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


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(
            f"provider response missing choices/message: {type(exc).__name__}"
        ) from exc
    if not isinstance(content, str) or not content:
        raise RuntimeError("provider returned no text content")
    return content


def _run_case(
    *,
    label: str,
    model: str,
    prompt: str,
    timeout_s: float,
) -> str:
    started = time.perf_counter()
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout=timeout_s,
        format=_response_union_schema(),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    raw = _extract_content(response)
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise RuntimeError(f"{label}: parsed output is not a mapping")
    loaded = load_local_worker_turn_response_payload(parsed)
    kind = parsed.get("kind")
    print(f"{label}: provider_call=succeeded latency_ms={elapsed_ms:.1f}")
    print(f"{label}: raw_content=received chars={len(raw)}")
    print(f"{label}: json=parsed")
    print(f"{label}: lm5g=loaded kind={kind}")
    if label == "absent" and kind == "action_request":
        raise RuntimeError("absent-style prompt loaded as action_request")
    return type(loaded.payload).__name__


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5O LiteLLM/Ollama structured-output feasibility spike."
    )
    parser.add_argument(
        "--model",
        default="ollama_chat/gemma4:12b-it-qat",
        help="LiteLLM model id; expected to be an Ollama/Gemma local model.",
    )
    parser.add_argument("--timeout-s", type=float, default=120.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        absent_payload = _run_case(
            label="absent",
            model=args.model,
            prompt=ABSENT_PROMPT,
            timeout_s=args.timeout_s,
        )
        present_payload = _run_case(
            label="present",
            model=args.model,
            prompt=PRESENT_PROMPT,
            timeout_s=args.timeout_s,
        )
    except Exception as exc:
        print(f"LM5O structured-output spike failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        "LM5O structured-output spike complete: "
        f"absent_payload={absent_payload} present_payload={present_payload}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
