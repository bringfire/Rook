"""Runtime health checks for the Rhino-owned chat service."""

from __future__ import annotations

import logging
import os
import asyncio
from typing import Any

from ...bridge import call_rhino
from ...providers.vertex_auth import (
    VertexAuthError,
    VertexStore,
    vertex_gemini_model_name,
)

logger = logging.getLogger(__name__)


def _provider_key_state() -> dict[str, bool]:
    return {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.environ.get("OPENROUTER_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
    }


def _effective_default_model() -> str:
    """Resolve the model a default chat turn would use (worker role).

    Used only when no explicit active model is available (e.g. the generic
    health endpoint).  Mirrors resolve_model_and_base's worker fallback.
    """
    try:
        from ...agent.model_profiles import get_models
        models = get_models()
        return models.worker or "anthropic/claude-sonnet-5"
    except Exception:
        return "anthropic/claude-sonnet-5"


def _llm_state(
    active_model: str | None = None,
    *,
    vertex_store: VertexStore | None = None,
) -> dict[str, Any]:
    """Health gated on the active/effective model's required key (I3).

    Gates ``configured`` on the key the active model actually needs: the
    conversation model during a turn, or the worker-role default otherwise.
    Local and unknown providers are treated as configured when they have no
    single required key. Vertex is checked through its local Rook record only.
    The full provider-key map is reported informationally.
    """
    from ...agent.model_profiles import api_key_env_for_model
    provider_keys = _provider_key_state()
    model = active_model or _effective_default_model()
    provider = model.split("/", 1)[0] if "/" in model else "unknown"
    key_env = api_key_env_for_model(model)

    if model.startswith("vertex_ai/"):
        try:
            vertex_gemini_model_name(model)
            store = vertex_store if vertex_store is not None else VertexStore.production()
            record = store.read()
        except VertexAuthError as exc:
            return {
                "configured": False,
                "provider": provider,
                "message": exc.public_message,
                "active_model": model,
                "provider_keys": provider_keys,
                "code": exc.code,
            }
        if record is None:
            return {
                "configured": False,
                "provider": provider,
                "message": "Vertex AI is not configured for this Windows user.",
                "active_model": model,
                "provider_keys": provider_keys,
                "code": "vertex_signed_out",
            }
        return {
            "configured": True,
            "provider": provider,
            "message": "Vertex AI is configured locally for the active model.",
            "active_model": model,
            "provider_keys": provider_keys,
        }

    if key_env is None:
        return {
            "configured": True,
            "provider": provider,
            "message": f"Active model '{model}' needs no single required key env var.",
            "active_model": model,
            "provider_keys": provider_keys,
        }

    configured = bool(os.environ.get(key_env))
    return {
        "configured": configured,
        "provider": provider,
        "message": (
            f"{key_env} is configured for active model '{model}'."
            if configured
            else f"{key_env} is missing for active model '{model}'. "
                 "Set it in the environment or mcp_server/.env."
        ),
        "active_model": model,
        "provider_keys": provider_keys,
    }


async def collect_runtime_facts(
    include_gh: bool = False, active_model: str | None = None
) -> dict[str, Any]:
    """Collect verified runtime facts for the chat service and prompt layer.

    Returns a stable dict describing Rhino bridge reachability, prompt-state
    availability, and optional Grasshopper availability. All failures are
    represented as structured facts rather than exceptions.
    """
    rhino_ping = await _call_rhino_with_timeout("/ping", timeout_seconds=3.0)
    rhino_connected = bool(rhino_ping.get("success") and rhino_ping.get("data") == "pong")

    prompt_available = False
    prompt_state: dict[str, Any] = {
        "available": False,
        "prompt": None,
        "is_active": None,
    }
    if rhino_connected:
        prompt_result = await _call_rhino_with_timeout("/command/prompt", timeout_seconds=1.5)
        if prompt_result.get("success") and isinstance(prompt_result.get("data"), dict):
            data = prompt_result["data"]
            prompt_state = {
                "available": True,
                "prompt": data.get("prompt"),
                "is_active": data.get("is_active"),
            }
            prompt_available = True
        else:
            prompt_state["error"] = prompt_result.get("data")

    gh_state: dict[str, Any] | None = None
    if include_gh:
        if rhino_connected:
            gh_result = await _call_rhino_with_timeout("/gh/status", timeout_seconds=1.5)
            gh_state = {
                "available": bool(gh_result.get("success")),
                "data": gh_result.get("data"),
            }
        else:
            gh_state = {
                "available": False,
                "data": "Rhino bridge unavailable",
            }

    llm_state = _llm_state(active_model)

    facts: dict[str, Any] = {
        "rhino": {
            "connected": rhino_connected,
            "data": rhino_ping.get("data"),
        },
        "prompt": prompt_state,
        "llm": llm_state,
    }
    if gh_state is not None:
        facts["gh"] = gh_state

    facts["verified_runtime_facts"] = _build_verified_fact_lines(
        rhino_connected=rhino_connected,
        prompt_available=prompt_available,
        prompt_state=prompt_state,
        gh_state=gh_state,
        llm_state=llm_state,
    )
    return facts


async def _call_rhino_with_timeout(path: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(call_rhino(path), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timed out collecting chat runtime health for %s", path)
        return {"success": False, "data": f"Timed out probing {path}"}
    except Exception as exc:
        logger.warning("Failed collecting chat runtime health for %s: %s", path, exc)
        return {"success": False, "data": str(exc)}


def _build_verified_fact_lines(
    *,
    rhino_connected: bool,
    prompt_available: bool,
    prompt_state: dict[str, Any],
    gh_state: dict[str, Any] | None,
    llm_state: dict[str, Any],
) -> list[str]:
    """Build short, verified fact lines for prompt injection."""
    lines: list[str] = []
    if rhino_connected:
        lines.append("Rhino bridge is connected and tool execution is available.")
    else:
        lines.append("Rhino bridge is currently unavailable; do not claim tools are connected.")

    if prompt_available:
        prompt = prompt_state.get("prompt") or "unknown"
        is_active = prompt_state.get("is_active")
        if is_active:
            lines.append(f"Rhino is waiting at command prompt: {prompt!r}.")
        else:
            lines.append(f"Rhino command prompt is idle at {prompt!r}.")
    else:
        lines.append("Rhino command prompt state could not be verified.")

    if gh_state is not None:
        if gh_state.get("available"):
            lines.append("Grasshopper is reachable in this session.")
        else:
            lines.append("Grasshopper availability is not verified in this session.")

    if llm_state.get("configured"):
        lines.append("The active LLM provider is configured for chat turns.")
    else:
        lines.append(
            "The active LLM provider is not configured; explain this explicitly "
            "instead of attempting a model call."
        )

    return lines
