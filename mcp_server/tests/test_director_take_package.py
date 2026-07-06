from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rook import director_take_package as dtp

pytestmark = pytest.mark.asyncio

DOC_PATH = "C:/models/live.3dm"
BLOCK = "ROOF_BLOCK"
INSTANCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"


def _doc_data(modified: bool = False, object_count: int = 112) -> dict[str, Any]:
    return {"name": "live.3dm", "path": DOC_PATH, "modified": modified,
            "objectCount": object_count, "layerCount": 5, "units": "millimeters"}


def _members(loose_second: bool = False) -> list[dict[str, Any]]:
    return [
        {"id": "8136d5f4-6d5c-47df-8f89-590df238c8e7", "index": 0, "type": "Brep",
         "layer": "001_MATERIAL::001_01_GARDEN WOOD", "name": "",
         "bbox": {"min": [0, 0, 0], "max": [10.123456, 10, 10]},
         "bboxMethod": "tight_object", "visible": True},
        {"id": "9247e6a5-7e6d-58e0-9f9a-6a1ef349d9f8", "index": 1, "type": "Curve",
         "layer": "000_SETOUT LINES::000_SETOUT_PRIMARY", "name": "axis",
         "bbox": {"min": [0, 0, 0], "max": [5, 0, 0]},
         "bboxMethod": "loose_fallback" if loose_second else "tight_object",
         "visible": True},
    ]


IDENTITY_XFORM = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
                  [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def make_fake_native(*, modified=False, save_copy_ok=True, invariants_hold=True,
                     modes=("Arctic", "Render_Layer_Color_AMR"), drift=False,
                     loose_second_member=False, instance_id=INSTANCE_ID,
                     member_drift=False, instance_xform_drift=False,
                     legacy_evidence=False):
    calls: list[tuple[str, str, dict | None]] = []
    doc_reads = {"n": 0}
    member_reads = {"n": 0}
    instance_reads = {"n": 0}

    async def fake(endpoint: str, method: str = "GET", data: dict | None = None,
                   port: int | None = None, **kwargs: Any):
        calls.append((endpoint, method, data))
        if endpoint == "/document":
            doc_reads["n"] += 1
            count = 112 if (doc_reads["n"] == 1 or not drift) else 999
            return {"success": True, "data": _doc_data(modified=modified, object_count=count)}
        if endpoint == "/document/save-copy":
            if not save_copy_ok:
                return {"success": False, "data": "route not found"}
            target = data["path"]
            Path(target).write_bytes(b"3D Geometry File Format fake")
            if legacy_evidence:
                # Old native build: no title/save_small fields in evidence.
                return {"success": True, "data": {
                    "copy_path": target, "path_before": DOC_PATH,
                    "path_after": DOC_PATH, "modified_before": modified,
                    "modified_after": modified}}
            after = modified if invariants_hold else (not modified)
            return {"success": True, "data": {
                "copy_path": target, "path_before": DOC_PATH, "path_after": DOC_PATH,
                "title_before": "live", "title_after": "live",
                "modified_before": modified, "modified_after": after,
                "save_small_used": False}}
        if endpoint == "/block/instances":
            assert data == {"name": BLOCK}
            instance_reads["n"] += 1
            xform = IDENTITY_XFORM
            if instance_xform_drift and instance_reads["n"] > 1:
                # Same instance id, moved between enumeration and snapshot.
                xform = [[1.0, 0.0, 0.0, 5.0], [0.0, 1.0, 0.0, 0.0],
                         [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
            return {"success": True, "data": {"blockName": BLOCK, "instances": [{
                "id": instance_id, "layer": "004_DIAGRAM::STRUCTURE", "name": "",
                "xform": xform,
                "definitionId": "d1d1d1d1-0000-0000-0000-000000000001",
                "definitionName": BLOCK}]}}
        if endpoint == "/block/objects-detailed":
            assert data == {"name": BLOCK}
            member_reads["n"] += 1
            members = _members(loose_second=loose_second_member)
            if member_drift and member_reads["n"] > 1:
                # Simulate a dirty-doc edit between enumeration and snapshot:
                # same count, changed layer — object count would NOT catch this.
                members[0]["layer"] = "001_MATERIAL::001_01_CONCRETE"
            return {"success": True, "data": {"name": BLOCK, "objects": members}}
        if endpoint == "/display-modes":
            return {"success": True, "data": {"modes": [
                {"id": f"id-{m}", "name": m, "isActive": False} for m in modes]}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    fake.calls = calls
    return fake


def _args(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "output_root": str(tmp_path / "packages"),
        "take_id": "take_001",
        "actor_sets": [{"actor_set_id": "roof_001", "block_name": BLOCK,
                        "source_top_level_object_id": INSTANCE_ID}],
        "motion": {"timeline": {"fps": 24, "frame_count": 48},
                   "motion": [{"target": "roof_001",
                               "keyframes": [{"t": 1, "translate": [0, 0, 8000]}]}]},
        "camera": None,
        "display_modes": ["Arctic", "Render_Layer_Color_AMR"],
    }
    args.update(overrides)
    return args


async def test_happy_path_writes_package(tmp_path):
    fake = make_fake_native()
    result = await dtp.package_take(_args(tmp_path), call_native=fake)

    root = Path(result["package_root"])
    assert root == tmp_path / "packages" / "take_001"
    for f in ("scene.3dm", "scene_manifest.json", "motion.json", "status.json"):
        assert (root / f).is_file(), f
    assert not (root / "camera.json").exists()  # camera was None
    # Staging dir was promoted atomically; no remnant left behind.
    assert not (tmp_path / "packages" / ".take_001.staging").exists()

    manifest = json.loads((root / "scene_manifest.json").read_text())
    assert manifest["schema_version"] == dtp.PACKAGE_SCHEMA_VERSION
    assert manifest["scene"]["mechanism"] == "save_copy"
    assert manifest["source_document"]["path"] == DOC_PATH
    [actor_set] = manifest["actor_sets"]
    assert actor_set["member_count"] == 2
    src = actor_set["source_instance"]
    assert src["instance_id"] == INSTANCE_ID
    assert src["definition_name"] == BLOCK
    assert src["definition_id"] == "d1d1d1d1-0000-0000-0000-000000000001"
    assert src["xform"] == IDENTITY_XFORM
    assert len(src["xform_sha256"]) == 64
    m0 = actor_set["members"][0]
    assert m0["actor_member_id"] == "roof_001_member_0000"
    assert m0["definition_object_index"] == 0
    assert m0["definition_object_id"] == "8136d5f4-6d5c-47df-8f89-590df238c8e7"
    assert m0["expected"]["layer"] == "001_MATERIAL::001_01_GARDEN WOOD"
    assert m0["bbox_evidence"]["bbox_method"] == "tight_object"
    assert m0["bbox_evidence"]["validation_strength"] == "tight_bbox"
    assert m0["bbox_evidence"]["rounding_policy"] == "round_to_4_decimal_places"
    assert m0["bbox_evidence"]["max"][0] == 10.1235  # rounded to 4 decimals
    dm = {d["name"]: d for d in manifest["display_mode_requirements"]}
    assert dm["Arctic"]["id"] == "id-Arctic"
    assert manifest["hashes"]["motion_json_sha256"] == result["hashes"]["motion_json_sha256"]
    assert manifest["hashes"]["scene_3dm_sha256"]

    status = json.loads((root / "status.json").read_text())
    assert status["phase"] == "packaged"
    assert status["package_id"] == result["package_id"]


async def test_modified_doc_without_save_copy_fails_document_not_saved(tmp_path):
    fake = make_fake_native(modified=True, save_copy_ok=False)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "document_not_saved"


async def test_unmodified_doc_without_save_copy_falls_back_to_raw_copy(tmp_path):
    src = tmp_path / "live.3dm"
    src.write_bytes(b"3D Geometry File Format fake-saved")
    fake = make_fake_native(modified=False, save_copy_ok=False)
    args = _args(tmp_path)
    result = await dtp.package_take(args, call_native=fake, source_path_override=str(src))
    manifest = json.loads((Path(result["package_root"]) / "scene_manifest.json").read_text())
    assert manifest["scene"]["mechanism"] == "raw_copy_saved_file"


async def test_save_copy_invariant_violation_is_typed(tmp_path):
    fake = make_fake_native(invariants_hold=False)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "save_copy_invariant_violation"


async def test_missing_display_mode_fails(tmp_path):
    fake = make_fake_native(modes=("Arctic",))
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "display_mode_missing"
    assert "Render_Layer_Color_AMR" in str(exc.value)


async def test_existing_package_dir_conflicts(tmp_path):
    (tmp_path / "packages" / "take_001").mkdir(parents=True)
    fake = make_fake_native()
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_already_exists"


async def test_document_drift_between_enumeration_and_finish_fails(tmp_path):
    fake = make_fake_native(drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"


async def test_bad_take_id_rejected(tmp_path):
    fake = make_fake_native()
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path, take_id="../evil"), call_native=fake)
    assert exc.value.code == "invalid_input"


async def test_loose_bbox_member_fails_tight_bbox_unavailable(tmp_path):
    """DEC-021: tight_object is the only admissible manifest bbox evidence."""
    fake = make_fake_native(loose_second_member=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "tight_bbox_unavailable"
    # The failing member is named so the user can fix or exclude it.
    assert "roof_001_member_0001" in str(exc.value)


async def test_id_not_an_instance_of_block_fails_source_instance_mismatch(tmp_path):
    """The claimed source id must be a CURRENT instance of the named block."""
    fake = make_fake_native(instance_id="00000000-0000-0000-0000-000000000099")
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "source_instance_mismatch"


async def test_actor_member_drift_after_snapshot_fails(tmp_path):
    """Same object count, changed member layer between enumeration and
    snapshot: the deep actor-state gate must catch what count cannot."""
    fake = make_fake_native(member_drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"
    # Atomicity: a failed run must not create the final package directory,
    # so a retry never hits package_already_exists.
    assert not (tmp_path / "packages" / "take_001").exists()


async def test_source_instance_xform_drift_after_snapshot_fails(tmp_path):
    """Same instance id, moved (xform changed) between enumeration and
    snapshot: instance identity/xform drift is gated, not just members."""
    fake = make_fake_native(instance_xform_drift=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "package_state_drift"
    assert not (tmp_path / "packages" / "take_001").exists()


async def test_legacy_save_copy_evidence_fails_invariant_check(tmp_path):
    """Old native builds returning partial evidence (no title/save_small
    fields) must not pass the invariant gate."""
    fake = make_fake_native(legacy_evidence=True)
    with pytest.raises(dtp.DirectorTakePackageError) as exc:
        await dtp.package_take(_args(tmp_path), call_native=fake)
    assert exc.value.code == "save_copy_invariant_violation"
    assert "title" in str(exc.value)


async def test_mcp_tool_is_registered_and_dispatches():
    """Mirrors the call_tool + AsyncMock pattern of test_director_mcp_tools.py."""
    from unittest.mock import AsyncMock, patch

    from rook import server, targeting

    with patch.object(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ]):
        request = {"take_id": "t", "output_root": "C:/x", "actor_sets": [],
                   "motion": {}, "display_modes": ["Arctic"]}
        with patch.object(server.director_take_package, "package_take",
                          new_callable=AsyncMock) as mock:
            mock.return_value = {"package_root": "C:/x/t", "package_id": "t-abc",
                                 "take_id": "t"}
            result = await server.call_tool("rhino_director_package_take", request)
        mock.assert_awaited_once()
        assert "t-abc" in result[0].text
