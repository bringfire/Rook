"""Slice 4A live gates: package -> prepare -> compile -> capture -> video.

DOCUMENT-SWITCHING TESTS. Gates A-C require ROOK_S4A_CAPTURE=1; Gate D
requires ROOK_S4A_THROUGHPUT=1. Run only with an unmodified SAVED SCRATCH
document open in Rhino.

The fixtures are temporarily saved into that scratch document before packaging.
Cleanup reopens the scratch document, deletes fixture block definitions and
instances, saves again, and asserts the original object count is restored.

Do NOT run these on a project file. A mid-gate failure can leave the fixture
saved in the document until cleanup is re-run manually. Gate A keeps its first
v3 video artifact only when ROOK_S4A_KEEP_OUTPUT=1.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from rook.bridge import native_client
import pytest

from rook import director_take_package as dtp
from rook import director_video as dvid
from rook import director_worker_capture as dwcap
from rook import director_worker_compile as dwc
from rook import director_worker_prepare as dprep
from .conftest import _create_brep

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

CAPTURE_SKIP = pytest.mark.skipif(
    os.environ.get("ROOK_S4A_CAPTURE") != "1",
    reason="Set ROOK_S4A_CAPTURE=1 to run Slice 4A capture live gates.",
)
THROUGHPUT_SKIP = pytest.mark.skipif(
    os.environ.get("ROOK_S4A_THROUGHPUT") != "1",
    reason="Set ROOK_S4A_THROUGHPUT=1 to run Slice 4A throughput gate.",
)


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _call_live_native(endpoint: str, method: str = "GET",
                            data: dict[str, Any] | None = None,
                            port: int | None = None) -> dict[str, Any]:
    del port
    base_url = _require_host()
    async with native_client(timeout=900.0) as client:
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


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _call_live_native(route, "POST", body)


async def _get(route: str) -> dict[str, Any]:
    return await _call_live_native(route, "GET", None)


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
    envelope_json = await _call_live_native(
        "/block", "DELETE", {"name": name, "deleteInstances": True})
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


def _capture_motion(actor_set_id: str, frame_count: int = 24) -> dict[str, Any]:
    # Verified against director_motion._parse_key: rotate uses angle_degrees,
    # not angle_deg; rotate also takes axis+pivot and scale accepts a 3-vector.
    return {
        "timeline": {"fps": 24, "frame_count": frame_count},
        "groups": {"moving": [actor_set_id]},
        "motion": [{
            "target": "moving",
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


def _scale_motion(actor_set_id: str) -> dict[str, Any]:
    return {
        "timeline": {"fps": 24, "frame_count": 60},
        "groups": {"moving": [actor_set_id]},
        "motion": [{
            "target": "moving",
            "keyframes": [
                {"t": 0},
                {"t": 1, "translate": [0.0, 0.0, 10.0]},
            ],
        }],
    }


async def _package_prepare_compile(root: Path, *, take_id: str,
                                   block_name: str, actor_set_id: str,
                                   instance_id: str, motion: dict[str, Any],
                                   display_modes: list[str]) -> str:
    package = await dtp.package_take({
        "take_id": take_id,
        "output_root": str(root),
        "actor_sets": [{
            "actor_set_id": actor_set_id,
            "block_name": block_name,
            "source_top_level_object_id": instance_id,
        }],
        "motion": motion,
        "display_modes": display_modes,
    })
    package_root = package["package_root"]
    prepare = await dprep.prepare_take({"package_root": package_root})
    assert prepare["phase"] == "prepared"
    compile_result = await dwc.compile_take({"package_root": package_root})
    assert compile_result["phase"] == "compiled"
    return package_root


async def _build_capture_package(tmp_path: Path, *, run: str,
                                 original_path: str, block_names: list[str],
                                 take_id: str, actor_set_id: str,
                                 display_modes: list[str],
                                 object_count: int = 3,
                                 motion: dict[str, Any] | None = None) -> str:
    block_name = f"S4AGate_{run}_{actor_set_id}"
    object_ids: list[str] = []
    for i in range(object_count):
        x = float(i % 30) * 2.0
        y = float(i // 30) * 2.0
        object_ids.append(await _create_brep(
            [x, y, 0.0], [x + 1.0, y + 1.0, 1.0],
            f"s4a_{run}_{actor_set_id}_{i:03d}"))
    await _make_block(block_name, object_ids)
    block_names.append(block_name)
    instance_id = await _instance_id(block_name)
    await _save_document(original_path)
    return await _package_prepare_compile(
        tmp_path, take_id=take_id, block_name=block_name,
        actor_set_id=actor_set_id, instance_id=instance_id,
        motion=motion or _capture_motion(actor_set_id),
        display_modes=display_modes)


def _run_status(run_root: Path) -> dict[str, Any]:
    return json.loads((run_root / "status.json").read_text(encoding="utf-8"))


def _track_context(package_root: str) -> tuple[int, float]:
    track = json.loads((Path(package_root) / "track.json").read_text(encoding="utf-8"))
    return int(track["frame_count"]), float(track["fps"])


async def _capture_take(package_root: str, *, passes: list[dict[str, str]],
                        width: int = 1280, height: int = 720) -> dict[str, Any]:
    return await dwcap.capture_take({
        "package_root": package_root,
        "passes": passes,
        "resolution": {"width": width, "height": height},
    }, call_native=_call_live_native)


async def _assemble_video_direct(run_root: Path, *, frame_count: int,
                                 fps: float, width: int,
                                 height: int) -> Path:
    output_path = run_root / "videos" / "take.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "schema_version": dvid.SCHEMA_VERSION,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": frame_count,
        "fps": fps,
        "fps_source": "timeline",
        "width": width,
        "height": height,
        "output_path": str(output_path),
        "codec": "h264",
        "container": "mp4",
    }
    envelope_json = await _call_live_native(
        "/director/video-assemble", "POST", request)
    assert envelope_json.get("success"), envelope_json
    assert output_path.is_file() and output_path.stat().st_size > 0
    return output_path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _director_output_root() -> Path:
    # Must match the already-running Rhino process. A pytest-local
    # ROOK_DIRECTOR_OUTPUT_ROOT monkeypatch does not cross the process boundary,
    # so this agrees with native unless Rhino itself was launched with that env.
    return dvid._default_output_root()


def _cleanup_take_dir(output_root: Path, take_id: str, *, keep: bool = False) -> None:
    if keep:
        return
    shutil.rmtree(output_root / "takes" / take_id, ignore_errors=True)


@CAPTURE_SKIP
async def test_gate_a_single_pass_to_video(tmp_path):
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    mode = os.environ.get("ROOK_S4A_MODE", "Arctic")
    take_id = f"s4a_gate_a_{run}"
    output_root = _director_output_root()
    block_names: list[str] = []
    keep_output = os.environ.get("ROOK_S4A_KEEP_OUTPUT") == "1"
    try:
        package_root = await _build_capture_package(
            tmp_path, run=run, original_path=original_path,
            block_names=block_names, take_id=take_id, actor_set_id="s4a",
            display_modes=[mode])
        result = await _capture_take(package_root, passes=[{
            "type": "display_mode",
            "pass_id": "arctic",
            "display_mode": mode,
        }])
        pass_result = result["passes"][0]
        run_root = Path(pass_result["run_root"])
        frame_count, fps = _track_context(package_root)
        assert frame_count == 24
        assert pass_result["frames_written"] == 24
        assert _run_status(run_root)["state"] == "complete"
        output_path = await _assemble_video_direct(
            run_root, frame_count=frame_count, fps=fps,
            width=1280, height=720)
        print(f"S4A Gate A first v3 video: {output_path}")
        if keep_output:
            print(f"S4A Gate A kept take dir: {output_root / 'takes' / take_id}")
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))
        _cleanup_take_dir(output_root, take_id, keep=keep_output)


@CAPTURE_SKIP
async def test_gate_b_two_pass_fidelity(tmp_path):
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    mode_a = os.environ.get("ROOK_S4A_MODE", "Arctic")
    mode_b = os.environ.get("ROOK_S4A_MODE_B", "Pen")
    take_id = f"s4a_gate_b_{run}"
    output_root = _director_output_root()
    block_names: list[str] = []
    try:
        package_root = await _build_capture_package(
            tmp_path, run=run, original_path=original_path,
            block_names=block_names, take_id=take_id, actor_set_id="s4b",
            display_modes=[mode_a, mode_b])
        result = await _capture_take(package_root, passes=[
            {"type": "display_mode", "pass_id": "arctic", "display_mode": mode_a},
            {"type": "display_mode", "pass_id": "pen", "display_mode": mode_b},
        ])
        by_id = {entry["pass_id"]: entry for entry in result["passes"]}
        arctic_root = Path(by_id["arctic"]["run_root"])
        pen_root = Path(by_id["pen"]["run_root"])
        assert _run_status(arctic_root)["state"] == "complete"
        assert _run_status(pen_root)["state"] == "complete"
        arctic_frame = arctic_root / "frames" / "frame_0012.png"
        pen_frame = pen_root / "frames" / "frame_0012.png"
        assert _sha256_file(arctic_frame) != _sha256_file(pen_frame)
        # Human fidelity check: when running this gate interactively, inspect
        # these paths before cleanup if visual mode/layer encoding is in doubt.
        print(f"S4A Gate B {mode_a} frame 12: {arctic_frame}")
        print(f"S4A Gate B {mode_b} frame 12: {pen_frame}")
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))
        _cleanup_take_dir(output_root, take_id)


@CAPTURE_SKIP
async def test_gate_c_display_mode_fail_hard(tmp_path):
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    take_id = f"s4a_gate_c_{run}"
    output_root = _director_output_root()
    block_names: list[str] = []
    try:
        package_root = await _build_capture_package(
            tmp_path, run=run, original_path=original_path,
            block_names=block_names, take_id=take_id, actor_set_id="s4c",
            display_modes=["Arctic"])
        with pytest.raises(dwcap.DirectorWorkerCaptureError) as exc_info:
            await _capture_take(package_root, passes=[{
                "type": "display_mode",
                "pass_id": "missing_mode",
                "display_mode": "RookNoSuchMode_S4A",
            }])
        assert exc_info.value.code == "display_mode_missing"
        run_root = output_root / "takes" / take_id / "missing_mode"
        assert _run_status(run_root)["state"] == "failed"
        frames = list((run_root / "frames").glob("*.png"))
        assert frames == []
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))
        _cleanup_take_dir(output_root, take_id)


@THROUGHPUT_SKIP
async def test_gate_d_capture_throughput(tmp_path):
    before, original_path = await _assert_clean_scratch_doc()
    run = uuid4().hex[:8]
    mode = os.environ.get("ROOK_S4A_MODE", "Arctic")
    take_id = f"s4a_gate_d_{run}"
    output_root = _director_output_root()
    block_names: list[str] = []
    try:
        package_root = await _build_capture_package(
            tmp_path, run=run, original_path=original_path,
            block_names=block_names, take_id=take_id, actor_set_id="s4scale",
            display_modes=[mode], object_count=300,
            motion=_scale_motion("s4scale"))
        result = await _capture_take(package_root, passes=[{
            "type": "display_mode",
            "pass_id": "throughput",
            "display_mode": mode,
        }])
        capture_ms = result["passes"][0]["capture_ms"]
        assert result["passes"][0]["frames_written"] == 60
        mean_vs_s3 = capture_ms["mean"] / 19.2
        print(
            "S4A Gate D capture throughput: "
            f"capture_ms={capture_ms}, mean_vs_s3_transform={mean_vs_s3:.3f}x")
    finally:
        await _restore_and_cleanup(
            original_path, block_names, before.get("objectCount"))
        _cleanup_take_dir(output_root, take_id)
