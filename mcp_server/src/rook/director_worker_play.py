"""Director v3 Slice 3: file-backed worker playback orchestrator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .director_take_package import canonical_json_text, sha256_file, utc_now_iso
from .director_worker_common import (
    get_document,
    norm_path,
    open_package_document,
)

KNOWN_NATIVE_REASONS = {
    "wrong_document",
    "track_invalid",
    "track_objects_missing",
    "worker_scene_not_pristine",
    "playback_drift_detected",
}


class DirectorWorkerPlayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json_file(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectorWorkerPlayError(
            "package_invalid", f"unparseable package JSON {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise DirectorWorkerPlayError(
            "package_invalid", f"{path.name} must contain a JSON object")
    return data


def _load_play_package(package_root_arg: Any) -> dict[str, Any]:
    if not isinstance(package_root_arg, str) or not package_root_arg.strip():
        raise DirectorWorkerPlayError("invalid_input", "package_root is required")
    root = Path(package_root_arg).expanduser().resolve()
    if not root.is_dir():
        raise DirectorWorkerPlayError(
            "package_invalid", f"not a package directory: {root}")

    required = (
        "scene.3dm", "prepared.3dm", "member_map.json",
        "resolved_motion.json", "track.json", "status.json")
    for name in required:
        if not (root / name).is_file():
            raise DirectorWorkerPlayError(
                "package_invalid", f"package is missing {name}")

    status = _read_json(root / "status.json")
    track = _read_json(root / "track.json")
    member_map = _read_json(root / "member_map.json")
    if status.get("phase") != "compiled":
        raise DirectorWorkerPlayError(
            "package_invalid",
            f"package phase {status.get('phase')!r} is not playable")

    evidence = status.get("evidence") or {}
    track_sha = _sha256_json_file(root / "track.json")
    member_map_sha = _sha256_json_file(root / "member_map.json")
    resolved_sha = _sha256_json_file(root / "resolved_motion.json")
    prepared_sha = sha256_file(root / "prepared.3dm")
    mismatches: list[str] = []

    if evidence.get("track_json_sha256") != track_sha:
        mismatches.append("track.json")
    if evidence.get("member_map_sha256") not in (None, member_map_sha):
        mismatches.append("member_map.json")
    if evidence.get("resolved_motion_sha256") not in (None, resolved_sha):
        mismatches.append("resolved_motion.json")
    if evidence.get("prepared_scene_sha256") not in (None, prepared_sha):
        mismatches.append("prepared.3dm")

    prepared_scene = member_map.get("prepared_scene") or {}
    if (prepared_scene.get("sha256") != prepared_sha
            or prepared_scene.get("bytes") != (root / "prepared.3dm").stat().st_size):
        mismatches.append("member_map.prepared_scene")

    derived = track.get("derived_from") or {}
    if derived.get("member_map_sha256") != member_map_sha:
        mismatches.append("track.derived_from.member_map_sha256")
    if derived.get("prepared_3dm_sha256") != prepared_sha:
        mismatches.append("track.derived_from.prepared_3dm_sha256")
    if derived.get("resolved_motion_sha256") not in (None, resolved_sha):
        mismatches.append("track.derived_from.resolved_motion_sha256")

    if mismatches:
        raise DirectorWorkerPlayError(
            "package_hash_mismatch",
            "package artifacts disagree with recorded hashes: "
            + ", ".join(mismatches))

    return {
        "root": root,
        "status": status,
        "track": track,
        "hashes": {
            "track": track_sha,
            "member_map": member_map_sha,
            "resolved_motion": resolved_sha,
            "prepared": prepared_sha,
        },
    }


def _optional_int(arguments: dict[str, Any], key: str) -> int | None:
    if key not in arguments or arguments[key] is None:
        return None
    if not isinstance(arguments[key], int):
        raise DirectorWorkerPlayError("invalid_input", f"{key} must be an integer")
    return arguments[key]


def _probe_frames(arguments: dict[str, Any]) -> list[int]:
    value = arguments.get("probe_frames")
    if value is None:
        return []
    if (not isinstance(value, list)
            or not all(isinstance(item, int) for item in value)):
        raise DirectorWorkerPlayError(
            "invalid_input", "probe_frames must be a list of integers")
    return list(value)


def _drift_tolerance(arguments: dict[str, Any]) -> float | None:
    value = arguments.get("drift_tolerance")
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise DirectorWorkerPlayError(
            "invalid_input", "drift_tolerance must be a positive number")
    return float(value)


async def _ensure_prepared_document(call_native, root: Path, *,
                                    port: int | None,
                                    reset: bool) -> None:
    prepared = root / "prepared.3dm"
    if reset:
        await open_package_document(
            call_native, root, prepared, port=port,
            error_cls=DirectorWorkerPlayError, mode="require_fresh")
        return

    live = await get_document(call_native, port, DirectorWorkerPlayError)
    live_path = live.get("path") or ""
    if norm_path(live_path) == norm_path(str(prepared)):
        return

    await open_package_document(
        call_native, root, prepared, port=port,
        error_cls=DirectorWorkerPlayError, mode="require_fresh")


async def _call_worker_play(call_native, request: dict[str, Any],
                            port: int | None) -> dict[str, Any]:
    envelope = await call_native(
        "/director/worker-play", "POST", request, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        reason = detail.get("reason") if isinstance(detail, dict) else None
        if reason in KNOWN_NATIVE_REASONS:
            raise DirectorWorkerPlayError(reason, str(detail))
        raise DirectorWorkerPlayError(
            "play_route_failed", f"/director/worker-play failed: {detail}")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise DirectorWorkerPlayError(
            "play_route_failed", "/director/worker-play returned no data object")
    return data


def _append_play_run(root: Path, status: dict[str, Any], play_data: dict[str, Any],
                     request: dict[str, Any], now_fn) -> int:
    evidence = dict(status.get("evidence") or {})
    play_runs = list(evidence.get("play_runs") or [])
    run_index = len(play_runs)
    play_runs.append({
        "run_index": run_index,
        "played_at_utc": now_fn(),
        "played_from": play_data.get("playedFrom"),
        "played_to": play_data.get("playedTo"),
        "frame_count": play_data.get("frameCount"),
        "object_count": play_data.get("objectCount"),
        "probe_count": len(play_data.get("probes") or []),
        "timing_total_ms": (play_data.get("timing") or {}).get("totalMs"),
        "drift": play_data.get("drift"),
        "request": request,
    })
    evidence["play_runs"] = play_runs
    status = dict(status)
    status["phase"] = "compiled"
    status["heartbeat_utc"] = now_fn()
    status["evidence"] = evidence
    (root / "status.json").write_text(
        canonical_json_text(status), encoding="utf-8")
    return run_index


async def play_take(arguments: dict[str, Any], *, call_native=call_rhino,
                    port: int | None = None,
                    now_fn=utc_now_iso) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise DirectorWorkerPlayError(
            "invalid_input", "play request must be an object")
    pkg = _load_play_package(arguments.get("package_root"))
    root = pkg["root"]

    await _ensure_prepared_document(
        call_native, root, port=port, reset=bool(arguments.get("reset")))

    request: dict[str, Any] = {
        "expectedDocumentPath": str(root / "prepared.3dm"),
        "trackPath": str(root / "track.json"),
    }
    from_frame = _optional_int(arguments, "from_frame")
    play_to = _optional_int(arguments, "play_to")
    if from_frame is not None:
        request["fromFrame"] = from_frame
    if play_to is not None:
        request["playTo"] = play_to
    probes = _probe_frames(arguments)
    if probes:
        request["probeFrames"] = probes
    tolerance = _drift_tolerance(arguments)
    if tolerance is not None:
        request["driftTolerance"] = tolerance

    play_data = await _call_worker_play(call_native, request, port)
    run_index = _append_play_run(
        root, pkg["status"], play_data, request, now_fn)

    probes_payload = play_data.get("probes") or []
    timing = play_data.get("timing") or {}
    return {
        "package_root": str(root),
        "take_id": pkg["status"].get("take_id"),
        "played_from": play_data.get("playedFrom"),
        "played_to": play_data.get("playedTo"),
        "drift": play_data.get("drift"),
        "timing_total_ms": timing.get("totalMs"),
        "probe_count": len(probes_payload),
        "run_index": run_index,
    }
