"""Live-Rhino characterization tests for POST /surface/pipe (Phase 1 PR-1).

Pins the worked-example contract for the managed-bridge (reuse) substrate:
  - full ObjectSnapshot on success
  - structured {errorCode, errorMessage} on failure (native-side normalization
    of managed string errors)
  - XOR validation for radius vs startRadius/endRadius
  - passthrough of attribute bundle (name, layer, color)

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_pipe_live.py

Rhino must be running with RookNative + Rook companion loaded. Tests
reset the document on entry via the fresh_document fixture — run in a
throwaway session.

See rook_docs/2026-04-17-typed-route-phase1-plan.md (§ Worked Example)
for the binding contract these tests pin.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_line(start: list[float], end: list[float], name: str) -> str:
    """Create a line curve. Returns object id."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _create_circle(center: list[float], radius: float, name: str) -> str:
    """Create a circle curve. Returns object id."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CIRCLE", "center": center, "radius": radius, "name": name},
    )
    assert not _is_error(res), f"rhino_create CIRCLE failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _post_pipe_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """POST to /surface/pipe directly (bypassing MCP formatting) and return
    (http_status, parsed_envelope).

    Direct HTTP is used for tests that need to assert on the structured
    {errorCode, errorMessage} envelope that the MCP layer stringifies into
    text form.
    """
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/surface/pipe", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/pipe returned non-JSON body: {resp.text!r} ({ex!r})")
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
    """Minimal ObjectSnapshot shape assertions. Full schema lives in the
    RhinoSerializer; here we only pin the fields this contract guarantees.
    """
    assert isinstance(snapshot, dict), f"Expected ObjectSnapshot dict, got {snapshot!r}"
    for key in ("id", "type"):
        assert key in snapshot, f"ObjectSnapshot missing {key!r}: {snapshot!r}"


# --- Happy-path tests ------------------------------------------------------


async def test_pipe_uniform_radius(fresh_document):
    """(a) Uniform radius → one brep, full ObjectSnapshot."""
    from rook.server import _mcp_tool_executor

    rail = await _create_line([0, 0, 0], [10, 0, 0], "PipeRail_Uniform")
    res = await _mcp_tool_executor(
        "rhino_create_pipe",
        {"curveId": rail, "radius": 1.0, "cap": True, "name": "UniformPipe"},
    )
    assert not _is_error(res), f"Uniform pipe failed: {res!r}"
    _assert_object_snapshot(res)


async def test_pipe_variable_radius(fresh_document):
    """(b) Variable radius (start=2.0 → end=0.5) → one brep."""
    from rook.server import _mcp_tool_executor

    rail = await _create_line([0, 0, 0], [10, 0, 0], "PipeRail_Variable")
    res = await _mcp_tool_executor(
        "rhino_create_pipe",
        {
            "curveId": rail,
            "startRadius": 2.0,
            "endRadius": 0.5,
            "cap": True,
            "name": "VariablePipe",
        },
    )
    assert not _is_error(res), f"Variable pipe failed: {res!r}"
    _assert_object_snapshot(res)


async def test_pipe_uncapped_vs_capped(fresh_document):
    """(c) Capped=false succeeds; capped=true also succeeds. Both are valid."""
    from rook.server import _mcp_tool_executor

    rail1 = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_Uncapped")
    uncapped = await _mcp_tool_executor(
        "rhino_create_pipe",
        {"curveId": rail1, "radius": 0.5, "cap": False, "name": "Uncapped"},
    )
    assert not _is_error(uncapped), f"Uncapped pipe failed: {uncapped!r}"
    _assert_object_snapshot(uncapped)

    rail2 = await _create_line([0, 2, 0], [5, 2, 0], "PipeRail_Capped")
    capped = await _mcp_tool_executor(
        "rhino_create_pipe",
        {"curveId": rail2, "radius": 0.5, "cap": True, "name": "Capped"},
    )
    assert not _is_error(capped), f"Capped pipe failed: {capped!r}"
    _assert_object_snapshot(capped)


# --- Validation-error tests (structured {errorCode, errorMessage}) ---------


async def test_pipe_missing_curveid(fresh_document):
    """(d) Missing curveId → invalid_input."""
    status, envelope = await _post_pipe_raw({"radius": 1.0})
    _assert_structured_error(envelope, "invalid_input")
    assert "curveId" in envelope["data"]["errorMessage"]


async def test_pipe_negative_radius(fresh_document):
    """(e) Negative radius → invalid_input."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_Neg")
    status, envelope = await _post_pipe_raw({"curveId": rail, "radius": -1.0})
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_xor_violation_both_forms(fresh_document):
    """(f) Both 'radius' and 'startRadius' set → invalid_input (XOR)."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_XOR")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 1.0,
        "startRadius": 1.0,
        "endRadius": 0.5,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_xor_violation_partial_variable(fresh_document):
    """(f-bis) startRadius without endRadius → invalid_input."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_Partial")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "startRadius": 1.0,
    })
    _assert_structured_error(envelope, "invalid_input")


# --- Failure-mode tests (managed-side errors normalized to operation_failed) -


async def test_pipe_non_curve_curveid(fresh_document):
    """(g) curveId points to a non-curve object → invalid_input.

    Managed CreatePipe differentiates not-found vs wrong-type and surfaces
    structured {errorCode:"invalid_input", errorMessage:...} through the
    native EmitNormalized pass-through for already-structured managed
    errors. Pinned per Phase 1 plan (§ Worked Example test (g)).
    """
    from rook.server import _mcp_tool_executor

    # Create a box (brep, not curve)
    box_res = await _mcp_tool_executor(
        "rhino_create",
        {
            "type": "BOX",
            "corner1": [0, 0, 0],
            "corner2": [1, 1, 1],
            "name": "NotACurve",
        },
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    box_id = box_res["id"]

    status, envelope = await _post_pipe_raw({"curveId": box_id, "radius": 0.5})
    _assert_structured_error(envelope, "invalid_input")
    assert "not a curve" in envelope["data"]["errorMessage"].lower(), (
        f"Expected 'not a curve' message: {envelope!r}"
    )


async def test_pipe_invalid_uuid_format(fresh_document):
    """Malformed UUID string in curveId → invalid_input.

    Native ParseUuid rejects the malformed string on the worker thread
    before the managed bridge is invoked.
    """
    status, envelope = await _post_pipe_raw({
        "curveId": "not-a-uuid",
        "radius": 1.0,
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_unknown_curveid(fresh_document):
    """curveId is valid UUID but does not exist in document → not_found.

    Managed CreatePipe rejects not-found ids with structured errors, distinct
    from invalid_input (bad UUID format) and wrong-type ("not a curve"), per
    the error-taxonomy base set (invalid_input / not_found / operation_failed).
    """
    # Use a syntactically valid UUID that cannot exist in a fresh doc.
    status, envelope = await _post_pipe_raw({
        "curveId": "00000000-0000-0000-0000-000000000001",
        "radius": 1.0,
    })
    _assert_structured_error(envelope, "not_found")
    assert "not found" in envelope["data"]["errorMessage"].lower(), (
        f"Expected 'not found' message: {envelope!r}"
    )


async def test_pipe_unknown_layer(fresh_document):
    """Attribute bundle: non-existent layer → invalid_input.

    Pins the Phase 1 Common Plan baseline: bad attribute values surface as
    invalid_input instead of silent-ignore.
    """
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_BadLayer")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 1.0,
        "layer": "NonexistentLayerDoesNotExist",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_unparseable_color(fresh_document):
    """Attribute bundle: malformed color → invalid_input.

    Native ParseColor rejects bad format on the worker thread before the
    managed bridge is invoked.
    """
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_BadColor")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 1.0,
        "color": "not-a-color",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_non_boolean_visible(fresh_document):
    """Attribute bundle: non-boolean visible → invalid_input (native reject)."""
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_BadVisible")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 1.0,
        "visible": "yes",  # string, not boolean
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_pipe_visible_false_applied(fresh_document):
    """Attribute bundle: visible=false is honored end-to-end.

    Verifies the managed CreateHandler reads 'visible' and applies it to
    the object's attributes — pins the Phase 1 contract that the full
    attribute bundle (name/layer/color/visible) is supported. The
    authoritative signal is the returned ObjectSnapshot's `visible` field.
    """
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_Invisible")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 0.5,
        "visible": False,
        "name": "InvisiblePipe",
    })
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    snapshot = envelope.get("data")
    _assert_object_snapshot(snapshot)
    assert snapshot.get("visible") is False, (
        f"Expected ObjectSnapshot.visible=False for visible=false pipe; got {snapshot!r}"
    )


async def test_pipe_visible_default_true(fresh_document):
    """Attribute bundle: omitted 'visible' defaults to true (baseline sanity).

    Pairs with test_pipe_visible_false_applied so the visible=False case
    can't accidentally pass because everything defaults to False.
    """
    rail = await _create_line([0, 0, 0], [5, 0, 0], "PipeRail_VisibleDefault")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 0.5,
        "name": "VisibleDefaultPipe",
    })
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    snapshot = envelope.get("data")
    _assert_object_snapshot(snapshot)
    assert snapshot.get("visible") is True, (
        f"Expected ObjectSnapshot.visible=True by default; got {snapshot!r}"
    )


async def test_pipe_success_envelope_has_data_and_id(fresh_document):
    """Direct-HTTP success path: envelope is {success:true, data:ObjectSnapshot}.

    Pins that the native normalization path does not mangle the managed
    success payload — only the error path is rewritten.
    """
    rail = await _create_line([0, 0, 0], [10, 0, 0], "PipeRail_Envelope")
    status, envelope = await _post_pipe_raw({
        "curveId": rail,
        "radius": 1.0,
    })
    assert status == 200, f"Expected HTTP 200, got {status}: {envelope!r}"
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    _assert_object_snapshot(data)
