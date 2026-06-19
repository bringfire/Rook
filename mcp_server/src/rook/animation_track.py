from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ANIMATION_SCHEMA_VERSION = 1
ANIMATION_VERSION = "v1"
TRANSFORM_SEMANTICS = "absolute_from_source"


class AnimationTrackError(Exception):
    pass


def build_animation_track(
    *,
    frame_count: int,
    fps: int | None,
    resolution: dict[str, int],
    camera_per_frame: list[dict[str, Any]],
    motion_frames: list[dict[str, Any]],
    camera_provenance: dict[str, Any],
    object_provenance: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise AnimationTrackError("frame_count must be an integer >= 1")
    if not isinstance(camera_per_frame, list):
        raise AnimationTrackError("camera_per_frame must be a list")
    if not isinstance(motion_frames, list):
        raise AnimationTrackError("motion_frames must be a list")
    if len(camera_per_frame) != frame_count:
        raise AnimationTrackError("camera_per_frame length must equal frame_count")
    if len(motion_frames) != frame_count:
        raise AnimationTrackError("motion_frames length must equal frame_count")

    for frame in motion_frames:
        if not isinstance(frame, dict):
            raise AnimationTrackError("motion_frames entries must be objects")
        frame_index = frame.get("frame_index")
        if not isinstance(frame_index, int) or isinstance(frame_index, bool):
            raise AnimationTrackError("motion_frames frame_index must be an integer")
        transforms = frame.get("object_transforms")
        if not isinstance(transforms, list) or not transforms:
            raise AnimationTrackError(
                "motion_frames object_transforms must be a non-empty list"
            )
        for transform in transforms:
            if not isinstance(transform, dict) or not isinstance(transform.get("object_id"), str):
                raise AnimationTrackError(
                    "motion_frames object_transforms.object_id must be a string"
                )

    animated_object_ids = [
        transform["object_id"]
        for transform in motion_frames[0]["object_transforms"]
    ]
    camera_frames = [
        {"frame_index": index + 1, "camera": camera_per_frame[index]}
        for index in range(frame_count)
    ]
    object_frames = [
        {
            "frame_index": frame["frame_index"],
            "object_transforms": frame["object_transforms"],
        }
        for frame in motion_frames
    ]
    return {
        "schema_version": ANIMATION_SCHEMA_VERSION,
        "animation_version": ANIMATION_VERSION,
        "frame_count": frame_count,
        "fps": fps,
        "resolution": resolution,
        "transform_semantics": TRANSFORM_SEMANTICS,
        "animated_object_ids": animated_object_ids,
        "camera_frames": camera_frames,
        "object_frames": object_frames,
        "camera_provenance": camera_provenance,
        "object_provenance": object_provenance,
    }


def _is_4x4_finite(matrix: Any) -> bool:
    if not isinstance(matrix, list) or len(matrix) != 4:
        return False
    for row in matrix:
        if not isinstance(row, list) or len(row) != 4:
            return False
        for value in row:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            if not math.isfinite(float(value)):
                return False
    return True


def _validate_frame_index_sequence(frames: list[dict[str, Any]], frame_count: int, field: str) -> None:
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise AnimationTrackError(
            f"{field} must contain exactly frame_count ({frame_count}) entries"
        )
    for position, frame in enumerate(frames, start=1):
        if not isinstance(frame, dict):
            raise AnimationTrackError(f"{field} entries must be objects")
        if frame.get("frame_index") != position:
            raise AnimationTrackError(
                f"{field} frame_index must be 1..frame_count in order"
            )


def validate_animation_track(track: dict[str, Any]) -> None:
    if not isinstance(track, dict):
        raise AnimationTrackError("track must be an object")
    if track.get("schema_version") != ANIMATION_SCHEMA_VERSION:
        raise AnimationTrackError("schema_version must be 1")
    if track.get("animation_version") != ANIMATION_VERSION:
        raise AnimationTrackError("animation_version must be 'v1'")
    if track.get("transform_semantics") != TRANSFORM_SEMANTICS:
        raise AnimationTrackError(
            "transform_semantics must be 'absolute_from_source'"
        )

    frame_count = track.get("frame_count")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise AnimationTrackError("frame_count must be an integer >= 1")

    fps = track.get("fps")
    if fps is not None and (not isinstance(fps, int) or isinstance(fps, bool) or fps < 1):
        raise AnimationTrackError("fps must be null or a positive integer")

    resolution = track.get("resolution")
    if not isinstance(resolution, dict):
        raise AnimationTrackError("resolution must be an object")
    for axis in ("width", "height"):
        value = resolution.get(axis)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AnimationTrackError(f"resolution.{axis} must be a positive integer")

    object_ids = track.get("animated_object_ids")
    if (
        not isinstance(object_ids, list)
        or not object_ids
        or not all(isinstance(oid, str) for oid in object_ids)
        or len(set(object_ids)) != len(object_ids)
    ):
        raise AnimationTrackError(
            "animated_object_ids must be a non-empty list of unique strings"
        )

    _validate_frame_index_sequence(track.get("camera_frames"), frame_count, "camera_frames")
    _validate_frame_index_sequence(track.get("object_frames"), frame_count, "object_frames")

    for frame in track["camera_frames"]:
        if not isinstance(frame.get("camera"), dict):
            raise AnimationTrackError("camera_frames[*].camera must be an object")

    expected_ids = set(object_ids)
    for frame in track["object_frames"]:
        transforms = frame.get("object_transforms")
        if not isinstance(transforms, list):
            raise AnimationTrackError("object_frames.object_transforms must be a list")
        for transform in transforms:
            if not isinstance(transform, dict):
                raise AnimationTrackError("object_transforms entries must be objects")
        frame_ids = [t.get("object_id") for t in transforms]
        if set(frame_ids) != expected_ids or len(frame_ids) != len(expected_ids):
            raise AnimationTrackError(
                "every object frame must cover exactly animated_object_ids "
                f"(frame {frame.get('frame_index')})"
            )
        for transform in transforms:
            if not isinstance(transform.get("object_id"), str):
                raise AnimationTrackError("object_transforms.object_id must be a string")
            source_state = transform.get("source_state")
            if not isinstance(source_state, dict):
                raise AnimationTrackError(
                    "object_transforms.source_state must be an object"
                )
            strength = source_state.get("validation_strength")
            if not isinstance(strength, str):
                raise AnimationTrackError(
                    "source_state.validation_strength is required"
                )
            if strength == "bbox_only":
                for bbox_field in ("bbox_min", "bbox_max"):
                    box = source_state.get(bbox_field)
                    if (
                        not isinstance(box, list)
                        or len(box) != 3
                        or not all(
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and math.isfinite(float(value))
                            for value in box
                        )
                    ):
                        raise AnimationTrackError(
                            f"source_state.{bbox_field} must be 3 finite numbers for bbox_only"
                        )
            if not _is_4x4_finite(transform.get("transform")):
                raise AnimationTrackError(
                    "object_transforms.transform must be a 4x4 matrix of finite numbers"
                )
