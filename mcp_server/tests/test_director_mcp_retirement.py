from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    Profile,
)


RETIRED_DIRECTOR_TOOLS = (
    "rhino_director_run",
    "rhino_director_curve_samples",
    "rhino_director_assemble_video",
    "rhino_director_publish_video",
    "rhino_director_canvas_extract",
    "rhino_director_replay",
    "rhino_director_replay_cancel",
    "rhino_director_compile_motion",
    "rhino_director_package_take",
    "rhino_director_prepare_take",
    "rhino_director_compile_take",
    "rhino_director_worker_play",
    "rhino_director_capture_take",
    "rhino_director_preview_motion",
    "rhino_director_capture_source_occurrence_v2",
    "rhino_director_build_actor_set_from_source_occurrence_v2",
    "rhino_director_write_actor_metadata_v2",
    "rhino_director_read_actor_metadata_v2",
)

DIRECTOR_PREFIX_PROBES = RETIRED_DIRECTOR_TOOLS + (
    "rhino_director_migrate_actor_metadata_v2",
    "rhino_director_future_probe",
)


MEDIA_SENTINELS = frozenset(
    {
        "rhino_render_video",
        "rhino_video_status",
        "rhino_video_cancel",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_viewport",
        "rhino_capture_depth",
        "rhino_display_modes",
        "rhino_display_mode_set",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
        "rhino_vision_approve",
        "rhino_vision_delete_artifact",
        "rhino_vision_consume_approved",
        "rhino_vision_presentation",
    }
)

READONLY_MEDIA_SENTINELS = frozenset(
    {
        "rhino_video_status",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_display_modes",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
    }
)


def _serialized_tools(tools) -> str:
    return json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ],
        sort_keys=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_serialized_discovery_contains_no_director_guidance(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    payload = _serialized_tools(await server.list_tools())
    lowered = payload.lower()
    assert "rhino_director_" not in lowered
    assert "/director" not in lowered
    assert "visiondirector" not in lowered
    assert '\"director\"' not in lowered


def _forbidden_sync(label):
    def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


def _forbidden_async(label):
    async def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_director_prefix_stops_before_targeting_and_dispatch(
    monkeypatch, profile, tool_name
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    discovery_calls = []

    def no_live_instances():
        discovery_calls.append("entered")
        return []

    monkeypatch.setattr(
        server.targeting, "policy_for_tool", _forbidden_sync("targeting policy")
    )
    monkeypatch.setattr(
        server.targeting,
        "get_panel_target_config_error",
        _forbidden_sync("panel policy"),
    )
    monkeypatch.setattr(
        server.targeting, "get_panel_target_lock", _forbidden_sync("panel lock")
    )
    monkeypatch.setattr(
        server.targeting, "discover_instances", no_live_instances
    )
    monkeypatch.setattr(
        server.targeting, "resolve_tool_route", _forbidden_sync("target resolution")
    )
    monkeypatch.setattr(
        server, "_call_tool_dispatch", _forbidden_async("tool dispatch")
    )

    result = await server.call_tool(
        tool_name,
        {"port": 9950, "session": "conflicting-target"},
    )
    text = result[0].text
    if profile == "readonly":
        assert "tool_profile_blocked" in text
        assert tool_name in text
    else:
        assert text == f"Error: Unknown tool: {tool_name}"
    assert discovery_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_non_director_unknown_keeps_existing_policy_path(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    calls = []

    def policy_for_tool(name):
        calls.append(("policy", name))
        return SimpleNamespace(requires_rhino=False)

    async def dispatch(name, arguments):
        calls.append(("dispatch", name))
        return {"success": False, "data": f"Unknown tool: {name}"}

    monkeypatch.setattr(server.targeting, "policy_for_tool", policy_for_tool)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_unknown_future_probe", {})

    if profile == "readonly":
        assert "tool_profile_blocked" in result[0].text
        assert calls == []
    else:
        assert result[0].text == "Error: Unknown tool: rhino_unknown_future_probe"
        assert calls == [
            ("policy", "rhino_unknown_future_probe"),
            ("dispatch", "rhino_unknown_future_probe"),
        ]


def test_server_has_no_active_director_runtime_imports():
    for attribute in (
        "canvas_director",
        "director",
        "director_actor_metadata",
        "director_compiler",
        "director_preview",
        "director_publish",
        "director_take_package",
        "director_video",
        "director_worker_capture",
        "director_worker_compile",
        "director_worker_play",
        "director_worker_prepare",
    ):
        assert not hasattr(server, attribute), attribute


def test_director_case_labels_are_absent():
    labels = server._scan_dispatch_case_labels()
    assert set(DIRECTOR_PREFIX_PROBES).isdisjoint(labels)


def test_secondary_callable_registries_contain_no_director_surface():
    assert "director" not in tool_groups.TOOL_GROUPS
    assert "director_readonly" not in tool_groups.TOOL_GROUPS
    assert "director" not in tool_groups.MCP_ONLY_GROUPS
    assert "director_readonly" not in tool_groups.READONLY_ALLOWED_GROUPS
    grouped_names = {
        name for names in tool_groups.TOOL_GROUPS.values() for name in names
    }
    assert not any(name.startswith("rhino_director_") for name in grouped_names)
    assert not any(
        name.startswith("rhino_director_")
        for name in tool_dispatcher.BRIDGE_ROUTES
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting._ALL_KNOWN_TOOLS
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting.TOOL_POLICIES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_LEAN_TOOL_NAMES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_READONLY_TOOL_NAMES
    )


@pytest.mark.asyncio
async def test_live_agent_inventory_contains_no_director_record():
    tools = await server._all_live_tools()
    records = server._collect_agent_records(tools)
    assert "rhino_objects" in records
    assert not any(name.startswith("rhino_director_") for name in records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_error"),
    (
        (Profile.FULL, "not_mcp_dispatchable"),
        (Profile.LEAN, "not_mcp_dispatchable"),
        (Profile.READONLY, "tool_profile_blocked"),
    ),
)
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_meta_dispatch_cannot_recover_director(
    monkeypatch, profile, expected_error, tool_name
):
    server._reset_capability_index_cache()

    async def forbidden_call_tool(*args, **kwargs):
        raise AssertionError("meta dispatcher must not re-enter call_tool")

    monkeypatch.setattr(server, "call_tool", forbidden_call_tool)
    result = await server._handle_meta_tool(
        "rook_tools_call",
        {"name": tool_name, "arguments": {}},
        profile,
    )
    assert expected_error in result[0].text


@pytest.mark.asyncio
async def test_progressive_catalog_has_no_director_record_or_path():
    server._reset_capability_index_cache()
    index = await server._get_capability_index()
    assert not any(record.name.startswith("rhino_director_") for record in index.records)
    assert not any(record.domain == "director" for record in index.records)
    assert index.read("rhino_director_preview_motion") is None
    root = index.ls("/", depth=1)
    assert "/director" not in root["children"]
    assert not any(entry["domain"] == "director" for entry in root["entries"])


@pytest.mark.asyncio
async def test_media_sentinels_keep_discovery_dispatch_and_targeting(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    full = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    lean = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    readonly = {tool.name for tool in await server.list_tools()}

    assert MEDIA_SENTINELS <= full
    assert MEDIA_SENTINELS.isdisjoint(lean)
    assert MEDIA_SENTINELS & readonly == READONLY_MEDIA_SENTINELS
    assert MEDIA_SENTINELS <= server._dispatchable_tool_names()

    for name in MEDIA_SENTINELS:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is True
        assert policy.risk == (
            "read" if name in READONLY_MEDIA_SENTINELS else "mutate"
        )


@pytest.mark.asyncio
async def test_scanner_failure_cannot_gate_normal_direct_dispatch(monkeypatch):
    def source_unavailable(*args, **kwargs):
        raise OSError("source unavailable in frozen build")

    monkeypatch.setattr(server.inspect, "getsource", source_unavailable)
    assert server._scan_dispatch_case_labels() == server.META_TOOL_NAMES
    monkeypatch.setattr(
        server, "_DISPATCHABLE_TOOL_NAMES", server.META_TOOL_NAMES
    )
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda name: SimpleNamespace(requires_rhino=False),
    )

    called = []

    async def dispatch(name, arguments):
        called.append(name)
        return {"success": True, "data": {"name": name}}

    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_objects", {})
    assert json.loads(result[0].text) == {"name": "rhino_objects"}
    assert called == ["rhino_objects"]
