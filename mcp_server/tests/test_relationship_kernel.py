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


def test_connects_adjacent_exact_edge_becomes_exact_topology_evidence_and_interface_record():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "beam-owner",
        "plate-owner",
        key="occt:adjacent_exact",
        relationship="adjacent_exact",
        sharedArea=12.5,
        lengthUnit="meters",
        areaUnit="square_meters",
        facePairs=[["face-a", "face-b"]],
        graphSequence=17,
        engineVersion="occt-test",
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["relationshipClaimCount"] == 1
    assert report["counts"]["evidenceCount"] == 1
    assert report["counts"]["interfaceRecordCount"] == 1
    interface = report["interfaceRecords"][0]
    assert interface["kind"] == "interface_record_v1"
    assert interface["interfaceType"] == "shared_topology"
    assert interface["method"] == "adjacent_exact"
    assert interface["source"] == "occt"
    assert interface["objectIds"] == ["beam-owner", "plate-owner"]
    assert interface["interfaceScope"] == "owner_pair"
    assert interface["featurePaths"] == ["beam_01.end", "plate_01.socket"]
    assert interface["featureScopeVerified"] is False
    assert interface["measures"]["sharedArea"] == 12.5

    evidence = report["evidence"][0]
    assert evidence["kind"] == "relationship_evidence_v1"
    assert evidence["relationshipClaimId"] == "beam_01.end_connects_plate_01.socket"
    assert evidence["method"] == "adjacent_exact"
    assert evidence["strength"] == "exact_topology"
    assert evidence["polarity"] == "supports"
    assert evidence["status"] == "measured"
    assert evidence["claimTypeField"] == "connects"
    assert evidence["evidenceMethodField"] == "adjacent_exact"
    assert evidence["interfaceRecordIds"] == [interface["interfaceRecordId"]]

    assert report["verdicts"][0]["verdict"] == "satisfied"
    assert report["verdicts"][0]["reason"] == "exact_topology_supports_owner_contact"


def test_connects_adjacent_exact_edge_is_orientation_independent_for_claim_endpoints():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "plate-owner",
        "beam-owner",
        key="occt:adjacent_exact:reverse",
        relationship="adjacent_exact",
        sharedArea=4.0,
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 1
    assert report["interfaceRecords"][0]["objectIds"] == ["beam-owner", "plate-owner"]
    assert report["verdicts"][0]["verdict"] == "satisfied"


def test_supports_requires_explicit_direct_contact_obligation_for_adjacent_exact_satisfaction():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="occt:adjacent_exact:supports",
        relationship="adjacent_exact",
        sharedArea=2.0,
    )

    report = query_relationship_kernel_report(sg, relationship_types=["supports"])

    assert report["counts"]["evidenceCount"] == 1
    assert report["evidence"][0]["strength"] == "exact_topology"
    assert report["verdicts"][0]["verdict"] == "not_applicable"
    assert report["verdicts"][0]["reason"] == "no_v1_physical_obligation"


def test_absent_adjacent_exact_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    report = query_relationship_kernel_report(_claim_graph(), relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 0
    assert report["verdicts"][0]["verdict"] == "unverified"
    assert report["verdicts"][0]["reason"] == "no_applicable_exact_topology_evidence"


def test_exact_refuted_annotation_becomes_contradicting_evidence():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "beam-owner",
        "plate-owner",
        key="spatial-adjacent",
        relationship="adjacent",
        exact_status="exact_refuted",
        exact_reason="no_shared_face",
        exact_graphSequence=42,
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 1
    evidence = report["evidence"][0]
    assert evidence["method"] == "adjacent_exact_refutation"
    assert evidence["strength"] == "exact_topology"
    assert evidence["polarity"] == "contradicts"
    assert evidence["status"] == "measured"
    assert evidence["measures"]["reason"] == "no_shared_face"
    assert report["verdicts"][0]["verdict"] == "contradicted"
    assert report["verdicts"][0]["reason"] == "explicit_exact_topology_refutation"


def test_exact_refuted_annotation_on_unrelated_pair_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "column-owner",
        "beam-owner",
        key="unrelated-spatial-adjacent",
        relationship="adjacent",
        exact_status="exact_refuted",
        exact_graphSequence=42,
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 0
    assert report["verdicts"][0]["verdict"] == "unverified"


def test_non_adjacent_exact_refuted_annotation_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "beam-owner",
        "plate-owner",
        key="analysis-note",
        relationship="analysis_note",
        exact_status="exact_refuted",
        exact_graphSequence=42,
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 0
    assert report["verdicts"][0]["verdict"] == "unverified"


def test_exact_refuted_annotation_without_graph_sequence_does_not_contradict_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    sg = _claim_graph()
    sg.graph.add_edge(
        "beam-owner",
        "plate-owner",
        key="spatial-adjacent-no-sequence",
        relationship="adjacent",
        exact_status="exact_refuted",
    )

    report = query_relationship_kernel_report(sg, relationship_types=["connects"])

    assert report["counts"]["evidenceCount"] == 0
    assert report["verdicts"][0]["verdict"] == "unverified"


def test_marker_evidence_is_marker_hint_and_does_not_satisfy_physical_claim():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    marker_records = [
        {
            "relationshipFactId": "beam_01.end_connects_plate_01.socket",
            "relationship": "connects",
            "evidence": {
                "kind": "relationship_geometry_evidence_v1",
                "method": "feature_marker_position_distance",
                "status": "measured",
                "distanceM": 0.0,
                "toleranceM": 0.01,
                "withinTolerance": True,
                "source": "rhino_user_text_feature_positions",
            },
        }
    ]

    report = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["connects"],
        marker_evidence_records=marker_records,
    )

    evidence = report["evidence"][0]
    assert evidence["method"] == "feature_marker_position_distance"
    assert evidence["strength"] == "marker_hint"
    assert evidence["polarity"] == "supports"
    assert evidence["status"] == "measured"
    assert report["verdicts"][0]["verdict"] == "unverified"
    assert report["verdicts"][0]["strongestEvidence"] == "marker_hint"


def test_missing_marker_evidence_is_missing_and_keeps_claim_unverified():
    from rook.scene.relationship_kernel import query_relationship_kernel_report

    marker_records = [
        {
            "relationshipFactId": "beam_01.end_connects_plate_01.socket",
            "relationship": "connects",
            "evidence": {
                "kind": "relationship_geometry_evidence_v1",
                "method": "feature_marker_position_distance",
                "status": "missing",
                "missing": ["fromFeaturePosition"],
                "source": "rhino_user_text_feature_positions",
            },
        }
    ]

    report = query_relationship_kernel_report(
        _claim_graph(),
        relationship_types=["connects"],
        marker_evidence_records=marker_records,
    )

    evidence = report["evidence"][0]
    assert evidence["strength"] == "marker_hint"
    assert evidence["polarity"] == "missing"
    assert evidence["status"] == "missing"
    assert evidence["diagnostics"]["missing"] == ["fromFeaturePosition"]
    assert report["verdicts"][0]["verdict"] == "unverified"
