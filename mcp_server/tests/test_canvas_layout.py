"""Tests for the CanvasLayout pipeline (adapted from Engram's graph formatter)."""

import pytest
from rook.learning.canvas_layout import CanvasLayout, LayoutSettings, GroupInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chain(n: int = 3):
    """Build a simple A -> B -> C chain of n components."""
    comps = [
        {"guid": f"n{i}", "name": f"Node{i}",
         "position": {"x": i * 200, "y": 0},
         "size": {"width": 100, "height": 40}}
        for i in range(n)
    ]
    conns = {}
    for i in range(n):
        guid = f"n{i}"
        inputs = []
        outputs = []
        if i > 0:
            inputs = [{"sources": [{"sourceComponentGuid": f"n{i - 1}"}]}]
        if i < n - 1:
            outputs = [{"recipients": [{"recipientComponentGuid": f"n{i + 1}"}]}]
        conns[guid] = {"inputs": inputs, "outputs": outputs}
    return comps, conns


def _fan_out(children: int = 4):
    """Build src -> {c0, c1, ..., cN} fan-out graph."""
    comps = [
        {"guid": "src", "name": "Source",
         "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
    ]
    conns = {
        "src": {
            "inputs": [],
            "outputs": [{"recipients": [
                {"recipientComponentGuid": f"c{i}"} for i in range(children)
            ]}],
        },
    }
    for i in range(children):
        comps.append({
            "guid": f"c{i}", "name": f"Child{i}",
            "position": {"x": 200, "y": i * 60},
            "size": {"width": 80, "height": 40},
        })
        conns[f"c{i}"] = {
            "inputs": [{"sources": [{"sourceComponentGuid": "src"}]}],
            "outputs": [],
        }
    return comps, conns


# ---------------------------------------------------------------------------
# Basic pipeline tests
# ---------------------------------------------------------------------------

class TestCanvasLayoutPipeline:
    """End-to-end tests for the 10-phase pipeline."""

    def test_empty_canvas(self):
        layout = CanvasLayout()
        result = layout.run([], {})
        assert result == {}

    def test_single_component(self):
        comps = [{"guid": "a", "name": "Slider",
                  "position": {"x": 50, "y": 50},
                  "size": {"width": 100, "height": 20}}]
        conns = {"a": {"inputs": [], "outputs": []}}
        layout = CanvasLayout()
        result = layout.run(comps, conns)
        assert "a" in result
        assert "x" in result["a"] and "y" in result["a"]

    def test_chain_produces_left_to_right(self):
        comps, conns = _chain(4)
        layout = CanvasLayout()
        result = layout.run(comps, conns, start_x=50, start_y=50)

        # Nodes should be ordered left-to-right
        xs = [result[f"n{i}"]["x"] for i in range(4)]
        for i in range(len(xs) - 1):
            assert xs[i] < xs[i + 1], f"n{i} ({xs[i]}) should be left of n{i+1} ({xs[i+1]})"

    def test_fan_out_layers(self):
        comps, conns = _fan_out(3)
        layout = CanvasLayout()
        result = layout.run(comps, conns)
        # Source should be in layer 0 (leftmost), children in layer 1
        assert result["src"]["x"] < result["c0"]["x"]
        assert result["src"]["x"] < result["c1"]["x"]
        assert result["src"]["x"] < result["c2"]["x"]

    def test_num_layers_property(self):
        comps, conns = _chain(5)
        layout = CanvasLayout()
        layout.run(comps, conns)
        assert layout.num_layers >= 5

    def test_bridge_connection_lists_do_not_crash_layout(self):
        """List-shaped bridge fields should be ignored or normalized safely."""
        comps = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
            {"guid": "b", "name": "B", "position": {"x": 200, "y": 0}, "size": {"width": 100, "height": 40}},
        ]
        conns = {
            "a": [
                {
                    "Outputs": [
                        {
                            "Recipients": [
                                {"ComponentGuid": "b"},
                            ],
                        },
                    ],
                }
            ],
            "b": {"Inputs": [{"Sources": [{"ComponentGuid": "a"}]}], "Outputs": []},
        }

        layout = CanvasLayout()
        result = layout.run(comps, conns)

        assert set(result) == {"a", "b"}
        assert result["a"]["x"] < result["b"]["x"]

    def test_non_dict_canvas_entries_are_skipped(self):
        """Malformed list entries from snapshots should not reach .get calls."""
        comps = [
            ["not", "a", "component"],
            {"guid": "a", "name": "A", "position": ["bad"], "size": ["bad"]},
        ]
        conns = {"a": {"outputs": [["not", "a", "connection"]]}}
        groups = [["not", "a", "group"], {"guid": "g1", "members": ["a"]}]

        layout = CanvasLayout()
        result = layout.run(comps, conns, groups=groups)

        assert set(result) == {"a"}
        assert "g1" in layout.groups


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

class TestCollisionDetection:
    """Tests for Phase 6 — iterative collision resolution."""

    def test_no_overlaps_after_layout(self):
        """All nodes should have non-overlapping bounding boxes."""
        comps, conns = _fan_out(5)
        layout = CanvasLayout(LayoutSettings(collision_detection=True))
        result = layout.run(comps, conns)

        # Check no pair of nodes in the same layer overlaps
        rects = []
        for guid, pos in result.items():
            node = layout.nodes.get(guid)
            if node:
                rects.append((pos["x"], pos["y"], node.width, node.height, guid))

        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                x1, y1, w1, h1, g1 = rects[i]
                x2, y2, w2, h2, g2 = rects[j]
                # Check horizontal overlap
                h_overlap = not (x1 + w1 <= x2 or x2 + w2 <= x1)
                # Check vertical overlap
                v_overlap = not (y1 + h1 <= y2 or y2 + h2 <= y1)
                assert not (h_overlap and v_overlap), \
                    f"Overlap between {g1} and {g2}: ({x1},{y1},{w1}x{h1}) vs ({x2},{y2},{w2}x{h2})"

    def test_collision_disabled(self):
        """With collision detection off, layout should still produce positions."""
        comps, conns = _fan_out(3)
        layout = CanvasLayout(LayoutSettings(collision_detection=False))
        result = layout.run(comps, conns)
        assert len(result) == 4  # src + 3 children

    def test_collision_with_large_components(self):
        """Components with large height should not overlap."""
        comps = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 200}},
            {"guid": "b", "name": "B", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 200}},
            {"guid": "c", "name": "C", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 200}},
        ]
        # All in same layer (no connections)
        conns = {g["guid"]: {"inputs": [], "outputs": []} for g in comps}

        layout = CanvasLayout(LayoutSettings(collision_detection=True))
        result = layout.run(comps, conns)

        ys = sorted([result[g]["y"] for g in ["a", "b", "c"]])
        # Each component is 200px tall — gaps should be at least 200 between starts
        for i in range(len(ys) - 1):
            assert ys[i + 1] - ys[i] >= 200, \
                f"Components at y={ys[i]} and y={ys[i+1]} overlap (height=200)"


# ---------------------------------------------------------------------------
# Branch centering
# ---------------------------------------------------------------------------

class TestBranchCentering:
    """Tests for Phase 7 — centering fan-out branches."""

    def test_branches_centered_on_parent(self):
        """When 3+ children fan out, they should be roughly centered on parent."""
        comps, conns = _fan_out(4)
        settings = LayoutSettings(
            center_branches=True,
            min_branches_for_centering=3,
            collision_detection=True,
        )
        layout = CanvasLayout(settings)
        result = layout.run(comps, conns)

        # Calculate center of children
        child_ys = [result[f"c{i}"]["y"] for i in range(4)]
        child_heights = [40] * 4  # All 40px tall
        child_centers = [y + h / 2 for y, h in zip(child_ys, child_heights)]
        avg_child_center = sum(child_centers) / len(child_centers)

        # Parent center
        parent_center = result["src"]["y"] + 20  # 40px / 2

        # Should be within reasonable tolerance (allow some collision-resolution shift)
        assert abs(avg_child_center - parent_center) < 100, \
            f"Child center ({avg_child_center}) too far from parent center ({parent_center})"

    def test_no_centering_with_2_children(self):
        """With only 2 children, centering should NOT activate (min_branches=3)."""
        comps, conns = _fan_out(2)
        settings = LayoutSettings(
            center_branches=True,
            min_branches_for_centering=3,
        )
        layout = CanvasLayout(settings)
        result = layout.run(comps, conns)
        # Just verify it runs without error
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Expand by height
# ---------------------------------------------------------------------------

class TestExpandByHeight:
    """Tests for Phase 8 — wire angle optimization."""

    def test_steep_wires_get_expanded_fan_out(self):
        """Fan-out with steep Y distance should expand children rightward.

        expand_by_height requires 2+ children to activate. We use tall
        components (height=200) so collision detection spreads them far
        enough that deltaY * 0.75 > deltaX triggers expansion.
        """
        # Source fans out to 3 tall children — collision detection will
        # spread them ~200px apart vertically, triggering expand_by_height.
        comps = [
            {"guid": "src", "name": "Source",
             "position": {"x": 0, "y": 0}, "size": {"width": 60, "height": 40}},
            {"guid": "c0", "name": "Child0",
             "position": {"x": 200, "y": 0}, "size": {"width": 60, "height": 200}},
            {"guid": "c1", "name": "Child1",
             "position": {"x": 200, "y": 200}, "size": {"width": 60, "height": 200}},
            {"guid": "c2", "name": "Child2",
             "position": {"x": 200, "y": 400}, "size": {"width": 60, "height": 200}},
        ]
        conns = {
            "src": {"inputs": [], "outputs": [{"recipients": [
                {"recipientComponentGuid": "c0"},
                {"recipientComponentGuid": "c1"},
                {"recipientComponentGuid": "c2"},
            ]}]},
            "c0": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
            "c1": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
            "c2": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
        }

        # Run with expand enabled
        layout_expand = CanvasLayout(LayoutSettings(expand_by_height=True))
        result_expand = layout_expand.run(comps, conns)

        # Run with expand disabled
        layout_no_expand = CanvasLayout(LayoutSettings(expand_by_height=False))
        result_no_expand = layout_no_expand.run(comps, conns)

        # With tall components spread vertically, expansion should push them further right
        avg_gap_expand = sum(
            result_expand[f"c{i}"]["x"] - result_expand["src"]["x"] for i in range(3)
        ) / 3
        avg_gap_no_expand = sum(
            result_no_expand[f"c{i}"]["x"] - result_no_expand["src"]["x"] for i in range(3)
        ) / 3
        assert avg_gap_expand > avg_gap_no_expand, \
            f"Expansion avg gap ({avg_gap_expand:.1f}) should be > no-expansion avg gap ({avg_gap_no_expand:.1f})"

    def test_no_double_shift_shared_descendants(self):
        """Shared downstream nodes should not be shifted multiple times.

        A -> C -> D
        B -> C -> D
        C and D should only be expanded once, not once per parent.
        """
        comps = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
            {"guid": "b", "name": "B", "position": {"x": 0, "y": 400}, "size": {"width": 100, "height": 40}},
            {"guid": "c", "name": "C", "position": {"x": 200, "y": 100}, "size": {"width": 80, "height": 40}},
            {"guid": "d", "name": "D", "position": {"x": 200, "y": 300}, "size": {"width": 80, "height": 40}},
            {"guid": "e", "name": "E", "position": {"x": 400, "y": 200}, "size": {"width": 80, "height": 40}},
        ]
        conns = {
            "a": {"inputs": [], "outputs": [{"recipients": [
                {"recipientComponentGuid": "c"}, {"recipientComponentGuid": "d"},
            ]}]},
            "b": {"inputs": [], "outputs": [{"recipients": [
                {"recipientComponentGuid": "c"}, {"recipientComponentGuid": "d"},
            ]}]},
            "c": {"inputs": [
                {"sources": [{"sourceComponentGuid": "a"}, {"sourceComponentGuid": "b"}]}
            ], "outputs": [{"recipients": [{"recipientComponentGuid": "e"}]}]},
            "d": {"inputs": [
                {"sources": [{"sourceComponentGuid": "a"}, {"sourceComponentGuid": "b"}]}
            ], "outputs": [{"recipients": [{"recipientComponentGuid": "e"}]}]},
            "e": {"inputs": [
                {"sources": [{"sourceComponentGuid": "c"}, {"sourceComponentGuid": "d"}]}
            ], "outputs": []},
        }

        layout = CanvasLayout(LayoutSettings(expand_by_height=True, expand_max_dist=200.0))
        result = layout.run(comps, conns)

        # E should not be pushed unreasonably far right (max 2x expansion from A+B)
        # With expand_max_dist=200, single expansion adds at most 200px
        e_gap = result["e"]["x"] - result["a"]["x"]
        # Should be within reasonable bounds (base gap + at most one expansion)
        assert e_gap < 1000, f"E gap ({e_gap:.0f}) seems too large — possible double-shift"


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    """Tests for Phase 3 — back-edge marking."""

    def test_simple_cycle_handled(self):
        """A -> B -> A cycle should not cause infinite loop."""
        comps = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
            {"guid": "b", "name": "B", "position": {"x": 200, "y": 0}, "size": {"width": 100, "height": 40}},
        ]
        conns = {
            "a": {
                "inputs": [{"sources": [{"sourceComponentGuid": "b"}]}],
                "outputs": [{"recipients": [{"recipientComponentGuid": "b"}]}],
            },
            "b": {
                "inputs": [{"sources": [{"sourceComponentGuid": "a"}]}],
                "outputs": [{"recipients": [{"recipientComponentGuid": "a"}]}],
            },
        }

        layout = CanvasLayout()
        result = layout.run(comps, conns)

        # Should produce valid positions without hanging
        assert len(result) == 2
        assert "a" in result and "b" in result

    def test_longer_cycle(self):
        """A -> B -> C -> A cycle should complete."""
        comps = [
            {"guid": "a", "name": "A", "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
            {"guid": "b", "name": "B", "position": {"x": 200, "y": 0}, "size": {"width": 100, "height": 40}},
            {"guid": "c", "name": "C", "position": {"x": 400, "y": 0}, "size": {"width": 100, "height": 40}},
        ]
        conns = {
            "a": {
                "inputs": [{"sources": [{"sourceComponentGuid": "c"}]}],
                "outputs": [{"recipients": [{"recipientComponentGuid": "b"}]}],
            },
            "b": {
                "inputs": [{"sources": [{"sourceComponentGuid": "a"}]}],
                "outputs": [{"recipients": [{"recipientComponentGuid": "c"}]}],
            },
            "c": {
                "inputs": [{"sources": [{"sourceComponentGuid": "b"}]}],
                "outputs": [{"recipients": [{"recipientComponentGuid": "a"}]}],
            },
        }

        layout = CanvasLayout()
        result = layout.run(comps, conns)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Grid snap & finalize
# ---------------------------------------------------------------------------

class TestFinalize:
    """Tests for Phase 10 — anchor and grid snap."""

    def test_grid_snap(self):
        """With snap_to_grid, all positions should be multiples of grid_size."""
        comps, conns = _chain(3)
        settings = LayoutSettings(snap_to_grid=True, grid_size=10.0)
        layout = CanvasLayout(settings)
        result = layout.run(comps, conns)

        for guid, pos in result.items():
            assert pos["x"] % 10 == 0, f"{guid} x={pos['x']} not snapped to grid 10"
            assert pos["y"] % 10 == 0, f"{guid} y={pos['y']} not snapped to grid 10"

    def test_anchor_guid(self):
        """The anchor component should stay at its original position."""
        comps = [
            {"guid": "anchor", "name": "Anchor",
             "position": {"x": 300, "y": 200}, "size": {"width": 100, "height": 40}},
            {"guid": "other", "name": "Other",
             "position": {"x": 0, "y": 0}, "size": {"width": 100, "height": 40}},
        ]
        conns = {
            "anchor": {"inputs": [], "outputs": [{"recipients": [{"recipientComponentGuid": "other"}]}]},
            "other": {"inputs": [{"sources": [{"sourceComponentGuid": "anchor"}]}], "outputs": []},
        }

        settings = LayoutSettings(anchor_guid="anchor")
        layout = CanvasLayout(settings)
        result = layout.run(comps, conns)

        # Anchor should be at its original position
        assert result["anchor"]["x"] == 300, f"Anchor x should be 300, got {result['anchor']['x']}"
        assert result["anchor"]["y"] == 200, f"Anchor y should be 200, got {result['anchor']['y']}"


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

class TestGroupAwareness:
    """Tests for Phases 2 & 9 — group containment and padding."""

    def test_groups_parsed_pascal_case(self):
        """PascalCase keys (direct C# before serialization)."""
        comps, conns = _chain(2)
        groups = [
            {"Guid": "g1", "NickName": "Input Group", "Members": ["n0"], "Bounds": None},
        ]
        layout = CanvasLayout()
        layout.run(comps, conns, groups=groups)
        assert "g1" in layout.groups
        assert layout.groups["g1"].member_guids == ["n0"]

    def test_groups_parsed_camel_case(self):
        """camelCase keys (from C# JsonNamingPolicy.CamelCase serialization)."""
        comps, conns = _chain(2)
        groups = [
            {"guid": "g1", "nickName": "Input Group", "members": ["n0"], "bounds": None},
        ]
        layout = CanvasLayout()
        layout.run(comps, conns, groups=groups)
        assert "g1" in layout.groups
        assert layout.groups["g1"].member_guids == ["n0"]
        assert layout.groups["g1"].nickname == "Input Group"

    def test_group_bounds_returned(self):
        comps, conns = _chain(2)
        groups = [
            {"guid": "g1", "nickName": "Group", "members": ["n0", "n1"], "bounds": None},
        ]
        settings = LayoutSettings(group_padding=20.0)
        layout = CanvasLayout(settings)
        layout.run(comps, conns, groups=groups)

        bounds = layout.get_group_bounds()
        assert "g1" in bounds
        assert bounds["g1"]["x"] <= layout.nodes["n0"].x
        assert bounds["g1"]["y"] <= layout.nodes["n0"].y


# ---------------------------------------------------------------------------
# LayoutSettings
# ---------------------------------------------------------------------------

class TestLayoutSettings:
    """Test LayoutSettings dataclass defaults."""

    def test_defaults(self):
        s = LayoutSettings()
        assert s.horizontal_gap == 30.0
        assert s.vertical_gap == 20.0
        assert s.style == "expanded"
        assert s.collision_detection is True
        assert s.center_branches is True
        assert s.expand_by_height is True
        assert s.snap_to_grid is False
        assert s.grid_size == 8.0

    def test_compact_style(self):
        s = LayoutSettings(style="compact")
        assert s.style == "compact"


# ---------------------------------------------------------------------------
# Backward compatibility with SugiyamaLayout
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """CanvasLayout should produce valid output for all inputs SugiyamaLayout handles."""

    def test_same_node_count(self):
        """CanvasLayout should layout the same number of nodes as input."""
        from rook.learning.sugiyama import SugiyamaLayout

        comps, conns = _chain(5)

        sugiyama = SugiyamaLayout()
        sugiyama.build_graph(comps, conns)
        sugiyama.assign_layers_coffman_graham(max_width=4)
        sugiyama.minimize_crossings()
        sug_positions = sugiyama.calculate_positions()

        canvas = CanvasLayout()
        can_positions = canvas.run(comps, conns)

        assert len(sug_positions) == len(can_positions)
