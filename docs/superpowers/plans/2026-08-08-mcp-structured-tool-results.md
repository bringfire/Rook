# MCP Structured Tool Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a legacy-text-compatible structured MCP projection of Rook's existing internal `{success, data}` result envelope, including containment paths, without changing internal callers.

**Architecture:** Keep `server.call_tool()` and `_handle_meta_tool()` as the existing internal text-content adapters. Add one private projection helper and a private public-MCP mode so the registered SDK handler receives `CallToolResult` directly from the authoritative envelope before text formatting; propagate that mode through `rook_tools_call` so the target result is not double wrapped. Route the existing containment wrapper through the same projection.

**Tech Stack:** Python 3.11, MCP Python SDK 1.28.0, pytest, existing Rook tool dispatcher and canonical gateway.

## Global Constraints

- Baseline is exact `02918747d38412419954c86fa3167a421eadfea4`.
- Production changes are limited to `mcp_server/src/rook/server.py`.
- `structuredContent` is exactly `{"success": exact boolean, "data": exact value}`.
- `isError` is exactly the inverse of the authoritative internal success boolean.
- Existing `TextContent` remains byte-for-byte unchanged.
- `rook_tools_call` exposes its target result directly; it never wraps a target envelope in a successful gateway envelope.
- Every public request-handler branch that completes with an ordinary Rook envelope uses the structured projection, including both containment bypasses.
- SDK-generated validation and pre-envelope exception results retain existing SDK behavior.
- Internal `server.call_tool()`, `_handle_meta_tool()`, shared text parsers, and ChatRunner gateway composition retain their current behavior.
- No `outputSchema`, result class, parser, new protocol, or receipt taxonomy.
- No changes to Prime, ChatRunner, managed Grasshopper, native code, sliders, component metadata, dispatch, targeting, profiles, or validation.
- No provider, Prime, Ollama, MCP subprocess, Rhino, or Grasshopper contact.
- Stop immediately if implementation requires a second production module.

## File Map

- Modify `mcp_server/src/rook/server.py`: retain authoritative envelopes through the public request boundary and project them into MCP `CallToolResult`.
- Create `mcp_server/tests/test_mcp_structured_tool_results.py`: table-driven public-handler, direct/gateway, SDK-deferral, and internal-compatibility tests.
- Modify `mcp_server/tests/test_containment_agent_protocols.py`: strengthen the two existing transport-wrapper cases with structured refusal assertions.
- Modify `docs/CURRENT_ARCHITECTURE.md`: document legacy text, additive structured content, deliberate error signaling, and SDK deferrals.
- Modify this plan only for execution evidence and review decisions; it does not authorize more behavior.

## Baseline

From the worktree root, use the existing reviewed Rook Python environment while forcing imports to this worktree:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_tool_result.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  -q
```

Recorded plan-time baseline: **190 passed, 11 existing DSPy warnings**.

---

### Task 1: Project Authoritative Envelopes At Every Rook-Owned Public MCP Branch

**Files:**
- Modify: `mcp_server/src/rook/server.py:20731-20940`
- Create: `mcp_server/tests/test_mcp_structured_tool_results.py`
- Modify: `mcp_server/tests/test_containment_agent_protocols.py:183-207`

**Interfaces:**
- Consumes: existing internal envelopes `dict[str, Any]` with exact `success` and `data` keys; existing `_format_tool_result(result) -> list[TextContent]`.
- Produces: `_project_tool_result(result, *, public_mcp)` returning existing text content for internal mode or `mcp_types.CallToolResult` for public mode.
- Preserves: `call_tool(name, arguments)` and `_handle_meta_tool(name, arguments, profile)` default to the existing internal list result.

- [x] **Step 1: Add table-driven public-handler RED tests**

Create `mcp_server/tests/test_mcp_structured_tool_results.py` with the following helpers and cases:

```python
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import types as mcp_types

from rook import server


async def _public_call(name: str, arguments: dict[str, Any]):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"value": 3},
        ["a", 2],
        "plain text",
        7,
        True,
        None,
    ],
)
async def test_public_direct_success_retains_text_and_adds_exact_envelope(
    monkeypatch, data
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    envelope = {"success": True, "data": data}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call("rhino_instances", {})

    assert result.content[0].text == server._format_tool_result(envelope)[0].text
    assert result.structuredContent == envelope
    assert result.isError is False
    retained.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [{"error": "blocked"}, "plain failure"])
async def test_public_direct_failure_retains_text_and_sets_mcp_error(
    monkeypatch, data
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    envelope = {"success": False, "data": data}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call("rhino_instances", {})

    assert result.content[0].text == server._format_tool_result(envelope)[0].text
    assert result.structuredContent == envelope
    assert result.isError is True
    retained.assert_awaited_once_with()
```

- [x] **Step 2: Add direct/gateway ownership and SDK-deferral RED tests**

Append these tests to the new module:

```python
@pytest.mark.asyncio
async def test_rook_tools_call_exposes_target_envelope_without_double_wrap(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    envelope = {"success": True, "data": ["native", 4]}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call(
        "rook_tools_call", {"name": "rhino_instances", "arguments": {}}
    )

    assert result.content[0].text == server._format_tool_result(envelope)[0].text
    assert result.structuredContent == envelope
    assert result.isError is False
    retained.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_gateway_owned_refusal_is_structured_and_marked_error(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")

    result = await _public_call(
        "rook_tools_call", {"name": "rook_tools_ls", "arguments": {}}
    )

    envelope = {
        "success": False,
        "data": {"error": "meta_recursion_forbidden", "name": "rook_tools_ls"},
    }
    assert result.content[0].text == server._format_tool_result(envelope)[0].text
    assert result.structuredContent == envelope
    assert result.isError is True


@pytest.mark.asyncio
async def test_public_handler_passes_decoded_arguments_to_canonical_ingress(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    seen = []
    envelope = {"success": True, "data": {"matched": 1}}

    async def retained_call_tool(name, arguments, *, _public_mcp=False):
        seen.append((name, arguments, _public_mcp))
        return server._project_tool_result(envelope, public_mcp=_public_mcp)

    monkeypatch.setattr(server, "call_tool", retained_call_tool)
    arguments = {"query": "gh_snapshot", "limit": 3}

    result = await _public_call("rook_tools_search", arguments)

    assert seen == [("rook_tools_search", arguments, True)]
    assert result.structuredContent == envelope


@pytest.mark.asyncio
async def test_sdk_validation_error_retains_sdk_owned_shape():
    result = await _public_call("rook_tools_search", {"query": []})

    assert result.isError is True
    assert result.structuredContent is None
    assert "Input validation error" in result.content[0].text


@pytest.mark.asyncio
async def test_pre_envelope_exception_retains_sdk_owned_shape(monkeypatch):
    async def raise_before_envelope(_name, _arguments, *, _public_mcp=False):
        raise RuntimeError("pre-envelope failure")

    monkeypatch.setattr(server, "call_tool", raise_before_envelope)

    result = await _public_call("rhino_instances", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text == "pre-envelope failure"
```

The argument test asserts equality at the canonical ingress only. It does not constrain later targeting enrichment.

- [x] **Step 3: Strengthen the containment transport RED test**

In `test_transport_wrapper_tombstones_missing_schema_before_sdk_validation`, retain both existing text assertions and add exact envelope/error assertions:

```python
async def test_transport_wrapper_tombstones_missing_schema_before_sdk_validation(
    monkeypatch,
) -> None:
    from mcp import types as mcp_types
    from rook import server

    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)

    # Retain the existing handler and request construction before these assertions.
    direct_payload = json.loads(text.removeprefix("Error: "))
    assert direct_payload["tool"] == "gh_execute_intent"
    assert result.root.structuredContent == {
        "success": False,
        "data": direct_payload,
    }
    assert result.root.isError is True

    nested_payload = json.loads(nested_text.removeprefix("Error: "))
    assert nested_payload["tool"] == "gh_replay_recipe"
    assert nested_result.root.structuredContent == {
        "success": False,
        "data": nested_payload,
    }
    assert nested_result.root.isError is True
    dispatch.assert_not_awaited()
```

The function already imports `server` before constructing the requests; place the mock after that import and before either handler call. Both refusals must remain pre-dispatch.

- [x] **Step 4: Run the RED selection**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_containment_agent_protocols.py::test_transport_wrapper_tombstones_missing_schema_before_sdk_validation `
  -q
```

Expected: failures show ordinary public results have `structuredContent is None`, failures retain `isError=False`, and containment still hard-codes `isError=False`. There must be no network or host contact.

- [x] **Step 5: Add one private projection helper**

In `server.py`, immediately after `_format_tool_result`, add:

```python
def _project_tool_result(
    result: dict[str, Any], *, public_mcp: bool
) -> list[TextContent] | mcp_types.CallToolResult:
    contents = _format_tool_result(result)
    if not public_mcp:
        return contents
    success = result["success"]
    return mcp_types.CallToolResult(
        content=contents,
        structuredContent={"success": success, "data": result["data"]},
        isError=not success,
    )
```

Do not change `_format_tool_result`. Indexing `success` and `data` treats a malformed code-owned envelope as an internal contradiction rather than inventing defaults.

- [x] **Step 6: Preserve `_handle_meta_tool()` defaults while propagating public mode**

Change its signature to:

```python
async def _handle_meta_tool(name, arguments, profile, *, _public_mcp=False):
```

For each locally owned result envelope in this function, replace:

```python
return _format_tool_result(envelope)
```

with:

```python
return _project_tool_result(envelope, public_mcp=_public_mcp)
```

This applies to containment denial, list/search/read success, read refusal, recursion refusal, profile refusal, dispatchability refusal, argument-shape refusal, and schema-validation refusal.

For the admitted target call, preserve the existing origin token and propagate the same mode:

```python
    token = _dispatch_origin.set("meta")
    try:
        return await call_tool(target, targs, _public_mcp=_public_mcp)
    finally:
        _dispatch_origin.reset(token)
```

With `_public_mcp=False`, existing ChatRunner composition still receives formatted content. With `True`, the target's envelope becomes the sole public structured result.

- [x] **Step 7: Preserve internal `call_tool()` while registering a thin public handler**

Remove `@mcp.call_tool()` from the existing `call_tool` function and add its private mode:

```python
async def call_tool(
    name: str,
    arguments: dict[str, Any] | None,
    *,
    _public_mcp: bool = False,
) -> list[TextContent] | mcp_types.CallToolResult:
```

Keep the existing policy, targeting, dispatch, observation, and route logic in place. Replace every `return _format_tool_result(envelope)` in this function with:

```python
return _project_tool_result(envelope, public_mcp=_public_mcp)
```

Change the meta interception to:

```python
    if name in META_TOOL_NAMES:
        return await _handle_meta_tool(
            name, arguments, _active_profile, _public_mcp=_public_mcp
        )
```

Then register only this thin public boundary immediately after `call_tool`:

```python
@mcp.call_tool()
async def _mcp_call_tool(name: str, arguments: dict[str, Any]):
    return await call_tool(name, arguments, _public_mcp=True)
```

The SDK therefore receives `CallToolResult`; all direct internal calls omit the private keyword and retain `list[TextContent]`.

- [x] **Step 8: Route both containment bypasses through the same projection**

Replace each manual containment `CallToolResult(content=contents, isError=False)` construction with:

```python
            result = await call_tool(raw_name, None, _public_mcp=True)
            return mcp_types.ServerResult(result)
```

and for the nested branch:

```python
                result = await call_tool(raw_name, outer, _public_mcp=True)
                return mcp_types.ServerResult(result)
```

Do not call the retained SDK handler for these tombstones; they intentionally refuse before SDK schema validation. Do not parse their text.

- [x] **Step 9: Run the GREEN selection**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_containment_agent_protocols.py::test_transport_wrapper_tombstones_missing_schema_before_sdk_validation `
  -q
```

Expected: all selected tests pass. Confirm the data-shape matrix covers object, array, string, number, boolean, and null success plus object/string failure.

- [x] **Step 10: Run the internal compatibility seam**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_tool_result.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  -q
```

Expected: all pass with the existing DSPy warnings only. Existing tests must continue proving the internal gateway conversion, text parser, profile intersection, targeting transformation, and ChatRunner injection behavior.

- [x] **Step 11: Review source scope and commit Task 1**

```powershell
git diff --check
git diff --name-only HEAD
git diff --stat HEAD
git add -- `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_containment_agent_protocols.py
git commit -m "fix: expose structured MCP tool results"
```

Expected production scope: only `mcp_server/src/rook/server.py`. Stop for independent review before Task 2 if any second production module appears, any legacy text changes, or any internal caller requires adaptation.

**Mandatory review gate:** Review the registered SDK handler, both containment branches, `rook_tools_call` propagation, exact text equality, and unchanged internal seams before documentation reconciliation.

---

### Task 2: Reconcile The Public Contract And Final No-Contact Evidence

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md:134-143`
- Modify: `docs/superpowers/plans/2026-08-08-mcp-structured-tool-results.md`

**Interfaces:**
- Consumes: Task 1's verified public `CallToolResult` projection.
- Produces: canonical architecture wording and a reproducible verification ledger.

- [x] **Step 1: Update the canonical Tool Result Surface documentation**

Retain the current internal/public text rows and add these facts without deleting the legacy parsing guidance:

```markdown
For every public request-handler branch that completes with an ordinary Rook
`{success, data}` envelope, MCP also returns:

- `structuredContent = {"success": success, "data": data}`;
- `isError = !success`.

The existing `TextContent` bytes remain unchanged. Structured content is additive,
but truthful `isError` is a deliberate semantic behavior change for compliant MCP
clients. SDK-generated schema-validation and pre-envelope exception results retain
the SDK's existing result behavior. Internal Python callers of `server.call_tool()`
continue receiving `list[TextContent]`.
```

- [x] **Step 2: Run the complete focused seam**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_tool_result.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  -q
```

Expected: baseline **190 tests** plus the new structured-result cases pass; warnings are limited to the existing DSPy warnings.

- [x] **Step 3: Compile and scan the exact surface**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_containment_agent_protocols.py

rg -n "structuredContent|isError|_public_mcp|_project_tool_result" `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_mcp_structured_tool_results.py `
  mcp_server/tests/test_containment_agent_protocols.py

git diff --check origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected complete branch scope:

```text
docs/CURRENT_ARCHITECTURE.md
docs/superpowers/plans/2026-08-08-mcp-structured-tool-results.md
docs/superpowers/specs/2026-08-08-mcp-structured-tool-results-design.md
mcp_server/src/rook/server.py
mcp_server/tests/test_containment_agent_protocols.py
mcp_server/tests/test_mcp_structured_tool_results.py
```

No Prime, ChatRunner, managed, native, slider, or component-metadata path may appear.

- [x] **Step 4: Record exact evidence in this plan**

Append an `## Execution Ledger` section with exactly these fixed labels and their observed
values copied from the preceding commands: `Baseline SHA`, `Task 1 commit`, `Focused seam`,
`Production scope`, `Legacy text equality`, `Structured data-shape matrix`,
`Direct/gateway no-double-wrap`, `Direct/nested containment`,
`SDK validation/exception deferral`, `Internal server.call_tool and ChatRunner seams`, and
`External contact`. Do not record estimates or provisional values; every entry must contain
the actual SHA, count, path, or pass/fail fact available at execution time.

- [x] **Step 5: Commit Task 2 and stop for final review**

```powershell
git add -- `
  docs/CURRENT_ARCHITECTURE.md `
  docs/superpowers/plans/2026-08-08-mcp-structured-tool-results.md
git diff --cached --check
git commit -m "docs: record structured MCP result contract"
git show --check --stat --oneline HEAD
git status --short --branch
```

Expected: clean worktree. Stop for independent review. Do not push, deploy, or contact Prime/Rhino/Grasshopper without later authorization.

## Execution Ledger

- **Baseline SHA:** `02918747d38412419954c86fa3167a421eadfea4` (`origin/main`).
- **Task 1 commit:** `8ddc2586c3c579c70132e822cbe65dc6f4947d9d` (`fix: expose structured MCP tool results`).
- **Focused seam:** `203 passed`, with exactly `11` existing DSPy warnings.
- **Production scope:** only `mcp_server/src/rook/server.py`; Git delta `80` additions and `52` deletions, of which `76` additions and `52` deletions are nonblank.
- **Legacy text equality:** passed for successful object, list, string, number, boolean, and null data; failed object and string data; and both direct and nested containment refusals.
- **Structured data-shape matrix:** exact `{"success": success, "data": data}` passed for successful object, list, string, number, boolean, and null data and for failed object and string data; `isError` matched `not success` in every case.
- **Direct/gateway no-double-wrap:** passed; the direct result and the target result reached through `rook_tools_call` each expose the target envelope exactly once.
- **Direct/nested containment:** passed; direct `gh_execute_intent` and nested `gh_replay_recipe` refusals retain exact legacy text, expose structured failure envelopes, set `isError=true`, and perform zero target dispatches.
- **SDK validation/exception deferral:** passed; SDK-generated schema-validation and pre-envelope exception results retain `structuredContent=None` and the existing SDK error behavior.
- **Internal server.call_tool and ChatRunner seams:** isolated compatibility selection `95 passed`, with exactly `11` existing DSPy warnings; default internal calls continue returning `list[TextContent]`.
- **External contact:** none; verification used imported handlers, causal test doubles, compilation, and repository scans only. No Prime, provider, Ollama, MCP subprocess, Rhino, or Grasshopper contact occurred.
