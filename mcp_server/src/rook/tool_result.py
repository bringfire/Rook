"""Read the public MCP ``call_tool()`` wire shape — the inverse of
``server._format_tool_result``.

``call_tool()`` returns ``list[TextContent]``. On success the single text item is
``json.dumps(data)`` (the ``data`` only). On failure it is
``"Error: " + (json.dumps(data) | str(data))``. These helpers parse that wire shape and
import nothing from ``server`` (``call_tool`` is injected), so this stays a leaf module.

See ``docs/CURRENT_ARCHITECTURE.md`` "Tool Result Surface" and issue #218.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

_ERROR_PREFIX = "Error: "


def text_from_call_tool_result(result: Any) -> str:
    """The single text payload of a ``call_tool()`` result list (``""`` if empty)."""
    if not result:
        return ""
    return result[0].text


def is_error_result(result: Any) -> bool:
    """True iff the wire text is a failure. Text-based only — no JSON, no inference."""
    return text_from_call_tool_result(result).startswith(_ERROR_PREFIX)


def parse_call_tool_data(result: Any) -> dict[str, Any]:
    """SUCCESS-only: the parsed ``data`` dict.

    Raises ``ValueError`` if the result is an error, the text is not JSON, or the parsed
    JSON is not a dict. Never returns ``{}`` silently.
    """
    text = text_from_call_tool_result(result)
    if text.startswith(_ERROR_PREFIX):
        raise ValueError(f"expected a success result, got an error: {text!r}")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"success text is not JSON: {text!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"success data is not a dict (got {type(data).__name__}): {text!r}"
        )
    return data


def parse_call_tool_error(result: Any) -> dict[str, Any] | str:
    """FAILURE-only: the error payload — a dict when JSON, else the raw string.

    Raises ``ValueError`` if the result is actually a success.
    """
    text = text_from_call_tool_result(result)
    if not text.startswith(_ERROR_PREFIX):
        raise ValueError(f"expected an error result, got a success: {text!r}")
    payload = text[len(_ERROR_PREFIX):]
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return payload
    return parsed if isinstance(parsed, dict) else payload
