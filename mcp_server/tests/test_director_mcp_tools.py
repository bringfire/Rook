from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_groups
from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools
from rook.agent.tool_registry import ToolRegistry


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


def _lite_tool_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


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
    camera_request_schema = schema["properties"]["camera"]
    assert camera_request_schema["required"] == ["strategy"]
    assert "curve_follow_target" in camera_request_schema["properties"]["strategy"]["description"]
    assert "curve_id" in camera_request_schema["properties"]
    assert (
        "Rhino curve object UUID"
        in camera_request_schema["properties"]["curve_id"]["description"]
    )
    assert "not a name" in camera_request_schema["properties"]["curve_id"]["description"]
    assert "target" in camera_request_schema["properties"]
    assert "numeric" in camera_request_schema["properties"]["target"]["description"]
    assert "not an object" in camera_request_schema["properties"]["target"]["description"]
    assert "sampling" in camera_request_schema["properties"]
    assert "lens_length" in camera_request_schema["properties"]
    assert "fov_degrees" in camera_request_schema["properties"]


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
async def test_director_assemble_video_tool_registered_as_mutating_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_assemble_video" in by_name

    schema = by_name["rhino_director_assemble_video"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["run_root"]
    assert _find_rejected_schema_keywords(schema) == []

    properties = schema["properties"]
    assert properties["run_root"]["type"] == "string"
    assert properties["fps"]["type"] == "number"
    assert properties["fps"]["exclusiveMinimum"] == 0


@pytest.mark.asyncio
async def test_director_publish_video_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_publish_video" in by_name
    schema = by_name["rhino_director_publish_video"].inputSchema
    assert schema["required"] == ["run_root"]
    assert schema["properties"]["run_root"]["type"] == "string"
    assert _find_rejected_schema_keywords(schema) == []


@pytest.mark.asyncio
async def test_director_prepare_take_tool_registered_with_clean_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_prepare_take" in by_name

    tool = by_name["rhino_director_prepare_take"]
    assert "metadata-only" in tool.description
    assert "external sidecars" in tool.description
    assert "no Rhino document mutation" in tool.description
    assert "no generated actor/replay target" in tool.description

    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert _find_rejected_schema_keywords(schema) == []
    assert "enum" not in json.dumps(schema)
    assert schema.get("required", []) == []
    properties = schema["properties"]
    assert set(properties) == {
        "scope",
        "source_object_ids",
        "use_current_selection",
        "page_size",
        "classify_nested",
        "write_markdown_audit",
        "portable",
        "output_root",
        "take_id",
    }
    assert "selected_occurrences" in properties["scope"]["description"]
    assert "only supported" in properties["scope"]["description"]


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
async def test_director_assemble_video_tool_dispatches_to_python_runner():
    request = {"run_root": "C:/runs/video", "fps": 24}
    with patch.object(
        server.director_video, "assemble_director_video", new_callable=AsyncMock
    ) as mock:
        mock.return_value = {"state": "complete", "output_path": "videos/preview.mp4"}
        result = await server.call_tool("rhino_director_assemble_video", request)
    mock.assert_awaited_once_with(request, port=None)
    assert "videos/preview.mp4" in result[0].text


@pytest.mark.asyncio
async def test_director_publish_video_dispatches_to_python(monkeypatch):
    request = {
        "run_root": "C:/Users/aryan/AppData/Local/Rook/rookvision_director/run-a"
    }
    called = {}

    async def fake_publish(arguments, *, port=None):
        called["arguments"] = arguments
        called["port"] = port
        return {
            "state": "complete",
            "artifact_id": "00000000-0000-0000-0000-000000000099",
            "profile": "director_publish_standard_v1",
            "preset": "hd_720",
        }

    monkeypatch.setattr(server.director_publish, "publish_director_video", fake_publish)
    result = await server.call_tool("rhino_director_publish_video", request)

    assert called["arguments"] == request
    assert result[0].text
    payload = json.loads(result[0].text)
    assert payload["state"] == "complete"


@pytest.mark.asyncio
async def test_director_assemble_video_tool_returns_error_envelope_for_video_error():
    request = {"run_root": "C:/runs/video"}
    with patch.object(
        server.director_video, "assemble_director_video", new_callable=AsyncMock
    ) as mock:
        mock.side_effect = server.director_video.DirectorVideoError("bad video request")
        result = await server.call_tool("rhino_director_assemble_video", request)
    mock.assert_awaited_once_with(request, port=None)
    assert result[0].text.startswith("Error:")
    payload = json.loads(result[0].text.removeprefix("Error: "))
    assert payload == {
        "code": "director_video_error",
        "message": "bad video request",
    }


@pytest.mark.asyncio
async def test_director_prepare_take_tool_dispatches_to_python_runner():
    request = {
        "scope": "selected_occurrences",
        "source_object_ids": ["root-a"],
        "take_id": "take-dispatch",
        "output_root": "C:/runs/director-takes",
    }
    with patch.object(
        server.director_prepare, "prepare_take", new_callable=AsyncMock
    ) as mock:
        mock.return_value = {
            "take_id": "take-dispatch",
            "paths": {
                "take_manifest": "C:/runs/director-takes/take-dispatch/take_manifest.json"
            },
        }
        result = await server.call_tool("rhino_director_prepare_take", request)

    mock.assert_awaited_once_with(request, port=None)
    text = result[0].text
    assert "take-dispatch" in text
    assert "take_manifest.json" in text


@pytest.mark.asyncio
async def test_director_prepare_take_tool_surfaces_public_prepare_error_code():
    request = {"take_id": "take-missing-selection"}
    with patch.object(
        server.director_prepare, "prepare_take", new_callable=AsyncMock
    ) as mock:
        mock.side_effect = server.director_prepare.DirectorPrepareError(
            "missing_source_selection", "source ids or current selection required"
        )
        result = await server.call_tool("rhino_director_prepare_take", request)

    mock.assert_awaited_once_with(request, port=None)
    text = result[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text.removeprefix("Error: "))
    assert payload["code"] == "missing_source_selection"
    assert payload["message"] == "source ids or current selection required"


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
    assert "rhino_director_replay" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_replay_cancel" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_compile_motion" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_preview_motion" in tool_groups.TOOL_GROUPS["director"]
    assert "director_readonly" in tool_groups.TOOL_GROUPS
    assert "rhino_director_curve_samples" in tool_groups.TOOL_GROUPS["director_readonly"]
    assert "rhino_director_compile_motion" in tool_groups.TOOL_GROUPS["director_readonly"]
    assert "director" in tool_groups.MCP_ONLY_GROUPS


def test_director_prepare_take_is_in_director_group_only():
    assert "rhino_director_prepare_take" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_prepare_take" not in tool_groups.TOOL_GROUPS[
        "director_readonly"
    ]


def test_director_tool_groups_include_assemble_video_mutating_only():
    assert "rhino_director_assemble_video" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_assemble_video" not in tool_groups.TOOL_GROUPS[
        "director_readonly"
    ]


def test_director_publish_video_in_director_group_only():
    assert "rhino_director_publish_video" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_publish_video" not in tool_groups.TOOL_GROUPS[
        "director_readonly"
    ]


def test_director_readonly_group_loads_for_readonly_registry():
    assert "director_readonly" in tool_groups.READONLY_ALLOWED_GROUPS
    catalog = {
        name: _lite_tool_schema(name)
        for name in tool_groups.TOOL_GROUPS["director_readonly"]
    }
    registry = ToolRegistry(
        catalog=catalog,
        tier0=set(),
        allowed_groups=tool_groups.READONLY_ALLOWED_GROUPS,
        agent_mode=True,
    )

    result = registry.request_group("director_readonly", turn=1)

    assert result["success"] is True
    assert "rhino_director_curve_samples" in result["loaded"]
    assert "rhino_director_compile_motion" in result["loaded"]


def test_director_compile_motion_is_agent_local_dispatchable():
    assert "rhino_director_compile_motion" in build_local_tools()


@pytest.mark.asyncio
async def test_director_compile_motion_agent_dispatch_uses_python_compiler(monkeypatch):
    from rook import director_compiler

    async def fake_compile(arguments, *, port=None):
        assert arguments == {"timeline": {"fps": 24, "frame_count": 2}, "motion": []}
        assert port == 9977
        return {"track": {"frame_count": 2}, "provenance": {"source": "agent-local"}}

    monkeypatch.setattr(director_compiler, "compile_motion", fake_compile)
    dispatcher = ToolDispatcher(port=9977, local_tools=build_local_tools())

    result = await dispatcher.dispatch(
        "rhino_director_compile_motion",
        {"timeline": {"fps": 24, "frame_count": 2}, "motion": []},
    )

    assert result == {
        "success": True,
        "data": {"track": {"frame_count": 2}, "provenance": {"source": "agent-local"}},
    }


def test_director_curve_samples_search_loads_readonly_bridge_tool():
    catalog = {
        "rhino_director_curve_samples": _lite_tool_schema("rhino_director_curve_samples"),
        "rhino_director_run": _lite_tool_schema("rhino_director_run"),
    }
    catalog["rhino_director_curve_samples"]["function"][
        "description"
    ] = "director curve samples"
    catalog["rhino_director_run"]["function"]["description"] = "director run"
    registry = ToolRegistry(
        catalog=catalog,
        tier0=set(),
        allowed_groups=tool_groups.READONLY_ALLOWED_GROUPS,
        agent_mode=True,
    )

    result = registry.search("director curve samples", top_k=5, turn=1)

    assert result["success"] is True
    assert "rhino_director_curve_samples" in result["loaded"]
    assert "rhino_director_run" not in result["loaded"]


def test_director_prepare_take_sidecar_writes_require_mutating_routing():
    policy = targeting.policy_for_tool("rhino_director_prepare_take")
    assert policy == targeting.RhinoToolPolicy(True, "mutate")


@pytest.mark.asyncio
async def test_replay_tools_registered_with_clean_schema():
    tools = {t.name: t for t in await server.list_tools()}
    assert "rhino_director_replay" in tools
    assert "rhino_director_replay_cancel" in tools
    schema = tools["rhino_director_replay"].inputSchema
    blob = json.dumps(schema)
    for forbidden in ["oneOf", "anyOf", "allOf"]:
        assert forbidden not in blob
    # display-only: no capture/output surface
    for banned in ["capture", "output_path", "output_dir", "output_root"]:
        assert banned not in blob
    props = schema["properties"]
    assert {"track", "track_path", "replay_session_id", "fps", "restore_on_finish", "loop"} <= set(props)
    cancel_props = tools["rhino_director_replay_cancel"].inputSchema["properties"]
    assert "replay_session_id" in cancel_props


@pytest.mark.asyncio
async def test_replay_dispatch_routes_to_director(monkeypatch):
    import rook.server as srv
    called = {}
    async def fake_run(args, port=None): called["run"] = args; return {"status": "completed"}
    async def fake_cancel(args, port=None): called["cancel"] = args; return {"cancel_requested": True}
    monkeypatch.setattr(srv.director, "run_replay", fake_run)
    monkeypatch.setattr(srv.director, "cancel_replay", fake_cancel)
    await srv.call_tool("rhino_director_replay", {"track": {"x": 1}})
    await srv.call_tool("rhino_director_replay_cancel", {"replay_session_id": "abc"})
    assert called["run"] == {"track": {"x": 1}}
    assert called["cancel"] == {"replay_session_id": "abc"}


@pytest.mark.asyncio
async def test_compile_motion_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_compile_motion" in by_name
    schema = by_name["rhino_director_compile_motion"].inputSchema
    assert schema["type"] == "object"
    assert _find_rejected_schema_keywords(schema) == []
    assert "motion" in schema["properties"]
    assert "timeline" in schema["properties"]


@pytest.mark.asyncio
async def test_compile_motion_tool_dispatch_success():
    spec = {
        "timeline": {"fps": 24, "frame_count": 2},
        "motion": [{"target": "11111111-1111-1111-1111-111111111111",
                    "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}],
    }

    async def fake_compile(arguments, *, port=None):
        assert arguments["timeline"]["fps"] == 24
        return {"track": {"frame_count": 2}, "provenance": {"frame_count": 2}}

    with patch("rook.server.director_compiler.compile_motion", new=fake_compile):
        out = await server.call_tool("rhino_director_compile_motion", spec)
    # IMPORTANT (see server._format_tool_result): success text IS the data, NOT a
    # {success, data} envelope. Parse the text directly as data.
    data = json.loads(out[0].text)
    assert data["track"]["frame_count"] == 2


@pytest.mark.asyncio
async def test_compile_motion_tool_dispatch_error_surfaces_code():
    async def boom(arguments, *, port=None):
        from rook import director_compiler
        raise director_compiler.DirectorCompileError("unknown_group", "nope", object_id="x")

    with patch("rook.server.director_compiler.compile_motion", new=boom):
        out = await server.call_tool("rhino_director_compile_motion", {"motion": []})
    # Failure text is "Error: " + json.dumps(data); strip the prefix then parse.
    text = out[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text[len("Error: "):])
    assert payload["code"] == "unknown_group"
    assert payload["object_id"] == "x"


@pytest.mark.asyncio
async def test_preview_motion_tool_registered_with_clean_schema():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}

    assert "rhino_director_preview_motion" in by_name
    schema = by_name["rhino_director_preview_motion"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["timeline", "motion"]
    assert _find_rejected_schema_keywords(schema) == []
    assert "timeline" in schema["properties"]
    assert "motion" in schema["properties"]
    assert "preview" in schema["properties"]

    props = schema["properties"]
    preview_props = props.get("preview", {}).get("properties", {})
    for banned in ["capture", "output_path", "output_dir", "output_root", "artifact", "persist"]:
        assert banned not in props
        assert banned not in preview_props


@pytest.mark.asyncio
async def test_preview_motion_tool_dispatch_success():
    request = {
        "timeline": {"fps": 24, "frame_count": 2},
        "motion": [
            {
                "target": "11111111-1111-1111-1111-111111111111",
                "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}],
            }
        ],
        "preview": {"restore_on_finish": True},
    }

    async def fake_preview(arguments, *, port=None):
        assert arguments == request
        assert port is None
        return {"state": "completed", "compile": {"track_summary": {"frame_count": 2}}, "replay": {"status": "completed"}}

    with patch("rook.server.director_preview.preview_motion", new=fake_preview):
        out = await server.call_tool("rhino_director_preview_motion", request)

    data = json.loads(out[0].text)
    assert data["state"] == "completed"
    assert data["replay"]["status"] == "completed"
