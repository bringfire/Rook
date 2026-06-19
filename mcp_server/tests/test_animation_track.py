from __future__ import annotations

import pytest

from rook import animation_track


def _identity():
    return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def _camera(location):
    return {
        "projection": "perspective",
        "location": location,
        "target": [0.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "lens_length": 35.0,
        "fov_degrees": None,
        "parallel_scale": None,
        "near_clip": None,
        "far_clip": None,
        "aspect": 1.7778,
    }


def _motion_frame(frame_index, object_id="a"):
    return {
        "frame_index": frame_index,
        "object_transforms": [
            {
                "object_id": object_id,
                "source_state": {
                    "bbox_min": [0, 0, 0],
                    "bbox_max": [1, 1, 1],
                    "validation_strength": "bbox_only",
                    "state_hash": None,
                },
                "transform": _identity(),
            }
        ],
    }


def test_build_animation_track_assembles_two_sections_and_metadata():
    track = animation_track.build_animation_track(
        frame_count=2,
        fps=24,
        resolution={"width": 320, "height": 180},
        camera_per_frame=[_camera([4, -4, 3]), _camera([6, -4, 3])],
        motion_frames=[_motion_frame(1), _motion_frame(2)],
        camera_provenance={"strategy": "keyframes"},
        object_provenance={"generator": "radial_bbox_center"},
    )

    assert track["schema_version"] == 1
    assert track["animation_version"] == "v1"
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["frame_count"] == 2
    assert track["fps"] == 24
    assert track["resolution"] == {"width": 320, "height": 180}
    assert track["animated_object_ids"] == ["a"]
    assert [f["frame_index"] for f in track["camera_frames"]] == [1, 2]
    assert track["camera_frames"][1]["camera"]["location"] == [6, -4, 3]
    assert [f["frame_index"] for f in track["object_frames"]] == [1, 2]
    assert track["object_frames"][0]["object_transforms"][0]["object_id"] == "a"
    assert track["camera_provenance"] == {"strategy": "keyframes"}
    assert track["object_provenance"] == {"generator": "radial_bbox_center"}


def test_build_rejects_empty_motion_frames():
    with pytest.raises(animation_track.AnimationTrackError, match="motion_frames"):
        animation_track.build_animation_track(
            frame_count=1,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_camera_motion_length_mismatch():
    with pytest.raises(animation_track.AnimationTrackError, match="frame_count"):
        animation_track.build_animation_track(
            frame_count=2,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[_motion_frame(1), _motion_frame(2)],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_bad_frame_count():
    with pytest.raises(animation_track.AnimationTrackError, match="frame_count"):
        animation_track.build_animation_track(
            frame_count=0,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[],
            motion_frames=[],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_first_frame_without_object_transforms():
    with pytest.raises(animation_track.AnimationTrackError, match="object_transforms"):
        animation_track.build_animation_track(
            frame_count=1,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[{"frame_index": 1}],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_non_string_object_id():
    bad_frame = {
        "frame_index": 1,
        "object_transforms": [
            {"object_id": 123, "source_state": {}, "transform": _identity()}
        ],
    }
    with pytest.raises(animation_track.AnimationTrackError, match="object_id"):
        animation_track.build_animation_track(
            frame_count=1,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=[bad_frame],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_malformed_non_first_motion_frame():
    # First frame is well-formed; the second is missing object_transforms.
    # Guards must cover every frame, not just motion_frames[0].
    with pytest.raises(animation_track.AnimationTrackError, match="object_transforms"):
        animation_track.build_animation_track(
            frame_count=2,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0]), _camera([1, 0, 0])],
            motion_frames=[_motion_frame(1), {"frame_index": 2}],
            camera_provenance={},
            object_provenance={},
        )


def test_build_rejects_non_list_motion_frames():
    with pytest.raises(animation_track.AnimationTrackError, match="motion_frames"):
        animation_track.build_animation_track(
            frame_count=1,
            fps=24,
            resolution={"width": 320, "height": 180},
            camera_per_frame=[_camera([0, 0, 0])],
            motion_frames=None,
            camera_provenance={},
            object_provenance={},
        )
