"""RookVisionDirector preview orchestration.

PR5 composes the PR4 compiler with native replay through the existing Python
helper. It does not add motion semantics, persistence, or async state.
"""
from __future__ import annotations

import copy
from numbers import Real
from typing import Any, Protocol

from . import director, director_compiler


class Compiler(Protocol):
    async def __call__(self, arguments: dict[str, Any], *, port: int | None = None) -> dict[str, Any]:
        raise NotImplementedError


class ReplayRunner(Protocol):
    async def __call__(self, arguments: dict[str, Any], *, port: int | None = None) -> dict[str, Any]:
        raise NotImplementedError


SUPPORTED_PREVIEW_CONTROLS = ["restore_on_finish", "fps", "replay_session_id"]


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _compile_failed(error: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "compile_failed",
        "compile": {"error": error},
        "replay": None,
        "next_edit_hooks": {},
    }


def _preview_block(arguments: dict[str, Any]) -> dict[str, Any]:
    preview = arguments.get("preview", {})
    if preview is None:
        return {}
    if not isinstance(preview, dict):
        return _error("invalid_preview", "preview must be an object", field="preview")
    if preview.get("loop") is True:
        return _error(
            "unsupported_preview_option",
            "preview.loop is not supported",
            option="loop",
        )
    if "include_track" in preview and not isinstance(preview["include_track"], bool):
        return _error("invalid_preview", "preview.include_track must be boolean", field="include_track")
    if "restore_on_finish" in preview and not isinstance(preview["restore_on_finish"], bool):
        return _error("invalid_preview", "preview.restore_on_finish must be boolean", field="restore_on_finish")
    if "fps" in preview:
        fps = preview["fps"]
        if isinstance(fps, bool) or not isinstance(fps, Real) or fps <= 0:
            return _error("invalid_preview", "preview.fps must be a positive number", field="fps")
    if "replay_session_id" in preview and not isinstance(preview["replay_session_id"], str):
        return _error("invalid_preview", "preview.replay_session_id must be a string", field="replay_session_id")
    return preview


def _compiler_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(arguments)
    copied.pop("preview", None)
    return copied


def _track_summary(track: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    frame_count = track.get("frame_count")
    fps = track.get("fps")
    duration_ms = provenance.get("duration_ms")
    if duration_ms is None and isinstance(frame_count, Real) and isinstance(fps, Real) and fps > 0:
        duration_ms = frame_count * (1000.0 / fps)
    return {
        "frame_count": frame_count,
        "fps": fps,
        "duration_ms": duration_ms,
        "animated_object_ids": list(track.get("animated_object_ids") or []),
        "camera_frame_count": len(track.get("camera_frames") or []),
        "object_frame_count": len(track.get("object_frames") or []),
    }


def _motion_targets(arguments: dict[str, Any]) -> list[Any]:
    motion = arguments.get("motion")
    if not isinstance(motion, list):
        return []
    return [entry.get("target") for entry in motion if isinstance(entry, dict) and "target" in entry]


def _next_edit_hooks(arguments: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "motion_targets": _motion_targets(arguments),
        "animated_object_ids": list(summary.get("animated_object_ids") or []),
        "timeline": {
            "fps": summary.get("fps"),
            "frame_count": summary.get("frame_count"),
            "duration_ms": summary.get("duration_ms"),
        },
        "preview_controls": list(SUPPORTED_PREVIEW_CONTROLS),
    }


def _replay_arguments(track: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {
        "track": track,
        "restore_on_finish": preview.get("restore_on_finish", True),
    }
    if "replay_session_id" in preview:
        args["replay_session_id"] = preview["replay_session_id"]
    if "fps" in preview:
        args["fps"] = preview["fps"]
    return args


def _state_from_replay_payload(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status == "completed":
        return "completed"
    if status == "cancelled":
        return "cancelled"
    return "replay_failed"


async def preview_motion(
    arguments: dict[str, Any],
    *,
    compile_motion: Compiler = director_compiler.compile_motion,
    run_replay: ReplayRunner = director.run_replay,
    port: int | None = None,
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return _compile_failed(_error("invalid_preview", "preview request must be an object"))

    preview = _preview_block(arguments)
    if "code" in preview:
        return _compile_failed(preview)

    try:
        compiled = await compile_motion(_compiler_arguments(arguments), port=port)
    except director_compiler.DirectorCompileError as exc:
        return _compile_failed(exc.to_data())

    track = compiled["track"]
    provenance = compiled.get("provenance") or {}
    summary = _track_summary(track, provenance)
    compile_block: dict[str, Any] = {
        "provenance": provenance,
        "track_summary": summary,
    }
    if preview.get("include_track") is True:
        compile_block["track"] = track

    try:
        replay_payload = await run_replay(_replay_arguments(track, preview), port=port)
    except director.DirectorError as exc:
        return {
            "state": "replay_failed",
            "compile": compile_block,
            "replay": {"error": _error("director_error", str(exc))},
            "next_edit_hooks": _next_edit_hooks(arguments, summary),
        }

    state = _state_from_replay_payload(replay_payload if isinstance(replay_payload, dict) else {})
    if state == "replay_failed":
        replay_block: dict[str, Any] = {
            "error": _error("unexpected_replay_result", "replay returned an unexpected status"),
            "raw": replay_payload,
        }
    else:
        replay_block = replay_payload

    return {
        "state": state,
        "compile": compile_block,
        "replay": replay_block,
        "next_edit_hooks": _next_edit_hooks(arguments, summary),
    }
