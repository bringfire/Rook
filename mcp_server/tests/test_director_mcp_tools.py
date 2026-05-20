from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_groups


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])


@pytest.mark.asyncio
async def test_director_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_run" in by_name
    schema = by_name["rhino_director_run"].inputSchema
    assert schema["required"] == [
        "object_ids",
        "frame_count",
        "resolution",
        "camera_keyframes",
    ]


@pytest.mark.asyncio
async def test_director_tool_dispatches_to_python_runner():
    request = {
        "object_ids": ["a"],
        "frame_count": 1,
        "resolution": {"width": 320, "height": 180},
        "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
    }
    with patch.object(server.director, "run_director", new_callable=AsyncMock) as mock:
        mock.return_value = {"state": "complete", "run_root": "C:/runs/x"}
        result = await server.call_tool("rhino_director_run", request)
    mock.assert_awaited_once()
    assert "complete" in result[0].text


@pytest.mark.asyncio
async def test_director_tool_returns_error_envelope_for_authoring_error():
    request = {
        "object_ids": ["a"],
        "frame_count": 1,
        "resolution": {"width": 320, "height": 180},
        "camera_keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}],
    }
    with patch.object(server.director, "run_director", new_callable=AsyncMock) as mock:
        mock.side_effect = server.director.DirectorInputError("bad director request")
        result = await server.call_tool("rhino_director_run", request)
    mock.assert_awaited_once()
    assert result[0].text.startswith("Error:")
    assert "bad director request" in result[0].text
    payload = json.loads(result[0].text.removeprefix("Error: "))
    assert payload == {
        "code": "director_error",
        "message": "bad director request",
    }


def test_director_tool_groups_are_mcp_only():
    assert "director" in tool_groups.TOOL_GROUPS
    assert "rhino_director_run" in tool_groups.TOOL_GROUPS["director"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS
