from pathlib import Path

from rook.scene import bim_facts_query as query
from rook.scene.scene_graph import SceneGraphAnalytics


def _bim_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg._sequence = 42
    sg.graph.add_node(
        "wall",
        name="Wall-01",
        layer="RookBim::L1::Walls",
        domain_label="wall",
        shape_class="vertical-planar",
        rookbimJoined=True,
        rookbimSidecarFingerprint="fp1",
        revitUniqueId="uid-wall",
        revitElementId="100",
        revitCategory="Walls",
        revitFamily="Basic Wall",
        revitType="Generic 200mm",
        revitName="Wall Type",
        revitLevel="L1",
    )
    sg.graph.add_node(
        "door",
        name="Door-01",
        layer="RookBim::L1::Doors",
        domain_label="door",
        shape_class="compact",
        rookbimJoined=True,
        rookbimSidecarFingerprint="fp1",
        revitUniqueId="uid-door",
        revitElementId="200",
        revitCategory="Doors",
        revitFamily="Single-Flush",
        revitType="0915 x 2134mm",
        revitName="Door Type",
        revitLevel="L1",
    )
    sg.graph.add_node("chair", name="Chair-01", domain_label="furniture", shape_class="compact")
    sg.graph.add_node(
        "room-a",
        nodeKind="rookbim_room",
        displayName="101 Office",
        roomUniqueId="room-1",
        roomNumber="101",
        roomName="Office",
        sidecarFingerprint="fp1",
        projectionKind="bim_relationship_v1",
        provenance="rookbim_sidecar",
    )
    sg.graph.add_node(
        "level-l1",
        nodeKind="rookbim_level",
        displayName="L1",
        levelName="L1",
        sidecarFingerprint="fp1",
        projectionKind="bim_relationship_v1",
        provenance="rookbim_sidecar",
    )
    sg.graph.add_edge(
        "door",
        "wall",
        key="rookbim:hosted_by:fp1:uid-door:uid-wall",
        relationship="revit_hosted_by",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
        source="revit_api",
    )
    sg.graph.add_edge(
        "door",
        "room-a",
        key="rookbim:in_room:fp1:uid-door:room-1",
        relationship="revit_in_room",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    sg.graph.add_edge(
        "door",
        "level-l1",
        key="rookbim:on_level:fp1:uid-door:L1",
        relationship="revit_on_level",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    sg.graph.add_edge(
        "wall",
        "level-l1",
        key="rookbim:on_level:fp1:uid-wall:L1",
        relationship="revit_on_level",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    return sg


def test_projection_absent_returns_hard_precondition_failure():
    sg = SceneGraphAnalytics()
    sg._sequence = 7
    sg.graph.add_node("plain", name="Plain")

    result = query.query_bim_facts(sg, mode="relationship_scan")

    assert result["success"] is False
    assert result["error"] == "bim_projection_required"
    assert result["bimProjectionPresent"] is False
    assert result["graphSequence"] == 7
    assert result["sidecarFingerprints"] == []
    assert "scene_project_bim_relationships" in result["message"]


def test_joined_sidecar_annotations_do_not_satisfy_projection_precondition():
    sg = SceneGraphAnalytics()
    sg._sequence = 8
    sg.graph.add_node(
        "wall",
        name="Wall-01",
        rookbimJoined=True,
        rookbimSidecarFingerprint="fp1",
    )

    result = query.query_bim_facts(sg, mode="relationship_scan")

    assert result["success"] is False
    assert result["error"] == "bim_projection_required"
    assert result["bimProjectionPresent"] is False


def test_unknown_mode_and_detail_are_input_errors():
    sg = _bim_graph()

    bad_mode = query.query_bim_facts(sg, mode="not_a_mode")
    assert bad_mode["success"] is False
    assert bad_mode["error"] == "invalid_bim_query_input"

    bad_detail = query.query_bim_facts(sg, mode="relationship_scan", detail="verbose")
    assert bad_detail["success"] is False
    assert bad_detail["error"] == "invalid_bim_query_input"


def test_query_module_does_not_import_runtime_projection_or_inference_modules():
    source = Path(query.__file__).read_text(encoding="utf-8")

    forbidden = [
        "call_rhino",
        "project_bim_relationships_for_tool",
        "exact_projection",
        "containment_refinement",
        "analytics.sync",
    ]
    for token in forbidden:
        assert token not in source


def test_object_context_returns_joined_and_unjoined_results():
    sg = _bim_graph()

    result = query.query_bim_facts(
        sg,
        mode="object_context",
        object_ids=["door", "chair"],
        limit=1,
    )

    assert result["success"] is True
    assert result["summary"]["effectiveLimit"] == 1
    assert result["truncated"] is False
    door = result["results"][0]
    chair = result["results"][1]

    assert door["objectId"] == "door"
    assert door["bimJoined"] is True
    assert door["identity"]["revitUniqueId"] == "uid-door"
    assert door["hostedBy"][0]["objectId"] == "wall"
    assert door["rooms"][0]["displayName"] == "101 Office"
    assert door["levels"][0]["displayName"] == "L1"
    assert door["hostedElements"]["totalCount"] == 0
    assert door["sameRoomCount"] == 1
    assert door["sameLevelCount"] == 2

    assert chair == {"objectId": "chair", "bimJoined": False}


def test_object_context_missing_object_ids_is_input_error():
    result = query.query_bim_facts(_bim_graph(), mode="object_context")

    assert result["success"] is False
    assert result["error"] == "invalid_bim_query_input"


def test_object_context_child_truncation_sets_top_level_truncated():
    sg = _bim_graph()
    for i in range(3):
        oid = f"door-{i}"
        sg.graph.add_node(oid, name=f"Door {i}", rookbimJoined=True, revitUniqueId=f"uid-door-{i}")
        sg.graph.add_edge(
            oid,
            "wall",
            key=f"rookbim:hosted_by:fp1:uid-door-{i}:uid-wall",
            relationship="revit_hosted_by",
            provenance="rookbim_sidecar",
            projectionKind="bim_relationship_v1",
            sidecarFingerprint="fp1",
        )

    result = query.query_bim_facts(sg, mode="object_context", object_ids=["wall"], limit=2)

    wall = result["results"][0]
    assert wall["hostedElements"]["totalCount"] == 4
    assert wall["hostedElements"]["effectiveLimit"] == 2
    assert wall["hostedElements"]["truncated"] is True
    assert result["truncated"] is True


def test_object_context_ignores_non_projection_bim_relationship_edges():
    sg = _bim_graph()
    sg.graph.add_node("legacy-host", name="Legacy Host", rookbimJoined=True)
    sg.graph.add_node("legacy-room", name="Legacy Room", nodeKind="rookbim_room")
    sg.graph.add_node("legacy-level", name="Legacy Level", nodeKind="rookbim_level")
    sg.graph.add_node("legacy-child", name="Legacy Child", rookbimJoined=True)
    sg.graph.add_node("legacy-room-peer", name="Legacy Room Peer", rookbimJoined=True)
    sg.graph.add_node("legacy-level-peer", name="Legacy Level Peer", rookbimJoined=True)

    sg.graph.add_edge(
        "door",
        "legacy-host",
        key="legacy:hosted_by:door:legacy-host",
        relationship="revit_hosted_by",
    )
    sg.graph.add_edge(
        "door",
        "legacy-room",
        key="legacy:in_room:door:legacy-room",
        relationship="revit_in_room",
        provenance="stale_projection",
        projectionKind="bim_relationship_v1",
    )
    sg.graph.add_edge(
        "door",
        "legacy-level",
        key="legacy:on_level:door:legacy-level",
        relationship="revit_on_level",
        provenance="rookbim_sidecar",
    )
    sg.graph.add_edge(
        "legacy-child",
        "door",
        key="legacy:hosted_by:legacy-child:door",
        relationship="revit_hosted_by",
        provenance="not_rookbim_sidecar",
        projectionKind="bim_relationship_v1",
    )
    sg.graph.add_edge(
        "legacy-room-peer",
        "room-a",
        key="legacy:in_room:peer:room-a",
        relationship="revit_in_room",
    )
    sg.graph.add_edge(
        "legacy-level-peer",
        "level-l1",
        key="legacy:on_level:peer:level-l1",
        relationship="revit_on_level",
        provenance="not_rookbim_sidecar",
        projectionKind="bim_relationship_v1",
    )

    result = query.query_bim_facts(sg, mode="object_context", object_ids=["door"], limit=10)

    door = result["results"][0]
    assert [row["objectId"] for row in door["hostedBy"]] == ["wall"]
    assert [row["objectId"] for row in door["rooms"]] == ["room-a"]
    assert [row["objectId"] for row in door["levels"]] == ["level-l1"]
    assert door["hostedElements"]["results"] == []
    assert door["hostedElements"]["totalCount"] == 0
    assert door["sameRoomCount"] == 1
    assert door["sameLevelCount"] == 2
