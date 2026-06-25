"""Animation compiler (PR4): compiles a high-level object-motion authoring spec
into the baked replay track consumed by native /director/replay. Python-only;
no native changes. See
docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from . import camera_planner, director_motion, timeline
from .bridge import call_rhino


class DirectorCompileError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_data(self) -> dict:
        return {"code": self.code, "message": self.message, **self.extra}


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(_uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def _is_uuid(value: Any) -> bool:
    return _canonical_uuid(value) is not None


def _require_uuid(value: Any, message: str) -> str:
    canonical = _canonical_uuid(value)
    if canonical is None:
        raise DirectorCompileError("invalid_input", message)
    return canonical


def _canonicalize_object_ids(object_ids) -> list[str]:
    out = []
    for oid in object_ids:
        canonical = _canonical_uuid(oid)
        if canonical is None:
            raise DirectorCompileError("source_resolution_failed", f"object id is not a valid UUID: {oid!r}")
        out.append(canonical)
    return out


def resolve_compiler_timeline(spec: dict) -> dict:
    block = spec.get("timeline")
    if not isinstance(block, dict):
        raise DirectorCompileError(
            "invalid_timeline", "timeline block with fps is required (fps-None path unsupported)")
    fps = block.get("fps")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise DirectorCompileError("invalid_timeline", "timeline.fps must be a positive integer")
    has_duration = "duration_seconds" in block
    has_frame_count = "frame_count" in block
    if has_duration == has_frame_count:
        raise DirectorCompileError(
            "invalid_timeline", "timeline needs exactly one of duration_seconds or frame_count")
    if has_duration:
        # reuse the verified timeline.py normalizer
        try:
            resolved = timeline.resolve_timeline({"timeline": {"fps": fps, "duration_seconds": block["duration_seconds"]}})
        except timeline.TimelineError as exc:
            raise DirectorCompileError("invalid_timeline", str(exc)) from exc
        return {"fps": resolved["fps"], "frame_count": resolved["frame_count"],
                "duration_seconds": float(resolved["duration_seconds"])}
    # {fps, frame_count}: compiler computes duration itself
    fc = block.get("frame_count")
    if isinstance(fc, bool) or not isinstance(fc, int) or fc < 1:
        raise DirectorCompileError("invalid_timeline", "timeline.frame_count must be a positive integer")
    return {"fps": fps, "frame_count": fc, "duration_seconds": fc / fps}


def _resolve_group(name: str, groups: dict) -> list[str]:
    members = groups[name]
    if not isinstance(members, list) or not members:
        raise DirectorCompileError("empty_group", f"group '{name}' resolves to no objects")
    # Duplicate ids WITHIN one group collapse to a set (spec) — preserve stable order.
    # Store the canonical UUID form so group members and bare-id targets key
    # identically, keeping cross-track duplicate_object_target detection consistent.
    seen: set[str] = set()
    out: list[str] = []
    for m in members:
        canonical = _require_uuid(m, f"group '{name}' member is not a valid object UUID: {m!r}")
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def expand_targets(spec: dict) -> dict:
    groups = spec.get("groups") or {}
    if not isinstance(groups, dict):
        raise DirectorCompileError("invalid_input", "groups must be an object")
    for name in groups:
        if _is_uuid(name):
            raise DirectorCompileError("invalid_input", f"group name must not be UUID-shaped: {name!r}")

    motion = spec.get("motion")
    if not isinstance(motion, list) or not motion:
        raise DirectorCompileError("invalid_input", "motion must be a non-empty array")

    expanded: dict[str, list[dict]] = {}
    for entry in motion:
        if not isinstance(entry, dict) or "target" not in entry:
            raise DirectorCompileError("invalid_input", "motion entry must be an object with a target")
        target = entry["target"]
        keyframes = entry.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise DirectorCompileError("invalid_input", "motion entry requires a non-empty keyframes array")
        if isinstance(target, str) and target in groups:
            object_ids = _resolve_group(target, groups)
        elif _is_uuid(target):
            object_ids = [_require_uuid(target, f"target is not a valid object UUID: {target!r}")]
        elif isinstance(target, str):
            raise DirectorCompileError("unknown_group", f"target is not a declared group or valid UUID: {target!r}")
        else:
            raise DirectorCompileError("invalid_input", "target must be a string (group name or object UUID)")
        for oid in object_ids:
            if oid in expanded:
                raise DirectorCompileError(
                    "duplicate_object_target",
                    f"object {oid} is claimed by more than one motion track", object_id=oid)
            expanded[oid] = keyframes
    return expanded


def validate_caps(object_count: int, frame_count: int, fps: int) -> None:
    if object_count > 256:
        raise DirectorCompileError("object_count_exceeds_cap", "animated objects exceed 256")
    if frame_count > 3000:
        raise DirectorCompileError("frame_count_exceeds_cap", "frame_count exceeds 3000")
    dwell_ms = 1000.0 / fps
    if dwell_ms > 250.0:
        raise DirectorCompileError("frame_dwell_exceeds_cap", "1000/fps exceeds 250ms (fps too low)")
    if frame_count * dwell_ms > 60000.0:
        raise DirectorCompileError("replay_duration_exceeds_cap", "frame_count*dwell exceeds 60000ms")


async def resolve_source_states(call_native, object_ids, port):
    object_ids = _canonicalize_object_ids(object_ids)
    result = await call_native("/director/object-states", "POST", {"object_ids": list(object_ids)}, port=port)
    if not result.get("success"):
        raise DirectorCompileError(
            "source_resolution_failed", f"object state resolution failed: {result.get('data')}")
    objects = (result.get("data") or {}).get("objects") or []
    by_id = {}
    for obj in objects:
        canonical = _canonical_uuid(obj.get("object_id"))
        if canonical is not None:
            by_id[canonical] = obj
    states = {}
    for oid in object_ids:
        obj = by_id.get(oid)
        if obj is None:
            raise DirectorCompileError(
                "source_resolution_failed", f"object not resolved: {oid}", object_id=oid)
        states[oid] = {
            "bbox_min": obj["bbox_min"],
            "bbox_max": obj["bbox_max"],
            "state_hash": obj.get("state_hash"),
        }
    return states


def _bbox_center(bbox_min, bbox_max):
    return [(float(bbox_min[i]) + float(bbox_max[i])) / 2.0 for i in range(3)]


def build_object_frames(expanded, source_states, frame_count, default_easing):
    object_ids = sorted(expanded)
    # per-object per-frame matrices
    per_object = {}
    for oid in object_ids:
        st = source_states[oid]
        center = _bbox_center(st["bbox_min"], st["bbox_max"])
        try:
            per_object[oid] = director_motion.compile_object_track(
                expanded[oid], frame_count=frame_count, source_center=center, default_easing=default_easing)
        except director_motion.MotionError as exc:
            raise DirectorCompileError(exc.code, str(exc), object_id=oid) from exc

    frames = []
    for i in range(frame_count):
        transforms = []
        for oid in object_ids:
            st = source_states[oid]
            transforms.append({
                "object_id": oid,
                "source_state": {
                    "bbox_min": st["bbox_min"],
                    "bbox_max": st["bbox_max"],
                    "validation_strength": "bbox_only",
                    "state_hash": st["state_hash"],
                },
                "transform": per_object[oid][i],
            })
        frames.append({"frame_index": i + 1, "object_transforms": transforms})
    return frames


_DEFAULT_RESOLUTION = {"width": 1920, "height": 1080}
_DEFAULT_CAMERA = {"strategy": "keyframes",
                   "keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]}


async def build_camera_frames(spec, frame_count, resolution, duration_seconds, fps, call_native, port):
    cam_spec = spec.get("camera")
    if not isinstance(cam_spec, dict):
        cam_spec = _DEFAULT_CAMERA
    request = {"timeline": {"fps": fps, "duration_seconds": duration_seconds}, "camera": cam_spec}
    try:
        normalized, _ = timeline.normalize_director_request(request)
    except timeline.TimelineError as exc:
        raise DirectorCompileError("invalid_camera", str(exc)) from exc
    try:
        camera_planner.validate_camera_request(normalized, frame_count=frame_count, resolution=resolution)
    except camera_planner.CameraPlanError as exc:
        raise DirectorCompileError("invalid_camera", str(exc)) from exc
    try:
        plan = await camera_planner.resolve_camera_plan(
            normalized, frame_count=frame_count, resolution=resolution, call_native=call_native, port=port)
    except camera_planner.CameraPlanError as exc:
        raise DirectorCompileError("camera_resolution_failed", str(exc)) from exc
    cam_frames = plan["frames"]
    return [{"frame_index": i + 1, "camera": cam_frames[i]} for i in range(frame_count)]


def _resolution(spec):
    res = spec.get("resolution") or _DEFAULT_RESOLUTION
    return res


async def compile_motion(arguments: dict, *, call_native=call_rhino, port: int | None = None) -> dict:
    if not isinstance(arguments, dict):
        raise DirectorCompileError("invalid_input", "compile request must be an object")
    default_easing = arguments.get("default_easing", "linear")
    if default_easing not in director_motion.EASING_NAMES:
        raise DirectorCompileError(
            "invalid_keyframe", f"unknown default_easing: {default_easing!r}")

    tl = resolve_compiler_timeline(arguments)
    fps, frame_count, duration_seconds = tl["fps"], tl["frame_count"], tl["duration_seconds"]

    expanded = expand_targets(arguments)
    object_ids = sorted(expanded)
    validate_caps(object_count=len(object_ids), frame_count=frame_count, fps=fps)

    source_states = await resolve_source_states(call_native, object_ids, port)
    object_frames = build_object_frames(expanded, source_states, frame_count, default_easing)
    resolution = _resolution(arguments)
    camera_frames = await build_camera_frames(
        arguments, frame_count, resolution, duration_seconds, fps, call_native, port)

    track = {
        "transform_semantics": "absolute_from_source",
        "fps": fps,
        "frame_count": frame_count,
        "animated_object_ids": object_ids,
        "camera_frames": camera_frames,
        "object_frames": object_frames,
    }
    groups = arguments.get("groups") or {}
    referenced_groups = {}
    for entry in arguments["motion"]:
        tgt = entry.get("target")
        if isinstance(tgt, str) and tgt in groups:
            referenced_groups[tgt] = list(groups[tgt])
    provenance = {
        "frame_count": frame_count,
        "fps": fps,
        "duration_ms": frame_count * (1000.0 / fps),
        "animated_object_ids": object_ids,
        "group_expansion": referenced_groups,
        "segment_mapping": {
            oid: [{"t": float(kf["t"]), "ease_from_previous": kf.get("ease_from_previous", default_easing)}
                  for kf in expanded[oid]]
            for oid in object_ids
        },
        "warnings": [],
    }
    return {"track": track, "provenance": provenance}
