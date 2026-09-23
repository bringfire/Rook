"""Live-Rhino characterization tests for POST /curve/blend (Phase 2 PR-1).

Pins the worked-example contract for the first managed-bridge-reuse route
in CurvesHandler.cpp:
  - full ObjectSnapshot on success (singular-contract creator; **first
    strict-attribute creator returning a Curve, not a Brep**)
  - structured {errorCode, errorMessage} on failure
  - continuity enum validation (Position/Tangency/Curvature)
  - strict attribute handling on a curve object (serialization parity
    with brep creators under _strictAttributes — strict-curve proof point)
  - factory-permissive-smoke per Common Plan amendment (2026-04-20)

Uses Curve.CreateBlendCurve(curveA, curveB, continuity) — overload 1.
Reverse flags / bulge / asymmetric per-end continuity deferred per
plan-doc §Non-goals.

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_blend_curves_live.py

See rook_docs/2026-04-20-phase2-surface-curve-plan.md (§ /curve/blend
sub-plan) and rook_docs/2026-04-17-typed-route-phase1-plan.md:257
(amended permissiveness rule) for the binding contract these tests pin.
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
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _post_blend_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST to /curve/blend directly and return (status, envelope)."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/curve/blend", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/curve/blend returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured data dict: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )


def _assert_object_snapshot(snapshot: Any) -> None:
    assert isinstance(snapshot, dict), f"Expected ObjectSnapshot dict, got {snapshot!r}"
    for key in ("id", "type"):
        assert key in snapshot, f"ObjectSnapshot missing {key!r}: {snapshot!r}"


# --- Happy-path tests ------------------------------------------------------


async def test_blend_curves_default_tangency(fresh_document):
    """(a) 2 lines with gap → 1 curve, continuity='Tangency' default."""
    from rook.server import _mcp_tool_executor

    a = await _create_line([0, 0, 0], [10, 0, 0], "BlendA")
    b = await _create_line([15, 5, 0], [25, 5, 0], "BlendB")
    res = await _mcp_tool_executor(
        "rhino_blend_curves",
        {"curve1Id": a, "curve2Id": b, "name": "TangentBlend"},
    )
    assert not _is_error(res), f"Default tangency blend failed: {res!r}"
    _assert_object_snapshot(res)


async def test_blend_curves_each_continuity_enum(fresh_document):
    """(b) Each continuity enum produces a distinct curve — asserts
    geometrically, not just that each call succeeds.

    If the continuity parameter were silently ignored, all three calls
    would produce identical curves. This test pins the parameter by
    measuring each resulting curve's length and asserting the three
    lengths are not all equal. Empirical values from the 2026-04-20 spike
    on a similar gap geometry: Position ≈ 10.0, Tangency ≈ 18.3,
    Curvature ≈ 19.2 — clearly distinguishable.
    """
    from rook.server import _mcp_tool_executor

    lengths: dict[str, float] = {}
    for cont in ("Position", "Tangency", "Curvature"):
        a = await _create_line([0, 0, 0], [10, 0, 0], f"EnumA_{cont}")
        b = await _create_line([15, 5, 0], [25, 5, 0], f"EnumB_{cont}")
        res = await _mcp_tool_executor(
            "rhino_blend_curves",
            {"curve1Id": a, "curve2Id": b, "continuity": cont, "name": f"Blend_{cont}"},
        )
        assert not _is_error(res), f"{cont} blend failed: {res!r}"
        _assert_object_snapshot(res)

        length_res = await _mcp_tool_executor(
            "rhino_measure_length",
            {"id": res["id"]},
        )
        assert not _is_error(length_res), (
            f"rhino_measure_length failed for {cont} blend: {length_res!r}"
        )
        length = length_res.get("length")
        assert isinstance(length, (int, float)) and length > 0, (
            f"Expected positive length for {cont} blend: {length_res!r}"
        )
        lengths[cont] = float(length)

    # Pin the continuity parameter: if it were silently ignored, all three
    # lengths would be identical. Soft assertion — "at least two of three
    # differ" — rather than "all three differ", to tolerate any future
    # factory change that happens to coalesce two of the three for an
    # arbitrary geometry.
    distinct_values = set(round(v, 3) for v in lengths.values())
    assert len(distinct_values) >= 2, (
        f"Continuity parameter appears ignored — all three blend lengths equal: "
        f"{lengths!r}"
    )


# --- Validation-error tests ------------------------------------------------


async def test_blend_curves_invalid_continuity(fresh_document):
    """(c) Invalid continuity string → invalid_continuity."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "InvalidContA")
    b = await _create_line([15, 5, 0], [25, 5, 0], "InvalidContB")
    status, envelope = await _post_blend_raw({
        "curve1Id": a,
        "curve2Id": b,
        "continuity": "Bogus",
    })
    _assert_structured_error(envelope, "invalid_continuity")


async def test_blend_curves_missing_curve1id(fresh_document):
    """(d) Missing curve1Id → invalid_input."""
    b = await _create_line([15, 5, 0], [25, 5, 0], "MissingB")
    status, envelope = await _post_blend_raw({"curve2Id": b})
    _assert_structured_error(envelope, "invalid_input")


async def test_blend_curves_non_curve_id(fresh_document):
    """(e) Non-curve ID → invalid_input (managed doc-dependent path)."""
    from rook.server import _mcp_tool_executor

    box_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "NotACurveB"},
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    box_id = box_res["id"]

    a = await _create_line([0, 0, 0], [10, 0, 0], "GoodCurveA")
    status, envelope = await _post_blend_raw({
        "curve1Id": a,
        "curve2Id": box_id,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_blend_curves_unknown_layer_strict(fresh_document):
    """(f) Unknown layer with strict → invalid_input (strict-curve proof point)."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "StrictLayerA")
    b = await _create_line([15, 5, 0], [25, 5, 0], "StrictLayerB")
    status, envelope = await _post_blend_raw({
        "curve1Id": a,
        "curve2Id": b,
        "layer": "NonexistentLayerForBlendTest",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_blend_curves_malformed_color(fresh_document):
    """(g) Malformed color → invalid_input (worker-thread rejection)."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "ColorA")
    b = await _create_line([15, 5, 0], [25, 5, 0], "ColorB")
    status, envelope = await _post_blend_raw({
        "curve1Id": a,
        "curve2Id": b,
        "color": "not-a-color",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_blend_curves_full_attribute_bundle(fresh_document):
    """(h) Happy path with full attribute bundle → response echoes attrs.

    Strict-curve proof point: this is the first strict-attribute creator
    whose factory returns a Curve (not a Brep). Must verify that the
    attribute bundle (name/layer/color/visible) is applied to the curve
    object identically to brep creators, and that RhinoSerializer returns
    the standard ObjectSnapshot shape for a curve.
    """
    from rook.server import _mcp_tool_executor

    # Tolerate "already exists" — test-session carry-over is not this
    # test's concern.
    layer_res = await _mcp_tool_executor(
        "rhino_layer_create",
        {"name": "BlendCurvesTest"},
    )
    if _is_error(layer_res):
        err_text = str(layer_res.get("data", ""))
        assert "already exists" in err_text, f"Layer create failed: {layer_res!r}"

    a = await _create_line([0, 0, 0], [10, 0, 0], "BundleBlendA")
    b = await _create_line([15, 5, 0], [25, 5, 0], "BundleBlendB")
    res = await _mcp_tool_executor(
        "rhino_blend_curves",
        {
            "curve1Id": a,
            "curve2Id": b,
            "continuity": "Curvature",
            "name": "BundledBlend",
            "layer": "BlendCurvesTest",
            "color": "#40c0ff",
            "visible": True,
        },
    )
    assert not _is_error(res), f"Bundled blend failed: {res!r}"
    _assert_object_snapshot(res)
    assert res.get("name") == "BundledBlend", f"name echo failed: {res!r}"
    assert res.get("layer") == "BlendCurvesTest", f"layer echo failed: {res!r}"
    # Strict-curve proof point: the returned ObjectSnapshot.type is a
    # curve-class string (not "Brep"). The serializer returns the
    # RhinoObject's ObjectType, which for curves is "Curve".
    assert "Curve" in str(res.get("type", "")), (
        f"Strict-curve proof point: type should be a curve class, got {res!r}"
    )


# --- Permissiveness-smoke (per Common Plan amendment, 2026-04-20) ---------


async def test_blend_curves_factory_permissive_smoke(fresh_document):
    """(i) Pathological input succeeds with valid ObjectSnapshot.

    Pins the empirical finding that Curve.CreateBlendCurve (overload 1)
    is extremely permissive — coincident curves, zero-length inputs, and
    degenerate NURBS all produce valid blend curves. Per Common Plan
    amendment at rook_docs/2026-04-17-typed-route-phase1-plan.md:257.

    Companion test to the happy-path cases above — the contract does NOT
    promise failure on coincident/degenerate input; the contract DOES
    promise a valid ObjectSnapshot when the factory succeeds.
    """
    from rook.server import _mcp_tool_executor

    # Two coincident lines — both (0,0,0)→(10,0,0).
    a = await _create_line([0, 0, 0], [10, 0, 0], "PermBlendA")
    b = await _create_line([0, 0, 0], [10, 0, 0], "PermBlendB")
    res = await _mcp_tool_executor(
        "rhino_blend_curves",
        {"curve1Id": a, "curve2Id": b, "continuity": "Position", "name": "PermissiveBlend"},
    )
    assert not _is_error(res), (
        f"Permissive smoke test failed — factory used to accept coincident "
        f"curves. If this now fails, update the Common Plan amendment and "
        f"revisit BlendCurves contract. Result: {res!r}"
    )
    _assert_object_snapshot(res)
