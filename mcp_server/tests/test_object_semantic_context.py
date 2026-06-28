import pytest

from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.object_semantic_context import query_object_semantic_context


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node(
        "member-a",
        name="spine_base_to_spine_top",
        objectKind="block_instance",
        definitionId="robot_member_definition",
        definitionName="RobotMember",
    )
    sg.graph.add_node("member-b", name="pelvis_to_left_hip")
    sg.graph.add_node("joint-a", name="spine_base")
    sg.graph.add_node("joint-b", name="left_hip")
    sg.graph.add_node("empty-id", name="empty_node")
    sg.graph.add_node("marker-id", name="feature_marker")
    sg.graph.add_edge(
        "member-a",
        "joint-a",
        key="relationship_fact:a",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="fact-a",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode="authored_graph_user_strings",
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
    )
    sg.graph.add_edge(
        "member-b",
        "joint-a",
        key="relationship_fact:b",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="fact-b",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode="authored_graph_user_strings",
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="rest_t_pose",
        fromFeature="pelvis_to_left_hip.end",
        toFeature="spine_base.point",
    )
    sg.graph.add_edge(
        "member-a",
        "joint-b",
        key="relationship_fact:c",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="fact-c",
        provenance="inferred_from_geometry",
        confidence=0.72,
        status="candidate",
        contactKind="point_to_region",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="rest_t_pose",
        fromFeature="spine_base_to_spine_top.end",
        toFeature="left_hip.region",
    )
    sg.graph.add_edge(
        "member-a",
        "empty-id",
        key="spatial:near",
        relationship="near",
        projectionKind="spatial_heuristic_v1",
    )
    return sg


def _zero_summary():
    return {
        "relationshipFactCount": 0,
        "relationshipViewCount": 0,
        "byRelationship": {},
        "byRelationshipCategory": {},
        "byDirection": {},
        "byStatus": {},
        "byProvenance": {},
        "poses": [],
    }


def test_missing_object_ids_is_validation_failure():
    result = query_object_semantic_context(_scene_graph(), object_ids=[])

    assert result == {
        "success": False,
        "error": "missing_object_ids",
        "message": "scene_object_semantic_context requires object_ids in v1",
    }


@pytest.mark.parametrize("bad_object_ids", ["member-a", ("member-a",), ["member-a", 123]])
def test_invalid_object_ids_shape_is_validation_failure(bad_object_ids):
    result = query_object_semantic_context(_scene_graph(), object_ids=bad_object_ids)

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1",
    }


def test_invalid_direction_is_validation_failure():
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a"], direction="sideways")

    assert result == {
        "success": False,
        "error": "invalid_direction",
        "message": "direction must be one of: both, outgoing, incoming",
    }


@pytest.mark.parametrize("kwargs", [{"max_groups": 0}, {"max_facts_per_group": -1}, {"max_groups": True}])
def test_invalid_card_bounds_are_validation_failure(kwargs):
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a"], **kwargs)

    assert result == {
        "success": False,
        "error": "invalid_card_bounds",
        "message": "max_groups and max_facts_per_group must be positive integers in v1",
    }


def test_missing_and_empty_cards_have_full_zero_shape_and_diagnostics():
    result = query_object_semantic_context(_scene_graph(), object_ids=["missing-id", "empty-id"])

    assert result["success"] is True
    assert result["counts"] == {
        "requestedObjectCount": 2,
        "existingSelectedObjectCount": 1,
        "missingSelectedObjectCount": 1,
        "relationshipFactCount": 0,
        "relationshipViewCount": 0,
        "cardCount": 2,
    }
    assert result["cards"][0] == {
        "objectId": "missing-id",
        "exists": False,
        "name": None,
        "objectKind": None,
        "definitionId": None,
        "definitionName": None,
        "canExpandChildren": False,
        "summary": _zero_summary(),
        "groups": [],
        "expandableGroups": [],
    }
    assert result["cards"][1]["objectId"] == "empty-id"
    assert result["cards"][1]["exists"] is True
    assert result["cards"][1]["summary"] == _zero_summary()
    assert result["cards"][1]["groups"] == []
    assert result["diagnostics"]["missingSelectedObjects"] == 1
    assert result["diagnostics"]["noFactsForSelectedObjects"] == 1


def test_card_preserves_order_metadata_summary_and_ignores_fuzzy_edges():
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a", "joint-a", "member-a"])

    assert result["success"] is True
    assert result["projectionKind"] == "relationship_fact_v1"
    assert [card["objectId"] for card in result["cards"]] == ["member-a", "joint-a"]
    assert result["counts"]["requestedObjectCount"] == 2
    assert result["counts"]["cardCount"] == 2
    assert result["counts"]["relationshipFactCount"] == 3
    assert result["counts"]["relationshipViewCount"] == 4

    member = result["cards"][0]
    assert member["name"] == "spine_base_to_spine_top"
    assert member["objectKind"] == "block_instance"
    assert member["definitionId"] == "robot_member_definition"
    assert member["definitionName"] == "RobotMember"
    assert member["canExpandChildren"] is False
    assert member["summary"]["relationshipFactCount"] == 2
    assert member["summary"]["relationshipViewCount"] == 2
    assert member["summary"]["byRelationship"] == {"connects": 1, "supports": 1}
    assert member["summary"]["byDirection"] == {"outgoing": 2}
    assert member["summary"]["byStatus"] == {"accepted": 1, "candidate": 1}
    assert member["summary"]["byProvenance"] == {
        "authored_assembly_graph": 1,
        "inferred_from_geometry": 1,
    }
    assert member["summary"]["poses"] == ["reclined_robot", "rest_t_pose"]
    connects_group = member["groups"][0]
    assert connects_group["relationshipLabel"] == "connects"
    assert connects_group["inverseRelationship"] == "connected by"
    assert connects_group["relationshipCategory"] == "assembly"
    assert member["summary"]["byRelationshipCategory"] == {"assembly": 1, "support": 1}
    assert member["groups"][0]["sampleFacts"][0]["relationshipLabel"] == "connects"
    assert member["groups"][0]["sampleFacts"][0]["contactKindLabel"] == "point to point"
    assert member["groups"][1]["relationshipCategory"] == "support"

    joint = result["cards"][1]
    assert joint["summary"]["relationshipFactCount"] == 2
    assert joint["summary"]["relationshipViewCount"] == 2
    assert joint["summary"]["byDirection"] == {"incoming": 2}


def test_groups_are_deterministic_and_sample_facts_keep_raw_fields():
    result = query_object_semantic_context(_scene_graph(), object_ids=["joint-a"])

    groups = result["cards"][0]["groups"]
    assert [group["groupKey"] for group in groups] == [
        "connects:incoming:accepted:authored_assembly_graph"
    ]
    group = groups[0]
    assert group["relationship"] == "connects"
    assert group["direction"] == "incoming"
    assert group["status"] == "accepted"
    assert group["provenance"] == "authored_assembly_graph"
    assert group["count"] == 2
    assert group["truncated"] is False
    assert [fact["relationshipFactId"] for fact in group["sampleFacts"]] == ["fact-b", "fact-a"]
    assert group["sampleFacts"][0]["fromFeature"] == "pelvis_to_left_hip.end"
    assert group["sampleFacts"][0]["toFeature"] == "spine_base.point"
    assert group["sampleFacts"][0]["graphSource"] == "pearson_robot_skeleton_graph"
    assert group["sampleFacts"][0]["graphRevision"] == "g002"
    assert group["sampleFacts"][0]["pose"] == "rest_t_pose"
    assert "connected by pelvis_to_left_hip" in group["lines"][0]


def test_max_facts_per_group_truncates_samples_and_lines():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["joint-a"],
        max_facts_per_group=1,
    )

    group = result["cards"][0]["groups"][0]
    assert group["count"] == 2
    assert group["truncated"] is True
    assert [fact["relationshipFactId"] for fact in group["sampleFacts"]] == ["fact-b"]
    assert len(group["lines"]) == 1


def test_max_groups_populates_expandable_groups():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        max_groups=1,
    )

    card = result["cards"][0]
    assert len(card["groups"]) == 1
    assert card["groups"][0]["groupKey"] == "connects:outgoing:accepted:authored_assembly_graph"
    assert card["expandableGroups"] == [
        {
            "groupKey": "supports:outgoing:candidate:inferred_from_geometry",
            "relationship": "supports",
            "direction": "outgoing",
            "status": "candidate",
            "provenance": "inferred_from_geometry",
            "relationshipLabel": "supports",
            "inverseRelationship": "supported by",
            "relationshipCategory": "support",
            "count": 1,
            "reason": "group_limit",
        }
    ]


def test_filters_are_forwarded_to_raw_inspector_before_grouping():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        relationship_types=["supports"],
        status=["candidate"],
        provenance=["inferred_from_geometry"],
        poses=["rest_t_pose"],
    )

    card = result["cards"][0]
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    assert card["summary"]["byRelationship"] == {"supports": 1}
    assert card["groups"][0]["groupKey"] == "supports:outgoing:candidate:inferred_from_geometry"
    assert result["diagnostics"]["filteredByRelationshipType"] == 1


def test_empty_graph_reports_projection_required_without_no_facts_for_selection():
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-a", name="member")

    result = query_object_semantic_context(sg, object_ids=["member-a"])

    assert result["success"] is True
    assert result["diagnostics"]["noProjectedRelationshipFacts"] == 1
    assert result["diagnostics"]["projectionRequired"] == 1
    assert "noFactsForSelectedObjects" not in result["diagnostics"]


def test_project_profile_enriches_card_labels(tmp_path):
    profile_dir = tmp_path / ".rook"
    profile_dir.mkdir()
    (profile_dir / "relationship_profile.json").write_text(
        """
{
  "schema": "rook.relationship_profile.v1",
  "relationships": {
    "supports": {
      "label": "props up",
      "category": "structural_support"
    }
  },
  "contactKinds": {
    "point_to_region": {
      "label": "bearing point to region"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        relationship_types=["supports"],
        project_root=str(tmp_path),
    )

    assert result["success"] is True
    group = result["cards"][0]["groups"][0]
    assert group["relationship"] == "supports"
    assert group["relationshipLabel"] == "props up"
    assert group["inverseRelationship"] == "supported by"
    assert group["relationshipCategory"] == "structural_support"
    assert group["sampleFacts"][0]["relationshipLabel"] == "props up"
    assert group["sampleFacts"][0]["contactKindLabel"] == "bearing point to region"
    assert result["cards"][0]["summary"]["byRelationshipCategory"] == {"structural_support": 1}


def test_invalid_project_profile_fails_card_request(tmp_path):
    profile_dir = tmp_path / ".rook"
    profile_dir.mkdir()
    (profile_dir / "relationship_profile.json").write_text(
        '{"schema": "wrong.schema", "relationships": {}}',
        encoding="utf-8",
    )

    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        project_root=str(tmp_path),
    )

    assert result == {
        "success": False,
        "error": "invalid_relationship_profile",
        "message": "Project relationship profile is invalid",
        "diagnostics": {"invalidSchema": 1},
    }
