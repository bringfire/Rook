from __future__ import annotations

import json
import math
import os
import struct
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from rook.bridge import native_client
import pytest

from rook import director, director_publish, director_video, server
from .conftest import _block_create, _block_insert, _create_brep


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post_director(route: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    base_url = _require_host()
    async with native_client(timeout=30.0) as client:
        resp = await client.post(f"{base_url}/director/{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/director/{route} returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _create_line_curve(name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {
            "type": "LINE",
            "start": [0.0, 0.0, 0.0],
            "end": [10.0, 0.0, 0.0],
            "name": name,
        },
    )
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _fixture_objects_by_layer(
    layer: str,
    *,
    object_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from rook.server import _mcp_tool_executor

    request: dict[str, Any] = {"layer": layer, "limit": limit}
    if object_type:
        request["type"] = object_type
    result = await _mcp_tool_executor("rhino_objects", request)
    if not isinstance(result, dict) or not isinstance(result.get("objects"), list):
        pytest.fail(f"rhino_objects returned unexpected result for {layer!r}: {result!r}")
    return result["objects"]


def _point_from_bbox(obj: dict[str, Any]) -> list[float]:
    bbox = obj.get("bbox") if isinstance(obj, dict) else None
    if not isinstance(bbox, dict):
        pytest.fail(f"Point object has no bbox coordinates: {obj!r}")
    minimum = bbox.get("min")
    maximum = bbox.get("max")
    if not isinstance(minimum, list) or not isinstance(maximum, list):
        pytest.fail(f"Point object bbox is malformed: {obj!r}")
    _assert_vector_close(minimum, maximum)
    return [float(value) for value in minimum]


def _vector_distance(a: list[float], b: list[float]) -> float:
    return math.dist([float(value) for value in a], [float(value) for value in b])


def _director_output_root() -> Path:
    configured = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if configured:
        return Path(configured).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        pytest.skip("LOCALAPPDATA is required to infer native director output root.")
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _director_port() -> int | None:
    parsed = urlparse(_require_host())
    return parsed.port


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _translation_matrix(x: float, y: float, z: float) -> list[list[float]]:
    matrix = _identity_matrix()
    matrix[0][3] = x
    matrix[1][3] = y
    matrix[2][3] = z
    return matrix


def _director_source_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "bbox_min": state["bbox_min"],
        "bbox_max": state["bbox_max"],
        "validation_strength": state["validation_strength"],
        "state_hash": state.get("state_hash"),
    }


def _compiled_object_transform(
    object_id: str,
    source_state: dict[str, Any],
    matrix: list[list[float]],
) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "source_state": _director_source_state(source_state),
        "transform": matrix,
    }


def _assert_native_phase_evidence(
    detail: dict[str, Any],
    *,
    expects_instance: bool,
    expected_instance_definition_name: str | None = None,
) -> None:
    required = [
        "transform_call_path",
        "requested_transform",
        "requested_inverse_transform",
        "phase_before_apply",
        "phase_after_apply",
        "phase_before_restore",
        "phase_after_restore",
    ]
    for key in required:
        assert key in detail, detail

    for phase_name in [
        "phase_before_apply",
        "phase_after_apply",
        "phase_before_restore",
        "phase_after_restore",
    ]:
        phase = detail[phase_name]
        assert isinstance(phase, dict), {phase_name: phase}
        for key in [
            "object_found",
            "object_id",
            "runtime_serial_number",
            "object_type",
            "bbox",
            "instance_definition_id",
            "instance_definition_name",
            "instance_xform",
        ]:
            assert key in phase, {phase_name: phase}

        assert phase["object_found"] is True, {phase_name: phase}
        if phase["object_found"]:
            assert isinstance(phase["object_id"], str)
            assert isinstance(phase["runtime_serial_number"], int)
            assert isinstance(phase["object_type"], str)
            assert isinstance(phase["bbox"], dict)
            assert "min" in phase["bbox"] and "max" in phase["bbox"]

            if expects_instance:
                assert phase["object_type"] == "InstanceReference", {phase_name: phase}
                assert isinstance(phase["instance_definition_id"], str)
                assert isinstance(phase["instance_definition_name"], str)
                if expected_instance_definition_name is not None:
                    assert phase["instance_definition_name"] == expected_instance_definition_name
                assert isinstance(phase["instance_xform"], list)
                assert len(phase["instance_xform"]) == 4
            else:
                assert phase["object_type"] != "InstanceReference"


def _phase_summary(phase: dict[str, Any]) -> dict[str, Any]:
    return {
        "object_found": phase.get("object_found"),
        "object_id": phase.get("object_id"),
        "runtime_serial_number": phase.get("runtime_serial_number"),
        "object_type": phase.get("object_type"),
        "bbox": phase.get("bbox"),
        "instance_definition_id": phase.get("instance_definition_id"),
        "instance_definition_name": phase.get("instance_definition_name"),
        "instance_xform": phase.get("instance_xform"),
    }


def _detail_phase_summary(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "restored": detail.get("restored"),
        "bbox_delta_min": detail.get("bbox_delta_min"),
        "bbox_delta_max": detail.get("bbox_delta_max"),
        "bbox_max_delta": detail.get("bbox_max_delta"),
        "phase_before_apply": _phase_summary(detail["phase_before_apply"]),
        "phase_after_apply": _phase_summary(detail["phase_after_apply"]),
        "phase_before_restore": _phase_summary(detail["phase_before_restore"]),
        "phase_after_restore": _phase_summary(detail["phase_after_restore"]),
    }


async def _cleanup_instance_restore_probe(created_ids: list[str], block_name: str) -> None:
    from rook.server import _mcp_tool_executor

    if created_ids:
        await _mcp_tool_executor("rhino_delete", {"ids": created_ids})
    await _mcp_tool_executor(
        "rhino_block_delete",
        {"name": block_name, "deleteInstances": True},
    )


def _assert_vector_close(actual: list[float], expected: list[float], tolerance: float = 1.0e-4) -> None:
    assert len(actual) == len(expected)
    for actual_value, expected_value in zip(actual, expected):
        assert abs(actual_value - expected_value) <= tolerance


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert header[12:16] == b"IHDR"
    return struct.unpack(">II", header[16:24])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _frame_instruction(
    *,
    run_root: Path | None = None,
    output_path: Path | None = None,
    schema_version: int = 1,
    director_version: str = "slice1",
    projection: str = "perspective",
    resolution: dict[str, int] | None = None,
    camera_overrides: dict[str, Any] | None = None,
    object_transforms: Any | None = None,
) -> dict[str, Any]:
    root = run_root or (_director_output_root() / "task8_contract")
    output = output_path or (root / "frames" / "frame_0001.png")
    if object_transforms is None:
        object_transforms = [
            {
                "object_id": "00000000-0000-0000-0000-000000000001",
                "transform": _identity_matrix(),
                "source_state": {
                    "bbox_min": [0, 0, 0],
                    "bbox_max": [1, 1, 1],
                    "validation_strength": "bbox_only",
                    "state_hash": None,
                },
            }
        ]
    camera = {
        "projection": projection,
        "location": [4, -4, 3],
        "target": [0, 0, 0],
        "up": [0, 0, 1],
        "lens_length": 35.0,
        "fov_degrees": 45.0,
        "parallel_scale": None,
        "near_clip": 0.1,
        "far_clip": 1000.0,
        "aspect": 1.7778,
    }
    if camera_overrides:
        camera.update(camera_overrides)
    return {
        "schema_version": schema_version,
        "director_version": director_version,
        "run_id": "task8_contract",
        "frame_index": 1,
        "frame_id": "frame_0001",
        "run_root": str(root),
        "output_path": str(output),
        "resolution": resolution or {"width": 320, "height": 180},
        "display": {"mode": "Rendered"},
        "camera": camera,
        "object_transforms": object_transforms,
    }


def _error_code(envelope: dict[str, Any]) -> str | None:
    data = envelope.get("data")
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
        if isinstance(data.get("code"), str):
            return data["code"]
    return None


async def test_director_view_state_active_view_contract():
    _, envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert envelope["success"] is True
    camera = envelope["data"]["camera"]
    assert camera["projection"] in {"perspective", "parallel"}
    assert len(camera["location"]) == 3
    assert len(camera["target"]) == 3
    assert len(camera["up"]) == 3
    for key in (
        "aspect",
        "lens_length",
        "fov_degrees",
        "parallel_scale",
        "near_clip",
        "far_clip",
    ):
        assert key in camera
    assert envelope["data"]["provenance"]["source"] == "active_view"


async def test_director_object_states_rejects_empty_ids():
    _, envelope = await _post_director("object-states", {"object_ids": []})
    assert envelope["success"] is False
    assert "object_ids" in str(envelope["data"])


async def test_director_curve_samples_live_smoke_samples_line_curve(fresh_document):
    curve_id = await _create_line_curve(f"director_curve_samples_{uuid4().hex}")

    _, envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": curve_id,
            "frame_count": 3,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )

    assert envelope["success"] is True
    data = envelope["data"]
    assert data["schema_version"] == 1
    assert data["curve_id"] == curve_id
    assert data["frame_count"] == 3
    assert data["provenance"]["sampling_mode"] == "normalized_parameter"
    assert data["provenance"]["parameter_mapping"] == "curve_domain_parameter_at"
    assert data["provenance"]["frame_count_source"] == "caller_canonical_frame_count"
    assert data["provenance"]["arc_length_sampled"] is False
    assert data["provenance"]["validation_strength"] == "curve_parameter_sampled"

    samples = data["samples"]
    assert [sample["frame_index"] for sample in samples] == [1, 2, 3]
    assert [sample["normalized_parameter"] for sample in samples] == [0.0, 0.5, 1.0]
    _assert_vector_close(samples[0]["point"], [0.0, 0.0, 0.0])
    _assert_vector_close(samples[1]["point"], [5.0, 0.0, 0.0])
    _assert_vector_close(samples[2]["point"], [10.0, 0.0, 0.0])
    for sample in samples:
        _assert_vector_close(sample["tangent"], [1.0, 0.0, 0.0])


async def test_director_curve_samples_rejects_missing_sampling_fields_and_over_limit():
    curve_id = "00000000-0000-0000-0000-000000000001"

    for body, message in [
        ({"curve_id": curve_id, "frame_count": 1}, "sampling"),
        ({"curve_id": curve_id, "frame_count": 1, "sampling": {"start": 0.0, "end": 1.0}}, "sampling.mode"),
        (
            {
                "curve_id": curve_id,
                "frame_count": 1,
                "sampling": {"mode": "normalized_parameter", "end": 1.0},
            },
            "sampling.start",
        ),
        (
            {
                "curve_id": curve_id,
                "frame_count": 1,
                "sampling": {"mode": "normalized_parameter", "start": 0.0},
            },
            "sampling.end",
        ),
        (
            {
                "curve_id": curve_id,
                "frame_count": 5001,
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
            },
            "5000",
        ),
        (
            {
                "curve_id": curve_id,
                "frame_count": 3,
                "sampling": {"mode": "normalized_parameter", "start": 1.0, "end": 0.0},
            },
            "sampling.start",
        ),
    ]:
        _, envelope = await _post_director("curve-samples", body)
        assert envelope["success"] is False
        assert envelope["data"]["code"] == "invalid_input"
        assert message in envelope["data"]["message"]


async def test_director_curve_samples_reports_expected_curve_contract_errors(fresh_document):
    missing_id = "00000000-0000-0000-0000-000000000001"
    _, missing_envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": missing_id,
            "frame_count": 1,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )
    assert missing_envelope["success"] is False
    assert missing_envelope["data"]["code"] == "curve_not_found"

    brep_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_curve_samples_not_curve_{uuid4().hex}",
    )
    _, not_curve_envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": brep_id,
            "frame_count": 1,
            "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
        },
    )
    assert not_curve_envelope["success"] is False
    assert not_curve_envelope["data"]["code"] == "not_curve"


async def test_director_frame_capture_rejects_run_root_outside_allowed_root(tmp_path):
    instruction = _frame_instruction(
        run_root=tmp_path / "outside",
        output_path=tmp_path / "outside" / "frames" / "frame_0001.png",
    )
    _, envelope = await _post_director("frame-capture", instruction)
    assert envelope["success"] is False
    assert _error_code(envelope) == "output_policy_violation"
    assert not Path(instruction["run_root"]).exists()
    assert not Path(instruction["output_path"]).exists()


async def test_director_frame_capture_rejects_output_outside_run_root():
    allowed_root = _director_output_root()
    suffix = uuid4().hex
    run_root = allowed_root / f"task8_run_root_{suffix}"
    output_path = allowed_root / f"task8_sibling_{suffix}" / "frame_0001.png"
    instruction = _frame_instruction(run_root=run_root, output_path=output_path)
    _, envelope = await _post_director("frame-capture", instruction)
    assert envelope["success"] is False
    assert _error_code(envelope) == "output_policy_violation"
    assert not Path(instruction["output_path"]).parent.exists()
    assert not Path(instruction["output_path"]).exists()


async def test_director_frame_capture_rejects_invalid_schema_version():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(schema_version=2),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_invalid_director_version():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(director_version="slice2"),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_over_limit_resolution():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(resolution={"width": 8193, "height": 180}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"

    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(resolution={"width": 320, "height": 8193}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_missing_perspective_lens_or_fov():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(camera_overrides={"lens_length": None, "fov_degrees": None}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_invalid_fov_degrees():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(camera_overrides={"lens_length": None, "fov_degrees": 180.0}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_invalid_frustum_fields():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(camera_overrides={"aspect": 0.0}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"
    assert "aspect" in str(envelope["data"])

    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(camera_overrides={"near_clip": 10.0, "far_clip": 1.0}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"
    assert "near_clip" in str(envelope["data"])


async def test_director_frame_capture_rejects_missing_validation_strength():
    transform = {
        "object_id": "00000000-0000-0000-0000-000000000001",
        "transform": _identity_matrix(),
        "source_state": {
            "bbox_min": [0, 0, 0],
            "bbox_max": [1, 1, 1],
            "state_hash": None,
        },
    }
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(object_transforms=[transform]),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_unsupported_validation_strength():
    transform = {
        "object_id": "00000000-0000-0000-0000-000000000001",
        "transform": _identity_matrix(),
        "source_state": {
            "bbox_min": [0, 0, 0],
            "bbox_max": [1, 1, 1],
            "validation_strength": "state_hash",
            "state_hash": None,
        },
    }
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(object_transforms=[transform]),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_parallel_projection_before_mutation():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(projection="parallel"),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "unsupported_projection"


async def test_director_frame_capture_rejects_malformed_object_transforms():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(object_transforms={"not": "an array"}),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_rejects_empty_object_transforms():
    _, envelope = await _post_director(
        "frame-capture",
        _frame_instruction(object_transforms=[]),
    )
    assert envelope["success"] is False
    assert _error_code(envelope) == "invalid_input"


async def test_director_frame_capture_success_writes_png_and_restores_state():
    _require_host()
    object_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_task10_{uuid4().hex}",
    )

    _, state_envelope = await _post_director("object-states", {"object_ids": [object_id]})
    assert state_envelope["success"] is True
    source_state = state_envelope["data"]["objects"][0]

    _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert view_envelope["success"] is True
    camera = view_envelope["data"]["camera"]
    if camera["projection"] != "perspective":
        pytest.skip("Active Rhino view is not perspective; slice 1 frame capture rejects parallel cameras.")
    original_display_mode = "Rendered"

    run_root = _director_output_root() / f"task10_success_{uuid4().hex}"
    output_path = run_root / "frames" / "frame_0001.png"
    instruction = _frame_instruction(
        run_root=run_root,
        output_path=output_path,
        camera_overrides=camera,
        object_transforms=[
            {
                "object_id": object_id,
                "transform": _translation_matrix(2.0, 0.0, 0.0),
                "source_state": {
                    "bbox_min": source_state["bbox_min"],
                    "bbox_max": source_state["bbox_max"],
                    "validation_strength": source_state["validation_strength"],
                    "state_hash": source_state.get("state_hash"),
                },
            }
        ],
    )

    _, capture_envelope = await _post_director("frame-capture", instruction)
    assert capture_envelope["success"] is True
    evidence = capture_envelope["data"]
    assert evidence["success"] is True
    assert evidence["dirty_partial_state"] is False
    assert Path(instruction["output_path"]).is_file()
    assert Path(instruction["output_path"]).stat().st_size > 0
    assert _png_size(Path(instruction["output_path"])) == (
        instruction["resolution"]["width"],
        instruction["resolution"]["height"],
    )
    assert evidence["objects"]["requested"] == 1
    assert evidence["objects"]["restored"] == 1
    assert evidence["objects"]["validation_strength"] == "bbox_only"
    assert evidence["viewport"]["restored"] is True
    assert evidence["viewport"]["restore_verified"] is True
    assert evidence["capture"]["width"] == instruction["resolution"]["width"]
    assert evidence["capture"]["height"] == instruction["resolution"]["height"]
    assert evidence["capture"]["output_path"] == instruction["output_path"]
    assert evidence["camera"]["applied"]["projection"] == "perspective"
    assert evidence["camera"]["applied"]["aspect"] == instruction["camera"]["aspect"]
    assert evidence["camera"]["applied"]["near_clip"] == instruction["camera"]["near_clip"]
    assert evidence["camera"]["applied"]["far_clip"] == instruction["camera"]["far_clip"]
    assert len(evidence["camera"]["applied"]["direction"]) == 3
    _assert_vector_close(evidence["camera"]["applied"]["location"], instruction["camera"]["location"])
    _assert_vector_close(evidence["camera"]["applied"]["target"], instruction["camera"]["target"])
    assert evidence["display"]["requested_mode"] == original_display_mode
    assert evidence["display"]["resolved_mode"]["id"]
    assert evidence["display"]["applied_mode"]["id"] == evidence["display"]["resolved_mode"]["id"]
    assert evidence["display"]["applied"] is True
    assert evidence["display"]["set_accepted"] is True
    assert evidence["display"]["readback_mode"]["id"] == evidence["display"]["resolved_mode"]["id"]
    assert evidence["display"]["readback_matches"] is True
    assert evidence["display"]["restored"] is True
    assert evidence["display"]["restore_readback_matches"] is True

    _, restored_state_envelope = await _post_director("object-states", {"object_ids": [object_id]})
    assert restored_state_envelope["success"] is True
    restored_state = restored_state_envelope["data"]["objects"][0]
    assert restored_state["bbox_min"] == source_state["bbox_min"]
    assert restored_state["bbox_max"] == source_state["bbox_max"]

    _, restored_view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert restored_view_envelope["success"] is True
    restored_camera = restored_view_envelope["data"]["camera"]
    _assert_vector_close(restored_camera["location"], camera["location"])
    _assert_vector_close(restored_camera["target"], camera["target"])
    _assert_vector_close(restored_camera["up"], camera["up"])


async def test_director_run_director_live_smoke_writes_three_frames_and_restores_state():
    _require_host()
    object_ids = [
        await _create_brep(
            [-1.0, -0.5, 0.0],
            [0.0, 0.5, 1.0],
            f"director_task11_a_{uuid4().hex}",
        ),
        await _create_brep(
            [1.0, -0.5, 0.0],
            [2.0, 0.5, 1.0],
            f"director_task11_b_{uuid4().hex}",
        ),
    ]

    _, state_envelope = await _post_director("object-states", {"object_ids": object_ids})
    assert state_envelope["success"] is True
    source_states = state_envelope["data"]["objects"]

    _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert view_envelope["success"] is True
    if view_envelope["data"]["camera"]["projection"] != "perspective":
        pytest.skip("Active Rhino view is not perspective; slice 1 director rejects parallel cameras.")

    run_id = f"task11_live_{uuid4().hex}"
    result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": object_ids,
            "frame_count": 3,
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "motion": {
                "strategy": "radial_bbox_center",
                "parameters": {"distance": 2.0},
            },
            "camera_keyframes": [
                {"frame_index": 1, "source": {"kind": "active_view"}},
                {"frame_index": 3, "source": {"kind": "active_view"}},
            ],
        },
        port=_director_port(),
    )

    assert result["state"] == "complete"
    run_root = Path(result["run_root"])
    assert run_root == _director_output_root() / run_id
    assert (run_root / "manifest.json").is_file()
    assert (run_root / "status.json").is_file()
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["state"] == "complete"

    frames = [run_root / "frames" / f"frame_{index:04d}.png" for index in range(1, 4)]
    for frame in frames:
        assert frame.is_file()
        assert frame.stat().st_size > 0
        assert _png_size(frame) == (320, 180)

    evidence_rows = _read_jsonl(run_root / "logs" / "frame_evidence.jsonl")
    assert len(evidence_rows) == 3
    for evidence in evidence_rows:
        assert evidence["success"] is True
        assert evidence["dirty_partial_state"] is False
        assert evidence["objects"]["requested"] == 2
        assert evidence["objects"]["restored"] == 2
        assert evidence["viewport"]["restore_verified"] is True
        assert evidence["display"]["applied"] is True
        assert evidence["display"]["readback_matches"] is True
        assert evidence["display"]["restored"] is True
        assert evidence["display"]["restore_readback_matches"] is True

    _, restored_state_envelope = await _post_director("object-states", {"object_ids": object_ids})
    assert restored_state_envelope["success"] is True
    restored_states = restored_state_envelope["data"]["objects"]
    for before, after in zip(source_states, restored_states):
        _assert_vector_close(after["bbox_min"], before["bbox_min"])
        _assert_vector_close(after["bbox_max"], before["bbox_max"])


async def test_director_instance_restore_semantics_large_coordinate_probe(fresh_document):
    _require_host()
    base = [125718.338195, -328450.993563, -29189.909203]
    size = [24.0, 16.0, 8.0]
    tiny_z = 0.628483
    suffix = uuid4().hex
    block_name = f"director_instance_restore_probe_{suffix}"
    created_ids: list[str] = []

    try:
        control_id = await _create_brep(
            base,
            [base[0] + size[0], base[1] + size[1], base[2] + size[2]],
            f"director_instance_restore_control_{suffix}",
        )
        created_ids.append(control_id)
        definition_source_id = await _create_brep(
            [0.0, 0.0, 0.0],
            size,
            f"director_instance_restore_definition_source_{suffix}",
        )
        created_ids.append(definition_source_id)

        await _block_create(
            block_name,
            [definition_source_id],
            [0.0, 0.0, 0.0],
            replace_with_instance=False,
        )
        instance_id = await _block_insert(block_name, base)
        created_ids.append(instance_id)

        _, state_envelope = await _post_director(
            "object-states",
            {"object_ids": [control_id, instance_id]},
        )
        assert state_envelope["success"] is True
        state_by_id = {
            item["object_id"]: item
            for item in state_envelope["data"]["objects"]
        }
        assert state_by_id[instance_id]["object_type"] == "InstanceReference"

        _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
        assert view_envelope["success"] is True
        camera = view_envelope["data"]["camera"]
        if camera["projection"] != "perspective":
            pytest.skip("Active Rhino view is not perspective; frame capture rejects parallel cameras.")

        object_ids = [control_id, instance_id]
        identity_transforms = [
            _compiled_object_transform(object_id, state_by_id[object_id], director.identity_matrix())
            for object_id in object_ids
        ]
        z_transforms = [
            _compiled_object_transform(
                object_id,
                state_by_id[object_id],
                director.translation_matrix([0.0, 0.0, tiny_z]),
            )
            for object_id in object_ids
        ]
        run_id = f"instance_restore_semantics_{suffix}"
        result = await director.run_compiled_track(
            {
                "run_id": run_id,
                "output_root": str(_director_output_root()),
                "resolution": {"width": 320, "height": 180},
                "display": {"mode": "Rendered"},
                "track": {
                    "transform_semantics": "absolute_from_source",
                    "fps": 24,
                    "frame_count": 2,
                    "animated_object_ids": object_ids,
                    "camera_frames": [
                        {"frame_index": 1, "camera": camera},
                        {"frame_index": 2, "camera": camera},
                    ],
                    "object_frames": [
                        {"frame_index": 1, "object_transforms": identity_transforms},
                        {"frame_index": 2, "object_transforms": z_transforms},
                    ],
                },
                "compile_provenance": {
                    "probe": "director_instance_restore_semantics",
                    "tiny_z": tiny_z,
                    "base": base,
                    "control_object_id": control_id,
                    "instance_object_id": instance_id,
                },
            },
            port=_director_port(),
        )

        assert result["state"] in {"complete", "unsafe_failed"}
        run_root = Path(result["run_root"])
        evidence_rows = _read_jsonl(run_root / "logs" / "frame_evidence.jsonl")
        assert [row["frame_index"] for row in evidence_rows] == [1, 2]
        rows_by_frame = {row["frame_index"]: row for row in evidence_rows}

        def _detail_for(frame_index: int, object_id: str) -> dict[str, Any]:
            matches = [
                detail
                for detail in rows_by_frame[frame_index]["objects"]["details"]
                if detail["object_id"] == object_id
            ]
            assert len(matches) == 1, {
                "frame_index": frame_index,
                "object_id": object_id,
                "matches": matches,
            }
            return matches[0]

        control_details = [
            _detail_for(1, control_id),
            _detail_for(2, control_id),
        ]
        instance_details = [
            _detail_for(1, instance_id),
            _detail_for(2, instance_id),
        ]

        summary = {
            "director_instance_restore_semantics_probe": {
                "run_state": result["state"],
                "run_root": str(run_root),
                "frame_indices": [row["frame_index"] for row in evidence_rows],
                "control_object_id": control_id,
                "instance_object_id": instance_id,
                "control_restored": [detail.get("restored") for detail in control_details],
                "instance_restored": [detail.get("restored") for detail in instance_details],
                "control_bbox_max_delta": [detail.get("bbox_max_delta") for detail in control_details],
                "instance_bbox_max_delta": [detail.get("bbox_max_delta") for detail in instance_details],
                "control_phase_summary": [_detail_phase_summary(detail) for detail in control_details],
                "instance_phase_summary": [_detail_phase_summary(detail) for detail in instance_details],
            }
        }
        summary_path = run_root / "logs" / "instance_restore_semantics_probe.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))

        for detail in control_details:
            _assert_native_phase_evidence(detail, expects_instance=False)
            assert detail["transform_call_path"] == "pDoc->TransformObject(objRef, xform, true, false, true)"
        for detail in instance_details:
            _assert_native_phase_evidence(
                detail,
                expects_instance=True,
                expected_instance_definition_name=block_name,
            )
            assert detail["transform_call_path"] == "pDoc->TransformObject(objRef, xform, true, false, true)"
    finally:
        await _cleanup_instance_restore_probe(created_ids, block_name)


async def test_director_run_director_live_smoke_curve_follow_target_uses_curve_uuid(
    fresh_document,
):
    _require_host()
    object_id = await _create_brep(
        [-0.5, -0.5, 0.0],
        [0.5, 0.5, 1.0],
        f"director_curve_follow_object_{uuid4().hex}",
    )
    curve_id = await _create_line_curve(f"director_curve_follow_path_{uuid4().hex}")

    run_id = f"curve_follow_live_{uuid4().hex}"
    result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": [object_id],
            "frame_count": 3,
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": curve_id,
                "target": [5.0, 5.0, 0.0],
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
        },
        port=_director_port(),
    )

    assert result["state"] == "complete"
    run_root = Path(result["run_root"])
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["camera_plan"]["strategy"] == "curve_follow_target"
    assert manifest["camera_plan"]["provenance"]["curve_id"] == curve_id
    assert manifest["camera_keyframes"] == []
    assert manifest["camera_keyframe_provenance"] == []
    assert [frame["camera"]["location"] for frame in manifest["frames"]] == [
        [0.0, 0.0, 0.0],
        [5.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
    ]
    for index in range(1, 4):
        frame = run_root / "frames" / f"frame_{index:04d}.png"
        assert frame.is_file()
        assert frame.stat().st_size > 0
        assert _png_size(frame) == (320, 180)


async def test_director_curve_follow_target_fixture_renders_four_second_video():
    _require_host()
    curve_objects = await _fixture_objects_by_layer("camera_curve", object_type="Curve")
    point_objects = await _fixture_objects_by_layer("focus_point", object_type="Point")
    scene_objects = await _fixture_objects_by_layer(
        "RookVisionDirector::TestParts", object_type="Brep"
    )
    if not curve_objects or not point_objects or not scene_objects:
        pytest.skip(
            "Fixture requires camera_curve, focus_point, and "
            "RookVisionDirector::TestParts objects in the active Rhino document."
        )
    if len(curve_objects) != 1:
        pytest.fail(f"Expected one camera_curve object, found {len(curve_objects)}")
    if len(point_objects) != 1:
        pytest.fail(f"Expected one focus_point object, found {len(point_objects)}")

    curve_id = curve_objects[0]["id"]
    target = _point_from_bbox(point_objects[0])
    object_ids = [obj["id"] for obj in scene_objects[:8]]
    native_calls: list[tuple[str, str]] = []

    async def tracked_call_native(endpoint, method, payload, *, port=None):
        native_calls.append((endpoint, method))
        return await director.call_rhino(endpoint, method, payload, port=port)

    run_id = f"curve_follow_fixture_video_{uuid4().hex}"
    result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": object_ids,
            "timeline": {"fps": 30, "duration_seconds": 4.0},
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            "camera": {
                "strategy": "curve_follow_target",
                "curve_id": curve_id,
                "target": target,
                "up": [0.0, 0.0, 1.0],
                "sampling": {"mode": "normalized_parameter", "start": 0.0, "end": 1.0},
                "lens_length": 35.0,
            },
        },
        call_native=tracked_call_native,
        port=_director_port(),
    )

    assert result["state"] == "complete"
    run_root = Path(result["run_root"])
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["timeline"] == {
        "source": "timeline",
        "fps": 30,
        "duration_seconds": 4.0,
        "frame_count": 120,
    }
    assert manifest["frame_count"] == 120
    assert manifest["camera_plan"]["strategy"] == "curve_follow_target"
    assert manifest["camera_plan"]["provenance"]["curve_id"] == curve_id
    assert manifest["camera_plan"]["provenance"]["target"] == target
    assert manifest["camera_keyframes"] == []
    assert manifest["camera_keyframe_provenance"] == []
    assert len(manifest["frames"]) == 120
    assert all(
        frame["camera"]["projection"] == "perspective" for frame in manifest["frames"]
    )
    assert all(frame["camera"]["target"] == target for frame in manifest["frames"])

    _, sample_envelope = await _post_director(
        "curve-samples",
        {
            "curve_id": curve_id,
            "frame_count": manifest["frame_count"],
            "sampling": manifest["camera_plan"]["provenance"]["sampling"],
        },
    )
    assert sample_envelope["success"] is True
    samples = sample_envelope["data"]["samples"]
    assert len(samples) == 120
    assert samples[0]["normalized_parameter"] == 0.0
    assert samples[-1]["normalized_parameter"] == 1.0
    max_location_delta = max(
        _vector_distance(sample["point"], frame["camera"]["location"])
        for sample, frame in zip(samples, manifest["frames"])
    )
    assert max_location_delta <= 1.0e-6

    frame_paths = [
        run_root / "frames" / f"frame_{index:04d}.png"
        for index in range(1, 121)
    ]
    for frame in frame_paths:
        assert frame.is_file()
        assert frame.stat().st_size > 0
    assert _png_size(frame_paths[0]) == (320, 180)
    assert _png_size(frame_paths[-1]) == (320, 180)

    request = {
        "schema_version": 1,
        "run_id": run_id,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": manifest["frame_count"],
        "fps": manifest["timeline"]["fps"],
        "fps_source": "timeline",
        "width": manifest["resolution"]["width"],
        "height": manifest["resolution"]["height"],
        "output_path": str(run_root / "videos" / "preview.mp4"),
        "codec": "h264",
        "container": "mp4",
    }
    _, envelope = await _post_director("video-assemble", request)
    if envelope["success"] is False and _error_code(envelope) == "backend_unavailable":
        pytest.skip(
            f"Media Foundation backend unavailable on this machine: {envelope['data']}"
        )
    assert envelope["success"] is True
    video_path = run_root / "videos" / "preview.mp4"
    assert video_path.is_file()
    assert video_path.stat().st_size > 0

    endpoints = [call[0] for call in native_calls]
    assert endpoints.count("/director/curve-samples") == 1
    assert "/director/view-state" not in endpoints


async def test_director_publish_video_live_smoke(fresh_document):
    _require_host()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        pytest.skip("LOCALAPPDATA is not available")

    object_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_publish_smoke_{uuid4().hex}",
    )
    _, view_envelope = await _post_director(
        "view-state", {"source": {"kind": "active_view"}}
    )
    assert view_envelope["success"] is True
    if view_envelope["data"]["camera"]["projection"] != "perspective":
        pytest.skip(
            "Active Rhino view is not perspective; slice 1 director rejects parallel cameras."
        )

    run_id = f"director_publish_live_smoke_{uuid4().hex}"
    run_result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": [object_id],
            "timeline": {"fps": 24, "duration_seconds": 1 / 24},
            "resolution": {"width": 1280, "height": 720},
            "display": {"mode": "Rendered"},
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            "camera_keyframes": [
                {"time": 0.0, "source": {"kind": "active_view"}},
            ],
        },
        port=_director_port(),
    )
    assert run_result["state"] == "complete"
    run_root = Path(run_result["run_root"])
    manifest_path = run_root / "manifest.json"
    status_path = run_root / "status.json"
    assert manifest_path.is_file()
    assert status_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["state"] == "complete"

    assemble_payload = await director_video.assemble_director_video(
        {"run_root": str(run_root)},
        port=_director_port(),
    )
    if assemble_payload.get("state") == "failed":
        error = assemble_payload.get("error") or {}
        if error.get("code") == "backend_unavailable":
            pytest.skip(
                f"Media Foundation backend unavailable on this machine: {error}"
            )
        pytest.fail(f"Video assembly failed before publish smoke: {error!r}")

    assert assemble_payload["state"] == "complete"
    video_manifest_path = run_root / "video_manifest.json"
    video_path = run_root / "videos" / "preview.mp4"
    assert video_manifest_path.is_file()
    assert video_path.is_file()
    assert video_path.stat().st_size > 0

    video_manifest = json.loads(video_manifest_path.read_text(encoding="utf-8"))
    assert video_manifest["state"] == "complete"
    assert video_manifest["output_current"] is True
    assert video_manifest["output_path"] == "videos/preview.mp4"
    assert video_manifest["format"] == "mp4"
    assert video_manifest["container"] == "mp4"
    assert video_manifest["codec"] == "h264"
    assert video_manifest["width"] == manifest["resolution"]["width"] == 1280
    assert video_manifest["height"] == manifest["resolution"]["height"] == 720
    assert video_manifest["fps"] == manifest["timeline"]["fps"] == 24
    assert video_manifest["frame_count"] == manifest["frame_count"]

    payload = await director_publish.publish_director_video(
        {"run_root": str(run_root)},
        port=_director_port(),
    )
    assert payload["state"] == "complete"
    assert payload["profile"] == "director_publish_standard_v1"
    artifact_id = payload["artifact_id"]

    artifact_result = await server.call_tool(
        "rhino_vision_get_artifact",
        {"artifact_id": artifact_id},
    )
    artifact_payload = json.loads(artifact_result[0].text)
    artifact = artifact_payload["artifact"]
    assert artifact["kind"] == "generated_video"
    files = artifact["files"]
    assert len(files) == 1
    assert {(file["role"], file["path"]) for file in files} == {
        ("video", "video.mp4")
    }


async def test_director_video_assemble_rejects_output_outside_run_videos():
    allowed_root = _director_output_root()
    run_root = allowed_root / f"video_policy_{uuid4().hex}"
    frames_dir = run_root / "frames"
    output_path = allowed_root / "escaped.mp4"
    request = {
        "schema_version": 1,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "frames_dir": str(frames_dir),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": 1,
        "fps": 24,
        "fps_source": "timeline",
        "width": 320,
        "height": 180,
        "output_path": str(output_path),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    assert envelope["success"] is False
    assert _error_code(envelope) == "output_policy_violation"


async def test_director_video_assemble_rejects_odd_dimensions_before_backend():
    allowed_root = _director_output_root()
    run_root = allowed_root / f"video_odd_{uuid4().hex}"
    request = {
        "schema_version": 1,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": 1,
        "fps": 24,
        "fps_source": "timeline",
        "width": 321,
        "height": 180,
        "output_path": str(run_root / "videos" / "preview.mp4"),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    assert envelope["success"] is False
    assert _error_code(envelope) == "unsupported_dimensions"


async def test_director_video_assemble_live_smoke_after_completed_run():
    _require_host()
    object_id = await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_video_smoke_{uuid4().hex}",
    )
    _, view_envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert view_envelope["success"] is True
    if view_envelope["data"]["camera"]["projection"] != "perspective":
        pytest.skip("Active Rhino view is not perspective; slice 1 director rejects parallel cameras.")

    run_id = f"video_smoke_{uuid4().hex}"
    result = await director.run_director(
        {
            "run_id": run_id,
            "output_root": str(_director_output_root()),
            "object_ids": [object_id],
            "timeline": {"fps": 12, "duration_seconds": 0.25},
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "motion": {"strategy": "radial_bbox_center", "parameters": {"distance": 0}},
            "camera_keyframes": [
                {"time": 0.0, "source": {"kind": "active_view"}},
                {"at": 1.0, "source": {"kind": "active_view"}},
            ],
        },
        port=_director_port(),
    )
    assert result["state"] == "complete"
    run_root = Path(result["run_root"])
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    request = {
        "schema_version": 1,
        "run_id": run_id,
        "run_root": str(run_root),
        "frames_dir": str(run_root / "frames"),
        "input_pattern": "frame_%04d.png",
        "start_number": 1,
        "frame_count": manifest["frame_count"],
        "fps": manifest["timeline"]["fps"],
        "fps_source": "timeline",
        "width": manifest["resolution"]["width"],
        "height": manifest["resolution"]["height"],
        "output_path": str(run_root / "videos" / "preview.mp4"),
        "codec": "h264",
        "container": "mp4",
    }

    _, envelope = await _post_director("video-assemble", request)

    if envelope["success"] is False and _error_code(envelope) == "backend_unavailable":
        pytest.skip(f"Media Foundation backend unavailable on this machine: {envelope['data']}")
    assert envelope["success"] is True
    assert (run_root / "videos" / "preview.mp4").is_file()
    assert (run_root / "videos" / "preview.mp4").stat().st_size > 0
