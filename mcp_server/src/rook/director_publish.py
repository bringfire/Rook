from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

PUBLISH_SCHEMA_VERSION = 1
PROFILE_NAME = "director_publish_standard_v1"
RELATIVE_SOURCE_VIDEO = "videos/preview.mp4"
SIDECAR_POLICY = "existing_generated_video_pipeline"
ALLOWED_PRESETS: dict[tuple[int, int], str] = {
    (1280, 720): "hd_720",
    (1920, 1080): "full_hd_1080",
    (3840, 2160): "uhd_4k",
    (7680, 4320): "uhd_8k",
}
ALLOWED_FPS = {24, 30}


class DirectorPublishError(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolved_source_path(run_root: Path) -> Path | None:
    source_path = run_root / RELATIVE_SOURCE_VIDEO
    resolved = source_path.resolve()
    videos_root = (run_root / "videos").resolve()
    if not _is_relative_to(resolved, run_root) or not _is_relative_to(
        resolved, videos_root
    ):
        return None
    return resolved


def _default_output_root() -> Path:
    env_root = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise DirectorPublishError(
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set"
        )
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DirectorPublishError(f"{path.name} must contain a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _base_publish_manifest(
    *,
    state: str,
    run_id: str,
    run_root: Path,
    started_at: str,
    artifact_id: str | None = None,
    prior_artifact_id: str | None = None,
    profile: str | None = None,
    preset: str | None = None,
    source_sha256: str | None = None,
    source_byte_size: int | None = None,
    video_manifest_hash: str | None = None,
    frame_manifest_hash: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "state": state,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "prior_artifact_id": prior_artifact_id,
        "profile": profile,
        "preset": preset,
        "run_root": str(run_root),
        "source_path": str((run_root / RELATIVE_SOURCE_VIDEO).resolve()),
        "source_video": RELATIVE_SOURCE_VIDEO,
        "source_sha256": source_sha256,
        "source_byte_size": source_byte_size,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
        "sidecar_policy": SIDECAR_POLICY,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "error": error,
    }


def _failure(
    *,
    run_id: str,
    run_root: Path,
    started_at: str,
    code: str,
    message: str,
    managed_subcode: str | None = None,
    prior_artifact_id: str | None = None,
    profile: str | None = None,
    preset: str | None = None,
    source_sha256: str | None = None,
    source_byte_size: int | None = None,
    video_manifest_hash: str | None = None,
    frame_manifest_hash: str | None = None,
    write_manifest: bool = True,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if managed_subcode:
        error["managed_subcode"] = managed_subcode
    manifest = _base_publish_manifest(
        state="failed",
        run_id=run_id,
        run_root=run_root,
        started_at=started_at,
        prior_artifact_id=prior_artifact_id,
        profile=profile,
        preset=preset,
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        error=error,
    )
    if write_manifest:
        _atomic_write_json(run_root / "publish_manifest.json", manifest)
    return manifest


def _positive_int(value: Any) -> int | None:
    if type(value) is not int or value <= 0:
        return None
    return value


def _integer_fps(value: Any) -> int | None:
    if type(value) is int and value > 0:
        return value
    if type(value) is float and value.is_integer() and value > 0:
        return int(value)
    return None


def _timeline_fps(manifest: dict[str, Any]) -> int | None:
    timeline = manifest.get("timeline")
    if not isinstance(timeline, dict):
        return None
    return _integer_fps(timeline.get("fps"))


def _validate_manifest_pair(
    manifest: dict[str, Any],
    video_manifest: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    resolution = manifest.get("resolution")
    if not isinstance(resolution, dict):
        return "manifest resolution is required", None
    width = _positive_int(resolution.get("width"))
    height = _positive_int(resolution.get("height"))
    frame_count = _positive_int(manifest.get("frame_count"))
    fps = _timeline_fps(manifest)
    if width is None or height is None or frame_count is None or fps is None:
        return (
            "manifest must contain positive resolution, frame_count, and timeline fps",
            None,
        )

    video_width = _positive_int(video_manifest.get("width"))
    video_height = _positive_int(video_manifest.get("height"))
    video_frame_count = _positive_int(video_manifest.get("frame_count"))
    video_fps = _integer_fps(video_manifest.get("fps"))
    if (
        video_width != width
        or video_height != height
        or video_frame_count != frame_count
        or video_fps != fps
    ):
        return (
            "manifest.json and video_manifest.json disagree on frame count, "
            "resolution, or fps",
            None,
        )
    return None, {
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
    }


def _validate_profile(
    video_manifest: dict[str, Any],
    facts: dict[str, Any],
) -> tuple[str | None, str | None]:
    required = ("format", "container", "codec")
    for field in required:
        if not isinstance(video_manifest.get(field), str):
            return "video_manifest_invalid", f"video_manifest.{field} is required"

    if (
        video_manifest["format"] != "mp4"
        or video_manifest["container"] != "mp4"
        or video_manifest["codec"] != "h264"
    ):
        return "unsupported_video_profile", _unsupported_profile_message()

    preset = ALLOWED_PRESETS.get((facts["width"], facts["height"]))
    if preset is None or facts["fps"] not in ALLOWED_FPS:
        return "unsupported_video_profile", _unsupported_profile_message()
    return None, preset


def _unsupported_profile_message() -> str:
    return (
        "Director publish supports director_publish_standard_v1: "
        "1280x720, 1920x1080, 3840x2160, or 7680x4320 MP4/H.264 "
        "at supported FPS values."
    )


def _camera_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    plan = manifest.get("camera_plan")
    plan = plan if isinstance(plan, dict) else {}
    strategy = str(plan.get("strategy") or "")
    if strategy == "curve_follow_target":
        provenance = plan.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        camera = {
            "strategy": "curve_follow_target",
            "curve_id": provenance.get("curve_id"),
            "target": provenance.get("target"),
            "up": provenance.get("up"),
            "sampling": provenance.get("sampling"),
        }
        return {"camera_strategy": strategy, "camera": camera}
    if strategy == "keyframes":
        keyframes = manifest.get("camera_keyframes")
        keyframes = keyframes if isinstance(keyframes, list) else []
        sources = []
        for keyframe in keyframes:
            if not isinstance(keyframe, dict):
                continue
            source = keyframe.get("source")
            source = source if isinstance(source, dict) else {}
            sources.append(
                {
                    "kind": source.get("kind"),
                    "name": source.get("name"),
                }
            )
        return {
            "camera_strategy": strategy,
            "camera": {
                "strategy": "keyframes",
                "keyframe_count": len(keyframes),
                "sources": sources,
            },
        }
    return {"camera_strategy": strategy, "camera": {"strategy": strategy}}


def _metadata_director(
    *,
    run_id: str,
    manifest: dict[str, Any],
    facts: dict[str, Any],
    preset: str,
    video_manifest_hash: str,
    frame_manifest_hash: str,
) -> dict[str, Any]:
    timeline = manifest.get("timeline")
    timeline = timeline if isinstance(timeline, dict) else {}
    camera = _camera_metadata(manifest)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
        "camera_strategy": camera["camera_strategy"],
        "camera": camera["camera"],
        "timeline": {
            "fps": facts["fps"],
            "duration_seconds": timeline.get("duration_seconds"),
            "frame_count": facts["frame_count"],
        },
        "resolution": {
            "width": facts["width"],
            "height": facts["height"],
        },
    }


def _prior_publish_artifact_id(
    publish_manifest_path: Path,
    *,
    source_sha256: str,
    source_byte_size: int,
    video_manifest_hash: str,
    frame_manifest_hash: str,
    preset: str,
) -> tuple[str | None, str | None]:
    if not publish_manifest_path.exists():
        return None, None
    try:
        previous = _read_json(publish_manifest_path)
    except (OSError, json.JSONDecodeError, DirectorPublishError):
        return None, "publish_manifest_invalid"
    if previous.get("state") != "complete":
        return None, None

    artifact_id = previous.get("artifact_id")
    try:
        uuid.UUID(str(artifact_id))
    except (TypeError, ValueError):
        return None, "publish_manifest_invalid"

    expected = {
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "source_sha256": source_sha256,
        "source_byte_size": source_byte_size,
        "video_manifest_hash": video_manifest_hash,
        "frame_manifest_hash": frame_manifest_hash,
    }
    for key, value in expected.items():
        if previous.get(key) != value:
            return None, "publish_facts_changed"
    return str(artifact_id), None


async def publish_director_video(
    arguments: dict[str, Any],
    *,
    call_managed=call_rhino,
    director_output_root: Path | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    allowed_root = (director_output_root or _default_output_root()).expanduser().resolve()
    run_root = Path(str(arguments.get("run_root", ""))).expanduser().resolve()
    run_id = run_root.name or ""
    if not _is_relative_to(run_root, allowed_root):
        return {
            "schema_version": PUBLISH_SCHEMA_VERSION,
            "state": "failed",
            "run_id": run_id,
            "error": {
                "code": "run_root_policy_violation",
                "message": "run_root must resolve under the configured Director output root",
            },
        }
    if not run_root.is_dir():
        return {
            "schema_version": PUBLISH_SCHEMA_VERSION,
            "state": "failed",
            "run_id": run_id,
            "error": {
                "code": "missing_run_metadata",
                "message": "run_root must be an existing Director run directory",
            },
        }

    try:
        status = _read_json(run_root / "status.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="run_not_complete",
            message=str(ex),
        )
    if status.get("state") != "complete":
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="run_not_complete",
            message="Director frame run must be complete before publish",
        )

    try:
        manifest = _read_json(run_root / "manifest.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="missing_run_metadata",
            message=str(ex),
        )
    run_id = str(manifest.get("run_id") or run_id)

    try:
        video_manifest = _read_json(run_root / "video_manifest.json")
    except (OSError, json.JSONDecodeError, DirectorPublishError) as ex:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_not_assembled",
            message=str(ex),
        )
    if video_manifest.get("state") != "complete":
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_not_assembled",
            message="Director video must be assembled before publish",
        )
    if video_manifest.get("output_current") is not True:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_not_current",
            message="Director preview is stale or not current",
        )
    if video_manifest.get("output_path") != RELATIVE_SOURCE_VIDEO:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_manifest_invalid",
            message="video_manifest output_path must be videos/preview.mp4",
        )

    mismatch, facts = _validate_manifest_pair(manifest, video_manifest)
    if mismatch is not None or facts is None:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_manifest_invalid",
            message=mismatch or "invalid manifest facts",
        )

    profile_error, preset_or_message = _validate_profile(video_manifest, facts)
    if profile_error is not None or preset_or_message is None:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code=profile_error or "video_manifest_invalid",
            message=preset_or_message or "unsupported video profile",
        )
    preset = preset_or_message

    source_path = _resolved_source_path(run_root)
    if source_path is None:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="source_path_invalid",
            message="videos/preview.mp4 must resolve under the Director run videos directory",
            profile=PROFILE_NAME,
            preset=preset,
        )
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="video_not_assembled",
            message="videos/preview.mp4 is missing or empty",
            profile=PROFILE_NAME,
            preset=preset,
        )

    source_sha256 = _sha256_file(source_path)
    source_byte_size = source_path.stat().st_size
    video_manifest_hash = _sha256_file(run_root / "video_manifest.json")
    frame_manifest_hash = _sha256_file(run_root / "manifest.json")

    prior_artifact_id, prior_error = _prior_publish_artifact_id(
        run_root / "publish_manifest.json",
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        preset=preset,
    )
    if prior_error is not None:
        message = (
            "publish_manifest.json is invalid"
            if prior_error == "publish_manifest_invalid"
            else "publish facts changed from prior successful publish"
        )
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code=prior_error,
            message=message,
            profile=PROFILE_NAME,
            preset=preset,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            video_manifest_hash=video_manifest_hash,
            frame_manifest_hash=frame_manifest_hash,
            write_manifest=False,
        )

    metadata_director = _metadata_director(
        run_id=run_id,
        manifest=manifest,
        facts=facts,
        preset=preset,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
    )
    managed_request: dict[str, Any] = {
        "run_id": run_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source": {
            "run_root": str(run_root),
            "relative_path": RELATIVE_SOURCE_VIDEO,
            "absolute_path": str(source_path),
            "byte_size": source_byte_size,
            "sha256": source_sha256,
        },
        "facts": {
            "container": "mp4",
            "format": "mp4",
            "codec": "h264",
            "width": facts["width"],
            "height": facts["height"],
            "fps": facts["fps"],
            "frame_count": facts["frame_count"],
        },
        "hashes": {
            "source_video_sha256": source_sha256,
            "video_manifest_sha256": video_manifest_hash,
            "frame_manifest_sha256": frame_manifest_hash,
        },
        "metadata": {"director": metadata_director},
        "sidecar_policy": SIDECAR_POLICY,
    }
    if prior_artifact_id is not None:
        managed_request["prior_artifact_id"] = prior_artifact_id

    managed = await call_managed(
        "/vision/director/publish-video",
        "POST",
        managed_request,
        port=port,
    )
    data = managed.get("data") if isinstance(managed.get("data"), dict) else {}
    if managed.get("success") is not True:
        code = str(data.get("code") or "managed_publish_rejected")
        managed_subcode = data.get("managed_subcode")
        preserve_prior_manifest = (
            prior_artifact_id is not None
            and (
                code == "published_artifact_missing"
                or str(managed_subcode or "") == "prior_artifact_mismatch"
            )
        )
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code=code,
            message=str(data.get("message") or "Managed publish rejected the request"),
            managed_subcode=str(managed_subcode) if managed_subcode else None,
            prior_artifact_id=prior_artifact_id,
            profile=PROFILE_NAME,
            preset=preset,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            video_manifest_hash=video_manifest_hash,
            frame_manifest_hash=frame_manifest_hash,
            write_manifest=not preserve_prior_manifest,
        )

    artifact_id = str(data.get("artifact_id") or "")
    try:
        uuid.UUID(artifact_id)
    except ValueError:
        return _failure(
            run_id=run_id,
            run_root=run_root,
            started_at=started_at,
            code="managed_publish_rejected",
            message="Managed publish response must include a valid artifact_id UUID",
            prior_artifact_id=prior_artifact_id,
            profile=PROFILE_NAME,
            preset=preset,
            source_sha256=source_sha256,
            source_byte_size=source_byte_size,
            video_manifest_hash=video_manifest_hash,
            frame_manifest_hash=frame_manifest_hash,
        )

    success_manifest = _base_publish_manifest(
        state="complete",
        run_id=run_id,
        run_root=run_root,
        started_at=started_at,
        artifact_id=artifact_id,
        prior_artifact_id=prior_artifact_id,
        profile=PROFILE_NAME,
        preset=preset,
        source_sha256=source_sha256,
        source_byte_size=source_byte_size,
        video_manifest_hash=video_manifest_hash,
        frame_manifest_hash=frame_manifest_hash,
        error=None,
    )
    _atomic_write_json(run_root / "publish_manifest.json", success_manifest)
    return {
        "schema_version": PUBLISH_SCHEMA_VERSION,
        "state": "complete",
        "run_id": run_id,
        "artifact_id": artifact_id,
        "profile": PROFILE_NAME,
        "preset": preset,
        "source_video": RELATIVE_SOURCE_VIDEO,
        "sidecar_policy": SIDECAR_POLICY,
    }
