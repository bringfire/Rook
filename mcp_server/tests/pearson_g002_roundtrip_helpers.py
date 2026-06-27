from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_SOURCE = "pearson_robot_skeleton_graph"
GRAPH_PATH = REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "assembly_graph.json"
GENERATED_SCRIPT_PATH = (
    REPO_ROOT
    / "experiments"
    / "pearson_robot_skeleton_graph"
    / "generated"
    / "skeleton_graph_rhino.py"
)

STRUCTURED_FACT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "contactKind",
    "provenance",
    "status",
    "graphSource",
    "graphRevision",
    "pose",
)

FACT_SORT_FIELDS = (
    "pose",
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
)


def load_assembly_graph(path: Path = GRAPH_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def embedded_graph_from_generated_script(path: Path = GENERATED_SCRIPT_PATH) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "GRAPH" for target in node.targets):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "loads"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "json"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
        ):
            return json.loads(value.args[0].value)
    raise AssertionError(f"Could not find GRAPH = json.loads(...) in {path}")


def build_expected_facts(graph: dict[str, Any]) -> list[dict[str, Any]]:
    revision = graph["revision"]
    pose_ids = sorted(graph["poses"])
    expected: list[dict[str, Any]] = []
    for pose in pose_ids:
        for relationship in graph["relationships"]:
            expected.append(
                {
                    "relationship": relationship["type"],
                    "fromFeature": relationship["from"],
                    "toFeature": relationship["to"],
                    "contactKind": relationship["contact_kind"],
                    "provenance": relationship["provenance"],
                    "status": relationship.get("status", "accepted"),
                    "graphSource": GRAPH_SOURCE,
                    "graphRevision": revision,
                    "pose": pose,
                }
            )
    return sorted_facts(expected)


def sorted_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        facts,
        key=lambda fact: tuple(fact.get(field) for field in FACT_SORT_FIELDS),
    )


def pearson_fact_counts_by_pose(facts: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(fact.get("pose")) for fact in facts).items()))


def extract_projected_facts(analytics: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != GRAPH_SOURCE:
            continue
        if attrs.get("graphRevision") != "g002":
            continue
        fact = {
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
        facts.append(fact)
    return sorted_facts(facts)


def semantic_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in STRUCTURED_FACT_FIELDS}


def semantic_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted_facts([semantic_fact(fact) for fact in facts])


def object_ids_for_feature_pairs(
    facts: list[dict[str, Any]],
    selected_pairs: list[tuple[str, str]],
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    wanted = set(selected_pairs)
    for fact in facts:
        pair = (str(fact.get("fromFeature")), str(fact.get("toFeature")))
        if pair not in wanted:
            continue
        for key in ("fromObjectId", "toObjectId"):
            object_id = fact.get(key)
            if object_id and object_id not in seen:
                seen.add(object_id)
                ids.append(str(object_id))
    return ids


def pearson_mismatch_report(
    *,
    roundtrip_report: dict[str, Any],
    actual_facts: list[dict[str, Any]],
    expected_facts: list[dict[str, Any]],
    fixture_summary: dict[str, Any],
) -> dict[str, Any]:
    report = dict(roundtrip_report)
    report["expectedByPose"] = pearson_fact_counts_by_pose(expected_facts)
    report["actualByPose"] = pearson_fact_counts_by_pose(actual_facts)
    report["fixtureSummary"] = fixture_summary
    return report
