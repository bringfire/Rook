"""Live-Rhino characterization tests for POST /annotation/dim-linear (Phase 2 PR-2).

Pins the LINEAR dimension contract:
  - Projected-distance semantics (NOT Euclidean); this is the LINEAR vs
    ALIGNED semantic pin.
  - annotationType echoes "LinearDimension" (ON::AnnotationType::Rotated),
    matching GeometryHandler.cpp:30's AnnotationTypeToString mapping.
  - Response/rhino_geometry agree on the annotationType string.
  - measuredValue comes from geometry math, NOT PlainText parsing.
  - Default direction is world X ([1,0,0]).
  - Strict-attrs inherited from PR-1 ApplyCommonAttributesStrict.
  - Coincident-point + zero-direction rejection via Unitize-fail posture,
    reusing legacy factory pattern at CreateHandler.cpp:586-587 — no
    custom tolerance policy.

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_dim_linear_live.py

Rhino must be running with RookNative loaded. Tests use _purge_objects()
because fresh_document's rhino_document_ops(action=new) does not wipe
the object table across sessions (PR-0 observation 2026-04-19).
"""

from __future__ import annotations

import math
from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _purge_objects() -> None:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_objects", {"limit": 500})
    if _is_error(res) or not isinstance(res, dict):
        return
    objects = res.get("objects") or []
    ids = [o["id"] for o in objects if isinstance(o, dict) and "id" in o]
    if ids:
        await _mcp_tool_executor("rhino_delete", {"ids": ids})


async def _post_dim_linear_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dim-linear", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dim-linear returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dim_linear(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dim_linear", body)
    assert not _is_error(res), f"rhino_annotation_dim_linear failed: {res!r}"
    return res


async def _read_geometry(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_geometry", {"id": obj_id})
    assert not _is_error(res), f"rhino_geometry failed: {res!r}"
    return res


def _assert_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert "id" in data, f"Expected id in data: {envelope!r}"
    return data


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured error data: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"]


# --- LINEAR semantic pin: projected distance, NOT Euclidean ------------------


async def test_horizontal_dim_reads_x_projection_not_euclidean(fresh_document):
    # Start [0,0,0], end [10,5,0] — slant distance sqrt(100+25) ≈ 11.18.
    # LINEAR with direction [1,0,0] MUST read the X-projection = 10.0.
    # If measuredValue comes back ~11.18, the handler is producing ALIGNED
    # semantics and the contract is broken.
    await _purge_objects()

    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
        "direction": [1, 0, 0],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)

    measured = data.get("measuredValue")
    assert measured is not None, f"Expected measuredValue in response: {envelope!r}"
    assert abs(measured - 10.0) < 1e-6, (
        f"LINEAR measuredValue should be X-projection = 10.0, got {measured!r}. "
        f"(If ~11.18, handler regressed to ALIGNED semantics.)"
    )


async def test_default_direction_is_world_x(fresh_document):
    # Omitting `direction` must behave identically to direction=[1,0,0].
    await _purge_objects()

    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 10.0) < 1e-6, (
        f"Default direction should project to X-axis = 10.0, got {data!r}"
    )


async def test_vertical_direction_reads_y_projection(fresh_document):
    # Same start/end, but projection direction [0,1,0]. Must read Y = 5.0.
    await _purge_objects()

    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
        "direction": [0, 1, 0],
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 5.0) < 1e-6, (
        f"Vertical direction should project to Y-axis = 5.0, got {data!r}"
    )


# --- annotationType pin (response + /geometry cross-check) -------------------


async def test_response_echoes_linear_dimension_type(fresh_document):
    # Response payload must echo annotationType = "LinearDimension"
    # (matches GeometryHandler.cpp:30 mapping of ON::AnnotationType::Rotated).
    await _purge_objects()

    result = await _tool_dim_linear({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
        "direction": [1, 0, 0],
    })
    assert result.get("annotationType") == "LinearDimension", (
        f"Expected annotationType='LinearDimension', got {result.get('annotationType')!r}. "
        f"(If 'AlignedDimension', the SDK construction path is producing ALIGNED "
        f"and PR-2 does NOT ship as LINEAR.)"
    )


async def test_geometry_agrees_on_annotation_type(fresh_document):
    # Cross-surface pin: POST /annotation/dim-linear response and
    # GET /geometry?id=<id> return the same annotationType string. If
    # they drift, downstream agents see contradictory info.
    await _purge_objects()

    result = await _tool_dim_linear({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
        "direction": [1, 0, 0],
    })
    response_type = result.get("annotationType")

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    geom_type = detail.get("annotationType")

    assert response_type == geom_type, (
        f"Response annotationType={response_type!r} but /geometry returned {geom_type!r}"
    )
    assert response_type == "LinearDimension", (
        f"Expected LinearDimension on both surfaces, got {response_type!r}"
    )


# --- Negative offset is accepted --------------------------------------------


async def test_negative_offset_succeeds(fresh_document):
    # Negative offset places the dim line on the opposite side of the
    # start-end line; not an error.
    await _purge_objects()

    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": -3,
    })
    assert status == 200, f"Negative offset should succeed, got {status}: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 10.0) < 1e-6


# --- Validation failures -----------------------------------------------------


async def test_missing_start_rejected(fresh_document):
    status, envelope = await _post_dim_linear_raw({
        "end": [10, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "start" in envelope["data"]["errorMessage"].lower()


async def test_missing_end_rejected(fresh_document):
    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "end" in envelope["data"]["errorMessage"].lower()


async def test_missing_offset_rejected(fresh_document):
    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "offset" in envelope["data"]["errorMessage"].lower()


async def test_coincident_start_end_rejected(fresh_document):
    # Unitize-fail posture (reused from legacy CreateLinearDimension factory):
    # distinct points required; no custom tolerance.
    await _purge_objects()
    status, envelope = await _post_dim_linear_raw({
        "start": [1, 2, 3],
        "end": [1, 2, 3],
        "offset": 2,
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_zero_direction_rejected(fresh_document):
    # Same Unitize-fail posture: non-zero direction required.
    await _purge_objects()
    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": 2,
        "direction": [0, 0, 0],
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "direction" in envelope["data"]["errorMessage"].lower()


async def test_overlong_start_rejected(fresh_document):
    # Exact-3 cardinality inherited from PR-1 strict-point contract.
    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0, 99],
        "end": [10, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    # Strict attribute handling inherited from PR-1 ApplyCommonAttributesStrict.
    status, envelope = await _post_dim_linear_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": 2,
        "layer": "NonExistentLayer__PR2_strict_check__",
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
