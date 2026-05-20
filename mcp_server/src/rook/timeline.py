from __future__ import annotations

import math
from typing import Any


class TimelineError(ValueError):
    pass


TIMING_FIELDS = ("frame_index", "time", "at")


def _round_half_up(value: float) -> int:
    if not math.isfinite(value) or value < 0:
        raise TimelineError("timeline rounding input must be finite and nonnegative")
    return int(math.floor(value + 0.5))


def _positive_integral(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise TimelineError(f"{field} must be a positive integral value")
    try:
        numeric = int(value)
    except (TypeError, ValueError, OverflowError) as ex:
        raise TimelineError(f"{field} must be a positive integral value") from ex
    if numeric != value and not (isinstance(value, str) and str(numeric) == value):
        raise TimelineError(f"{field} must be a positive integral value")
    if numeric <= 0:
        raise TimelineError(f"{field} must be a positive integral value")
    return numeric


def _finite_float(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as ex:
        raise TimelineError(f"{field} must be finite") from ex
    if not math.isfinite(numeric):
        raise TimelineError(f"{field} must be finite")
    return numeric


def resolve_timeline(request: dict[str, Any]) -> dict[str, Any]:
    timeline = request.get("timeline")
    if timeline is None:
        frame_count = _positive_integral(request.get("frame_count"), "frame_count")
        return {
            "source": "frame_count",
            "fps": None,
            "duration_seconds": None,
            "frame_count": frame_count,
        }

    if not isinstance(timeline, dict):
        raise TimelineError("timeline must be an object")

    fps = _positive_integral(timeline.get("fps"), "timeline.fps")
    duration_seconds = _finite_float(
        timeline.get("duration_seconds"), "timeline.duration_seconds"
    )
    if duration_seconds <= 0:
        raise TimelineError("timeline.duration_seconds must be positive")

    derived_frame_count = _round_half_up(duration_seconds * fps)
    if derived_frame_count < 1:
        raise TimelineError("timeline derived frame_count must be >= 1")

    if "frame_count" in request:
        supplied_frame_count = _positive_integral(
            request.get("frame_count"), "frame_count"
        )
        if supplied_frame_count != derived_frame_count:
            raise TimelineError("frame_count must equal timeline-derived frame_count")

    return {
        "source": "timeline",
        "fps": fps,
        "duration_seconds": duration_seconds,
        "frame_count": derived_frame_count,
    }


def _timing_fields_present(keyframe: dict[str, Any]) -> list[str]:
    return [field for field in TIMING_FIELDS if field in keyframe]


def _frame_index_from_keyframe(
    keyframe: dict[str, Any],
    *,
    timeline_manifest: dict[str, Any],
) -> int:
    present = _timing_fields_present(keyframe)
    if len(present) != 1:
        raise TimelineError(
            "camera keyframe must contain exactly one of frame_index, time, or at"
        )

    frame_count = int(timeline_manifest["frame_count"])
    field = present[0]
    if field == "frame_index":
        frame_index = _positive_integral(keyframe.get("frame_index"), "frame_index")
    elif field == "time":
        if timeline_manifest["duration_seconds"] is None:
            raise TimelineError(
                "camera keyframe time requires timeline.duration_seconds"
            )
        time_value = _finite_float(keyframe.get("time"), "time")
        duration = float(timeline_manifest["duration_seconds"])
        if time_value < 0 or time_value > duration:
            raise TimelineError(
                "camera keyframe time must be inside 0..duration_seconds"
            )
        frame_index = _round_half_up(
            1 + (time_value / duration) * (frame_count - 1)
        )
    else:
        at_value = _finite_float(keyframe.get("at"), "at")
        if at_value < 0 or at_value > 1:
            raise TimelineError("camera keyframe at must be inside 0..1")
        frame_index = _round_half_up(1 + at_value * (frame_count - 1))

    if frame_index < 1 or frame_index > frame_count:
        raise TimelineError(
            "camera keyframe frame_index must be inside 1..frame_count"
        )
    return frame_index


def _normalize_keyframe(
    keyframe: Any,
    *,
    timeline_manifest: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(keyframe, dict):
        raise TimelineError("camera keyframe entries must be objects")
    normalized = dict(keyframe)
    frame_index = _frame_index_from_keyframe(
        normalized, timeline_manifest=timeline_manifest
    )
    for field in ("time", "at"):
        normalized.pop(field, None)
    normalized["frame_index"] = frame_index
    return normalized


def _normalize_keyframes(
    keyframes: Any,
    *,
    timeline_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(keyframes, list) or not keyframes:
        raise TimelineError("camera keyframes must contain at least one keyframe")
    return [
        _normalize_keyframe(keyframe, timeline_manifest=timeline_manifest)
        for keyframe in keyframes
    ]


def normalize_director_request(
    request: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timeline_manifest = resolve_timeline(request)
    normalized = dict(request)
    normalized["frame_count"] = timeline_manifest["frame_count"]

    if isinstance(normalized.get("camera"), dict):
        camera = dict(normalized["camera"])
        camera["keyframes"] = _normalize_keyframes(
            camera.get("keyframes"), timeline_manifest=timeline_manifest
        )
        normalized["camera"] = camera
    elif "camera_keyframes" in normalized:
        normalized["camera_keyframes"] = _normalize_keyframes(
            normalized.get("camera_keyframes"), timeline_manifest=timeline_manifest
        )

    return normalized, timeline_manifest
