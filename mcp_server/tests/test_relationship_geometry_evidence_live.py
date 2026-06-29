from __future__ import annotations

import json

import pytest

from .architectural_fixture_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_fixture_summary,
    json_from_execute_output,
    script_output_from_execute_result,
)
from .conftest import _is_error, fresh_document


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _create_architectural_fixture() -> dict:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute architectural fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


def _record_by_relationship(records: list[dict], relationship: str) -> dict:
    for record in records:
        if record["relationship"] == relationship:
            return record
    raise AssertionError(f"relationship evidence record not found: {relationship}; records={records!r}")


async def test_architectural_relationship_geometry_evidence_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_geometry_evidence import query_relationship_evidence_for_tool
    from rook.scene.scene_graph import get_scene_graph

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
    assert projection["counts"]["projectedEdgeCount"] == 5

    evidence = await query_relationship_evidence_for_tool(
        analytics=sg,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )
    if evidence.get("success") is not True:
        pytest.fail(json.dumps({"fixtureSummary": fixture_summary, "evidence": evidence}, indent=2, sort_keys=True))

    assert evidence["counts"] == {
        "matchingRelationshipFactCount": 5,
        "evidenceRecordCount": 5,
        "measuredEvidenceCount": 5,
        "missingEvidenceCount": 0,
        "withinToleranceCount": 3,
        "outsideToleranceCount": 2,
        "hydratedFeatureObjectCount": 10,
    }
    assert evidence["diagnostics"]["outsideTolerance"] == 2

    supports = _record_by_relationship(evidence["records"], "supports")
    assert supports["contactKind"] == "point_to_region"
    assert supports["evidence"]["status"] == "measured"
    assert supports["evidence"]["distanceM"] == pytest.approx(0.0)
    assert supports["evidence"]["withinTolerance"] is True

    hosted_by = _record_by_relationship(evidence["records"], "hosted_by")
    assert hosted_by["contactKind"] == "body_to_region"
    assert hosted_by["evidence"]["distanceM"] == pytest.approx(0.1)
    assert hosted_by["evidence"]["withinTolerance"] is False

    voids = _record_by_relationship(evidence["records"], "voids")
    assert voids["contactKind"] == "profile_to_region"
    assert voids["evidence"]["distanceM"] == pytest.approx(0.02)
    assert voids["evidence"]["withinTolerance"] is False

    penetrates = _record_by_relationship(evidence["records"], "penetrates")
    assert penetrates["contactKind"] == "line_to_region"
    assert penetrates["evidence"]["distanceM"] == pytest.approx(0.0)
    assert penetrates["evidence"]["withinTolerance"] is True

    bounded_by = _record_by_relationship(evidence["records"], "bounded_by")
    assert bounded_by["contactKind"] == "boundary_to_face"
    assert bounded_by["evidence"]["distanceM"] == pytest.approx(0.0)
    assert bounded_by["evidence"]["withinTolerance"] is True
