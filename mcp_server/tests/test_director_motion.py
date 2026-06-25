from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_motion as dm


@pytest.mark.parametrize("name", sorted(dm.EASING_NAMES))
def test_easing_pins_endpoints(name):
    assert dm.apply_easing(name, 0.0) == pytest.approx(0.0)
    assert dm.apply_easing(name, 1.0) == pytest.approx(1.0)


def test_easing_linear_is_identity():
    assert dm.apply_easing("linear", 0.25) == pytest.approx(0.25)


def test_easing_in_starts_slow():
    # ease_in is below the linear line in the first half
    assert dm.apply_easing("ease_in", 0.5) < 0.5


def test_easing_out_starts_fast():
    assert dm.apply_easing("ease_out", 0.5) > 0.5


def test_easing_in_out_is_symmetric_about_midpoint():
    assert dm.apply_easing("ease_in_out", 0.5) == pytest.approx(0.5)
    assert dm.apply_easing("ease_in_out", 0.25) == pytest.approx(
        1.0 - dm.apply_easing("ease_in_out", 0.75)
    )


def _kf(t, **kw):
    kf = {"t": t}
    kf.update(kw)
    return kf


def test_single_translate_keyframe_pins_endpoints_and_holds_shape():
    # one keyframe at t=1 moving +10 in X; frame 1 = identity, frame N = full delta
    frames = dm.compile_object_track(
        [_kf(1.0, translate=[10, 0, 0])],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    assert len(frames) == 3
    assert frames[0] == dm.IDENTITY_4X4              # frame 1 is source identity
    assert frames[1][0][3] == pytest.approx(5.0)     # linear midpoint
    assert frames[2][0][3] == pytest.approx(10.0)    # final, translation in column 3
    # nested 4x4 shape
    assert len(frames[2]) == 4 and all(len(row) == 4 for row in frames[2])


def test_hold_after_last_keyframe():
    # last keyframe at t=0.5; frames after hold the delta
    frames = dm.compile_object_track(
        [_kf(0.5, translate=[8, 0, 0])],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    assert frames[1][0][3] == pytest.approx(8.0)   # t=0.5
    assert frames[2][0][3] == pytest.approx(8.0)   # t=1.0 holds


def test_scale_about_object_center_keeps_center_fixed():
    # scale 2x about a fully non-zero object_center: the center maps to itself
    # in all three axes (guards every row of the pivot composition, not just x).
    center = [5, 3, 2]
    frames = dm.compile_object_track(
        [_kf(1.0, scale=2.0)],
        frame_count=2, source_center=center, default_easing="linear",
    )
    m = frames[1]
    # apply the 4x4 to the homogeneous center point (cx,cy,cz,1)
    for row in range(3):
        mapped = (m[row][0] * center[0] + m[row][1] * center[1]
                  + m[row][2] * center[2] + m[row][3])
        assert mapped == pytest.approx(center[row])
    # diagonal scale factor is 2 on every axis
    assert m[0][0] == pytest.approx(2.0)
    assert m[1][1] == pytest.approx(2.0)
    assert m[2][2] == pytest.approx(2.0)


def test_rotation_slerp_halfway_is_half_angle():
    # rotate 90deg about Z at t=1; frame at t=0.5 ~ 45deg
    frames = dm.compile_object_track(
        [_kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 90})],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    half = frames[1]
    c = math.cos(math.radians(45))
    assert half[0][0] == pytest.approx(c, abs=1e-6)
    assert half[1][1] == pytest.approx(c, abs=1e-6)


def test_reject_scale_zero():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.0, scale=0.0)], frame_count=2,
                                source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_angle_over_180():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 270})],
            frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_non_identity_t0():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(0.0, translate=[1, 0, 0]), _kf(1.0, translate=[5, 0, 0])],
            frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_duplicate_t():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(0.5, translate=[1, 0, 0]), _kf(0.5, translate=[2, 0, 0])],
            frame_count=3, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_out_of_range_t():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.5, translate=[1, 0, 0])], frame_count=2,
                                source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_inconsistent_pivot():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [
                _kf(0.5, rotate={"axis": [0, 0, 1], "angle_degrees": 30, "pivot": "object_center"}),
                _kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 60, "pivot": [9, 9, 9]}),
            ],
            frame_count=3, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "inconsistent_pivot"


def test_reject_unknown_easing():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.0, translate=[1, 0, 0], ease_from_previous="boing")],
                                frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_single_frame_count_returns_identity():
    frames = dm.compile_object_track(
        [_kf(1.0, translate=[5, 0, 0])],
        frame_count=1, source_center=[0, 0, 0], default_easing="linear",
    )
    assert frames == [dm.IDENTITY_4X4]


# --- P1: malformed numeric fields must raise MotionError, not raw ValueError/IndexError ---

@pytest.mark.parametrize("bad_kf", [
    {"t": "abc", "translate": [1, 0, 0]},                                  # non-numeric t
    {"t": True, "translate": [1, 0, 0]},                                   # bool t (was silently 1.0)
    {"t": None, "translate": [1, 0, 0]},                                   # None t
    {"t": 1.0, "translate": ["x", 0, 0]},                                  # non-numeric translate
    {"t": 1.0, "translate": [True, 0, 0]},                                 # bool translate component
    {"t": 1.0, "scale": "big"},                                            # non-numeric scalar scale
    {"t": 1.0, "scale": [True, 1, 1]},                                     # bool scale component
    {"t": 1.0, "scale": ["a", 1, 1]},                                      # non-numeric scale component
    {"t": 1.0, "rotate": {"axis": [0, 0, 1], "angle_degrees": "ninety"}},  # non-numeric angle
    {"t": 1.0, "rotate": {"axis": [0, 0, 1], "angle_degrees": True}},      # bool angle
    {"t": 1.0, "rotate": {"axis": ["x", 0, 1], "angle_degrees": 90}},      # non-numeric axis component
    {"t": 1.0, "rotate": {"axis": [0, 1], "angle_degrees": 90}},           # axis len 2 (was IndexError)
    {"t": 1.0, "rotate": {"axis": [0, 0, 1, 0], "angle_degrees": 90}},     # axis len 4 (was silently OK)
    {"t": 1.0, "rotate": {"axis": [0, 0, 1], "angle_degrees": 90,
                          "pivot": ["x", 0, 0]}},                          # non-numeric pivot component
])
def test_malformed_numeric_fields_raise_motionerror(bad_kf):
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([bad_kf], frame_count=2,
                                source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_valid_int_fields_still_accepted():
    # ints (not bools) remain valid for t/translate/scale/angle/axis
    frames = dm.compile_object_track(
        [{"t": 1, "translate": [4, 0, 0], "scale": 2,
          "rotate": {"axis": [0, 0, 1], "angle_degrees": 90}}],
        frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert len(frames) == 2
    assert frames[0] == dm.IDENTITY_4X4
