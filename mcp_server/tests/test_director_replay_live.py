"""Live Rhino integration tests for /director/replay + /director/replay/cancel.

Requires a running Rhino with the deployed RookNative plugin. The load-bearing
test is `test_replay_cancel_mid_replay`: a concurrent cancel while the replay
blocks on the UI thread — the only proof that the worker-thread cancel atomic
interrupts a held UI-thread replay loop.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from .test_director_routes_live import (
    _assert_vector_close,
    _create_line_curve,
    _error_code,
    _identity_matrix,
    _post_director,
    _translation_matrix,
)

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _camera() -> dict[str, Any]:
    return {
        "projection": "perspective",
        "location": [4, -4, 3],
        "target": [0, 0, 0],
        "up": [0, 0, 1],
        "lens_length": 35.0,
        "fov_degrees": 45.0,
        "near_clip": 0.1,
        "far_clip": 1000.0,
        "aspect": 1.7778,
    }


async def _object_bbox(object_id: str) -> tuple[list[float], list[float]]:
    _, env = await _post_director("object-states", {"object_ids": [object_id]})
    objects = env["data"]["objects"]
    obj = objects[0]
    return [float(v) for v in obj["bbox_min"]], [float(v) for v in obj["bbox_max"]]


def _build_track(
    object_id: str,
    bbox_min: list[float],
    bbox_max: list[float],
    translations: list[tuple[float, float, float]],
    *,
    fps: int = 24,
) -> dict[str, Any]:
    """A baked-track payload: one object, `len(translations)` frames, absolute_from_source.

    Frame i applies `_translation_matrix(*translations[i])` from the object's source pose.
    """
    frame_count = len(translations)
    camera_frames = [{"frame_index": i + 1, "camera": _camera()} for i in range(frame_count)]
    object_frames = []
    for i, (tx, ty, tz) in enumerate(translations):
        transform = _identity_matrix() if (tx, ty, tz) == (0, 0, 0) else _translation_matrix(tx, ty, tz)
        object_frames.append(
            {
                "frame_index": i + 1,
                "object_transforms": [
                    {
                        "object_id": object_id,
                        "source_state": {
                            "bbox_min": bbox_min,
                            "bbox_max": bbox_max,
                            "validation_strength": "bbox_only",
                            "state_hash": None,
                        },
                        "transform": transform,
                    }
                ],
            }
        )
    return {
        "schema_version": 1,
        "animation_version": "v1",
        "transform_semantics": "absolute_from_source",
        "frame_count": frame_count,
        "fps": fps,
        "resolution": {"width": 320, "height": 180},
        "animated_object_ids": [object_id],
        "camera_frames": camera_frames,
        "object_frames": object_frames,
    }


async def test_replay_completes_and_restores(fresh_document):
    oid = await _create_line_curve("replay_done")
    bmin, bmax = await _object_bbox(oid)
    track = _build_track(oid, bmin, bmax, [(0, 0, 0), (0, 0, 2), (0, 0, 4)], fps=24)

    status, env = await _post_director(
        "replay", {"replay_session_id": "done1", "track": track, "restore_on_finish": True}
    )
    assert status == 200, env
    data = env["data"]
    assert data["status"] == "completed", data
    assert data["frames_played"] == 3
    assert data["restored"] is True

    rmin, rmax = await _object_bbox(oid)
    _assert_vector_close(rmin, bmin)
    _assert_vector_close(rmax, bmax)


async def test_replay_restore_on_finish_false_leaves_final_frame(fresh_document):
    oid = await _create_line_curve("replay_leave")
    bmin, bmax = await _object_bbox(oid)
    track = _build_track(oid, bmin, bmax, [(0, 0, 0), (0, 0, 6)], fps=24)

    status, env = await _post_director(
        "replay", {"replay_session_id": "leave1", "track": track, "restore_on_finish": False}
    )
    assert status == 200, env
    assert env["data"]["status"] == "completed"
    assert env["data"]["restored"] is False

    lmin, lmax = await _object_bbox(oid)
    _assert_vector_close(lmin, [bmin[0], bmin[1], bmin[2] + 6])
    _assert_vector_close(lmax, [bmax[0], bmax[1], bmax[2] + 6])


async def test_replay_cancel_mid_replay(fresh_document):
    """LOAD-BEARING: a concurrent cancel interrupts a held UI-thread replay loop."""
    oid = await _create_line_curve("replay_cancel")
    bmin, bmax = await _object_bbox(oid)
    # 20 frames at fps=5 -> 200ms dwell -> ~4s total; cancel well before it finishes.
    translations = [(0.0, 0.0, i * 0.2) for i in range(20)]
    track = _build_track(oid, bmin, bmax, translations, fps=5)
    sid = "cancel1"

    async def _cancel_after(delay: float):
        await asyncio.sleep(delay)
        return await _post_director("replay/cancel", {"replay_session_id": sid})

    (rstatus, renv), (_cstatus, cenv) = await asyncio.gather(
        _post_director("replay", {"replay_session_id": sid, "track": track, "restore_on_finish": True}),
        _cancel_after(0.6),
    )

    assert rstatus == 200, renv
    data = renv["data"]
    assert data["status"] == "cancelled", data
    assert 0 < data["frames_played"] < 20, data
    assert data["restored"] is True
    assert cenv["data"]["cancel_requested"] is True, cenv

    rmin, rmax = await _object_bbox(oid)
    _assert_vector_close(rmin, bmin)
    _assert_vector_close(rmax, bmax)


async def test_replay_already_active(fresh_document):
    oid = await _create_line_curve("replay_busy")
    bmin, bmax = await _object_bbox(oid)
    track = _build_track(oid, bmin, bmax, [(0.0, 0.0, i * 0.2) for i in range(15)], fps=5)

    results = await asyncio.gather(
        _post_director("replay", {"replay_session_id": "busyA", "track": track, "restore_on_finish": True}),
        _post_director("replay", {"replay_session_id": "busyB", "track": track, "restore_on_finish": True}),
    )
    statuses = [env["data"].get("status") for _, env in results]
    codes = [_error_code(env) for _, env in results]
    assert "replay_already_active" in codes, (statuses, codes)
    assert "completed" in statuses, (statuses, codes)


async def test_replay_validation_errors_live(fresh_document):
    oid = await _create_line_curve("replay_val")
    bmin, bmax = await _object_bbox(oid)
    base = _build_track(oid, bmin, bmax, [(0, 0, 0)], fps=24)

    _, env = await _post_director("replay", {"replay_session_id": "v1", "track": base, "loop": True})
    assert _error_code(env) == "unsupported_replay_option", env

    bad_semantics = dict(base)
    bad_semantics["transform_semantics"] = "delta"
    _, env = await _post_director("replay", {"replay_session_id": "v2", "track": bad_semantics})
    assert _error_code(env) == "unsupported_transform_semantics", env

    missing = _build_track("00000000-0000-0000-0000-0000000000ff", bmin, bmax, [(0, 0, 0)], fps=24)
    _, env = await _post_director("replay", {"replay_session_id": "v3", "track": missing})
    assert _error_code(env) == "object_not_found", env


async def test_replay_malformed_later_frame_rejected_without_mutation(fresh_document):
    """Finding-1 contract: a malformed later frame is caught pre-flight, no mutation."""
    oid = await _create_line_curve("replay_malformed")
    bmin, bmax = await _object_bbox(oid)
    track = _build_track(oid, bmin, bmax, [(0, 0, 0), (0, 0, 2), (0, 0, 4)], fps=24)
    # Corrupt frame 2 (index 1): its object set no longer equals animated_object_ids.
    track["object_frames"][1]["object_transforms"][0]["object_id"] = "00000000-0000-0000-0000-0000000000ee"

    _, env = await _post_director("replay", {"replay_session_id": "m1", "track": track})
    assert _error_code(env) == "track_invalid", env

    rmin, rmax = await _object_bbox(oid)
    _assert_vector_close(rmin, bmin)
    _assert_vector_close(rmax, bmax)
