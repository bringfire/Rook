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
