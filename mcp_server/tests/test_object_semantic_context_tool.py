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
async def test_server_tool_schema_exposes_scene_object_semantic_context_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_object_semantic_context"].inputSchema

    assert schema["required"] == ["object_ids"]
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["status"]["items"]["type"] == "string"
    assert schema["properties"]["provenance"]["items"]["type"] == "string"
    assert schema["properties"]["direction"]["enum"] == ["both", "outgoing", "incoming"]
    assert schema["properties"]["max_groups"]["type"] == "integer"
    assert schema["properties"]["max_facts_per_group"]["type"] == "integer"
    assert schema["properties"]["project_root"]["type"] == "string"
    assert "project_root" not in schema["required"]
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]
    assert "port" not in schema["properties"]


def test_tool_group_contains_scene_object_semantic_context():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_object_semantic_context" in TOOL_GROUPS["scene_graph"]


def test_scene_object_semantic_context_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_object_semantic_context")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_object_semantic_context" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_object_semantic_context():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_object_semantic_context" in tools
    assert callable(tools["scene_object_semantic_context"])


@pytest.mark.asyncio
async def test_local_scene_object_semantic_context_dispatch_uses_current_mirror_without_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_object_semantic_context"](object_ids=["member-id"])

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["cardCount"] == 1
    assert result["cards"][0]["groups"][0]["groupKey"] == "connects:outgoing:accepted:authored_assembly_graph"
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_local_scene_object_semantic_context_rejects_bare_string_object_ids(monkeypatch):
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_object_semantic_context"](object_ids="member-id")

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1",
    }


@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_does_not_sync_or_project(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0, "project": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    async def fake_project(*args, **kwargs):
        called["project"] += 1
        return {"success": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(
        "rook.scene.relationship_fact_projection.project_relationship_facts_for_tool",
        fake_project,
    )

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_object_semantic_context", {"object_ids": ["joint-id"]})

    assert result["success"] is True
    assert result["data"]["counts"]["relationshipFactCount"] == 1
    assert result["data"]["cards"][0]["groups"][0]["direction"] == "incoming"
    assert called == {"sync": 0, "project": 0}


@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_object_semantic_context",
        {"object_ids": ["member-id"], "max_groups": 0},
    )

    assert result == {
        "success": False,
        "data": {
            "success": False,
            "error": "invalid_card_bounds",
            "message": "max_groups and max_facts_per_group must be positive integers in v1",
        },
    }


@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_passes_project_root(monkeypatch, tmp_path):
    sg = _scene_graph()
    seen = {}

    def fake_query(analytics, **kwargs):
        assert analytics is sg
        seen.update(kwargs)
        return {"success": True, "counts": {}, "cards": [], "diagnostics": {}}

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(
        "rook.scene.object_semantic_context.query_object_semantic_context",
        fake_query,
    )

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_object_semantic_context",
        {"object_ids": ["member-id"], "project_root": str(tmp_path)},
    )

    assert result["success"] is True
    assert seen["project_root"] == str(tmp_path)
