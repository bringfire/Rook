from __future__ import annotations

import pytest

from rook.agent.tool_dispatcher import BRIDGE_ROUTES
from rook.agent.capability_inventory import (
    collect_live_sources,
    dispatch_context_from_sources,
)
from rook.agent.chat.tool_contracts import classify_visible_tool
from rook.agent.tool_groups import TOOL_GROUPS, READONLY_ALLOWED_GROUPS

_SCENE_TRIO = {
    "scene_query": ("/scene/graph/query", "POST"),
    "scene_classify": ("/scene/graph/classify", "POST"),
    "scene_overlay": ("/scene/graph/overlay", "POST"),
}


def test_scene_trio_in_bridge_routes():
    for tool, route in _SCENE_TRIO.items():
        assert tool in BRIDGE_ROUTES, f"{tool} missing from BRIDGE_ROUTES"
        assert BRIDGE_ROUTES[tool] == route, (
            f"{tool} route mismatch: {BRIDGE_ROUTES[tool]} != {route}"
        )


def test_scene_trio_classifies_as_bridge_route():
    # Realistic DispatchContext from the static surface snapshot; bridge_names is
    # populated from BRIDGE_ROUTES.keys(), so the trio must now classify as a
    # real dispatch path (was "failure" before the routes were added).
    ctx = dispatch_context_from_sources(collect_live_sources())
    for tool in _SCENE_TRIO:
        assert classify_visible_tool(tool, ctx) == "bridge_route", (
            f"{tool} did not classify as bridge_route"
        )


def test_gh_canvas_image_not_in_any_readonly_group():
    # Removed from gh_canvas_readonly (MCP-only, returns a PNG, no agent dispatch
    # path). Must not be reachable by the readonly profile via ANY allowed group.
    assert "gh_canvas_image" not in TOOL_GROUPS["gh_canvas_readonly"]
    for group in READONLY_ALLOWED_GROUPS:
        members = TOOL_GROUPS.get(group, [])
        assert "gh_canvas_image" not in members, (
            f"gh_canvas_image leaked into readonly-allowed group {group}"
        )


@pytest.mark.asyncio
async def test_gh_canvas_image_still_advertised_over_mcp():
    # Intent is "not local readonly, still public MCP". Pin that it remains in the
    # advertised catalog for Claude Code / external clients.
    from rook import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "gh_canvas_image" in names
