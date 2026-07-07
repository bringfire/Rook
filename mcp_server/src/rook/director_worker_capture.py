"""Director v3 Slice 4A: multi-pass worker capture orchestrator."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .director_take_package import canonical_json_text, utc_now_iso
from .director_video import DirectorVideoError, _default_output_root, _png_size
from .director_worker_common import open_package_document
from .director_worker_play import DirectorWorkerPlayError, _load_play_package

KNOWN_NATIVE_REASONS = {
    "wrong_document",
    "track_invalid",
    "track_objects_missing",
    "worker_scene_not_pristine",
    "playback_drift_detected",
    "invalid_input",
    "output_policy_violation",
    "run_root_exists",
    "display_mode_missing",
    "display_mode_mismatch",
    "capture_failed",
}

_PASS_ID_RE = re.compile(r"^[a-z0-9_-]+$")


class DirectorWorkerCaptureError(Exception):
    def __init__(self, code: str, message: str,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.extra = dict(extra or {})

    def to_data(self) -> dict[str, Any]:
        data = {"code": self.code, "message": str(self)}
        data.update(self.extra)
        return data


def _validate_resolution(arguments: dict[str, Any]) -> tuple[int, int]:
    resolution = arguments.get("resolution")
    if not isinstance(resolution, dict):
        raise DirectorWorkerCaptureError(
            "invalid_input", "resolution must be an object")

    values: list[int] = []
    for key in ("width", "height"):
        value = resolution.get(key)
        if (not isinstance(value, int) or isinstance(value, bool)
                or value <= 0 or value % 2):
            raise DirectorWorkerCaptureError(
                "invalid_input",
                f"resolution.{key} must be a positive even integer")
        values.append(value)
    return values[0], values[1]


def _validate_passes(arguments: dict[str, Any]) -> list[dict[str, str]]:
    passes = arguments.get("passes")
    if not isinstance(passes, list) or not passes:
        raise DirectorWorkerCaptureError(
            "invalid_input", "passes must be a non-empty list")

    seen: set[str] = set()
    validated: list[dict[str, str]] = []
    for index, item in enumerate(passes):
        if not isinstance(item, dict):
            raise DirectorWorkerCaptureError(
                "invalid_input", f"passes[{index}] must be an object")
        pass_type = item.get("type")
        if pass_type != "display_mode":
            raise DirectorWorkerCaptureError(
                "unsupported_pass_type",
                f"passes[{index}].type {pass_type!r} is not supported in 4A")

        pass_id = item.get("pass_id")
        if not isinstance(pass_id, str) or not _PASS_ID_RE.fullmatch(pass_id):
            raise DirectorWorkerCaptureError(
                "invalid_input",
                f"passes[{index}].pass_id must match ^[a-z0-9_-]+$")
        if pass_id in seen:
            raise DirectorWorkerCaptureError(
                "invalid_input", f"duplicate pass_id: {pass_id}")
        seen.add(pass_id)

        display_mode = item.get("display_mode")
        if (not isinstance(display_mode, str) or not display_mode.strip()
                or display_mode.strip().lower() == "current"):
            raise DirectorWorkerCaptureError(
                "invalid_input",
                f"passes[{index}].display_mode must name a concrete display mode")
        validated.append({"pass_id": pass_id, "display_mode": display_mode})
    return validated


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.parent / f"{path.name}.staging"
    staging.write_text(canonical_json_text(payload), encoding="utf-8")
    os.replace(staging, path)


def _write_run_manifest(run_root: Path, *, run_id: str, frame_count: int,
                        width: int, height: int, fps: float) -> None:
    _write_json_atomic(run_root / "manifest.json", {
        "schema_version": 1,
        "director_version": "slice1",
        "run_id": run_id,
        "frame_count": frame_count,
        "resolution": {"width": width, "height": height},
        "timeline": {"fps": fps, "frame_count": frame_count},
        "frames": [
            {"frame_index": i, "file": f"frames/frame_{i:04d}.png"}
            for i in range(1, frame_count + 1)
        ],
    })


def _write_run_status(run_root: Path, *, state: str, now_fn,
                      detail: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"state": state, "written_at_utc": now_fn()}
    payload.update(detail or {})
    _write_json_atomic(run_root / "status.json", payload)


def _verify_frames(frames_dir: Path, frame_count: int,
                   width: int, height: int) -> None:
    for frame_index in range(1, frame_count + 1):
        frame = frames_dir / f"frame_{frame_index:04d}.png"
        if not frame.is_file() or frame.stat().st_size == 0:
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete",
                f"missing or empty frame: {frame.name}")
        try:
            observed = _png_size(frame)
        except DirectorVideoError as exc:
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete",
                f"unparsable PNG {frame.name}: {exc}") from exc
        if observed != (width, height):
            raise DirectorWorkerCaptureError(
                "pass_output_incomplete",
                f"{frame.name} is {observed[0]}x{observed[1]}, "
                f"expected {width}x{height}")


def _capture_ms_summary(per_frame: list[float]) -> dict[str, float]:
    if not per_frame:
        return {"total": 0.0, "mean": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(per_frame)
    total = sum(per_frame)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "total": total,
        "mean": total / len(per_frame),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


async def _call_worker_play_capture(call_native, request: dict[str, Any],
                                    port: int | None) -> dict[str, Any]:
    envelope = await call_native(
        "/director/worker-play", "POST", request, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        reason = detail.get("reason") if isinstance(detail, dict) else None
        if reason in KNOWN_NATIVE_REASONS:
            raise DirectorWorkerCaptureError(reason, str(detail))
        raise DirectorWorkerCaptureError(
            "capture_route_failed",
            f"/director/worker-play failed: {detail}")

    data = envelope.get("data")
    if not isinstance(data, dict):
        raise DirectorWorkerCaptureError(
            "capture_route_failed",
            "/director/worker-play returned no data object")
    return data


def _append_capture_pass(root: Path, status: dict[str, Any],
                         entry: dict[str, Any], now_fn) -> dict[str, Any]:
    evidence = dict(status.get("evidence") or {})
    capture_passes = list(evidence.get("capture_passes") or [])
    entry = dict(entry)
    entry["pass_index"] = len(capture_passes)
    capture_passes.append(entry)
    evidence["capture_passes"] = capture_passes

    next_status = dict(status)
    next_status["heartbeat_utc"] = now_fn()
    next_status["evidence"] = evidence
    (root / "status.json").write_text(
        canonical_json_text(next_status), encoding="utf-8")
    return next_status


def _validate_capture_timing(raw_per_frame: Any,
                             frame_count: int) -> list[float]:
    if (not isinstance(raw_per_frame, list)
            or len(raw_per_frame) != frame_count
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       for v in raw_per_frame)):
        raise DirectorWorkerCaptureError(
            "pass_output_incomplete",
            "native capture timing is not a numeric array of length "
            f"{frame_count}: {type(raw_per_frame).__name__}")
    return [float(v) for v in raw_per_frame]


async def capture_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None,
                       now_fn=utc_now_iso) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DirectorWorkerCaptureError(
            "invalid_input", "capture request must be an object")

    passes = _validate_passes(arguments)
    width, height = _validate_resolution(arguments)

    try:
        pkg = _load_play_package(arguments.get("package_root"))
    except DirectorWorkerPlayError as exc:
        raise DirectorWorkerCaptureError(exc.code, str(exc)) from exc

    root: Path = pkg["root"]
    status = pkg["status"]
    track = pkg["track"]
    take_id = status.get("take_id")
    if not isinstance(take_id, str) or not take_id.strip():
        raise DirectorWorkerCaptureError(
            "package_invalid", "package status.json has no take_id")

    fps = track.get("fps")
    frame_count = track.get("frame_count")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        raise DirectorWorkerCaptureError(
            "package_invalid", "track.json has no valid fps")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count <= 0:
        raise DirectorWorkerCaptureError(
            "package_invalid", "track.json has no valid frame_count")

    output_root = _default_output_root() / "takes" / take_id
    completed: list[dict[str, Any]] = []

    for pass_spec in passes:
        pass_id = pass_spec["pass_id"]
        display_mode = pass_spec["display_mode"]
        run_root = output_root / pass_id
        frames_dir = run_root / "frames"

        def _fail(code: str, message: str, *, mark_failed: bool) -> None:
            if mark_failed and run_root.is_dir():
                _write_run_status(run_root, state="failed", now_fn=now_fn,
                                  detail={"reason": code, "message": message})
            status_entry = {
                "pass_id": pass_id,
                "display_mode": display_mode,
                "captured_at_utc": now_fn(),
                "run_root": str(run_root),
                "outcome": "failed",
                "reason": code,
            }
            _append_capture_pass(root, status, status_entry, now_fn)
            raise DirectorWorkerCaptureError(code, message, extra={
                "failed_pass": pass_id,
                "completed_passes": [entry["pass_id"] for entry in completed],
            })

        if run_root.exists():
            _fail("run_root_exists", f"run root already exists: {run_root}",
                  mark_failed=False)

        try:
            await open_package_document(
                call_native, root, root / "prepared.3dm", port=port,
                error_cls=DirectorWorkerCaptureError, mode="require_fresh")
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=False)

        request = {
            "expectedDocumentPath": str(root / "prepared.3dm"),
            "trackPath": str(root / "track.json"),
            "capture": {
                "runRoot": str(run_root),
                "framesDir": str(frames_dir),
                "displayMode": display_mode,
                "width": width,
                "height": height,
            },
        }

        try:
            play_data = await _call_worker_play_capture(call_native, request, port)
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=True)

        capture_data = play_data.get("capture") or {}
        frames_written = capture_data.get("framesWritten")
        raw_per_frame = (capture_data.get("timing") or {}).get("capturePerFrameMs")
        try:
            if frames_written != frame_count:
                raise DirectorWorkerCaptureError(
                    "pass_output_incomplete",
                    f"native reported {frames_written} frames, expected {frame_count}")
            per_frame = _validate_capture_timing(raw_per_frame, frame_count)
            _verify_frames(frames_dir, frame_count, width, height)
        except DirectorWorkerCaptureError as exc:
            _fail(exc.code, str(exc), mark_failed=True)

        run_id = f"{take_id}-{pass_id}"
        _write_run_manifest(
            run_root, run_id=run_id, frame_count=frame_count,
            width=width, height=height, fps=float(fps))
        capture_ms = _capture_ms_summary(per_frame)
        _write_run_status(run_root, state="complete", now_fn=now_fn, detail={
            "run_id": run_id,
            "frame_count": frame_count,
            "capture_ms": capture_ms,
            "drift": play_data.get("drift"),
        })

        pass_result = {
            "pass_id": pass_id,
            "display_mode": display_mode,
            "run_root": str(run_root),
            "frames_written": frame_count,
            "backend": capture_data.get("backend"),
            "capture_ms": capture_ms,
            "drift": play_data.get("drift"),
        }
        status = _append_capture_pass(root, status, {
            "pass_id": pass_id,
            "display_mode": display_mode,
            "captured_at_utc": now_fn(),
            "run_root": str(run_root),
            "frames_written": frame_count,
            "backend": capture_data.get("backend"),
            "outcome": "complete",
            "capture_ms": capture_ms,
            "drift": play_data.get("drift"),
        }, now_fn)
        completed.append(pass_result)

    return {
        "package_root": str(root),
        "take_id": take_id,
        "output_root": str(output_root),
        "passes": completed,
    }
