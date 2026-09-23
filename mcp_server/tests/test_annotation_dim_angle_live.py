"""Live-Rhino characterization tests for POST /annotation/dim-angle (Phase 2 PR-5).

Pins the 3-point angular dimension contract:
  - Right-angle core math (90° exact)
  - Known 45° and 135° cases pin acute/obtuse handling
  - annotationType echoes "Angular3ptDimension" on POST + /geometry
  - `point` semantic effect: characterize whether the SDK selects different
    spans from different `point` positions with the same center/start/end
    (pinning observed behavior rather than asserting a pre-committed value)
  - `center == start` / `center == end` → invalid_input (Unitize-fail posture)
  - Missing any of the four required points → invalid_input
  - measuredValue sourced from ON_DimAngular::Measurement() (SDK accessor),
    not a pre-committed acos shortcut — so reflex/supplementary cases
    reflect the SDK's actual choice

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_dim_angle_live.py
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


async def _post_dim_angle_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dim-angle", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dim-angle returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dim_angle(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dim_angle", body)
    assert not _is_error(res), f"rhino_annotation_dim_angle failed: {res!r}"
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


# --- Core angular math -----------------------------------------------------


async def test_right_angle(fresh_document):
    # X-axis ray + Y-axis ray, dim point in interior of XY+ quadrant.
    # If measuredValue comes back anything other than ~90°, the core
    # math or SDK Measurement() accessor regressed.
    await _purge_objects()

    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
        "point":  [5, 5, 0],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 90.0) < 1e-4, (
        f"Expected 90° right angle, got {data.get('measuredValue')!r}"
    )


async def test_45_degree_acute(fresh_document):
    await _purge_objects()
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [10, 10, 0],
        "point":  [10, 5, 0],
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 45.0) < 1e-4, f"{envelope!r}"


async def test_135_degree_obtuse(fresh_document):
    # Ray1 along +X, Ray2 at 135° in XY plane. Pin that obtuse works.
    await _purge_objects()
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [-10, 10, 0],  # 135° from +X
        "point":  [0, 5, 0],     # interior of the obtuse span
    })
    data = _assert_success(envelope)
    assert abs(data.get("measuredValue") - 135.0) < 1e-4, f"{envelope!r}"


# --- annotationType cross-surface invariant --------------------------------


async def test_annotationType_angular(fresh_document):
    await _purge_objects()
    result = await _tool_dim_angle({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
        "point":  [5, 5, 0],
    })
    assert result.get("annotationType") == "Angular3ptDimension", (
        f"Expected annotationType='Angular3ptDimension', got {result.get('annotationType')!r}"
    )

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert detail.get("annotationType") == "Angular3ptDimension", f"/geometry: {detail!r}"


# --- `point` semantic effect (characterization, not pre-commit) ------------


async def test_point_selects_angular_span(fresh_document):
    # Holds center/start/end fixed; varies `point` between the interior
    # of the acute span (XY+ quadrant) and the interior of the reflex
    # span (XY- quadrant).
    #
    # OBSERVED CONTRACT on Rhino 8 / RookNative 2026-04-19:
    # ON_DimAngular::Measurement() DOES honor `point` for numeric span
    # selection. Point inside the principal span returns the principal
    # angle (~90° for a right angle); point inside the reflex span on
    # the opposite side returns the reflex angle (~270°). This pins
    # point as a LOAD-BEARING measurement input, not just a visual
    # placement hint.
    #
    # Initial ship of this test had a lax `90 OR 270` assertion per
    # Codex 2026-04-19 review; tightening exposed that the actual
    # observed behavior is the reflex-honoring one (270° for the
    # opposite quadrant). The handler doc + MCP tool description were
    # updated in the same commit to reflect this correct contract,
    # rather than the principal-only assumption that had been made
    # without ground truth.
    await _purge_objects()

    base = {
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
    }

    acute = await _tool_dim_angle({**base, "point": [5, 5, 0]})
    reflex_position = await _tool_dim_angle({**base, "point": [-5, -5, 0]})

    assert abs(acute.get("measuredValue") - 90.0) < 1e-4, (
        f"Acute-span measurement drifted from 90°: {acute!r}"
    )
    assert abs(reflex_position.get("measuredValue") - 270.0) < 1e-4, (
        f"Reflex-position measurement should be 270° (360° - 90°) when "
        f"`point` sits in the reflex quadrant. Got "
        f"{reflex_position.get('measuredValue')!r}. If this fails with "
        f"~90°, the SDK may have stopped honoring reflex selection — "
        f"update handler docs + MCP tool description in lockstep."
    )


# --- Validation failures ---------------------------------------------------


async def test_missing_center_rejected(fresh_document):
    status, envelope = await _post_dim_angle_raw({
        "start": [10, 0, 0],
        "end":   [0, 10, 0],
        "point": [5, 5, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "center" in envelope["data"]["errorMessage"].lower()


async def test_missing_start_rejected(fresh_document):
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "end":    [0, 10, 0],
        "point":  [5, 5, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_missing_end_rejected(fresh_document):
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "point":  [5, 5, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_missing_point_rejected(fresh_document):
    # `point` is required — not optional. No algorithmic default;
    # caller must be explicit about which span to dimension.
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "point" in envelope["data"]["errorMessage"].lower()


async def test_degenerate_start_ray_rejected(fresh_document):
    # center == start → Unitize-fail on rayA.
    status, envelope = await _post_dim_angle_raw({
        "center": [5, 5, 5],
        "start":  [5, 5, 5],
        "end":    [10, 0, 0],
        "point":  [7, 2, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_degenerate_end_ray_rejected(fresh_document):
    # center == end → Unitize-fail on rayB.
    status, envelope = await _post_dim_angle_raw({
        "center": [5, 5, 5],
        "start":  [10, 0, 0],
        "end":    [5, 5, 5],
        "point":  [7, 2, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_overlong_center_rejected(fresh_document):
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0, 99],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
        "point":  [5, 5, 0],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    status, envelope = await _post_dim_angle_raw({
        "center": [0, 0, 0],
        "start":  [10, 0, 0],
        "end":    [0, 10, 0],
        "point":  [5, 5, 0],
        "layer":  "NonExistentLayer__PR5_strict_check__",
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
