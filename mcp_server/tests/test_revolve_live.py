"""Live-Rhino characterization tests for POST /surface/revolve (Phase 1 PR-4).

Pins the second singular-contract typed route (Pipe was the first).
  - Envelope: {success:true, data: <bare ObjectSnapshot>} (NOT plural)
  - Error codes: invalid_input, not_found, operation_failed (base);
                 axis_degenerate, angle_invalid (route-specific)
  - `curve_intersects_axis` is a DEFERRED PLAN-CODE: factory failures
    (including curve-intersects-axis) classify as operation_failed
    until a future PR adds geometric detection via Intersection.CurveLine.

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_revolve_live.py

Rhino must be running with RookNative + Rook companion loaded. Tests
reset the document on entry — run in a throwaway session.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_line(start: list[float], end: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _create_arc(center: list[float], radius: float, start_angle: float, end_angle: float, name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {
            "type": "ARC",
            "center": center,
            "radius": radius,
            "startAngle": start_angle,
            "endAngle": end_angle,
            "name": name,
        },
    )
    assert not _is_error(res), f"rhino_create ARC failed: {res!r}"
    return res["id"]


async def _create_point_obj(point: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": point, "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    return res["id"]


async def _post_revolve_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/revolve", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/revolve returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured data dict: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )


def _assert_singular_success(envelope: dict[str, Any]) -> dict[str, Any]:
    """Singular envelope: {success:true, data: <bare ObjectSnapshot>}.
    Distinctly NOT {objects:[...]} plural shape."""
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert "id" in data and "type" in data, f"Snapshot missing id/type: {data!r}"
    assert "objects" not in data, (
        f"Singular envelope must not have 'objects' key (that's plural): {envelope!r}"
    )
    return data


# --- Happy-path tests ------------------------------------------------------


async def test_revolve_line_profile_full_360(fresh_document):
    """Line profile + full 360° revolve around Z axis → cylinder-like brep."""
    # Vertical line offset from axis, so revolving produces a cylindrical surface.
    profile = await _create_line([5, 0, 0], [5, 0, 10], "RevLineProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
    })
    _assert_singular_success(envelope)


async def test_revolve_arc_profile_full_360(fresh_document):
    """Arc profile + full revolve around vertical axis → sphere-like surface."""
    profile = await _create_arc([0, 50, 5], 5, 0, 180, "RevArcProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 50, 0],
        "axisEnd": [0, 50, 1],
    })
    _assert_singular_success(envelope)


async def test_revolve_partial_sweep(fresh_document):
    """startAngle=90, endAngle=270 → 180° partial revolve."""
    profile = await _create_line([5, 100, 0], [5, 100, 10], "RevPartialProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 100, 0],
        "axisEnd": [0, 100, 1],
        "startAngle": 90,
        "endAngle": 270,
    })
    _assert_singular_success(envelope)


async def test_revolve_non_z_axis(fresh_document):
    """Axis along X (not default Z) → revolve works about arbitrary axis."""
    # Profile offset from the X axis in the Y direction.
    profile = await _create_line([0, 5, 150], [10, 5, 150], "RevXAxisProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 0, 150],
        "axisEnd": [1, 0, 150],
    })
    _assert_singular_success(envelope)


# --- Validation-error tests (structured {errorCode, errorMessage}) ---------


async def test_revolve_axis_degenerate(fresh_document):
    """axisStart == axisEnd → axis_degenerate."""
    profile = await _create_line([5, 0, 0], [5, 0, 10], "RevDegenAxisProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 0],
    })
    _assert_structured_error(envelope, "axis_degenerate")


async def test_revolve_angle_invalid(fresh_document):
    """startAngle == endAngle → angle_invalid."""
    profile = await _create_line([5, 0, 0], [5, 0, 10], "RevAngleInvalidProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
        "startAngle": 90,
        "endAngle": 90,
    })
    _assert_structured_error(envelope, "angle_invalid")


async def test_revolve_missing_curveid(fresh_document):
    """Missing curveId → invalid_input (native ParseUuid reject)."""
    status, envelope = await _post_revolve_raw({
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_missing_axis_start(fresh_document):
    """Missing axisStart → invalid_input."""
    profile = await _create_line([5, 0, 0], [5, 0, 10], "RevMissingStartProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisEnd": [0, 0, 1],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_missing_axis_end(fresh_document):
    """Missing axisEnd → invalid_input."""
    profile = await _create_line([5, 0, 0], [5, 0, 10], "RevMissingEndProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 0, 0],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_malformed_uuid(fresh_document):
    """Non-UUID string in curveId → invalid_input."""
    status, envelope = await _post_revolve_raw({
        "curveId": "not-a-uuid",
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_unknown_curveid(fresh_document):
    """Valid UUID not in doc → not_found."""
    status, envelope = await _post_revolve_raw({
        "curveId": "00000000-0000-0000-0000-000000000001",
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
    })
    _assert_structured_error(envelope, "not_found")


async def test_revolve_non_curve_curveid(fresh_document):
    """curveId points to a non-curve object → invalid_input."""
    point = await _create_point_obj([0, 0, 0], "RevNotACurve")
    status, envelope = await _post_revolve_raw({
        "curveId": point,
        "axisStart": [0, 0, 0],
        "axisEnd": [0, 0, 1],
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "not a curve" in envelope["data"]["errorMessage"].lower()


# --- Attribute-bundle tests (pin the singular strict path) -----------------


async def test_revolve_unknown_layer(fresh_document):
    """Non-existent layer → invalid_input (BuildAttributesStrict)."""
    profile = await _create_line([5, 200, 0], [5, 200, 10], "RevLayerProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 200, 0],
        "axisEnd": [0, 200, 1],
        "layer": "NonexistentLayerForRevolve",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_non_boolean_visible(fresh_document):
    """Non-boolean 'visible' → invalid_input (native reject).

    Pins the singular-contract strict path: Revolve is the second singular
    typed route after Pipe, and this test ensures the attribute-bundle
    validation fires on the non-plural seam too. Without this, the singular
    strict path would only be inferred from Pipe's coverage.
    """
    profile = await _create_line([5, 250, 0], [5, 250, 10], "RevBadVisibleProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 250, 0],
        "axisEnd": [0, 250, 1],
        "visible": "no",  # string, not boolean
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_revolve_visible_false_applied(fresh_document):
    """visible=false honored end-to-end on the resulting brep."""
    profile = await _create_line([5, 300, 0], [5, 300, 10], "RevInvisibleProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 300, 0],
        "axisEnd": [0, 300, 1],
        "visible": False,
        "name": "InvisibleRevolve",
    })
    snap = _assert_singular_success(envelope)
    assert snap.get("visible") is False, (
        f"Expected ObjectSnapshot.visible=False; got {snap!r}"
    )


# --- Envelope shape --------------------------------------------------------


async def test_revolve_envelope_singular_shape(fresh_document):
    """Raw envelope: data has id at top level, not data.objects[]."""
    profile = await _create_line([5, 350, 0], [5, 350, 10], "RevEnvelopeProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 350, 0],
        "axisEnd": [0, 350, 1],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    data = _assert_singular_success(envelope)
    # Extra explicit check beyond the helper:
    assert "objects" not in data
    assert "id" in data


# --- curve_intersects_axis detection (Phase 3 PR-1, 2026-04-21) ------------
# Phase 1 deferred `curve_intersects_axis` — detection was documented as
# needing geometric curve-line intersection with tolerance-sensitive handling,
# and until Phase 3 PR-1 a curve that crossed the revolution axis would
# silently produce self-intersecting geometry with `success: true` (empirically
# verified via Probe 1 Case 1.2 on 2026-04-21). The detection check now runs
# in CreateHandler.CreateRevolveStrict BEFORE RevSurface.Create, using
# parameter-space classification of Intersection.CurveLine events. See
# rook_docs/2026-04-21-typed-route-phase3-pr1-plan.md for the full rule.


async def _create_polyline(points: list[list[float]], name: str) -> str:
    """Helper: create a polyline through the given points, return its id."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POLYLINE", "points": points, "name": name},
    )
    assert not _is_error(res), f"rhino_create POLYLINE failed: {res!r}"
    return res["id"]


async def test_revolve_curve_crosses_axis_interior(fresh_document):
    """Line profile crossing Z axis interior → curve_intersects_axis.

    Promotes Probe 1 Case 1.2 (2026-04-21) to a regression test. Before PR-1
    this payload returned success: true with a self-intersecting brep — no
    diagnostic signal for the caller. PR-1 pre-validates via
    Intersection.CurveLine and rejects interior crossings.
    """
    # Line from (-2,0,3) to (2,0,7) — crosses the Z axis at (0,0,5).
    profile = await _create_line([-2, 400, 3], [2, 400, 7], "RevCrossAxisProfile")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 400, 0],
        "axisEnd": [0, 400, 10],
    })
    _assert_structured_error(envelope, "curve_intersects_axis")


async def test_revolve_polyline_crosses_axis_twice_rejected(fresh_document):
    """Polyline with two interior axis crossings → curve_intersects_axis.

    Pins the detection loop's "first-hit-wins" semantics — the first interior
    event discovered causes rejection; the rest of the event list is not
    scanned. Polyline via (2,0,0) → (-2,0,5) → (2,0,10) crosses the Z axis
    at (0,0,2.5) and (0,0,7.5), both interior.
    """
    profile = await _create_polyline(
        [[2, 450, 0], [-2, 450, 5], [2, 450, 10]],
        "RevPolylineCrossAxis",
    )
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 450, 0],
        "axisEnd": [0, 450, 10],
    })
    _assert_structured_error(envelope, "curve_intersects_axis")


async def test_revolve_endpoint_on_axis_still_accepted(fresh_document):
    """Line profile with endpoint ON axis → still accepts (legal cone-with-pole).

    CRITICAL REGRESSION FLOOR. Guards against tolerance-too-loose →
    misclassifying endpoint-touch as interior-crossing. Promotes Probe 1
    Case 1.1 (2026-04-21). The parameter-space classifier checks ParameterA
    vs Curve.Domain.{Min,Max} with RhinoMath.ZeroTolerance — if this check
    regresses, vase-profile geometry (anchored on the axis at one end)
    starts failing.
    """
    # Line from (0,0,0) [ON Z axis] to (5,0,5). Start point on axis, end
    # point off. Revolving 360° produces a cone-with-pole at the origin.
    profile = await _create_line([0, 500, 0], [5, 500, 5], "RevEndpointOnAxis")
    status, envelope = await _post_revolve_raw({
        "curveId": profile,
        "axisStart": [0, 500, 0],
        "axisEnd": [0, 500, 10],
    })
    _assert_singular_success(envelope)
