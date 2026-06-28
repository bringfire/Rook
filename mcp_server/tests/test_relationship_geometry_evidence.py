from __future__ import annotations

import pytest

from rook.scene.relationship_geometry_evidence import query_relationship_evidence
from rook.scene.scene_graph import SceneGraphAnalytics


def _empty_scene_graph() -> SceneGraphAnalytics:
    return SceneGraphAnalytics()


def test_query_relationship_evidence_rejects_bad_object_ids():
    result = query_relationship_evidence(_empty_scene_graph(), object_ids="owner-id")

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "object_ids must be a list of strings when supplied",
    }


def test_query_relationship_evidence_rejects_bad_list_filters():
    result = query_relationship_evidence(_empty_scene_graph(), poses="architectural_reference")

    assert result == {
        "success": False,
        "error": "invalid_poses",
        "message": "poses must be a list of strings when supplied",
    }


@pytest.mark.parametrize("value", [None, "0.01", -0.1, float("inf"), True])
def test_query_relationship_evidence_rejects_invalid_tolerance(value):
    result = query_relationship_evidence(_empty_scene_graph(), tolerance_m=value)

    assert result["success"] is False
    assert result["error"] == "invalid_tolerance_m"
    assert result["message"] == "tolerance_m must be a finite number greater than or equal to 0"


def test_query_relationship_evidence_returns_empty_success_without_projected_facts():
    result = query_relationship_evidence(_empty_scene_graph())

    assert result == {
        "success": True,
        "projectionKind": "relationship_fact_v1",
        "evidenceKind": "relationship_geometry_evidence_v1",
        "method": "feature_marker_position_distance",
        "counts": {
            "matchingRelationshipFactCount": 0,
            "evidenceRecordCount": 0,
            "measuredEvidenceCount": 0,
            "missingEvidenceCount": 0,
            "withinToleranceCount": 0,
            "outsideToleranceCount": 0,
            "hydratedFeatureObjectCount": 0,
        },
        "records": [],
        "diagnostics": {
            "noProjectedRelationshipFacts": 1,
        },
    }


def _scene_graph_with_projected_edges() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_node("door-owner", name="door_01")
    sg.graph.add_node("wall-owner", name="wall_01")
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="relationship_fact:architectural:supports",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="column_01.top_point_supports_slab_01.underside_region",
        fromFeature="column_01.top_point",
        toFeature="slab_01.underside_region",
        fromFeatureObjectId="feature-column-top",
        toFeatureObjectId="feature-slab-underside",
        contactKind="point_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "door-owner",
        "wall-owner",
        key="relationship_fact:architectural:hosted",
        relationship="hosted_by",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="hosted_by",
        relationshipFactId="door_01.body_hosted_by_wall_01.host_region",
        fromFeature="door_01.body",
        toFeature="wall_01.host_region",
        fromFeatureObjectId="feature-door-body",
        toFeatureObjectId="feature-wall-host",
        contactKind="body_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "column-owner",
        "wall-owner",
        key="spatial-near",
        relationship="near",
        distance=0.2,
    )
    return sg


def _positions() -> dict[str, dict[str, str]]:
    return {
        "feature-column-top": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-slab-underside": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-door-body": {"rook.graph.true_position_m": "[2.0, -0.1, 1.0]"},
        "feature-wall-host": {"rook.graph.true_position_m": "[2.0, 0.0, 1.0]"},
    }


def test_query_relationship_evidence_filters_by_graph_scope_and_relationship_type():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        graph_source="architectural_relationship_fixture",
        graph_revision="a001",
        poses=["architectural_reference"],
        relationship_types=["supports"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["success"] is True
    assert result["counts"]["matchingRelationshipFactCount"] == 1
    assert result["counts"]["evidenceRecordCount"] == 1
    assert result["records"][0]["relationship"] == "supports"
    assert result["records"][0]["relationshipFactId"] == "column_01.top_point_supports_slab_01.underside_region"
    assert "filteredByRelationshipType" in result["diagnostics"]


def test_query_relationship_evidence_filters_by_object_ids_and_fact_ids():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        object_ids=["door-owner"],
        relationship_fact_ids=["door_01.body_hosted_by_wall_01.host_region"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["success"] is True
    assert result["counts"]["matchingRelationshipFactCount"] == 1
    assert result["records"][0]["fromObjectId"] == "door-owner"
    assert result["records"][0]["toObjectId"] == "wall-owner"
    assert result["records"][0]["relationship"] == "hosted_by"


def test_query_relationship_evidence_measures_distance_inside_tolerance():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        tolerance_m=0.01,
        feature_user_strings_by_id=_positions(),
    )

    evidence = result["records"][0]["evidence"]
    assert evidence == {
        "kind": "relationship_geometry_evidence_v1",
        "method": "feature_marker_position_distance",
        "status": "measured",
        "distanceM": 0.0,
        "toleranceM": 0.01,
        "withinTolerance": True,
        "source": "rhino_user_text_feature_positions",
    }
    assert result["counts"]["measuredEvidenceCount"] == 1
    assert result["counts"]["withinToleranceCount"] == 1
    assert result["counts"]["outsideToleranceCount"] == 0


def test_query_relationship_evidence_measures_distance_outside_tolerance():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["hosted_by"],
        tolerance_m=0.01,
        feature_user_strings_by_id=_positions(),
    )

    evidence = result["records"][0]["evidence"]
    assert evidence["status"] == "measured"
    assert evidence["distanceM"] == pytest.approx(0.1)
    assert evidence["toleranceM"] == 0.01
    assert evidence["withinTolerance"] is False
    assert result["counts"]["outsideToleranceCount"] == 1
    assert result["diagnostics"]["outsideTolerance"] == 1


def test_query_relationship_evidence_reports_missing_feature_object_id():
    sg = _scene_graph_with_projected_edges()
    edge_attrs = list(sg.graph["column-owner"]["slab-owner"].values())[0]
    edge_attrs.pop("fromFeatureObjectId")

    result = query_relationship_evidence(
        sg,
        relationship_types=["supports"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["fromFeatureObjectId"]
    assert result["diagnostics"]["missingFeatureObjectId"] == 1


def test_query_relationship_evidence_reports_missing_user_text():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        feature_user_strings_by_id={"feature-slab-underside": _positions()["feature-slab-underside"]},
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["fromFeatureUserText"]
    assert result["diagnostics"]["missingFeatureUserText"] == 1


def test_query_relationship_evidence_reports_invalid_position():
    positions = dict(_positions())
    positions["feature-slab-underside"] = {"rook.graph.true_position_m": "[0.0, 0.0]"}

    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        feature_user_strings_by_id=positions,
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["toFeaturePosition"]
    assert result["diagnostics"]["invalidFeaturePosition"] == 1
