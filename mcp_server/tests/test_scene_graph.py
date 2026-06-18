"""Tests for SceneGraphAnalytics — the Python NetworkX analytics layer.

These tests inject synthetic data directly into the NetworkX graph,
bypassing the C# bridge. This lets us validate graph algorithms,
NL formatting, caching, and export without a live Rhino instance.
"""

import pytest
from rook.scene.scene_graph import SceneGraphAnalytics, _inverse_rel


# ---------------------------------------------------------------------------
# Fixtures: synthetic scene data
# ---------------------------------------------------------------------------

def _make_node_attrs(
    name: str = "Box1",
    layer: str = "Default",
    geometry_type: str = "Brep",
    shape_class: str = "compact",
    domain_label: str = "",
    bbox_min: list = None,
    bbox_max: list = None,
    max_dim: float = 1.0,
    mid_dim: float = 1.0,
    min_dim: float = 1.0,
    elongation: float = 1.0,
    flatness: float = 1.0,
    thinness: float = 1.0,
    volume: float = 1.0,
    centroid_z: float = 0.5,
    base_z: float = 0.0,
    top_z: float = 1.0,
    primary_axis: str = "X",
    thin_axis: str = "Z",
    confidence: float = 0.8,
    created_by: str = "",
    creation_intent: str = "",
    creation_command: str = "",
) -> dict:
    return {
        "name": name,
        "layer": layer,
        "geometry_type": geometry_type,
        "shape_class": shape_class,
        "domain_label": domain_label,
        "bbox_min": bbox_min or [0, 0, 0],
        "bbox_max": bbox_max or [1, 1, 1],
        "max_dim": max_dim,
        "mid_dim": mid_dim,
        "min_dim": min_dim,
        "elongation": elongation,
        "flatness": flatness,
        "thinness": thinness,
        "volume": volume,
        "centroid_z": centroid_z,
        "base_z": base_z,
        "top_z": top_z,
        "primary_axis": primary_axis,
        "thin_axis": thin_axis,
        "confidence": confidence,
        "created_by": created_by,
        "creation_intent": creation_intent,
        "creation_command": creation_command,
    }


def _build_room_scene() -> SceneGraphAnalytics:
    """Build a simple room: 4 walls + 1 floor + 1 ceiling.

    Layout (top view):
        Wall-N
    Wall-W  [Floor]  Wall-E
        Wall-S
    Ceiling above everything.
    """
    sg = SceneGraphAnalytics()

    # Floor: 10x10x0.2, horizontal slab
    sg.graph.add_node("floor-1", **_make_node_attrs(
        name="Floor", shape_class="horizontal-slab", domain_label="floor",
        bbox_min=[0, 0, 0], bbox_max=[10, 10, 0.2],
        max_dim=10, mid_dim=10, min_dim=0.2, flatness=50, thinness=0.02,
        base_z=0, top_z=0.2, centroid_z=0.1,
    ))

    # Walls: 10x0.2x3, vertical planar
    for i, (name, bmin, bmax) in enumerate([
        ("Wall-N", [0, 9.8, 0.2], [10, 10, 3.2]),
        ("Wall-S", [0, 0, 0.2], [10, 0.2, 3.2]),
        ("Wall-E", [9.8, 0, 0.2], [10, 10, 3.2]),
        ("Wall-W", [0, 0, 0.2], [0.2, 10, 3.2]),
    ]):
        sg.graph.add_node(f"wall-{i}", **_make_node_attrs(
            name=name, shape_class="vertical-planar", domain_label="wall",
            bbox_min=bmin, bbox_max=bmax,
            max_dim=10, mid_dim=3, min_dim=0.2, flatness=15, thinness=0.02,
            base_z=0.2, top_z=3.2, centroid_z=1.7,
            primary_axis="X" if i < 2 else "Y", thin_axis="Y" if i < 2 else "X",
        ))

    # Ceiling: 10x10x0.2, horizontal slab
    sg.graph.add_node("ceiling-1", **_make_node_attrs(
        name="Ceiling", shape_class="horizontal-slab", domain_label="ceiling",
        bbox_min=[0, 0, 3.2], bbox_max=[10, 10, 3.4],
        max_dim=10, mid_dim=10, min_dim=0.2, flatness=50, thinness=0.02,
        base_z=3.2, top_z=3.4, centroid_z=3.3,
    ))

    # Relationships
    # Floor supports all 4 walls
    for i in range(4):
        sg.graph.add_edge("floor-1", f"wall-{i}", relationship="supports", distance=0, overlap=0, direction="above")

    # Walls support ceiling
    for i in range(4):
        sg.graph.add_edge(f"wall-{i}", "ceiling-1", relationship="supports", distance=0, overlap=0, direction="above")

    # Adjacent walls (corners)
    sg.graph.add_edge("wall-0", "wall-2", relationship="adjacent", distance=0, overlap=0, direction="east")
    sg.graph.add_edge("wall-0", "wall-3", relationship="adjacent", distance=0, overlap=0, direction="west")
    sg.graph.add_edge("wall-1", "wall-2", relationship="adjacent", distance=0, overlap=0, direction="east")
    sg.graph.add_edge("wall-1", "wall-3", relationship="adjacent", distance=0, overlap=0, direction="west")

    sg._sequence = 10
    return sg


def _build_simple_chain() -> SceneGraphAnalytics:
    """A -> contains -> B -> near -> C (linear chain)."""
    sg = SceneGraphAnalytics()
    sg.graph.add_node("a", **_make_node_attrs(name="Container", domain_label="room"))
    sg.graph.add_node("b", **_make_node_attrs(name="Table", domain_label="furniture"))
    sg.graph.add_node("c", **_make_node_attrs(name="Chair", domain_label="furniture"))
    sg.graph.add_edge("a", "b", relationship="contains", distance=0, overlap=0, direction="")
    sg.graph.add_edge("b", "c", relationship="near", distance=1.5, overlap=0, direction="east")
    sg._sequence = 3
    return sg


# ---------------------------------------------------------------------------
# Tests: Basic properties
# ---------------------------------------------------------------------------

class TestBasicProperties:
    def test_empty_graph(self):
        sg = SceneGraphAnalytics()
        assert sg.node_count == 0
        assert sg.edge_count == 0
        assert sg.sequence == 0

    def test_room_counts(self):
        sg = _build_room_scene()
        assert sg.node_count == 6  # floor + 4 walls + ceiling
        assert sg.edge_count == 12  # 4 floor->wall + 4 wall->ceiling + 4 adjacent
        assert sg.sequence == 10

    def test_chain_counts(self):
        sg = _build_simple_chain()
        assert sg.node_count == 3
        assert sg.edge_count == 2


# ---------------------------------------------------------------------------
# Tests: Graph algorithms
# ---------------------------------------------------------------------------

class TestGraphAlgorithms:
    def test_find_path_direct(self):
        sg = _build_simple_chain()
        path = sg.find_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_path_no_path(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("x", **_make_node_attrs(name="X"))
        sg.graph.add_node("y", **_make_node_attrs(name="Y"))
        # No edge between them
        assert sg.find_path("x", "y") == []

    def test_find_path_missing_node(self):
        sg = _build_simple_chain()
        assert sg.find_path("a", "nonexistent") == []

    def test_find_path_room(self):
        sg = _build_room_scene()
        # Floor to ceiling: floor -> wall-X -> ceiling
        path = sg.find_path("floor-1", "ceiling-1")
        assert len(path) == 3
        assert path[0] == "floor-1"
        assert path[-1] == "ceiling-1"
        assert path[1].startswith("wall-")  # goes through a wall

    def test_community_detection_empty(self):
        sg = SceneGraphAnalytics()
        assert sg.community_detection() == {}

    def test_community_detection_room(self):
        sg = _build_room_scene()
        communities = sg.community_detection()
        # All nodes are interconnected, so likely 1-2 communities
        assert len(communities) >= 1
        all_nodes = set()
        for nodes in communities.values():
            all_nodes.update(nodes)
        assert all_nodes == set(sg.graph.nodes)

    def test_community_detection_cached(self):
        sg = _build_room_scene()
        c1 = sg.community_detection()
        c2 = sg.community_detection()
        assert c1 is c2  # Same object = cached

    def test_centrality_empty(self):
        sg = SceneGraphAnalytics()
        assert sg.centrality() == {}

    def test_centrality_room(self):
        sg = _build_room_scene()
        c = sg.centrality()
        assert len(c) == 6
        # Walls should have higher centrality (more connections)
        for i in range(4):
            assert c[f"wall-{i}"] > 0

    def test_centrality_cached(self):
        sg = _build_room_scene()
        c1 = sg.centrality()
        c2 = sg.centrality()
        assert c1 is c2

    def test_cache_invalidation(self):
        sg = _build_room_scene()
        c1 = sg.community_detection()
        cent1 = sg.centrality()
        sg._invalidate_caches()
        c2 = sg.community_detection()
        cent2 = sg.centrality()
        assert c1 is not c2  # Different objects = re-computed
        assert cent1 is not cent2


# ---------------------------------------------------------------------------
# Tests: Containment tree
# ---------------------------------------------------------------------------

class TestContainmentTree:
    def test_simple_containment(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("building", **_make_node_attrs(name="Building", domain_label="building"))
        sg.graph.add_node("room1", **_make_node_attrs(name="Room1", domain_label="room"))
        sg.graph.add_node("room2", **_make_node_attrs(name="Room2", domain_label="room"))
        sg.graph.add_node("desk", **_make_node_attrs(name="Desk", domain_label="furniture"))
        sg.graph.add_edge("building", "room1", relationship="contains", distance=0, overlap=0, direction="")
        sg.graph.add_edge("building", "room2", relationship="contains", distance=0, overlap=0, direction="")
        sg.graph.add_edge("room1", "desk", relationship="contains", distance=0, overlap=0, direction="")

        tree = sg.containment_tree()
        assert len(tree["roots"]) == 1
        root = tree["roots"][0]
        assert root["id"] == "building"
        assert len(root["children"]) == 2
        # room1 should have desk as child
        room1 = next(c for c in root["children"] if c["id"] == "room1")
        assert len(room1["children"]) == 1
        assert room1["children"][0]["id"] == "desk"

    def test_no_containment(self):
        sg = _build_simple_chain()  # uses "contains" but also "near"
        tree = sg.containment_tree()
        # "a" contains "b", so "a" is root, "c" is isolated
        assert len(tree["roots"]) == 1
        assert tree["isolated_count"] == 1  # "c" has no containment edges

    def test_empty_containment(self):
        sg = _build_room_scene()  # room has "supports" and "adjacent", no "contains"
        tree = sg.containment_tree()
        assert len(tree["roots"]) == 0
        assert tree["isolated_count"] == 6  # all nodes are isolated from containment


# ---------------------------------------------------------------------------
# Tests: Natural language context
# ---------------------------------------------------------------------------

class TestNLContext:
    def test_context_single_node(self):
        sg = _build_simple_chain()
        ctx = sg.get_context(["b"])
        assert "Table" in ctx
        assert "FURNITURE" in ctx or "furniture" in ctx.lower()

    def test_context_with_relationships(self):
        sg = _build_simple_chain()
        ctx = sg.get_context(["b"])
        # b has incoming "contains" from a, outgoing "near" to c
        assert "near" in ctx.lower() or "Chair" in ctx
        assert "within" in ctx.lower() or "Container" in ctx  # inverse of "contains"

    def test_context_missing_node(self):
        sg = _build_simple_chain()
        ctx = sg.get_context(["nonexistent"])
        assert "not in scene graph" in ctx.lower()

    def test_context_multiple_nodes(self):
        sg = _build_simple_chain()
        ctx = sg.get_context(["a", "b", "c"])
        # All three should appear
        assert "Container" in ctx
        assert "Table" in ctx
        assert "Chair" in ctx

    def test_context_room_wall(self):
        sg = _build_room_scene()
        ctx = sg.get_context(["wall-0"])
        assert "Wall-N" in ctx
        assert "WALL" in ctx
        # Should show supports relationship to ceiling
        assert "ceiling" in ctx.lower() or "Ceiling" in ctx
        # Should show supported-by from floor
        assert "floor" in ctx.lower() or "Floor" in ctx

    def test_context_formats_bim_relationships_readably(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("door", name="Door", domain_label="door", shape_class="compact")
        sg.graph.add_node("wall", name="Wall", domain_label="wall", shape_class="vertical-planar")
        sg.graph.add_node(
            "room",
            name="room-1",
            displayName="101 Office",
            nodeKind="rookbim_room",
            domain_label="room",
            shape_class="bim-reference",
        )
        sg.graph.add_node(
            "level",
            name="level-id",
            displayName="L1",
            nodeKind="rookbim_level",
            domain_label="level",
            shape_class="bim-reference",
        )
        sg.graph.add_edge("door", "wall", key="rookbim:hosted_by:fp:uid-door:uid-wall", relationship="revit_hosted_by", provenance="rookbim_sidecar")
        sg.graph.add_edge("door", "room", key="rookbim:in_room:fp:uid-door:room-1", relationship="revit_in_room", provenance="rookbim_sidecar")
        sg.graph.add_edge("door", "level", key="rookbim:on_level:fp:uid-door:L1", relationship="revit_on_level", provenance="rookbim_sidecar")

        text = sg.get_context(["door", "wall"])

        assert 'Hosted by Revit: WALL "Wall"' in text
        assert 'In Revit room: ROOM "101 Office"' in text
        assert 'On Revit level: LEVEL "L1"' in text
        assert 'Revit host for: DOOR "Door"' in text

    def test_context_renders_compact_bim_block_with_correct_edge_directions(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node(
            "door",
            name="Door-01",
            domain_label="door",
            shape_class="compact",
            rookbimJoined=True,
            revitUniqueId="uid-door",
            revitElementId="200",
            revitCategory="Doors",
            revitFamily="Single-Flush",
            revitType="0915 x 2134mm",
        )
        sg.graph.add_node(
            "wall",
            name="Wall-01",
            domain_label="wall",
            shape_class="vertical-planar",
            rookbimJoined=True,
            revitUniqueId="uid-wall",
            revitElementId="100",
            revitCategory="Walls",
            revitFamily="Basic Wall",
            revitType="Generic 200mm",
        )
        sg.graph.add_node("room", displayName="101 Office", domain_label="room", nodeKind="rookbim_room")
        sg.graph.add_node("level", displayName="L1", domain_label="level", nodeKind="rookbim_level")
        sg.graph.add_edge("door", "wall", relationship="revit_hosted_by")
        sg.graph.add_edge("door", "room", relationship="revit_in_room")
        sg.graph.add_edge("door", "level", relationship="revit_on_level")

        text = sg.get_context(["door", "wall"])

        assert "BIM: Doors | Single-Flush | 0915 x 2134mm" in text
        assert "Revit: element 200, uniqueId uid-door" in text
        assert "Room: 101 Office" in text
        assert "Level: L1" in text
        assert "Hosted by: Wall-01" in text
        assert "Hosts: 1 element" in text

    def test_context_caps_multiple_bim_rooms_and_levels(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("obj", name="Obj", rookbimJoined=True, revitCategory="Furniture")
        sg.graph.add_node("nearby", name="Nearby", domain_label="fixture")
        for i in range(5):
            sg.graph.add_node(f"room-{i}", displayName=f"{100 + i} Room", nodeKind="rookbim_room")
            sg.graph.add_node(f"level-{i}", displayName=f"L{i}", nodeKind="rookbim_level")
            sg.graph.add_edge("obj", f"room-{i}", relationship="revit_in_room")
            sg.graph.add_edge("obj", f"level-{i}", relationship="revit_on_level")
        sg.graph.add_edge("obj", "nearby", relationship="near")

        text = sg.get_context(["obj"])

        assert "Room: 100 Room, 101 Room, 102 Room, +2 more" in text
        assert "Level: L0, L1, L2, +2 more" in text
        assert "In Revit room:" not in text
        assert "On Revit level:" not in text
        assert 'near: FIXTURE "Nearby"' in text

    def test_context_suppresses_generic_incoming_bim_host_edges_after_compact_block(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("host", name="Host Wall", rookbimJoined=True, revitCategory="Walls")
        sg.graph.add_node("nearby", name="Nearby", domain_label="fixture")
        for i in range(4):
            sg.graph.add_node(f"child-{i}", name=f"Child {i}", domain_label="fixture", rookbimJoined=True)
            sg.graph.add_edge(f"child-{i}", "host", relationship="revit_hosted_by")
        sg.graph.add_edge("nearby", "host", relationship="near")

        text = sg.get_context(["host"])

        assert "Hosts: 4 elements" in text
        assert "Revit host for:" not in text
        assert 'near: FIXTURE "Nearby"' in text


# ---------------------------------------------------------------------------
# Tests: Statistics
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_empty(self):
        sg = SceneGraphAnalytics()
        stats = sg.get_stats()
        assert stats["nodes"] == 0
        assert stats["edges"] == 0
        assert stats["components"] == 0
        assert stats["density"] == 0

    def test_stats_room(self):
        sg = _build_room_scene()
        stats = sg.get_stats()
        assert stats["nodes"] == 6
        assert stats["edges"] == 12
        assert stats["sequence"] == 10
        assert "wall" in stats["classifications"] or "vertical-planar" in stats["classifications"]
        assert "supports" in stats["relationships"]
        assert "adjacent" in stats["relationships"]
        assert stats["components"] == 1  # single connected component
        assert stats["density"] > 0


# ---------------------------------------------------------------------------
# Tests: JSON export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_structure(self):
        sg = _build_simple_chain()
        j = sg.export_json()
        assert "graph" in j
        assert j["graph"]["type"] == "scene_graph"
        assert j["graph"]["directed"] is True
        assert len(j["graph"]["nodes"]) == 3
        assert len(j["graph"]["edges"]) == 2

    def test_export_node_data(self):
        sg = _build_simple_chain()
        j = sg.export_json()
        node_b = j["graph"]["nodes"]["b"]
        assert node_b["label"] == "furniture"
        assert "name" in node_b["metadata"]

    def test_export_edge_data(self):
        sg = _build_simple_chain()
        j = sg.export_json()
        edges = j["graph"]["edges"]
        rels = {e["relation"] for e in edges}
        assert "contains" in rels
        assert "near" in rels

    def test_export_empty(self):
        sg = SceneGraphAnalytics()
        j = sg.export_json()
        assert len(j["graph"]["nodes"]) == 0
        assert len(j["graph"]["edges"]) == 0


# ---------------------------------------------------------------------------
# Tests: Inverse relationships
# ---------------------------------------------------------------------------

class TestInverseRels:
    def test_known_inverses(self):
        assert _inverse_rel("contains") == "within"
        assert _inverse_rel("supports") == "supported by"
        assert _inverse_rel("above") == "below"
        assert _inverse_rel("intersects") == "intersects"
        assert _inverse_rel("adjacent") == "adjacent to"
        assert _inverse_rel("near") == "near"

    def test_unknown_inverse(self):
        assert _inverse_rel("custom_rel") == "custom_rel"


# ---------------------------------------------------------------------------
# Tests: Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_scene_graph_returns_same_instance(self):
        from rook.scene.scene_graph import get_scene_graph
        sg1 = get_scene_graph()
        sg2 = get_scene_graph()
        assert sg1 is sg2
