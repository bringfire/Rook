from __future__ import annotations

import json
from typing import Any

import pytest

from .conftest import _is_error, fresh_document
from .pearson_g002_roundtrip_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_PATH,
    GRAPH_SOURCE,
    assert_fixture_summary,
    build_expected_facts,
    extract_projected_facts,
    json_from_execute_output,
    load_assembly_graph,
    object_ids_for_feature_pairs,
    pearson_mismatch_report,
    script_output_from_execute_result,
    semantic_facts,
)


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


SELECTED_CONTEXT_PAIRS = [
    ("spine_base_to_spine_top.start", "spine_base.point"),
    ("spine_top_to_left_shoulder.end", "left_shoulder.point"),
    ("left_hip_to_left_knee.end", "left_knee.point"),
    ("right_knee_to_right_foot.end", "right_foot.point"),
]

REQUIRED_CONTEXT_SUBSTRINGS = [
    "connects",
    "connected by",
    "spine_base_to_spine_top.start -> spine_base.point",
    "spine_top_to_left_shoulder.end -> left_shoulder.point",
    "left_hip_to_left_knee.end -> left_knee.point",
    "right_knee_to_right_foot.end -> right_foot.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


async def _create_pearson_fixture() -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute Pearson fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


async def test_pearson_g002_roundtrip_scale_gate_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph
    from rook.server import _call_tool_dispatch

    expected_facts = build_expected_facts(load_assembly_graph(GRAPH_PATH))
    fixture_summary = await _create_pearson_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=GRAPH_SOURCE,
        graph_revision="g002",
        strict=True,
        analytics=sg,
    )

    assert projection["success"] is True, f"projection failed: {projection!r}"
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 56
    assert counts["projectedEdgeCount"] == 56
    assert counts["skippedFactCount"] == 0
    assert projection["byRelationshipType"] == {"connects": 56}
    assert projection["byPose"] == {
        "reclined_robot": 28,
        "rest_t_pose": 28,
    }

    actual_facts = extract_projected_facts(sg)
    selected_object_ids = object_ids_for_feature_pairs(actual_facts, SELECTED_CONTEXT_PAIRS)
    assert selected_object_ids, f"no owner object ids found for selected context pairs: {actual_facts!r}"

    context_result = await _call_tool_dispatch(
        "scene_context",
        {
            "object_ids": selected_object_ids,
            "sync": False,
        },
    )
    assert context_result["success"] is True, f"scene_context failed: {context_result!r}"

    report = compare_roundtrip(
        expected_facts=expected_facts,
        actual_facts=semantic_facts(actual_facts),
        context_text=context_result["data"],
        required_substrings=REQUIRED_CONTEXT_SUBSTRINGS,
    )
    if not report["success"]:
        enriched = pearson_mismatch_report(
            roundtrip_report=report,
            actual_facts=actual_facts,
            expected_facts=expected_facts,
            fixture_summary=fixture_summary,
        )
        enriched["selectedObjectIds"] = selected_object_ids
        enriched["projectionCounts"] = counts
        pytest.fail(json.dumps(enriched, indent=2, sort_keys=True))
