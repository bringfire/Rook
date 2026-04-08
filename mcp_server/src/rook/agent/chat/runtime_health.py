"""Runtime health checks for the Rhino-owned chat service."""

from __future__ import annotations

import logging
import os
import asyncio
from typing import Any

from ...bridge import call_rhino

logger = logging.getLogger(__name__)


async def collect_runtime_facts(include_gh: bool = False) -> dict[str, Any]:
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

    llm_state = {
        "configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "provider": "anthropic",
        "message": (
            "Anthropic API key is configured."
            if os.environ.get("ANTHROPIC_API_KEY")
            else "Anthropic API key is missing. Set ANTHROPIC_API_KEY in the environment or mcp_server/.env."
        ),
    }

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
        lines.append("Anthropic API key is configured for chat turns.")
    else:
        lines.append("Anthropic API key is missing; explain this explicitly instead of attempting a model call.")

    return lines
