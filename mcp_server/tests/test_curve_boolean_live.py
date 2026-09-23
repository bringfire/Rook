"""Live-Rhino characterization tests for POST /curve/boolean (Phase 2 PR-4).

Pins the plural-contract, three-intents-to-one-endpoint shape for the
second managed-bridge-reuse route in CurvesHandler.cpp:
  - success response shape is {success:true, data:{objects:[ObjectSnapshot,...]}}
  - structured {errorCode, errorMessage} on failure
  - operation enum validation (union | difference | intersection)
  - per-operation cardinality (union ≥ 2, diff/intersection exactly 2)
  - tolerance rejection (non-positive)
  - empty-factory-result normalization (disjoint intersection, fully-erased
    difference) → operation_failed per plural-contract atomicity
  - factory-permissive-smoke per Common Plan amendment (2026-04-20)

Uses Curve.CreateBooleanUnion / _Difference / _Intersection.
Region form (Curve.CreateBooleanRegions), combineRegions flag, and the
1-minuend + N-subtractor difference overload are deferred per plan-doc
§Non-goals.

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_curve_boolean_live.py

See rook_docs/2026-04-20-phase2-surface-curve-plan.md (§ /curve/boolean
sub-plan) for the binding contract these tests pin.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_circle_xy(center: list[float], radius: float, name: str) -> str:
    """Create a closed circle curve in world-XY plane at `center`."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CIRCLE", "center": center, "radius": radius, "name": name},
    )
    assert not _is_error(res), f"rhino_create CIRCLE failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _create_circle_tilted(center: list[float], radius: float, name: str) -> str:
    """Create a circle in a plane tilted ~45° off XY. Used for
    non-coplanar-input pinning (factory returns empty Curve[]).
    """
    from rook.server import _mcp_tool_executor

    code = f"""
import scriptcontext as sc
from Rhino.Geometry import Plane, Point3d, Vector3d, Circle

plane = Plane(Point3d({center[0]}, {center[1]}, {center[2]}),
              Vector3d(1, 0, 1))
c = Circle(plane, Point3d({center[0]}, {center[1]}, {center[2]}), {radius})
nc = c.ToNurbsCurve()
attrs = sc.doc.CreateDefaultAttributes()
attrs.Name = "{name}"
gid = sc.doc.Objects.AddCurve(nc, attrs)
print(str(gid))
"""
    res = await _mcp_tool_executor("rhino_execute", {"code": code})
    assert not _is_error(res), f"rhino_execute tilted circle failed: {res!r}"
    output = (res.get("output") or "").strip().splitlines()
    assert output, f"rhino_execute returned no output: {res!r}"
    gid = output[-1].strip()
    assert gid, f"tilted-circle gid empty: {res!r}"
    return gid


async def _create_line(start: list[float], end: list[float], name: str) -> str:
    """Create an open line curve — for open-input-rejected tests."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _create_point_object(point: list[float], name: str) -> str:
    """Create a Rhino.Geometry.Point object — for non-curve-id test."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": point, "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    return res["id"]


async def _post_curve_boolean_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST to /curve/boolean directly and return (status, envelope)."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/curve/boolean", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/curve/boolean returned non-JSON: {resp.text!r} ({ex!r})")
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
    """Assert {success:true, data:{objects:[...]}} with ≥ min_objects
    entries. Returns the objects list for further assertions."""
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


# --- Happy-path tests ------------------------------------------------------


async def test_curve_boolean_union_two_overlapping_circles(fresh_document):
    """(a) Union of 2 overlapping XY circles → 1 envelope curve."""
    a = await _create_circle_xy([0, 0, 0], 5, "UnionA")
    b = await _create_circle_xy([3, 0, 0], 5, "UnionB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, b],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    objs = _assert_plural_success(envelope, min_objects=1)
    assert len(objs) == 1, f"Expected exactly 1 envelope curve, got {len(objs)}: {envelope!r}"


async def test_curve_boolean_difference_two_overlapping_circles(fresh_document):
    """(b) Difference of 2 overlapping XY circles → ≥ 1 curve."""
    a = await _create_circle_xy([0, 10, 0], 5, "DiffA")
    b = await _create_circle_xy([3, 10, 0], 5, "DiffB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "difference",
        "curveIds": [a, b],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    _assert_plural_success(envelope, min_objects=1)


async def test_curve_boolean_intersection_two_overlapping_circles(fresh_document):
    """(c) Intersection of 2 overlapping XY circles → ≥ 1 curve."""
    a = await _create_circle_xy([0, 20, 0], 5, "IntxA")
    b = await _create_circle_xy([3, 20, 0], 5, "IntxB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "intersection",
        "curveIds": [a, b],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    _assert_plural_success(envelope, min_objects=1)


async def test_curve_boolean_union_three_overlapping_circles(fresh_document):
    """(d) Union of 3 overlapping closed curves → ≥ 1 curve."""
    a = await _create_circle_xy([0, 30, 0], 5, "Union3A")
    b = await _create_circle_xy([3, 30, 0], 5, "Union3B")
    c = await _create_circle_xy([6, 30, 0], 5, "Union3C")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, b, c],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    _assert_plural_success(envelope, min_objects=1)


async def test_curve_boolean_difference_nested_multi_output(fresh_document):
    """(e) Difference outer - inner (fully nested) → 2 curves.

    Pins the plural helper's multi-output branch: when subtracting a
    small inner circle fully contained within a larger outer circle,
    Curve.CreateBooleanDifference returns 2 curves (outer envelope +
    inner hole). The plural helper must insert both and return them
    in the objects array.
    """
    outer = await _create_circle_xy([0, 40, 0], 10, "NestedOuter")
    inner = await _create_circle_xy([0, 40, 0], 3, "NestedInner")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "difference",
        "curveIds": [outer, inner],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    objs = _assert_plural_success(envelope, min_objects=2)
    assert len(objs) == 2, (
        f"Nested outer-minus-inner should yield exactly 2 curves, "
        f"got {len(objs)}: {envelope!r}"
    )


# --- Validation-error tests (worker-thread rejection) ---------------------


async def test_curve_boolean_invalid_operation(fresh_document):
    """(f) operation='xor' → invalid_operation (worker-thread enum rejection)."""
    a = await _create_circle_xy([0, 50, 0], 5, "XorA")
    b = await _create_circle_xy([3, 50, 0], 5, "XorB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "xor",
        "curveIds": [a, b],
    })
    _assert_structured_error(envelope, "invalid_operation")


async def test_curve_boolean_union_insufficient_curves(fresh_document):
    """(g) Union with 1 curve → invalid_curve_count."""
    a = await _create_circle_xy([0, 60, 0], 5, "UnionOneA")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a],
    })
    _assert_structured_error(envelope, "invalid_curve_count")


async def test_curve_boolean_difference_wrong_count(fresh_document):
    """(h) Difference with 3 curves → invalid_curve_count (pair form only)."""
    a = await _create_circle_xy([0, 70, 0], 5, "Diff3A")
    b = await _create_circle_xy([3, 70, 0], 5, "Diff3B")
    c = await _create_circle_xy([6, 70, 0], 5, "Diff3C")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "difference",
        "curveIds": [a, b, c],
    })
    _assert_structured_error(envelope, "invalid_curve_count")


async def test_curve_boolean_intersection_wrong_count(fresh_document):
    """(i) Intersection with 3 curves → invalid_curve_count (pair form only)."""
    a = await _create_circle_xy([0, 80, 0], 5, "Intx3A")
    b = await _create_circle_xy([3, 80, 0], 5, "Intx3B")
    c = await _create_circle_xy([6, 80, 0], 5, "Intx3C")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "intersection",
        "curveIds": [a, b, c],
    })
    _assert_structured_error(envelope, "invalid_curve_count")


async def test_curve_boolean_missing_operation(fresh_document):
    """(j) Missing operation → invalid_input."""
    a = await _create_circle_xy([0, 90, 0], 5, "NoOpA")
    b = await _create_circle_xy([3, 90, 0], 5, "NoOpB")
    status, envelope = await _post_curve_boolean_raw({
        "curveIds": [a, b],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_curve_boolean_missing_curveids(fresh_document):
    """(k) Missing curveIds → invalid_input."""
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_curve_boolean_non_positive_tolerance(fresh_document):
    """(l) tolerance=0 → invalid_input (factory does NOT silently coerce —
    empirical 2026-04-20 probe showed tolerance<=0 produces empty Curve[],
    but that's ambiguous with a real factory failure; reject on worker
    thread for diagnostic specificity)."""
    a = await _create_circle_xy([0, 100, 0], 5, "ZeroTolA")
    b = await _create_circle_xy([3, 100, 0], 5, "ZeroTolB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, b],
        "tolerance": 0.0,
    })
    _assert_structured_error(envelope, "invalid_input")


# --- Factory-empty tests (operation_failed with diagnostic) ---------------
# These pin the collapsed error-code rhythm (PR-3 precedent). The factory
# produces empty Curve[] for many reasons — non-coplanar inputs, disjoint
# intersection, "fully erased" difference. All surface as operation_failed
# since the factory offers no error-classification surface.


async def test_curve_boolean_non_coplanar_inputs(fresh_document):
    """(m) Non-coplanar union (XY circle + tilted circle) → operation_failed.

    2026-04-20 probe: factory returns empty Curve[] for non-coplanar pairs
    without distinguishing the cause. Contract collapses to operation_failed
    with diagnostic message hinting "open, non-coplanar, or unsuitable".
    """
    a = await _create_circle_xy([0, 110, 0], 5, "NonCoplanarA")
    b = await _create_circle_tilted([3, 110, 0], 5, "NonCoplanarB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, b],
    })
    _assert_structured_error(envelope, "operation_failed")


async def test_curve_boolean_disjoint_intersection(fresh_document):
    """(n) Disjoint intersection → operation_failed.

    Empty result is semantically VALID here ("no overlap"), but per plural
    contract (Rule 5 cardinality convention) empty is normalized to
    operation_failed so callers receive a uniform signal across all 3
    operations. Rationale recorded in scope pass §Open questions #1.
    """
    a = await _create_circle_xy([0, 120, 0], 2, "DisjointA")
    b = await _create_circle_xy([100, 120, 0], 2, "DisjointB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "intersection",
        "curveIds": [a, b],
    })
    _assert_structured_error(envelope, "operation_failed")


async def test_curve_boolean_fully_erased_difference(fresh_document):
    """(s — bonus per reviewer) Difference inner - outer → operation_failed.

    When the minuend is entirely contained within the subtractor,
    Curve.CreateBooleanDifference returns an empty Curve[] (the minuend
    is fully erased). Per plural contract, empty → operation_failed.
    Pins the second canonical empty-result branch alongside
    disjoint-intersection (test `n` above).
    """
    inner = await _create_circle_xy([0, 130, 0], 3, "ErasedInner")
    outer = await _create_circle_xy([0, 130, 0], 10, "ErasedOuter")
    # element 0 = minuend (inner); element 1 = subtractor (outer).
    status, envelope = await _post_curve_boolean_raw({
        "operation": "difference",
        "curveIds": [inner, outer],
    })
    _assert_structured_error(envelope, "operation_failed")


# --- Managed-strict tests --------------------------------------------------


async def test_curve_boolean_non_curve_id(fresh_document):
    """(o) Non-curve id (point object) → invalid_input (managed strict)."""
    a = await _create_circle_xy([0, 140, 0], 5, "NonCurveA")
    pt = await _create_point_object([50, 140, 0], "NonCurveB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, pt],
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_curve_boolean_unknown_curveid(fresh_document):
    """(p) Unknown curveId (valid UUID, not in doc) → not_found (managed).

    Uses a randomly-generated non-zero UUID. The all-zeros Guid
    (00000000-...) is rejected at native-side ParseUuids as "Invalid
    UUID" before reaching managed FindId — this test needs a
    well-formed unknown GUID to exercise the managed `not_found` branch.
    """
    import uuid as _uuid

    a = await _create_circle_xy([0, 150, 0], 5, "KnownA")
    fake = str(_uuid.uuid4())
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, fake],
    })
    _assert_structured_error(envelope, "not_found")


async def test_curve_boolean_unknown_layer_strict(fresh_document):
    """(r) Unknown layer with strict → invalid_input (managed-strict path)."""
    a = await _create_circle_xy([0, 160, 0], 5, "StrictLayerA")
    b = await _create_circle_xy([3, 160, 0], 5, "StrictLayerB")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [a, b],
        "layer": "NonexistentLayerForCurveBoolTest",
    })
    _assert_structured_error(envelope, "invalid_input")


# --- Happy path with full attribute bundle --------------------------------


async def test_curve_boolean_full_attribute_bundle(fresh_document):
    """(q) Happy path with full attribute bundle → response echoes attrs
    on each inserted curve. Same attribute rhythm as brep plural
    creators (Loft / Sweep*)."""
    from rook.server import _mcp_tool_executor

    layer_res = await _mcp_tool_executor(
        "rhino_layer_create",
        {"name": "CurveBooleanTest"},
    )
    if _is_error(layer_res):
        err_text = str(layer_res.get("data", ""))
        assert "already exists" in err_text, f"Layer create failed: {layer_res!r}"

    outer = await _create_circle_xy([0, 170, 0], 10, "BundleOuter")
    inner = await _create_circle_xy([0, 170, 0], 3, "BundleInner")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "difference",
        "curveIds": [outer, inner],
        "name": "BundledCurveBool",
        "layer": "CurveBooleanTest",
        "color": "#40c0ff",
        "visible": True,
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    objs = _assert_plural_success(envelope, min_objects=1)
    for snap in objs:
        assert snap.get("name") == "BundledCurveBool", (
            f"name echo failed on one of the inserted curves: {snap!r}"
        )
        assert snap.get("layer") == "CurveBooleanTest", (
            f"layer echo failed: {snap!r}"
        )


# --- Permissiveness-smoke (per Common Plan amendment, 2026-04-20) ---------


async def test_curve_boolean_factory_permissive_smoke(fresh_document):
    """(t) Pathological input succeeds with valid ObjectSnapshot envelope.

    Pins the empirical finding that Curve.CreateBooleanUnion absorbs
    nested inputs cleanly: a small circle fully contained within a larger
    one returns `Length=1` (just the outer envelope). Per Common Plan
    amendment at rook_docs/2026-04-17-typed-route-phase1-plan.md:257.

    Companion to the operation_failed tests above — the contract does
    NOT promise failure on every non-obvious input; many pathological-
    looking cases (nested, tangent-touching, coincident) succeed.
    """
    outer = await _create_circle_xy([0, 180, 0], 10, "PermOuter")
    inner = await _create_circle_xy([0, 180, 0], 3, "PermInner")
    status, envelope = await _post_curve_boolean_raw({
        "operation": "union",
        "curveIds": [outer, inner],
        "name": "PermissiveUnion",
    })
    assert status == 200, (
        f"Permissive smoke test failed — factory used to absorb nested "
        f"union cleanly. If this now fails, update the Common Plan amendment "
        f"and revisit CurveBoolean contract. Envelope: {envelope!r}"
    )
    objs = _assert_plural_success(envelope, min_objects=1)
    # Nested union → factory discards inner, returns just the outer envelope.
    assert len(objs) == 1, (
        f"Nested union should yield exactly 1 curve (outer envelope), "
        f"got {len(objs)}: {envelope!r}"
    )


# --- Operation-injection pins through MCP tool executor -------------------
#
# Codex review: the raw /curve/boolean tests above never exercise the
# three `rhino_curve_boolean_*` MCP tools, so a copy/paste bug in the
# executor injection (e.g. `rhino_curve_boolean_difference -> "union"`)
# would pass every existing test. These three pins route through
# `_mcp_tool_executor` and use discriminating geometry (disjoint
# circles) where each operation has a distinct observable outcome:
#   - union of 2 disjoint closed curves → Length=2 (both kept)
#   - difference of 2 disjoint → Length=1 (minuend unchanged)
#   - intersection of 2 disjoint → empty → operation_failed
# A wrong injection for any tool would fail the specific assertion,
# not a generic success check.


async def test_mcp_tool_curve_boolean_union_injects_union(fresh_document):
    """Pin: rhino_curve_boolean_union MCP tool dispatches with
    operation='union'. Discriminating geometry: 2 disjoint circles →
    union returns 2 curves (both kept, not merged). If this tool were
    mapped to intersection, the call would return operation_failed; if
    mapped to difference, it would return 1 curve."""
    from rook.server import _mcp_tool_executor

    a = await _create_circle_xy([0, 200, 0], 3, "InjUnionA")
    b = await _create_circle_xy([20, 200, 0], 3, "InjUnionB")
    res = await _mcp_tool_executor(
        "rhino_curve_boolean_union",
        {"curveIds": [a, b]},
    )
    assert not _is_error(res), (
        f"rhino_curve_boolean_union on disjoint circles failed — if injection "
        f"is wrong the tool may have mapped to intersection (operation_failed) "
        f"or difference (1 curve). Result: {res!r}"
    )
    objs = res.get("objects")
    assert isinstance(objs, list) and len(objs) == 2, (
        f"Disjoint union must yield 2 curves (both kept). If this returns 1, "
        f"tool mapped to difference; if this raises operation_failed, tool "
        f"mapped to intersection. Result: {res!r}"
    )


async def test_mcp_tool_curve_boolean_difference_injects_difference(fresh_document):
    """Pin: rhino_curve_boolean_difference MCP tool dispatches with
    operation='difference'. Discriminating geometry: 2 disjoint circles
    → difference(A, B) leaves A unchanged (Length=1). Union would
    return 2; intersection would return operation_failed."""
    from rook.server import _mcp_tool_executor

    a = await _create_circle_xy([0, 210, 0], 3, "InjDiffA")
    b = await _create_circle_xy([20, 210, 0], 3, "InjDiffB")
    res = await _mcp_tool_executor(
        "rhino_curve_boolean_difference",
        {"curveIds": [a, b]},
    )
    assert not _is_error(res), (
        f"rhino_curve_boolean_difference on disjoint circles failed — if "
        f"injection is wrong the tool may have mapped to intersection "
        f"(operation_failed). Result: {res!r}"
    )
    objs = res.get("objects")
    assert isinstance(objs, list) and len(objs) == 1, (
        f"Disjoint difference(A,B) must yield 1 curve (A unchanged). If this "
        f"returns 2, tool mapped to union. Result: {res!r}"
    )


async def test_mcp_tool_curve_boolean_intersection_injects_intersection(fresh_document):
    """Pin: rhino_curve_boolean_intersection MCP tool dispatches with
    operation='intersection'. Discriminating geometry: 2 disjoint
    circles → intersection is empty → operation_failed. Union would
    return 2 curves; difference would return 1."""
    a = await _create_circle_xy([0, 220, 0], 3, "InjIntxA")
    b = await _create_circle_xy([20, 220, 0], 3, "InjIntxB")

    # Uses the raw executor (not _mcp_tool_executor) so we can assert
    # the structured error shape directly. _mcp_tool_executor wraps
    # failures but the envelope shape still comes through.
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_curve_boolean_intersection",
        {"curveIds": [a, b]},
    )
    assert _is_error(res), (
        f"rhino_curve_boolean_intersection on disjoint circles should return "
        f"operation_failed (empty intersection per plural contract). If this "
        f"returned success with 2 objects, tool mapped to union; if 1 object, "
        f"tool mapped to difference. Result: {res!r}"
    )
    # Deeper assertion: the error code is operation_failed (the signal
    # the factory returned empty), not a validation error code like
    # invalid_operation (which would mean the wrong string got injected
    # but was rejected downstream).
    data = res.get("data") if isinstance(res, dict) else None
    if isinstance(data, dict):
        assert data.get("errorCode") == "operation_failed", (
            f"Expected errorCode='operation_failed' for disjoint intersection, "
            f"got {data.get('errorCode')!r}. If it's 'invalid_operation', the "
            f"injected string was wrong. Full result: {res!r}"
        )
