from __future__ import annotations

from rook.scene.relationship_fact_roundtrip import compare_roundtrip

from .architectural_fixture_helpers import (
    EXPECTED_FEATURE_IDS,
    EXPECTED_OWNER_IDS,
    EXPECTED_RELATIONSHIP_TYPES,
    GENERATED_SCRIPT_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_architectural_card_expectations,
    build_expected_facts,
    build_synthetic_projected_graph,
    extract_projected_facts,
    load_architectural_graph,
    query_fixture_cards,
    query_fixture_semantic_relationships,
    semantic_facts,
)


def test_architectural_graph_shape_is_stable():
    graph = load_architectural_graph()

    assert graph["schema"] == "rook.architectural_relationship_fixture.v1"
    assert graph["source"] == GRAPH_SOURCE
    assert graph["revision"] == GRAPH_REVISION
    assert graph["unit"] == "meters"
    assert sorted(graph["poses"]) == [POSE]
    assert {obj["object_id"] for obj in graph["objects"]} == EXPECTED_OWNER_IDS
    assert {feature["feature_id"] for feature in graph["features"]} == EXPECTED_FEATURE_IDS
    assert {rel["relationship_type"] for rel in graph["relationships"]} == EXPECTED_RELATIONSHIP_TYPES
    assert len(graph["objects"]) == 7
    assert len(graph["features"]) == 10
    assert len(graph["relationships"]) == 5


def test_architectural_relationships_reference_existing_features():
    graph = load_architectural_graph()
    feature_ids = {feature["feature_id"] for feature in graph["features"]}

    for relationship in graph["relationships"]:
        assert relationship["from_feature"] in feature_ids
        assert relationship["to_feature"] in feature_ids
        assert relationship["provenance"] == "authored_architectural_fixture"
        assert relationship["status"] == "accepted"


def test_expected_facts_are_built_from_graph():
    graph = load_architectural_graph()

    assert build_expected_facts(graph) == [
        {
            "relationship": "bounded_by",
            "fromFeature": "space_01.boundary",
            "toFeature": "wall_01.inner_face",
            "contactKind": "boundary_to_face",
            "provenance": "authored_architectural_fixture",
            "status": "accepted",
            "graphSource": GRAPH_SOURCE,
            "graphRevision": GRAPH_REVISION,
            "pose": POSE,
        },
        {
            "relationship": "hosted_by",
            "fromFeature": "door_01.body",
            "toFeature": "wall_01.host_region",
            "contactKind": "body_to_region",
            "provenance": "authored_architectural_fixture",
            "status": "accepted",
            "graphSource": GRAPH_SOURCE,
            "graphRevision": GRAPH_REVISION,
            "pose": POSE,
        },
        {
            "relationship": "penetrates",
            "fromFeature": "duct_01.centerline",
            "toFeature": "wall_01.penetration_region",
            "contactKind": "line_to_region",
            "provenance": "authored_architectural_fixture",
            "status": "accepted",
            "graphSource": GRAPH_SOURCE,
            "graphRevision": GRAPH_REVISION,
            "pose": POSE,
        },
        {
            "relationship": "supports",
            "fromFeature": "column_01.top_point",
            "toFeature": "slab_01.underside_region",
            "contactKind": "point_to_region",
            "provenance": "authored_architectural_fixture",
            "status": "accepted",
            "graphSource": GRAPH_SOURCE,
            "graphRevision": GRAPH_REVISION,
            "pose": POSE,
        },
        {
            "relationship": "voids",
            "fromFeature": "opening_01.profile",
            "toFeature": "wall_01.opening_region",
            "contactKind": "profile_to_region",
            "provenance": "authored_architectural_fixture",
            "status": "accepted",
            "graphSource": GRAPH_SOURCE,
            "graphRevision": GRAPH_REVISION,
            "pose": POSE,
        },
    ]


def test_synthetic_projected_graph_matches_expected_facts():
    graph = load_architectural_graph()
    sg = build_synthetic_projected_graph(graph)
    expected_facts = build_expected_facts(graph)
    actual_facts = extract_projected_facts(sg)

    report = compare_roundtrip(
        expected_facts=expected_facts,
        actual_facts=semantic_facts(actual_facts),
        context_text="",
        required_substrings=[],
    )

    assert report["success"] is True, report


def test_semantic_relationship_inspector_reports_selected_architectural_facts():
    graph = load_architectural_graph()
    sg = build_synthetic_projected_graph(graph)

    result = query_fixture_semantic_relationships(sg, ["column_01", "slab_01", "wall_01"])

    assert result["success"] is True, result
    assert result["counts"]["relationshipFactCount"] == 5
    assert result["counts"]["relationshipViewCount"] == 6
    assert result["objects"][0]["facts"][0]["relationship"] == "supports"
    assert result["objects"][0]["facts"][0]["direction"] == "outgoing"
    assert result["objects"][1]["facts"][0]["relationship"] == "supports"
    assert result["objects"][1]["facts"][0]["direction"] == "incoming"
    wall_facts = result["objects"][2]["facts"]
    assert {fact["relationship"] for fact in wall_facts} == {
        "bounded_by",
        "hosted_by",
        "penetrates",
        "voids",
    }
    assert {fact["direction"] for fact in wall_facts} == {"incoming"}


def test_object_semantic_context_cards_summarize_architectural_relationships():
    graph = load_architectural_graph()
    sg = build_synthetic_projected_graph(graph)

    cards = query_fixture_cards(
        sg,
        ["column_01", "slab_01", "wall_01", "door_01", "opening_01", "duct_01", "space_01"],
    )

    assert cards["counts"] == {
        "requestedObjectCount": 7,
        "existingSelectedObjectCount": 7,
        "missingSelectedObjectCount": 0,
        "relationshipFactCount": 5,
        "relationshipViewCount": 10,
        "cardCount": 7,
    }
    assert_architectural_card_expectations(cards)


def test_generated_script_embeds_expected_fixture_constants():
    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'SOURCE = "architectural_relationship_fixture"' in script
    assert 'REVISION = "a001"' in script
    assert 'POSE = "architectural_reference"' in script
    assert 'LAYER_NAME = "Rook_ArchitecturalRelationshipFixture"' in script
    assert '"rook.graph.visual_type": visual_type' in script
    assert '"rook.graph.object_id": obj["object_id"]' in script
    assert '"rook.graph.object_kind": obj["object_kind"]' in script
    assert '"rook.graph.owner_id": feature["owner_id"]' in script
    assert ('"rook.graph.' + 'member_id"') not in script
    assert ('"rook.graph.' + 'owner":') not in script
