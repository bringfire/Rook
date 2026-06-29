from __future__ import annotations

import json

import pytest

from .architectural_fixture_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_architectural_card_expectations,
    assert_fixture_summary,
    build_expected_facts,
    extract_projected_facts,
    json_from_execute_output,
    load_architectural_graph,
    object_ids_for_features,
    query_fixture_cards,
    query_fixture_semantic_relationships,
    script_output_from_execute_result,
    semantic_facts,
)
from .conftest import _is_error, fresh_document


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


SELECTED_FEATURE_PAIRS = [
    ("column_01.top_point", "slab_01.underside_region"),
    ("door_01.body", "wall_01.host_region"),
    ("duct_01.centerline", "wall_01.penetration_region"),
    ("space_01.boundary", "wall_01.inner_face"),
]


async def _create_architectural_fixture() -> dict:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute architectural fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


async def test_architectural_relationship_fixture_roundtrip_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph

    graph = load_architectural_graph()
    expected_facts = build_expected_facts(graph)
    fixture_summary = await _create_architectural_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
        strict=True,
        analytics=sg,
    )

    assert projection["success"] is True, f"projection failed: {projection!r}"
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 5
    assert counts["projectedEdgeCount"] == 5
    assert counts["skippedFactCount"] == 0
    assert projection["byRelationshipType"] == {
        "bounded_by": 1,
        "hosted_by": 1,
        "penetrates": 1,
        "supports": 1,
        "voids": 1,
    }
    assert projection["byPose"] == {POSE: 5}

    actual_facts = extract_projected_facts(sg)
    report = compare_roundtrip(
        expected_facts=expected_facts,
        actual_facts=semantic_facts(actual_facts),
        context_text="",
        required_substrings=[],
    )
    if not report["success"]:
        report["fixtureSummary"] = fixture_summary
        report["actualFacts"] = actual_facts
        report["projectionCounts"] = counts
        pytest.fail(json.dumps(report, indent=2, sort_keys=True))

    selected_from_projection = object_ids_for_features(actual_facts, SELECTED_FEATURE_PAIRS)
    expected_selected_subset = {
        fixture_summary["ownerObjectIds"]["column_01"],
        fixture_summary["ownerObjectIds"]["slab_01"],
        fixture_summary["ownerObjectIds"]["door_01"],
        fixture_summary["ownerObjectIds"]["wall_01"],
        fixture_summary["ownerObjectIds"]["duct_01"],
        fixture_summary["ownerObjectIds"]["space_01"],
    }
    assert set(selected_from_projection) == expected_selected_subset, (
        f"unexpected projected object ids: {selected_from_projection!r}; "
        f"expected={expected_selected_subset!r}; facts={actual_facts!r}"
    )

    selected_object_ids = [
        fixture_summary["ownerObjectIds"][owner_id]
        for owner_id in sorted(fixture_summary["ownerObjectIds"])
    ]

    inspector = query_fixture_semantic_relationships(sg, selected_object_ids)
    assert inspector["success"] is True, inspector
    assert inspector["counts"]["relationshipFactCount"] == 5
    assert inspector["counts"]["relationshipViewCount"] == 10

    cards = query_fixture_cards(sg, selected_object_ids)
    assert_architectural_card_expectations(cards, fixture_summary["ownerObjectIds"])

    card_text = json.dumps(cards, sort_keys=True)
    for substring in [
        "supports",
        "hosted_by",
        "penetrates",
        "bounded_by",
        "column_01.top_point",
        "slab_01.underside_region",
        "door_01.body",
        "wall_01.host_region",
        "duct_01.centerline",
        "wall_01.penetration_region",
        "space_01.boundary",
        "wall_01.inner_face",
        "accepted",
        "authored_architectural_fixture",
    ]:
        assert substring in card_text
