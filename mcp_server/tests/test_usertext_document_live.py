"""Live-Rhino characterization tests for POST /usertext/document-set +
POST /usertext/document-get (Phase 2 PR-10).

Pins the document-level usertext contract + reserved-prefix denylist:

Contract:
  - set then get round-trips values verbatim
  - set RESPONSE itself echoes the full post-mutation map, read back
    from pDoc->GetUserStringKeys — no `id` field (document-level scope)
  - empty-string values REJECTED with invalid_input (SDK treats
    pDoc->SetUserString(k, "") as a delete sentinel, empirically
    confirmed 2026-04-19; delete deferred to /usertext/document-delete)
  - overwrite / accumulate semantics preserved in the set response
    (second set sees prior keys in its own echo)
  - empty userStrings {} is an idempotent no-op (returns current map
    unchanged; no undo fingerprint)
  - get of clean document returns {}
  - empty body AND `{}` body both accepted on document-get
  - strict validation: missing / non-object userStrings / non-string
    value all → invalid_input with key-specific messages

Reserved-prefix denylist (WRITES ONLY):
  - `RookBlock::*` keys rejected on document-set with
    `reserved_namespace` error code
  - Error message names the offending prefix, owner, and redirect
  - Reads are unrestricted (operators can inspect reserved keys for
    diagnostics)
  - Rejection is WHOLESALE: mixed-map `{allowed: "v", "RookBlock::X":
    "v"}` does NOT write `allowed` either; pre-existing keys survive

Run:
    pytest -m requires_rhino mcp_server/tests/test_usertext_document_live.py
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _purge_doc_strings() -> None:
    """Wipe every document-level user string by overwriting each key
    with an empty string via rhino_execute. Empirical observation
    2026-04-19: RhinoCommon `StringTable.SetString(k, None)` does NOT
    delete — it returns the current value without mutating. The
    actual delete sentinel is the empty string, same as the native
    handler's empirical pre-flight result. Deterministic, isolated:
    a single self-contained script is run. Codex caveat satisfied."""
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


async def _seed_reserved_doc_string(key: str, value: str) -> None:
    """Seed a reserved-prefix key at the document level via
    rhino_execute so tests can verify read-side behavior (reads are
    unrestricted on the denylist). The typed route cannot write
    reserved-prefix keys, so seeding bypasses the denylist by going
    through the SDK directly. Deterministic and isolated."""
    from rook.server import _mcp_tool_executor

    code = (
        "import Rhino\n"
        f"Rhino.RhinoDoc.ActiveDoc.Strings.SetString({key!r}, {value!r})\n"
        f"print('seeded {key}')\n"
    )
    res = await _mcp_tool_executor("rhino_execute", {"code": code})
    assert not _is_error(res), f"seed failed: {res!r}"


async def _post_set_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/usertext/document-set", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/usertext/document-set returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _post_get_raw(body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        if body is None:
            # Raw POST with no content body — pins that ParseBodyAndDocSn
            # normalizes empty-body to {} and the handler accepts it.
            resp = await client.post(f"{base_url}/usertext/document-get")
        else:
            resp = await client.post(f"{base_url}/usertext/document-get", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/usertext/document-get returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _tool_set(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_usertext_document_set", body)
    assert not _is_error(res), f"rhino_usertext_document_set failed: {res!r}"
    return res


async def _tool_get(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_usertext_document_get", body or {})
    assert not _is_error(res), f"rhino_usertext_document_get failed: {res!r}"
    return res


def _assert_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict)
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
    await _purge_doc_strings()

    set_res = await _tool_set({"userStrings": {"project": "Alpha"}})
    assert set_res.get("userStrings") == {"project": "Alpha"}, (
        f"set response echo off: {set_res!r}"
    )

    get_res = await _tool_get()
    assert get_res.get("userStrings") == {"project": "Alpha"}, (
        f"get after set off: {get_res!r}"
    )


async def test_set_multiple_keys(fresh_document):
    await _purge_doc_strings()

    set_res = await _tool_set({
        "userStrings": {"a": "1", "b": "2", "c": "3"},
    })
    assert set_res.get("userStrings") == {"a": "1", "b": "2", "c": "3"}


async def test_set_response_echoes_full_map(fresh_document):
    # Pin full-echo contract directly on the set call itself — read
    # back from pDoc->GetUserStringKeys, NOT synthesized from request.
    await _purge_doc_strings()

    set_res = await _tool_set({"userStrings": {"keyA": "valA", "keyB": "valB"}})
    assert "id" not in set_res, (
        f"document-set must NOT echo `id` (document-level scope): {set_res!r}"
    )
    assert set_res.get("userStrings") == {"keyA": "valA", "keyB": "valB"}


# --- No-op path -------------------------------------------------------------


async def test_empty_map_no_op_returns_existing_map_unchanged(fresh_document):
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"a": "1", "b": "2"}})

    noop_res = await _tool_set({"userStrings": {}})
    assert noop_res.get("userStrings") == {"a": "1", "b": "2"}, (
        f"Empty-map no-op must return existing map unchanged: {noop_res!r}"
    )


async def test_get_returns_empty_dict_on_clean_doc(fresh_document):
    await _purge_doc_strings()
    get_res = await _tool_get()
    assert get_res.get("userStrings") == {}


async def test_document_get_accepts_empty_body(fresh_document):
    # Raw HTTP with NO body — ParseBodyAndDocSn normalizes to {}.
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"x": "y"}})

    status, envelope = await _post_get_raw(body=None)
    assert status == 200
    data = _assert_success(envelope)
    assert data.get("userStrings") == {"x": "y"}


async def test_document_get_accepts_empty_json_object(fresh_document):
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"x": "y"}})

    status, envelope = await _post_get_raw(body={})
    assert status == 200
    data = _assert_success(envelope)
    assert data.get("userStrings") == {"x": "y"}


async def test_document_get_has_no_id_field(fresh_document):
    # Acceptance gate #2 from plan doc: doc routes do NOT echo `id`.
    await _purge_doc_strings()
    get_res = await _tool_get()
    assert "id" not in get_res, (
        f"document-get must NOT carry `id` field: {get_res!r}"
    )


# --- Overwrite / accumulation -----------------------------------------------


async def test_overwrite_same_key(fresh_document):
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"k": "first"}})
    set_res = await _tool_set({"userStrings": {"k": "second"}})
    assert set_res.get("userStrings") == {"k": "second"}


async def test_second_set_preserves_prior_keys_in_set_response(fresh_document):
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"a": "1"}})
    second = await _tool_set({"userStrings": {"b": "2"}})
    assert second.get("userStrings") == {"a": "1", "b": "2"}, (
        f"Second set response must carry prior key 'a': {second!r}"
    )


# --- Empty-string rejection (SDK delete-sentinel guard) ---------------------


async def test_empty_string_value_rejected(fresh_document):
    # Pin: document-level empty-string values rejected just like
    # attribute-level (PR-9). Empirical pre-flight 2026-04-19 confirmed
    # pDoc->SetUserString(k, "") deletes the key.
    await _purge_doc_strings()

    status, envelope = await _post_set_raw({"userStrings": {"flag": ""}})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    msg = envelope["data"]["errorMessage"]
    assert "flag" in msg, f"Expected key-specific message naming 'flag': {msg!r}"
    assert "delete" in msg.lower(), (
        f"Expected delete-sentinel rationale in message: {msg!r}"
    )
    assert "/usertext/document-delete" in msg, (
        f"Expected document-specific forward-reference: {msg!r}"
    )


async def test_empty_string_value_does_not_sneak_delete_existing_key(fresh_document):
    # Atomicity guard (mirror of PR-9 test): rejected empty-string set
    # must NOT reach pDoc->SetUserString. Pre-existing key survives.
    await _purge_doc_strings()
    await _tool_set({"userStrings": {"flag": "real"}})

    status, envelope = await _post_set_raw({"userStrings": {"flag": ""}})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")

    get_res = await _tool_get()
    assert get_res.get("userStrings") == {"flag": "real"}, (
        f"Rejected empty-string set leaked into doc store: {get_res!r}"
    )


# --- Strict validation: userStrings shape ------------------------------------


async def test_missing_user_strings_field_rejected(fresh_document):
    status, envelope = await _post_set_raw({})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "userstrings" in envelope["data"]["errorMessage"].lower()


async def test_non_object_user_strings_rejected(fresh_document):
    status, envelope = await _post_set_raw({"userStrings": ["a", "b"]})
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")


async def test_non_string_value_rejected(fresh_document):
    status, envelope = await _post_set_raw({
        "userStrings": {"count": 42, "ok": "yes"},
    })
    assert status == 400
    _assert_structured_error(envelope, "invalid_input")
    assert "count" in envelope["data"]["errorMessage"], (
        f"Expected error message to name offending key 'count': "
        f"{envelope['data']['errorMessage']!r}"
    )


# --- Reserved-prefix denylist (writes only) ---------------------------------


async def test_reserved_prefix_rook_block_rejected_on_set(fresh_document):
    await _purge_doc_strings()
    status, envelope = await _post_set_raw({
        "userStrings": {"RookBlock::test::key": "value"},
    })
    assert status == 400
    # NEW route-local error code for PR-10 — not invalid_input.
    _assert_structured_error(envelope, "reserved_namespace")


async def test_reserved_prefix_error_message_names_prefix_and_owner(fresh_document):
    await _purge_doc_strings()
    status, envelope = await _post_set_raw({
        "userStrings": {"RookBlock::hit": "v"},
    })
    assert status == 400
    msg = envelope["data"]["errorMessage"]
    # Tight assertions: prefix + owner + sanctioned redirect.
    assert "RookBlock::" in msg, f"Expected prefix in message: {msg!r}"
    assert "block-definition metadata" in msg, (
        f"Expected owner description in message: {msg!r}"
    )
    assert "/block/user-strings" in msg, (
        f"Expected sanctioned-alternative redirect in message: {msg!r}"
    )


async def test_reserved_prefix_readable_via_get(fresh_document):
    # Reads are deliberately unrestricted so operators can inspect
    # reserved keys for diagnostics. Seed a reserved-prefix key
    # directly via rhino_execute (bypasses the denylist — only writes
    # through /usertext/document-set are gated), then read it back
    # through the typed route.
    await _purge_doc_strings()
    await _seed_reserved_doc_string("RookBlock::SeedTest::x", "seeded-value")

    get_res = await _tool_get()
    assert get_res.get("userStrings", {}).get("RookBlock::SeedTest::x") == "seeded-value", (
        f"document-get must surface reserved-prefix keys for diagnostics: {get_res!r}"
    )


async def test_reserved_prefix_does_not_sneak_through_on_mixed_map(fresh_document):
    # Atomicity contract: wholesale-reject. A mixed map that contains
    # ANY reserved-prefix key must NOT write any of its keys (allowed
    # or not). Pre-seeded allowed key must also survive unchanged.
    await _purge_doc_strings()
    # Pre-seed an allowed key so we can verify it survives the
    # rejection path unchanged.
    await _tool_set({"userStrings": {"preexisting": "untouched"}})

    status, envelope = await _post_set_raw({
        "userStrings": {
            "newallowed": "wouldbeok",
            "RookBlock::bad": "rejectme",
        },
    })
    assert status == 400
    _assert_structured_error(envelope, "reserved_namespace")

    # Verify:
    #   1. preexisting allowed key is unchanged ("untouched")
    #   2. new allowed key was NOT added
    get_res = await _tool_get()
    stored = get_res.get("userStrings", {})
    assert stored.get("preexisting") == "untouched", (
        f"Pre-existing allowed key must survive rejection unchanged: {get_res!r}"
    )
    assert "newallowed" not in stored, (
        f"New allowed key must NOT have been written on rejected mixed map: {get_res!r}"
    )
