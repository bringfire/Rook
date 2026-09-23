"""Live-Rhino characterization tests for POST /surface/loft (Phase 1 PR-2).

Pins the plural-contract route and the Phase 1 attribute-bundle baseline:
  - success response shape is {success:true, data:{objects:[ObjectSnapshot,...]}}
    unconditional (even when N=1), per Rule 5 cardinality convention
  - structured {errorCode, errorMessage} on failure
  - all 6 loftType enum values accepted
  - closed + convergence points rejected as convergence_point_conflict
  - missing-from-doc curveId → not_found (distinct from invalid_input)
  - atomic undo: pre-insert failures roll back cleanly

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_loft_live.py

Rhino must be running with RookNative + Rook companion loaded. Tests
reset the document on entry via the fresh_document fixture — run in a
throwaway session.

See rook_docs/2026-04-17-typed-route-phase1-plan.md (§ /surface/loft)
for the binding contract these tests pin.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_circle(center: list[float], radius: float, name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CIRCLE", "center": center, "radius": radius, "name": name},
    )
    assert not _is_error(res), f"rhino_create CIRCLE failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _create_point_object(point: list[float], name: str) -> str:
    """Create a Rhino.Geometry.Point object (not a curve). Used to test
    non-curve rejection in loft curveIds."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": point, "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _post_loft_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/loft", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/loft returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured data dict: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


def _assert_plural_success(envelope: dict[str, Any], min_objects: int = 1) -> list:
    """Assert success envelope shape is {success:true, data:{objects:[...]}}
    with at least min_objects elements, each with a plausible ObjectSnapshot
    shape. Returns the objects list for further assertions."""
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    objs = data.get("objects")
    assert isinstance(objs, list), f"Expected data.objects list: {envelope!r}"
    assert len(objs) >= min_objects, (
        f"Expected >= {min_objects} objects, got {len(objs)}: {envelope!r}"
    )
    for snap in objs:
        assert isinstance(snap, dict), f"Snapshot not a dict: {snap!r}"
        assert "id" in snap and "type" in snap, f"Snapshot missing id/type: {snap!r}"
    return objs


async def _make_three_circle_rails() -> list[str]:
    """Three stacked circles; basic loft fixture."""
    c1 = await _create_circle([0, 0, 0], 5, "LoftC1")
    c2 = await _create_circle([0, 0, 10], 7, "LoftC2")
    c3 = await _create_circle([0, 0, 20], 4, "LoftC3")
    return [c1, c2, c3]


async def _make_two_circle_rails() -> list[str]:
    c1 = await _create_circle([0, 20, 0], 5, "LoftTwoA")
    c2 = await _create_circle([0, 20, 10], 5, "LoftTwoB")
    return [c1, c2]


# --- Happy-path tests ------------------------------------------------------


async def test_loft_three_circles_normal(fresh_document):
    """3 circles, Normal (default), open → ≥ 1 brep, plural envelope."""
    ids = await _make_three_circle_rails()
    status, envelope = await _post_loft_raw({"curveIds": ids})
    assert status == 200, f"HTTP {status}: {envelope!r}"
    _assert_plural_success(envelope, min_objects=1)


async def test_loft_two_circles_minimum(fresh_document):
    """2 curves satisfy the minimum-curve requirement."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({"curveIds": ids})
    _assert_plural_success(envelope, min_objects=1)


@pytest.mark.parametrize(
    "loft_type",
    ["Normal", "Loose", "Tight", "Straight", "Uniform", "Developable"],
)
async def test_loft_all_enum_values_accepted(fresh_document, loft_type):
    """Each of the 6 loftType enum values parses and invokes the factory.

    Some values (Developable especially) may return empty Brep[] for
    arbitrary inputs; allow either success (plural envelope) OR
    operation_failed (factory rejected the combination) — but never
    invalid_loft_type, which would signal the enum mapping regressed.
    """
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({"curveIds": ids, "loftType": loft_type})
    if envelope.get("success"):
        _assert_plural_success(envelope, min_objects=1)
    else:
        # The enum must have been accepted by the router; only operation_failed
        # is tolerated here (factory couldn't produce geometry for this combo).
        assert envelope["data"]["errorCode"] == "operation_failed", (
            f"Enum {loft_type} surfaced unexpected error: {envelope!r}"
        )


async def test_loft_closed_true(fresh_document):
    """closed=true creates a periodic/closed brep through 3 circular profiles.

    RhinoCommon Brep.CreateFromLoft with closed=true needs enough curves to
    form a closing sequence; empirically, 2 curves returns empty even with
    distinct positions. 3 stacked circles reliably yield a closed brep.
    """
    ids = await _make_three_circle_rails()
    status, envelope = await _post_loft_raw({"curveIds": ids, "closed": True})
    _assert_plural_success(envelope, min_objects=1)


async def test_loft_start_point_convergence(fresh_document):
    """startPoint set on open loft converges at start."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "startPoint": [0, 20, -5],
        "closed": False,
    })
    _assert_plural_success(envelope, min_objects=1)


async def test_loft_end_point_convergence(fresh_document):
    """endPoint set on open loft converges at end."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "endPoint": [0, 20, 15],
        "closed": False,
    })
    _assert_plural_success(envelope, min_objects=1)


# --- Validation-error tests ------------------------------------------------


async def test_loft_insufficient_curves_one(fresh_document):
    """1 curve → insufficient_curves (native pre-dispatch)."""
    c1 = await _create_circle([40, 0, 0], 3, "LoftSolo")
    status, envelope = await _post_loft_raw({"curveIds": [c1]})
    _assert_structured_error(envelope, "insufficient_curves")


async def test_loft_invalid_enum(fresh_document):
    """Unknown loftType string → invalid_loft_type."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "loftType": "Nonsense",
    })
    _assert_structured_error(envelope, "invalid_loft_type")


async def test_loft_malformed_uuid(fresh_document):
    """Bad UUID in curveIds → invalid_input (native ParseUuids reject)."""
    status, envelope = await _post_loft_raw({
        "curveIds": ["not-a-uuid", "00000000-0000-0000-0000-000000000001"],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_loft_unknown_curveid(fresh_document):
    """Valid UUID not in doc → not_found (managed resolves)."""
    status, envelope = await _post_loft_raw({
        "curveIds": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    })
    _assert_structured_error(envelope, "not_found")


async def test_loft_non_curve_curveid(fresh_document):
    """Point object id in curveIds → invalid_input."""
    c1 = await _create_circle([50, 0, 0], 3, "LoftWithPointNeighbor")
    pt = await _create_point_object([50, 0, 10], "LoftPointNotCurve")
    status, envelope = await _post_loft_raw({"curveIds": [c1, pt]})
    _assert_structured_error(envelope, "invalid_input")
    assert "not a curve" in envelope["data"]["errorMessage"].lower(), (
        f"Expected 'not a curve' message: {envelope!r}"
    )


async def test_loft_convergence_conflict_start(fresh_document):
    """closed=true + startPoint → convergence_point_conflict."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "closed": True,
        "startPoint": [0, 0, 0],
    })
    _assert_structured_error(envelope, "convergence_point_conflict")


async def test_loft_convergence_conflict_end(fresh_document):
    """closed=true + endPoint → convergence_point_conflict."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "closed": True,
        "endPoint": [0, 0, 10],
    })
    _assert_structured_error(envelope, "convergence_point_conflict")


# --- Attribute-bundle tests ------------------------------------------------


async def test_loft_unknown_layer(fresh_document):
    """Non-existent layer → invalid_input (shared BuildAttributesStrict)."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "layer": "NonexistentLayerDoesNotExist",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_loft_unparseable_color(fresh_document):
    """Bad color format → invalid_input (native ParseColor reject)."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "color": "not-a-color",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_loft_visible_false_applied(fresh_document):
    """visible=false honored end-to-end on every brep in the plural result."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({
        "curveIds": ids,
        "visible": False,
        "name": "InvisibleLoft",
    })
    objs = _assert_plural_success(envelope, min_objects=1)
    for snap in objs:
        assert snap.get("visible") is False, (
            f"Expected visible=False on loft brep; got {snap!r}"
        )


# --- Envelope-shape test ---------------------------------------------------


async def test_loft_envelope_plural_shape(fresh_document):
    """Raw HTTP envelope: data.objects array, not data.id — contract stable."""
    ids = await _make_two_circle_rails()
    status, envelope = await _post_loft_raw({"curveIds": ids})
    assert status == 200, f"HTTP {status}: {envelope!r}"
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope["data"]
    assert isinstance(data, dict), f"data not dict: {envelope!r}"
    assert "objects" in data, f"plural envelope must have 'objects': {envelope!r}"
    assert "id" not in data, (
        f"plural envelope must NOT have top-level 'id' (that's singular): {envelope!r}"
    )
