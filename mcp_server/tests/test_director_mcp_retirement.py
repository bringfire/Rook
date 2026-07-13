from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rook import server


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
