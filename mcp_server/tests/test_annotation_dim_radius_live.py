"""Live-Rhino characterization tests for POST /annotation/dim-radius (Phase 2 PR-4).

Pins:
  - Circle happy path: measuredValue == radius exactly
  - Arc happy path: same semantic on a partial arc
  - annotationType response + /geometry agree on "RadialDimension"
  - curveId → not-arc-or-circle → invalid_input
  - Unknown curveId → not_found (explicit structured-error path via
    StructuredError, not the generic catch mapper)
  - Invalid GUID string → invalid_input
  - Omission of `point` triggers the arc-midpoint default (pinned so the
    shared DispatchRadialDim fallback does not silently drift)
  - Strict attribute handling inherited from PR-1
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


async def _create_circle(center: list[float], radius: float) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CIRCLE", "center": center, "radius": radius},
    )
    assert not _is_error(res), f"rhino_create CIRCLE failed: {res!r}"
    return res["id"]


async def _create_arc(center: list[float], radius: float, angle_deg: float) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "ARC", "center": center, "radius": radius, "angle": angle_deg},
    )
    assert not _is_error(res), f"rhino_create ARC failed: {res!r}"
    return res["id"]


async def _create_line(start: list[float], end: list[float]) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _post_dim_radius_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dim-radius", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dim-radius returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dim_radius(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dim_radius", body)
    assert not _is_error(res), f"rhino_annotation_dim_radius failed: {res!r}"
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


# --- Happy paths -------------------------------------------------------------


async def test_circle_radius_exact(fresh_document):
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 5.0)

    status, envelope = await _post_dim_radius_raw({
        "curveId": circle_id,
        "point": [8, 0, 0],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 5.0) < 1e-6, (
        f"Expected measuredValue=5.0 for r=5 circle, got {data.get('measuredValue')!r}"
    )


async def test_arc_radius_exact(fresh_document):
    await _purge_objects()
    arc_id = await _create_arc([0, 0, 0], 7.5, 180.0)

    status, envelope = await _post_dim_radius_raw({
        "curveId": arc_id,
        "point": [10, 0, 0],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 7.5) < 1e-6, (
        f"Expected measuredValue=7.5 for r=7.5 arc, got {data.get('measuredValue')!r}"
    )


# --- annotationType cross-surface invariant ---------------------------------


async def test_annotationType_radial(fresh_document):
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 3.0)
    result = await _tool_dim_radius({"curveId": circle_id, "point": [5, 0, 0]})

    assert result.get("annotationType") == "RadialDimension", (
        f"Expected annotationType='RadialDimension', got {result.get('annotationType')!r}"
    )

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert detail.get("annotationType") == "RadialDimension", (
        f"/geometry disagreed: {detail!r}"
    )


# --- Default-point fallback (pins arc.MidPoint behavior) -------------------


async def test_point_omitted_uses_arc_midpoint(fresh_document):
    # Request omits `point`; handler falls back to arc.MidPoint. This pins
    # the shared DispatchRadialDim default so a later edit that silently
    # changes the fallback (e.g. to arc.Center or to nullptr) fails loud.
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 4.0)

    status, envelope = await _post_dim_radius_raw({"curveId": circle_id})
    assert status == 200, f"Point-omitted request should succeed: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 4.0) < 1e-6, f"{envelope!r}"


# --- Error taxonomy --------------------------------------------------------


async def test_unknown_curveId_returns_not_found(fresh_document):
    # Explicit structured-error path via StructuredError("not_found", ...).
    # Unknown GUID must NOT map to invalid_input or operation_failed — the
    # contract distinguishes "bad input shape" from "referenced object
    # doesn't exist".
    await _purge_objects()
    status, envelope = await _post_dim_radius_raw({
        "curveId": "00000000-0000-0000-0000-000000000001",
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "not_found")


async def test_invalid_guid_string_rejected(fresh_document):
    status, envelope = await _post_dim_radius_raw({"curveId": "not-a-guid"})
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_line_curve_rejected(fresh_document):
    # curveId points at a curve that is not arc/circle → invalid_input
    # with a message naming arc/circle.
    await _purge_objects()
    line_id = await _create_line([0, 0, 0], [10, 0, 0])

    status, envelope = await _post_dim_radius_raw({"curveId": line_id})
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "arc" in envelope["data"]["errorMessage"].lower()


async def test_missing_curveId_rejected(fresh_document):
    status, envelope = await _post_dim_radius_raw({"point": [1, 2, 3]})
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "curveid" in envelope["data"]["errorMessage"].lower()


async def test_unknown_layer_rejected(fresh_document):
    # Strict-attrs inherited from PR-1 ApplyCommonAttributesStrict.
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 2.0)
    status, envelope = await _post_dim_radius_raw({
        "curveId": circle_id,
        "layer": "NonExistentLayer__PR4_strict_check__",
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
