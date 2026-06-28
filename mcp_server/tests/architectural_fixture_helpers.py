from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rook.scene.object_semantic_context import query_object_semantic_context
from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.semantic_relationship_inspector import query_semantic_relationships


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "experiments" / "architectural_relationship_fixture"
GRAPH_PATH = FIXTURE_DIR / "assembly_graph.json"
GENERATED_SCRIPT_PATH = FIXTURE_DIR / "generated" / "create_architectural_fixture_rhino.py"

GRAPH_SOURCE = "architectural_relationship_fixture"
GRAPH_REVISION = "a001"
POSE = "architectural_reference"
PROVENANCE = "authored_architectural_fixture"
STATUS = "accepted"

EXPECTED_OWNER_IDS = {
    "column_01",
    "slab_01",
    "wall_01",
    "door_01",
    "opening_01",
    "duct_01",
    "space_01",
}

EXPECTED_FEATURE_IDS = {
    "column_01.top_point",
    "slab_01.underside_region",
    "door_01.body",
    "wall_01.host_region",
    "opening_01.profile",
    "wall_01.opening_region",
    "duct_01.centerline",
    "wall_01.penetration_region",
    "space_01.boundary",
    "wall_01.inner_face",
}

EXPECTED_RELATIONSHIP_TYPES = {
    "bounded_by",
    "hosted_by",
    "penetrates",
    "supports",
    "voids",
}

WALL_EXPECTED_GROUP_KEYS = {
    "hosted_by:incoming:accepted:authored_architectural_fixture",
    "voids:incoming:accepted:authored_architectural_fixture",
    "penetrates:incoming:accepted:authored_architectural_fixture",
    "bounded_by:incoming:accepted:authored_architectural_fixture",
}

FACT_SORT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
    "pose",
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


def load_architectural_graph(path: Path = GRAPH_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sorted_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(facts, key=lambda fact: tuple(fact.get(field) for field in FACT_SORT_FIELDS))


def build_expected_facts(graph: dict[str, Any]) -> list[dict[str, Any]]:
    revision = graph["revision"]
    pose_ids = sorted(graph["poses"])
    expected: list[dict[str, Any]] = []
    for pose in pose_ids:
        for relationship in graph["relationships"]:
            expected.append(
                {
                    "relationship": relationship["relationship_type"],
                    "fromFeature": relationship["from_feature"],
                    "toFeature": relationship["to_feature"],
                    "contactKind": relationship["contact_kind"],
                    "provenance": relationship.get("provenance", PROVENANCE),
                    "status": relationship.get("status", STATUS),
                    "graphSource": graph["source"],
                    "graphRevision": revision,
                    "pose": pose,
                }
            )
    return sorted_facts(expected)


def semantic_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in STRUCTURED_FACT_FIELDS}


def semantic_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted_facts([semantic_fact(fact) for fact in facts])


def owner_for_feature(graph: dict[str, Any], feature_id: str) -> str:
    features = {feature["feature_id"]: feature for feature in graph["features"]}
    return str(features[feature_id]["owner_id"])


def object_name(graph: dict[str, Any], object_id: str) -> str:
    objects = {obj["object_id"]: obj for obj in graph["objects"]}
    return str(objects[object_id]["name"])


def build_synthetic_projected_graph(graph: dict[str, Any]) -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    for obj in graph["objects"]:
        sg.graph.add_node(obj["object_id"], name=obj["name"], objectKind=obj["object_kind"])

    for relationship in graph["relationships"]:
        source_id = owner_for_feature(graph, relationship["from_feature"])
        target_id = owner_for_feature(graph, relationship["to_feature"])
        sg.graph.add_edge(
            source_id,
            target_id,
            key=(
                "relationship_fact:authored_graph_user_strings:"
                f"{GRAPH_SOURCE}:{GRAPH_REVISION}:{POSE}:{relationship['relationship_id']}"
            ),
            relationship=relationship["relationship_type"],
            projectionKind="relationship_fact_v1",
            semanticRelationshipType=relationship["relationship_type"],
            relationshipFactId=relationship["relationship_id"],
            provenance=relationship.get("provenance", PROVENANCE),
            confidence=1.0,
            status=relationship.get("status", STATUS),
            sourceMode="authored_graph_user_strings",
            contactKind=relationship["contact_kind"],
            graphSource=graph["source"],
            graphRevision=graph["revision"],
            pose=POSE,
            fromFeature=relationship["from_feature"],
            toFeature=relationship["to_feature"],
        )
    return sg


def extract_projected_facts(analytics: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != GRAPH_SOURCE:
            continue
        if attrs.get("graphRevision") != GRAPH_REVISION:
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
    return sorted_facts(facts)


def object_ids_for_features(facts: list[dict[str, Any]], feature_pairs: list[tuple[str, str]]) -> list[str]:
    wanted = set(feature_pairs)
    ids: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        pair = (str(fact.get("fromFeature")), str(fact.get("toFeature")))
        if pair not in wanted:
            continue
        for key in ("fromObjectId", "toObjectId"):
            object_id = fact.get(key)
            if object_id and object_id not in seen:
                seen.add(str(object_id))
                ids.append(str(object_id))
    return ids


def query_fixture_semantic_relationships(analytics: Any, object_ids: list[str]) -> dict[str, Any]:
    return query_semantic_relationships(
        analytics,
        object_ids=object_ids,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )


def query_fixture_cards(analytics: Any, object_ids: list[str]) -> dict[str, Any]:
    return query_object_semantic_context(
        analytics,
        object_ids=object_ids,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )


def card_by_id(cards_result: dict[str, Any], object_id: str) -> dict[str, Any]:
    for card in cards_result["cards"]:
        if card["objectId"] == object_id:
            return card
    raise AssertionError(f"card not found for {object_id!r}: {cards_result!r}")


def group_keys(card: dict[str, Any]) -> set[str]:
    return {group["groupKey"] for group in card["groups"]}


def assert_architectural_card_expectations(
    cards_result: dict[str, Any],
    owner_object_ids: dict[str, str] | None = None,
) -> None:
    if owner_object_ids is None:
        owner_object_ids = {owner_id: owner_id for owner_id in EXPECTED_OWNER_IDS}

    assert cards_result["success"] is True, cards_result
    assert cards_result["counts"]["relationshipFactCount"] == 5
    assert cards_result["counts"]["relationshipViewCount"] == 10

    column = card_by_id(cards_result, owner_object_ids["column_01"])
    assert group_keys(column) == {"supports:outgoing:accepted:authored_architectural_fixture"}
    assert column["summary"]["byRelationship"] == {"supports": 1}
    assert column["summary"]["byDirection"] == {"outgoing": 1}
    assert column["groups"][0]["relationshipCategory"] == "support"

    slab = card_by_id(cards_result, owner_object_ids["slab_01"])
    assert group_keys(slab) == {"supports:incoming:accepted:authored_architectural_fixture"}
    assert slab["summary"]["byRelationship"] == {"supports": 1}
    assert slab["summary"]["byDirection"] == {"incoming": 1}
    assert slab["groups"][0]["inverseRelationship"] == "supported by"

    door = card_by_id(cards_result, owner_object_ids["door_01"])
    assert group_keys(door) == {"hosted_by:outgoing:accepted:authored_architectural_fixture"}
    assert door["summary"]["byRelationship"] == {"hosted_by": 1}
    assert door["groups"][0]["relationshipCategory"] == "hosting"

    duct = card_by_id(cards_result, owner_object_ids["duct_01"])
    assert group_keys(duct) == {"penetrates:outgoing:accepted:authored_architectural_fixture"}
    assert duct["summary"]["byRelationship"] == {"penetrates": 1}
    assert duct["groups"][0]["relationshipCategory"] == "penetration"

    space = card_by_id(cards_result, owner_object_ids["space_01"])
    assert group_keys(space) == {"bounded_by:outgoing:accepted:authored_architectural_fixture"}
    assert space["summary"]["byRelationship"] == {"bounded_by": 1}
    assert space["groups"][0]["relationshipCategory"] == "boundary"

    wall = card_by_id(cards_result, owner_object_ids["wall_01"])
    assert group_keys(wall) == WALL_EXPECTED_GROUP_KEYS
    assert wall["summary"]["relationshipFactCount"] == 4
    assert wall["summary"]["relationshipViewCount"] == 4
    assert wall["summary"]["byRelationship"] == {
        "bounded_by": 1,
        "hosted_by": 1,
        "penetrates": 1,
        "voids": 1,
    }
    assert wall["summary"]["byRelationshipCategory"] == {
        "boundary": 1,
        "hosting": 1,
        "penetration": 1,
        "voiding": 1,
    }
    assert wall["summary"]["byDirection"] == {"incoming": 4}
    assert wall["summary"]["byStatus"] == {STATUS: 4}
    assert wall["summary"]["byProvenance"] == {PROVENANCE: 4}


def assert_fixture_summary(summary: dict[str, Any]) -> None:
    expected = {
        "success": True,
        "source": GRAPH_SOURCE,
        "revision": GRAPH_REVISION,
        "pose": POSE,
        "ownerObjectCount": 7,
        "featureObjectCount": 10,
        "relationshipObjectCount": 5,
        "createdObjectCount": 22,
    }
    for key, value in expected.items():
        assert summary.get(key) == value, (
            f"fixture summary {key}={summary.get(key)!r}, expected {value!r}; "
            f"summary={summary!r}"
        )
    assert "clearedObjectCount" in summary, f"fixture summary missing clearedObjectCount: {summary!r}"
    assert set(summary.get("ownerObjectIds", {})) == EXPECTED_OWNER_IDS
    assert set(summary.get("featureObjectIds", {})) == EXPECTED_FEATURE_IDS
    assert len(summary.get("relationshipObjectIds", {})) == 5


def json_from_execute_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start, f"rhino_execute output contained no JSON object: {output!r}"
    return json.loads(output[start : end + 1])


def script_output_from_execute_result(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        output = result.get("data", "")
    if isinstance(output, (dict, list)):
        return json.dumps(output)
    assert isinstance(output, str), f"rhino_execute output/data was not text-like: {result!r}"
    assert output, f"rhino_execute returned no script output: {result!r}"
    return output
