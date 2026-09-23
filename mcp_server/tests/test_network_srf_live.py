"""Live-Rhino characterization tests for POST /surface/network (Phase 2 PR-3).

Pins the worked-example contract:
  - XOR input form: auto-detect (curveIds) vs explicit (uCurveIds + vCurveIds)
  - continuity distinctness on the EXPLICIT form (simultaneously pins
    overload 2 is reachable AND continuity is actually honored)
  - worker-thread rejections for all input-form edge branches (conflict,
    incomplete, both-empty, neither, min-count)
  - worker-thread rejections for out-of-range continuity + non-positive
    tolerances (factory silently coerces these into garbage output)
  - real Rhino-side failure: parallel/disjoint curves -> operation_failed
  - Brep wrap: singular-contract response with type='Brep'

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_network_srf_live.py

See rook_docs/2026-04-20-phase2-surface-curve-plan.md §/surface/network.
Overload + error-code + continuity-coalescing behavior pinned empirically
2026-04-20 before implementation.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _add_line(start: list[float], end: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _add_interp(points: list[list[float]]) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_execute",
        {"code": (
            "import rhinoscriptsyntax as rs\n"
            f"_id = rs.AddInterpCurve({points!r})\n"
            "print(str(_id))\n"
        )},
    )
    assert not _is_error(res), f"AddInterpCurve failed: {res!r}"
    return res["output"].strip().splitlines()[-1]


async def _post_network_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/network", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/network returned non-JSON body: {resp.text!r} ({ex!r})")
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
    assert snapshot["type"] == "Brep", (
        f"NetworkSrf result should wrap as Brep (for /surface/* parity), got: {snapshot!r}"
    )


async def _build_rect_network() -> tuple[list[str], list[str]]:
    """2 U-curves + 2 V-curves forming a rectangular network.
    Returns (u_ids, v_ids)."""
    u1 = await _add_line([0, 0, 0], [10, 0, 0], "Net_U1")
    u2 = await _add_line([0, 10, 2], [10, 10, 2], "Net_U2")
    v1 = await _add_line([0, 0, 0], [0, 10, 2], "Net_V1")
    v2 = await _add_line([10, 0, 0], [10, 10, 2], "Net_V2")
    return [u1, u2], [v1, v2]


async def _build_curved_network() -> tuple[list[str], list[str]]:
    """Curved-edge 2U+2V network (continuity is observable on this geometry).
    Returns (u_ids, v_ids)."""
    def _arc_like(a, b):
        mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2 + 2]
        return [a, mid, b]

    u1 = await _add_interp(_arc_like([0, 0, 0], [10, 0, 0]))
    u2 = await _add_interp(_arc_like([0, 10, 0], [10, 10, 0]))
    v1 = await _add_interp(_arc_like([0, 0, 0], [0, 10, 0]))
    v2 = await _add_interp(_arc_like([10, 0, 0], [10, 10, 0]))
    return [u1, u2], [v1, v2]


async def _area_via_mcp(brep_id: str) -> float:
    from rook.server import _mcp_tool_executor
    res = await _mcp_tool_executor("rhino_measure_area", {"id": brep_id})
    assert not _is_error(res), f"rhino_measure_area failed: {res!r}"
    area = res.get("area")
    assert isinstance(area, (int, float)) and area > 0, f"Bad area: {res!r}"
    return float(area)


# --- Happy-path tests ------------------------------------------------------


async def test_network_srf_auto_detect(fresh_document):
    """(a) auto-detect form with a 4-line rectangular network -> 1 brep."""
    from rook.server import _mcp_tool_executor
    u_ids, v_ids = await _build_rect_network()
    res = await _mcp_tool_executor(
        "rhino_create_network_srf",
        {"curveIds": u_ids + v_ids, "name": "NetAuto"},
    )
    assert not _is_error(res), f"Auto-detect NetworkSrf failed: {res!r}"
    _assert_object_snapshot(res)


async def test_network_srf_explicit(fresh_document):
    """(b) explicit uCurveIds + vCurveIds form -> 1 brep."""
    from rook.server import _mcp_tool_executor
    u_ids, v_ids = await _build_rect_network()
    res = await _mcp_tool_executor(
        "rhino_create_network_srf",
        {"uCurveIds": u_ids, "vCurveIds": v_ids, "name": "NetExplicit"},
    )
    assert not _is_error(res), f"Explicit NetworkSrf failed: {res!r}"
    _assert_object_snapshot(res)


async def test_network_srf_continuity_distinctness_on_explicit(fresh_document):
    """(c) continuity distinctness PIN on the EXPLICIT form.

    Simultaneously pins:
      - explicit overload 2 is reachable via the route's payload shape
      - continuity is actually honored on the explicit path (not silently
        coerced or ignored)

    Empirical 2026-04-20 probe showed cont=0 produces a measurably smaller
    surface than cont=1 on a curved-edge network (delta ~0.1). Asserting
    > 0.01 delta here.
    """
    from rook.server import _mcp_tool_executor

    u_ids_0, v_ids_0 = await _build_curved_network()
    res0 = await _mcp_tool_executor(
        "rhino_create_network_srf",
        {"uCurveIds": u_ids_0, "vCurveIds": v_ids_0, "continuity": 0, "name": "NetC0"},
    )
    assert not _is_error(res0), f"cont=0 NetworkSrf failed: {res0!r}"
    area0 = await _area_via_mcp(res0["id"])

    u_ids_1, v_ids_1 = await _build_curved_network()
    res1 = await _mcp_tool_executor(
        "rhino_create_network_srf",
        {"uCurveIds": u_ids_1, "vCurveIds": v_ids_1, "continuity": 1, "name": "NetC1"},
    )
    assert not _is_error(res1), f"cont=1 NetworkSrf failed: {res1!r}"
    area1 = await _area_via_mcp(res1["id"])

    assert abs(area1 - area0) > 0.01, (
        f"Continuity appears silently ignored on explicit path: "
        f"cont=0 area={area0}, cont=1 area={area1}"
    )


# --- Validation-error tests -----------------------------------------------


async def test_network_srf_continuity_out_of_range_high(fresh_document):
    """(d) continuity=3 -> invalid_continuity (worker-thread reject)."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": v_ids, "continuity": 3,
    })
    _assert_structured_error(envelope, "invalid_continuity")


async def test_network_srf_continuity_negative(fresh_document):
    """(e) continuity=-1 -> invalid_continuity."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": v_ids, "continuity": -1,
    })
    _assert_structured_error(envelope, "invalid_continuity")


async def test_network_srf_both_forms(fresh_document):
    """(f) both curveIds AND explicit form -> input_form_conflict."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "curveIds": u_ids + v_ids,
        "uCurveIds": u_ids,
        "vCurveIds": v_ids,
    })
    _assert_structured_error(envelope, "input_form_conflict")


async def test_network_srf_only_u(fresh_document):
    """(g) only uCurveIds -> input_form_incomplete."""
    u_ids, _ = await _build_rect_network()
    status, envelope = await _post_network_raw({"uCurveIds": u_ids})
    _assert_structured_error(envelope, "input_form_incomplete")


async def test_network_srf_only_v(fresh_document):
    """(h) only vCurveIds -> input_form_incomplete."""
    _, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({"vCurveIds": v_ids})
    _assert_structured_error(envelope, "input_form_incomplete")


async def test_network_srf_u_empty_v_valid(fresh_document):
    """(i) uCurveIds=[] with valid vCurveIds -> input_form_incomplete."""
    _, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": [], "vCurveIds": v_ids,
    })
    _assert_structured_error(envelope, "input_form_incomplete")


async def test_network_srf_u_valid_v_empty(fresh_document):
    """(j) valid uCurveIds with vCurveIds=[] -> input_form_incomplete."""
    u_ids, _ = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": [],
    })
    _assert_structured_error(envelope, "input_form_incomplete")


async def test_network_srf_both_empty(fresh_document):
    """(j+) both uCurveIds=[] AND vCurveIds=[] -> input_form_incomplete."""
    status, envelope = await _post_network_raw({"uCurveIds": [], "vCurveIds": []})
    _assert_structured_error(envelope, "input_form_incomplete")


async def test_network_srf_neither_form(fresh_document):
    """(k) no curveIds, no uCurveIds, no vCurveIds -> invalid_input."""
    status, envelope = await _post_network_raw({})
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_single_curve(fresh_document):
    """(l) curveIds with single element -> invalid_input (min 2)."""
    c1 = await _add_line([0, 0, 0], [10, 0, 0], "Solo")
    status, envelope = await _post_network_raw({"curveIds": [c1]})
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_empty_curveids(fresh_document):
    """(m) curveIds=[] -> invalid_input."""
    status, envelope = await _post_network_raw({"curveIds": []})
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_edge_tolerance_zero(fresh_document):
    """(n) edgeTolerance=0 -> invalid_input."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": v_ids, "edgeTolerance": 0.0,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_interior_tolerance_zero(fresh_document):
    """(o) interiorTolerance=0 -> invalid_input (load-bearing worker-thread reject)."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": v_ids, "interiorTolerance": 0.0,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_angle_tolerance_negative(fresh_document):
    """(p) angleTolerance=-1 -> invalid_input."""
    u_ids, v_ids = await _build_rect_network()
    status, envelope = await _post_network_raw({
        "uCurveIds": u_ids, "vCurveIds": v_ids, "angleTolerance": -1.0,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_parallel_no_crossing(fresh_document):
    """(q) 2 parallel lines, no crossing network -> operation_failed."""
    c1 = await _add_line([0, 0, 0], [10, 0, 0], "Par1")
    c2 = await _add_line([0, 10, 0], [10, 10, 0], "Par2")
    status, envelope = await _post_network_raw({"curveIds": [c1, c2]})
    _assert_structured_error(envelope, "operation_failed")
    assert "error code" in envelope["data"]["errorMessage"].lower(), (
        f"Expected raw error code in message: {envelope!r}"
    )


async def test_network_srf_non_curve_id(fresh_document):
    """(r) non-curve ID in input -> invalid_input via ResolveCurvesStrict."""
    from rook.server import _mcp_tool_executor

    u_ids, v_ids = await _build_rect_network()
    box_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "NotACurve"},
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    box_id = box_res["id"]

    # Swap one valid id for the box id
    status, envelope = await _post_network_raw({
        "uCurveIds": [u_ids[0], box_id], "vCurveIds": v_ids,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_network_srf_full_attribute_bundle(fresh_document):
    """(s) happy path with full attribute bundle -> ObjectSnapshot echoes attrs."""
    from rook.server import _mcp_tool_executor

    layer_res = await _mcp_tool_executor(
        "rhino_layer_create",
        {"name": "NetworkSrfTest"},
    )
    if _is_error(layer_res):
        err_text = str(layer_res.get("data", ""))
        assert "already exists" in err_text, f"Layer create failed: {layer_res!r}"

    u_ids, v_ids = await _build_rect_network()
    res = await _mcp_tool_executor(
        "rhino_create_network_srf",
        {
            "uCurveIds": u_ids,
            "vCurveIds": v_ids,
            "continuity": 1,
            "name": "BundledNet",
            "layer": "NetworkSrfTest",
            "color": "#20a0ff",
            "visible": True,
        },
    )
    assert not _is_error(res), f"Bundled NetworkSrf failed: {res!r}"
    _assert_object_snapshot(res)
    assert res.get("name") == "BundledNet"
    assert res.get("layer") == "NetworkSrfTest"
