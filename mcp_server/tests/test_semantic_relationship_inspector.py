import pytest

from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.semantic_relationship_inspector import query_semantic_relationships


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-id", name="spine_base_to_spine_top", domain_label="member")
    sg.graph.add_node("joint-id", name="spine_base", domain_label="joint")
    sg.graph.add_node("other-id", name="unrelated", domain_label="marker")
    sg.graph.add_node("missing-peer-id", name="unused", domain_label="marker")
    sg.graph.add_edge(
        "member-id",
        "joint-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:spine",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="spine_base_to_spine_top.start_connects_spine_base",
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
        relationshipObjectId="relationship-marker-id",
        fromFeatureObjectId="feature-member-start-id",
        toFeatureObjectId="feature-joint-point-id",
        engineVersion=1,
    )
    sg.graph.add_edge(
        "member-id",
        "other-id",
        key="spatial:near",
        relationship="near",
        projectionKind="spatial_heuristic_v1",
    )
    return sg


def test_missing_object_ids_is_validation_failure():
    result = query_semantic_relationships(_scene_graph(), object_ids=[])

    assert result == {
        "success": False,
        "error": "missing_object_ids",
        "message": "scene_semantic_relationships requires object_ids in v1",
    }


def test_invalid_direction_is_validation_failure():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id"], direction="sideways")

    assert result == {
        "success": False,
        "error": "invalid_direction",
        "message": "direction must be one of: both, outgoing, incoming",
    }


def test_object_entries_preserve_input_order_and_missing_objects():
    result = query_semantic_relationships(
        _scene_graph(),
        object_ids=["missing-id", "member-id", "missing-id", "other-id"],
    )

    assert result["success"] is True
    assert result["counts"]["requestedObjectCount"] == 3
    assert result["counts"]["existingSelectedObjectCount"] == 2
    assert result["counts"]["missingSelectedObjectCount"] == 1
    assert [entry["objectId"] for entry in result["objects"]] == ["missing-id", "member-id", "other-id"]
    assert result["objects"][0] == {
        "objectId": "missing-id",
        "exists": False,
        "name": None,
        "facts": [],
        "lines": [],
    }
    assert result["diagnostics"]["missingSelectedObjects"] == 1


def test_outgoing_fact_ignores_fuzzy_edges_and_reports_structured_fields():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id"])

    assert result["success"] is True
    assert result["projectionKind"] == "relationship_fact_v1"
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    member = result["objects"][0]
    assert member["exists"] is True
    assert member["name"] == "spine_base_to_spine_top"
    assert len(member["facts"]) == 1
    fact = member["facts"][0]
    assert fact["direction"] == "outgoing"
    assert fact["relationship"] == "connects"
    assert fact["objectId"] == "member-id"
    assert fact["otherObjectId"] == "joint-id"
    assert fact["otherName"] == "spine_base"
    assert fact["fromFeature"] == "spine_base_to_spine_top.start"
    assert fact["toFeature"] == "spine_base.point"
    assert fact["contactKind"] == "point_to_point"
    assert fact["provenance"] == "authored_assembly_graph"
    assert fact["confidence"] == 1.0
    assert fact["status"] == "accepted"
    assert fact["graphSource"] == "pearson_robot_skeleton_graph"
    assert fact["graphRevision"] == "g002"
    assert fact["pose"] == "reclined_robot"
    assert "connects spine_base via spine_base_to_spine_top.start -> spine_base.point" in member["lines"][0]


def test_incoming_direction_view_for_target_object():
    result = query_semantic_relationships(_scene_graph(), object_ids=["joint-id"])

    joint = result["objects"][0]
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    assert joint["facts"][0]["direction"] == "incoming"
    assert joint["facts"][0]["otherObjectId"] == "member-id"
    assert "connected by spine_base_to_spine_top" in joint["lines"][0]


def test_selecting_both_endpoints_counts_unique_fact_and_two_views():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"])

    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 2
    assert [len(entry["facts"]) for entry in result["objects"]] == [1, 1]
    assert result["objects"][0]["facts"][0]["direction"] == "outgoing"
    assert result["objects"][1]["facts"][0]["direction"] == "incoming"


def test_direction_filter_is_relative_to_selected_object():
    outgoing = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"], direction="outgoing")
    incoming = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"], direction="incoming")

    assert outgoing["counts"]["relationshipFactCount"] == 1
    assert outgoing["counts"]["relationshipViewCount"] == 1
    assert [len(entry["facts"]) for entry in outgoing["objects"]] == [1, 0]
    assert incoming["counts"]["relationshipFactCount"] == 1
    assert incoming["counts"]["relationshipViewCount"] == 1
    assert [len(entry["facts"]) for entry in incoming["objects"]] == [0, 1]


def test_filters_apply_before_grouping_and_report_filter_diagnostics():
    result = query_semantic_relationships(
        _scene_graph(),
        object_ids=["member-id"],
        graph_source="other_source",
        graph_revision="g002",
        poses=["reclined_robot"],
        relationship_types=["connects"],
        status=["accepted"],
        provenance=["authored_assembly_graph"],
    )

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 0
    assert result["counts"]["relationshipViewCount"] == 0
    assert result["diagnostics"]["filteredByGraphSource"] == 1
    assert result["diagnostics"]["noFactsForSelectedObjects"] == 1


def test_empty_graph_diagnostics_distinguish_no_projection_from_no_facts_for_selection():
    no_projection = SceneGraphAnalytics()
    no_projection.graph.add_node("member-id", name="member")

    result = query_semantic_relationships(no_projection, object_ids=["member-id"])

    assert result["diagnostics"]["noProjectedRelationshipFacts"] == 1
    assert result["diagnostics"]["projectionRequired"] == 1
    assert "noFactsForSelectedObjects" not in result["diagnostics"]

    existing_projection = query_semantic_relationships(_scene_graph(), object_ids=["other-id"])
    assert existing_projection["diagnostics"]["noFactsForSelectedObjects"] == 1
    assert "noProjectedRelationshipFacts" not in existing_projection["diagnostics"]
