"""Live-Rhino characterization tests for POST /annotation/leader (Phase 2 PR-6).

Pins the leader route contract:
  - 2-point happy path: text + arrow/text polyline
  - 3-point polyline leader (arrow + bend + text)
  - annotationType == "Leader" on POST response and /geometry (cross-surface)
  - plainText exact-equality on /geometry (tight, not substring — per PR-5
    "lax assertions mask load-bearing behavior" lesson)
  - Non-zero Z input is accepted (leader succeeds, annotationType still
    "Leader"). Exact Z behavior in the resulting geometry is SDK-governed
    and deliberately not pinned; scope-pass initially assumed the SDK
    flattens to Z=0 per the rhinoSdkDoc.h docstring, but empirical
    verification 2026-04-19 showed Z is preserved, so Rook's contract
    now says "SDK-governed, not part of Rook's published contract."
  - No measuredValue field in the response (leaders have no dimensioned
    numeric quantity)
  - Strict validation: missing text / empty text / missing points / <2
    points / wrong-shape points / non-numeric point entries all →
    invalid_input
  - Strict attrs inherited from PR-1 ApplyCommonAttributesStrict

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_leader_live.py
"""

from __future__ import annotations

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


async def _post_leader_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/leader", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/leader returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_leader(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_leader", body)
    assert not _is_error(res), f"rhino_annotation_leader failed: {res!r}"
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


# --- Happy paths -----------------------------------------------------------


async def test_two_point_leader_happy_path(fresh_document):
    await _purge_objects()
    result = await _tool_leader({
        "text": "Hello",
        "points": [[0, 0, 0], [5, 5, 0]],
    })

    assert result.get("annotationType") == "Leader", (
        f"Expected annotationType='Leader', got {result.get('annotationType')!r}"
    )
    assert result.get("type") == "Annotation"

    # No measuredValue on leader responses.
    assert "measuredValue" not in result, (
        f"Leader responses must not carry measuredValue: {result!r}"
    )

    # plainText echoes exact input text (tight assertion per PR-5 lesson —
    # substring matching could mask prefix/suffix drift).
    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert detail.get("plainText") == "Hello", (
        f"Expected plainText == 'Hello' exactly, got {detail.get('plainText')!r}"
    )


async def test_three_point_polyline_leader(fresh_document):
    # Arrow at [0,0,0] → bend at [3,0,0] → text at [6,3,0]. Pins that
    # intermediate polyline points are supported, not just 2-point leaders.
    await _purge_objects()
    result = await _tool_leader({
        "text": "Bent",
        "points": [[0, 0, 0], [3, 0, 0], [6, 3, 0]],
    })

    assert result.get("annotationType") == "Leader"
    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert detail.get("plainText") == "Bent"


# --- annotationType cross-surface invariant --------------------------------


async def test_annotationType_leader_cross_surface(fresh_document):
    await _purge_objects()
    result = await _tool_leader({
        "text": "X",
        "points": [[0, 0, 0], [5, 0, 0]],
    })

    geom = await _read_geometry(result["id"])
    detail = geom.get("geometry") or {}
    assert result.get("annotationType") == detail.get("annotationType"), (
        f"POST response and /geometry disagreed: "
        f"{result.get('annotationType')!r} vs {detail.get('annotationType')!r}"
    )
    assert detail.get("annotationType") == "Leader"


# --- Non-zero Z input ------------------------------------------------------


async def test_non_zero_z_input_accepted(fresh_document):
    # Initial scope pass claimed the SDK flattens non-zero Z to World_xy
    # per the rhinoSdkDoc.h:3190 docstring. Empirical verification
    # 2026-04-19 showed that claim is wrong: input Z passes through to
    # the resulting geometry. The handler doc + MCP description now
    # reflect that the Z behavior is SDK-governed and NOT part of Rook's
    # contract, so this test no longer pins a specific Z value — it only
    # pins that non-zero Z input succeeds and still produces a Leader.
    # Callers who need explicit 3D or non-axis-aligned planes should file
    # a feature request for a `plane` parameter.
    await _purge_objects()
    result = await _tool_leader({
        "text": "3D",
        "points": [[0, 0, 5], [10, 10, 3]],
    })

    assert result.get("annotationType") == "Leader", (
        f"Non-zero Z input still must produce a Leader: {result!r}"
    )
    # bbox must exist and be well-formed, but we deliberately do NOT
    # assert specific Z values here — doing so would re-introduce the
    # false-flattening assumption.
    bbox = result.get("bbox") or {}
    assert isinstance(bbox.get("min"), list) and len(bbox["min"]) == 3
    assert isinstance(bbox.get("max"), list) and len(bbox["max"]) == 3


# --- Validation failures ---------------------------------------------------


async def test_missing_text_rejected(fresh_document):
    status, envelope = await _post_leader_raw({
        "points": [[0, 0, 0], [5, 0, 0]],
    })
    assert status == 400, f"{envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "text" in envelope["data"]["errorMessage"].lower()


async def test_empty_text_rejected(fresh_document):
    status, envelope = await _post_leader_raw({
        "text": "",
        "points": [[0, 0, 0], [5, 0, 0]],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "text" in envelope["data"]["errorMessage"].lower()


async def test_missing_points_rejected(fresh_document):
    status, envelope = await _post_leader_raw({"text": "Hello"})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "points" in envelope["data"]["errorMessage"].lower()


async def test_single_point_rejected(fresh_document):
    # Need at least 2 points (arrow tip + text anchor); a single-point
    # request is semantically just a text-at-location, which is the
    # /annotation/text route's job.
    status, envelope = await _post_leader_raw({
        "text": "X",
        "points": [[0, 0, 0]],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    msg = envelope["data"]["errorMessage"].lower()
    assert "2" in msg or "two" in msg or "at least" in msg


async def test_overlong_point_entry_rejected(fresh_document):
    status, envelope = await _post_leader_raw({
        "text": "X",
        "points": [[0, 0, 0, 99], [5, 0, 0]],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_non_numeric_point_entry_rejected(fresh_document):
    status, envelope = await _post_leader_raw({
        "text": "X",
        "points": [[0, 0, 0], [5, "nope", 0]],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    status, envelope = await _post_leader_raw({
        "text": "X",
        "points": [[0, 0, 0], [5, 0, 0]],
        "layer": "NonExistentLayer__PR6_strict_check__",
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
