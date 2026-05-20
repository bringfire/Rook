from __future__ import annotations

import pytest

from rook import timeline


def test_legacy_frame_count_gets_timeline_manifest():
    normalized, manifest = timeline.normalize_director_request(
        {
            "frame_count": 3,
            "camera_keyframes": [
                {"frame_index": 1, "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["frame_count"] == 3
    assert normalized["camera_keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}}
    ]
    assert manifest == {
        "source": "frame_count",
        "fps": None,
        "duration_seconds": None,
        "frame_count": 3,
    }


def test_timeline_derives_frame_count_and_maps_endpoints():
    normalized, manifest = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 5.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}},
                    {"time": 5.0, "source": {"kind": "named_view", "name": "End"}},
                ],
            },
        }
    )

    assert normalized["frame_count"] == 120
    assert normalized["camera"]["keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}},
        {"frame_index": 120, "source": {"kind": "named_view", "name": "End"}},
    ]
    assert manifest == {
        "source": "timeline",
        "fps": 24,
        "duration_seconds": 5.0,
        "frame_count": 120,
    }


def test_timeline_maps_normalized_at_values():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 10, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"at": 0.0, "source": {"kind": "active_view"}},
                    {"at": 0.5, "source": {"kind": "named_view", "name": "Middle"}},
                    {"at": 1.0, "source": {"kind": "named_view", "name": "End"}},
                ],
            },
        }
    )

    assert [k["frame_index"] for k in normalized["camera"]["keyframes"]] == [1, 6, 10]


def test_timeline_normalizes_integral_fps_and_frame_indexes():
    normalized, manifest = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24.0, "duration_seconds": 0.125},
            "camera_keyframes": [
                {"frame_index": "3", "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["frame_count"] == 3
    assert normalized["camera_keyframes"][0]["frame_index"] == 3
    assert manifest["fps"] == 24


def test_timeline_rejects_inconsistent_top_level_frame_count():
    with pytest.raises(timeline.TimelineError, match="frame_count must equal"):
        timeline.normalize_director_request(
            {
                "frame_count": 119,
                "timeline": {"fps": 24, "duration_seconds": 5.0},
                "camera_keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            }
        )


@pytest.mark.parametrize(
    ("timeline_payload", "message"),
    [
        ({"fps": 0, "duration_seconds": 5.0}, "fps"),
        ({"fps": 24.5, "duration_seconds": 5.0}, "fps"),
        ({"fps": float("inf"), "duration_seconds": 5.0}, "fps"),
        ({"fps": 24, "duration_seconds": 0}, "duration_seconds"),
        ({"fps": 24, "duration_seconds": float("inf")}, "duration_seconds"),
    ],
)
def test_timeline_rejects_invalid_values(timeline_payload, message):
    with pytest.raises(timeline.TimelineError, match=message):
        timeline.normalize_director_request(
            {
                "timeline": timeline_payload,
                "camera_keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            }
        )


@pytest.mark.parametrize(
    ("keyframe", "message"),
    [
        ({"source": {"kind": "active_view"}}, "exactly one"),
        (
            {"frame_index": 1, "time": 0.0, "source": {"kind": "active_view"}},
            "exactly one",
        ),
        ({"frame_index": 0, "source": {"kind": "active_view"}}, "frame_index"),
        ({"frame_index": 1.5, "source": {"kind": "active_view"}}, "frame_index"),
        ({"frame_index": "3.5", "source": {"kind": "active_view"}}, "frame_index"),
        ({"time": -0.1, "source": {"kind": "active_view"}}, "time"),
        ({"time": 5.1, "source": {"kind": "active_view"}}, "time"),
        ({"at": -0.1, "source": {"kind": "active_view"}}, "at"),
        ({"at": 1.1, "source": {"kind": "active_view"}}, "at"),
    ],
)
def test_timeline_rejects_invalid_keyframe_timing(keyframe, message):
    with pytest.raises(timeline.TimelineError, match=message):
        timeline.normalize_director_request(
            {
                "timeline": {"fps": 24, "duration_seconds": 5.0},
                "camera": {"strategy": "keyframes", "keyframes": [keyframe]},
            }
        )


def test_timeline_preserves_camera_precedence_over_legacy_keyframes():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}}
                ],
            },
            "camera_keyframes": [
                {"time": 2.0, "source": {"kind": "active_view"}}
            ],
        }
    )

    assert normalized["camera"]["keyframes"] == [
        {"frame_index": 1, "source": {"kind": "active_view"}}
    ]
    assert normalized["camera_keyframes"] == [
        {"time": 2.0, "source": {"kind": "active_view"}}
    ]


def test_timeline_removes_time_fields_before_camera_planner():
    normalized, _ = timeline.normalize_director_request(
        {
            "timeline": {"fps": 24, "duration_seconds": 1.0},
            "camera": {
                "strategy": "keyframes",
                "keyframes": [
                    {"time": 0.0, "source": {"kind": "active_view"}},
                    {"at": 1.0, "source": {"kind": "active_view"}},
                ],
            },
        }
    )

    for keyframe in normalized["camera"]["keyframes"]:
        assert set(keyframe).issuperset({"frame_index", "source"})
        assert "time" not in keyframe
        assert "at" not in keyframe
