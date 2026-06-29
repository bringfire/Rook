from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = (
    REPO_ROOT
    / "experiments"
    / "relationship_fact_projection_smoke"
    / "scripts"
    / "create_smoke_fixture_rhino.py"
)

SOURCE = "relationship_fact_smoke"

EXPECTED_FACT = {
    "relationship": "connects",
    "fromFeature": "smoke_member.start",
    "toFeature": "smoke_joint.point",
    "contactKind": "point_to_point",
    "provenance": "authored_assembly_graph",
    "status": "accepted",
    "graphSource": SOURCE,
    "graphRevision": "smoke001",
    "pose": "smoke_pose",
}

REQUIRED_CONTEXT_SUBSTRINGS = [
    "connects",
    "connected by",
    "smoke_member.start -> smoke_joint.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


def _json_from_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start, f"rhino_execute output contained no JSON object: {output!r}"
    return json.loads(output[start : end + 1])


def _script_output_from_execute_result(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        output = result.get("data", "")
    if isinstance(output, (dict, list)):
        output = json.dumps(output)
    assert isinstance(output, str), f"rhino_execute output/data was not text-like: {result!r}"
    assert output, f"rhino_execute returned no script output: {result!r}"
    return output


async def _create_smoke_fixture() -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    script = SMOKE_SCRIPT.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute smoke fixture failed: {result!r}"
    fixture = _json_from_output(_script_output_from_execute_result(result))
    assert fixture["source"] == SOURCE
    assert fixture["revision"] == "smoke001"
    assert fixture["pose"] == "smoke_pose"
    assert fixture["memberObjectId"]
    assert fixture["jointObjectId"]
    return fixture


def _extract_projected_facts(analytics, *, graph_source: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != graph_source:
            continue
        facts.append(
            {
                "relationship": attrs.get("semanticRelationshipType") or attrs.get("relationship"),
                "fromFeature": attrs.get("fromFeature"),
                "toFeature": attrs.get("toFeature"),
                "contactKind": attrs.get("contactKind"),
                "provenance": attrs.get("provenance"),
                "status": attrs.get("status"),
                "graphSource": attrs.get("graphSource"),
                "graphRevision": attrs.get("graphRevision"),
                "pose": attrs.get("pose"),
                "fromObjectId": str(source_id),
                "toObjectId": str(target_id),
            }
        )
    return sorted(
        facts,
        key=lambda fact: (
            fact["relationship"],
            fact["fromFeature"],
            fact["toFeature"],
            fact["graphSource"],
            fact["graphRevision"],
            fact["pose"],
        ),
    )


async def test_relationship_fact_smoke_roundtrip_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph
    from rook.server import _call_tool_dispatch

    fixture = await _create_smoke_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=SOURCE,
        strict=True,
        analytics=sg,
    )

    assert projection["success"] is True, f"projection failed: {projection!r}"
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 1
    assert counts["projectedEdgeCount"] == 1
    assert counts["skippedFactCount"] == 0

    actual_facts = _extract_projected_facts(sg, graph_source=SOURCE)
    context_result = await _call_tool_dispatch(
        "scene_context",
        {
            "object_ids": [fixture["memberObjectId"], fixture["jointObjectId"]],
            "sync": False,
        },
    )
    assert context_result["success"] is True, f"scene_context failed: {context_result!r}"

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=actual_facts,
        context_text=context_result["data"],
        required_substrings=REQUIRED_CONTEXT_SUBSTRINGS,
    )
    if not report["success"]:
        report["fixture"] = {
            "memberObjectId": fixture["memberObjectId"],
            "jointObjectId": fixture["jointObjectId"],
            "clearedObjectCount": fixture.get("clearedObjectCount"),
        }
        report["actualFacts"] = actual_facts
        pytest.fail(json.dumps(report, indent=2, sort_keys=True))
