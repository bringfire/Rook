"""Live-Rhino characterization tests for POST /usertext/object-delete
+ POST /usertext/document-delete (2026-04-20 usertext-delete PR).

Closes the usertext family — complements PR-9 (object set/get) and
PR-10 (document set/get + reserved-prefix denylist).

Contract pins:
  - Empty-string sentinel is the delete path (attribute + document).
    Handler pre/post-state diff derives `deletedKeys` — no dependency
    on SDK return-value semantics.
  - Idempotent: deleting a non-existent key is a success with that
    key absent from `deletedKeys`.
  - Duplicate keys in the request are silently deduplicated,
    PRESERVING FIRST-SEEN ORDER in `deletedKeys` (not sorted — caller
    order is the audit contract per scope pass 2026-04-20).
  - Empty `keys: []` is an idempotent no-op that leaves no fingerprint
    in the undo stack (parallel to PR-9/PR-10's empty-map no-op).
  - Reserved-prefix denylist GATES document-level writes (including
    delete). Error message anchors caller at the sanctioned delete
    action on /block/user-strings. Rejection is WHOLESALE — no keys
    deleted when any reserved-prefix key is in the request.
  - Strict validation: missing/malformed id + missing/malformed keys
    + non-string/empty-string element → invalid_input.
  - Unknown object id → not_found (structured).

Run:
    pytest -m requires_rhino mcp_server/tests/test_usertext_delete_live.py
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Fixtures + helpers --------------------------------------------------


async def _purge_objects() -> None:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_objects", {"limit": 500})
    if _is_error(res) or not isinstance(res, dict):
        return
    objects = res.get("objects") or []
    ids = [o["id"] for o in objects if isinstance(o, dict) and "id" in o]
    if ids:
        await _mcp_tool_executor("rhino_delete", {"ids": ids})


async def _purge_doc_strings() -> None:
    """Wipe every document-level user string by overwriting each key
    with an empty string via rhino_execute. Uses the proven
    `StringTable.GetKey(i)` enumeration pattern from
    test_usertext_document_live.py:48 — RhinoCommon's `.Keys`
    property may not be available on `StringTable`, and the indexed
    enumeration is the pattern already characterized as stable across
    Rhino versions. Asserts the `rhino_execute` result so the fixture
    fails loudly if the script errors rather than running tests
    against a dirty document."""
    from rook.server import _mcp_tool_executor

    code = (
        "import Rhino\n"
        "strings = Rhino.RhinoDoc.ActiveDoc.Strings\n"
        "keys = [strings.GetKey(i) for i in range(strings.Count)]\n"
        "for k in keys:\n"
        "    strings.SetString(k, '')\n"
        "print('purged %d -> %d doc-level user-strings' "
        "% (len(keys), strings.Count))\n"
    )
    res = await _mcp_tool_executor("rhino_execute", {"code": code})
    assert not _is_error(res), f"purge failed: {res!r}"


async def _create_test_object(name: str = "UsertextDeleteTestPoint") -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": [0.0, 0.0, 0.0], "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    return res["id"]


async def _seed_object_strings(obj_id: str, kv: dict[str, str]) -> None:
    """Seed an object's attribute user-string store via /usertext/object-set."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_usertext_object_set",
        {"id": obj_id, "userStrings": kv},
    )
    assert not _is_error(res), f"seed set failed: {res!r}"


async def _seed_doc_strings(kv: dict[str, str]) -> None:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_usertext_document_set",
        {"userStrings": kv},
    )
    assert not _is_error(res), f"seed doc set failed: {res!r}"


async def _post_object_delete_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/usertext/object-delete", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(
            f"/usertext/object-delete returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _post_document_delete_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/usertext/document-delete", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(
            f"/usertext/document-delete returned non-JSON body: {resp.text!r} ({ex!r})")
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


def _assert_delete_success(
    envelope: dict[str, Any],
    *,
    expected_deleted: list[str],
    expected_post: dict[str, str],
    expect_id: bool,
) -> None:
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert data.get("deletedKeys") == expected_deleted, (
        f"deletedKeys mismatch: expected {expected_deleted!r}, got {data.get('deletedKeys')!r}"
    )
    assert data.get("userStrings") == expected_post, (
        f"post-state mismatch: expected {expected_post!r}, got {data.get('userStrings')!r}"
    )
    if expect_id:
        assert "id" in data, f"object route response must include id: {envelope!r}"
    else:
        assert "id" not in data, (
            f"document route response must NOT include id: {envelope!r}"
        )


# --- Object-delete: happy path ------------------------------------------


async def test_object_delete_single_existing_key(fresh_document):
    """Delete 1 existing key → deletedKeys=[k]; post-state omits it.

    Implicitly also exercises the survived-existing-key failure branch
    (Codex 2026-04-20): the handler computes the pre/post diff AFTER
    SetUserString and throws operation_failed if any key in `preSet`
    also appears in `postSet`. A 200 success response with the
    expected post-state is positive evidence that the sentinel
    actually deleted — if the SDK ever stopped deleting on empty-
    string, this test would flip to operation_failed.
    """
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"flag": "v1", "color": "red"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["flag"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["flag"],
        expected_post={"color": "red"},
        expect_id=True,
    )
    # Explicit contract pin: an existing key that was requested for
    # deletion must be absent from the post-state. If the SDK ever
    # changed behavior and the key survived, the handler's
    # survived-existing-key check would surface operation_failed
    # rather than returning success with a misleading audit.
    assert "flag" not in envelope["data"]["userStrings"], (
        "Survived-existing-key contract: requested key still present "
        "post-mutation should surface operation_failed, not a success "
        "envelope that omits it from deletedKeys."
    )


async def test_object_delete_multiple_existing_keys(fresh_document):
    """Delete multiple existing keys → all in deletedKeys; post-state
    loses them; preserved keys intact."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(
        obj_id, {"a": "1", "b": "2", "c": "3", "d": "4"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["a", "c"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["a", "c"],
        expected_post={"b": "2", "d": "4"},
        expect_id=True,
    )


async def test_object_delete_mix_existing_and_missing(fresh_document):
    """Mix of existing + non-existent keys → only existing in deletedKeys."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"a": "1", "b": "2"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["a", "ghost", "b", "phantom"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["a", "b"],
        expected_post={},
        expect_id=True,
    )


async def test_object_delete_non_existent_only_is_success(fresh_document):
    """Delete a key that doesn't exist → success, deletedKeys=[],
    post-state unchanged. Idempotent contract."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"real": "value"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["ghost"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=[],
        expected_post={"real": "value"},
        expect_id=True,
    )


async def test_object_delete_empty_keys_is_noop(fresh_document):
    """Empty keys [] → idempotent no-op; returns current state."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"k": "v"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": [],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=[],
        expected_post={"k": "v"},
        expect_id=True,
    )


# --- Object-delete: duplicate-key / first-seen order (Codex pin) --------


async def test_object_delete_duplicate_keys_preserve_first_seen_order(fresh_document):
    """`["b", "a", "b"]` where both `a` and `b` exist → deletedKeys is
    first-seen-order deduplication: `["b", "a"]` (NOT sorted `["a", "b"]`).
    Load-bearing pin per Codex review 2026-04-20 — caller order is the
    audit contract."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"a": "1", "b": "2"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["b", "a", "b"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["b", "a"],
        expected_post={},
        expect_id=True,
    )


async def test_object_delete_duplicate_keys_for_absent_key(fresh_document):
    """`["a", "a"]` where `a` is absent → success, deletedKeys=[],
    post-state unchanged. Duplicate still deduplicates even when
    absent."""
    await _purge_objects()
    obj_id = await _create_test_object()
    await _seed_object_strings(obj_id, {"b": "2"})

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["a", "a"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=[],
        expected_post={"b": "2"},
        expect_id=True,
    )


# --- Object-delete: validation errors ------------------------------------


async def test_object_delete_missing_keys_field(fresh_document):
    """Missing `keys` → invalid_input."""
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_object_delete_raw({"id": obj_id})
    _assert_structured_error(envelope, "invalid_input")


async def test_object_delete_keys_not_array(fresh_document):
    """`keys` not an array → invalid_input."""
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": "not-an-array",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_object_delete_keys_element_not_string(fresh_document):
    """Non-string element in `keys` → invalid_input, index-specific."""
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["ok", 42, "also-ok"],
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "keys[1]" in envelope["data"]["errorMessage"], (
        f"Expected index-specific error: {envelope!r}"
    )


async def test_object_delete_keys_element_empty_string(fresh_document):
    """Empty-string element → invalid_input, index-specific."""
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_object_delete_raw({
        "id": obj_id, "keys": ["ok", ""],
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "keys[1]" in envelope["data"]["errorMessage"]


async def test_object_delete_unknown_id(fresh_document):
    """Unknown (random) id → not_found (structured)."""
    import uuid as _uuid

    fake_id = str(_uuid.uuid4())
    status, envelope = await _post_object_delete_raw({
        "id": fake_id, "keys": ["anything"],
    })
    _assert_structured_error(envelope, "not_found")


async def test_object_delete_missing_id(fresh_document):
    """Missing `id` → invalid_input."""
    status, envelope = await _post_object_delete_raw({"keys": ["a"]})
    _assert_structured_error(envelope, "invalid_input")


# --- Document-delete: happy path ----------------------------------------


async def test_document_delete_single_existing_key(fresh_document):
    """Delete 1 existing doc key → deletedKeys=[k]; post omits it;
    response has NO id field (doc scope)."""
    await _purge_doc_strings()
    await _seed_doc_strings({"project": "Alpha", "version": "1.0"})

    status, envelope = await _post_document_delete_raw({"keys": ["project"]})
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["project"],
        expected_post={"version": "1.0"},
        expect_id=False,
    )


async def test_document_delete_duplicate_keys_preserve_first_seen_order(fresh_document):
    """Document-level duplicate/first-seen-order pin — parallel to the
    object-level test."""
    await _purge_doc_strings()
    await _seed_doc_strings({"a": "1", "b": "2"})

    status, envelope = await _post_document_delete_raw({
        "keys": ["b", "a", "b"],
    })
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=["b", "a"],
        expected_post={},
        expect_id=False,
    )


async def test_document_delete_empty_keys_is_noop(fresh_document):
    """Empty keys [] → idempotent no-op at doc level."""
    await _purge_doc_strings()
    await _seed_doc_strings({"k": "v"})

    status, envelope = await _post_document_delete_raw({"keys": []})
    assert status == 200
    _assert_delete_success(
        envelope,
        expected_deleted=[],
        expected_post={"k": "v"},
        expect_id=False,
    )


# --- Document-delete: reserved-prefix gating ----------------------------


async def test_document_delete_reserved_prefix_rejected(fresh_document):
    """RookBlock::* key in doc-delete → reserved_namespace;
    wholesale rejection; error message anchors caller at
    /block/user-strings with action=delete."""
    await _purge_doc_strings()

    status, envelope = await _post_document_delete_raw({
        "keys": ["RookBlock::SomeKey"],
    })
    _assert_structured_error(envelope, "reserved_namespace")

    msg = envelope["data"]["errorMessage"]
    # Specific anchors per scope-pass v2: route AND the delete action.
    assert "RookBlock::" in msg, f"Missing prefix name: {msg!r}"
    assert "/block/user-strings" in msg, f"Missing redirect route: {msg!r}"
    assert "action=delete" in msg, (
        f"Missing delete-action hint — Codex scope-pass required the redirect "
        f"to anchor the sanctioned delete surface, not just the route: {msg!r}"
    )


async def test_document_delete_reserved_prefix_sneak_delete_guard(fresh_document):
    """Mixed request `[allowed, "RookBlock::X"]` fails wholesale:
    reserved_namespace returned AND `allowed` survives unchanged.
    Parallel to PR-10's set-side sneak-delete guard."""
    await _purge_doc_strings()
    await _seed_doc_strings({"allowed": "v"})

    status, envelope = await _post_document_delete_raw({
        "keys": ["allowed", "RookBlock::X"],
    })
    _assert_structured_error(envelope, "reserved_namespace")

    # The allowed key must still be present post-rejection.
    from rook.server import _mcp_tool_executor

    get_res = await _mcp_tool_executor("rhino_usertext_document_get", {})
    assert not _is_error(get_res), f"doc-get after rejection failed: {get_res!r}"
    assert get_res.get("userStrings") == {"allowed": "v"}, (
        f"Sneak-delete guard failed — `allowed` was removed by the rejected "
        f"wholesale request: {get_res!r}"
    )


async def test_document_delete_missing_keys_field(fresh_document):
    """Missing `keys` → invalid_input at doc level."""
    status, envelope = await _post_document_delete_raw({})
    _assert_structured_error(envelope, "invalid_input")
