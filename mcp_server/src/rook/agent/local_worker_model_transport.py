"""LM5K LiteLLM-backed local worker transport (implements LM5J's protocol)."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import litellm

from rook.agent.local_worker_adapter import TransportError
from rook.agent.local_worker_turn_response import LOCAL_WORKER_TURN_RESPONSE_SCHEMA
from rook.agent.model_profiles import api_base_for_model

__all__ = (
    "LiteLLMWorkerTransport",
    "TransportCallInfo",
)


@dataclass(frozen=True)
class TransportCallInfo:
    model: str
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None


def _copy_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    "structured_response_schema values must be JSON-shaped"
                )
            copied[key] = _copy_json_value(item)
        return copied
    if isinstance(value, (list, tuple)):
        return [_copy_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("structured_response_schema values must be JSON-shaped")


def _local_worker_response_union_schema() -> dict[str, Any]:
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


class LiteLLMWorkerTransport:
    """Sync LocalWorkerTransport over litellm.completion.

    Provider/LiteLLM exceptions propagate unwrapped (the LM5J adapter
    classifies them as transport_error:unexpected:<ClassName>).
    TransportError is raised only for transport-detected conditions.
    Telemetry is best-effort and reset at the top of every send.
    """

    def __init__(
        self,
        model: str,
        profile_api_base: str | None = None,
        generation_params: Mapping[str, Any] | None = None,
        structured_response_schema: Mapping[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        if (
            structured_response_schema is not None
            and not isinstance(structured_response_schema, Mapping)
        ):
            raise TypeError("structured_response_schema must be a mapping")
        self.model = model
        self.profile_api_base = profile_api_base
        self.generation_params = dict(generation_params or {})
        if "format" in self.generation_params and structured_response_schema is not None:
            raise TypeError(
                "generation_params must not include format when "
                "structured_response_schema is set"
            )
        self.structured_response_schema = (
            _copy_json_value(structured_response_schema)
            if structured_response_schema is not None
            else None
        )
        self.timeout_s = timeout_s
        self.last_call_info: TransportCallInfo | None = None
        self.last_raw_output: str | None = None

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.last_call_info = None
        self.last_raw_output = None
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(m) for m in prompt_artifact["messages"]],
            "timeout": self.timeout_s,
        }
        kwargs.update(self.generation_params)
        if self.structured_response_schema is not None:
            kwargs["format"] = _copy_json_value(self.structured_response_schema)
        api_base = api_base_for_model(self.model, self.profile_api_base)
        if api_base:
            kwargs["api_base"] = api_base
        started = time.perf_counter()
        response = litellm.completion(**kwargs)
        latency_ms = (time.perf_counter() - started) * 1000.0
        content = _extract_content(response)
        self.last_raw_output = content
        self.last_call_info = _best_effort_call_info(
            self.model, latency_ms, response
        )
        return content


def _extract_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise TransportError(
            f"provider response missing choices/message: {type(exc).__name__}"
        ) from exc
    if not isinstance(content, str):
        raise TransportError("provider returned no text content")
    return content


def _best_effort_call_info(
    model: str, latency_ms: float, response: Any
) -> TransportCallInfo:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    try:
        usage = getattr(response, "usage", None)
        if usage is not None:
            pt = getattr(usage, "prompt_tokens", None)
            ct = getattr(usage, "completion_tokens", None)
            prompt_tokens = pt if isinstance(pt, int) else None
            completion_tokens = ct if isinstance(ct, int) else None
    except Exception:
        prompt_tokens = None
        completion_tokens = None
    try:
        cost = litellm.completion_cost(completion_response=response)
        cost_usd = float(cost) if cost is not None else None
    except Exception:
        cost_usd = None
    return TransportCallInfo(
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
