"""Tests for Sugiyama layout algorithm."""

import pytest
from rook.learning.sugiyama import SugiyamaLayout, Node, Edge


class TestGraphBuilding:
    """Test graph construction from GH data."""

    def test_build_graph_simple_chain(self):
        """Build graph from A -> B -> C chain."""
        # Simulated gh_query result
        components = [
            {"guid": "a", "name": "Slider", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "b", "name": "Addition", "position": {"x": 200, "y": 0}, "size": {"width": 80, "height": 40}},
            {"guid": "c", "name": "Panel", "position": {"x": 400, "y": 0}, "size": {"width": 60, "height": 30}},
        ]

        # Simulated connection data: a->b, b->c
        connections = {
            "a": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "b"}]}]},
            "b": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}]}],
                  "outputs": [{"recipients": [{"recipientComponentGuid": "c"}]}]},
            "c": {"inputs": [{"sources": [{"sourceComponentGuid": "b"}]}], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        assert len(layout.nodes) == 3
        assert len(layout.edges) == 2
        assert layout.nodes["a"].name == "Slider"
        assert layout.nodes["b"].name == "Addition"

    def test_build_graph_with_fan_out(self):
        """Build graph where one component feeds multiple."""
        components = [
            {"guid": "src", "name": "Slider", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "dst1", "name": "Add", "position": {"x": 200, "y": 0}, "size": {"width": 80, "height": 40}},
            {"guid": "dst2", "name": "Multiply", "position": {"x": 200, "y": 100}, "size": {"width": 80, "height": 40}},
        ]

        connections = {
            "src": {"inputs": [], "outputs": [{"recipients": [
                {"recipientComponentGuid": "dst1"},
                {"recipientComponentGuid": "dst2"}
            ]}]},
            "dst1": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
            "dst2": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        assert len(layout.nodes) == 3
        assert len(layout.edges) == 2  # src->dst1, src->dst2

    def test_build_graph_with_fan_in(self):
        """Build graph where multiple components feed one."""
        components = [
            {"guid": "a", "name": "SliderA", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "b", "name": "SliderB", "position": {"x": 0, "y": 50}, "size": {"width": 100, "height": 20}},
            {"guid": "c", "name": "Add", "position": {"x": 200, "y": 25}, "size": {"width": 80, "height": 40}},
        ]

        connections = {
            "a": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "c"}]}]},
            "b": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "c"}]}]},
            "c": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}, {"sourceComponentGuid": "b"}]}], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        assert len(layout.nodes) == 3
        assert len(layout.edges) == 2  # a->c, b->c

    def test_build_graph_empty(self):
        """Build graph with no components."""
        layout = SugiyamaLayout()
        layout.build_graph([], {})

        assert len(layout.nodes) == 0
        assert len(layout.edges) == 0

    def test_build_graph_isolated_node(self):
        """Build graph with a node that has no connections."""
        components = [
            {"guid": "a", "name": "Panel", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
        ]

        connections = {
            "a": {"inputs": [], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        assert len(layout.nodes) == 1
        assert len(layout.edges) == 0
        assert layout.nodes["a"].name == "Panel"

    def test_build_graph_stores_dimensions(self):
        """Build graph correctly stores node dimensions."""
        components = [
            {"guid": "a", "name": "Slider", "position": {"x": 10, "y": 20}, "size": {"width": 150, "height": 25}},
        ]

        connections = {"a": {"inputs": [], "outputs": []}}

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        node = layout.nodes["a"]
        assert node.width == 150
        assert node.height == 25
        assert node.original_x == 10
        assert node.original_y == 20

    def test_build_graph_deduplicates_edges(self):
        """Build graph doesn't create duplicate edges for multi-output connections."""
        components = [
            {"guid": "a", "name": "Slider", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "b", "name": "Add", "position": {"x": 200, "y": 0}, "size": {"width": 80, "height": 40}},
        ]

        # Two different outputs from a both connect to b
        connections = {
            "a": {"inputs": [], "outputs": [
                {"recipients": [{"recipientComponentGuid": "b"}]},
                {"recipients": [{"recipientComponentGuid": "b"}]},
            ]},
            "b": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}]}], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        # Should only have one edge a->b despite two output connections
        assert len(layout.edges) == 1

    def test_node_defaults(self):
        """Verify Node default values."""
        node = Node(
            guid="test",
            name="Test",
            width=100,
            height=40,
            original_x=0,
            original_y=0,
        )

        assert node.layer == -1
        assert node.position_in_layer == -1
        assert node.x == 0.0
        assert node.y == 0.0

    def test_edge_creation(self):
        """Verify Edge creation."""
        edge = Edge(source_guid="a", target_guid="b")

        assert edge.source_guid == "a"
        assert edge.target_guid == "b"

    def test_adjacency_lists_built(self):
        """Verify adjacency lists are correctly built."""
        components = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "b", "name": "B", "position": {"x": 100, "y": 0}, "size": {"width": 100, "height": 20}},
            {"guid": "c", "name": "C", "position": {"x": 200, "y": 0}, "size": {"width": 100, "height": 20}},
        ]

        connections = {
            "a": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "b"}]}]},
            "b": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}]}],
                  "outputs": [{"recipients": [{"recipientComponentGuid": "c"}]}]},
            "c": {"inputs": [{"sources": [{"sourceComponentGuid": "b"}]}], "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)

        # Check forward adjacency
        assert "b" in layout._adjacency["a"]
        assert "c" in layout._adjacency["b"]
        assert layout._adjacency["c"] == []

        # Check reverse adjacency
        assert layout._reverse_adjacency["a"] == []
        assert "a" in layout._reverse_adjacency["b"]
        assert "b" in layout._reverse_adjacency["c"]


class TestLayerAssignment:
    """Test Sugiyama layer assignment phase."""

    def test_assign_layers_simple_chain(self):
        """A → B → C should get layers 0, 1, 2."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0),
            "b": Node("b", "B", 100, 40, 0, 0),
            "c": Node("c", "C", 100, 40, 0, 0),
        }
        layout.edges = [Edge("a", "b"), Edge("b", "c")]
        layout._adjacency = {"a": ["b"], "b": ["c"], "c": []}
        layout._reverse_adjacency = {"a": [], "b": ["a"], "c": ["b"]}

        layout.assign_layers()

        assert layout.nodes["a"].layer == 0
        assert layout.nodes["b"].layer == 1
        assert layout.nodes["c"].layer == 2

    def test_assign_layers_fan_out(self):
        """Source at layer 0, both targets at layer 1."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "src": Node("src", "Src", 100, 40, 0, 0),
            "dst1": Node("dst1", "Dst1", 100, 40, 0, 0),
            "dst2": Node("dst2", "Dst2", 100, 40, 0, 0),
        }
        layout.edges = [Edge("src", "dst1"), Edge("src", "dst2")]
        layout._adjacency = {"src": ["dst1", "dst2"], "dst1": [], "dst2": []}
        layout._reverse_adjacency = {"src": [], "dst1": ["src"], "dst2": ["src"]}

        layout.assign_layers()

        assert layout.nodes["src"].layer == 0
        assert layout.nodes["dst1"].layer == 1
        assert layout.nodes["dst2"].layer == 1

    def test_assign_layers_diamond(self):
        """A → B, A → C, B → D, C → D should have A:0, B:1, C:1, D:2."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0),
            "b": Node("b", "B", 100, 40, 0, 0),
            "c": Node("c", "C", 100, 40, 0, 0),
            "d": Node("d", "D", 100, 40, 0, 0),
        }
        layout.edges = [Edge("a", "b"), Edge("a", "c"), Edge("b", "d"), Edge("c", "d")]
        layout._adjacency = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}
        layout._reverse_adjacency = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}

        layout.assign_layers()

        assert layout.nodes["a"].layer == 0
        assert layout.nodes["b"].layer == 1
        assert layout.nodes["c"].layer == 1
        assert layout.nodes["d"].layer == 2

    def test_assign_layers_disconnected(self):
        """Disconnected nodes get layer 0."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "alone": Node("alone", "Alone", 100, 40, 0, 0),
            "a": Node("a", "A", 100, 40, 0, 0),
            "b": Node("b", "B", 100, 40, 0, 0),
        }
        layout.edges = [Edge("a", "b")]
        layout._adjacency = {"alone": [], "a": ["b"], "b": []}
        layout._reverse_adjacency = {"alone": [], "a": [], "b": ["a"]}

        layout.assign_layers()

        assert layout.nodes["alone"].layer == 0  # No inputs, so layer 0
        assert layout.nodes["a"].layer == 0
        assert layout.nodes["b"].layer == 1


class TestCrossingMinimization:
    """Test Sugiyama crossing minimization phase."""

    def test_minimize_crossings_simple(self):
        """Two parallel edges should not cross."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a1": Node("a1", "A1", 100, 40, 0, 0, layer=0),
            "a2": Node("a2", "A2", 100, 40, 0, 50, layer=0),
            "b1": Node("b1", "B1", 100, 40, 200, 0, layer=1),
            "b2": Node("b2", "B2", 100, 40, 200, 50, layer=1),
        }
        # a1→b1, a2→b2 (parallel, no crossing needed)
        layout.edges = [Edge("a1", "b1"), Edge("a2", "b2")]
        layout._adjacency = {"a1": ["b1"], "a2": ["b2"], "b1": [], "b2": []}
        layout._reverse_adjacency = {"a1": [], "a2": [], "b1": ["a1"], "b2": ["a2"]}

        layout.minimize_crossings()

        # After minimization, b1 should be above b2 (matching a1, a2 order)
        assert layout.nodes["b1"].position_in_layer < layout.nodes["b2"].position_in_layer

    def test_minimize_crossings_reorder_needed(self):
        """Crossed edges should be uncrossed by reordering."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a1": Node("a1", "A1", 100, 40, 0, 0, layer=0),
            "a2": Node("a2", "A2", 100, 40, 0, 50, layer=0),
            "b1": Node("b1", "B1", 100, 40, 200, 50, layer=1),  # Wrong Y
            "b2": Node("b2", "B2", 100, 40, 200, 0, layer=1),   # Wrong Y
        }
        # a1→b2, a2→b1 (crossing - should reorder layer 1)
        layout.edges = [Edge("a1", "b2"), Edge("a2", "b1")]
        layout._adjacency = {"a1": ["b2"], "a2": ["b1"], "b1": [], "b2": []}
        layout._reverse_adjacency = {"a1": [], "a2": [], "b1": ["a2"], "b2": ["a1"]}

        layout.minimize_crossings()

        # After minimization: b2 should be first (connected to a1 which is first)
        # and b1 should be second (connected to a2 which is second)
        assert layout.nodes["b2"].position_in_layer < layout.nodes["b1"].position_in_layer


class TestCoordinateAssignment:
    """Test Sugiyama coordinate assignment phase."""

    def test_calculate_positions_simple_chain(self):
        """Three nodes in a chain should be positioned left to right."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0, layer=0, position_in_layer=0),
            "b": Node("b", "B", 80, 40, 0, 0, layer=1, position_in_layer=0),
            "c": Node("c", "C", 60, 30, 0, 0, layer=2, position_in_layer=0),
        }
        layout.edges = [Edge("a", "b"), Edge("b", "c")]

        positions = layout.calculate_positions(
            start_x=50, start_y=50,
            horizontal_gap=30, vertical_gap=20
        )

        # Check X positions increase left to right
        assert positions["a"]["x"] == 50
        assert positions["b"]["x"] == 50 + 100 + 30  # start + width_a + gap = 180
        assert positions["c"]["x"] == 180 + 80 + 30  # prev + width_b + gap = 290

        # Y should be same (single row)
        assert positions["a"]["y"] == 50
        assert positions["b"]["y"] == 50
        assert positions["c"]["y"] == 50

    def test_calculate_positions_vertical_stacking(self):
        """Multiple nodes in same layer should stack vertically."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0, layer=0, position_in_layer=0),
            "b": Node("b", "B", 100, 50, 0, 0, layer=0, position_in_layer=1),
            "c": Node("c", "C", 100, 30, 0, 0, layer=0, position_in_layer=2),
        }
        layout.edges = []

        positions = layout.calculate_positions(
            start_x=50, start_y=50,
            horizontal_gap=30, vertical_gap=20
        )

        # All same X (same layer)
        assert positions["a"]["x"] == 50
        assert positions["b"]["x"] == 50
        assert positions["c"]["x"] == 50

        # Y increases with vertical gap
        assert positions["a"]["y"] == 50
        assert positions["b"]["y"] == 50 + 40 + 20  # prev_y + height_a + gap = 110
        assert positions["c"]["y"] == 110 + 50 + 20  # prev_y + height_b + gap = 180

    def test_calculate_positions_returns_all_nodes(self):
        """All nodes should be in the result."""
        layout = SugiyamaLayout()
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0, layer=0, position_in_layer=0),
            "b": Node("b", "B", 100, 40, 0, 0, layer=1, position_in_layer=0),
        }
        layout.edges = [Edge("a", "b")]

        positions = layout.calculate_positions()

        assert "a" in positions
        assert "b" in positions
        assert set(positions["a"].keys()) == {"guid", "x", "y"}


class TestFullPipeline:
    """Test complete Sugiyama layout pipeline."""

    def test_full_pipeline_spiral_staircase_pattern(self):
        """Test layout of a typical GH pattern: sliders → math → geometry."""
        # Simulated components: 3 sliders → 2 math ops → 1 geometry
        components = [
            {"guid": "s1", "name": "Number Slider", "position": {"x": 500, "y": 100}, "size": {"width": 150, "height": 20}},
            {"guid": "s2", "name": "Number Slider", "position": {"x": 480, "y": 300}, "size": {"width": 150, "height": 20}},
            {"guid": "s3", "name": "Number Slider", "position": {"x": 520, "y": 200}, "size": {"width": 150, "height": 20}},
            {"guid": "m1", "name": "Division", "position": {"x": 100, "y": 150}, "size": {"width": 80, "height": 40}},
            {"guid": "m2", "name": "Multiplication", "position": {"x": 200, "y": 250}, "size": {"width": 80, "height": 40}},
            {"guid": "g1", "name": "Arc", "position": {"x": 800, "y": 180}, "size": {"width": 100, "height": 60}},
        ]

        # Wiring: s1→m1, s2→m1, s3→m2, m1→g1, m2→g1
        connections = {
            "s1": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "m1"}]}]},
            "s2": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "m1"}]}]},
            "s3": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "m2"}]}]},
            "m1": {"inputs": [{"sources": [{"sourceComponentGuid": "s1"}, {"sourceComponentGuid": "s2"}]}],
                   "outputs": [{"recipients": [{"recipientComponentGuid": "g1"}]}]},
            "m2": {"inputs": [{"sources": [{"sourceComponentGuid": "s3"}]}],
                   "outputs": [{"recipients": [{"recipientComponentGuid": "g1"}]}]},
            "g1": {"inputs": [{"sources": [{"sourceComponentGuid": "m1"}, {"sourceComponentGuid": "m2"}]}],
                   "outputs": []},
        }

        layout = SugiyamaLayout()
        layout.build_graph(components, connections)
        num_layers = layout.assign_layers()
        layout.minimize_crossings()
        positions = layout.calculate_positions(start_x=50, start_y=50)

        # Should have 3 layers: sliders(0) → math(1) → geometry(2)
        assert num_layers == 3
        assert layout.nodes["s1"].layer == 0
        assert layout.nodes["s2"].layer == 0
        assert layout.nodes["s3"].layer == 0
        assert layout.nodes["m1"].layer == 1
        assert layout.nodes["m2"].layer == 1
        assert layout.nodes["g1"].layer == 2

        # All positions should be calculated
        assert len(positions) == 6

        # X should increase: sliders < math < geometry
        assert positions["s1"]["x"] < positions["m1"]["x"] < positions["g1"]["x"]

        # Sliders should be stacked vertically
        slider_ys = [positions["s1"]["y"], positions["s2"]["y"], positions["s3"]["y"]]
        assert len(set(slider_ys)) == 3  # All different Y values


class TestCoffmanGrahamLayering:
    """Test Coffman-Graham layering with width constraints."""

    def test_coffman_graham_respects_max_width(self):
        """Layer width should not exceed max_width."""
        layout = SugiyamaLayout()
        # 6 nodes, all sources (no edges) - should spread across layers
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0),
            "b": Node("b", "B", 100, 40, 0, 50),
            "c": Node("c", "C", 100, 40, 0, 100),
            "d": Node("d", "D", 100, 40, 0, 150),
            "e": Node("e", "E", 100, 40, 0, 200),
            "f": Node("f", "F", 100, 40, 0, 250),
        }
        layout.edges = []
        layout._adjacency = {k: [] for k in layout.nodes}
        layout._reverse_adjacency = {k: [] for k in layout.nodes}

        num_layers = layout.assign_layers_coffman_graham(max_width=2)

        # 6 nodes with max_width=2 should need 3 layers
        assert num_layers == 3
        # Count nodes per layer
        layer_counts = {}
        for node in layout.nodes.values():
            layer_counts[node.layer] = layer_counts.get(node.layer, 0) + 1
        # No layer should have more than 2 nodes
        assert all(count <= 2 for count in layer_counts.values())

    def test_coffman_graham_respects_dependencies(self):
        """Predecessors must be in earlier layers."""
        layout = SugiyamaLayout()
        # Chain: a -> b -> c
        layout.nodes = {
            "a": Node("a", "A", 100, 40, 0, 0),
            "b": Node("b", "B", 100, 40, 0, 50),
            "c": Node("c", "C", 100, 40, 0, 100),
        }
        layout.edges = [Edge("a", "b"), Edge("b", "c")]
        layout._adjacency = {"a": ["b"], "b": ["c"], "c": []}
        layout._reverse_adjacency = {"a": [], "b": ["a"], "c": ["b"]}

        layout.assign_layers_coffman_graham(max_width=5)

        # Dependencies must be respected: a < b < c
        assert layout.nodes["a"].layer < layout.nodes["b"].layer
        assert layout.nodes["b"].layer < layout.nodes["c"].layer

    def test_coffman_graham_spreads_fan_out(self):
        """Fan-out should spread across layers, not stack."""
        layout = SugiyamaLayout()
        # src -> a, b, c, d (fan-out of 4)
        layout.nodes = {
            "src": Node("src", "Src", 100, 40, 0, 0),
            "a": Node("a", "A", 100, 40, 0, 50),
            "b": Node("b", "B", 100, 40, 0, 100),
            "c": Node("c", "C", 100, 40, 0, 150),
            "d": Node("d", "D", 100, 40, 0, 200),
        }
        layout.edges = [Edge("src", "a"), Edge("src", "b"), Edge("src", "c"), Edge("src", "d")]
        layout._adjacency = {"src": ["a", "b", "c", "d"], "a": [], "b": [], "c": [], "d": []}
        layout._reverse_adjacency = {"src": [], "a": ["src"], "b": ["src"], "c": ["src"], "d": ["src"]}

        num_layers = layout.assign_layers_coffman_graham(max_width=2)

        # src in layer 0, then a,b,c,d spread across layers 1+ (max 2 per layer)
        assert layout.nodes["src"].layer == 0
        # With max_width=2, need at least 2 layers for 4 downstream nodes
        assert num_layers >= 3  # layer 0 (src) + at least 2 more for a,b,c,d