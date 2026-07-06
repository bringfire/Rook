from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_worker_compile as dwc
from rook.director_take_package import canonical_json_text, sha256_file, write_canonical_json

pytestmark = pytest.mark.asyncio

LIVE_DOC_PATH = "C:/work/live_project.3dm"


def _uuid(index: int) -> str:
    return f"00000000-0000-0000-0000-{index:012x}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_file_sha(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _camera_response() -> dict[str, Any]:
    return {
        "camera": {
            "projection": "perspective",
            "location": [0, -10, 5],
            "target": [0, 0, 0],
            "direction": [0, 1, 0],
            "up": [0, 0, 1],
            "lens_length": 35.0,
            "fov_degrees": None,
            "parallel_scale": None,
            "near_clip": None,
            "far_clip": None,
            "aspect": 1920 / 1080,
        },
        "provenance": {"source": "active_view"},
    }


def make_prepared_package(
    tmp_path: Path, *,
    object_count: int = 2,
    animated_indices: list[int] | None = None,
    frame_count: int = 3,
    phase: str = "prepared",
    group_name: str = "moving",
    tamper: str | None = None,
) -> Path:
    root = tmp_path / "take1"
    root.mkdir()
    scene = root / "scene.3dm"
    prepared = root / "prepared.3dm"
    scene.write_bytes(b"scene-3dm")
    prepared.write_bytes(b"prepared-3dm")

    object_ids = [_uuid(i + 1) for i in range(object_count)]
    if animated_indices is None:
        animated_indices = list(range(object_count))
    animated_ids = [object_ids[i] for i in animated_indices]

    motion = {
        "timeline": {"fps": 24, "frame_count": frame_count},
        "groups": {"canonical": ["setA"]},
        "motion": [{"target": "canonical", "keyframes": [{"t": 1, "translate": [1, 0, 0]}]}],
    }
    motion_sha = write_canonical_json(root / "motion.json", motion)

    manifest = {
        "schema_version": 1,
        "metadata_kind": "director_take_package_manifest",
        "take_id": "take1",
        "actor_sets": [{"actor_set_id": "setA", "members": []}],
        "hashes": {
            "motion_json_sha256": motion_sha,
            "camera_json_sha256": None,
            "scene_3dm_sha256": sha256_file(scene),
            "scene_3dm_bytes": scene.stat().st_size,
        },
    }
    manifest_sha = write_canonical_json(root / "scene_manifest.json", manifest)

    prepared_sha = sha256_file(prepared)
    members = [
        {
            "actor_member_id": f"setA_member_{i:04d}",
            "created_object_ids": [object_id],
        }
        for i, object_id in enumerate(object_ids)
    ]
    member_map = {
        "schema_version": 1,
        "metadata_kind": "director_member_map",
        "take_id": "take1",
        "package_id": "take1-abc123def456",
        "prepared_at_utc": "2026-07-06T00:00:00+00:00",
        "scene_manifest_sha256": manifest_sha,
        "prepared_scene": {
            "file": "prepared.3dm",
            "sha256": prepared_sha,
            "bytes": prepared.stat().st_size,
        },
        "actor_sets": [{
            "actor_set_id": "setA",
            "source_top_level_object_id": _uuid(999),
            "exploded_instance_id": _uuid(998),
            "members": members,
        }],
    }
    member_map_sha = write_canonical_json(root / "member_map.json", member_map)

    resolved = {
        "schema_version": 1,
        "metadata_kind": "director_resolved_motion",
        "timeline": {"fps": 24, "frame_count": frame_count},
        "groups": {group_name: animated_ids},
        "motion": [{
            "target": group_name,
            "keyframes": [{"t": 1, "translate": [1, 0, 0]}],
        }],
        "derived_from": {
            "member_map_sha256": member_map_sha,
            "motion_json_sha256": motion_sha,
            "scene_manifest_sha256": manifest_sha,
        },
    }
    resolved_sha = write_canonical_json(root / "resolved_motion.json", resolved)

    status = {
        "schema_version": 1,
        "package_id": "take1-abc123def456",
        "take_id": "take1",
        "phase": phase,
        "heartbeat_utc": "2026-07-06T00:00:00+00:00",
        "scene_manifest_sha256": manifest_sha,
        "evidence": {
            "member_map_sha256": member_map_sha,
            "resolved_motion_sha256": resolved_sha,
            "prepared_scene_sha256": prepared_sha,
        },
    }
    if phase == "compiled":
        (root / "track.json").write_text("old-track", encoding="utf-8")
        (root / "compile_provenance.json").write_text("old-provenance", encoding="utf-8")
        status["evidence"]["track_json_sha256"] = "old-track-sha"
        status["evidence"]["compile_provenance_sha256"] = "old-provenance-sha"
    write_canonical_json(root / "status.json", status)

    if tamper == "missing_prepared":
        prepared.unlink()
    elif tamper == "member_map":
        (root / "member_map.json").write_text(
            (root / "member_map.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
    elif tamper == "motion":
        (root / "motion.json").write_text(
            (root / "motion.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
    elif tamper == "resolved_derived_from":
        data = json.loads((root / "resolved_motion.json").read_text(encoding="utf-8"))
        data["derived_from"]["member_map_sha256"] = "bad"
        write_canonical_json(root / "resolved_motion.json", data)
        status = json.loads((root / "status.json").read_text(encoding="utf-8"))
        status["evidence"]["resolved_motion_sha256"] = _sha256_text(
            canonical_json_text(data))
        write_canonical_json(root / "status.json", status)
    elif tamper == "prepared":
        prepared.write_bytes(b"prepared-3dm-tampered")
    elif tamper == "bad_group_name":
        data = json.loads((root / "resolved_motion.json").read_text(encoding="utf-8"))
        bad = _uuid(777)
        data["groups"] = {bad: animated_ids}
        data["motion"][0]["target"] = bad
        write_canonical_json(root / "resolved_motion.json", data)
        status = json.loads((root / "status.json").read_text(encoding="utf-8"))
        status["evidence"]["resolved_motion_sha256"] = _sha256_text(
            canonical_json_text(data))
        write_canonical_json(root / "status.json", status)
    return root


def make_fake_native(
    root: Path, *,
    start_on_prepared: bool = False,
    same_path_already_open: bool = False,
    bbox_method: str = "tight_object",
):
    scene = str(root / "scene.3dm")
    prepared = str(root / "prepared.3dm")
    state = {
        "current_path": prepared if start_on_prepared else LIVE_DOC_PATH,
        "modified": False,
        "calls": [],
        "opens": [],
        "already_open_returned": False,
    }

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            return {"success": True, "data": {
                "path": state["current_path"],
                "modified": state["modified"],
                "objectCount": 10,
            }}
        if endpoint == "/document/open" and method == "POST":
            path = data["path"]
            state["opens"].append(path)
            if (same_path_already_open
                    and not state["already_open_returned"]
                    and path.lower().replace("\\", "/")
                    == state["current_path"].lower().replace("\\", "/")):
                state["already_open_returned"] = True
                return {"success": True, "data": {
                    "path": path,
                    "alreadyOpen": True,
                }}
            state["current_path"] = path
            state["modified"] = False
            return {"success": True, "data": {"path": path}}
        if endpoint == "/director/object-states" and method == "POST":
            objects = []
            for index, object_id in enumerate(data["object_ids"]):
                objects.append({
                    "object_id": object_id,
                    "bbox_min": [float(index), 0.0, 0.0],
                    "bbox_max": [float(index + 1), 1.0, 1.0],
                    "bbox_method": bbox_method,
                    "state_hash": f"state-{index}",
                })
            return {"success": True, "data": {"objects": objects, "units": "Meters"}}
        if endpoint == "/director/view-state" and method == "POST":
            return {"success": True, "data": _camera_response()}
        raise AssertionError(f"unexpected native call: {endpoint} {method}")

    fake.state = state
    return fake


async def expect_error(coro, code: str) -> dwc.DirectorWorkerCompileError:
    with pytest.raises(dwc.DirectorWorkerCompileError) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


async def test_missing_prepared_3dm_is_package_invalid(tmp_path):
    root = make_prepared_package(tmp_path, tamper="missing_prepared")
    fake = make_fake_native(root)
    err = await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")
    assert "re-run prepare" in str(err)


async def test_wrong_phase_is_package_invalid(tmp_path):
    root = make_prepared_package(tmp_path, phase="packaged")
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_member_map_hash_tamper_is_package_hash_mismatch(tmp_path):
    root = make_prepared_package(tmp_path, tamper="member_map")
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_motion_hash_tamper_is_package_hash_mismatch(tmp_path):
    root = make_prepared_package(tmp_path, tamper="motion")
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_resolved_motion_derived_from_tamper_is_package_hash_mismatch(tmp_path):
    root = make_prepared_package(tmp_path, tamper="resolved_derived_from")
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_prepared_3dm_content_tamper_is_package_hash_mismatch(tmp_path):
    root = make_prepared_package(tmp_path, tamper="prepared")
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_already_open_prepared_triggers_double_hop_then_compiles(tmp_path):
    root = make_prepared_package(tmp_path)
    fake = make_fake_native(
        root, start_on_prepared=True, same_path_already_open=True)
    result = await dwc.compile_take({"package_root": str(root)}, call_native=fake)
    assert result["phase"] == "compiled"
    assert fake.state["opens"] == [
        str(root / "prepared.3dm"), str(root / "scene.3dm"),
        str(root / "prepared.3dm")]


async def test_animated_id_not_in_member_map_is_compile_track_mismatch(tmp_path):
    root = make_prepared_package(tmp_path)
    data = json.loads((root / "resolved_motion.json").read_text(encoding="utf-8"))
    data["groups"]["moving"] = [_uuid(500)]
    write_canonical_json(root / "resolved_motion.json", data)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    status["evidence"]["resolved_motion_sha256"] = _sha256_text(
        canonical_json_text(data))
    write_canonical_json(root / "status.json", status)
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "compile_track_mismatch")


async def test_loose_bbox_method_from_object_states_is_rejected(tmp_path):
    root = make_prepared_package(tmp_path)
    fake = make_fake_native(root, bbox_method="loose_fallback")
    err = await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "compile_source_state_not_tight")
    assert _uuid(1) in str(err)


async def test_happy_path_writes_track_provenance_and_status(tmp_path):
    root = make_prepared_package(tmp_path)
    fake = make_fake_native(root)
    result = await dwc.compile_take(
        {"package_root": str(root)}, call_native=fake,
        now_fn=lambda: "2026-07-06T03:00:00+00:00")

    assert result["phase"] == "compiled"
    assert result["animated_object_count"] == 2

    track = json.loads((root / "track.json").read_text(encoding="utf-8"))
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["frame_count"] == 3
    assert track["derived_from"]["member_map_sha256"] == _json_file_sha(
        root / "member_map.json")
    assert track["derived_from"]["resolved_motion_sha256"] == _json_file_sha(
        root / "resolved_motion.json")
    assert track["derived_from"]["prepared_3dm_sha256"] == sha256_file(
        root / "prepared.3dm")
    for frame in track["object_frames"]:
        for transform in frame["object_transforms"]:
            source_state = transform["source_state"]
            assert source_state["bbox_method"] == "tight_object"
            assert source_state["validation_strength"] == "tight_bbox"

    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "compiled"
    assert status["evidence"]["track_json_sha256"] == _json_file_sha(
        root / "track.json")
    assert status["evidence"]["compile_provenance_sha256"] == _json_file_sha(
        root / "compile_provenance.json")
    assert result["track_json_sha256"] == status["evidence"]["track_json_sha256"]


async def test_happy_path_camera_frames_match_frame_count(tmp_path):
    root = make_prepared_package(tmp_path, frame_count=5)
    fake = make_fake_native(root)
    await dwc.compile_take({"package_root": str(root)}, call_native=fake)
    track = json.loads((root / "track.json").read_text(encoding="utf-8"))
    assert len(track["camera_frames"]) == 5
    assert [f["frame_index"] for f in track["camera_frames"]] == [1, 2, 3, 4, 5]


async def test_cap_free_compile_allows_300_animated_objects(tmp_path):
    root = make_prepared_package(tmp_path, object_count=300, frame_count=2)
    fake = make_fake_native(root)
    result = await dwc.compile_take({"package_root": str(root)}, call_native=fake)
    assert result["animated_object_count"] == 300
    track = json.loads((root / "track.json").read_text(encoding="utf-8"))
    assert len(track["animated_object_ids"]) == 300
    assert len(track["object_frames"][0]["object_transforms"]) == 300


async def test_frame_count_above_worker_max_is_compile_failed(tmp_path):
    root = make_prepared_package(
        tmp_path, object_count=1, frame_count=dwc.WORKER_MAX_FRAME_COUNT + 1)
    fake = make_fake_native(root)
    await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "compile_failed")


async def test_director_compile_error_from_target_expansion_is_wrapped(tmp_path):
    root = make_prepared_package(tmp_path, tamper="bad_group_name")
    fake = make_fake_native(root)
    err = await expect_error(
        dwc.compile_take({"package_root": str(root)}, call_native=fake),
        "compile_failed")
    assert "invalid_input" in str(err)


async def test_recompile_from_compiled_phase_overwrites_track_and_hashes(tmp_path):
    root = make_prepared_package(tmp_path, phase="compiled")
    fake = make_fake_native(root)
    old_track = (root / "track.json").read_text(encoding="utf-8")
    result = await dwc.compile_take({"package_root": str(root)}, call_native=fake)
    assert (root / "track.json").read_text(encoding="utf-8") != old_track
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["evidence"]["track_json_sha256"] == result["track_json_sha256"]
    assert status["evidence"]["track_json_sha256"] != "old-track-sha"


async def test_subset_compile_succeeds_and_tracks_only_animated_objects(tmp_path):
    root = make_prepared_package(
        tmp_path, object_count=4, animated_indices=[2], frame_count=3)
    fake = make_fake_native(root)
    await dwc.compile_take({"package_root": str(root)}, call_native=fake)
    track = json.loads((root / "track.json").read_text(encoding="utf-8"))
    assert track["animated_object_ids"] == [_uuid(3)]
    for frame in track["object_frames"]:
        assert [t["object_id"] for t in frame["object_transforms"]] == [_uuid(3)]
