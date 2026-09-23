"""Live-Rhino characterization tests for POST /annotation/text (Phase 2 PR-1).

Pins the direct-sdk native annotation substrate worked example:
  - Happy path: basic string returns full snapshot + echoed effective typography
  - Override persistence: bold + italic + custom font read back cleanly via
    `rhino_geometry` (which surfaces annotation-level overrides through
    `GetEffectiveDimensionStyle` at GeometryHandler.cpp:56-62)
  - Multi-line text persists verbatim
  - Strict-attrs: height=0 / empty text / unknown layer → structured invalid_input
  - Font fallback: non-existent font → success + effective-font echo reflects
    the document default, not the requested font

Run:
    pytest -m requires_rhino mcp_server/tests/test_annotation_text_live.py

Rhino must be running with RookNative loaded. Tests reset the document on
entry via `_purge_objects()` because `fresh_document` via
`rhino_document_ops(action=new)` does not reliably wipe the object table
(PR-0 observation 2026-04-19).
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


async def _post_text_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/annotation/text", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/annotation/text returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_annotation_text(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_annotation_text", body)
    assert not _is_error(res), f"rhino_annotation_text failed: {res!r}"
    return res


async def _read_geometry(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_geometry", {"id": obj_id})
    assert not _is_error(res), f"rhino_geometry failed: {res!r}"
    return res


def _assert_text_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert "id" in data, f"Expected id in data: {envelope!r}"
    return data


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured error data: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


# --- Happy path --------------------------------------------------------------


async def test_basic_string_succeeds(fresh_document):
    await _purge_objects()

    status, envelope = await _post_text_raw({
        "text": "Hello",
        "point": [1.0, 2.0, 0.0],
        "height": 2.5,
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_text_success(envelope)

    # ObjectSnapshot fields from direct-sdk native.
    assert data.get("type") == "Annotation"
    assert data.get("name") in ("", None) or isinstance(data.get("name"), str)
    assert "bbox" in data and isinstance(data["bbox"], dict)

    # Echoed effective typography (Phase 2 PR-1 response enrichment).
    assert abs(data["height"] - 2.5) < 1e-6, f"height echo = {data.get('height')!r}"
    assert isinstance(data["font"], str) and data["font"]
    assert data["bold"] is False
    assert data["italic"] is False


# --- Override persistence ----------------------------------------------------


async def test_bold_italic_custom_font_persists(fresh_document):
    # Pins the worked-example gate: extraction did NOT regress the
    # annotation-level override persistence that the native factory stamps
    # via SetAnnotationBold / SetAnnotationItalic / SetAnnotationFacename
    # against the parent dimstyle. Verified against the live annotation via
    # rhino_geometry, which reads through GetEffectiveDimensionStyle.
    await _purge_objects()

    text_id = (await _tool_annotation_text({
        "text": "Styled",
        "height": 3.0,
        "font": "Arial",
        "bold": True,
        "italic": True,
    }))["id"]

    geom = await _read_geometry(text_id)

    # AnnotationDetail fields surfaced by GeometryHandler.cpp:56-62 live
    # under `geometry` in the rhino_geometry response.
    detail = geom.get("geometry") or {}
    assert detail.get("bold") is True, f"bold override did not persist: {geom!r}"
    assert detail.get("italic") is True, f"italic override did not persist: {geom!r}"
    font_family = detail.get("fontFamily") or ""
    assert isinstance(font_family, str) and "Arial" in font_family, (
        f"Expected Arial family, got {font_family!r}"
    )
    assert abs(detail.get("textHeight", 0.0) - 3.0) < 1e-3, (
        f"textHeight persistence off: {geom!r}"
    )


async def test_multiline_text_persists(fresh_document):
    await _purge_objects()
    text_id = (await _tool_annotation_text({
        "text": "line1\nline2",
        "height": 1.0,
    }))["id"]

    geom = await _read_geometry(text_id)
    detail = geom.get("geometry") or {}
    plain = detail.get("plainText") or ""
    assert "line1" in plain and "line2" in plain, (
        f"Multi-line text did not persist: {plain!r}"
    )


# --- Strict attribute validation --------------------------------------------


async def test_height_zero_rejected(fresh_document):
    status, envelope = await _post_text_raw({"text": "X", "height": 0})
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "height" in envelope["data"]["errorMessage"].lower()


async def test_empty_text_rejected(fresh_document):
    status, envelope = await _post_text_raw({"text": ""})
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "text" in envelope["data"]["errorMessage"].lower()


async def test_missing_text_rejected(fresh_document):
    status, envelope = await _post_text_raw({"height": 1.0})
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_layer_rejected(fresh_document):
    # Strict-attrs behavior: unknown layer must deterministically throw
    # invalid_input. Relies on ResolveLayerRef's already-strict semantics
    # at LayerHelpers.cpp:77-107. Legacy /create silently defaults —
    # Phase 2 typed routes MUST NOT inherit that leniency.
    await _purge_objects()

    status, envelope = await _post_text_raw({
        "text": "X",
        "layer": "NonExistentLayer__PR1_strict_check__",
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_non_boolean_visible_rejected(fresh_document):
    status, envelope = await _post_text_raw({
        "text": "X",
        "visible": "nope",
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "visible" in envelope["data"]["errorMessage"].lower()


async def test_non_string_name_rejected(fresh_document):
    # Strict attribute handling: malformed `name` type surfaces as
    # invalid_input, not a successful create with the field silently
    # dropped.
    status, envelope = await _post_text_raw({
        "text": "X",
        "name": 123,
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "name" in envelope["data"]["errorMessage"].lower()


async def test_non_string_layer_rejected(fresh_document):
    status, envelope = await _post_text_raw({
        "text": "X",
        "layer": {"nested": "object"},
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "layer" in envelope["data"]["errorMessage"].lower()


async def test_overlong_point_rejected(fresh_document):
    # Schema and contract say point is exactly 3 numbers. Overlong arrays
    # were previously silently truncated by ParsePoint3d — now rejected.
    status, envelope = await _post_text_raw({
        "text": "X",
        "point": [1.0, 2.0, 0.0, 99.0],
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "point" in envelope["data"]["errorMessage"].lower()


# --- Font fallback -----------------------------------------------------------


async def test_nonexistent_font_falls_back(fresh_document):
    # Font-characteristic failures fall back to the document default font;
    # the response echoes the EFFECTIVE applied font, not the requested one.
    # Pins the Codex 2026-04-19 caution: "echo-back must be effective applied
    # values, not merely request echoes."
    await _purge_objects()

    status, envelope = await _post_text_raw({
        "text": "X",
        "font": "NoSuchFontFamily_PR1_fallback_check",
    })
    assert status == 200, f"Expected 200 with font fallback, got {status}: {envelope!r}"
    data = _assert_text_success(envelope)

    effective_font = data.get("font") or ""
    assert isinstance(effective_font, str) and effective_font, (
        f"Expected non-empty effective font: {envelope!r}"
    )
    assert "NoSuchFontFamily_PR1" not in effective_font, (
        f"Response echoed the requested bogus font instead of the fallback: {envelope!r}"
    )
