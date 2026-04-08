"""Tests for canvas alignment utilities."""

import pytest
from rook.learning.canvas_align import align_positions, distribute_positions, straighten_wire_positions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comps(positions: list[tuple[float, float]], size=(100, 40)):
    """Create component dicts from (x, y) tuples."""
    return [
        {
            "guid": f"c{i}",
            "name": f"Comp{i}",
            "position": {"x": x, "y": y},
            "size": {"width": size[0], "height": size[1]},
        }
        for i, (x, y) in enumerate(positions)
    ]


# ---------------------------------------------------------------------------
# align_positions
# ---------------------------------------------------------------------------

class TestAlignPositions:
    """Tests for align_positions()."""

    def test_align_left(self):
        comps = _make_comps([(10, 0), (50, 50), (30, 100)])
        result = align_positions(comps, "left", "first")
        # All should align to first component's x = 10
        for r in result:
            assert r["x"] == 10

    def test_align_right(self):
        comps = _make_comps([(10, 0), (50, 50), (30, 100)])
        result = align_positions(comps, "right", "max")
        # Max right edge is 50 + 100 = 150
        for r in result:
            assert r["x"] + 100 == 150  # x + width = 150

    def test_align_top(self):
        comps = _make_comps([(0, 20), (100, 80), (200, 50)])
        result = align_positions(comps, "top", "min")
        for r in result:
            assert r["y"] == 20

    def test_align_bottom(self):
        comps = _make_comps([(0, 20), (100, 80), (200, 50)])
        result = align_positions(comps, "bottom", "max")
        # Max bottom = 80 + 40 = 120
        for r in result:
            assert r["y"] + 40 == 120

    def test_align_center_h(self):
        comps = _make_comps([(0, 0), (100, 0), (200, 0)])
        result = align_positions(comps, "center_h", "median")
        # Median center_h = sorted centers: 50, 150, 250 → median is 150
        for r in result:
            assert r["x"] + 50 == 150  # x + width/2 = 150

    def test_align_center_v(self):
        comps = _make_comps([(0, 0), (0, 100), (0, 200)])
        result = align_positions(comps, "center_v", "median")
        # Median center_v = sorted centers: 20, 120, 220 → median is 120
        for r in result:
            assert r["y"] + 20 == 120

    def test_too_few_components(self):
        comps = _make_comps([(0, 0)])
        result = align_positions(comps, "left")
        assert result == []

    def test_preserves_other_axis(self):
        """Aligning left should not change Y positions."""
        comps = _make_comps([(10, 30), (50, 70), (30, 110)])
        result = align_positions(comps, "left", "first")
        ys = [r["y"] for r in result]
        assert ys == [30, 70, 110]


# ---------------------------------------------------------------------------
# distribute_positions
# ---------------------------------------------------------------------------

class TestDistributePositions:
    """Tests for distribute_positions()."""

    def test_equal_horizontal_distribution(self):
        comps = _make_comps([(0, 0), (300, 0), (100, 0)])
        result = distribute_positions(comps, "horizontal")
        # Sorted by x: c0(0), c2(100), c1(300)
        # Equal distribution: 0, 150, 300
        xs = sorted([r["x"] for r in result])
        assert xs == pytest.approx([0, 150, 300])

    def test_equal_vertical_distribution(self):
        comps = _make_comps([(0, 0), (0, 200), (0, 100)])
        result = distribute_positions(comps, "vertical")
        ys = sorted([r["y"] for r in result])
        assert ys == pytest.approx([0, 100, 200])

    def test_fixed_spacing_horizontal(self):
        comps = _make_comps([(0, 0), (50, 0), (100, 0)])
        result = distribute_positions(comps, "horizontal", spacing=20)
        # Sorted by x, each placed after previous: x=0, x=120, x=240
        xs = sorted([r["x"] for r in result])
        assert xs[0] == 0
        assert xs[1] == 120  # 0 + 100 + 20
        assert xs[2] == 240  # 120 + 100 + 20

    def test_fixed_spacing_vertical(self):
        comps = _make_comps([(0, 0), (0, 50), (0, 100)])
        result = distribute_positions(comps, "vertical", spacing=10)
        ys = sorted([r["y"] for r in result])
        assert ys[0] == 0
        assert ys[1] == 50   # 0 + 40 + 10
        assert ys[2] == 100  # 50 + 40 + 10

    def test_too_few_components(self):
        comps = _make_comps([(0, 0)])
        assert distribute_positions(comps, "horizontal") == []

    def test_preserves_other_axis(self):
        """Horizontal distribution should not change Y positions."""
        comps = _make_comps([(0, 10), (200, 20), (100, 30)])
        result = distribute_positions(comps, "horizontal")
        # After sorting by x: c0(y=10), c2(y=30), c1(y=20)
        result_by_guid = {r["guid"]: r for r in result}
        assert result_by_guid["c0"]["y"] == 10
        assert result_by_guid["c1"]["y"] == 20
        assert result_by_guid["c2"]["y"] == 30


# ---------------------------------------------------------------------------
# straighten_wire_positions
# ---------------------------------------------------------------------------

class TestStraightenWires:
    """Tests for straighten_wire_positions()."""

    def test_simple_straighten(self):
        comps = [
            {"guid": "src", "name": "Source",
             "position": {"x": 0, "y": 50},
             "size": {"width": 100, "height": 40}},
            {"guid": "dst", "name": "Dest",
             "position": {"x": 200, "y": 200},
             "size": {"width": 80, "height": 40}},
        ]
        conns = {
            "src": {"inputs": [], "outputs": [{"recipients": [{"sourceComponentGuid": "dst"}]}]},
            "dst": {"inputs": [{"sources": [{"sourceComponentGuid": "src"}]}], "outputs": []},
        }

        result = straighten_wire_positions(comps, conns)
        assert len(result) > 0, "Should produce at least one adjustment"
        result_by_guid = {r["guid"]: r for r in result}
        assert "dst" in result_by_guid, "dst should be adjusted"
        # dst Y should be closer to src center (50 + 20 = 70)
        src_center = 50 + 20
        new_dst_center = result_by_guid["dst"]["y"] + 20
        assert abs(new_dst_center - src_center) < abs(200 + 20 - src_center)

    def test_empty_connections(self):
        comps = _make_comps([(0, 0), (100, 100)])
        conns = {
            "c0": {"inputs": [], "outputs": []},
            "c1": {"inputs": [], "outputs": []},
        }
        result = straighten_wire_positions(comps, conns)
        assert result == []

    def test_target_guids_filter(self):
        comps = [
            {"guid": "a", "name": "A",
             "position": {"x": 0, "y": 0},
             "size": {"width": 100, "height": 40}},
            {"guid": "b", "name": "B",
             "position": {"x": 200, "y": 100},
             "size": {"width": 80, "height": 40}},
            {"guid": "c", "name": "C",
             "position": {"x": 200, "y": 200},
             "size": {"width": 80, "height": 40}},
        ]
        conns = {
            "a": {"inputs": [], "outputs": [{"recipients": [
                {"recipientComponentGuid": "b"},
                {"recipientComponentGuid": "c"},
            ]}]},
            "b": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}]}], "outputs": []},
            "c": {"inputs": [{"sources": [{"sourceComponentGuid": "a"}]}], "outputs": []},
        }

        # Only straighten "b", not "c"
        result = straighten_wire_positions(comps, conns, target_guids=["b"])
        result_guids = {r["guid"] for r in result}
        assert "c" not in result_guids
