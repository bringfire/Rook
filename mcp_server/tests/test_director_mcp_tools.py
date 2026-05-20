from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_groups


OPENAI_REJECTED_SCHEMA_KEYWORDS = {"oneOf", "anyOf", "allOf", "not"}


def _find_rejected_schema_keywords(value, path="$"):
    if isinstance(value, dict):
        findings = [
            f"{path}.{key}"
            for key in OPENAI_REJECTED_SCHEMA_KEYWORDS
            if key in value
        ]
        for key, child in value.items():
            findings.extend(_find_rejected_schema_keywords(child, f"{path}.{key}"))
        return findings
    if isinstance(value, list):
        findings = []
        for index, child in enumerate(value):
            findings.extend(_find_rejected_schema_keywords(child, f"{path}[{index}]"))
        return findings
    return []


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
    assert schema["type"] == "object"
    assert not {"oneOf", "anyOf", "allOf", "enum", "not"} & set(schema)
    assert _find_rejected_schema_keywords(schema) == []
    assert schema["required"] == ["object_ids", "resolution"]
    assert "frame_count" in schema["properties"]
    assert "timeline" in schema["properties"]
    assert schema["properties"]["timeline"]["type"] == "object"
    assert "fps" in schema["properties"]["timeline"]["properties"]
    assert "duration_seconds" in schema["properties"]["timeline"]["properties"]
    assert (
        "MCP callers should send a JSON integer"
        in schema["properties"]["timeline"]["properties"]["fps"]["description"]
    )
    assert "camera_keyframes" in schema["properties"]
    assert "camera" in schema["properties"]
    keyframe_schema = schema["properties"]["camera_keyframes"]["items"]
    assert keyframe_schema["required"] == ["source"]
    assert "frame_index" in keyframe_schema["properties"]
    assert "time" in keyframe_schema["properties"]
    assert "at" in keyframe_schema["properties"]
    assert (
        "MCP callers should send a JSON integer"
        in keyframe_schema["properties"]["frame_index"]["description"]
    )
    source_schema = keyframe_schema["properties"]["source"]
    assert "explicit_camera" in source_schema["description"]
    assert "camera" in source_schema["properties"]
    camera_schema = source_schema["properties"]["camera"]
    assert "lens_length or fov_degrees" in camera_schema["description"]
    assert camera_schema["required"] == ["projection", "location", "target", "up"]


@pytest.mark.asyncio
async def test_director_schema_keeps_nullable_copied_camera_fields_runtime_only():
    tools = await server.list_tools()
    schema = {tool.name: tool for tool in tools}["rhino_director_run"].inputSchema
    camera_schema = schema["properties"]["camera_keyframes"]["items"]["properties"][
        "source"
    ]["properties"]["camera"]

    assert not OPENAI_REJECTED_SCHEMA_KEYWORDS & set(camera_schema)
    assert camera_schema["additionalProperties"] is True
    assert set(camera_schema["properties"]) == {
        "projection",
        "location",
        "target",
        "up",
    }


@pytest.mark.asyncio
async def test_director_curve_samples_tool_registered_as_readonly_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_curve_samples" in by_name

    schema = by_name["rhino_director_curve_samples"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["curve_id", "frame_count", "sampling"]
    assert _find_rejected_schema_keywords(schema) == []

    properties = schema["properties"]
    assert properties["curve_id"]["type"] == "string"
    assert properties["frame_count"]["type"] == "integer"
    assert properties["frame_count"]["minimum"] == 1
    assert properties["frame_count"]["maximum"] == 5000

    sampling = properties["sampling"]
    assert sampling["type"] == "object"
    assert sampling["required"] == ["mode", "start", "end"]
    assert sampling["properties"]["mode"]["type"] == "string"
    assert "normalized_parameter" in sampling["properties"]["mode"]["description"]
    assert sampling["properties"]["start"]["minimum"] == 0
    assert sampling["properties"]["start"]["maximum"] == 1
    assert sampling["properties"]["end"]["minimum"] == 0
    assert sampling["properties"]["end"]["maximum"] == 1


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
async def test_director_tool_dispatches_timeline_only_request_to_python_runner():
    request = {
        "object_ids": ["obj-1"],
        "timeline": {"fps": 24, "duration_seconds": 0.125},
        "resolution": {"width": 64, "height": 64},
        "camera_keyframes": [
            {"time": 0.0, "source": {"kind": "active_view"}}
        ],
    }
    with patch.object(server.director, "run_director", new_callable=AsyncMock) as mock:
        mock.return_value = {"state": "complete", "run_root": "C:/runs/timeline"}
        result = await server.call_tool("rhino_director_run", request)
    mock.assert_awaited_once()
    assert mock.await_args.args[0] == request
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


@pytest.mark.asyncio
async def test_director_curve_samples_tool_dispatches_to_native_route(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data, port))
        return {
            "success": True,
            "data": {
                "schema_version": 1,
                "curve_id": data["curve_id"],
                "frame_count": data["frame_count"],
                "samples": [],
                "provenance": {
                    "sampling_mode": "normalized_parameter",
                    "validation_strength": "curve_parameter_sampled",
                },
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    request = {
        "curve_id": "00000000-0000-0000-0000-000000000001",
        "frame_count": 3,
        "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
    }

    result = await server.call_tool("rhino_director_curve_samples", request)

    assert calls == [("/director/curve-samples", "POST", request, None)]
    assert "curve_parameter_sampled" in result[0].text


def test_director_tool_groups_include_curve_samples_readonly():
    assert "director" in tool_groups.TOOL_GROUPS
    assert "rhino_director_run" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director"]
    assert "director_readonly" in tool_groups.TOOL_GROUPS
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director_readonly"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS
