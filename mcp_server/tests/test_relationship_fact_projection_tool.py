import pytest

from rook.scene import relationship_fact_projection as rel
from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    for object_id in [
        "member-rhino-id",
        "joint-rhino-id",
        "feature-member-start-id",
        "feature-joint-point-id",
        "relationship-marker-id",
    ]:
        sg.graph.add_node(object_id, name=object_id, domain_label="debug", shape_class="point")
    sg._sequence = 77
    return sg


def _add_unrelated_fact_nodes(sg: SceneGraphAnalytics) -> None:
    for object_id in [
        "unrelated-member-id",
        "unrelated-joint-id",
        "unrelated-feature-member-id",
        "unrelated-feature-joint-id",
        "unrelated-relationship-id",
    ]:
        sg.graph.add_node(object_id, name=object_id, domain_label="debug", shape_class="point")


def _user_strings_for(object_id: str) -> dict:
    records = {
        "member-rhino-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "spine_base_to_spine_top",
        },
        "joint-rhino-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "spine_base",
        },
        "feature-member-start-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "spine_base_to_spine_top.start",
            "rook.graph.owner": "spine_base_to_spine_top",
            "rook.graph.owner_kind": "member",
        },
        "feature-joint-point-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "spine_base.point",
            "rook.graph.owner": "spine_base",
            "rook.graph.owner_kind": "node",
        },
        "relationship-marker-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "spine_base_to_spine_top.start_connects_spine_base",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "spine_base_to_spine_top.start",
            "rook.graph.to_feature": "spine_base.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
        "unrelated-member-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "unrelated_member",
        },
        "unrelated-joint-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "unrelated_joint",
        },
        "unrelated-feature-member-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "unrelated_member.start",
            "rook.graph.owner": "unrelated_member",
            "rook.graph.owner_kind": "member",
        },
        "unrelated-feature-joint-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "unrelated_joint.point",
            "rook.graph.owner": "unrelated_joint",
            "rook.graph.owner_kind": "node",
        },
        "unrelated-relationship-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "unrelated_member.start_connects_unrelated_joint",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "unrelated_member.start",
            "rook.graph.to_feature": "unrelated_joint.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
    }
    return records[object_id]


@pytest.mark.asyncio
async def test_project_relationship_facts_for_tool_hydrates_scene_and_projects(monkeypatch):
    sg = _scene_graph()
    sg.graph.add_node(
        "rookbim:room:synthetic",
        name="Synthetic BIM room",
        projectionKind="bim_relationship_v1",
        nodeKind="rookbim_room",
    )
    calls = []

    async def fake_sync(port=None):
        calls.append(("sync", port))
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        calls.append((path, payload["id"], port))
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        port=9876,
        analytics=sg,
    )

    assert result["success"] is True
    assert result["counts"]["candidateObjectCount"] == 5
    assert result["counts"]["hydratedObjectCount"] == 5
    assert result["counts"]["ownerObjectCount"] == 2
    assert result["counts"]["featureObjectCount"] == 2
    assert result["counts"]["relationshipObjectCount"] == 1
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["projectedEdgeCount"] == 1
    assert result["byRelationshipType"] == {"connects": 1}
    assert result["byPose"] == {"reclined_robot": 1}
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert all(call[0] in {"sync", "/usertext/object-get"} for call in calls)
    hydrated_ids = {call[1] for call in calls if call[0] == "/usertext/object-get"}
    assert "rookbim:room:synthetic" not in hydrated_ids


@pytest.mark.asyncio
async def test_scoped_object_ids_hydrate_full_scene_but_filter_projected_facts(monkeypatch):
    sg = _scene_graph()
    _add_unrelated_fact_nodes(sg)
    hydrated_ids = []

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        hydrated_ids.append(payload["id"])
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        object_ids=["member-rhino-id"],
        analytics=sg,
    )

    assert result["success"] is True
    assert set(hydrated_ids) == {
        "member-rhino-id",
        "joint-rhino-id",
        "feature-member-start-id",
        "feature-joint-point-id",
        "relationship-marker-id",
        "unrelated-member-id",
        "unrelated-joint-id",
        "unrelated-feature-member-id",
        "unrelated-feature-joint-id",
        "unrelated-relationship-id",
    }
    assert result["counts"]["relationshipFactCount"] == 2
    assert result["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert not sg.graph.has_edge("unrelated-member-id", "unrelated-joint-id")


@pytest.mark.asyncio
async def test_strict_tool_failure_on_malformed_fact(monkeypatch):
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        user_strings = dict(_user_strings_for(payload["id"]))
        if payload["id"] == "relationship-marker-id":
            user_strings.pop("rook.graph.to_feature", None)
        return {"success": True, "data": {"id": payload["id"], "userStrings": user_strings}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        strict=True,
        analytics=sg,
    )

    assert result["success"] is False
    assert result["error"] == "relationship_fact_projection_validation_failed"
    assert "relationshipObjectsMissingFeatureEndpoint" in result["message"]


@pytest.mark.asyncio
async def test_scene_context_sync_false_renders_relationship_fact_details(monkeypatch):
    sg = _scene_graph()
    sg.graph.nodes["joint-rhino-id"]["domain_label"] = "joint"
    sg.graph.add_edge(
        "member-rhino-id",
        "joint-rhino-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:spine",
        relationship="connects",
        projectionKind=rel.PROJECTION_KIND,
        semanticRelationshipType="connects",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode=rel.DEFAULT_SOURCE_MODE,
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
        relationshipFactId="spine_base_to_spine_top.start_connects_spine_base",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
        engineVersion=rel.ENGINE_VERSION,
    )
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"success": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_context",
        {"object_ids": ["member-rhino-id", "joint-rhino-id"], "sync": False},
    )

    assert result["success"] is True
    assert called["sync"] == 0
    assert "connects: JOINT" in result["data"]
    assert "connected by: DEBUG" in result["data"]
    assert "via spine_base_to_spine_top.start -> spine_base.point" in result["data"]
    assert "point_to_point" in result["data"]
    assert "accepted" in result["data"]
    assert "authored_assembly_graph" in result["data"]


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_project_relationship_facts_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_project_relationship_facts"].inputSchema

    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["source_mode"]["enum"] == ["authored_graph_user_strings"]
    assert schema["properties"]["strict"]["type"] == "boolean"
    assert schema["properties"]["port"]["type"] == "integer"


def test_tool_group_contains_scene_project_relationship_facts():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_project_relationship_facts" in TOOL_GROUPS["scene_graph"]


def test_scene_project_relationship_facts_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_project_relationship_facts")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_project_relationship_facts" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_project_relationship_facts():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_project_relationship_facts" in tools
    assert callable(tools["scene_project_relationship_facts"])


@pytest.mark.asyncio
async def test_server_dispatch_projects_relationship_facts(monkeypatch):
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_project_relationship_facts",
        {"graph_source": "pearson_robot_skeleton_graph"},
    )

    assert result["success"] is True
    payload = result["data"]
    assert payload["success"] is True
    assert payload["projectionKind"] == rel.PROJECTION_KIND
    assert payload["counts"]["projectedEdgeCount"] == 1
