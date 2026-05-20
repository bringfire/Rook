from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest

from rook import director
from .conftest import _create_brep


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post_director(route: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
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
