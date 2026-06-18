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
