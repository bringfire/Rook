from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

SCHEMA_VERSION = 1
VIDEO_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_NAME = "preview.mp4"
RELATIVE_OUTPUT_PATH = "videos/preview.mp4"
RELATIVE_INPUT_PATTERN = "frames/frame_%04d.png"
NATIVE_INPUT_PATTERN = "frame_%04d.png"
MAX_VIDEO_FPS = 240.0
MIN_VIDEO_FPS = 1.0
MAX_VIDEO_FRAME_COUNT = 5000
MAX_VIDEO_WIDTH = 8192
MAX_VIDEO_HEIGHT = 8192


class DirectorVideoError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_output_root() -> Path:
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorVideoError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DirectorVideoError(f"{path.name} must contain a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if (
        len(header) < 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise DirectorVideoError(f"invalid PNG header: {path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def _positive_int(value: Any, *, maximum: int | None = None) -> int | None:
    if type(value) is not int:
        return None
    if value <= 0:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def _finite_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _failure_manifest(
    *,
    run_id: str,
    output_path: Path,
    error_code: str,
    message: str,
    started_at: str,
    evidence: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    return {
        "schema_version": VIDEO_SCHEMA_VERSION,
        "state": "failed",
        "run_id": run_id,
        "backend": "media_foundation",
        "platform": "windows",
        "format": "mp4",
        "codec": "h264",
        "container": "mp4",
        "fps": context.get("fps"),
        "fps_source": context.get("fps_source"),
        "frame_count": context.get("frame_count"),
        "width": context.get("width"),
        "height": context.get("height"),
        "input_pattern": context.get("input_pattern", RELATIVE_INPUT_PATTERN),
        "output_path": RELATIVE_OUTPUT_PATH,
        "bytes": 0,
        "overwrote_existing": False,
        "output_current": False,
        "preserved_previous_output": output_path.exists(),
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": {"code": error_code, "message": message},
        "evidence": evidence or {},
    }


def _write_failure(
    *,
    run_id: str,
    run_root: Path,
    output_path: Path,
    error_code: str,
    message: str,
    started_at: str,
    evidence: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _failure_manifest(
        run_id=run_id,
        output_path=output_path,
        error_code=error_code,
        message=message,
        started_at=started_at,
        evidence=evidence,
        context=context,
    )
    _atomic_write_json(run_root / "video_manifest.json", manifest)
    return manifest


def _resolve_fps(
    request: dict[str, Any], manifest: dict[str, Any]
) -> tuple[float, str] | tuple[None, None]:
    if request.get("fps") is not None:
        fps = _finite_number(request["fps"])
        if fps is None:
            return None, None
        if MIN_VIDEO_FPS <= fps <= MAX_VIDEO_FPS:
            return fps, "explicit_override"
        return None, None

    timeline = manifest.get("timeline")
    if not isinstance(timeline, dict):
        return None, None
    fps = _finite_number(timeline.get("fps"))
    if fps is None:
        return None, None
    if MIN_VIDEO_FPS <= fps <= MAX_VIDEO_FPS:
        return fps, "timeline"
    return None, None


def _failure_context(
    *,
    fps: float | None = None,
    fps_source: str | None = None,
    frame_count: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    return {
        "fps": fps,
        "fps_source": fps_source,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "input_pattern": RELATIVE_INPUT_PATTERN,
    }


def _context_from_manifest(
    request: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], int | None, int | None, int | None]:
    resolution = manifest.get("resolution")
    resolution = resolution if isinstance(resolution, dict) else {}
    frame_count = _positive_int(
        manifest.get("frame_count"), maximum=MAX_VIDEO_FRAME_COUNT
    )
    width = _positive_int(resolution.get("width"), maximum=MAX_VIDEO_WIDTH)
    height = _positive_int(resolution.get("height"), maximum=MAX_VIDEO_HEIGHT)
    fps, fps_source = _resolve_fps(request, manifest)
    context = _failure_context(
        fps=fps,
        fps_source=fps_source,
        frame_count=frame_count,
        width=width,
        height=height,
    )
    return context, frame_count, width, height


def _validate_video_child_paths(
    run_root: Path,
    frames_dir: Path,
    output_path: Path,
) -> tuple[str, str] | None:
    run_root_resolved = run_root.resolve()
    expected_frames_dir = run_root_resolved / "frames"
    if frames_dir.resolve() != expected_frames_dir:
        return (
            "frames_dir_policy_violation",
            "frames_dir must resolve to run_root/frames",
        )

    videos_dir = run_root_resolved / "videos"
    output_resolved = output_path.resolve(strict=False)
    if output_resolved == videos_dir or not _is_relative_to(output_resolved, videos_dir):
        return (
            "output_policy_violation",
            "output_path must resolve under run_root/videos and name a file",
        )
    return None


def _validate_manifest_identity(manifest: dict[str, Any]) -> str | None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return "manifest schema_version must be 1"
    if manifest.get("director_version") != "slice1":
        return "manifest director_version must be slice1"
    if "frame_count" not in manifest:
        return "manifest frame_count is required"
    if not isinstance(manifest.get("resolution"), dict):
        return "manifest resolution is required"
    if not isinstance(manifest.get("frames"), list):
        return "manifest frames must be an array"
    if not isinstance(manifest.get("timeline"), dict):
        return "manifest timeline is required"
    return None


async def assemble_director_video(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    director_output_root: Path | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    allowed_root = (director_output_root or _default_output_root()).expanduser().resolve()
    run_root = Path(str(request.get("run_root", ""))).expanduser().resolve()
    output_path = run_root / "videos" / DEFAULT_OUTPUT_NAME
    run_id = run_root.name or ""

    if not _is_relative_to(run_root, allowed_root):
        return _failure_manifest(
            run_id=run_id,
            output_path=output_path,
            error_code="run_root_policy_violation",
            message="run_root must resolve under the configured Director output root",
            started_at=started_at,
        )

    if not run_root.is_dir():
        return _failure_manifest(
            run_id=run_id,
            output_path=output_path,
            error_code="missing_run_metadata",
            message="run_root must be an existing Director run directory",
            started_at=started_at,
        )

    try:
        manifest = _read_json(run_root / "manifest.json")
    except (OSError, json.JSONDecodeError, DirectorVideoError) as ex:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="missing_run_metadata",
            message=str(ex),
            started_at=started_at,
        )

    run_id = str(manifest.get("run_id") or run_id)
    context, frame_count, width, height = _context_from_manifest(request, manifest)
    manifest_identity_error = _validate_manifest_identity(manifest)
    if manifest_identity_error is not None:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="invalid_run_manifest",
            message=manifest_identity_error,
            started_at=started_at,
            context=context,
        )

    try:
        status = _read_json(run_root / "status.json")
    except (OSError, json.JSONDecodeError, DirectorVideoError) as ex:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="missing_run_metadata",
            message=str(ex),
            started_at=started_at,
            context=context,
        )

    if status.get("state") != "complete":
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="frame_run_incomplete",
            message="Director frame run must be complete before video assembly",
            started_at=started_at,
            context=context,
        )

    fps = context["fps"]
    fps_source = context["fps_source"]
    if fps is None or fps_source is None:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="fps_missing",
            message="timeline fps or explicit fps override is required",
            started_at=started_at,
            context=context,
        )

    if frame_count is None:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="frame_count_mismatch",
            message="manifest frame_count must be a positive integer",
            started_at=started_at,
            context=context,
        )

    frames = manifest.get("frames")
    if not isinstance(frames, list) or len(frames) != frame_count:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="frame_count_mismatch",
            message="manifest frame_count must match frames length",
            started_at=started_at,
            context=context,
        )

    if width is None or height is None or width % 2 or height % 2:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="unsupported_dimensions",
            message="v1 H.264 MP4 assembly requires positive even dimensions",
            started_at=started_at,
            context=context,
        )

    frames_dir = run_root / "frames"
    child_path_error = _validate_video_child_paths(run_root, frames_dir, output_path)
    if child_path_error is not None:
        error_code, message = child_path_error
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code=error_code,
            message=message,
            started_at=started_at,
            context=context,
        )

    for index in range(1, frame_count + 1):
        frame_path = frames_dir / f"frame_{index:04d}.png"
        if not frame_path.is_file():
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="missing_frame",
                message=f"missing frame file: {frame_path}",
                started_at=started_at,
                context=context,
            )
        try:
            frame_width, frame_height = _png_size(frame_path)
        except (OSError, DirectorVideoError) as ex:
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="unsupported_frame_format",
                message=str(ex),
                started_at=started_at,
                context=context,
            )
        if (frame_width, frame_height) != (width, height):
            return _write_failure(
                run_id=run_id,
                run_root=run_root,
                output_path=output_path,
                error_code="dimension_mismatch",
                message=(
                    f"{frame_path.name} is {frame_width}x{frame_height}, "
                    f"expected {width}x{height}"
                ),
                started_at=started_at,
                context=context,
            )

    native_request = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "frames_dir": str(frames_dir.resolve()),
        "input_pattern": NATIVE_INPUT_PATTERN,
        "start_number": 1,
        "frame_count": frame_count,
        "fps": fps,
        "fps_source": fps_source,
        "width": width,
        "height": height,
        "output_path": str(output_path.resolve()),
        "codec": "h264",
        "container": "mp4",
    }

    native = await call_native(
        "/director/video-assemble", "POST", native_request, port=port
    )
    native_data = native.get("data") if isinstance(native.get("data"), dict) else {}
    if not native.get("success"):
        error = native_data.get("error")
        error = error if isinstance(error, dict) else {}
        evidence = native_data.get("evidence")
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code=str(error.get("code") or "backend_encode_failed"),
            message=str(
                error.get("message") or native_data or "native video assembly failed"
            ),
            started_at=started_at,
            evidence=evidence if isinstance(evidence, dict) else native_data,
            context=context,
        )

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        return _write_failure(
            run_id=run_id,
            run_root=run_root,
            output_path=output_path,
            error_code="missing_output",
            message="native video assembly reported success but preview output is missing or empty",
            started_at=started_at,
            evidence=native_data.get("evidence") or {},
            context=context,
        )

    output_bytes = native_data.get("bytes")
    if output_bytes is None:
        output_bytes = output_path.stat().st_size
    result = {
        "schema_version": VIDEO_SCHEMA_VERSION,
        "state": "complete",
        "run_id": run_id,
        "backend": native_data.get("backend", "media_foundation"),
        "platform": native_data.get("platform", "windows"),
        "format": "mp4",
        "codec": "h264",
        "container": "mp4",
        "fps": fps,
        "fps_source": fps_source,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "input_pattern": RELATIVE_INPUT_PATTERN,
        "output_path": RELATIVE_OUTPUT_PATH,
        "bytes": int(output_bytes),
        "overwrote_existing": bool(native_data.get("overwrote_existing")),
        "output_current": True,
        "preserved_previous_output": False,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": None,
        "evidence": native_data.get("evidence") or {},
    }
    _atomic_write_json(run_root / "video_manifest.json", result)
    return result
