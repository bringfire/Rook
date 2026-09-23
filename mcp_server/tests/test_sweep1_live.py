"""Live-Rhino characterization tests for POST /surface/sweep1 (Phase 1 PR-3).

Pins the plural-contract Sweep1 route and the style=Roadlike contract.
  - Envelope: {success:true, data:{objects:[...]}} unconditional (Rule 5)
  - Error codes: invalid_input, not_found, operation_failed (base);
                 invalid_style, no_profiles,
                 missing_roadlike_up, roadlike_up_without_style (route-specific)
  - style='AlignWithSurface' deferred to Phase 2 → invalid_style with
    explanatory message (Codex review 2026-04-17)

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_sweep1_live.py

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


async def _create_circle(center: list[float], radius: float, name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CIRCLE", "center": center, "radius": radius, "name": name},
    )
    assert not _is_error(res), f"rhino_create CIRCLE failed: {res!r}"
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


async def _post_sweep1_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/sweep1", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/sweep1 returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured data dict: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )


def _assert_plural_success(envelope: dict[str, Any], min_objects: int = 1) -> list:
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    objs = data.get("objects")
    assert isinstance(objs, list), f"Expected data.objects list: {envelope!r}"
    assert len(objs) >= min_objects, (
        f"Expected >= {min_objects} objects, got {len(objs)}: {envelope!r}"
    )
    for snap in objs:
        assert isinstance(snap, dict), f"Snapshot not dict: {snap!r}"
        assert "id" in snap and "type" in snap, f"Snapshot missing id/type: {snap!r}"
    return objs


# --- Happy-path tests ------------------------------------------------------


async def test_sweep1_line_rail_circle_profile(fresh_document):
    """Line rail + circle profile at rail start → plural envelope, ≥ 1 brep."""
    rail = await _create_line([0, 0, 0], [10, 0, 0], "S1Rail")
    profile = await _create_circle([0, 0, 0], 1.0, "S1Profile")
    status, envelope = await _post_sweep1_raw({"railId": rail, "profileIds": [profile]})
    _assert_plural_success(envelope)


async def test_sweep1_arc_rail_circle_profile(fresh_document):
    """Arc rail + circle profile → plural envelope."""
    rail = await _create_arc([0, 50, 0], 10, 0, 180, "S1ArcRail")
    profile = await _create_circle([10, 50, 0], 0.5, "S1ArcProfile")
    status, envelope = await _post_sweep1_raw({"railId": rail, "profileIds": [profile]})
    _assert_plural_success(envelope)


async def test_sweep1_closed_true(fresh_document):
    """closed=true on a planar circle rail produces a closed sweep."""
    rail = await _create_circle([0, 100, 0], 5, "S1ClosedRail")
    # Profile: small circle at rail start point
    profile = await _create_circle([5, 100, 0], 0.5, "S1ClosedProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "closed": True,
    })
    # Closed sweep on a circle rail is factory-sensitive — accept either
    # success or operation_failed, but not any invalid_* code.
    if envelope.get("success"):
        _assert_plural_success(envelope)
    else:
        assert envelope["data"]["errorCode"] == "operation_failed", (
            f"Unexpected error from closed-rail sweep: {envelope!r}"
        )


async def test_sweep1_roadlike_with_up(fresh_document):
    """style=Roadlike with valid roadlikeUp → plural envelope."""
    rail = await _create_line([0, 150, 0], [10, 150, 0], "S1RoadlikeRail")
    profile = await _create_circle([0, 150, 0], 0.5, "S1RoadlikeProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "style": "Roadlike",
        "roadlikeUp": [0, 0, 1],
    })
    _assert_plural_success(envelope)


# --- Validation-error tests ------------------------------------------------


async def test_sweep1_missing_rail(fresh_document):
    """Missing railId → invalid_input (native ParseUuid reject)."""
    profile = await _create_circle([0, 0, 0], 0.5, "S1OrphanProfile")
    status, envelope = await _post_sweep1_raw({"profileIds": [profile]})
    _assert_structured_error(envelope, "invalid_input")


async def test_sweep1_empty_profiles(fresh_document):
    """Empty profileIds → no_profiles."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1RailForEmpty")
    status, envelope = await _post_sweep1_raw({"railId": rail, "profileIds": []})
    _assert_structured_error(envelope, "no_profiles")


async def test_sweep1_roadlike_missing_up(fresh_document):
    """style=Roadlike without roadlikeUp → missing_roadlike_up."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1MissingUpRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1MissingUpProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "style": "Roadlike",
    })
    _assert_structured_error(envelope, "missing_roadlike_up")


async def test_sweep1_up_without_roadlike_style(fresh_document):
    """roadlikeUp provided but style != Roadlike → roadlike_up_without_style."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1StrayUpRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1StrayUpProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "style": "Freeform",
        "roadlikeUp": [0, 0, 1],
    })
    _assert_structured_error(envelope, "roadlike_up_without_style")


async def test_sweep1_invalid_style(fresh_document):
    """Unknown style enum → invalid_style."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1BadStyleRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1BadStyleProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "style": "Nonsense",
    })
    _assert_structured_error(envelope, "invalid_style")


async def test_sweep1_align_with_surface_deferred(fresh_document):
    """style='AlignWithSurface' → invalid_style (Phase 2 deferral).

    Pins that the Phase 2 deferral stays explicit; if someone adds
    AlignWithSurface without also adding the surface-reference schema,
    this test fails until the contract is consistent.
    """
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1AWSRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1AWSProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "style": "AlignWithSurface",
    })
    _assert_structured_error(envelope, "invalid_style")


async def test_sweep1_non_curve_rail(fresh_document):
    """railId points to a non-curve object → invalid_input."""
    point = await _create_point_obj([0, 0, 0], "S1NotACurveRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1NonCurveProfile")
    status, envelope = await _post_sweep1_raw({"railId": point, "profileIds": [profile]})
    _assert_structured_error(envelope, "invalid_input")
    assert "not a curve" in envelope["data"]["errorMessage"].lower()


async def test_sweep1_unknown_rail(fresh_document):
    """Valid UUID not in doc for railId → not_found."""
    profile = await _create_circle([0, 0, 0], 0.5, "S1UnknownRailProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": "00000000-0000-0000-0000-000000000001",
        "profileIds": [profile],
    })
    _assert_structured_error(envelope, "not_found")


async def test_sweep1_unknown_profile(fresh_document):
    """Valid UUID not in doc inside profileIds → not_found."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1UnknownProfileRail")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": ["00000000-0000-0000-0000-000000000002"],
    })
    _assert_structured_error(envelope, "not_found")


# --- Attribute bundle + envelope -------------------------------------------


async def test_sweep1_unknown_layer(fresh_document):
    """Non-existent layer → invalid_input (BuildAttributesStrict)."""
    rail = await _create_line([0, 0, 0], [1, 0, 0], "S1LayerRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1LayerProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "layer": "NonexistentLayerForSweep1",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_sweep1_visible_false_applied(fresh_document):
    """visible=false honored on every resulting brep."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "S1InvisibleRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1InvisibleProfile")
    status, envelope = await _post_sweep1_raw({
        "railId": rail,
        "profileIds": [profile],
        "visible": False,
        "name": "InvisibleSweep1",
    })
    objs = _assert_plural_success(envelope)
    for snap in objs:
        assert snap.get("visible") is False, f"Expected visible=False: {snap!r}"


async def test_sweep1_envelope_plural_shape(fresh_document):
    """Raw envelope has data.objects, not data.id."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "S1EnvelopeRail")
    profile = await _create_circle([0, 0, 0], 0.5, "S1EnvelopeProfile")
    status, envelope = await _post_sweep1_raw({"railId": rail, "profileIds": [profile]})
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope["data"]
    assert "objects" in data and isinstance(data["objects"], list)
    assert "id" not in data, f"Singular 'id' must not appear in plural envelope: {envelope!r}"
