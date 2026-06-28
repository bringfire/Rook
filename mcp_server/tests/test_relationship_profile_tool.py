import pytest


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_relationship_profile_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_relationship_profile"].inputSchema

    assert schema["required"] == []
    assert schema["properties"]["project_root"]["type"] == "string"
    assert "sync" not in schema["properties"]
    assert "port" not in schema["properties"]


def test_tool_group_contains_scene_relationship_profile():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_relationship_profile" in TOOL_GROUPS["scene_graph"]


def test_scene_relationship_profile_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_relationship_profile")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_relationship_profile" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_relationship_profile():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_relationship_profile" in tools
    assert callable(tools["scene_relationship_profile"])


@pytest.mark.asyncio
async def test_local_scene_relationship_profile_returns_defaults():
    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_relationship_profile"]()

    assert result["success"] is True
    assert result["projectProfileLoaded"] is False
    assert result["profileSources"][1]["reason"] == "project_root_not_supplied"
    assert "supports" in result["profile"]["relationships"]


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_profile_returns_defaults_without_project_root():
    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_relationship_profile", {})

    assert result["success"] is True
    assert result["data"]["success"] is True
    assert result["data"]["projectProfileLoaded"] is False
    assert result["data"]["profileSources"][1]["reason"] == "project_root_not_supplied"
    assert "supports" in result["data"]["profile"]["relationships"]


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_profile_rejects_relative_project_root():
    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_relationship_profile", {"project_root": "."})

    assert result == {
        "success": False,
        "data": {
            "success": False,
            "error": "invalid_project_root",
            "message": "project_root must be an absolute path in v1",
            "diagnostics": {"invalidProjectRoot": 1},
        },
    }
