"""Live-Rhino characterization tests for POST /annotation/dim-aligned (Phase 2 PR-3).

Pins the ALIGNED dimension contract:
  - Euclidean-distance semantics (slant, NOT projected); this is the
    ALIGNED vs LINEAR semantic pin in the opposite direction from PR-2.
  - annotationType echoes "AlignedDimension" (ON::AnnotationType::Aligned),
    matching GeometryHandler.cpp:25's AnnotationTypeToString mapping.
  - Response/rhino_geometry agree on the annotationType string.
  - measuredValue = (end - start).Length() from geometry math, NOT
    PlainText parsing.
  - `direction` parameter is rejected with invalid_input (ALIGNED has
    no projection direction — use /annotation/dim-linear for that).
  - Strict-attrs inherited from PR-1 ApplyCommonAttributesStrict.
  - Coincident-point rejection via Unitize-fail posture (reuses PR-1/PR-2
    convention, no custom tolerance).

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_dim_aligned_live.py
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


async def _post_dim_aligned_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dim-aligned", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dim-aligned returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dim_aligned(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dim_aligned", body)
    assert not _is_error(res), f"rhino_annotation_dim_aligned failed: {res!r}"
    return res


async def _read_geometry(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_geometry", {"id": obj_id})
    assert not _is_error(res), f"rhino_geometry failed: {res!r}"
    return res


def _assert_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict) and "id" in data, f"Expected data with id: {envelope!r}"
    return data


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured error data: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"]


# --- ALIGNED semantic pin: Euclidean distance, NOT projected -----------------


async def test_slant_reads_euclidean_not_x_projection(fresh_document):
    # [0,0,0] → [10,5,0] — X-projection is 10.0, Euclidean is sqrt(125) ≈ 11.180.
    # ALIGNED MUST read the slant. If measuredValue comes back ~10.0, the
    # handler regressed to LINEAR semantics and the contract is broken.
    await _purge_objects()

    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)

    expected = math.sqrt(125.0)
    measured = data.get("measuredValue")
    assert measured is not None, f"Expected measuredValue: {envelope!r}"
    assert abs(measured - expected) < 1e-6, (
        f"ALIGNED measuredValue should be Euclidean = {expected!r}, got {measured!r}. "
        f"(If ~10.0, handler regressed to LINEAR/projected semantics.)"
    )


async def test_collinear_x_still_euclidean(fresh_document):
    # When (end - start) is parallel to X, ALIGNED and LINEAR-with-X give
    # the same answer (10.0). Pins the degenerate-where-they-agree case.
    await _purge_objects()

    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": 2,
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 10.0) < 1e-6, f"{envelope!r}"


async def test_3d_slant(fresh_document):
    # 3-4-12 Pythagorean triple extended: sqrt(9+16+144) = sqrt(169) = 13.
    await _purge_objects()

    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [3, 4, 12],
        "offset": 2,
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 13.0) < 1e-6, f"{envelope!r}"


# --- annotationType pin (response + /geometry cross-check) ------------------


async def test_response_echoes_aligned_dimension_type(fresh_document):
    await _purge_objects()
    result = await _tool_dim_aligned({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
    })
    assert result.get("annotationType") == "AlignedDimension", (
        f"Expected annotationType='AlignedDimension', got {result.get('annotationType')!r}."
    )


async def test_geometry_agrees_on_annotation_type(fresh_document):
    # Cross-surface invariant: POST response and /geometry return the
    # same annotationType string.
    await _purge_objects()
    result = await _tool_dim_aligned({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
    })
    response_type = result.get("annotationType")

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    geom_type = detail.get("annotationType")

    assert response_type == geom_type, (
        f"Response annotationType={response_type!r} but /geometry returned {geom_type!r}"
    )
    assert response_type == "AlignedDimension", (
        f"Expected AlignedDimension on both surfaces, got {response_type!r}"
    )


# --- Negative offset -------------------------------------------------------


async def test_negative_offset_succeeds(fresh_document):
    await _purge_objects()
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": -3,
    })
    assert status == 200, f"Negative offset should succeed: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 10.0) < 1e-6


# --- `direction` parameter is explicitly rejected --------------------------


async def test_direction_parameter_rejected(fresh_document):
    # ALIGNED has no projection direction. Silently accepting `direction`
    # would weaken the LINEAR/ALIGNED route split. PR-3 rejects it
    # explicitly with a pointer to /annotation/dim-linear.
    await _purge_objects()
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 5, 0],
        "offset": 2,
        "direction": [1, 0, 0],
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    msg = envelope["data"]["errorMessage"].lower()
    assert "direction" in msg
    assert "dim-linear" in msg, (
        f"Rejection message should point callers at /annotation/dim-linear: {envelope!r}"
    )


# --- Validation failures ---------------------------------------------------


async def test_missing_start_rejected(fresh_document):
    status, envelope = await _post_dim_aligned_raw({
        "end": [10, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "start" in envelope["data"]["errorMessage"].lower()


async def test_missing_end_rejected(fresh_document):
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "end" in envelope["data"]["errorMessage"].lower()


async def test_missing_offset_rejected(fresh_document):
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "offset" in envelope["data"]["errorMessage"].lower()


async def test_coincident_start_end_rejected(fresh_document):
    await _purge_objects()
    status, envelope = await _post_dim_aligned_raw({
        "start": [1, 2, 3],
        "end": [1, 2, 3],
        "offset": 2,
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_overlong_start_rejected(fresh_document):
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0, 99],
        "end": [10, 0, 0],
        "offset": 2,
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    status, envelope = await _post_dim_aligned_raw({
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": 2,
        "layer": "NonExistentLayer__PR3_strict_check__",
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
