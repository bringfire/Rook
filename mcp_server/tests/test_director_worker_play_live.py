"""Slice 3 live gates: package -> prepare -> compile -> worker play.

DOCUMENT-SWITCHING TESTS. Require ROOK_S3_DOC_SWITCH=1, an unmodified live
document, and a SAVED SCRATCH document. The fixtures are temporarily saved
into that scratch document before packaging; the cleanup reopens the scratch
document, deletes fixture block definitions and instances, saves again, and
asserts the original object count is restored.

Do NOT run these on a project file. A mid-gate failure can leave the fixture
saved in the document until cleanup is re-run manually. Gate D additionally
requires ROOK_S3_SCALE=1 because it creates a larger synthetic actor set and
prints the throughput measurement used to size Slice 4 capture work.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from rook.bridge import native_client
import pytest

from rook import director_take_package as dtp
from rook import director_worker_compile as dwc
from rook import director_worker_play as dwp
from rook import director_worker_prepare as dprep
from .conftest import _create_brep
from .test_director_worker_play import envelope

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_opt_in() -> None:
    if os.environ.get("ROOK_S3_DOC_SWITCH") != "1":
        pytest.skip("Set ROOK_S3_DOC_SWITCH=1 to allow document switching.")


def _require_scale_opt_in() -> None:
    if os.environ.get("ROOK_S3_SCALE") != "1":
        pytest.skip("Set ROOK_S3_SCALE=1 to run the Slice 3 throughput gate.")


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url = _require_host()
    async with native_client(timeout=180.0) as client:
        resp = await client.post(f"{base_url}{route}", json=body)
    return resp.json()


async def _call_live_native(endpoint: str, method: str = "GET",
                            data: dict[str, Any] | None = None,
                            port: int | None = None) -> dict[str, Any]:
    del port
    base_url = _require_host()
    async with native_client(timeout=180.0) as client:
        if method == "GET":
            resp = await client.get(f"{base_url}{endpoint}")
        elif method == "DELETE":
            resp = await client.request(
                "DELETE", f"{base_url}{endpoint}",
                json=data if data is not None else None)
        else:
            resp = await client.post(
                f"{base_url}{endpoint}",
                json=data if data is not None else {})
    return resp.json()


async def _get(route: str) -> dict[str, Any]:
    base_url = _require_host()
    async with native_client(timeout=30.0) as client:
        resp = await client.get(f"{base_url}{route}")
    return resp.json()


async def _doc() -> dict[str, Any]:
    envelope_json = await _get("/document")
    assert envelope_json.get("success"), envelope_json
    return envelope_json["data"]


async def _make_block(name: str, object_ids: list[str]) -> dict[str, Any]:
    envelope_json = await _post("/block/create", {
        "name": name,
        "ids": object_ids,
        "basePoint": [0.0, 0.0, 0.0],
        "replaceWithInstance": True,
    })
    assert envelope_json.get("success"), envelope_json
    return envelope_json["data"]


async def _instance_id(block_name: str) -> str:
    envelope_json = await _post("/block/instances", {"name": block_name})
    assert envelope_json.get("success"), envelope_json
    instances = envelope_json["data"].get("instances") or []
    assert len(instances) == 1, instances
    return instances[0]["id"]


async def _save_document(path: str) -> None:
    envelope_json = await _post("/document/save", {"path": path})
    assert envelope_json.get("success"), envelope_json


async def _delete_block(name: str) -> None:
    base_url = _require_host()
    async with native_client(timeout=30.0) as client:
        resp = await client.request(
            "DELETE", f"{base_url}/block",
            json={"name": name, "deleteInstances": True})
    envelope_json = resp.json()
    assert envelope_json.get("success"), envelope_json


async def _restore_and_cleanup(original_path: str, block_names: list[str],
                               before_count: int | None) -> None:
    restore = await _post("/document/open", {"path": original_path})
    assert restore.get("success"), restore
    after_open = await _doc()
    assert (after_open.get("path") or "").lower() == original_path.lower()

    for name in block_names:
        await _delete_block(name)
    await _save_document(original_path)

    final = await _doc()
    if before_count is not None:
        assert final.get("objectCount") == before_count, (
            "fixture cleanup left residue objects")
    assert not final.get("modified")


async def _assert_clean_scratch_doc() -> tuple[dict[str, Any], str]:
    before = await _doc()
    if before.get("modified"):
        pytest.skip("Live document has unsaved changes; save the scratch doc first.")
    original_path = before.get("path") or ""
    assert original_path, "live document must have a path to restore to"
    return before, original_path


async def _package_prepare_compile(root: Path, *, take_id: str, block_name: str,
                                   actor_set_id: str, instance_id: str,
                                   motion: dict[str, Any]) -> str:
    package = await dtp.package_take({
        "take_id": take_id,
        "output_root": str(root),
        "actor_sets": [{
            "actor_set_id": actor_set_id,
            "block_name": block_name,
            "source_top_level_object_id": instance_id,
        }],
        "motion": motion,
        "display_modes": ["Shaded"],
    })
    package_root = package["package_root"]
    prepare = await dprep.prepare_take({"package_root": package_root})
    assert prepare["phase"] == "prepared"
    compile_result = await dwc.compile_take({"package_root": package_root})
    assert compile_result["phase"] == "compiled"
    return package_root


async def _play_take_capture_native(package_root: str, args: dict[str, Any]
                                    ) -> tuple[dict[str, Any], dict[str, Any]]:
    native_worker_play: list[dict[str, Any]] = []

    async def capture_call(endpoint: str, method: str = "GET",
                           data: dict[str, Any] | None = None,
                           port: int | None = None) -> dict[str, Any]:
        envelope_json = await _call_live_native(endpoint, method, data, port)
        if endpoint == "/director/worker-play":
            native_worker_play.append(envelope_json)
        return envelope_json

    request = {"package_root": package_root, **args}
    result = await dwp.play_take(request, call_native=capture_call)
    assert native_worker_play, "play_take did not call native worker-play"
    native_envelope = native_worker_play[-1]
    assert native_envelope.get("success"), native_envelope
    return result, native_envelope["data"]


def _assert_probe_matches_track_envelope(package_root: str, probe: dict[str, Any],
                                         *, tolerance: float) -> None:
    track = json.loads((Path(package_root) / "track.json").read_text(encoding="utf-8"))
    frame_index = probe["frameIndex"]
    frame = track["object_frames"][frame_index - 1]
    by_id = {
        entry["object_id"]: entry
        for entry in frame["object_transforms"]
    }
    for observed in probe["objects"]:
        object_id = observed["objectId"]
        track_entry = by_id[object_id]
        source = track_entry["source_state"]
        expected_min, expected_max = envelope(
            source["bbox_min"], source["bbox_max"], track_entry["transform"])
        assert observed["bboxMin"] == pytest.approx(expected_min, abs=tolerance)
        assert observed["bboxMax"] == pytest.approx(expected_max, abs=tolerance)


def _probe_at(native_data: dict[str, Any], frame_index: int) -> dict[str, Any]:
    matches = [
        probe for probe in native_data.get("probes", [])
        if probe.get("frameIndex") == frame_index
    ]
    assert len(matches) == 1, native_data.get("probes")
    return matches[0]


def _assert_probe_bboxes_agree(left: dict[str, Any], right: dict[str, Any],
                               *, tolerance: float) -> None:
    left_objects = {
        item["objectId"]: item
        for item in left.get("objects", [])
    }
    right_objects = {
        item["objectId"]: item
        for item in right.get("objects", [])
    }
    assert set(left_objects) == set(right_objects)
    for object_id, left_obj in left_objects.items():
        right_obj = right_objects[object_id]
        assert right_obj["bboxMin"] == pytest.approx(
            left_obj["bboxMin"], abs=tolerance)
        assert right_obj["bboxMax"] == pytest.approx(
            left_obj["bboxMax"], abs=tolerance)


def _gate_a_motion(actor_set_id: str) -> dict[str, Any]:
    # Verified against director_motion._parse_key: rotate requires
    # {axis, angle_degrees, pivot}; scale accepts a 3-vector; translate
    # accepts a 3-vector.
    return {
        "timeline": {"fps": 24, "frame_count": 24},
        "groups": {},
        "motion": [{
            "target": f"{actor_set_id}_member_0000",
            "keyframes": [
                {"t": 0},
                {
                    "t": 1,
                    "translate": [10.0, 0.0, 0.0],
                    "rotate": {
                        "axis": [0.0, 0.0, 1.0],
                        "angle_degrees": 45.0,
                        "pivot": [5.0, 0.0, 0.0],
                    },
                    "scale": [1.0, 1.5, 2.0],
                },
            ],
        }],
    }


async def test_gate_a_composition_order(tmp_path):
    _require_opt_in()
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    block_name = f"S3GateA_{run}"
    block_names: list[str] = []

    try:
        box = await _create_brep([4.0, 0.0, 0.0], [5.0, 2.0, 3.0],
                                 f"s3_gate_a_box_{run}")
        await _make_block(block_name, [box])
        block_names.append(block_name)
        instance_id = await _instance_id(block_name)
        await _save_document(original_path)

        package_root = await _package_prepare_compile(
            tmp_path, take_id=f"s3_gate_a_{run}", block_name=block_name,
            actor_set_id="s3a", instance_id=instance_id,
            motion=_gate_a_motion("s3a"))
        result, native_data = await _play_take_capture_native(package_root, {
            "probe_frames": [12, 24],
            "reset": True,
        })
        assert result["played_to"] == 24
        probes = native_data["probes"]
        assert {probe["frameIndex"] for probe in probes} == {12, 24}
        tolerance = native_data["drift"]["tolerance"]
        for probe in probes:
            _assert_probe_matches_track_envelope(
                package_root, probe, tolerance=tolerance)
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))


async def _build_gate_a_package(tmp_path: Path, run: str,
                                original_path: str,
                                block_names: list[str]) -> tuple[str, str]:
    block_name = f"S3GateReset_{run}"
    box = await _create_brep([4.0, 0.0, 0.0], [5.0, 2.0, 3.0],
                             f"s3_gate_reset_box_{run}")
    await _make_block(block_name, [box])
    block_names.append(block_name)
    instance_id = await _instance_id(block_name)
    await _save_document(original_path)
    package_root = await _package_prepare_compile(
        tmp_path, take_id=f"s3_gate_reset_{run}", block_name=block_name,
        actor_set_id="s3r", instance_id=instance_id,
        motion=_gate_a_motion("s3r"))
    return package_root, block_name


async def test_gate_b_reset_authority(tmp_path):
    _require_opt_in()
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    block_names: list[str] = []
    try:
        package_root, block_name = await _build_gate_a_package(
            tmp_path, run, original_path, block_names)

        first, first_native = await _play_take_capture_native(package_root, {
            "reset": True,
            "probe_frames": [24],
        })
        second, second_native = await _play_take_capture_native(package_root, {
            "reset": True,
            "probe_frames": [24],
        })
        assert first["played_to"] == second["played_to"] == 24
        first_probe = _probe_at(first_native, 24)
        second_probe = _probe_at(second_native, 24)
        tolerance = max(
            first_native["drift"]["tolerance"],
            second_native["drift"]["tolerance"])
        _assert_probe_bboxes_agree(
            first_probe, second_probe, tolerance=tolerance)
        status = json.loads((Path(package_root) / "status.json").read_text(encoding="utf-8"))
        assert len(status["evidence"]["play_runs"]) >= 2
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))


async def test_gate_c_pristine_gate_fires(tmp_path):
    _require_opt_in()
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    block_names: list[str] = []
    try:
        package_root, block_name = await _build_gate_a_package(
            tmp_path, run, original_path, block_names)

        await dwp.play_take({"package_root": package_root, "reset": True})
        with pytest.raises(dwp.DirectorWorkerPlayError) as exc_info:
            await dwp.play_take({"package_root": package_root, "reset": False})
        assert exc_info.value.code == "worker_scene_not_pristine"
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))


async def test_gate_d_throughput_measurement(tmp_path):
    _require_opt_in()
    _require_scale_opt_in()
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    block_name = f"S3GateScale_{run}"
    block_names: list[str] = []
    try:
        ids = []
        for i in range(300):
            x = float(i % 30) * 2.0
            y = float(i // 30) * 2.0
            ids.append(await _create_brep(
                [x, y, 0.0], [x + 1.0, y + 1.0, 1.0],
                f"s3_scale_{run}_{i:03d}"))
        await _make_block(block_name, ids)
        block_names.append(block_name)
        instance_id = await _instance_id(block_name)
        await _save_document(original_path)

        motion = {
            "timeline": {"fps": 24, "frame_count": 60},
            "groups": {"moving": ["s3scale"]},
            "motion": [{
                "target": "moving",
                "keyframes": [
                    {"t": 0},
                    {"t": 1, "translate": [0.0, 0.0, 10.0]},
                ],
            }],
        }
        package_root = await _package_prepare_compile(
            tmp_path, take_id=f"s3_gate_scale_{run}",
            block_name=block_name, actor_set_id="s3scale",
            instance_id=instance_id, motion=motion)
        result = await dwp.play_take({"package_root": package_root, "reset": True})
        assert result["played_to"] == 60
        assert result["drift"]
        status = json.loads((Path(package_root) / "status.json").read_text(encoding="utf-8"))
        run_evidence = status["evidence"]["play_runs"][-1]
        total_ms = run_evidence["timing_total_ms"]
        mean_ms = total_ms / 60.0
        print(f"S3 Gate D throughput: total_ms={total_ms:.3f}, mean_frame_ms={mean_ms:.3f}")
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))
