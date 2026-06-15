import pytest

from rook import server


@pytest.mark.asyncio
async def test_gh_canvas_cleanup_dispatch_returns_internal_envelope(monkeypatch):
    """The dispatcher must not return raw MCP TextContent to routed call_tool."""

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/query":
            return {
                "success": True,
                "data": [
                    {
                        "Guid": "a",
                        "type": "Panel",
                        "Position": {"X": 200, "Y": 20},
                        "Size": {"Width": 100, "Height": 40},
                    },
                    {
                        "guid": "b",
                        "type": "Panel",
                        "position": {"x": 20, "y": 20},
                        "size": {"width": 100, "height": 40},
                    },
                ],
            }
        if route == "/gh/connections?guid=a":
            return {
                "success": True,
                "data": [{"Outputs": [{"Recipients": [{"ComponentGuid": "b"}]}]}],
            }
        if route == "/gh/connections?guid=b":
            return {
                "success": True,
                "data": [{"Inputs": [{"Sources": [{"ComponentGuid": "a"}]}]}],
            }
        if route == "/gh/groups":
            return {"success": True, "data": []}
        raise AssertionError(f"Unexpected Rhino call: {method} {route} {payload}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._call_tool_dispatch(
        "gh_canvas_cleanup",
        {"dry_run": True, "style": "compact", "snap_to_grid": True},
    )

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["data"]["dry_run"] is True
    assert result["data"]["components_analyzed"] == 2
    assert set(result["data"]["positions"]) == {"a", "b"}

