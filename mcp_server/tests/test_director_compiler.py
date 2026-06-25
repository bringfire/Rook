# mcp_server/tests/test_director_compiler.py
from __future__ import annotations

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
