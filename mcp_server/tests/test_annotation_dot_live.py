"""Live-Rhino characterization tests for POST /annotation/dot (Phase 2 PR-7).

Pins the text-dot contract:
  - Happy path — type == "TextDot" exactly, echoed text matches input,
    default heightInPoints == 14, default fontFace pinned to observed
    value (Arial / Arial Bold — SDK documentation is ambiguous but the
    runtime gives one exact answer)
  - Custom heightInPoints (JSON integer) echoed exactly
  - Custom fontFace echoed exactly
  - secondaryText round-trips via response echo
  - No annotationType field in response (dots are ON_Geometry, not
    ON_Annotation)
  - No measuredValue field in response
  - Verification is ROUTE-RESPONSE-ONLY for this PR — GeometryHandler
    has no ON_TextDot branch, so GET /geometry does not surface
    dot-specific fields (text / font / height). Richer /geometry
    support is deferred follow-up hygiene.
  - Strict validation: missing text / empty text / missing location /
    overlong location / heightInPoints < 3 / heightInPoints as JSON
    float (including 24.0) all → invalid_input

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_dot_live.py
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


async def _post_dot_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/dot", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/dot returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_dot(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_dot", body)
    assert not _is_error(res), f"rhino_annotation_dot failed: {res!r}"
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


async def test_basic_dot_happy_path(fresh_document):
    await _purge_objects()
    result = await _tool_dot({
        "text": "Hello",
        "location": [5, 5, 0],
    })

    # type field pinned to "TextDot" per DocumentHelpers.h:127's ON::text_dot branch.
    assert result.get("type") == "TextDot", (
        f"Expected type='TextDot' per DocumentHelpers mapping, got {result.get('type')!r}"
    )

    # text field echoes the live dot's PrimaryText exactly.
    assert result.get("text") == "Hello", (
        f"Expected text='Hello' exactly, got {result.get('text')!r}"
    )

    # Default heightInPoints per ON_TextDot::DefaultHeightInPoints (14).
    assert result.get("heightInPoints") == 14, (
        f"Expected default heightInPoints=14, got {result.get('heightInPoints')!r}"
    )

    # Default fontFace pinned to exact value observed on Rhino 8 /
    # RookNative 2026-04-19. SDK header is ambiguous (DefaultFontFace =
    # "Arial" but the FontFace() getter remark says "Arial Bold"); the
    # runtime returns "Arial". Pinning the exact string instead of a
    # disjunction — PR-5 lesson carried forward (lax `A OR B` matchers
    # mask the real behavior).
    assert result.get("fontFace") == "Arial", (
        f"Expected default fontFace == 'Arial' exactly, got "
        f"{result.get('fontFace')!r}. If the runtime changed to "
        f"'Arial Bold' (matching the SDK getter remark), update the MCP "
        f"tool description and this test together."
    )

    # Dots are ON_Geometry not ON_Annotation — no annotationType field.
    assert "annotationType" not in result, (
        f"Dot response must NOT carry annotationType: {result!r}"
    )
    # Dots are not dimensions — no measuredValue.
    assert "measuredValue" not in result, (
        f"Dot response must NOT carry measuredValue: {result!r}"
    )

    # Empty secondaryText by default.
    assert result.get("secondaryText") == "", (
        f"Expected empty secondaryText by default, got {result.get('secondaryText')!r}"
    )


async def test_custom_height_in_points_echoed_exactly(fresh_document):
    await _purge_objects()
    result = await _tool_dot({
        "text": "H24",
        "location": [0, 0, 0],
        "heightInPoints": 24,
    })
    assert result.get("heightInPoints") == 24, (
        f"Expected heightInPoints=24 exactly, got {result.get('heightInPoints')!r}"
    )


async def test_custom_font_face_echoed_exactly(fresh_document):
    await _purge_objects()
    result = await _tool_dot({
        "text": "FontTest",
        "location": [0, 0, 0],
        "fontFace": "Courier New",
    })
    assert result.get("fontFace") == "Courier New", (
        f"Expected fontFace='Courier New' exactly, got {result.get('fontFace')!r}"
    )


async def test_secondary_text_round_trips(fresh_document):
    await _purge_objects()
    result = await _tool_dot({
        "text": "Primary",
        "location": [0, 0, 0],
        "secondaryText": "Detail string",
    })
    assert result.get("secondaryText") == "Detail string", (
        f"Expected secondaryText='Detail string' exactly, got {result.get('secondaryText')!r}"
    )


# --- Validation failures ---------------------------------------------------


async def test_missing_text_rejected(fresh_document):
    status, envelope = await _post_dot_raw({"location": [0, 0, 0]})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "text" in envelope["data"]["errorMessage"].lower()


async def test_empty_text_rejected(fresh_document):
    status, envelope = await _post_dot_raw({"text": "", "location": [0, 0, 0]})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_missing_location_rejected(fresh_document):
    status, envelope = await _post_dot_raw({"text": "X"})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "location" in envelope["data"]["errorMessage"].lower()


async def test_overlong_location_rejected(fresh_document):
    status, envelope = await _post_dot_raw({
        "text": "X",
        "location": [0, 0, 0, 99],
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_height_below_minimum_rejected(fresh_document):
    status, envelope = await _post_dot_raw({
        "text": "X",
        "location": [0, 0, 0],
        "heightInPoints": 2,
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "height" in envelope["data"]["errorMessage"].lower()


async def test_height_json_float_rejected(fresh_document):
    # `is_number_integer()` posture — 24.0 is rejected because the JSON
    # came in as a float literal, even though it's mathematically integer.
    # Matches ArrayHandler.cpp:224's integer-posture convention.
    status, envelope = await _post_dot_raw({
        "text": "X",
        "location": [0, 0, 0],
        "heightInPoints": 24.0,
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "integer" in envelope["data"]["errorMessage"].lower()


async def test_height_fractional_rejected(fresh_document):
    status, envelope = await _post_dot_raw({
        "text": "X",
        "location": [0, 0, 0],
        "heightInPoints": 3.5,
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    status, envelope = await _post_dot_raw({
        "text": "X",
        "location": [0, 0, 0],
        "layer": "NonExistentLayer__PR7_strict_check__",
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
