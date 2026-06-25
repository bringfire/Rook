# mcp_server/tests/test_director_compiler.py
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_compiler as dc

U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"


def test_timeline_duration_shape():
    out = dc.resolve_compiler_timeline({"timeline": {"fps": 24, "duration_seconds": 5}})
    assert out == {"fps": 24, "frame_count": 120, "duration_seconds": 5.0}


def test_timeline_frame_count_shape():
    out = dc.resolve_compiler_timeline({"timeline": {"fps": 30, "frame_count": 90}})
    assert out["fps"] == 30 and out["frame_count"] == 90
    assert out["duration_seconds"] == pytest.approx(3.0)


def test_timeline_rejects_fps_none_path():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.resolve_compiler_timeline({"frame_count": 100})  # no timeline block
    assert ei.value.code == "invalid_timeline"


def test_timeline_rejects_fractional_fps():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.resolve_compiler_timeline({"timeline": {"fps": 23.976, "frame_count": 90}})
    assert ei.value.code == "invalid_timeline"


def test_expand_explicit_id():
    spec = {"motion": [{"target": U1, "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}]}
    expanded = dc.expand_targets(spec)
    assert set(expanded) == {U1}


def test_expand_group_and_mixed():
    spec = {
        "groups": {"towers": [U1, U2]},
        "motion": [{"target": "towers", "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}],
    }
    expanded = dc.expand_targets(spec)
    assert set(expanded) == {U1, U2}


def test_reject_uuid_shaped_group_name():
    spec = {"groups": {U1: [U2]}, "motion": [{"target": U1, "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "invalid_input"


def test_reject_unknown_group():
    spec = {"motion": [{"target": "ghosts", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "unknown_group"


def test_reject_empty_group():
    spec = {"groups": {"empty": []}, "motion": [{"target": "empty", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "empty_group"


def test_reject_bad_group_member():
    spec = {"groups": {"g": ["not-a-uuid"]}, "motion": [{"target": "g", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "invalid_input"


def test_reject_duplicate_object_target_across_motion():
    spec = {
        "groups": {"a": [U1]},
        "motion": [
            {"target": "a", "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]},
            {"target": U1, "keyframes": [{"t": 1.0, "translate": [0, 1, 0]}]},
        ],
    }
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "duplicate_object_target"


def test_caps_objects():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=257, frame_count=10, fps=24)
    assert ei.value.code == "object_count_exceeds_cap"


def test_caps_frames():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=3001, fps=24)
    assert ei.value.code == "frame_count_exceeds_cap"


def test_caps_dwell():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=10, fps=3)  # 1000/3 > 250
    assert ei.value.code == "frame_dwell_exceeds_cap"


def test_caps_duration():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=2000, fps=24)  # 2000*41.6ms > 60000
    assert ei.value.code == "replay_duration_exceeds_cap"


def _objstate(oid, bbox_min, bbox_max):
    return {"object_id": oid, "bbox_min": bbox_min, "bbox_max": bbox_max,
            "validation_strength": "bbox_only", "state_hash": None}


class FakeNative:
    def __init__(self, objects, *, object_states_ok=True):
        self.objects = objects
        self.object_states_ok = object_states_ok
        self.calls = []

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, data))
        if endpoint == "/director/object-states":
            if not self.object_states_ok:
                return {"success": False, "data": {"code": "x", "message": "boom"}}
            return {"success": True, "data": {"objects": self.objects, "units": "Inches"}}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def test_resolve_source_states_indexes_by_id():
    fake = FakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    states = asyncio.run(dc.resolve_source_states(fake, [U1], None))
    assert states[U1]["bbox_min"] == [0, 0, 0]


def test_resolve_source_states_missing_object_fails():
    fake = FakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.resolve_source_states(fake, [U1, U2], None))
    assert ei.value.code == "source_resolution_failed"
    assert ei.value.extra.get("object_id") == U2


def test_resolve_source_states_native_failure():
    fake = FakeNative([], object_states_ok=False)
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.resolve_source_states(fake, [U1], None))
    assert ei.value.code == "source_resolution_failed"


def test_build_object_frames_every_object_every_frame():
    expanded = {U1: [{"t": 1.0, "translate": [4, 0, 0]}], U2: [{"t": 1.0, "translate": [0, 4, 0]}]}
    states = {U1: _objstate(U1, [0, 0, 0], [2, 2, 2]), U2: _objstate(U2, [0, 0, 0], [2, 2, 2])}
    frames = dc.build_object_frames(expanded, states, frame_count=3, default_easing="linear")
    assert len(frames) == 3
    for f in frames:
        ids = {ot["object_id"] for ot in f["object_transforms"]}
        assert ids == {U1, U2}
        for ot in f["object_transforms"]:
            assert ot["source_state"]["validation_strength"] == "bbox_only"
            assert ot["source_state"]["bbox_min"] == [0, 0, 0]
    # frame 1 is identity for both
    assert frames[0]["object_transforms"][0]["transform"][0][3] == pytest.approx(0.0)
    assert [f["frame_index"] for f in frames] == [1, 2, 3]


def test_build_object_frames_propagates_motion_error_code():
    expanded = {U1: [{"t": 1.0, "scale": 0.0}]}
    states = {U1: _objstate(U1, [0, 0, 0], [2, 2, 2])}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.build_object_frames(expanded, states, frame_count=2, default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


class FullFakeNative(FakeNative):
    def __init__(self, objects, *, view_ok=True, **kw):
        super().__init__(objects, **kw)
        self.view_ok = view_ok

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, data))
        if endpoint == "/director/object-states":
            if not self.object_states_ok:
                return {"success": False, "data": {"code": "x", "message": "boom"}}
            return {"success": True, "data": {"objects": self.objects, "units": "Inches"}}
        if endpoint == "/director/view-state":
            if not self.view_ok:
                return {"success": False, "data": {"code": "x", "message": "no view"}}
            return {"success": True, "data": {"camera": {
                "projection": "perspective", "location": [4, -4, 3], "target": [0, 0, 0],
                "up": [0, 0, 1], "lens_length": 35.0, "fov_degrees": None,
                "parallel_scale": None, "near_clip": None, "far_clip": None, "aspect": 1.7778},
                "provenance": {"source": "active_view"}}}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _spec(**over):
    spec = {
        "timeline": {"fps": 24, "frame_count": 3},
        "resolution": {"width": 1920, "height": 1080},
        "motion": [{"target": U1, "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}],
    }
    spec.update(over)
    return spec


def test_compile_motion_default_camera_hold_produces_valid_track():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    out = asyncio.run(dc.compile_motion(_spec(), call_native=fake, port=None))
    track = out["track"]
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["fps"] == 24
    assert track["frame_count"] == 3
    assert track["animated_object_ids"] == [U1]
    assert len(track["camera_frames"]) == 3
    assert len(track["object_frames"]) == 3
    assert track["camera_frames"][0]["frame_index"] == 1
    # provenance
    assert out["provenance"]["frame_count"] == 3
    assert out["provenance"]["group_expansion"] == {}


def test_compile_motion_track_passes_structural_native_rules():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2]),
                           _objstate(U2, [0, 0, 0], [2, 2, 2])])
    spec = _spec(groups={"g": [U1, U2]},
                 motion=[{"target": "g", "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}])
    track = asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))["track"]
    fc = track["frame_count"]
    assert len(track["camera_frames"]) == fc and len(track["object_frames"]) == fc
    aset = set(track["animated_object_ids"])
    assert len(aset) == len(track["animated_object_ids"]) <= 256
    for i, of in enumerate(track["object_frames"]):
        assert of["frame_index"] == i + 1
        ids = [ot["object_id"] for ot in of["object_transforms"]]
        assert set(ids) == aset and len(ids) == len(aset)
        for ot in of["object_transforms"]:
            m = ot["transform"]
            assert len(m) == 4 and all(len(r) == 4 for r in m)
    for i, cf in enumerate(track["camera_frames"]):
        assert cf["frame_index"] == i + 1


def test_compile_motion_camera_resolution_failure():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])], view_ok=False)
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(_spec(), call_native=fake, port=None))
    assert ei.value.code == "camera_resolution_failed"


def test_compile_motion_invalid_camera_spec():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    # a keyframes camera with an unsupported source kind -> invalid_camera
    bad = _spec(camera={"strategy": "keyframes",
                        "keyframes": [{"frame_index": 1, "source": {"kind": "bogus"}}]})
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(bad, call_native=fake, port=None))
    assert ei.value.code == "invalid_camera"


def test_compile_motion_source_failure_distinct_from_camera():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    spec = _spec(motion=[{"target": U2, "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}])
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))
    assert ei.value.code == "source_resolution_failed"


def test_compile_motion_rejects_bogus_default_easing():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    spec = _spec(default_easing="boing",
                 motion=[{"target": U1, "keyframes": [
                     {"t": 1.0, "translate": [4, 0, 0], "ease_from_previous": "linear"}]}])
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))
    assert ei.value.code == "invalid_keyframe"


def test_compile_motion_provenance_segment_mapping_shape():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    spec = _spec(motion=[{"target": U1, "keyframes": [
        {"t": 1.0, "translate": [4, 0, 0], "ease_from_previous": "ease_in_out"}]}])
    prov = asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))["provenance"]
    assert U1 in prov["segment_mapping"]
    seg = prov["segment_mapping"][U1]
    assert seg == [{"t": 1.0, "ease_from_previous": "ease_in_out"}]
