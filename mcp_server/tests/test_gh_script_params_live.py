"""Live-Rhino defense-in-depth tests for POST /gh/script-params (issue #39).

Pins the atomic-rejection contract added in fix/gh-script-params-pre-validate:
invalid JSON shapes or values must be rejected BEFORE any destructive component
mutation, so the component state is identical before and after a rejected call.

These paths are NOT reachable via the Rook MCP tool surface — the Python
normalizer `_normalize_gh_script_pin_access` (server.py:526) rejects invalid
access values before the HTTP call ever goes out, and the MCP schemas type-check
name/nick/description/current_name fields. Tests here fire raw HTTP at the
native→companion route to simulate direct-HTTP callers.

Invariant probe is `GET /gh/connections?guid=...` per Codex review — exposes
the component's input/output names + source/recipient state directly.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_gh_script_params_live.py

See GitHub issue #39 and rook_docs/work-queue.md for the binding contract.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_python_script(pins_in: list[Any] | None = None) -> str:
    """Create a Python script component; return its guid."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "gh_create_python_script",
        {
            "code": "Result = X",
            "pins_in": pins_in if pins_in is not None else [{"name": "X", "type": "float"}],
            "pins_out": [{"name": "Result", "type": "float"}],
            "name": "ScriptParamsGuard",
        },
    )
    assert not _is_error(res), f"gh_create_python_script failed: {res!r}"
    guid = res.get("guid") or (res.get("data") or {}).get("guid")
    assert isinstance(guid, str) and guid, f"no guid in create response: {res!r}"
    return guid


async def _get_connections(guid: str) -> dict[str, Any]:
    """GET /gh/connections?guid=... → envelope. Used as the invariant probe."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/gh/connections", params={"guid": guid})
    envelope = resp.json()
    assert envelope.get("success") is True, f"/gh/connections returned failure: {envelope!r}"
    data = envelope.get("data") or {}
    assert isinstance(data, dict), f"expected dict data, got: {envelope!r}"
    return data


async def _post_script_params_raw(body: Any) -> tuple[int, dict[str, Any]]:
    """Raw POST to /gh/script-params bypassing all Python-side normalization."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/gh/script-params", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/gh/script-params returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _connections_signature(conns: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (input_names, output_names) as the invariant for rejection tests."""
    inputs = conns.get("Inputs") or conns.get("inputs") or []
    outputs = conns.get("Outputs") or conns.get("outputs") or []

    def _names(items: list[Any]) -> tuple[str, ...]:
        names: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            n = item.get("Name") or item.get("name") or item.get("paramName")
            if isinstance(n, str):
                names.append(n)
        return tuple(names)

    return _names(inputs), _names(outputs)


async def _assert_rejected_without_mutation(
    guid: str,
    body: Any,
    expected_substring: str,
) -> None:
    """Post body, assert it fails, assert connection signature unchanged."""
    before = _connections_signature(await _get_connections(guid))
    status, envelope = await _post_script_params_raw(body)
    assert envelope.get("success") is False, f"expected failure for {body!r}: {envelope!r}"
    data = envelope.get("data")
    if isinstance(data, str):
        assert expected_substring.lower() in data.lower(), (
            f"error text missing {expected_substring!r} for body={body!r}: {data!r}"
        )
    after = _connections_signature(await _get_connections(guid))
    assert before == after, (
        f"component mutated on rejected call {body!r}: before={before} after={after}"
    )


# --- Tests ----------------------------------------------------------------


async def test_bogus_access_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": "X", "access": "bogus"}]},
        "invalid access",
    )


async def test_non_string_access_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": "X", "access": 123}]},
        "'access' must be a string",
    )


async def test_missing_name_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"access": "item"}]},
        "missing 'name'",
    )


async def test_empty_name_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": "   "}]},
        "empty 'name'",
    )


async def test_non_string_name_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": 42}]},
        "'name' must be a string",
    )


async def test_non_string_pin_nick_rejected_without_mutation(fresh_document):
    """Codex finding #1 — pin-level `nick` was on the destructive path."""
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": "X", "nick": 42}]},
        "'nick' must be a string",
    )


async def test_non_string_pin_description_rejected_without_mutation(fresh_document):
    """Codex finding #1 — pin-level `description` was on the destructive path."""
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": [{"name": "X", "description": 42}]},
        "'description' must be a string",
    )


async def test_non_array_inputs_rejected_without_mutation(fresh_document):
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "inputs": {}},
        "'inputs' must be an array",
    )


async def test_non_string_root_nick_rejected_without_mutation(fresh_document):
    """Codex finding #2 — root-level `nick` was post-rebuild but still a gap."""
    guid = await _create_python_script()
    await _assert_rejected_without_mutation(
        guid,
        {"guid": guid, "nick": 42, "inputs": [{"name": "X"}]},
        "'nick' must be a string",
    )


async def test_non_string_guid_rejected_without_mutation(fresh_document):
    """Pre-destructive path — benign before, now gives a structured error."""
    guid = await _create_python_script()
    # Use the real guid on the component under test, but send garbage to the route.
    status, envelope = await _post_script_params_raw({"guid": 12345})
    assert envelope.get("success") is False, f"expected failure: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, str) and "'guid' must be a string" in data, (
        f"missing 'guid' type error: {data!r}"
    )
    # Component on the document is untouched; canvas is unchanged.
    await _get_connections(guid)  # sanity: component still exists and is queryable


async def test_valid_set_script_pins_still_succeeds(fresh_document):
    """Regression floor — the positive path continues to work end-to-end
    after the pre-validation hoist. Uses gh_set_script_pins so we exercise
    the real Rook-client path, then confirms the rename took effect via
    /gh/connections.
    """
    from rook.server import _mcp_tool_executor

    guid = await _create_python_script()
    before_inputs, _ = _connections_signature(await _get_connections(guid))
    assert "X" in before_inputs, f"initial input 'X' missing: {before_inputs!r}"

    rename = await _mcp_tool_executor(
        "gh_set_script_pins",
        {
            "guid": guid,
            "input_updates": [{"current_name": "X", "name": "Xr"}],
        },
    )
    assert not _is_error(rename), f"gh_set_script_pins failed: {rename!r}"

    after_inputs, _ = _connections_signature(await _get_connections(guid))
    assert "Xr" in after_inputs and "X" not in after_inputs, (
        f"rename did not take effect: before={before_inputs}, after={after_inputs}"
    )
