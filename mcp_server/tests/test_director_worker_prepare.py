from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_worker_prepare as dwp
from rook.director_take_package import canonical_json_text, write_canonical_json

pytestmark = pytest.mark.asyncio

LIVE_DOC_PATH = "C:/work/live_project.3dm"

MEMBER0_ID = "11111111-1111-1111-1111-111111111111"
MEMBER1_ID = "22222222-2222-2222-2222-222222222222"
NESTED_LEAF_ID = "33333333-3333-3333-3333-333333333333"
INSTANCE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CREATED0_ID = "99999999-9999-9999-9999-999999999999"
CREATED1_ID = "88888888-8888-8888-8888-888888888888"


def make_manifest(scene_sha: str, scene_bytes: int, motion_sha: str) -> dict:
    return {
        "schema_version": 1,
        "metadata_kind": "director_take_package_manifest",
        "take_id": "take1",
        "created_at_utc": "2026-07-06T00:00:00+00:00",
        "source_document": {"path": LIVE_DOC_PATH, "modified_at_package_time": False,
                            "object_count": 10, "units": "Millimeters"},
        "scene": {"file": "scene.3dm", "mechanism": "save_copy", "evidence": {},
                  "bytes": scene_bytes, "sha256": scene_sha},
        "actor_sets": [{
            "actor_set_id": "setA",
            "block_name": "S2Outer",
            "source_top_level_object_id": INSTANCE_ID,
            "source_instance": {"instance_id": INSTANCE_ID},
            "member_count": 2,
            "members": [
                {"actor_member_id": "setA_member_0000",
                 "definition_object_index": 0,
                 "definition_object_id": MEMBER0_ID,
                 "expected": {"type": "Brep", "layer": "Default", "name": ""},
                 "bbox_evidence": {"bbox_method": "tight_object",
                                   "bbox_space": "definition_object",
                                   "min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0],
                                   "rounding_policy": "round_to_4_decimal_places",
                                   "validation_strength": "tight_bbox"}},
                {"actor_member_id": "setA_member_0001",
                 "definition_object_index": 1,
                 "definition_object_id": MEMBER1_ID,
                 "expected": {"type": "InstanceReference", "layer": "Default", "name": ""},
                 "bbox_evidence": {"bbox_method": "tight_object",
                                   "bbox_space": "definition_object",
                                   "min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0],
                                   "rounding_policy": "round_to_4_decimal_places",
                                   "validation_strength": "tight_bbox"}},
            ],
        }],
        "display_mode_requirements": [
            {"name": "Shaded", "id": "mode-1", "settings_fingerprint": None}],
        "hashes": {"motion_json_sha256": motion_sha, "camera_json_sha256": None,
                   "scene_3dm_sha256": scene_sha, "scene_3dm_bytes": scene_bytes},
    }


def make_motion() -> dict:
    # The REAL compiler vocabulary (director_compiler.py:56/:102; Slice 1
    # fixture test_director_take_package.py:112): timeline is the fps dict,
    # motion is the track array.
    return {
        "timeline": {"fps": 24, "frame_count": 48},
        "groups": {"roof": ["setA"]},
        "motion": [
            {"target": "roof", "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]},
            {"target": "setA_member_0001",
             "keyframes": [{"t": 1, "translate": [0, 0, 100]}]},
        ],
    }


def make_package(tmp_path: Path, *, motion: dict | None = None,
                 tamper: str | None = None) -> Path:
    root = tmp_path / "take1"
    root.mkdir()
    scene = root / "scene.3dm"
    scene.write_bytes(b"fake-3dm-bytes")
    motion = motion if motion is not None else make_motion()
    motion_text = canonical_json_text(motion)
    (root / "motion.json").write_text(motion_text, encoding="utf-8")
    motion_sha = hashlib.sha256(motion_text.encode("utf-8")).hexdigest()
    scene_sha = hashlib.sha256(b"fake-3dm-bytes").hexdigest()
    manifest = make_manifest(scene_sha, len(b"fake-3dm-bytes"), motion_sha)
    manifest_sha = write_canonical_json(root / "scene_manifest.json", manifest)
    write_canonical_json(root / "status.json", {
        "schema_version": 1, "package_id": "take1-abc123def456", "take_id": "take1",
        "phase": "packaged", "heartbeat_utc": "2026-07-06T00:00:00+00:00",
        "scene_manifest_sha256": manifest_sha,
        "evidence": {"scene_mechanism": "save_copy"}})

    if tamper == "motion":
        (root / "motion.json").write_text(motion_text + " ", encoding="utf-8")
    elif tamper == "scene":
        scene.write_bytes(b"fake-3dm-bytes-tampered")
    elif tamper == "manifest":
        text = (root / "scene_manifest.json").read_text(encoding="utf-8")
        (root / "scene_manifest.json").write_text(text + " ", encoding="utf-8")
    return root


def make_prepare_payload(root: Path, **overrides: Any) -> dict:
    member0 = {
        "index": 0, "definitionObjectId": MEMBER0_ID, "type": "Brep",
        "layer": overrides.get("member0_layer", "Default"), "name": "",
        "defBbox": overrides.get(
            "member0_bbox", {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]}),
        "bboxMethod": "tight_object",
        "created": [{"occurrencePath": "0", "definitionObjectId": MEMBER0_ID,
                     "createdObjectId": CREATED0_ID, "type": "Brep"}],
        "skipped": [],
    }
    member1 = {
        "index": 1, "definitionObjectId": MEMBER1_ID, "type": "InstanceReference",
        "layer": "Default", "name": "",
        "defBbox": {"min": [2.0, 0.0, 0.0], "max": [3.0, 1.0, 1.0]},
        "bboxMethod": "tight_object",
        "created": [{"occurrencePath": "1/0", "definitionObjectId": NESTED_LEAF_ID,
                     "createdObjectId": CREATED1_ID, "type": "Brep"}],
        "skipped": [],
    }
    if overrides.get("member1_skip"):
        member1["created"] = []
        member1["skipped"] = [{"occurrencePath": "1/0",
                               "definitionObjectId": NESTED_LEAF_ID,
                               "reason": "unsupported_geometry_type:ON_SubD"}]
    members = [member0, member1]
    if overrides.get("drop_member1"):
        members = [member0]
    return {
        "documentPath": str(root / "scene.3dm"),
        "actorSets": [{"actorSetId": "setA", "instanceId": INSTANCE_ID,
                       "definitionName": "S2Outer", "instanceDeleted": True,
                       "members": members}],
    }


def make_fake_native(root: Path, *, live_modified: bool = False,
                     open_ok: bool = True, opened_path: str | None = None,
                     start_on_scene: bool = False,
                     instance_missing: bool = False,
                     open_already_open: bool = False,
                     modes: tuple[str, ...] = ("Shaded",),
                     prepare_ok: bool = True,
                     prepare_payload: dict | None = None):
    """Stateful fake: /document reports the live doc until /document/open
    succeeds, then reports the opened path. start_on_scene=True simulates a
    take copy already being the active document (the re-prepare scenario);
    instance_missing=True simulates a mutated copy (source instance gone);
    open_already_open=True simulates the native same-path no-op branch
    (alreadyOpen: true — the doc was NOT reloaded from disk)."""
    scene_path = str(root / "scene.3dm")
    state = {"opened": start_on_scene, "calls": []}

    async def fake(endpoint: str, method: str, data: dict | None = None, *,
                   port: int | None = None) -> dict:
        state["calls"].append((endpoint, method, data))
        if endpoint == "/document" and method == "GET":
            if state["opened"]:
                return {"success": True, "data": {
                    "path": opened_path or scene_path, "modified": False,
                    "objectCount": 10}}
            return {"success": True, "data": {
                "path": LIVE_DOC_PATH, "modified": live_modified,
                "objectCount": 10}}
        if endpoint == "/document/open":
            if not open_ok:
                return {"success": False, "data": {"error": "open failed"}}
            state["opened"] = True
            payload = {"path": data["path"]}
            if open_already_open:
                payload["alreadyOpen"] = True
            return {"success": True, "data": payload}
        if endpoint == "/block/instances":
            instances = [] if instance_missing else [{"id": INSTANCE_ID}]
            return {"success": True, "data": {"instances": instances}}
        if endpoint == "/display-modes":
            return {"success": True, "data": {
                "modes": [{"name": n, "id": f"mode-{i}"}
                          for i, n in enumerate(modes, start=1)]}}
        if endpoint == "/director/prepare-take":
            if not prepare_ok:
                return {"success": False, "data": {"reason": "wrong_document"}}
            return {"success": True,
                    "data": prepare_payload or make_prepare_payload(root)}
        raise AssertionError(f"unexpected native call: {endpoint}")

    fake.state = state
    return fake


async def expect_error(coro, code: str) -> dwp.DirectorWorkerPrepareError:
    with pytest.raises(dwp.DirectorWorkerPrepareError) as exc_info:
        await coro
    assert exc_info.value.code == code, exc_info.value
    return exc_info.value


async def test_missing_package_root_rejected(tmp_path):
    fake = make_fake_native(tmp_path)
    await expect_error(dwp.prepare_take({}, call_native=fake), "invalid_input")


async def test_missing_manifest_rejected(tmp_path):
    root = make_package(tmp_path)
    (root / "scene_manifest.json").unlink()
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_bad_phase_rejected(tmp_path):
    root = make_package(tmp_path)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    status["phase"] = "captured"
    write_canonical_json(root / "status.json", status)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")


async def test_motion_hash_mismatch_rejected(tmp_path):
    root = make_package(tmp_path, tamper="motion")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_scene_hash_mismatch_rejected(tmp_path):
    root = make_package(tmp_path, tamper="scene")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_manifest_tamper_rejected(tmp_path):
    root = make_package(tmp_path, tamper="manifest")
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_hash_mismatch")


async def test_modified_live_document_blocks_open(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, live_modified=True)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "document_not_saved")
    # The guard must fire BEFORE any /document/open call.
    assert not any(c[0] == "/document/open" for c in fake.state["calls"])


async def test_open_failure_surfaces(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, open_ok=False)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "document_open_failed")


async def test_wrong_document_after_open(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, opened_path="C:/somewhere/else.3dm")
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "wrong_document")


async def test_reprepare_forces_reopen_of_open_copy(tmp_path):
    # Re-prepare scenario: the take copy is ALREADY the active document
    # (e.g. a previous prepare ran in this session). A fresh reopen must be
    # issued anyway — the in-memory copy may be mutated, and the dirty flag
    # is unreliable (native /document/open force-clears it).
    root = make_package(tmp_path)
    fake = make_fake_native(root, start_on_scene=True)
    result = await dwp.prepare_take({"package_root": str(root)}, call_native=fake)
    assert result["phase"] == "prepared"
    assert any(c[0] == "/document/open" for c in fake.state["calls"]), (
        "same-path prepare must force a fresh reopen of scene.3dm")


async def test_same_path_noop_open_rejected(tmp_path):
    # Native's same-path branch can report success with alreadyOpen=true
    # WITHOUT reloading from disk. A partially mutated copy can still hold
    # its source instances (so the instance-presence gate passes) plus
    # stray duplicates — the only safe response to a no-op reopen is to
    # fail closed, even though the source instance is present in this fake.
    root = make_package(tmp_path)
    fake = make_fake_native(root, start_on_scene=True, open_already_open=True)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "take_copy_not_pristine")
    assert not any(c[0] == "/director/prepare-take"
                   for c in fake.state["calls"])


async def test_mutated_copy_rejected_as_not_pristine(tmp_path):
    # If the source instance is gone after (re)open — a prior prepare
    # exploded it and the reopen no-opped (alreadyOpen) — prepare must
    # refuse before any destructive call.
    root = make_package(tmp_path)
    fake = make_fake_native(root, start_on_scene=True, instance_missing=True)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "take_copy_not_pristine")
    assert not any(c[0] == "/director/prepare-take"
                   for c in fake.state["calls"])


async def test_missing_display_mode_rejected(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, modes=("Wireframe",))
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "display_mode_missing")


async def test_prepare_route_failure_surfaces(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root, prepare_ok=False)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_route_failed")


async def test_coverage_incomplete_on_skip(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(
        root, prepare_payload=make_prepare_payload(root, member1_skip=True))
    err = await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_coverage_incomplete")
    assert "unsupported_geometry_type:ON_SubD" in str(err)
    assert "setA_member_0001" in str(err)


async def test_coverage_incomplete_on_missing_member(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(
        root, prepare_payload=make_prepare_payload(root, drop_member1=True))
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_coverage_incomplete")


async def test_verification_failure_on_bbox_mismatch(tmp_path):
    root = make_package(tmp_path)
    payload = make_prepare_payload(
        root, member0_bbox={"min": [0.0, 0.0, 0.0], "max": [1.5, 1.0, 1.0]})
    fake = make_fake_native(root, prepare_payload=payload)
    err = await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_verification_failed")
    assert "setA_member_0000" in str(err)


async def test_verification_failure_on_layer_mismatch(tmp_path):
    root = make_package(tmp_path)
    payload = make_prepare_payload(root, member0_layer="OtherLayer")
    fake = make_fake_native(root, prepare_payload=payload)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "prepare_verification_failed")


async def test_happy_path_writes_all_artifacts(tmp_path):
    root = make_package(tmp_path)
    fake = make_fake_native(root)
    result = await dwp.prepare_take(
        {"package_root": str(root)}, call_native=fake,
        now_fn=lambda: "2026-07-06T01:00:00+00:00")

    assert result["phase"] == "prepared"
    assert result["actor_sets"] == [{
        "actor_set_id": "setA", "member_count": 2, "created_object_count": 2}]

    member_map = json.loads((root / "member_map.json").read_text(encoding="utf-8"))
    assert member_map["metadata_kind"] == "director_member_map"
    members = member_map["actor_sets"][0]["members"]
    # Fresh UUID proof: created id differs from the definition-object id.
    assert members[0]["created_object_ids"] == [CREATED0_ID]
    assert members[0]["created_object_ids"][0] != members[0]["definition_object_id"]
    # Nested provenance: occurrence path keys the nested leaf.
    assert members[1]["occurrences"][0]["occurrence_path"] == "1/0"
    assert members[1]["occurrences"][0]["definition_object_id"] == NESTED_LEAF_ID

    member_map_text = (root / "member_map.json").read_text(encoding="utf-8")
    member_map_sha = hashlib.sha256(member_map_text.encode("utf-8")).hexdigest()
    assert result["member_map_sha256"] == member_map_sha

    resolved = json.loads((root / "resolved_motion.json").read_text(encoding="utf-8"))
    assert resolved["metadata_kind"] == "director_resolved_motion"
    # Group "roof" contained canonical set id "setA" -> all created ids.
    assert resolved["groups"]["roof"] == [CREATED0_ID, CREATED1_ID]
    # Bare canonical target became a synthesized group.
    assert resolved["groups"]["setA_member_0001"] == [CREATED1_ID]
    assert resolved["derived_from"]["member_map_sha256"] == member_map_sha
    # Untouched motion keys pass through — timeline is the fps DICT, never
    # rewritten (real compiler vocabulary).
    assert resolved["timeline"] == {"fps": 24, "frame_count": 48}
    assert resolved["motion"] == make_motion()["motion"]

    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "prepared"
    assert status["evidence"]["member_map_sha256"] == member_map_sha


async def test_unmapped_motion_target_rejected(tmp_path):
    motion = make_motion()
    motion["motion"].append(
        {"target": "not_a_member", "keyframes": [{"t": 1}]})
    root = make_package(tmp_path, motion=motion)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "motion_member_unmapped")
    # Failed derivation must not leave partial artifacts.
    assert not (root / "member_map.json").exists()
    assert not (root / "resolved_motion.json").exists()


async def test_raw_uuid_motion_target_rejected(tmp_path):
    motion = make_motion()
    motion["groups"]["roof"] = ["44444444-4444-4444-4444-444444444444"]
    root = make_package(tmp_path, motion=motion)
    fake = make_fake_native(root)
    await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "motion_member_unmapped")


async def test_group_name_shadowing_canonical_id_rejected(tmp_path):
    # A group named exactly like a canonical id would silently shadow it:
    # the compiler resolves group names before bare targets, so target
    # "setA" would animate the authored group instead of the whole set.
    motion = make_motion()
    motion["groups"]["setA"] = ["setA_member_0000"]
    root = make_package(tmp_path, motion=motion)
    fake = make_fake_native(root)
    err = await expect_error(
        dwp.prepare_take({"package_root": str(root)}, call_native=fake),
        "package_invalid")
    assert "setA" in str(err)
    # Collision detected during derivation — no partial artifacts.
    assert not (root / "member_map.json").exists()
    assert not (root / "resolved_motion.json").exists()


async def test_mcp_dispatch_prepare_take():
    """Mirrors the call_tool + AsyncMock pattern of test_director_take_package.py.

    NOTE: the wire success shape is the `data` payload directly (see
    server._format_tool_result docstring) -- NOT a {success, data} envelope.
    """
    from unittest.mock import AsyncMock, patch

    from rook import server, targeting

    with patch.object(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ]):
        with patch.object(server.director_worker_prepare, "prepare_take",
                          new_callable=AsyncMock) as mock_prepare:
            mock_prepare.return_value = {"phase": "prepared", "take_id": "take1"}
            result = await server.call_tool(
                "rhino_director_prepare_take", {"package_root": "C:/takes/take1"})
        mock_prepare.assert_awaited_once()
    payload = json.loads(result[0].text)
    assert payload["phase"] == "prepared"
    assert payload["take_id"] == "take1"
