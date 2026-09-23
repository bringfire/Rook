"""Live-Rhino characterization tests for POST /surface/edge (Phase 2 PR-1).

Pins the worked-example contract for the Phase 2 surface/curve extension:
  - full ObjectSnapshot on success (singular-contract creator)
  - structured {errorCode, errorMessage} on failure
  - count validation (2..4 curves, worker-thread rejection)
  - strict attribute handling (managed-side strict mode)
  - factory-permissive-smoke per Common Plan amendment (2026-04-20)

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_edge_srf_live.py

Rhino must be running with RookNative + Rook companion loaded. Tests reset
the document on entry via the fresh_document fixture — run in a throwaway
session.

See rook_docs/2026-04-20-phase2-surface-curve-plan.md (§ Worked Example)
and rook_docs/2026-04-17-typed-route-phase1-plan.md:257 (amended
permissiveness rule) for the binding contract these tests pin.
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


async def _post_edge_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST to /surface/edge directly and return (status, envelope)."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/surface/edge", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/edge returned non-JSON body: {resp.text!r} ({ex!r})")
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


def _assert_object_snapshot(snapshot: Any) -> None:
    assert isinstance(snapshot, dict), f"Expected ObjectSnapshot dict, got {snapshot!r}"
    for key in ("id", "type"):
        assert key in snapshot, f"ObjectSnapshot missing {key!r}: {snapshot!r}"


# --- Happy-path tests ------------------------------------------------------


async def test_edge_srf_triangle(fresh_document):
    """(a) 3 lines forming a triangle → 1 brep (happy path, spike geometry)."""
    from rook.server import _mcp_tool_executor

    a = await _create_line([0, 0, 0], [10, 0, 0], "TriA")
    b = await _create_line([10, 0, 0], [5, 10, 0], "TriB")
    c = await _create_line([5, 10, 0], [0, 0, 0], "TriC")
    res = await _mcp_tool_executor(
        "rhino_create_edge_srf",
        {"curveIds": [a, b, c], "name": "Triangle"},
    )
    assert not _is_error(res), f"Triangle EdgeSrf failed: {res!r}"
    _assert_object_snapshot(res)


async def test_edge_srf_quad_max_count(fresh_document):
    """(c) 4 lines forming a quad → 1 brep (max count boundary)."""
    from rook.server import _mcp_tool_executor

    a = await _create_line([0, 0, 0], [10, 0, 0], "QuadA")
    b = await _create_line([10, 0, 0], [10, 10, 0], "QuadB")
    c = await _create_line([10, 10, 0], [0, 10, 0], "QuadC")
    d = await _create_line([0, 10, 0], [0, 0, 0], "QuadD")
    res = await _mcp_tool_executor(
        "rhino_create_edge_srf",
        {"curveIds": [a, b, c, d], "name": "Quad"},
    )
    assert not _is_error(res), f"Quad EdgeSrf failed: {res!r}"
    _assert_object_snapshot(res)


# --- Validation-error tests (structured {errorCode, errorMessage}) ---------


async def test_edge_srf_one_curve_rejected(fresh_document):
    """(d) 1 curve → invalid_curve_count (worker-thread rejection)."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "Single")
    status, envelope = await _post_edge_raw({"curveIds": [a]})
    _assert_structured_error(envelope, "invalid_curve_count")


async def test_edge_srf_five_curves_rejected(fresh_document):
    """(e) 5 curves → invalid_curve_count.

    API spec documents 2..4; `_-EdgeSrf` command UI empirically accepts 5+
    (2026-04-20 probe), but the typed route enforces the API bound
    explicitly.
    """
    ids = []
    for i in range(5):
        ids.append(await _create_line([i, 0, 0], [i, 10, 0], f"L{i}"))
    status, envelope = await _post_edge_raw({"curveIds": ids})
    _assert_structured_error(envelope, "invalid_curve_count")


async def test_edge_srf_missing_curveids(fresh_document):
    """Missing curveIds → invalid_input."""
    status, envelope = await _post_edge_raw({})
    _assert_structured_error(envelope, "invalid_input")


async def test_edge_srf_malformed_uuid(fresh_document):
    """(f) Malformed UUID in curveIds → invalid_input (worker-thread rejection)."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "GoodA")
    status, envelope = await _post_edge_raw({"curveIds": [a, "not-a-uuid"]})
    _assert_structured_error(envelope, "invalid_input")


async def test_edge_srf_non_curve_id(fresh_document):
    """(g) Non-curve object ID in curveIds → invalid_input (managed doc-dependent)."""
    from rook.server import _mcp_tool_executor

    # Create a box (brep, not curve)
    box_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "NotACurve"},
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    box_id = box_res["id"]

    a = await _create_line([0, 0, 0], [10, 0, 0], "GoodA")
    b = await _create_line([0, 10, 0], [10, 10, 0], "GoodB")
    status, envelope = await _post_edge_raw({"curveIds": [a, b, box_id]})
    _assert_structured_error(envelope, "invalid_input")


async def test_edge_srf_unknown_layer(fresh_document):
    """(h) Unknown layer with strict mode → invalid_input."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "LayerTestA")
    b = await _create_line([0, 10, 0], [10, 10, 0], "LayerTestB")
    status, envelope = await _post_edge_raw({
        "curveIds": [a, b],
        "layer": "NonexistentLayerDoesNotExist",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_edge_srf_malformed_color(fresh_document):
    """(i) Malformed color → invalid_input (worker-thread rejection)."""
    a = await _create_line([0, 0, 0], [10, 0, 0], "ColorTestA")
    b = await _create_line([0, 10, 0], [10, 10, 0], "ColorTestB")
    status, envelope = await _post_edge_raw({
        "curveIds": [a, b],
        "color": "not-a-color",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_edge_srf_full_attribute_bundle(fresh_document):
    """(j) Happy path with full attribute bundle → response echoes attrs."""
    from rook.server import _mcp_tool_executor

    # Ensure a custom layer exists for the strict-layer path. Tolerate
    # "already exists" — test-session carry-over is not this test's concern.
    layer_res = await _mcp_tool_executor(
        "rhino_layer_create",
        {"name": "EdgeSrfTest"},
    )
    if _is_error(layer_res):
        err_text = str(layer_res.get("data", ""))
        assert "already exists" in err_text, f"Layer create failed: {layer_res!r}"

    a = await _create_line([0, 0, 0], [10, 0, 0], "BundleA")
    b = await _create_line([0, 10, 0], [10, 10, 0], "BundleB")
    res = await _mcp_tool_executor(
        "rhino_create_edge_srf",
        {
            "curveIds": [a, b],
            "name": "BundledEdge",
            "layer": "EdgeSrfTest",
            "color": "#ff8000",
            "visible": True,
        },
    )
    assert not _is_error(res), f"Bundled EdgeSrf failed: {res!r}"
    _assert_object_snapshot(res)
    assert res.get("name") == "BundledEdge", f"name echo failed: {res!r}"
    assert res.get("layer") == "EdgeSrfTest", f"layer echo failed: {res!r}"


# --- Permissiveness-smoke (per Common Plan amendment, 2026-04-20) ---------


async def test_edge_srf_factory_permissive_smoke(fresh_document):
    """(k) Pathological input succeeds with valid ObjectSnapshot.

    Pins the empirical finding that Brep.CreateEdgeSurface is extremely
    permissive — disjoint far-apart line segments and zero-length curves
    still produce valid breps. Rather than contrive a pathological input
    that may fail cleanly in future Rhino versions, this test pins the
    permissive behavior itself per the Common Plan amendment landed at
    rook_docs/2026-04-17-typed-route-phase1-plan.md:257 (2026-04-20).

    Companion test to the happy-path cases above — the contract does NOT
    promise failure on disconnected/degenerate input; the contract DOES
    promise a valid ObjectSnapshot when the factory succeeds (which it
    empirically does for these inputs).
    """
    from rook.server import _mcp_tool_executor

    # Two parallel lines with a gap — empirically produces 1 brep per
    # 2026-04-20 spike.
    a = await _create_line([0, 0, 0], [10, 0, 0], "PermA")
    b = await _create_line([0, 5, 0], [10, 5, 0], "PermB")
    res = await _mcp_tool_executor(
        "rhino_create_edge_srf",
        {"curveIds": [a, b], "name": "PermissiveSmoke"},
    )
    assert not _is_error(res), (
        f"Permissive smoke test failed — factory used to accept parallel "
        f"lines with gap. If this now fails, update the Common Plan "
        f"amendment and revisit EdgeSrf contract. Result: {res!r}"
    )
    _assert_object_snapshot(res)
