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
from collections import Counter
from collections.abc import Mapping
from typing import Any

import litellm

from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)

UNION_KINDS = {
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
}


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
    attempts: int,
    temperature: float | None,
) -> Counter[str]:
    kinds: Counter[str] = Counter()
    for index in range(attempts):
        kind = _run_attempt(
            label=label,
            index=index,
            model=model,
            prompt=prompt,
            timeout_s=timeout_s,
            temperature=temperature,
        )
        kinds[kind] += 1
    print(f"{label}: kind_counts={dict(kinds)}")
    return kinds


def _run_attempt(
    *,
    label: str,
    index: int,
    model: str,
    prompt: str,
    timeout_s: float,
    temperature: float | None,
) -> str:
    started = time.perf_counter()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "timeout": timeout_s,
        "format": _response_union_schema(),
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = litellm.completion(**kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    raw = _extract_content(response)
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise RuntimeError(f"{label}[{index}]: parsed output is not a mapping")
    if parsed.get("schema") != LOCAL_WORKER_TURN_RESPONSE_SCHEMA:
        raise RuntimeError(
            f"{label}[{index}]: schema field is not the LM5 response schema"
        )
    kind = parsed.get("kind")
    if kind not in UNION_KINDS:
        raise RuntimeError(f"{label}[{index}]: unknown response kind {kind!r}")
    loaded = load_local_worker_turn_response_payload(parsed)
    print(f"{label}[{index}]: provider_call=succeeded latency_ms={elapsed_ms:.1f}")
    print(f"{label}[{index}]: raw_content=received chars={len(raw)}")
    print(f"{label}[{index}]: json=parsed")
    print(f"{label}[{index}]: schema=literal")
    print(f"{label}[{index}]: lm5g=loaded kind={kind}")
    return kind


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
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if args.attempts <= 0:
        print("LM5O structured-output spike failed: attempts must be positive")
        return 1
    try:
        absent_kinds = _run_case(
            label="absent",
            model=args.model,
            prompt=ABSENT_PROMPT,
            timeout_s=args.timeout_s,
            attempts=args.attempts,
            temperature=args.temperature,
        )
        present_kinds = _run_case(
            label="present",
            model=args.model,
            prompt=PRESENT_PROMPT,
            timeout_s=args.timeout_s,
            attempts=args.attempts,
            temperature=args.temperature,
        )
    except Exception as exc:
        print(f"LM5O structured-output spike failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        "LM5O structured-output spike complete: "
        f"absent_kind_counts={dict(absent_kinds)} "
        f"present_kind_counts={dict(present_kinds)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
