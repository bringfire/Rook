"""Live-Rhino characterization tests for POST /annotation/dim-diameter (Phase 2 PR-4).

Pins:
  - Circle happy path: measuredValue == 2·radius exactly
  - Concrete numeric: r=5 circle → measuredValue = 10.0
  - annotationType "DiameterDimension" on both POST response and /geometry
  - Distinguishes from radius via the AnnotationType + measuredValue pair
  - Unknown curveId → not_found; non-arc curve → invalid_input
"""

from __future__ import annotations

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


async def _create_line(start: list[float], end: list[float]) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _post_dim_diameter_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dim-diameter", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dim-diameter returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dim_diameter(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dim_diameter", body)
    assert not _is_error(res), f"rhino_annotation_dim_diameter failed: {res!r}"
    return res


async def _read_geometry(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_geometry", {"id": obj_id})
    assert not _is_error(res), f"rhino_geometry failed: {res!r}"
    return res


def _assert_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict) and "id" in data
    return data


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict)
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )


async def test_circle_diameter_exact(fresh_document):
    # r=5 → diameter=10. Concrete numeric pin — if measuredValue comes
    # back as 5.0, the handler regressed to radius math.
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 5.0)

    status, envelope = await _post_dim_diameter_raw({
        "curveId": circle_id,
        "point": [8, 0, 0],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 10.0) < 1e-6, (
        f"Expected diameter=10.0 for r=5 circle, got {data.get('measuredValue')!r}. "
        f"(If ~5.0, handler regressed to radius semantics.)"
    )


async def test_annotationType_diameter(fresh_document):
    await _purge_objects()
    circle_id = await _create_circle([0, 0, 0], 3.0)
    result = await _tool_dim_diameter({"curveId": circle_id, "point": [5, 0, 0]})

    assert result.get("annotationType") == "DiameterDimension", (
        f"Expected annotationType='DiameterDimension', got {result.get('annotationType')!r}"
    )

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert detail.get("annotationType") == "DiameterDimension", f"/geometry: {detail!r}"


async def test_unknown_curveId_returns_not_found(fresh_document):
    await _purge_objects()
    status, envelope = await _post_dim_diameter_raw({
        "curveId": "00000000-0000-0000-0000-000000000001",
    })
    assert status == 400
    _assert_structured_error(envelope, "not_found")


async def test_line_curve_rejected(fresh_document):
    await _purge_objects()
    line_id = await _create_line([0, 0, 0], [10, 0, 0])
    status, envelope = await _post_dim_diameter_raw({"curveId": line_id})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_missing_curveId_rejected(fresh_document):
    status, envelope = await _post_dim_diameter_raw({"point": [1, 2, 3]})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
