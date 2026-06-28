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
