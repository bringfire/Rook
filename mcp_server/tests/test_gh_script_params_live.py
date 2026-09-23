"""Live-Rhino defense-in-depth tests for POST /gh/script-params (issue #39).

Pins the atomic-rejection contract added in fix/gh-script-params-pre-validate:
invalid JSON shapes or values must be rejected BEFORE any destructive component
mutation, so the component state is identical before and after a rejected call.
The key invariant is that an already-wired upstream source remains attached to
its input pin — if the handler stripped the component mid-loop, the wire would
be dropped.

These paths are NOT reachable via the Rook MCP tool surface — the Python
normalizer `_normalize_gh_script_pin_access` (server.py:526) rejects invalid
access values before the HTTP call ever goes out, and the MCP schemas type-check
name/nick/description/current_name fields. Tests here fire raw HTTP at the
native→companion route to simulate direct-HTTP callers.

Invariant probe is `GET /gh/connections?guid=...` per Codex review. Critical
response-shape facts observed in `GrasshopperHandler.GetConnections`
(src/Rook/Handlers/GrasshopperHandler.cs:2011):
  - Envelope keys are PascalCase: `Inputs`, `Outputs`, `ParamName`, `Sources`,
    `Recipients`, `ParamIndex`, `ParamNickName`.
  - A pin appears in `Inputs`/`Outputs` ONLY if `sourceList.Count > 0` /
    `recipientList.Count > 0` (GrasshopperHandler.cs:2105 / 2140). An
    unconnected pin produces no entry. So tests MUST establish an upstream
    wire during setup for the invariant to be meaningful — otherwise before
    and after would both be empty for trivially wrong reasons.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_gh_script_params_live.py

See GitHub issue #39 and rook_docs/work-queue.md for the binding contract.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


def _get_guid(result: Any) -> str | None:
    """Extract a guid from a GH tool response. Schemas vary across MCP tools:
    `gh_create_python_script` returns `component_guid`, `gh_create_panel`
    returns `guid`, and some wrap inside `data`. Accept any.
    """
    if not isinstance(result, dict):
        return None
    for key in ("component_guid", "guid", "Guid"):
        val = result.get(key)
        if isinstance(val, str) and val:
            return val
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("component_guid", "guid", "Guid"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


async def _create_python_script() -> str:
    """Create a Python script component with one declared input ('X'); return guid."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "gh_create_python_script",
        {
            "code": "Result = X",
            "pins_in": [{"name": "X", "type": "float"}],
            "pins_out": [{"name": "Result", "type": "float"}],
            "name": "ScriptParamsGuard",
        },
    )
    assert not _is_error(res), f"gh_create_python_script failed: {res!r}"
    guid = _get_guid(res)
    assert isinstance(guid, str) and guid, f"no guid in create response: {res!r}"
    return guid


async def _create_upstream_panel(content: str = "42") -> str:
    """Create a panel to serve as an upstream source; return guid."""
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "gh_create_panel",
        {"content": content, "x": 100, "y": 100},
    )
    assert not _is_error(res), f"gh_create_panel failed: {res!r}"
    guid = _get_guid(res)
    assert isinstance(guid, str) and guid, f"no guid in panel response: {res!r}"
    return guid


async def _wire(
    source_guid: str,
    target_guid: str,
    *,
    target_param: str | None = None,
    source_param: str | None = None,
) -> None:
    """Wire source.output -> target.input via raw HTTP.

    This live harness intentionally uses the companion route directly even
    though `gh_connect` is also exposed on the MCP surface; the route remains
    POST /gh/connect (see GrasshopperHandler.cs:5193).

    `source_param` is required when the source is a multi-output component
    (e.g. the script's second output "Result"). `target_param` can be omitted
    when the target is a simple IGH_Param (panel/slider) — GetParam
    (GrasshopperHandler.cs:5822) returns the component itself.
    """
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    body: dict[str, Any] = {"sourceGuid": source_guid, "targetGuid": target_guid}
    if target_param is not None:
        body["targetParam"] = target_param
    if source_param is not None:
        body["sourceParam"] = source_param

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/gh/connect", json=body)
    envelope = resp.json()
    assert envelope.get("success") is True, f"POST /gh/connect failed: {envelope!r}"


async def _get_connections(guid: str) -> dict[str, Any]:
    """GET /gh/connections?guid=... and return the `data` dict."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
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

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/gh/script-params", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/gh/script-params returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _connections_signature(conns: dict[str, Any]) -> tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]:
    """Extract ((input_name, source_count), ...) and same for outputs.

    IMPORTANT: The JSON wire format is camelCase — `inputs`/`outputs`/`paramName`/
    `sources`/`recipients`. The C# anonymous type uses PascalCase (Inputs/
    ParamName/Sources) but ASP.NET's default serializer applies
    `JsonNamingPolicy.CamelCase`, lowercasing the first letter. Verified
    empirically via probe 2026-04-21 — do not trust the C# source casing.

    Only pins with Sources.Count > 0 / Recipients.Count > 0 are emitted by
    the handler (GrasshopperHandler.cs:2105 / 2140), so a mutation that
    strips a wired pin would drop its entry and change the signature.
    """
    inputs = conns.get("inputs") or []
    outputs = conns.get("outputs") or []

    def _pairs(items: list[Any], count_key: str) -> tuple[tuple[str, int], ...]:
        out: list[tuple[str, int]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("paramName")
            conn_list = item.get(count_key) or []
            if isinstance(name, str):
                out.append((name, len(conn_list) if isinstance(conn_list, list) else 0))
        return tuple(out)

    return _pairs(inputs, "sources"), _pairs(outputs, "recipients")


async def _setup_wired_script() -> tuple[str, tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]]:
    """Create script + upstream panel, wire them, return (script_guid, signature_before).

    Asserts the wire actually landed by checking the signature's first input has
    Sources.Count >= 1 — protects against the test harness silently passing on
    an empty-Inputs payload (which is what an unconnected script returns).
    """
    script_guid = await _create_python_script()
    panel_guid = await _create_upstream_panel()
    await _wire(panel_guid, script_guid, target_param="X")
    sig = _connections_signature(await _get_connections(script_guid))
    input_sig, _ = sig
    assert input_sig and input_sig[0][1] >= 1, (
        f"test setup failed — wire did not land; initial signature was {sig!r}"
    )
    return script_guid, sig


async def _setup_wired_script_with_downstream_recipient() -> tuple[str, tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]]:
    """Create script + upstream panel + downstream panel, wire BOTH directions,
    return (script_guid, signature_before).

    The script's "Result" output is wired to a second panel so that `Outputs`
    has at least one entry with Recipients.Count >= 1. Covers Codex's
    residual-risk note from PR #79: invalid `outputs` payloads are guarded
    structurally by the same `ValidateScriptPinDef` pre-validation loop as
    `inputs`, but the existing 11 live tests only prove the invariant on the
    input side.

    Fails loud if either wire fails to land — same pattern as _setup_wired_script.
    """
    from rook.server import _mcp_tool_executor

    script_guid = await _create_python_script()
    upstream_guid = await _create_upstream_panel("upstream")
    # Second panel positioned to the right so it doesn't overlap the upstream.
    downstream_res = await _mcp_tool_executor(
        "gh_create_panel",
        {"content": "downstream", "x": 500, "y": 100},
    )
    assert not _is_error(downstream_res), f"downstream panel create failed: {downstream_res!r}"
    downstream_guid = _get_guid(downstream_res)
    assert isinstance(downstream_guid, str) and downstream_guid, (
        f"no guid in downstream panel: {downstream_res!r}"
    )

    await _wire(upstream_guid, script_guid, target_param="X")
    # Script has two outputs: the default "out" print stream at index 0,
    # then "Result" at index 1. Wire the "Result" output -> downstream panel
    # (panel is a simple IGH_Param, so omit targetParam — GetParam returns
    # the panel itself per GrasshopperHandler.cs:5843).
    await _wire(script_guid, downstream_guid, source_param="Result")

    sig = _connections_signature(await _get_connections(script_guid))
    input_sig, output_sig = sig
    assert input_sig and input_sig[0][1] >= 1, (
        f"test setup failed — input wire did not land; initial signature was {sig!r}"
    )
    assert output_sig and any(name == "Result" and count >= 1 for name, count in output_sig), (
        f"test setup failed — output wire did not land; initial output_sig was {output_sig!r}"
    )
    return script_guid, sig


async def _assert_rejected_without_mutation(
    script_guid: str,
    before_sig: tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]],
    body: Any,
    expected_substring: str,
) -> None:
    """Post body, assert it fails, assert connection signature unchanged from before_sig."""
    status, envelope = await _post_script_params_raw(body)
    assert envelope.get("success") is False, f"expected failure for {body!r}: {envelope!r}"
    data = envelope.get("data")
    if isinstance(data, str):
        assert expected_substring.lower() in data.lower(), (
            f"error text missing {expected_substring!r} for body={body!r}: {data!r}"
        )
    after_sig = _connections_signature(await _get_connections(script_guid))
    assert before_sig == after_sig, (
        f"component mutated on rejected call {body!r}:\n"
        f"  before={before_sig}\n  after={after_sig}"
    )


# --- Tests ----------------------------------------------------------------


async def test_bogus_access_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": "X", "access": "bogus"}]},
        "invalid access",
    )


async def test_non_string_access_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": "X", "access": 123}]},
        "'access' must be a string",
    )


async def test_missing_name_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"access": "item"}]},
        "missing 'name'",
    )


async def test_empty_name_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": "   "}]},
        "empty 'name'",
    )


async def test_non_string_name_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": 42}]},
        "'name' must be a string",
    )


async def test_non_string_pin_nick_rejected_without_mutation(fresh_document):
    """Codex finding #1 — pin-level `nick` was on the destructive path."""
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": "X", "nick": 42}]},
        "'nick' must be a string",
    )


async def test_non_string_pin_description_rejected_without_mutation(fresh_document):
    """Codex finding #1 — pin-level `description` was on the destructive path."""
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": [{"name": "X", "description": 42}]},
        "'description' must be a string",
    )


async def test_non_array_inputs_rejected_without_mutation(fresh_document):
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "inputs": {}},
        "'inputs' must be an array",
    )


async def test_non_string_root_nick_rejected_without_mutation(fresh_document):
    """Codex finding #2 — root-level `nick` was post-rebuild but still a gap."""
    guid, before = await _setup_wired_script()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "nick": 42, "inputs": [{"name": "X"}]},
        "'nick' must be a string",
    )


async def test_non_string_guid_rejected_without_mutation(fresh_document):
    """Pre-destructive path — benign before, now gives a structured error."""
    guid, before = await _setup_wired_script()
    status, envelope = await _post_script_params_raw({"guid": 12345})
    assert envelope.get("success") is False, f"expected failure: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, str) and "'guid' must be a string" in data, (
        f"missing 'guid' type error: {data!r}"
    )
    after = _connections_signature(await _get_connections(guid))
    assert before == after, f"component mutated on {{guid:12345}}: before={before} after={after}"


async def test_valid_set_script_pins_still_succeeds(fresh_document):
    """Regression floor — the positive path continues to work end-to-end
    after the pre-validation hoist. Renames the wired input 'X' -> 'Xr'
    via `gh_set_script_pins`; asserts the rename took effect AND the
    upstream wire was reattached (non-zero Sources on the renamed pin).
    """
    from rook.server import _mcp_tool_executor

    guid, before = await _setup_wired_script()
    assert before[0][0] == ("X", 1), f"unexpected pre-rename signature: {before!r}"

    rename = await _mcp_tool_executor(
        "gh_set_script_pins",
        {
            "guid": guid,
            "input_updates": [{"current_name": "X", "name": "Xr"}],
        },
    )
    assert not _is_error(rename), f"gh_set_script_pins failed: {rename!r}"

    after_inputs, _ = _connections_signature(await _get_connections(guid))
    assert after_inputs, f"no connected inputs after rename: {after_inputs!r}"
    assert after_inputs[0][0] == "Xr", (
        f"rename did not take effect; after_inputs={after_inputs!r}"
    )
    assert after_inputs[0][1] >= 1, (
        f"wire was dropped on valid rename; after_inputs={after_inputs!r}"
    )


async def test_bogus_access_on_outputs_rejected_without_mutation(fresh_document):
    """#41 Codex residual-risk bundle — prove the output-side destructive path
    is guarded symmetric to inputs. Structurally already the case (the
    ValidateScriptPinDef pre-validation loop iterates `outputs` the same way
    it iterates `inputs`), but the existing 11 tests all probe the input side.
    This 12th case wires script.Result -> downstream panel, sends an invalid
    `outputs` payload, and asserts the downstream wire survived.
    """
    guid, before = await _setup_wired_script_with_downstream_recipient()
    await _assert_rejected_without_mutation(
        guid,
        before,
        {"guid": guid, "outputs": [{"name": "Result", "access": "bogus"}]},
        "invalid access",
    )
