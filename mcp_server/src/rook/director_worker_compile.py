"""Director v3 Slice 3: file-backed worker compiler."""

from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from pathlib import Path
from typing import Any

from . import director_compiler, director_motion
from .bridge import call_rhino
from .director_take_package import (
    canonical_json_text,
    sha256_file,
    utc_now_iso,
)
from .director_worker_common import native_call, open_package_document

WORKER_MAX_FRAME_COUNT = 100_000
_DEFAULT_RESOLUTION = {"width": 1920, "height": 1080}


class DirectorWorkerCompileError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json_file(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(_uuid.UUID(value.strip()))
    except (AttributeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectorWorkerCompileError(
            "package_invalid", f"unparseable package JSON {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise DirectorWorkerCompileError(
            "package_invalid", f"{path.name} must contain a JSON object")
    return data


def _load_compiled_package(package_root_arg: Any) -> dict[str, Any]:
    if not isinstance(package_root_arg, str) or not package_root_arg.strip():
        raise DirectorWorkerCompileError("invalid_input", "package_root is required")
    root = Path(package_root_arg).expanduser().resolve()
    if not root.is_dir():
        raise DirectorWorkerCompileError(
            "package_invalid", f"not a package directory: {root}")

    required = (
        "scene_manifest.json", "scene.3dm", "motion.json", "status.json",
        "member_map.json", "resolved_motion.json", "prepared.3dm")
    for name in required:
        if not (root / name).is_file():
            if name == "prepared.3dm":
                raise DirectorWorkerCompileError(
                    "package_invalid",
                    "package is missing prepared.3dm; re-run prepare")
            raise DirectorWorkerCompileError(
                "package_invalid", f"package is missing {name}")

    manifest = _read_json(root / "scene_manifest.json")
    member_map = _read_json(root / "member_map.json")
    resolved_motion = _read_json(root / "resolved_motion.json")
    status = _read_json(root / "status.json")

    if status.get("phase") not in ("prepared", "compiled"):
        raise DirectorWorkerCompileError(
            "package_invalid",
            f"package phase {status.get('phase')!r} is not compilable")

    manifest_sha = _sha256_json_file(root / "scene_manifest.json")
    motion_sha = _sha256_json_file(root / "motion.json")
    member_map_sha = _sha256_json_file(root / "member_map.json")
    resolved_sha = _sha256_json_file(root / "resolved_motion.json")
    prepared_sha = sha256_file(root / "prepared.3dm")
    evidence = status.get("evidence") or {}
    mismatches: list[str] = []

    if status.get("scene_manifest_sha256") != manifest_sha:
        mismatches.append("scene_manifest.json")
    manifest_hashes = manifest.get("hashes") or {}
    if manifest_hashes.get("motion_json_sha256") != motion_sha:
        mismatches.append("motion.json")
    if evidence.get("member_map_sha256") != member_map_sha:
        mismatches.append("member_map.json")
    if evidence.get("resolved_motion_sha256") != resolved_sha:
        mismatches.append("resolved_motion.json")
    if evidence.get("prepared_scene_sha256") != prepared_sha:
        mismatches.append("prepared.3dm")

    prepared_scene = member_map.get("prepared_scene") or {}
    if (prepared_scene.get("sha256") != prepared_sha
            or prepared_scene.get("bytes") != (root / "prepared.3dm").stat().st_size):
        mismatches.append("member_map.prepared_scene")

    derived = resolved_motion.get("derived_from") or {}
    if derived.get("motion_json_sha256") != motion_sha:
        mismatches.append("resolved_motion.derived_from.motion_json_sha256")
    if derived.get("member_map_sha256") != member_map_sha:
        mismatches.append("resolved_motion.derived_from.member_map_sha256")
    if derived.get("scene_manifest_sha256") != manifest_sha:
        mismatches.append("resolved_motion.derived_from.scene_manifest_sha256")

    if mismatches:
        raise DirectorWorkerCompileError(
            "package_hash_mismatch",
            "package artifacts disagree with recorded hashes: "
            + ", ".join(mismatches))

    return {
        "root": root,
        "manifest": manifest,
        "member_map": member_map,
        "resolved_motion": resolved_motion,
        "status": status,
        "hashes": {
            "manifest": manifest_sha,
            "member_map": member_map_sha,
            "resolved_motion": resolved_sha,
            "prepared": prepared_sha,
        },
    }


def _member_map_created_ids(member_map: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for actor in member_map.get("actor_sets") or []:
        for member in actor.get("members") or []:
            for object_id in member.get("created_object_ids") or []:
                canonical = _canonical_uuid(object_id)
                if canonical is None:
                    raise DirectorWorkerCompileError(
                        "package_invalid",
                        f"member_map contains invalid created object id: {object_id!r}")
                out.add(canonical)
    return out


async def resolve_worker_source_states(call_native, object_ids: list[str],
                                       port: int | None) -> dict[str, dict[str, Any]]:
    response = await native_call(
        call_native, "/director/object-states", "POST",
        {"object_ids": list(object_ids)}, port, "compile_failed",
        DirectorWorkerCompileError)
    objects = response.get("objects") if isinstance(response, dict) else None
    if not isinstance(objects, list):
        raise DirectorWorkerCompileError(
            "compile_failed", "/director/object-states returned no objects array")

    by_id: dict[str, dict[str, Any]] = {}
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        canonical = _canonical_uuid(obj.get("object_id"))
        if canonical is not None:
            by_id[canonical] = obj

    states: dict[str, dict[str, Any]] = {}
    non_tight: list[str] = []
    missing: list[str] = []
    for object_id in object_ids:
        obj = by_id.get(object_id)
        if obj is None:
            missing.append(object_id)
            continue
        if obj.get("bbox_method") != "tight_object":
            non_tight.append(
                f"{object_id} (bbox_method={obj.get('bbox_method')!r})")
            continue
        states[object_id] = {
            "bbox_min": obj["bbox_min"],
            "bbox_max": obj["bbox_max"],
            "bbox_method": "tight_object",
            "validation_strength": "tight_bbox",
            "state_hash": obj.get("state_hash"),
        }
    if missing:
        raise DirectorWorkerCompileError(
            "compile_failed",
            "object state resolution missed animated objects: "
            + ", ".join(missing))
    if non_tight:
        raise DirectorWorkerCompileError(
            "compile_source_state_not_tight",
            "tight bbox required for animated objects: "
            + ", ".join(non_tight))
    return states


def _bbox_center(bbox_min, bbox_max):
    return [(float(bbox_min[i]) + float(bbox_max[i])) / 2.0 for i in range(3)]


def build_worker_object_frames(expanded: dict[str, list[dict[str, Any]]],
                               source_states: dict[str, dict[str, Any]],
                               frame_count: int,
                               default_easing: str) -> list[dict[str, Any]]:
    object_ids = sorted(expanded)
    per_object = {}
    for object_id in object_ids:
        state = source_states[object_id]
        center = _bbox_center(state["bbox_min"], state["bbox_max"])
        try:
            per_object[object_id] = director_motion.compile_object_track(
                expanded[object_id], frame_count=frame_count,
                source_center=center, default_easing=default_easing)
        except director_motion.MotionError as exc:
            raise director_compiler.DirectorCompileError(
                exc.code, str(exc), object_id=object_id) from exc

    frames = []
    for frame_index in range(frame_count):
        transforms = []
        for object_id in object_ids:
            state = source_states[object_id]
            transforms.append({
                "object_id": object_id,
                "source_state": {
                    "bbox_min": state["bbox_min"],
                    "bbox_max": state["bbox_max"],
                    "bbox_method": state["bbox_method"],
                    "validation_strength": state["validation_strength"],
                    "state_hash": state["state_hash"],
                },
                "transform": per_object[object_id][frame_index],
            })
        frames.append({
            "frame_index": frame_index + 1,
            "object_transforms": transforms,
        })
    return frames


def _wrap_compile_error(exc: director_compiler.DirectorCompileError):
    return DirectorWorkerCompileError(
        "compile_failed", f"{exc.code}: {exc.message}")


def _provenance(spec: dict[str, Any], expanded: dict[str, list[dict[str, Any]]],
                frame_count: int, fps: int, default_easing: str,
                object_ids: list[str]) -> dict[str, Any]:
    groups = spec.get("groups") or {}
    referenced_groups = {}
    for entry in spec.get("motion") or []:
        target = entry.get("target") if isinstance(entry, dict) else None
        if isinstance(target, str) and target in groups:
            referenced_groups[target] = list(groups[target])
    return {
        "frame_count": frame_count,
        "fps": fps,
        "duration_ms": frame_count * (1000.0 / fps),
        "animated_object_ids": object_ids,
        "group_expansion": referenced_groups,
        "segment_mapping": {
            object_id: [
                {
                    "t": float(kf["t"]),
                    "ease_from_previous": kf.get(
                        "ease_from_previous", default_easing),
                }
                for kf in expanded[object_id]
            ]
            for object_id in object_ids
        },
        "warnings": [],
    }


async def compile_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None,
                       now_fn=utc_now_iso) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DirectorWorkerCompileError(
            "invalid_input", "compile request must be an object")
    pkg = _load_compiled_package(arguments.get("package_root"))
    root = pkg["root"]

    await open_package_document(
        call_native, root, root / "prepared.3dm", port=port,
        error_cls=DirectorWorkerCompileError, mode="require_fresh")

    spec = pkg["resolved_motion"]
    default_easing = arguments.get("default_easing", "linear")
    if default_easing not in director_motion.EASING_NAMES:
        raise DirectorWorkerCompileError(
            "compile_failed", f"invalid_keyframe: unknown default_easing: {default_easing!r}")

    try:
        timeline = director_compiler.resolve_compiler_timeline(spec)
        expanded = director_compiler.expand_targets(spec)
    except director_compiler.DirectorCompileError as exc:
        raise _wrap_compile_error(exc) from exc

    fps = timeline["fps"]
    frame_count = timeline["frame_count"]
    duration_seconds = timeline["duration_seconds"]
    if frame_count > WORKER_MAX_FRAME_COUNT:
        raise DirectorWorkerCompileError(
            "compile_failed",
            f"frame_count exceeds worker max {WORKER_MAX_FRAME_COUNT}")

    object_ids = sorted(expanded)
    allowed_ids = _member_map_created_ids(pkg["member_map"])
    unknown = [object_id for object_id in object_ids if object_id not in allowed_ids]
    if unknown:
        raise DirectorWorkerCompileError(
            "compile_track_mismatch",
            "animated ids are not present in member_map: " + ", ".join(unknown))

    source_states = await resolve_worker_source_states(
        call_native, object_ids, port)
    try:
        object_frames = build_worker_object_frames(
            expanded, source_states, frame_count, default_easing)
        camera_frames = await director_compiler.build_camera_frames(
            spec, frame_count, spec.get("resolution") or _DEFAULT_RESOLUTION,
            duration_seconds, fps, call_native, port)
    except director_compiler.DirectorCompileError as exc:
        raise _wrap_compile_error(exc) from exc

    track = {
        "transform_semantics": "absolute_from_source",
        "fps": fps,
        "frame_count": frame_count,
        "animated_object_ids": object_ids,
        "camera_frames": camera_frames,
        "object_frames": object_frames,
        "derived_from": {
            "resolved_motion_sha256": pkg["hashes"]["resolved_motion"],
            "member_map_sha256": pkg["hashes"]["member_map"],
            "prepared_3dm_sha256": pkg["hashes"]["prepared"],
        },
    }
    provenance = _provenance(
        spec, expanded, frame_count, fps, default_easing, object_ids)

    track_text = canonical_json_text(track)
    provenance_text = canonical_json_text(provenance)
    track_sha = _sha256_text(track_text)
    provenance_sha = _sha256_text(provenance_text)

    (root / "track.json").write_text(track_text, encoding="utf-8")
    (root / "compile_provenance.json").write_text(
        provenance_text, encoding="utf-8")

    status = dict(pkg["status"])
    status["phase"] = "compiled"
    status["heartbeat_utc"] = now_fn()
    status["evidence"] = {
        **(status.get("evidence") or {}),
        "track_json_sha256": track_sha,
        "compile_provenance_sha256": provenance_sha,
        "prepared_scene_sha256": pkg["hashes"]["prepared"],
    }
    (root / "status.json").write_text(
        canonical_json_text(status), encoding="utf-8")

    return {
        "package_root": str(root),
        "take_id": pkg["status"].get("take_id"),
        "package_id": pkg["status"].get("package_id"),
        "phase": "compiled",
        "frame_count": frame_count,
        "fps": fps,
        "animated_object_count": len(object_ids),
        "track_json_sha256": track_sha,
        "compile_provenance_sha256": provenance_sha,
    }
