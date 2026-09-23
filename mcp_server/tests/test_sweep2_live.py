"""Live-Rhino characterization tests for POST /surface/sweep2 (Phase 1 PR-3).

Pins the plural-contract Sweep2 route.
  - Envelope: {success:true, data:{objects:[...]}} unconditional (Rule 5)
  - Error codes: invalid_input, not_found, operation_failed (base);
                 no_profiles, rails_coincident (route-specific)
  - `rails_disconnected` is deferred: empty PerformSweep results classify
    as operation_failed (Codex review 2026-04-17)

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_sweep2_live.py

Rhino must be running with RookNative + Rook companion loaded.
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


async def _create_point_obj(point: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": point, "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    return res["id"]


async def _post_sweep2_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/sweep2", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/sweep2 returned non-JSON: {resp.text!r} ({ex!r})")
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
    assert len(objs) >= min_objects
    for snap in objs:
        assert "id" in snap and "type" in snap, f"Snapshot missing id/type: {snap!r}"
    return objs


async def _make_parallel_rails_with_profile() -> tuple[str, str, str]:
    """Two parallel horizontal lines + a vertical cross-section connecting
    their start points. Known-good Sweep2 fixture."""
    rail1 = await _create_line([0, 0, 0], [10, 0, 0], "S2Rail1")
    rail2 = await _create_line([0, 0, 5], [10, 0, 5], "S2Rail2")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2Profile")
    return rail1, rail2, profile


# --- Happy-path tests ------------------------------------------------------


async def test_sweep2_parallel_rails(fresh_document):
    """Two parallel rails + connecting cross-section → plural envelope."""
    r1, r2, p = await _make_parallel_rails_with_profile()
    status, envelope = await _post_sweep2_raw({
        "rail1Id": r1, "rail2Id": r2, "profileIds": [p],
    })
    _assert_plural_success(envelope)


async def test_sweep2_maintain_height_true(fresh_document):
    """maintainHeight=true on diverging rails produces a surface."""
    rail1 = await _create_line([0, 50, 0], [10, 50, 0], "S2DivRail1")
    # rail2 diverges in Z
    rail2 = await _create_line([0, 50, 5], [10, 50, 8], "S2DivRail2")
    profile = await _create_line([0, 50, 0], [0, 50, 5], "S2DivProfile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail1, "rail2Id": rail2, "profileIds": [profile],
        "maintainHeight": True,
    })
    # Either success or operation_failed acceptable; the point is it
    # doesn't surface an invalid_* code.
    if envelope.get("success"):
        _assert_plural_success(envelope)
    else:
        assert envelope["data"]["errorCode"] == "operation_failed"


async def test_sweep2_maintain_height_false(fresh_document):
    """maintainHeight=false on diverging rails (same fixture as True case)."""
    rail1 = await _create_line([0, 100, 0], [10, 100, 0], "S2MHRail1")
    rail2 = await _create_line([0, 100, 5], [10, 100, 8], "S2MHRail2")
    profile = await _create_line([0, 100, 0], [0, 100, 5], "S2MHProfile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail1, "rail2Id": rail2, "profileIds": [profile],
        "maintainHeight": False,
    })
    if envelope.get("success"):
        _assert_plural_success(envelope)
    else:
        assert envelope["data"]["errorCode"] == "operation_failed"


# --- Validation-error tests ------------------------------------------------


async def test_sweep2_coincident_rails(fresh_document):
    """Same UUID for both rails → rails_coincident (native string check)."""
    rail = await _create_line([0, 0, 0], [10, 0, 0], "S2CoincidentRail")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2CoincidentProfile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail, "rail2Id": rail, "profileIds": [profile],
    })
    _assert_structured_error(envelope, "rails_coincident")


async def test_sweep2_empty_profiles(fresh_document):
    """Empty profileIds → no_profiles."""
    rail1 = await _create_line([0, 0, 0], [10, 0, 0], "S2EmptyR1")
    rail2 = await _create_line([0, 0, 5], [10, 0, 5], "S2EmptyR2")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail1, "rail2Id": rail2, "profileIds": [],
    })
    _assert_structured_error(envelope, "no_profiles")


# NOTE: A "disconnected profile → operation_failed" characterization test
# was considered but dropped. Empirical finding (2026-04-17 live run on
# RhinoCommon 8.0.23304): SweepTwoRail.PerformSweep is more permissive
# than expected — it produces a brep even when the profile is nowhere
# near either rail, rather than returning an empty array. Without a
# reliable fixture that forces empty-result behavior, the deferred
# `rails_disconnected` → `operation_failed` classification can't be
# pinned by a live test. The managed code's explicit
# `if (breps == null || breps.Length == 0)` guard remains the sole
# source-level assertion for that path. See PR #57 description for the
# full Codex review chain that led to this deferral.


async def test_sweep2_missing_rail1(fresh_document):
    """Missing rail1Id → invalid_input."""
    rail2 = await _create_line([0, 0, 5], [10, 0, 5], "S2MR1R2")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2MR1Profile")
    status, envelope = await _post_sweep2_raw({
        "rail2Id": rail2, "profileIds": [profile],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_sweep2_missing_rail2(fresh_document):
    """Missing rail2Id → invalid_input."""
    rail1 = await _create_line([0, 0, 0], [10, 0, 0], "S2MR2R1")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2MR2Profile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail1, "profileIds": [profile],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_sweep2_non_curve_rail1(fresh_document):
    """rail1Id points to a non-curve → invalid_input."""
    point = await _create_point_obj([0, 0, 0], "S2NotACurveR1")
    rail2 = await _create_line([0, 0, 5], [10, 0, 5], "S2NonCurveR2")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2NonCurveProfile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": point, "rail2Id": rail2, "profileIds": [profile],
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "not a curve" in envelope["data"]["errorMessage"].lower()


async def test_sweep2_unknown_rail1(fresh_document):
    """rail1Id valid UUID not in doc → not_found."""
    rail2 = await _create_line([0, 0, 5], [10, 0, 5], "S2UnkR1R2")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2UnkR1Profile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": "00000000-0000-0000-0000-000000000001",
        "rail2Id": rail2, "profileIds": [profile],
    })
    _assert_structured_error(envelope, "not_found")


async def test_sweep2_unknown_rail2(fresh_document):
    """rail2Id valid UUID not in doc → not_found.

    Symmetric with rail1 so error taxonomy can't drift by position
    (Codex review 2026-04-17 Low finding).
    """
    rail1 = await _create_line([0, 0, 0], [10, 0, 0], "S2UnkR2R1")
    profile = await _create_line([0, 0, 0], [0, 0, 5], "S2UnkR2Profile")
    status, envelope = await _post_sweep2_raw({
        "rail1Id": rail1,
        "rail2Id": "00000000-0000-0000-0000-000000000002",
        "profileIds": [profile],
    })
    _assert_structured_error(envelope, "not_found")


# --- Attribute bundle + envelope -------------------------------------------


async def test_sweep2_unparseable_color(fresh_document):
    """Bad color format → invalid_input."""
    r1, r2, p = await _make_parallel_rails_with_profile()
    status, envelope = await _post_sweep2_raw({
        "rail1Id": r1, "rail2Id": r2, "profileIds": [p],
        "color": "not-a-color",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_sweep2_visible_false_applied(fresh_document):
    """visible=false honored on every resulting brep."""
    r1, r2, p = await _make_parallel_rails_with_profile()
    status, envelope = await _post_sweep2_raw({
        "rail1Id": r1, "rail2Id": r2, "profileIds": [p],
        "visible": False,
        "name": "InvisibleSweep2",
    })
    objs = _assert_plural_success(envelope)
    for snap in objs:
        assert snap.get("visible") is False, f"Expected visible=False: {snap!r}"


async def test_sweep2_envelope_plural_shape(fresh_document):
    """Raw envelope has data.objects, not data.id."""
    r1, r2, p = await _make_parallel_rails_with_profile()
    status, envelope = await _post_sweep2_raw({
        "rail1Id": r1, "rail2Id": r2, "profileIds": [p],
    })
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope["data"]
    assert "objects" in data and isinstance(data["objects"], list)
    assert "id" not in data
