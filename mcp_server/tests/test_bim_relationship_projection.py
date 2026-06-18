import ast
import json
from pathlib import Path

import pytest

from rook.scene import bim_relationship_projection as bim
from rook.scene.scene_graph import SceneGraphAnalytics


def _sidecar() -> dict:
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {
                    "uniqueId": "uid-wall",
                    "elementId": 100,
                    "documentTitle": "Model A",
                },
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic 200mm",
                "name": "Wall Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": None, "source": "unavailable", "confidence": None},
                    "containingRoomId": {"value": None, "source": "unavailable", "confidence": None},
                },
            },
            {
                "identity": {
                    "uniqueId": "uid-door",
                    "elementId": 200,
                    "documentTitle": "Model A",
                },
                "category": "Doors",
                "family": "Single-Flush",
                "type": "0915 x 2134mm",
                "name": "Door Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": 100, "source": "revit_api", "confidence": "high"},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high"},
                },
            },
        ],
        "rooms": [
            {
                "uniqueId": "room-1",
                "roomId": "room-1",
                "number": "101",
                "name": "Office",
                "geometryRepresentation": "room_mesh",
                "referenceGeometry": True,
            }
        ],
        "relationships": {
            "hostMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "hostUniqueId": "uid-wall",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "roomMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "roomUniqueId": "room-1",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "levelMembership": [
                {
                    "elementUniqueId": "uid-wall",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
                {
                    "elementUniqueId": "uid-door",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
            ],
        },
    }


def _analytics_with_bim_nodes() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("rh-wall", name="Wall", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node("rh-door", name="Door", domain_label="door", shape_class="compact")
    sg._sequence = 9
    return sg


def _analytics_with_multi_fragment_bim_nodes() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("rh-wall-a", name="Wall A", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node("rh-wall-b", name="Wall B", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node("rh-door-a", name="Door A", domain_label="door", shape_class="compact")
    sg.graph.add_node("rh-door-b", name="Door B", domain_label="door", shape_class="compact")
    sg._sequence = 9
    return sg


def _joined_for_projection():
    return bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.elementId": "100", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.elementId": "200", "revit.category": "Doors"}),
    ])


def test_module_constants():
    assert bim.PROJECTION_KIND == "bim_relationship_v1"
    assert bim.PROVENANCE == "rookbim_sidecar"
    assert bim.REL_HOSTED_BY == "revit_hosted_by"
    assert bim.REL_IN_ROOM == "revit_in_room"
    assert bim.REL_ON_LEVEL == "revit_on_level"
    assert bim.ENGINE_VERSION == 1


def test_projector_source_does_not_call_inference_mutation_or_save_routes():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "rook"
        / "scene"
        / "bim_relationship_projection.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = [
        "scene_exact_neighbors",
        "scene_refine_containment",
        "/scene/graph/adjacency/exact",
        "/bim/",
        "/usertext/object-set",
        "/usertext/object-set-batch",
        "/usertext/object-delete",
        "/document/save",
    ]

    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstring_nodes.add(value)

    executable_tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstring_nodes:
                executable_tokens.add(node.value)
        elif isinstance(node, ast.Name):
            executable_tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            executable_tokens.add(node.attr)
        elif isinstance(node, ast.alias):
            executable_tokens.add(node.name)
            if node.asname:
                executable_tokens.add(node.asname)

    assert "/usertext/object-get" in executable_tokens
    for token in forbidden:
        assert not any(token in executable_token for executable_token in executable_tokens)


def test_node_attrs_include_bim_projection_annotations():
    assert {
        "rookbimJoined",
        "rookbimSidecarFingerprint",
        "rookbimSidecarPath",
        "rookbimGraphSequence",
        "revitUniqueId",
        "revitElementId",
        "revitCategory",
        "revitFamily",
        "revitType",
        "revitName",
        "revitLevel",
    }.issubset(set(bim.NODE_ATTRS))


def test_parse_sidecar_payload_normalizes_real_export_shape():
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")

    assert sidecar.schema_version == 1
    assert sidecar.source_path == "C:/tmp/shell.sidecar.json"
    assert set(sidecar.elements_by_uid) == {"uid-wall", "uid-door"}
    assert sidecar.elements_by_uid["uid-door"].category == "Doors"
    assert sidecar.elements_by_uid["uid-door"].element_id == "200"
    assert sidecar.elements_by_uid["uid-door"].family == "Single-Flush"
    assert sidecar.elements_by_uid["uid-door"].type_name == "0915 x 2134mm"
    assert sidecar.elements_by_uid["uid-door"].name == "Door Type"
    assert sidecar.elements_by_uid["uid-door"].level == "L1"
    assert sidecar.rooms_by_uid["room-1"].display_name == "101 Office"
    assert sidecar.host_memberships[0].element_uid == "uid-door"
    assert sidecar.host_memberships[0].target_uid == "uid-wall"
    assert sidecar.room_memberships[0].target_uid == "room-1"
    assert sidecar.level_memberships[0].target_uid == "L1"


def test_parse_sidecar_payload_requires_object_root():
    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload([])

    assert "root" in str(exc.value)


def test_parse_sidecar_payload_requires_integer_or_null_schema_version():
    payload = _sidecar()
    payload["schemaVersion"] = "1"

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "schemaVersion" in str(exc.value)


def test_parse_sidecar_payload_rejects_boolean_schema_version():
    payload = _sidecar()
    payload["schemaVersion"] = True

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "schemaVersion" in str(exc.value)


def test_parse_sidecar_payload_requires_enabled_sections():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "roomMembership" in str(exc.value)


def test_parse_sidecar_payload_requires_host_membership():
    payload = _sidecar()
    del payload["relationships"]["hostMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "hostMembership" in str(exc.value)


def test_parse_sidecar_payload_requires_enabled_level_section():
    payload = _sidecar()
    del payload["relationships"]["levelMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "levelMembership" in str(exc.value)


def test_parse_sidecar_payload_allows_disabled_room_section():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    sidecar = bim.parse_sidecar_payload(payload, include_rooms=False, include_levels=True)

    assert sidecar.room_memberships == []


def test_parse_sidecar_payload_requires_rooms_list_when_present():
    payload = _sidecar()
    payload["rooms"] = {"room-1": {"name": "Office"}}

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload)

    assert "rooms" in str(exc.value)
    assert "list" in str(exc.value)


def test_parse_sidecar_payload_allows_missing_rooms_section():
    payload = _sidecar()
    del payload["rooms"]

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.rooms_by_uid == {}


def test_parse_sidecar_payload_diagnoses_malformed_elements_and_missing_uid():
    payload = _sidecar()
    payload["elements"].extend([
        "not-an-element",
        {"identity": {"elementId": 300}, "category": "Windows"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert set(sidecar.elements_by_uid) == {"uid-wall", "uid-door"}
    assert sidecar.diagnostics["malformedElementRecords"] == 1
    assert sidecar.diagnostics["elementsMissingUniqueId"] == 1


def test_parse_sidecar_payload_diagnoses_duplicate_elements_last_record_wins():
    payload = _sidecar()
    payload["elements"].append({
        "identity": {"uniqueId": "uid-door", "elementId": 201},
        "category": "Doors",
        "family": "Replacement",
        "type": "Replacement Type",
        "name": "Replacement Door",
        "labels": {"level": {"value": "L2"}},
    })

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.diagnostics["duplicateElements"] == 1
    assert sidecar.elements_by_uid["uid-door"].element_id == "201"
    assert sidecar.elements_by_uid["uid-door"].family == "Replacement"
    assert sidecar.elements_by_uid["uid-door"].level == "L2"


def test_parse_sidecar_payload_diagnoses_malformed_rooms_and_duplicate_rooms():
    payload = _sidecar()
    payload["rooms"].extend([
        "not-a-room",
        {"number": "102", "name": "No Id"},
        {"uniqueId": "room-1", "number": "103", "name": "Replacement"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert sidecar.diagnostics["malformedRoomRecords"] == 1
    assert sidecar.diagnostics["roomsMissingUniqueId"] == 1
    assert sidecar.diagnostics["duplicateRooms"] == 1
    assert sidecar.rooms_by_uid["room-1"].display_name == "103 Replacement"


def test_parse_sidecar_payload_diagnoses_malformed_and_incomplete_memberships():
    payload = _sidecar()
    payload["relationships"]["hostMembership"].extend([
        "not-a-membership",
        {"hostUniqueId": "uid-wall"},
        {"elementUniqueId": "uid-door"},
    ])

    sidecar = bim.parse_sidecar_payload(payload)

    assert len(sidecar.host_memberships) == 1
    assert sidecar.diagnostics["malformedHostMembershipRecords"] == 1
    assert sidecar.diagnostics["hostMembershipMissingElementUniqueId"] == 1
    assert sidecar.diagnostics["hostMembershipMissingTarget"] == 1


def test_fingerprint_uses_file_content(tmp_path):
    path_a = tmp_path / "a.sidecar.json"
    path_b = tmp_path / "b.sidecar.json"
    path_c = tmp_path / "c.sidecar.json"
    path_a.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")
    changed = _sidecar()
    changed["elements"][0]["category"] = "Modified Walls"
    path_c.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")

    fp_a = bim.fingerprint_sidecar_path(path_a)
    fp_b = bim.fingerprint_sidecar_path(path_b)
    fp_c = bim.fingerprint_sidecar_path(path_c)

    assert fp_a == fp_b
    assert fp_a != fp_c
    assert fp_a.short_id != fp_c.short_id
    assert len(fp_a.short_id) == 16
    assert fp_a.full_hash


def test_build_runtime_join_map_extracts_revit_user_strings():
    records = [
        bim.RuntimeObjectRecord(
            object_id="rh-wall",
            user_strings={
                "revit.uniqueId": "uid-wall",
                "revit.elementId": "100",
                "revit.category": "Walls",
            },
        ),
        bim.RuntimeObjectRecord(
            object_id="rh-no-uid",
            user_strings={"revit.category": "Doors"},
        ),
    ]

    join = bim.build_runtime_join_map(records)

    assert join.by_revit_uid["uid-wall"][0].object_id == "rh-wall"
    assert join.by_object_id["rh-wall"].revit_category == "Walls"
    assert join.diagnostics["objectsMissingRevitUniqueId"] == 1


def test_build_runtime_join_map_retains_duplicate_revit_uid_fragments():
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall-a", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-wall-b", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
    ])

    assert [joined.object_id for joined in join.by_revit_uid["uid-wall"]] == ["rh-wall-a", "rh-wall-b"]
    assert join.by_object_id["rh-wall-a"].object_id == "rh-wall-a"
    assert join.by_object_id["rh-wall-b"].object_id == "rh-wall-b"
    assert join.diagnostics["duplicateRuntimeRevitUniqueIds"] == 1


def test_build_runtime_join_map_diagnoses_duplicate_object_ids_last_record_wins():
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall-a", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall-b", "revit.category": "Walls"}),
    ])

    assert join.by_object_id["rh-wall"].revit_unique_id == "uid-wall-b"
    assert "uid-wall-a" not in join.by_revit_uid
    assert join.by_revit_uid["uid-wall-b"][0].object_id == "rh-wall"
    assert join.diagnostics["duplicateRuntimeObjectIds"] == 1


def test_build_runtime_join_map_handles_mixed_duplicate_uid_and_object_id_replacements():
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("a", {"revit.uniqueId": "u1"}),
        bim.RuntimeObjectRecord("b", {"revit.uniqueId": "u1"}),
        bim.RuntimeObjectRecord("b", {"revit.uniqueId": "u2"}),
    ])

    assert join.by_object_id["a"].revit_unique_id == "u1"
    assert join.by_object_id["b"].revit_unique_id == "u2"
    assert join.by_revit_uid["u1"][0].object_id == "a"
    assert join.by_revit_uid["u2"][0].object_id == "b"


def test_select_eligible_objects_honors_object_ids_and_category_filters():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.category": "Doors"}),
    ])

    eligible = bim.select_eligible_objects(
        join,
        sidecar,
        object_ids=["rh-door"],
        category_filters=["doors"],
    )

    assert eligible.object_ids == {"rh-door"}
    assert eligible.revit_uids == {"uid-door"}
    assert eligible.diagnostics == {}


def test_select_eligible_objects_with_empty_object_ids_selects_none():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.category": "Doors"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar, object_ids=[])

    assert eligible.object_ids == set()
    assert eligible.revit_uids == set()
    assert eligible.diagnostics == {}


def test_select_eligible_objects_uses_all_joinable_when_no_filters():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.category": "Doors"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar)

    assert eligible.object_ids == {"rh-wall", "rh-door"}
    assert eligible.revit_uids == {"uid-wall", "uid-door"}


def test_select_eligible_objects_diagnoses_requested_object_not_joinable():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar, object_ids=["rh-missing"])

    assert eligible.object_ids == set()
    assert eligible.revit_uids == set()
    assert eligible.diagnostics["requestedObjectNotJoinable"] == 1


def test_select_eligible_objects_diagnoses_joined_object_missing_from_sidecar():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-window", {"revit.uniqueId": "uid-window", "revit.category": "Windows"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar)

    assert eligible.object_ids == set()
    assert eligible.revit_uids == set()
    assert eligible.diagnostics["joinedObjectMissingFromSidecar"] == 1


def test_select_eligible_objects_diagnoses_category_mismatch():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar, category_filters=["doors"])

    assert eligible.object_ids == set()
    assert eligible.revit_uids == set()
    assert eligible.diagnostics["filteredByCategory"] == 1


def test_select_eligible_objects_matches_sidecar_category_when_runtime_category_is_missing():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar, category_filters=["doors"])

    assert eligible.object_ids == {"rh-door"}
    assert eligible.revit_uids == {"uid-door"}
    assert eligible.diagnostics == {}


def test_project_bim_relationships_upserts_nodes_edges_and_annotations():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=True,
        include_levels=True,
    )

    assert result["counts"]["annotatedObjectCount"] == 2
    assert result["counts"]["projectedHostEdges"] == 1
    assert result["counts"]["projectedRoomEdges"] == 1
    assert result["counts"]["projectedLevelEdges"] == 2
    assert sg.graph.nodes["rh-door"]["revitUniqueId"] == "uid-door"
    assert sg.graph.nodes["rh-door"]["revitCategory"] == "Doors"

    host_key = "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall"
    assert sg.graph["rh-door"]["rh-wall"][host_key]["relationship"] == "revit_hosted_by"
    assert sg.graph["rh-door"]["rh-wall"][host_key]["projectionKind"] == bim.PROJECTION_KIND

    room_id = bim.room_node_id(fp, "room-1")
    assert sg.graph.nodes[room_id]["nodeKind"] == "rookbim_room"
    assert sg.graph.nodes[room_id]["displayName"] == "101 Office"
    assert sg.graph.nodes[room_id]["name"] == "101 Office"
    assert sg.graph.nodes[room_id]["domain_label"] == "room"
    assert sg.graph.nodes[room_id]["shape_class"] == "bim-reference"

    level_id = bim.level_node_id(fp, "L1")
    assert sg.graph.nodes[level_id]["nodeKind"] == "rookbim_level"
    assert sg.graph.nodes[level_id]["name"] == "L1"
    assert sg.graph.nodes[level_id]["domain_label"] == "level"
    assert sg.graph.nodes[level_id]["shape_class"] == "bim-reference"
    level_segment = level_id.rsplit(":", 1)[-1]
    assert sg.graph.has_edge(
        "rh-door",
        level_id,
        f"rookbim:on_level:abcdefabcdefabcd:uid-door:{level_segment}",
    )


def test_project_bim_relationships_projects_all_multi_fragment_uid_edges():
    sg = _analytics_with_multi_fragment_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall-a", {"revit.uniqueId": "uid-wall", "revit.elementId": "100", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-wall-b", {"revit.uniqueId": "uid-wall", "revit.elementId": "100", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door-a", {"revit.uniqueId": "uid-door", "revit.elementId": "200", "revit.category": "Doors"}),
        bim.RuntimeObjectRecord("rh-door-b", {"revit.uniqueId": "uid-door", "revit.elementId": "200", "revit.category": "Doors"}),
    ])
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=True,
        include_levels=True,
    )

    assert result["counts"]["annotatedObjectCount"] == 4
    assert result["counts"]["projectedHostEdges"] == 4
    assert result["counts"]["projectedRoomEdges"] == 2
    assert result["counts"]["projectedLevelEdges"] == 4
    assert result["diagnostics"]["duplicateRuntimeRevitUniqueIds"] == 2
    for object_id in ["rh-wall-a", "rh-wall-b", "rh-door-a", "rh-door-b"]:
        assert sg.graph.nodes[object_id]["projectionKind"] == bim.PROJECTION_KIND

    host_edges = [
        (source, target, key)
        for source, target, key, attrs in sg.graph.edges(keys=True, data=True)
        if attrs.get("relationship") == bim.REL_HOSTED_BY
    ]
    assert sorted((source, target) for source, target, _key in host_edges) == [
        ("rh-door-a", "rh-wall-a"),
        ("rh-door-a", "rh-wall-b"),
        ("rh-door-b", "rh-wall-a"),
        ("rh-door-b", "rh-wall-b"),
    ]
    assert len({key for _source, _target, key in host_edges}) == 4

    room_id = bim.room_node_id(fp, "room-1")
    room_edges = [
        (source, target, key)
        for source, target, key, attrs in sg.graph.edges(keys=True, data=True)
        if attrs.get("relationship") == bim.REL_IN_ROOM
    ]
    assert sorted((source, target) for source, target, _key in room_edges) == [
        ("rh-door-a", room_id),
        ("rh-door-b", room_id),
    ]
    assert len({key for _source, _target, key in room_edges}) == 2

    level_id = bim.level_node_id(fp, "L1")
    level_edges = [
        (source, target, key)
        for source, target, key, attrs in sg.graph.edges(keys=True, data=True)
        if attrs.get("relationship") == bim.REL_ON_LEVEL
    ]
    assert sorted((source, target) for source, target, _key in level_edges) == [
        ("rh-door-a", level_id),
        ("rh-door-b", level_id),
        ("rh-wall-a", level_id),
        ("rh-wall-b", level_id),
    ]
    assert len({key for _source, _target, key in level_edges}) == 4


def test_projection_edge_keys_preserve_raw_revit_uids_except_level_segment():
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    assert (
        bim.host_edge_key(fp, "uid:door {A}", "uid:wall/B")
        == "rookbim:hosted_by:abcdefabcdefabcd:uid:door {A}:uid:wall/B"
    )
    assert (
        bim.room_edge_key(fp, "uid:door {A}", "room:101 A")
        == "rookbim:in_room:abcdefabcdefabcd:uid:door {A}:room:101 A"
    )
    assert (
        bim.level_edge_key(fp, "uid:door {A}", "Level 1/A")
        == f"rookbim:on_level:abcdefabcdefabcd:uid:door {{A}}:{bim.level_node_id(fp, 'Level 1/A').rsplit(':', 1)[-1]}"
    )


def test_project_bim_relationships_is_idempotent_for_same_inputs():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)
    first_edges = sg.graph.number_of_edges()
    second = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert sg.graph.number_of_edges() == first_edges
    assert second["counts"]["roomNodes"] == 1
    assert second["counts"]["levelNodes"] == 1
    assert second["counts"]["createdRoomNodes"] == 0
    assert second["counts"]["createdLevelNodes"] == 0


def test_room_and_level_node_ids_are_collision_resistant_for_same_normalized_values():
    payload = _sidecar()
    payload["rooms"] = [
        {"uniqueId": "room:101 A", "number": "101", "name": "A"},
        {"uniqueId": "room 101/A", "number": "101", "name": "Slash A"},
    ]
    payload["relationships"]["roomMembership"] = [
        {"elementUniqueId": "uid-door", "roomUniqueId": "room:101 A"},
        {"elementUniqueId": "uid-door", "roomUniqueId": "room 101/A"},
    ]
    payload["relationships"]["levelMembership"] = [
        {"elementUniqueId": "uid-wall", "levelName": "Level 1/A"},
        {"elementUniqueId": "uid-door", "levelName": "Level 1 A"},
    ]
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(payload)
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    room_a = bim.room_node_id(fp, "room:101 A")
    room_b = bim.room_node_id(fp, "room 101/A")
    level_a = bim.level_node_id(fp, "Level 1/A")
    level_b = bim.level_node_id(fp, "Level 1 A")
    assert room_a != room_b
    assert level_a != level_b
    assert sg.graph.has_node(room_a)
    assert sg.graph.has_node(room_b)
    assert sg.graph.has_node(level_a)
    assert sg.graph.has_node(level_b)
    assert result["counts"]["roomNodes"] == 2
    assert result["counts"]["levelNodes"] == 2


def test_project_bim_relationships_sums_diagnostics_from_inputs():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    sidecar.diagnostics["sharedDiagnostic"] = 1
    join.diagnostics["sharedDiagnostic"] = 2
    eligible.diagnostics["sharedDiagnostic"] = 3
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert result["diagnostics"]["sharedDiagnostic"] == 6


def test_host_edge_requires_host_present_but_not_eligible():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar, object_ids=["rh-door"])
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert result["counts"]["eligibleObjectCount"] == 1
    assert result["counts"]["projectedHostEdges"] == 1
    assert sg.graph.has_edge("rh-door", "rh-wall", "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall")


def test_sparse_room_node_is_created_when_room_record_missing():
    payload = _sidecar()
    payload["rooms"] = []
    sidecar = bim.parse_sidecar_payload(payload)
    sg = _analytics_with_bim_nodes()
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar, object_ids=["rh-door"])
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    room_id = bim.room_node_id(fp, "room-1")
    assert sg.graph.nodes[room_id]["recordCompleteness"] == "sparse"
    assert result["diagnostics"]["roomReferenceMissingRecord"] == 1


def test_prune_removes_only_bim_relationship_v1_artifacts():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)
    sg.graph.add_edge("rh-door", "rh-wall", key="future:bim", relationship="future_bim", provenance="rookbim_sidecar")

    room_id = bim.room_node_id(fp, "room-1")
    level_id = bim.level_node_id(fp, "L1")
    assert sg.graph.has_node(room_id)
    assert sg.graph.has_node(level_id)

    result = bim.prune_bim_relationship_projection(sg)

    assert result["pruned"] is True
    assert sg.graph.has_edge("rh-door", "rh-wall", "future:bim")
    assert not sg.graph.has_edge("rh-door", "rh-wall", "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall")
    assert not sg.graph.has_node(room_id)
    assert not sg.graph.has_node(level_id)
    assert "revitUniqueId" not in sg.graph.nodes["rh-door"]
    assert "projectionKind" not in sg.graph.nodes["rh-door"]
    assert "provenance" not in sg.graph.nodes["rh-door"]
    assert "rookbimEngineVersion" not in sg.graph.nodes["rh-door"]


def test_project_can_skip_room_and_level_families():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sidecar = bim.parse_sidecar_payload(_sidecar(), include_rooms=False, include_levels=False)
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)

    result = bim.project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=False,
        include_levels=False,
    )

    assert result["counts"]["projectedHostEdges"] == 1
    assert result["counts"]["projectedRoomEdges"] == 0
    assert result["counts"]["projectedLevelEdges"] == 0
    assert result["counts"]["roomNodes"] == 0
    assert result["counts"]["levelNodes"] == 0
    assert sg.graph.has_edge("rh-door", "rh-wall", "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall")
    assert not sg.graph.has_node(bim.room_node_id(fp, "room-1"))
    assert not sg.graph.has_node(bim.level_node_id(fp, "L1"))


def test_projection_requires_prune_only_for_changed_sequence_or_sidecar():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert bim.projection_requires_prune(sg, fp) is False

    changed_fp = bim.SidecarFingerprint(full_hash="123456" * 11, short_id="1234567890abcdef")
    assert bim.projection_requires_prune(sg, changed_fp) is True

    sg._sequence += 1
    assert bim.projection_requires_prune(sg, fp) is True


def test_prune_ignores_joined_annotations_not_owned_by_this_projector():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sg.graph.nodes["rh-door"].update({
        "rookbimJoined": True,
        "rookbimSidecarFingerprint": "otherfingerprint",
        "rookbimGraphSequence": sg.sequence - 1,
        "revitUniqueId": "uid-door",
    })
    sg.graph.nodes["rh-wall"].update({
        "projectionKind": "future_bim_relationship_v2",
        "rookbimJoined": True,
        "rookbimSidecarFingerprint": "otherfingerprint",
        "rookbimGraphSequence": sg.sequence - 1,
        "revitUniqueId": "uid-wall",
    })

    assert bim.projection_requires_prune(sg, fp) is False

    result = bim.prune_bim_relationship_projection(sg)

    assert result["pruned"] is False
    assert sg.graph.nodes["rh-door"]["rookbimJoined"] is True
    assert sg.graph.nodes["rh-door"]["rookbimSidecarFingerprint"] == "otherfingerprint"
    assert sg.graph.nodes["rh-door"]["revitUniqueId"] == "uid-door"
    assert sg.graph.nodes["rh-wall"]["projectionKind"] == "future_bim_relationship_v2"
    assert sg.graph.nodes["rh-wall"]["rookbimJoined"] is True
    assert sg.graph.nodes["rh-wall"]["rookbimSidecarFingerprint"] == "otherfingerprint"
    assert sg.graph.nodes["rh-wall"]["revitUniqueId"] == "uid-wall"
