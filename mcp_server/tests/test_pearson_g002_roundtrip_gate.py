from __future__ import annotations

from pathlib import Path

from .pearson_g002_roundtrip_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_PATH,
    build_expected_facts,
    embedded_graph_from_generated_script,
    load_assembly_graph,
    pearson_fact_counts_by_pose,
    pearson_mismatch_report,
)


def test_pearson_expected_facts_expand_across_both_poses():
    graph = load_assembly_graph(GRAPH_PATH)

    facts = build_expected_facts(graph)

    assert len(graph["relationships"]) == 28
    assert set(graph["poses"]) == {"rest_t_pose", "reclined_robot"}
    assert len(facts) == 56
    assert pearson_fact_counts_by_pose(facts) == {
        "reclined_robot": 28,
        "rest_t_pose": 28,
    }
    assert {
        "relationship": "connects",
        "fromFeature": "spine_base_to_spine_top.start",
        "toFeature": "spine_base.point",
        "contactKind": "point_to_point",
        "provenance": "authored_assembly_graph",
        "status": "accepted",
        "graphSource": "pearson_robot_skeleton_graph",
        "graphRevision": "g002",
        "pose": "rest_t_pose",
    } in facts
    assert {
        "relationship": "connects",
        "fromFeature": "right_knee_to_right_foot.end",
        "toFeature": "right_foot.point",
        "contactKind": "point_to_point",
        "provenance": "authored_assembly_graph",
        "status": "accepted",
        "graphSource": "pearson_robot_skeleton_graph",
        "graphRevision": "g002",
        "pose": "reclined_robot",
    } in facts


def test_generated_pearson_fixture_payload_matches_assembly_graph():
    assembly_graph = load_assembly_graph(GRAPH_PATH)
    embedded_graph = embedded_graph_from_generated_script(GENERATED_SCRIPT_PATH)

    assert embedded_graph["revision"] == assembly_graph["revision"] == "g002"
    assert set(embedded_graph["poses"]) == set(assembly_graph["poses"])
    assert len(embedded_graph["nodes"]) == len(assembly_graph["nodes"]) == 15
    assert len(embedded_graph["members"]) == len(assembly_graph["members"]) == 14
    assert len(embedded_graph["features"]) == len(assembly_graph["features"]) == 43
    assert len(embedded_graph["relationships"]) == len(assembly_graph["relationships"]) == 28
    assert {
        relationship["id"] for relationship in embedded_graph["relationships"]
    } == {
        relationship["id"] for relationship in assembly_graph["relationships"]
    }


def test_pearson_mismatch_report_adds_pose_counts():
    report = pearson_mismatch_report(
        roundtrip_report={
            "success": False,
            "missingFacts": [{"pose": "rest_t_pose"}],
            "unexpectedFacts": [],
            "wrongMetadata": [],
            "missingContextSubstrings": [],
        },
        actual_facts=[
            {"pose": "rest_t_pose"},
            {"pose": "reclined_robot"},
            {"pose": "reclined_robot"},
        ],
        expected_facts=[
            {"pose": "rest_t_pose"},
            {"pose": "rest_t_pose"},
            {"pose": "reclined_robot"},
        ],
        fixture_summary={"revision": "g002", "created_count": 200},
    )

    assert report["success"] is False
    assert report["expectedByPose"] == {"reclined_robot": 1, "rest_t_pose": 2}
    assert report["actualByPose"] == {"reclined_robot": 2, "rest_t_pose": 1}
    assert report["fixtureSummary"] == {"revision": "g002", "created_count": 200}
