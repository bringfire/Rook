from __future__ import annotations

import json
import os
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .runtime_paths import resolve_runtime_paths

SCHEMA_VERSION = 1
DIRECTOR_VERSION = "slice1"


class DirectorError(Exception):
    pass


class DirectorInputError(DirectorError):
    pass


@dataclass(frozen=True)
class DirectorRuntimePaths:
    director_output_root: Path | None = None


def _runtime_paths() -> DirectorRuntimePaths:
    resolve_runtime_paths()
    return DirectorRuntimePaths()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_director_output_root(runtime: DirectorRuntimePaths | None = None) -> Path:
    runtime = runtime or _runtime_paths()
    if runtime.director_output_root is not None:
        return Path(runtime.director_output_root).expanduser().resolve()
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorInputError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def resolve_output_root(
    output_root: str | None, runtime: DirectorRuntimePaths | None = None
) -> Path:
    allowed_root = _default_director_output_root(runtime)
    if output_root is None:
        return allowed_root
    candidate = Path(output_root).expanduser().resolve()
    if not _is_relative_to(candidate, allowed_root):
        raise DirectorInputError(
            "output_root must resolve under the configured RookVisionDirector output root"
        )
    return candidate


def validate_authoring_request(request: dict[str, Any]) -> None:
    frame_count = int(request.get("frame_count", 0))
    if frame_count < 1:
        raise DirectorInputError("frame_count must be >= 1")

    resolution = request.get("resolution") or {}
    width = int(resolution.get("width", 0))
    height = int(resolution.get("height", 0))
    if width <= 0 or height <= 0:
        raise DirectorInputError("resolution width and height must be positive")

    motion = request.get("motion") or {}
    if motion.get("strategy", "radial_bbox_center") != "radial_bbox_center":
        raise DirectorInputError("motion strategy must be radial_bbox_center for slice1")
    params = motion.get("parameters") or {}
    distance = float(params.get("distance", 10.0))
    if distance < 0:
        raise DirectorInputError("motion distance must be nonnegative")


def identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def translation_matrix(vector: list[float]) -> list[list[float]]:
    matrix = identity_matrix()
    matrix[0][3] = float(vector[0])
    matrix[1][3] = float(vector[1])
    matrix[2][3] = float(vector[2])
    return matrix


def _center(bbox_min: list[float], bbox_max: list[float]) -> list[float]:
    return [(float(a) + float(b)) / 2.0 for a, b in zip(bbox_min, bbox_max)]


def _normalize(vector: list[float]) -> list[float] | None:
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length < 1e-9:
        return None
    return [float(v) / length for v in vector]


def expand_radial_bbox_center(
    objects: list[dict[str, Any]],
    *,
    frame_count: int,
    distance: float,
    per_object_scale: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_mins = [float(v) for obj in objects for v in obj["bbox_min"]]
    all_maxs = [float(v) for obj in objects for v in obj["bbox_max"]]
    selection_min = [min(all_mins[i::3]) for i in range(3)]
    selection_max = [max(all_maxs[i::3]) for i in range(3)]
    selection_center = _center(selection_min, selection_max)

    directions: dict[str, list[float]] = {}
    warnings: list[dict[str, Any]] = []
    for obj in objects:
        object_id = obj["object_id"]
        object_center = _center(obj["bbox_min"], obj["bbox_max"])
        raw = [object_center[i] - selection_center[i] for i in range(3)]
        direction = _normalize(raw)
        if direction is None:
            direction = [1.0, 0.0, 0.0]
            warnings.append({"code": "center_direction_fallback", "object_id": object_id})
        directions[object_id] = direction

    frames: list[dict[str, Any]] = []
    for index in range(1, frame_count + 1):
        t = 0.0 if frame_count == 1 else (index - 1) / (frame_count - 1)
        object_transforms = []
        for obj in objects:
            object_id = obj["object_id"]
            scale = float(per_object_scale.get(object_id, 1.0))
            direction = directions[object_id]
            vector = [component * float(distance) * scale * t for component in direction]
            object_transforms.append(
                {
                    "object_id": object_id,
                    "source_state": {
                        "bbox_min": obj["bbox_min"],
                        "bbox_max": obj["bbox_max"],
                        "validation_strength": obj.get(
                            "validation_strength", "bbox_only"
                        ),
                        "state_hash": obj.get("state_hash"),
                    },
                    "transform": translation_matrix(vector),
                }
            )
        frames.append({"frame_index": index, "object_transforms": object_transforms})
    return frames, warnings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")


async def _resolve_objects(call_native, object_ids: list[str], port: int | None):
    result = await call_native(
        "/director/object-states", "POST", {"object_ids": object_ids}, port=port
    )
    if not result.get("success"):
        raise DirectorInputError(f"object state resolution failed: {result.get('data')}")
    return result["data"]


async def _resolve_camera_keyframes(
    call_native,
    keyframes: list[dict[str, Any]],
    *,
    frame_count: int,
    port: int | None,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for keyframe in sorted(keyframes, key=lambda item: int(item["frame_index"])):
        frame_index = int(keyframe["frame_index"])
        if frame_index < 1 or frame_index > frame_count:
            raise DirectorInputError(
                "camera keyframe frame_index must be inside 1..frame_count"
            )
        result = await call_native(
            "/director/view-state", "POST", {"source": keyframe["source"]}, port=port
        )
        if not result.get("success"):
            raise DirectorInputError(f"camera resolution failed: {result.get('data')}")
        data = result["data"]
        resolved.append(
            {
                "frame_index": frame_index,
                "camera": data["camera"],
                "provenance": data.get("provenance"),
            }
        )
    if not resolved:
        raise DirectorInputError("camera_keyframes must contain at least one keyframe")
    return resolved


def _lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * t


def _lerp_vec(a: list[float], b: list[float], t: float) -> list[float]:
    return [_lerp(a[i], b[i], t) for i in range(3)]


def _normalized_required(vector: list[float], field: str) -> list[float]:
    normalized = _normalize(vector)
    if normalized is None:
        raise DirectorInputError(
            f"camera {field} vector became degenerate during interpolation"
        )
    return normalized


def _interpolate_camera(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, Any]:
    if a["projection"] != b["projection"]:
        raise DirectorInputError(
            "camera projection cannot change during slice1 interpolation"
        )
    camera = dict(a)
    camera["location"] = _lerp_vec(a["location"], b["location"], t)
    camera["target"] = _lerp_vec(a["target"], b["target"], t)
    camera["up"] = _normalized_required(_lerp_vec(a["up"], b["up"], t), "up")
    for field in (
        "lens_length",
        "fov_degrees",
        "parallel_scale",
        "near_clip",
        "far_clip",
        "aspect",
    ):
        av = a.get(field)
        bv = b.get(field)
        if av is None or bv is None:
            camera[field] = av if t < 0.5 else bv
        else:
            camera[field] = _lerp(float(av), float(bv), t)
    return camera


def interpolate_camera_frames(
    resolved_keyframes: list[dict[str, Any]], frame_count: int
) -> list[dict[str, Any]]:
    keyframes = sorted(resolved_keyframes, key=lambda item: item["frame_index"])
    if len(keyframes) == 1:
        return [dict(keyframes[0]["camera"]) for _ in range(frame_count)]

    cameras: list[dict[str, Any]] = []
    for frame_index in range(1, frame_count + 1):
        previous = keyframes[0]
        next_key = keyframes[-1]
        for candidate in keyframes:
            if candidate["frame_index"] <= frame_index:
                previous = candidate
            if candidate["frame_index"] >= frame_index:
                next_key = candidate
                break
        if previous["frame_index"] == next_key["frame_index"]:
            cameras.append(dict(previous["camera"]))
            continue
        span = next_key["frame_index"] - previous["frame_index"]
        t = (frame_index - previous["frame_index"]) / span
        cameras.append(_interpolate_camera(previous["camera"], next_key["camera"], t))
    return cameras


def _frame_id(index: int) -> str:
    return f"frame_{index:04d}"


async def run_director(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    runtime: DirectorRuntimePaths | None = None,
    port: int | None = None,
    should_cancel=None,
) -> dict[str, Any]:
    validate_authoring_request(request)
    runtime = runtime or _runtime_paths()
    output_root = resolve_output_root(request.get("output_root"), runtime)
    run_id = request.get("run_id") or (
        f"director_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}"
    )

    object_ids = list(request.get("object_ids") or [])
    if not object_ids:
        raise DirectorInputError("object_ids must contain at least one object for slice1")

    object_data = await _resolve_objects(call_native, object_ids, port)
    objects = object_data["objects"]
    frame_count = int(request["frame_count"])
    resolved_camera_keyframes = await _resolve_camera_keyframes(
        call_native,
        request["camera_keyframes"],
        frame_count=frame_count,
        port=port,
    )
    frame_cameras = interpolate_camera_frames(resolved_camera_keyframes, frame_count)
    motion_params = (request.get("motion") or {}).get("parameters") or {}
    motion_frames, motion_warnings = expand_radial_bbox_center(
        objects,
        frame_count=frame_count,
        distance=float(motion_params.get("distance", 10.0)),
        per_object_scale=dict(motion_params.get("per_object_scale") or {}),
    )

    run_root = (output_root / run_id).resolve()
    frames_dir = run_root / "frames"
    logs_dir = run_root / "logs"
    frames_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=True)

    manifest_frames = []
    for frame in motion_frames:
        index = frame["frame_index"]
        frame_name = _frame_id(index)
        manifest_frames.append(
            {
                "frame_index": index,
                "frame_id": frame_name,
                "camera": frame_cameras[index - 1],
                "object_transforms": frame["object_transforms"],
                "output_path": str((frames_dir / f"{frame_name}.png").resolve()),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "director_version": DIRECTOR_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_root": str(output_root),
        "created_at": _utc_now(),
        "document_units": object_data.get("units"),
        "source_objects": objects,
        "motion": {
            "strategy": "radial_bbox_center",
            "parameters": motion_params,
            "warnings": motion_warnings,
        },
        "camera_keyframes": request["camera_keyframes"],
        "camera_keyframe_provenance": [
            {
                "frame_index": keyframe["frame_index"],
                "provenance": keyframe.get("provenance"),
            }
            for keyframe in resolved_camera_keyframes
        ],
        "resolution": request["resolution"],
        "display": request.get("display") or {"mode": "Rendered"},
        "frames": manifest_frames,
        "exclusions": [
            "true_depth",
            "edge_pass",
            "rookvision_artifact_handoff",
            "grasshopper_nle",
        ],
    }
    _atomic_write_json(run_root / "manifest.json", manifest)
    _atomic_write_json(
        run_root / "status.json",
        {"state": "running", "run_id": run_id, "updated_at": _utc_now()},
    )

    state = "complete"
    evidence_path = logs_dir / "frame_evidence.jsonl"
    should_cancel = should_cancel or (lambda: False)
    for frame in manifest_frames:
        if should_cancel():
            state = "cancelled"
            break
        instruction = {
            "schema_version": SCHEMA_VERSION,
            "director_version": DIRECTOR_VERSION,
            "run_id": run_id,
            "frame_index": frame["frame_index"],
            "frame_id": frame["frame_id"],
            "run_root": str(run_root),
            "output_path": frame["output_path"],
            "resolution": request["resolution"],
            "display": request.get("display") or {"mode": "Rendered"},
            "camera": frame["camera"],
            "object_transforms": frame["object_transforms"],
        }
        result = await call_native("/director/frame-capture", "POST", instruction, port=port)
        evidence = (
            result.get("data") if isinstance(result.get("data"), dict) else {"error": result.get("data")}
        )
        evidence["success"] = bool(result.get("success"))
        output_path = Path(frame["output_path"])
        if result.get("success") and (
            not output_path.exists() or output_path.stat().st_size <= 0
        ):
            evidence["success"] = False
            evidence["error"] = {
                "code": "missing_output",
                "message": f"Expected frame output was not created: {output_path}",
            }
        try:
            _append_evidence(evidence_path, evidence)
        except OSError:
            state = "evidence_failed"
            break
        if evidence.get("dirty_partial_state"):
            state = "unsafe_failed"
            break
        if not result.get("success"):
            state = "failed"
            break
        if not evidence["success"]:
            state = "failed"
            break

    summary = {
        "state": state,
        "run_id": run_id,
        "run_root": str(run_root),
        "updated_at": _utc_now(),
    }
    _atomic_write_json(run_root / "status.json", summary)
    return summary
