from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import pytest

from rook.director_take_package import sha256_file, write_canonical_json
from rook.director_video import _validate_manifest_identity
from rook.director_worker_capture import DirectorWorkerCaptureError, capture_take

pytestmark = pytest.mark.asyncio

FRAME_COUNT = 4
FPS = 24
LIVE_DOC_PATH = "C:/work/live_project.3dm"
DEFAULT_TIMING = object()


@pytest.fixture(autouse=True)
def director_output_root(monkeypatch, tmp_path):
    root = tmp_path / "director_output"
    monkeypatch.setenv("ROOK_DIRECTOR_OUTPUT_ROOT", str(root))
    return root


def _uuid(index: int) -> str:
    return f"00000000-0000-0000-0000-{index:012x}"


def _png_bytes(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _write_png(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(width, height))


def _camera_frame(frame_index: int) -> dict[str, Any]:
    return {
        "frame_index": frame_index,
        "camera": {
            "projection": "perspective",
            "location": [6.0, -8.0, 5.0],
            "target": [0.0, 0.0, 0.5],
            "up": [0.0, 0.0, 1.0],
            "lens_length": 35.0,
        },
    }


def _track(object_ids: list[str]) -> dict[str, Any]:
    object_frames = []
    for frame_index in range(1, FRAME_COUNT + 1):
        object_frames.append({
            "frame_index": frame_index,
            "object_transforms": [
                {
                    "object_id": object_id,
                    "source_state": {
                        "bbox_min": [0.0, 0.0, 0.0],
                        "bbox_max": [1.0, 1.0, 1.0],
                        "bbox_method": "tight_object",
                        "validation_strength": "tight_bbox",
                    },
                    "transform": [
                        [1.0, 0.0, 0.0, float(frame_index)],
                        [0.0, 1.0, 0.0, 0.0],
                        [0.0, 0.0, 1.0, 0.0],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                }
                for object_id in object_ids
            ],
        })
    return {
        "transform_semantics": "absolute_from_source",
        "fps": FPS,
        "frame_count": FRAME_COUNT,
        "animated_object_ids": object_ids,
        "camera_frames": [_camera_frame(i) for i in range(1, FRAME_COUNT + 1)],
        "object_frames": object_frames,
        "derived_from": {},
    }


def make_compiled_package(tmp_path: Path, *, take_id: str = "take1",
                          tamper: str | None = None,
                          include_take_id: bool = True) -> Path:
    root = tmp_path / take_id
    root.mkdir(parents=True)
    scene = root / "scene.3dm"
    prepared = root / "prepared.3dm"
    scene.write_bytes(b"scene-3dm")
    prepared.write_bytes(b"prepared-3dm")

    member_map = {
        "schema_version": 1,
        "metadata_kind": "director_member_map",
        "take_id": take_id,
        "package_id": f"{take_id}-abc123def456",
        "prepared_scene": {
            "file": "prepared.3dm",
            "sha256": sha256_file(prepared),
            "bytes": prepared.stat().st_size,
        },
        "actor_sets": [{
            "actor_set_id": "setA",
            "members": [
                {"actor_member_id": "setA_member_0000",
                 "created_object_ids": [_uuid(1)]},
                {"actor_member_id": "setA_member_0001",
                 "created_object_ids": [_uuid(2)]},
            ],
        }],
    }
    member_map_sha = write_canonical_json(root / "member_map.json", member_map)

    resolved_motion = {
        "schema_version": 1,
        "metadata_kind": "director_resolved_motion",
        "timeline": {"fps": FPS, "frame_count": FRAME_COUNT},
        "groups": {"moving": [_uuid(1), _uuid(2)]},
        "motion": [{
            "target": "moving",
            "keyframes": [{"t": 1, "translate": [1, 0, 0]}],
        }],
    }
    resolved_sha = write_canonical_json(root / "resolved_motion.json", resolved_motion)

    track = _track([_uuid(1), _uuid(2)])
    track["derived_from"] = {
        "resolved_motion_sha256": resolved_sha,
        "member_map_sha256": member_map_sha,
        "prepared_3dm_sha256": sha256_file(prepared),
    }
    track_sha = write_canonical_json(root / "track.json", track)

    status = {
        "schema_version": 1,
        "package_id": f"{take_id}-abc123def456",
        "phase": "compiled",
        "heartbeat_utc": "2026-07-06T00:00:00+00:00",
        "evidence": {
            "member_map_sha256": member_map_sha,
            "resolved_motion_sha256": resolved_sha,
            "prepared_scene_sha256": sha256_file(prepared),
            "track_json_sha256": track_sha,
            "compile_provenance_sha256": "not-used-here",
        },
    }
    if include_take_id:
        status["take_id"] = take_id
    write_canonical_json(root / "status.json", status)

    if tamper == "track_hash":
        (root / "track.json").write_text(
            (root / "track.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
    return root


def make_args(root: Path, *, passes: list[dict[str, Any]] | None = None,
              width: int = 1280, height: int = 720) -> dict[str, Any]:
    return {
        "package_root": str(root),
        "passes": passes or [{
            "type": "display_mode",
            "pass_id": "arctic",
            "display_mode": "Arctic",
        }],
        "resolution": {"width": width, "height": height},
    }


def make_fake_native(root: Path, *, output_root: Path,
                     start_path: str | None = None,
                     modified: bool = False,
                     fail_by_call: dict[int, str] | None = None,
                     timing_override: Any = DEFAULT_TIMING,
                     frames_written_override: int | None = None,
                     skip_frame: int | None = None,
                     wrong_dimension_frame: int | None = None,
                     create_run_root_on_failure: bool | None = None,
                     already_open_on_open: bool = False):
    prepared = str(root / "prepared.3dm")
    track = json.loads((root / "track.json").read_text(encoding="utf-8"))
    frame_count = int(track["frame_count"])
    state = {
        "current_path": start_path or LIVE_DOC_PATH,
        "modified": modified,
        "calls": [],
        "events": [],
        "play_requests": [],
        "play_call_count": 0,
    }
    fail_by_call = dict(fail_by_call or {})

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict[str, Any]:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            return {"success": True, "data": {
                "path": state["current_path"],
                "modified": state["modified"],
                "objectCount": 10,
            }}
        if endpoint == "/document/open" and method == "POST":
            path = data["path"]
            state["events"].append(("open", path))
            same = Path(path) == Path(state["current_path"])
            state["current_path"] = path
            state["modified"] = False
            payload = {"path": path}
            if already_open_on_open or same:
                payload["alreadyOpen"] = True
            return {"success": True, "data": payload}
        if endpoint == "/director/worker-play" and method == "POST":
            state["play_call_count"] += 1
            call_index = state["play_call_count"]
            state["events"].append(("play", data["capture"]["passId"]
                                    if "passId" in data["capture"]
                                    else data["capture"]["displayMode"]))
            state["play_requests"].append(data)
            capture = data["capture"]
            run_root = Path(capture["runRoot"])
            frames_dir = Path(capture["framesDir"])
            reason = fail_by_call.get(call_index)
            if reason:
                should_create = create_run_root_on_failure
                if should_create is None:
                    should_create = reason in {
                        "display_mode_missing", "display_mode_mismatch",
                        "capture_failed",
                    }
                if should_create:
                    frames_dir.mkdir(parents=True, exist_ok=True)
                return {"success": False, "data": {"reason": reason}}

            frames_dir.mkdir(parents=True, exist_ok=True)
            for frame_index in range(1, frame_count + 1):
                if frame_index == skip_frame:
                    continue
                dims = (capture["width"], capture["height"])
                if frame_index == wrong_dimension_frame:
                    dims = (640, 480)
                _write_png(frames_dir / f"frame_{frame_index:04d}.png", *dims)

            per_frame = ([1.0, 2.0, 3.0, 4.0]
                         if timing_override is DEFAULT_TIMING else timing_override)
            frames_written = (frame_count if frames_written_override is None
                              else frames_written_override)
            capture_timing = {"captureTotalMs": 10.0}
            if timing_override is not None:
                capture_timing["capturePerFrameMs"] = per_frame
            return {"success": True, "data": {
                "documentPath": prepared,
                "playedFrom": 0,
                "playedTo": frame_count,
                "frameCount": frame_count,
                "objectCount": 2,
                "probes": [],
                "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0,
                          "worstDiagonalRatio": 1.0},
                "timing": {"totalMs": 12.5, "perFrameMs": [2.5] * frame_count},
                "capture": {
                    "backend": "scripted_command",
                    "runRoot": str(run_root),
                    "framesDir": str(frames_dir),
                    "framesWritten": frames_written,
                    "displayModeRequested": capture["displayMode"],
                    "displayModeResolved": {"id": "mode-id", "name": capture["displayMode"]},
                    "timing": capture_timing,
                },
            }}
        raise AssertionError(f"unexpected native call: {endpoint} {method}")

    fake.state = state
    return fake


async def expect_capture_error(coro, code: str) -> DirectorWorkerCaptureError:
    with pytest.raises(DirectorWorkerCaptureError) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value.to_data()
    return exc_info.value


def _capture_passes(root: Path) -> list[dict[str, Any]]:
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    return status.get("evidence", {}).get("capture_passes", [])


async def test_rejects_non_dict_arguments(director_output_root):
    await expect_capture_error(capture_take("x"), "invalid_input")


async def test_unsupported_pass_type_rejected_before_native(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    args = make_args(root, passes=[{
        "type": "depth", "pass_id": "depth", "display_mode": "Arctic",
    }])
    await expect_capture_error(capture_take(args, call_native=fake), "unsupported_pass_type")
    assert fake.state["calls"] == []


@pytest.mark.parametrize("passes", [
    [{"type": "display_mode", "display_mode": "Arctic"}],
    [{"type": "display_mode", "pass_id": "", "display_mode": "Arctic"}],
    [{"type": "display_mode", "pass_id": "Bad ID!", "display_mode": "Arctic"}],
    [
        {"type": "display_mode", "pass_id": "dup", "display_mode": "Arctic"},
        {"type": "display_mode", "pass_id": "dup", "display_mode": "Pen"},
    ],
])
async def test_pass_id_validation(tmp_path, director_output_root, passes):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    await expect_capture_error(
        capture_take(make_args(root, passes=passes), call_native=fake),
        "invalid_input")
    assert fake.state["calls"] == []


@pytest.mark.parametrize("resolution", [
    {"width": 1279, "height": 720},
    {"width": 1280, "height": 0},
    None,
    {"width": "1280", "height": 720},
])
async def test_resolution_validation(tmp_path, director_output_root, resolution):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    args = make_args(root)
    if resolution is None:
        args.pop("resolution")
    else:
        args["resolution"] = resolution
    await expect_capture_error(capture_take(args, call_native=fake), "invalid_input")
    assert fake.state["calls"] == []


@pytest.mark.parametrize("display_mode", [None, "", "current", "CURRENT"])
async def test_display_mode_validation(tmp_path, director_output_root, display_mode):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    pass_spec = {"type": "display_mode", "pass_id": "arctic"}
    if display_mode is not None:
        pass_spec["display_mode"] = display_mode
    await expect_capture_error(
        capture_take(make_args(root, passes=[pass_spec]), call_native=fake),
        "invalid_input")
    assert fake.state["calls"] == []


async def test_package_verification_reuses_play_loader(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path, tamper="track_hash")
    fake = make_fake_native(root, output_root=director_output_root)
    await expect_capture_error(
        capture_take(make_args(root), call_native=fake),
        "package_hash_mismatch")


async def test_take_id_required(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path, include_take_id=False)
    fake = make_fake_native(root, output_root=director_output_root)
    await expect_capture_error(
        capture_take(make_args(root), call_native=fake),
        "package_invalid")


async def test_run_root_layout(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake)
    request = fake.state["play_requests"][0]
    run_root = Path(request["capture"]["runRoot"])
    assert run_root == director_output_root / "takes" / "take1" / "arctic"
    assert Path(request["capture"]["framesDir"]) == run_root / "frames"


async def test_existing_run_root_fails_early(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    (director_output_root / "takes" / "take1" / "arctic").mkdir(parents=True)
    fake = make_fake_native(root, output_root=director_output_root)
    await expect_capture_error(capture_take(make_args(root), call_native=fake), "run_root_exists")
    assert fake.state["calls"] == []


async def test_reset_before_each_pass(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    args = make_args(root, passes=[
        {"type": "display_mode", "pass_id": "arctic", "display_mode": "Arctic"},
        {"type": "display_mode", "pass_id": "pen", "display_mode": "Pen"},
    ])
    await capture_take(args, call_native=fake)
    events = fake.state["events"]
    assert events[0] == ("open", str(root / "prepared.3dm"))
    assert events[1][0] == "play"
    next_open = next(i for i in range(2, len(events)) if events[i][0] == "open")
    assert events[next_open] == ("open", str(root / "prepared.3dm"))
    assert any(event[0] == "play" for event in events[next_open + 1:])


async def test_native_request_shape(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake)
    request = fake.state["play_requests"][0]
    assert "fromFrame" not in request
    assert "playTo" not in request
    assert set(request["capture"]) == {"runRoot", "framesDir", "displayMode", "width", "height"}
    assert request["expectedDocumentPath"] == str(root / "prepared.3dm")
    assert request["trackPath"] == str(root / "track.json")


async def test_manifest_json_assembly_compatible(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake)
    manifest = json.loads(
        (director_output_root / "takes" / "take1" / "arctic" / "manifest.json")
        .read_text(encoding="utf-8"))
    assert _validate_manifest_identity(manifest) is None
    assert len(manifest["frames"]) == FRAME_COUNT
    assert manifest["frames"] == [
        {"frame_index": i, "file": f"frames/frame_{i:04d}.png"}
        for i in range(1, FRAME_COUNT + 1)
    ]
    assert manifest["timeline"] == {"fps": FPS, "frame_count": FRAME_COUNT}


async def test_run_status_complete_written_last(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path / "ok")
    fake = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake)
    run_root = director_output_root / "takes" / "take1" / "arctic"
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"] == "complete"
    assert (run_root / "manifest.json").is_file()

    bad_root = make_compiled_package(tmp_path / "bad", take_id="take2")
    bad_fake = make_fake_native(bad_root, output_root=director_output_root, skip_frame=FRAME_COUNT)
    await expect_capture_error(capture_take(make_args(bad_root), call_native=bad_fake),
                               "pass_output_incomplete")
    bad_run = director_output_root / "takes" / "take2" / "arctic"
    assert json.loads((bad_run / "status.json").read_text(encoding="utf-8"))["state"] == "failed"
    assert not (bad_run / "manifest.json").exists()


async def test_png_dimension_verification(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            wrong_dimension_frame=2)
    error = await expect_capture_error(
        capture_take(make_args(root), call_native=fake),
        "pass_output_incomplete")
    assert "frame_0002.png" in str(error)
    run_root = director_output_root / "takes" / "take1" / "arctic"
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"] == "failed"


async def test_missing_frame_detected(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root, skip_frame=3)
    error = await expect_capture_error(
        capture_take(make_args(root), call_native=fake),
        "pass_output_incomplete")
    assert "frame_0003.png" in str(error)


async def test_partial_pass_failure_preserves_prior_evidence(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            fail_by_call={2: "display_mode_missing"})
    args = make_args(root, passes=[
        {"type": "display_mode", "pass_id": "arctic", "display_mode": "Arctic"},
        {"type": "display_mode", "pass_id": "pen", "display_mode": "Pen"},
    ])
    error = await expect_capture_error(capture_take(args, call_native=fake),
                                       "display_mode_missing")
    assert error.to_data()["failed_pass"] == "pen"
    assert error.to_data()["completed_passes"] == ["arctic"]
    entries = _capture_passes(root)
    assert [entry["outcome"] for entry in entries] == ["complete", "failed"]
    assert json.loads(
        (director_output_root / "takes" / "take1" / "arctic" / "status.json")
        .read_text(encoding="utf-8"))["state"] == "complete"


async def test_failed_native_pass_marks_run_root_failed(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            fail_by_call={1: "capture_failed"},
                            create_run_root_on_failure=True)
    await expect_capture_error(capture_take(make_args(root), call_native=fake),
                               "capture_failed")
    status = json.loads(
        (director_output_root / "takes" / "take1" / "arctic" / "status.json")
        .read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert status["reason"] == "capture_failed"


async def test_failed_native_pass_without_run_root(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            fail_by_call={1: "wrong_document"},
                            create_run_root_on_failure=False)
    await expect_capture_error(capture_take(make_args(root), call_native=fake),
                               "wrong_document")
    assert not (director_output_root / "takes" / "take1" / "arctic" / "status.json").exists()


@pytest.mark.parametrize("reason,expected", [
    ("invalid_input", "invalid_input"),
    ("output_policy_violation", "output_policy_violation"),
    ("run_root_exists", "run_root_exists"),
    ("display_mode_missing", "display_mode_missing"),
    ("display_mode_mismatch", "display_mode_mismatch"),
    ("capture_failed", "capture_failed"),
    ("worker_scene_not_pristine", "worker_scene_not_pristine"),
    ("weird", "capture_route_failed"),
])
async def test_known_native_reasons_reraise(tmp_path, director_output_root, reason, expected):
    root = make_compiled_package(tmp_path, take_id=f"take_{reason}")
    fake = make_fake_native(root, output_root=director_output_root,
                            fail_by_call={1: reason})
    await expect_capture_error(capture_take(make_args(root), call_native=fake), expected)


async def test_capture_timing_aggregates(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            timing_override=[1.0, 2.0, 3.0, 4.0])
    result = await capture_take(make_args(root), call_native=fake)
    assert result["passes"][0]["capture_ms"] == {
        "total": 10.0,
        "mean": 2.5,
        "p95": 4.0,
        "max": 4.0,
    }


async def test_frames_written_mismatch_is_incomplete(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            frames_written_override=FRAME_COUNT - 1)
    await expect_capture_error(capture_take(make_args(root), call_native=fake),
                               "pass_output_incomplete")


async def test_package_evidence_append_only(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake1 = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake1)
    first_entries = _capture_passes(root)

    fake2 = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root, passes=[{
        "type": "display_mode", "pass_id": "pen", "display_mode": "Pen",
    }]), call_native=fake2)
    second_entries = _capture_passes(root)
    assert second_entries[:1] == first_entries
    assert [entry["pass_index"] for entry in second_entries] == [0, 1]


async def test_success_payload_shape(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root)
    result = await capture_take(make_args(root), call_native=fake)
    assert set(result) == {"package_root", "take_id", "output_root", "passes"}
    assert result["take_id"] == "take1"
    assert len(result["passes"]) == 1
    pass_result = result["passes"][0]
    assert set(pass_result) == {
        "pass_id", "display_mode", "run_root", "frames_written",
        "backend", "capture_ms", "drift",
    }
    assert pass_result["backend"] == "scripted_command"
    assert pass_result["frames_written"] == FRAME_COUNT


async def test_atomic_metadata_writes(tmp_path, director_output_root):
    root = make_compiled_package(tmp_path / "ok")
    fake = make_fake_native(root, output_root=director_output_root)
    await capture_take(make_args(root), call_native=fake)
    ok_run = director_output_root / "takes" / "take1" / "arctic"
    assert list(ok_run.glob("*.staging")) == []

    bad_root = make_compiled_package(tmp_path / "bad", take_id="take2")
    bad_fake = make_fake_native(bad_root, output_root=director_output_root,
                                skip_frame=1)
    await expect_capture_error(capture_take(make_args(bad_root), call_native=bad_fake),
                               "pass_output_incomplete")
    bad_run = director_output_root / "takes" / "take2" / "arctic"
    assert list(bad_run.glob("*.staging")) == []


@pytest.mark.parametrize("timing", [
    3.5,
    [1.0, 2.0, 3.0],
    [1.0, "bad", 3.0, 4.0],
    None,
])
async def test_bad_capture_timing_shape_is_incomplete(tmp_path, director_output_root, timing):
    root = make_compiled_package(tmp_path)
    fake = make_fake_native(root, output_root=director_output_root,
                            timing_override=timing)
    await expect_capture_error(capture_take(make_args(root), call_native=fake),
                               "pass_output_incomplete")
    run_root = director_output_root / "takes" / "take1" / "arctic"
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"] == "failed"
    assert not (run_root / "manifest.json").exists()
