"""Live-Rhino characterization tests for POST /select (Phase 2 PR-0).

Pins the additive-contract hygiene landed by PR-0:
  - `name` (exact attribute-name match, case-insensitive) selects the matching object
  - `name` matching is case-insensitive — `"alpha"` matches object named "Alpha"
  - `name` does NOT treat `*` as a wildcard (exact match only)
  - `namePattern` (wildcard) still works after PR-0 (regression guard)
  - Nested `bbox: {min, max}` shape selects the expected objects
  - Flat `bboxMin` / `bboxMax` still works after PR-0 (regression guard)
  - Flat bbox takes precedence over nested when both present
  - Malformed nested `bbox` (non-object, short arrays, non-numeric) → invalid_input
  - Mixed `name` + `namePattern` → structured {errorCode: "invalid_input"}

Run:
    pytest -m requires_rhino mcp_server/tests/test_select_additive_live.py

Rhino must be running with RookNative loaded. Tests reset the document on
entry via the fresh_document fixture — run them in a throwaway session.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _purge_objects() -> None:
    """Delete every object in the active document.

    `fresh_document` calls `rhino_document_ops(action=new)` but that does NOT
    reliably wipe the object table across test sessions (live verification
    2026-04-19: 19 objects survived a `new` call). These tests assert absolute
    `selectedCount` values, so they need a guaranteed-clean slate. This helper
    enumerates via `/objects` and bulk-deletes via `/delete` to pin state.
    """
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_objects", {"limit": 500})
    if _is_error(res) or not isinstance(res, dict):
        return
    objects = res.get("objects") or []
    ids = [o["id"] for o in objects if isinstance(o, dict) and "id" in o]
    if ids:
        await _mcp_tool_executor("rhino_delete", {"ids": ids})


async def _create_named_box(
    corner1: list[float],
    corner2: list[float],
    name: str,
) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {
            "type": "BOX",
            "corner1": corner1,
            "corner2": corner2,
            "name": name,
        },
    )
    assert not _is_error(res), f"rhino_create BOX failed: {res!r}"
    return res["id"]


async def _post_select_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/select", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/select returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _get_selection_raw() -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/selection")
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/selection returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_select_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
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


async def _selected_ids() -> set[str]:
    status, envelope = await _get_selection_raw()
    assert status == 200, f"/selection returned {status}: {envelope!r}"
    data = envelope.get("data") or {}
    objects = data.get("objects") or []
    return {obj["id"] for obj in objects if isinstance(obj, dict) and "id" in obj}


# --- name (exact match) predicate --------------------------------------------


async def test_name_exact_match_selects_only_that_object(fresh_document):
    await _purge_objects()
    a = await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")
    await _create_named_box([2, 0, 0], [3, 1, 1], "Beta")
    await _create_named_box([4, 0, 0], [5, 1, 1], "AlphaBeta")

    status, envelope = await _post_select_raw({"name": "Alpha"})
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 1, f"Expected 1 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == {a}, f"Expected only Alpha box selected, got {selected!r}"


async def test_name_no_match_selects_nothing(fresh_document):
    await _purge_objects()
    await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")
    await _create_named_box([2, 0, 0], [3, 1, 1], "Beta")

    status, envelope = await _post_select_raw({"name": "Gamma"})
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount", 0) == 0, f"Expected 0 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == set(), f"Expected empty selection, got {selected!r}"


async def test_name_is_case_insensitive(fresh_document):
    # `namePattern` uses case-insensitive wildcard match (towlower); `name`
    # must match that semantics, or callers migrating from `namePattern: "Alpha"`
    # to `name: "alpha"` would silently stop selecting the same objects.
    await _purge_objects()
    a = await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")
    await _create_named_box([2, 0, 0], [3, 1, 1], "Beta")

    status, envelope = await _post_select_raw({"name": "alpha"})
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 1, (
        f"Expected case-insensitive match to find Alpha: {envelope!r}"
    )

    selected = await _selected_ids()
    assert selected == {a}, f"Expected Alpha selected by 'alpha', got {selected!r}"


async def test_name_does_not_match_as_wildcard(fresh_document):
    # `name` is exact — passing a pattern with '*' should match literal '*',
    # not act as a wildcard. No box is named "Alpha*" so selection is empty.
    await _purge_objects()
    await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")
    await _create_named_box([2, 0, 0], [3, 1, 1], "AlphaBeta")

    status, envelope = await _post_select_raw({"name": "Alpha*"})
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount", 0) == 0, (
        f"`name` must be exact, not wildcard: {envelope!r}"
    )


# --- namePattern (wildcard) regression guard ---------------------------------


async def test_namePattern_wildcard_still_works(fresh_document):
    await _purge_objects()
    a = await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")
    ab = await _create_named_box([2, 0, 0], [3, 1, 1], "AlphaBeta")
    await _create_named_box([4, 0, 0], [5, 1, 1], "Gamma")

    status, envelope = await _post_select_raw({"namePattern": "Alpha*"})
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 2, f"Expected 2 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == {a, ab}, f"Expected Alpha + AlphaBeta selected, got {selected!r}"


# --- bbox nested + flat regression guard -------------------------------------


async def test_nested_bbox_selects_contained_objects(fresh_document):
    await _purge_objects()
    inside = await _create_named_box([0, 0, 0], [1, 1, 1], "Inside")
    await _create_named_box([10, 10, 10], [11, 11, 11], "Outside")

    status, envelope = await _post_select_raw({
        "bbox": {"min": [-1, -1, -1], "max": [5, 5, 5]},
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 1, f"Expected 1 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == {inside}, f"Expected Inside box selected, got {selected!r}"


async def test_flat_bbox_still_works(fresh_document):
    await _purge_objects()
    inside = await _create_named_box([0, 0, 0], [1, 1, 1], "Inside")
    await _create_named_box([10, 10, 10], [11, 11, 11], "Outside")

    status, envelope = await _post_select_raw({
        "bboxMin": [-1, -1, -1],
        "bboxMax": [5, 5, 5],
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 1, f"Expected 1 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == {inside}, f"Expected Inside box selected, got {selected!r}"


async def test_flat_bbox_takes_precedence_over_nested(fresh_document):
    # Flat bbox covers Inside only; nested bbox covers Outside only. If flat
    # wins, selection is {Inside}. Pins the documented precedence rule so
    # stable callers that send flat keep observing flat semantics even if a
    # future edit accidentally adds an `else` branch order swap.
    await _purge_objects()
    inside = await _create_named_box([0, 0, 0], [1, 1, 1], "Inside")
    await _create_named_box([10, 10, 10], [11, 11, 11], "Outside")

    status, envelope = await _post_select_raw({
        "bboxMin": [-1, -1, -1],
        "bboxMax": [5, 5, 5],
        "bbox": {"min": [9, 9, 9], "max": [12, 12, 12]},
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_select_success(envelope)
    assert data.get("selectedCount") == 1, f"Expected 1 selected: {envelope!r}"

    selected = await _selected_ids()
    assert selected == {inside}, (
        f"Flat bbox should win precedence; got {selected!r}"
    )


# --- malformed nested bbox → invalid_input -----------------------------------


async def test_malformed_nested_bbox_non_object_rejected(fresh_document):
    # `bbox` as a string (not an object) — caller sent the wrong shape.
    status, envelope = await _post_select_raw({"bbox": "oops"})
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "bbox" in envelope["data"]["errorMessage"].lower()


async def test_malformed_nested_bbox_missing_min_rejected(fresh_document):
    status, envelope = await _post_select_raw({
        "bbox": {"max": [5, 5, 5]},
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_malformed_nested_bbox_short_array_rejected(fresh_document):
    status, envelope = await _post_select_raw({
        "bbox": {"min": [0, 0], "max": [5, 5, 5]},
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


async def test_malformed_nested_bbox_non_numeric_rejected(fresh_document):
    status, envelope = await _post_select_raw({
        "bbox": {"min": [0, 0, 0], "max": [5, "nope", 5]},
    })
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")


# --- mixed-predicate rejection -----------------------------------------------


async def test_mixed_name_and_namePattern_rejected(fresh_document):
    await _create_named_box([0, 0, 0], [1, 1, 1], "Alpha")

    status, envelope = await _post_select_raw({
        "name": "Alpha",
        "namePattern": "Alpha*",
    })
    # SendErrorData emits HTTP 400 + success:false + structured data. Pin
    # the status so a future refactor that silently demotes the error path
    # to SendError (string-only) fails loudly here.
    assert status == 400, f"Expected 400, got {status}: {envelope!r}"
    _assert_structured_error(envelope, "invalid_input")
    assert "name" in envelope["data"]["errorMessage"].lower()
