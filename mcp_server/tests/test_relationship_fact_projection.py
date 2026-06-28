import ast
from pathlib import Path

import pytest

from rook.scene import relationship_fact_projection as rel
from rook.scene.scene_graph import SceneGraphAnalytics


def _owner_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "object",
            "rook.graph.object_id": "spine_base_to_spine_top",
            "rook.graph.object_kind": "member",
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
            "rook.graph.visual_type": "object",
            "rook.graph.object_id": "spine_base",
            "rook.graph.object_kind": "joint",
            "rook.graph.feature_ids": "spine_base.point",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _feature_record(
    object_id: str,
    feature_id: str,
    owner_id: str,
    owner_kind: str | None = None,
    *,
    pose: str = "reclined_robot",
) -> rel.RuntimeObjectRecord:
    record = rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": feature_id,
            "rook.graph.owner_id": owner_id,
            "rook.graph.feature_kind": "endpoint",
            "rook.graph.role": "start",
            "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
            "rook.graph.visual_lift_m": "0.08",
        },
    )
    if owner_kind is not None:
        record.user_strings["rook.graph.owner_kind"] = owner_kind
    return record


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
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint"),
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
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top"),
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base"),
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


def test_parse_runtime_records_requires_object_id_for_object_records():
    bad_owner = _owner_record("member-rhino-id")
    bad_owner.user_strings.pop("rook.graph.object_id")

    parsed = rel.parse_runtime_records([bad_owner])

    assert parsed.owners_by_key == {}
    assert parsed.diagnostics["ownerObjectsMissingOwnerId"] == 1


def test_parse_runtime_records_requires_object_kind_for_object_records():
    bad_owner = _owner_record("member-rhino-id")
    bad_owner.user_strings.pop("rook.graph.object_kind")

    parsed = rel.parse_runtime_records([bad_owner])

    assert parsed.owners_by_key == {}
    assert parsed.diagnostics["ownerObjectsMissingOwnerKind"] == 1


def test_parse_runtime_records_requires_pose_for_graph_records():
    bad_relationship = _relationship_record("relationship-marker-id")
    bad_relationship.user_strings.pop("rook.graph.pose")

    parsed = rel.parse_runtime_records([bad_relationship])

    assert parsed.relationship_records == []
    assert parsed.diagnostics["recordsMissingPose"] == 1


def test_parse_runtime_records_ignores_plain_non_graph_objects_in_strict_flow():
    records = [
        rel.RuntimeObjectRecord(
            "plain-rhino-id",
            {
                "material": "steel",
                "notes": "ordinary Rhino object with user text",
            },
        ),
        *_valid_records(),
    ]

    parsed = rel.parse_runtime_records(records, graph_source="pearson_robot_skeleton_graph")
    fact_set = rel.build_relationship_fact_set(parsed, strict=True)

    assert fact_set.success is True
    assert len(fact_set.facts) == 1
    assert "recordsMissingGraphSource" not in parsed.diagnostics
    assert parsed.diagnostics["ignoredNonGraphObjects"] == 1


def _analytics_for_relationship_projection() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-rhino-id", name="Spine member", domain_label="member", shape_class="curve")
    sg.graph.add_node("joint-rhino-id", name="Spine base", domain_label="joint", shape_class="point")
    sg.graph.add_node("unrelated-rhino-id", name="Unrelated", domain_label="marker", shape_class="point")
    sg._sequence = 42
    return sg


def test_resolve_relationship_facts_projects_owner_to_owner():
    parsed = rel.parse_runtime_records(_valid_records())
    facts = rel.resolve_relationship_facts(parsed)

    assert len(facts) == 1
    fact = facts[0]
    assert fact.from_owner == "spine_base_to_spine_top"
    assert fact.from_owner_kind == "member"
    assert fact.from_owner_object_id == "member-rhino-id"
    assert fact.from_feature == "spine_base_to_spine_top.start"
    assert fact.from_feature_object_id == "feature-member-start-id"
    assert fact.to_owner == "spine_base"
    assert fact.to_owner_kind == "joint"
    assert fact.to_owner_object_id == "joint-rhino-id"
    assert fact.to_feature == "spine_base.point"
    assert fact.to_feature_object_id == "feature-joint-point-id"


def test_project_relationship_facts_adds_connects_edge_with_metadata():
    sg = _analytics_for_relationship_projection()
    parsed = rel.parse_runtime_records(_valid_records())
    facts = rel.resolve_relationship_facts(parsed)

    result = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert result["success"] is True
    assert result["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    edge_data = list(sg.graph["member-rhino-id"]["joint-rhino-id"].values())[0]
    assert edge_data["relationship"] == "connects"
    assert edge_data["projectionKind"] == rel.PROJECTION_KIND
    assert edge_data["semanticRelationshipType"] == "connects"
    assert edge_data["provenance"] == "authored_assembly_graph"
    assert edge_data["confidence"] == 1.0
    assert edge_data["status"] == "accepted"
    assert edge_data["sourceMode"] == "authored_graph_user_strings"
    assert edge_data["contactKind"] == "point_to_point"
    assert edge_data["fromFeature"] == "spine_base_to_spine_top.start"
    assert edge_data["toFeature"] == "spine_base.point"
    assert edge_data["fromFeatureObjectId"] == "feature-member-start-id"
    assert edge_data["toFeatureObjectId"] == "feature-joint-point-id"
    assert edge_data["relationshipObjectId"] == "relationship-marker-id"
    assert edge_data["engineVersion"] == 1


def test_projection_is_idempotent_for_same_fact_key():
    sg = _analytics_for_relationship_projection()
    facts = rel.resolve_relationship_facts(rel.parse_runtime_records(_valid_records()))

    first = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())
    second = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert first["counts"]["projectedEdgeCount"] == 1
    assert second["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.number_of_edges("member-rhino-id", "joint-rhino-id") == 1


def test_pose_separation_creates_distinct_edge_keys():
    sg = _analytics_for_relationship_projection()
    records = [
        *_valid_records(),
        _owner_record("member-rhino-id", pose="rest_t_pose"),
        _joint_record("joint-rhino-id", pose="rest_t_pose"),
        _feature_record(
            "feature-member-start-id-rest",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
            pose="rest_t_pose",
        ),
        _feature_record("feature-joint-point-id-rest", "spine_base.point", "spine_base", "joint", pose="rest_t_pose"),
        _relationship_record("relationship-marker-id-rest", pose="rest_t_pose"),
    ]
    facts = rel.resolve_relationship_facts(rel.parse_runtime_records(records))

    result = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert result["counts"]["projectedEdgeCount"] == 2
    assert sg.graph.number_of_edges("member-rhino-id", "joint-rhino-id") == 2
    poses = {data["pose"] for data in sg.graph["member-rhino-id"]["joint-rhino-id"].values()}
    assert poses == {"reclined_robot", "rest_t_pose"}


def test_prune_relationship_fact_projection_preserves_other_projection_kinds():
    sg = _analytics_for_relationship_projection()
    sg.graph.add_edge(
        "member-rhino-id",
        "joint-rhino-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g001:reclined_robot:old",
        relationship="connects",
        projectionKind=rel.PROJECTION_KIND,
        sourceMode=rel.DEFAULT_SOURCE_MODE,
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g001",
        pose="reclined_robot",
        engineVersion=rel.ENGINE_VERSION,
    )
    sg.graph.add_edge(
        "member-rhino-id",
        "unrelated-rhino-id",
        key="bim-edge",
        relationship="revit_hosted_by",
        projectionKind="bim_relationship_v1",
    )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g001",
            poses=["reclined_robot"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert sg.graph.has_edge("member-rhino-id", "unrelated-rhino-id", "bim-edge")


def test_scoped_prune_preserves_out_of_scope_pose():
    sg = _analytics_for_relationship_projection()
    for pose in ("reclined_robot", "rest_t_pose"):
        sg.graph.add_edge(
            "member-rhino-id",
            "joint-rhino-id",
            key=f"relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:{pose}:old",
            relationship="connects",
            projectionKind=rel.PROJECTION_KIND,
            sourceMode=rel.DEFAULT_SOURCE_MODE,
            graphSource="pearson_robot_skeleton_graph",
            graphRevision="g002",
            pose=pose,
            engineVersion=rel.ENGINE_VERSION,
        )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g002",
            poses=["reclined_robot"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not any(data["pose"] == "reclined_robot" for _, _, data in sg.graph.edges(data=True))
    assert any(data["pose"] == "rest_t_pose" for _, _, data in sg.graph.edges(data=True))


def test_scoped_prune_preserves_edges_outside_primary_object_scope():
    sg = _analytics_for_relationship_projection()
    sg.graph.add_node("other-member-id", name="Other member")
    sg.graph.add_node("other-joint-id", name="Other joint")
    for source_id, target_id in (("member-rhino-id", "joint-rhino-id"), ("other-member-id", "other-joint-id")):
        sg.graph.add_edge(
            source_id,
            target_id,
            key=f"relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:{source_id}",
            relationship="connects",
            projectionKind=rel.PROJECTION_KIND,
            sourceMode=rel.DEFAULT_SOURCE_MODE,
            graphSource="pearson_robot_skeleton_graph",
            graphRevision="g002",
            pose="reclined_robot",
            engineVersion=rel.ENGINE_VERSION,
        )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g002",
            poses=["reclined_robot"],
            primary_object_ids=["member-rhino-id"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert sg.graph.has_edge("other-member-id", "other-joint-id")


def test_lenient_missing_feature_endpoint_reports_diagnostic_without_crashing():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["relationshipFactsMissingFeatureEndpoint"] == 1


def test_strict_missing_feature_endpoint_fails():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _relationship_record("relationship-marker-id"),
    ]

    with pytest.raises(rel.RelationshipFactProjectionError) as exc:
        rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=True)

    assert "relationshipFactsMissingFeatureEndpoint" in str(exc.value)


def test_strict_mode_ignores_informational_filter_diagnostics():
    records = [
        *_valid_records(),
        _owner_record("member-rhino-id-rest", pose="rest_t_pose"),
        _joint_record("joint-rhino-id-rest", pose="rest_t_pose"),
    ]
    parsed = rel.parse_runtime_records(records, poses=["reclined_robot"])

    result = rel.build_relationship_fact_set(parsed, strict=True)

    assert result.success is True
    assert len(result.facts) == 1
    assert parsed.diagnostics["filteredByPose"] == 2


def test_missing_owner_object_reports_diagnostic():
    records = [
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["relationshipFactsMissingOwnerObject"] == 1


def test_feature_owner_kind_is_optional_and_resolves_by_owner_id():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            owner_kind=None,
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", owner_kind=None),
        _relationship_record("relationship-marker-id"),
    ]

    fact_set = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=True)

    assert fact_set.success is True
    assert len(fact_set.facts) == 1
    fact = fact_set.facts[0]
    assert fact.from_owner_kind == "member"
    assert fact.to_owner_kind == "joint"


def test_feature_owner_kind_mismatch_reports_diagnostic():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "joint",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["featureObjectsOwnerKindMismatch"] == 1


def test_duplicate_object_id_with_conflicting_kind_reports_diagnostic():
    duplicate = _owner_record("member-rhino-id-duplicate")
    duplicate.user_strings["rook.graph.object_kind"] = "joint"
    parsed = rel.parse_runtime_records([_owner_record("member-rhino-id"), duplicate])

    assert len(parsed.owners_by_key) == 1
    assert (
        parsed.owners_by_key[
            ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top")
        ].owner_kind
        == "member"
    )
    assert parsed.diagnostics["duplicateOwnerRecords"] == 1


def test_duplicate_records_report_bounded_diagnostics():
    records = [
        *_valid_records(),
        _feature_record(
            "feature-member-start-id-duplicate",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
    ]

    parsed = rel.parse_runtime_records(records)

    assert parsed.diagnostics["duplicateFeatureRecords"] == 1
