from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest


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


def _director_output_root() -> Path:
    configured = os.environ.get("ROOK_DIRECTOR_OUTPUT_ROOT")
    if configured:
        return Path(configured).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        pytest.skip("LOCALAPPDATA is required to infer native director output root.")
    return (Path(local_app_data) / "Rook" / "rookvision_director").resolve()


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


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
