"""Runtime admission helper for legacy semantic-authority tombstones."""

from __future__ import annotations

from enum import Enum

from .tool_lifecycle import denial_payload, resolve_contained_tool


class DispatchOrigin(str, Enum):
    PUBLIC_MCP = "public_mcp"
    PROGRESSIVE_META = "progressive_meta"
    SERVER_DISPATCH = "server_dispatch"
    ROOK_AGENT = "rook_agent"
    ROOK_CHAT = "rook_chat"
    PLAN_GRAPH = "plan_graph"
    TOOL_DISPATCHER = "tool_dispatcher"
    INTERNAL_HANDLER = "internal_handler"


def _record_denial(entry, origin: DispatchOrigin) -> None:
    from .learning.metrics_store import get_metrics_store

    get_metrics_store().record_containment_denial(entry, origin)


def deny_if_contained(name: object, origin: DispatchOrigin) -> dict[str, object] | None:
    """Return a denial before callers inspect arguments or dispatch downstream."""
    if type(origin) is not DispatchOrigin:
        raise TypeError("origin must be a DispatchOrigin")
    entry = resolve_contained_tool(name)
    if entry is None:
        return None
    try:
        _record_denial(entry, origin)
    except Exception:
        pass
    return denial_payload(entry)
