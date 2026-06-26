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
