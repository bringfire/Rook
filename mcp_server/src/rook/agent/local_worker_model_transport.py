"""LM5K LiteLLM-backed local worker transport (implements LM5J's protocol)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import litellm

from rook.agent.local_worker_adapter import TransportError
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
        timeout_s: float = 120.0,
    ) -> None:
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        self.model = model
        self.profile_api_base = profile_api_base
        self.generation_params = dict(generation_params or {})
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
