from __future__ import annotations

import copy
import hashlib
import json
import os
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import camera_planner, timeline
from .bridge import call_rhino
from .runtime_paths import resolve_runtime_paths

SCHEMA_VERSION = 1
DIRECTOR_VERSION = "slice1"
MAX_VIDEO_FPS = 240
MAX_VIDEO_FRAME_COUNT = 5000
MAX_VIDEO_WIDTH = 8192
MAX_VIDEO_HEIGHT = 8192
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


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

    per_object_scale = params.get("per_object_scale", {})
    if not isinstance(per_object_scale, dict):
        raise DirectorInputError("per_object_scale must be an object")
    for object_id, scale in per_object_scale.items():
        try:
            numeric_scale = float(scale)
        except (TypeError, ValueError) as ex:
            raise DirectorInputError(
                f"per_object_scale for {object_id} must be numeric"
            ) from ex
        if numeric_scale < 0:
            raise DirectorInputError(
                f"per_object_scale for {object_id} must be nonnegative"
            )

    has_legacy_camera = "camera_keyframes" in request
    has_camera_request = isinstance(request.get("camera"), dict)
    if not has_legacy_camera and not has_camera_request:
        raise DirectorInputError("camera.keyframes or camera_keyframes is required")


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


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _prepare_run_inputs(
    director_authoring_spec: dict[str, Any],
    provenance: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    copied_spec_hash = _sha256_payload(director_authoring_spec)
    copied_spec = copy.deepcopy(director_authoring_spec)
    full_provenance = copy.deepcopy(provenance)
    source_hash = full_provenance.get("source_spec_sha256")
    if source_hash is not None and source_hash != copied_spec_hash:
        raise DirectorInputError("source_spec_sha256 must match copied authoring spec")
    spec_id = director_authoring_spec.get("spec_id")
    source_spec_id = full_provenance.get("source_spec_id")
    if source_spec_id is not None and source_spec_id != spec_id:
        raise DirectorInputError("source_spec_id must match copied authoring spec spec_id")
    spec_source = director_authoring_spec.get("source")
    spec_canvas_hash = (
        spec_source.get("canvas_export_state_sha256")
        if isinstance(spec_source, dict)
        else None
    )
    canvas_hash = full_provenance.get("canvas_export_state_sha256")
    if (
        canvas_hash is not None
        and spec_canvas_hash is not None
        and canvas_hash != spec_canvas_hash
    ):
        raise DirectorInputError(
            "canvas_export_state_sha256 must match copied authoring spec source"
        )
    full_provenance["source_spec_sha256"] = copied_spec_hash
    full_provenance["copied_spec_sha256"] = copied_spec_hash
    return copied_spec, full_provenance


def _write_run_inputs(
    run_root: Path,
    *,
    director_authoring_spec: dict[str, Any],
    provenance: dict[str, Any],
) -> None:
    copied_spec, full_provenance = _prepare_run_inputs(
        director_authoring_spec,
        provenance,
    )
    inputs_dir = run_root / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(inputs_dir / "director_authoring_spec.json", copied_spec)
    _atomic_write_json(inputs_dir / "provenance.json", full_provenance)


def _validate_run_inputs(
    run_inputs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(run_inputs, dict):
        raise DirectorInputError("run_inputs must be an object")
    director_authoring_spec = run_inputs.get("director_authoring_spec")
    if not isinstance(director_authoring_spec, dict):
        raise DirectorInputError("run_inputs.director_authoring_spec must be an object")
    provenance = run_inputs.get("provenance", {})
    if not isinstance(provenance, dict):
        raise DirectorInputError("run_inputs.provenance must be an object")
    return director_authoring_spec, provenance


def _positive_int_field(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DirectorInputError(f"{field} must be a positive integer")
    return value


def _resolve_run_root(output_root: Path, run_id: Any) -> tuple[str, Path]:
    if run_id is None:
        run_id = (
            f"director_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:8]}"
        )
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise DirectorInputError(
            "run_id must be a safe 1..128 char [A-Za-z0-9][A-Za-z0-9_-]* token"
        )
    if run_id.lower() in _WINDOWS_RESERVED_NAMES:
        raise DirectorInputError("run_id must not be a Windows reserved device name")

    run_root = (output_root / run_id).resolve()
    if run_root == output_root or not _is_relative_to(run_root, output_root):
        raise DirectorInputError("run_id must resolve to a child of output_root")
    return run_id, run_root


def _track_frame_index(frame: Any, *, kind: str) -> int:
    if not isinstance(frame, dict):
        raise DirectorInputError(f"{kind} frame must be an object with frame_index")
    index = frame.get("frame_index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise DirectorInputError(f"{kind} frame_index must be an integer")
    return index


def _index_frames(
    frames: Any,
    frame_count: int,
    *,
    key: str,
    kind: str,
    required_payload: str,
) -> list[dict[str, Any]]:
    if not isinstance(frames, list):
        raise DirectorInputError(f"{key} must be an array")
    by_index: dict[int, dict[str, Any]] = {}
    for frame in frames:
        index = _track_frame_index(frame, kind=kind)
        if index in by_index:
            raise DirectorInputError(f"duplicate {kind} frame_index: {index}")
        by_index[index] = frame
        payload = frame.get(required_payload)
        if required_payload == "camera" and not isinstance(payload, dict):
            raise DirectorInputError("camera frame must include camera object")
        if required_payload == "object_transforms" and not isinstance(payload, list):
            raise DirectorInputError("object frame must include object_transforms array")

    expected = set(range(1, frame_count + 1))
    if set(by_index) != expected:
        raise DirectorInputError(f"{kind} frame_index values must exactly cover 1..frame_count")
    return [by_index[index] for index in range(1, frame_count + 1)]


def _indexed_track_frames(
    track: dict[str, Any],
    frame_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    camera_frames = _index_frames(
        track.get("camera_frames"),
        frame_count,
        key="camera_frames",
        kind="camera",
        required_payload="camera",
    )
    object_frames = _index_frames(
        track.get("object_frames"),
        frame_count,
        key="object_frames",
        kind="object",
        required_payload="object_transforms",
    )
    return camera_frames, object_frames


def _validate_director_resolution(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise DirectorInputError("resolution must be an object")
    width = _positive_int_field(value.get("width"), field="resolution.width")
    height = _positive_int_field(value.get("height"), field="resolution.height")
    if width > MAX_VIDEO_WIDTH:
        raise DirectorInputError(
            f"resolution.width must be <= {MAX_VIDEO_WIDTH} for Director video assembly"
        )
    if height > MAX_VIDEO_HEIGHT:
        raise DirectorInputError(
            f"resolution.height must be <= {MAX_VIDEO_HEIGHT} for Director video assembly"
        )
    if width % 2 or height % 2:
        raise DirectorInputError(
            "resolution width and height must be even for Director video assembly"
        )
    return {"width": width, "height": height}


def _validate_video_compatible_track_limits(frame_count: int, fps: int) -> None:
    if fps > MAX_VIDEO_FPS:
        raise DirectorInputError(f"fps must be <= {MAX_VIDEO_FPS} for Director video assembly")
    if frame_count > MAX_VIDEO_FRAME_COUNT:
        raise DirectorInputError(
            f"frame_count must be <= {MAX_VIDEO_FRAME_COUNT} for Director video assembly"
        )


async def _resolve_objects(call_native, object_ids: list[str], port: int | None):
    result = await call_native(
        "/director/object-states", "POST", {"object_ids": object_ids}, port=port
    )
    if not result.get("success"):
        raise DirectorInputError(f"object state resolution failed: {result.get('data')}")
    return result["data"]


def _frame_id(index: int) -> str:
    return f"frame_{index:04d}"


async def _capture_manifest_frames(
    manifest_frames: list[dict[str, Any]],
    *,
    run_id: str,
    run_root: Path,
    resolution: dict[str, int],
    display: dict[str, Any],
    logs_dir: Path,
    call_native,
    port: int | None,
    should_cancel,
) -> str:
    state = "complete"
    evidence_path = logs_dir / "frame_evidence.jsonl"
    for frame in manifest_frames:
        if should_cancel():
            return "cancelled"
        instruction = {
            "schema_version": SCHEMA_VERSION,
            "director_version": DIRECTOR_VERSION,
            "run_id": run_id,
            "frame_index": frame["frame_index"],
            "frame_id": frame["frame_id"],
            "run_root": str(run_root),
            "output_path": frame["output_path"],
            "resolution": resolution,
            "display": display,
            "camera": frame["camera"],
            "object_transforms": frame["object_transforms"],
        }
        result = await call_native("/director/frame-capture", "POST", instruction, port=port)
        evidence = (
            result.get("data")
            if isinstance(result.get("data"), dict)
            else {"error": result.get("data")}
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
            return "evidence_failed"
        if evidence.get("dirty_partial_state"):
            state = "unsafe_failed"
            break
        if not result.get("success"):
            state = "failed"
            break
        if not evidence["success"]:
            state = "failed"
            break
    return state


async def run_compiled_track(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    runtime: DirectorRuntimePaths | None = None,
    port: int | None = None,
    should_cancel=None,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise DirectorInputError("compiled track request must be an object")
    track = request.get("track")
    if not isinstance(track, dict):
        raise DirectorInputError("track must be an object")

    frame_count = _positive_int_field(track.get("frame_count"), field="frame_count")
    fps = _positive_int_field(track.get("fps"), field="fps")
    _validate_video_compatible_track_limits(frame_count, fps)
    resolution = _validate_director_resolution(request.get("resolution"))
    display = request.get("display") or {"mode": "Rendered"}
    if not isinstance(display, dict):
        raise DirectorInputError("display must be an object")
    camera_frames, object_frames = _indexed_track_frames(track, frame_count)
    compile_provenance = request.get("compile_provenance") or {}
    if not isinstance(compile_provenance, dict):
        raise DirectorInputError("compile_provenance must be an object")
    animated_object_ids = track.get("animated_object_ids", [])
    if not isinstance(animated_object_ids, list):
        raise DirectorInputError("animated_object_ids must be an array")
    transform_semantics = track.get("transform_semantics")
    if not isinstance(transform_semantics, str) or not transform_semantics:
        raise DirectorInputError("transform_semantics must be a non-empty string")

    run_inputs = request.get("run_inputs")
    prepared_run_inputs = None
    if run_inputs is not None:
        director_authoring_spec, provenance = _validate_run_inputs(run_inputs)
        prepared_run_inputs = _prepare_run_inputs(director_authoring_spec, provenance)

    runtime = runtime or _runtime_paths()
    output_root = resolve_output_root(request.get("output_root"), runtime)
    run_id, run_root = _resolve_run_root(output_root, request.get("run_id"))

    frames_dir = run_root / "frames"
    logs_dir = run_root / "logs"
    try:
        run_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise DirectorInputError(f"run_id already exists: {run_id}") from exc
    frames_dir.mkdir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    if prepared_run_inputs is not None:
        copied_spec, full_provenance = prepared_run_inputs
        _write_run_inputs(
            run_root,
            director_authoring_spec=copied_spec,
            provenance=full_provenance,
        )

    manifest_frames = []
    for index in range(1, frame_count + 1):
        frame_name = _frame_id(index)
        camera_frame = camera_frames[index - 1]
        object_frame = object_frames[index - 1]
        manifest_frames.append(
            {
                "frame_index": index,
                "frame_id": frame_name,
                "camera": camera_frame["camera"],
                "object_transforms": object_frame["object_transforms"],
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
        "frame_count": frame_count,
        "timeline": {
            "source": "compiled_track",
            "fps": fps,
            "frame_count": frame_count,
            "duration_seconds": frame_count / fps,
        },
        "motion": {
            "strategy": "compiled_track",
            "transform_semantics": transform_semantics,
            "animated_object_ids": animated_object_ids,
            "provenance": copy.deepcopy(compile_provenance),
        },
        "camera_plan": {"strategy": "compiled_track"},
        "resolution": resolution,
        "display": display,
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

    should_cancel = should_cancel or (lambda: False)
    state = await _capture_manifest_frames(
        manifest_frames,
        run_id=run_id,
        run_root=run_root,
        resolution=resolution,
        display=display,
        logs_dir=logs_dir,
        call_native=call_native,
        port=port,
        should_cancel=should_cancel,
    )
    summary = {
        "state": state,
        "run_id": run_id,
        "run_root": str(run_root),
        "updated_at": _utc_now(),
    }
    _atomic_write_json(run_root / "status.json", summary)
    return summary


async def run_director(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    runtime: DirectorRuntimePaths | None = None,
    port: int | None = None,
    should_cancel=None,
) -> dict[str, Any]:
    try:
        request, timeline_manifest = timeline.normalize_director_request(request)
    except timeline.TimelineError as ex:
        raise DirectorInputError(str(ex)) from ex

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

    frame_count = int(request["frame_count"])
    try:
        camera_planner.validate_camera_request(
            request,
            frame_count=frame_count,
            resolution=request["resolution"],
        )
    except camera_planner.CameraPlanError as ex:
        raise DirectorInputError(str(ex)) from ex

    object_data = await _resolve_objects(call_native, object_ids, port)
    objects = object_data["objects"]
    try:
        camera_plan = await camera_planner.resolve_camera_plan(
            request,
            frame_count=frame_count,
            resolution=request["resolution"],
            call_native=call_native,
            port=port,
        )
    except camera_planner.CameraPlanError as ex:
        raise DirectorInputError(str(ex)) from ex
    frame_cameras = camera_plan["frames"]
    plan_provenance = camera_plan.get("provenance", {})
    resolved_camera_keyframes = (
        plan_provenance.get("keyframes", [])
        if camera_plan.get("strategy") == "keyframes"
        else []
    )
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

    manifest_camera_plan = {
        "strategy": camera_plan["strategy"],
        "request_shape": plan_provenance.get("request_shape"),
        "aspect_authority": plan_provenance.get("aspect_authority"),
        "optics_authority": plan_provenance.get("optics_authority"),
    }
    if camera_plan["strategy"] == "curve_follow_target":
        manifest_camera_plan["provenance"] = {
            "curve_id": plan_provenance["curve_id"],
            "target": plan_provenance["target"],
            "up": plan_provenance["up"],
            "sampling": plan_provenance["sampling"],
            "curve_sampling": plan_provenance.get("curve_sampling", {}),
        }

    manifest_camera_keyframes = [
        {
            "frame_index": keyframe["frame_index"],
            "source": keyframe["source"],
        }
        for keyframe in resolved_camera_keyframes
    ]

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "director_version": DIRECTOR_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_root": str(output_root),
        "created_at": _utc_now(),
        "document_units": object_data.get("units"),
        "source_objects": objects,
        "frame_count": frame_count,
        "timeline": timeline_manifest,
        "motion": {
            "strategy": "radial_bbox_center",
            "parameters": motion_params,
            "warnings": motion_warnings,
        },
        "camera_plan": manifest_camera_plan,
        "camera_keyframes": manifest_camera_keyframes,
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


# ---------------------------------------------------------------------------
# Replay (Task 4) — thin resolver over native /director/replay routes
# ---------------------------------------------------------------------------

_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _resolve_track(arguments: dict) -> dict:
    inline = arguments.get("track")
    path = arguments.get("track_path")
    if (inline is None) == (path is None):  # both or neither
        raise DirectorInputError("invalid_track_input: provide exactly one of track or track_path")
    if inline is not None:
        if not isinstance(inline, dict):
            raise DirectorInputError("invalid_track_input: track must be an object")
        return inline
    p = Path(path)
    if not p.is_file():
        raise DirectorInputError(f"track_not_found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DirectorInputError(f"track_read_failed: {exc}") from exc


def _resolve_session_id(arguments: dict) -> str:
    # Absent (key missing or None) -> generate. Present -> must be a valid string.
    if arguments.get("replay_session_id") is None:
        return uuid.uuid4().hex
    sid = arguments["replay_session_id"]
    if not isinstance(sid, str) or not _SESSION_RE.match(sid):
        raise DirectorInputError("invalid_session_id: must be a 1..128 char [A-Za-z0-9._-] token")
    return sid


async def run_replay(arguments: dict, *, call_native=call_rhino, port=None) -> dict:
    track = _resolve_track(arguments)
    sid = _resolve_session_id(arguments)
    req = {"replay_session_id": sid, "track": track,
           "restore_on_finish": arguments.get("restore_on_finish", True),
           "loop": arguments.get("loop", False)}
    if arguments.get("fps") is not None:
        req["fps"] = arguments["fps"]
    result = await call_native("/director/replay", "POST", req, port=port)
    if not result.get("success", False):
        data = result.get("data", {})
        raise DirectorError(f"{data.get('code', 'director_error')}: {data.get('message', '')}")
    return result["data"]


async def cancel_replay(arguments: dict, *, call_native=call_rhino, port=None) -> dict:
    sid = arguments.get("replay_session_id")
    if not isinstance(sid, str) or not _SESSION_RE.match(sid):
        raise DirectorInputError("invalid_session_id: must be a 1..128 char [A-Za-z0-9._-] token")
    result = await call_native("/director/replay/cancel", "POST", {"replay_session_id": sid}, port=port)
    if not result.get("success", False):
        data = result.get("data", {})
        raise DirectorError(f"{data.get('code', 'director_error')}: {data.get('message', '')}")
    return result["data"]
