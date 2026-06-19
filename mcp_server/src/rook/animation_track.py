from __future__ import annotations

import json
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
