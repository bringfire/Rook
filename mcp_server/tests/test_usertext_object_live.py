"""Live-Rhino characterization tests for POST /usertext/object-set +
POST /usertext/object-get (Phase 2 PR-9).

Pins the direct-sdk native usertext substrate worked example:

Contract:
  - set then get round-trips values verbatim
  - set RESPONSE itself echoes the full post-mutation map (not just a
    count) — read back from persisted attributes, not synthesized from
    the request body
  - empty-string values REJECTED with invalid_input (SDK treats them
    as a delete sentinel; delete is deferred to a follow-up route, so
    the set surface guards against sneak-delete) — rejection must not
    touch the persisted store
  - overwrite / accumulate / no-op semantics preserved in the set
    response (a second set sees prior keys in its own echo)
  - empty userStrings {} is an idempotent no-op that leaves no
    fingerprint (returns current map unchanged)
  - strict validation: missing / malformed id / non-object userStrings
    / non-string value / empty-string value all → invalid_input.
    Non-string and empty-string errors name the offending key exactly.
  - unknown object id → structured not_found (via StructuredError)
  - deleted-object id (once-valid, now-gone) → not_found

Run:
    pytest -m requires_rhino mcp_server/tests/test_usertext_object_live.py

Rhino must be running with RookNative loaded.
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


async def _create_test_object(name: str = "UsertextTestPoint") -> str:
    """Create a Rhino.Geometry.Point object and return its id."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": [0.0, 0.0, 0.0], "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _post_set_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/usertext/object-set", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/usertext/object-set returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _post_get_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/usertext/object-get", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/usertext/object-get returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_set(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_usertext_object_set", body)
    assert not _is_error(res), f"rhino_usertext_object_set failed: {res!r}"
    return res


async def _tool_get(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_usertext_object_get", body)
    assert not _is_error(res), f"rhino_usertext_object_get failed: {res!r}"
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
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


# --- Happy path -------------------------------------------------------------


async def test_set_then_get_round_trip(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    set_res = await _tool_set({
        "id": obj_id,
        "userStrings": {"greeting": "hello"},
    })
    assert set_res.get("userStrings") == {"greeting": "hello"}, (
        f"set response echo off: {set_res!r}"
    )

    get_res = await _tool_get({"id": obj_id})
    assert get_res.get("userStrings") == {"greeting": "hello"}, (
        f"get after set off: {get_res!r}"
    )


async def test_set_multiple_keys(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    set_res = await _tool_set({
        "id": obj_id,
        "userStrings": {"a": "1", "b": "2", "c": "3"},
    })
    assert set_res.get("userStrings") == {"a": "1", "b": "2", "c": "3"}, (
        f"set response missing keys: {set_res!r}"
    )


async def test_set_response_echoes_full_map(fresh_document):
    # Pin the PR-9 response-shape contract directly on the set call
    # (not via a follow-up get): {id, userStrings: {...}} read back
    # from persisted attributes, not synthesized from the request body.
    await _purge_objects()
    obj_id = await _create_test_object()

    set_res = await _tool_set({
        "id": obj_id,
        "userStrings": {"keyA": "valA", "keyB": "valB"},
    })
    assert set_res.get("id") == obj_id
    user_strings = set_res.get("userStrings")
    assert user_strings == {"keyA": "valA", "keyB": "valB"}, (
        f"Expected full post-mutation map in set response, got {user_strings!r}"
    )


# --- Empty-string rejection (SDK delete-sentinel guard) ---------------------


async def test_empty_string_value_rejected(fresh_document):
    # Pin: empty-string values are rejected with invalid_input. SDK
    # contract verified empirically 2026-04-19:
    # ON_3dmObjectAttributes::SetUserString(key, "") DELETES the key
    # from the attribute store (the attribute-level analog of the
    # document-level SetUserString(k, nullptr) delete at
    # BlocksHandler.cpp:3090). Accepting empty-string input would
    # therefore deliver delete semantics through /usertext/object-set,
    # which is explicitly out of scope for PR-9 — delete is deferred
    # to a future /usertext/object-delete surface with its own contract.
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_set_raw({
        "id": obj_id,
        "userStrings": {"flag": ""},
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    msg = envelope["data"]["errorMessage"]
    # Key-specific: names the offending key.
    assert "flag" in msg, (
        f"Expected error message to name the offending key 'flag': {msg!r}"
    )
    # Makes the rationale discoverable in the error text — delete is
    # the real reason, not "empty strings are ugly."
    assert "delete" in msg.lower(), (
        f"Expected error message to explain the delete-sentinel rationale: {msg!r}"
    )


async def test_empty_string_value_does_not_sneak_delete_existing_key(fresh_document):
    # Stronger variant: pin that the handler REJECTS at validation and
    # does not reach ModifyObjectAttributes. If the rejection were
    # lost, the SDK would delete the pre-existing key — this test
    # pins that the key survives the failed set.
    await _purge_objects()
    obj_id = await _create_test_object()

    await _tool_set({"id": obj_id, "userStrings": {"flag": "real"}})

    status, envelope = await _post_set_raw({
        "id": obj_id,
        "userStrings": {"flag": ""},
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")

    # The prior value MUST still be present — the rejected set must
    # not have touched the attribute store.
    get_res = await _tool_get({"id": obj_id})
    assert get_res.get("userStrings") == {"flag": "real"}, (
        f"Rejected empty-string set leaked into attribute store: {get_res!r}"
    )


# --- Overwrite / accumulation ------------------------------------------------


async def test_overwrite_same_key(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    await _tool_set({"id": obj_id, "userStrings": {"k": "first"}})
    set_res = await _tool_set({"id": obj_id, "userStrings": {"k": "second"}})
    assert set_res.get("userStrings") == {"k": "second"}, (
        f"Overwrite did not land: {set_res!r}"
    )


async def test_second_set_preserves_prior_keys_in_set_response(fresh_document):
    # Pin the "full echo" contract on the second set's own response —
    # NOT just via a follow-up get. A caller issuing the second set
    # should see both keys in its response without needing an
    # additional read round-trip.
    await _purge_objects()
    obj_id = await _create_test_object()

    await _tool_set({"id": obj_id, "userStrings": {"a": "1"}})
    second = await _tool_set({"id": obj_id, "userStrings": {"b": "2"}})
    assert second.get("userStrings") == {"a": "1", "b": "2"}, (
        f"Second set response must carry prior key 'a': {second!r}"
    )


# --- No-op path --------------------------------------------------------------


async def test_empty_map_no_op_returns_existing_map_unchanged(fresh_document):
    # Pin the declared-no-op contract: sending userStrings={} on an
    # object that already has user strings returns the existing map
    # unchanged (no wipe, no open UndoScope, no redraw).
    await _purge_objects()
    obj_id = await _create_test_object()

    await _tool_set({"id": obj_id, "userStrings": {"a": "1", "b": "2"}})
    noop_res = await _tool_set({"id": obj_id, "userStrings": {}})
    assert noop_res.get("userStrings") == {"a": "1", "b": "2"}, (
        f"Empty-map no-op did not return existing map unchanged: {noop_res!r}"
    )


async def test_get_empty_object_returns_empty_dict(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    get_res = await _tool_get({"id": obj_id})
    assert get_res.get("userStrings") == {}, (
        f"Object with no user strings must return empty dict: {get_res!r}"
    )


# --- Strict validation: id ---------------------------------------------------


async def test_missing_id_rejected(fresh_document):
    status, envelope = await _post_set_raw({"userStrings": {"a": "1"}})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "id" in envelope["data"]["errorMessage"].lower()


async def test_malformed_uuid_rejected(fresh_document):
    status, envelope = await _post_set_raw({
        "id": "not-a-uuid",
        "userStrings": {"a": "1"},
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_unknown_object_id_rejected(fresh_document):
    # Syntactically valid UUID that does not resolve to any document
    # object → structured not_found (via StructuredError, not silent
    # mapping to invalid_input).
    await _purge_objects()
    status, envelope = await _post_set_raw({
        "id": "00000000-0000-0000-0000-000000000001",
        "userStrings": {"a": "1"},
    })
    assert status == 400
    _assert_structured_error(envelope, "not_found")


async def test_set_on_deleted_object_rejected(fresh_document):
    # Stronger variant of `unknown_object_id`: create a real object,
    # delete it, then try to set user-strings on its now-stale id.
    # Pins not_found behavior on a "once-valid, now-gone" id rather
    # than on a random UUID.
    from rook.server import _mcp_tool_executor

    await _purge_objects()
    obj_id = await _create_test_object()

    del_res = await _mcp_tool_executor("rhino_delete", {"ids": [obj_id]})
    assert not _is_error(del_res), f"rhino_delete failed: {del_res!r}"

    status, envelope = await _post_set_raw({
        "id": obj_id,
        "userStrings": {"a": "1"},
    })
    assert status == 400
    _assert_structured_error(envelope, "not_found")


# --- Strict validation: userStrings ------------------------------------------


async def test_missing_user_strings_field_rejected(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_set_raw({"id": obj_id})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "userstrings" in envelope["data"]["errorMessage"].lower()


async def test_non_object_user_strings_rejected(fresh_document):
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_set_raw({
        "id": obj_id,
        "userStrings": ["a", "b"],  # array, not object
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "userstrings" in envelope["data"]["errorMessage"].lower()


async def test_non_string_value_rejected(fresh_document):
    # Deliberate divergence from legacy block-handler silent coercion
    # at BlocksHandler.cpp:2550-2551. Phase 2 typed routes reject
    # non-strings with a KEY-SPECIFIC message, so callers know exactly
    # which value was rejected.
    await _purge_objects()
    obj_id = await _create_test_object()

    status, envelope = await _post_set_raw({
        "id": obj_id,
        "userStrings": {"count": 42, "ok": "yes"},
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    # Key-specific error message — names the offending key.
    msg = envelope["data"]["errorMessage"]
    assert "count" in msg, (
        f"Expected error message to name the offending key 'count': {msg!r}"
    )
