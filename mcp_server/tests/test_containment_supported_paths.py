from __future__ import annotations

import sys
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.agent.tool_dispatcher import ToolDispatcher  # noqa: E402
from rook.tool_lifecycle import resolve_contained_tool  # noqa: E402


SUPPORTED = (
    "rhino_execute",
    "rhino_command",
    "rhino_create",
    "rhino_transform",
    "gh_snapshot",
    "gh_edit",
    "gh_errors",
    "gh_create_script",
    "gh_update_script",
    "gh_set_script",
    "knowledge_query",
    "rhino_knowledge_query",
    "gh_knowledge_query",
    "road_intersection_candidates",
    "road_intersection_resolve",
)

NATIVE_INTERSECTION_ROUTES = {
    "road_intersection_candidates": "/road/intersection/candidates",
    "road_intersection_resolve": "/road/intersection/resolve",
}


@pytest.mark.asyncio
async def test_supported_paths_remain_public_and_model_visible() -> None:
    from rook import server
    from rook.agent.tool_registry import build_catalog_from_mcp_tools

    tools = await server._all_live_tools()
    public = {tool.name for tool in tools}
    catalog = build_catalog_from_mcp_tools(tools)
    assert set(SUPPORTED).issubset(public)
    assert set(SUPPORTED).issubset(catalog)
    assert all(resolve_contained_tool(name) is None for name in SUPPORTED)


@pytest.mark.asyncio
async def test_supported_local_dispatch_is_not_intercepted() -> None:
    calls = []

    async def handler(**params):
        calls.append(params)
        return {"success": True, "data": {"verified": True}}

    dispatcher = ToolDispatcher(local_tools={name: handler for name in SUPPORTED})
    for name in SUPPORTED:
        result = await dispatcher._dispatch_inner(name, {"marker": name}, None)
        assert result["success"] is True, name
    assert len(calls) == len(SUPPORTED)


@pytest.mark.asyncio
async def test_native_intersection_tools_reach_normal_routing_boundary(monkeypatch) -> None:
    from rook import server

    calls = []

    async def fake_call_rhino(path, method="GET", data=None, *, port=None, **_kwargs):
        calls.append((path, method, data, port))
        return {"success": True, "data": {"verified": True}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    for name, path in NATIVE_INTERSECTION_ROUTES.items():
        result = await server._call_tool_dispatch(name, {"marker": name, "port": 12001})
        assert result["success"] is True
        assert calls[-1] == (path, "POST", {"marker": name}, 12001)
