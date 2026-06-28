import pytest

from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-id", name="spine_base_to_spine_top")
    sg.graph.add_node("joint-id", name="spine_base")
    sg.graph.add_edge(
        "member-id",
        "joint-id",
        key="relationship_fact:example",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
        contactKind="point_to_point",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
    )
    return sg


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_semantic_relationships_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_semantic_relationships"].inputSchema

    assert schema["required"] == ["object_ids"]
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["status"]["items"]["type"] == "string"
    assert schema["properties"]["provenance"]["items"]["type"] == "string"
    assert schema["properties"]["direction"]["enum"] == ["both", "outgoing", "incoming"]
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]


def test_tool_group_contains_scene_semantic_relationships():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_semantic_relationships" in TOOL_GROUPS["scene_graph"]


def test_scene_semantic_relationships_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_semantic_relationships")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_semantic_relationships" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_semantic_relationships():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_semantic_relationships" in tools
    assert callable(tools["scene_semantic_relationships"])


@pytest.mark.asyncio
async def test_local_scene_semantic_relationships_dispatch_uses_current_mirror_without_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_semantic_relationships"](object_ids=["member-id"])

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 1
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_server_dispatch_scene_semantic_relationships_does_not_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_semantic_relationships", {"object_ids": ["joint-id"]})

    assert result["success"] is True
    assert result["data"]["counts"]["relationshipFactCount"] == 1
    assert result["data"]["objects"][0]["facts"][0]["direction"] == "incoming"
    assert called["sync"] == 0
