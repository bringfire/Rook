import ast
from pathlib import Path

from rook.scene import relationship_fact_projection as rel


def _owner_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "spine_base_to_spine_top",
            "rook.graph.feature_ids": "spine_base_to_spine_top.start,spine_base_to_spine_top.end",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _joint_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "spine_base",
            "rook.graph.feature_ids": "spine_base.point",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _feature_record(
    object_id: str,
    feature_id: str,
    owner: str,
    owner_kind: str,
    *,
    pose: str = "reclined_robot",
) -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": feature_id,
            "rook.graph.owner": owner,
            "rook.graph.owner_kind": owner_kind,
            "rook.graph.feature_kind": "endpoint",
            "rook.graph.role": "start",
            "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
            "rook.graph.visual_lift_m": "0.08",
        },
    )


def _relationship_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "spine_base_to_spine_top.start_connects_spine_base",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "spine_base_to_spine_top.start",
            "rook.graph.to_feature": "spine_base.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
    )


def _valid_records() -> list[rel.RuntimeObjectRecord]:
    return [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "node"),
        _relationship_record("relationship-marker-id"),
    ]


def test_module_constants():
    assert rel.PROJECTION_KIND == "relationship_fact_v1"
    assert rel.DEFAULT_SOURCE_MODE == "authored_graph_user_strings"
    assert rel.DEFAULT_CONFIDENCE == 1.0
    assert rel.DEFAULT_STATUS == "accepted"
    assert rel.ENGINE_VERSION == 1


def test_projector_source_is_read_only_and_uses_object_get():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "rook"
        / "scene"
        / "relationship_fact_projection.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = [
        "/usertext/object-set",
        "/usertext/object-delete",
        "/usertext/document-set",
        "/usertext/document-delete",
        "/document/save",
        "scene_exact_neighbors",
        "scene_refine_containment",
    ]

    executable_tokens: set[str] = set()
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstring_nodes.add(value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstring_nodes:
                executable_tokens.add(node.value)
        elif isinstance(node, ast.Name):
            executable_tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            executable_tokens.add(node.attr)

    assert "/usertext/object-get" in executable_tokens
    for token in forbidden:
        assert not any(token in executable_token for executable_token in executable_tokens)


def test_parse_runtime_records_defaults_missing_fact_fields():
    parsed = rel.parse_runtime_records(_valid_records())

    assert parsed.diagnostics == {}
    assert set(parsed.owners_by_key) == {
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "member", "spine_base_to_spine_top"),
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "node", "spine_base"),
    }
    assert set(parsed.features_by_key) == {
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top.start"),
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base.point"),
    }
    assert len(parsed.relationship_records) == 1
    relationship = parsed.relationship_records[0]
    assert relationship.relationship_id == "spine_base_to_spine_top.start_connects_spine_base"
    assert relationship.relationship_type == "connects"
    assert relationship.confidence == 1.0
    assert relationship.status == "accepted"
    assert relationship.source_mode == "authored_graph_user_strings"


def test_parse_runtime_records_requires_pose_for_graph_records():
    bad_relationship = _relationship_record("relationship-marker-id")
    bad_relationship.user_strings.pop("rook.graph.pose")

    parsed = rel.parse_runtime_records([bad_relationship])

    assert parsed.relationship_records == []
    assert parsed.diagnostics["recordsMissingPose"] == 1
