from __future__ import annotations

from rook.scene.scene_graph import SceneGraphAnalytics


def _empty_scene_graph() -> SceneGraphAnalytics:
    return SceneGraphAnalytics()


def _claim_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_node("door-owner", name="door_01")
    sg.graph.add_node("wall-owner", name="wall_01")
    sg.graph.add_node("beam-owner", name="beam_01")
    sg.graph.add_node("plate-owner", name="plate_01")
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
        "beam-owner",
        "plate-owner",
        key="relationship_fact:architectural:connects",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="beam_01.end_connects_plate_01.socket",
        fromFeature="beam_01.end",
        toFeature="plate_01.socket",
        fromFeatureObjectId="feature-beam-end",
        toFeatureObjectId="feature-plate-socket",
        contactKind="point_to_point",
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


def test_relationship_kernel_constants():
    from rook.scene import relationship_kernel

    assert relationship_kernel.REPORT_SCHEMA == "rook.relationship_kernel_report.v1"
    assert relationship_kernel.CLAIM_PROJECTION_KIND == "relationship_fact_v1"
    assert relationship_kernel.EXACT_RELATIONSHIP == "adjacent_exact"
    assert relationship_kernel.EVIDENCE_STRENGTH_ORDER == (
        "none",
        "marker_hint",
        "bbox_observation",
        "exact_topology",
        "explicit_connector",
    )


def test_relationship_kernel_empty_report_without_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    report = query_relationship_kernel_report(_empty_scene_graph())

    assert report == {
        "success": True,
        "schema": "rook.relationship_kernel_report.v1",
        "counts": {
            "relationshipClaimCount": 0,
            "evidenceCount": 0,
            "interfaceRecordCount": 0,
            "verdictCount": 0,
            "byVerdict": {},
        },
        "claims": [],
        "evidence": [],
        "interfaceRecords": [],
        "verdicts": [],
        "diagnostics": {"noRelationshipClaims": 1},
    }


def test_relationship_kernel_normalizes_relationship_fact_edges_to_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    report = query_relationship_kernel_report(
        _claim_graph(),
        graph_source="architectural_relationship_fixture",
        graph_revision="a001",
        poses=["architectural_reference"],
    )

    assert report["counts"]["relationshipClaimCount"] == 3
    assert report["counts"]["evidenceCount"] == 0
    assert report["counts"]["interfaceRecordCount"] == 0
    assert report["counts"]["verdictCount"] == 3
    assert report["counts"]["byVerdict"] == {
        "not_applicable": 2,
        "unverified": 1,
    }
    assert [claim["relationshipClaimId"] for claim in report["claims"]] == [
        "beam_01.end_connects_plate_01.socket",
        "column_01.top_point_supports_slab_01.underside_region",
        "door_01.body_hosted_by_wall_01.host_region",
    ]

    supports_claim = report["claims"][1]
    assert supports_claim == {
        "relationshipClaimId": "column_01.top_point_supports_slab_01.underside_region",
        "relationship": "supports",
        "claimTypeField": "supports",
        "fromObjectId": "column-owner",
        "toObjectId": "slab-owner",
        "fromFeature": "column_01.top_point",
        "toFeature": "slab_01.underside_region",
        "fromFeatureObjectId": "feature-column-top",
        "toFeatureObjectId": "feature-slab-underside",
        "contactKind": "point_to_region",
        "provenance": "authored_architectural_fixture",
        "confidence": 1.0,
        "status": "accepted",
        "graphSource": "architectural_relationship_fixture",
        "graphRevision": "a001",
        "pose": "architectural_reference",
        "physicalObligation": None,
        "edgeKey": "relationship_fact:architectural:supports",
    }
    assert "method" not in supports_claim


def test_relationship_kernel_filters_claims_without_treating_fuzzy_edges_as_claims():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    report = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["supports"],
        object_ids=["column-owner", "beam-owner"],
    )

    assert report["counts"]["relationshipClaimCount"] == 1
    assert report["claims"][0]["relationship"] == "supports"
    assert report["diagnostics"]["filteredByRelationshipType"] == 1
    assert all(claim["relationship"] != "near" for claim in report["claims"])
