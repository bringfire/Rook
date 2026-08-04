# ChatRunner MCP Capability-Parity Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ChatRunner a conditional, scope-bound client of Rook's existing `rook_tools_ls`, `rook_tools_search`, `rook_tools_read`, and `rook_tools_call` MCP gateway without duplicating capability or dispatch authority.

**Architecture:** One lightweight contract module single-sources the four existing MCP schemas. The MCP server owns a scope-bound executor that intersects ChatRunner's immutable `full | readonly` ceiling with the active MCP profile, invokes the existing meta handler, and reuses the existing MCP-to-agent result conversion. ChatRunner conditionally exposes and intercepts those four tools only when that executor is injected; the production Chat service supplies it lazily from the MCP owner.

**Tech Stack:** Python 3.12, MCP `Tool`/`TextContent`, LiteLLM tool schemas, existing `ChatRunner`, `ToolRegistry`, aiohttp Chat service, pytest, `unittest.mock`.

## Global Constraints

- Baseline is exact commit `8baf325a459ec9bb53cae24b1af0fab452b3001e`; the two approved specification commits precede implementation.
- No provider, Ollama, Worker, Rhino, Grasshopper, readiness, or mutation contact during implementation or review.
- `ChatRunner` core must not import `rook.server`.
- Existing `request_tools`, `search_tools`, direct ChatRunner tools, `ToolDispatcher`, tool groups, capability index, targeting, validation, target dispatch, observations, and receipts remain authoritative.
- Do not add `gh_library` or `gh_batch_component_info` as new direct ChatRunner routes or groups.
- Do not create another capability index, dispatch table, policy allowlist, result taxonomy, receipt system, or gateway client framework.
- The canonical executor is optional. With no executor, all four `rook_tools_*` schemas are absent and hallucinated gateway calls fail without direct dispatch.
- ChatRunner's code-owned `tool_access` is exact `full | readonly` and cannot be supplied by the model.
- Effective authority is the intersection of that fixed ceiling and the active MCP profile. `readonly` at either boundary wins; otherwise the active `full | lean` profile remains unchanged.
- The exact profile equations are:

  ```text
  ChatRunner readonly + MCP full     -> readonly
  ChatRunner readonly + MCP lean     -> readonly
  ChatRunner readonly + MCP readonly -> readonly
  ChatRunner full     + MCP readonly -> readonly
  ChatRunner full     + MCP lean     -> lean
  ChatRunner full     + MCP full     -> full
  ```

- Invalid MCP profile configuration fails before capability-index access or target dispatch.
- Reuse the existing MCP-to-agent result conversion unchanged. Do not claim raw MCP wire or object identity preservation.
- Assert exact gateway arguments at canonical-executor ingress. At target dispatch, assert existing canonical Rhino/document targeting enrichment instead of unchanged arguments.
- Preserve existing exception stringification. Exception-content hardening is outside this slice.
- No retry, fallback to direct dispatch, alternate target, model routing change, skill routing, benchmark, archive, or live qualification.
- The explicit-skill local-agent qualification remains paused through this plan.

## Known Clean-Base Test Conditions

The initial focused audit reproduced the schema-golden failure below. Plan self-review expanded the exact broad selection and also reproduced the existing Chat integration test's stale non-streaming LiteLLM mock. The two unrelated clean-base failures are:

```text
mcp_server/tests/test_rookchat_tool_schema_golden.py::test_local_catalog_rhino_execute_intent_schema_is_actionable
KeyError: 'rhino_execute_intent'

mcp_server/tests/test_chat_integration.py::TestChatIntegration::test_full_conversation_flow
AssertionError: assert 'text_delta' in ['done']
```

Focused commands omit these unrelated tests. Final verification reruns the exact broad command and requires the same two test IDs and signatures with no new failures.

Fresh plan self-review of that broad selection at the documentation-only branch state produced:

```text
537 passed, 2 failed, 13 deselected, 18 warnings
```

## File Responsibility Map

- Create `mcp_server/src/rook/mcp_capability_gateway_contract.py`
  - Own only the four canonical names and their existing MCP `Tool` definitions.
  - No index, policy, executor, target, or ChatRunner imports.
- Modify `mcp_server/src/rook/server.py`
  - Consume the shared schemas in the live MCP surface.
  - Factor the existing MCP-to-agent conversion without changing its output.
  - Build the fixed-scope executor and intersect authority before invoking the existing meta handler.
- Modify `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Accept an optional injected canonical executor.
  - Conditionally expose the shared schemas.
  - Intercept the four exact names and delegate once without direct fallback.
- Modify `mcp_server/src/rook/agent/chat/server.py`
  - Lazily compose the default full-access ChatRunner with the real scope-bound executor.
- Modify `mcp_server/src/rook/agent/capability_inventory.py`
  - Reuse the shared names in the existing intercepted-surface accounting.
- Create `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`
  - Own focused schema, conditional exposure, ChatRunner loop, and production-composition regressions.
- Modify `mcp_server/tests/test_rook_tools_meta.py`
  - Pin shared schema identity, authority intersection, canonical result conversion, and existing MCP policy ownership.
- Modify only adjacent existing tests if a genuine current assertion must include the newly intercepted four names.

---

### Task 1: Single-Source Schemas and Build the Scope-Bound Canonical Executor

**Files:**
- Create: `mcp_server/src/rook/mcp_capability_gateway_contract.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_rook_tools_meta.py`

**Interfaces:**
- Produces: `MCP_CAPABILITY_GATEWAY_NAMES: frozenset[str]`
- Produces: `build_mcp_capability_gateway_tools() -> tuple[Tool, ...]`
- Produces: `build_mcp_capability_gateway_executor(tool_access: str) -> Callable[[str, dict[str, Any]], Awaitable[Any]]`
- Preserves: `_mcp_tool_executor(tool_name: str, params: dict) -> dict` and its current runtime result shapes
- Reuses: `_handle_meta_tool(name, arguments, profile)` and `call_tool(name, arguments)`

- [x] **Step 1: Add valid-red tests for one canonical schema source**

Append tests that import the not-yet-created contract and compare it to the real MCP surface:

```python
from rook.mcp_capability_gateway_contract import (
    MCP_CAPABILITY_GATEWAY_NAMES,
    build_mcp_capability_gateway_tools,
)


EXPECTED_GATEWAY_NAMES = frozenset({
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
})


def _tool_projection(tool):
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema,
    }


def test_gateway_contract_owns_exact_existing_schemas():
    tools = build_mcp_capability_gateway_tools()
    assert MCP_CAPABILITY_GATEWAY_NAMES == EXPECTED_GATEWAY_NAMES
    assert tuple(tool.name for tool in tools) == (
        "rook_tools_ls",
        "rook_tools_search",
        "rook_tools_read",
        "rook_tools_call",
    )
    assert len({_tool_projection(tool)["name"] for tool in tools}) == 4


def test_live_mcp_surface_uses_shared_gateway_contract():
    expected = {
        tool.name: _tool_projection(tool)
        for tool in build_mcp_capability_gateway_tools()
    }
    live = {
        tool.name: _tool_projection(tool)
        for tool in asyncio.run(server._all_live_tools())
        if tool.name in EXPECTED_GATEWAY_NAMES
    }
    assert live == expected
```

- [x] **Step 2: Run the schema tests and verify behavioral RED**

Run from the repository root:

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_rook_tools_meta.py `
  -k "gateway_contract_owns or live_mcp_surface_uses_shared" -q
```

Expected: collection fails because `rook.mcp_capability_gateway_contract` does not exist.

- [x] **Step 3: Create the single schema source and consume it from the MCP surface**

Create the contract module with this exact responsibility and shape:

```python
from __future__ import annotations

from mcp.types import Tool

MCP_CAPABILITY_GATEWAY_NAMES = frozenset({
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
})


def build_mcp_capability_gateway_tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="rook_tools_ls",
            description=(
                "Browse the Rook tool catalog like a filesystem. Lists tool entries and child paths "
                "under a domain/group path (e.g. '/', '/rhino', '/gh', '/video'). Returns compact "
                "entries only (no input schemas) — use rook_tools_read for a tool's full schema. "
                "Pair with rook_tools_search to find tools, then rook_tools_call to invoke them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Catalog path to list, e.g. '/' or '/rhino'. Default '/'.",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many path segments deep to expand. Default 1.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="rook_tools_search",
            description=(
                "Search the Rook tool catalog by keyword; returns matching tools with a one-line "
                "summary each. Covers the full tool surface — geometry, Grasshopper, native "
                "road intersections, vision, BIM, scene, video, knowledge. Use this to discover a tool, then "
                "rook_tools_read for its schema and rook_tools_call to invoke it. "
                "Exact hidden GH aliases resolve through this gateway, including "
                "gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
                "and gh_snapshot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search for, e.g. 'camera preview' or 'boolean union'.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter, e.g. 'rhino', 'gh', 'video', 'bim'.",
                    },
                    "readonly_safe": {
                        "type": "boolean",
                        "description": "If true, only return read-only-safe tools.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return. Default 10.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="rook_tools_read",
            description=(
                "Read one Rook tool's full record: description, domain/groups, and input JSON schema. "
                "Call this after rook_tools_search to learn a tool's arguments before rook_tools_call. "
                "Use this after searching exact hidden GH names such as gh_update_script, "
                "gh_set_script_pins, gh_status, gh_create_csharp_script, and gh_snapshot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact tool name, e.g. 'rhino_video_models'.",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="rook_tools_call",
            description=(
                "Invoke any dispatchable Rook tool by name with its arguments, through the normal "
                "policy path (the readonly profile wall still applies to the target). Use "
                "rook_tools_read first to get the target's input schema. "
                "For hidden GH tools discovered by name, this invokes targets such as "
                "gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
                "and gh_snapshot through the normal policy path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact tool name to invoke."},
                    "arguments": {
                        "type": "object",
                        "description": "Arguments object matching the target tool's input schema.",
                    },
                },
                "required": ["name"],
            },
        ),
    )
```

Move the current descriptions and input schemas byte-for-byte in meaning from `server.py` into this builder. The literals above create fresh dictionaries on each call so no caller can mutate a later result. Keep the tuple in the existing MCP order shown above.

In `server.py`, import the builder and replace the four inline `Tool(...)` entries with:

```python
*build_mcp_capability_gateway_tools(),
```

Import `MCP_CAPABILITY_GATEWAY_NAMES` and define the existing `META_TOOL_NAMES` as that exact object or a direct alias. Do not retain a second four-name literal.

- [x] **Step 4: Run the schema tests and the current meta-tool suite**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_rook_tools_meta.py `
  mcp_server\tests\test_server_tool_profiles.py `
  mcp_server\tests\test_containment_catalogs.py `
  -q
```

Expected: all selected tests pass; no network or host call occurs.

- [x] **Step 5: Add valid-red tests for fixed scope, all profile intersections, ingress custody, and conversion**

Add table-driven tests around the not-yet-created executor:

```python
@pytest.mark.parametrize(
    ("tool_access", "mcp_profile", "effective"),
    [
        ("readonly", "full", server.Profile.READONLY),
        ("readonly", "lean", server.Profile.READONLY),
        ("readonly", "readonly", server.Profile.READONLY),
        ("full", "full", server.Profile.FULL),
        ("full", "lean", server.Profile.LEAN),
        ("full", "readonly", server.Profile.READONLY),
    ],
)
def test_scope_bound_executor_intersects_authority(
    monkeypatch, tool_access, mcp_profile, effective
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", mcp_profile)
    seen = []

    async def retained_handler(name, arguments, profile):
        seen.append((name, arguments, profile))
        return server._format_tool_result({
            "success": True,
            "data": {"effective": profile.value},
        })

    monkeypatch.setattr(server, "_handle_meta_tool", retained_handler)
    executor = server.build_mcp_capability_gateway_executor(tool_access)
    arguments = {"query": "component", "limit": 7}
    result = asyncio.run(executor("rook_tools_search", arguments))

    assert seen == [("rook_tools_search", arguments, effective)]
    assert result == {"effective": effective.value}


def test_invalid_mcp_profile_fails_before_handler_or_dispatch(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "invalid-profile")
    handler = AsyncMock()
    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_handle_meta_tool", handler)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)

    executor = server.build_mcp_capability_gateway_executor("full")
    result = asyncio.run(executor("rook_tools_search", {"query": "grid"}))

    assert result["success"] is False
    assert handler.await_count == 0
    assert dispatch.await_count == 0


def test_invalid_chatrunner_scope_refuses_at_factory():
    with pytest.raises(ValueError, match="tool_access"):
        server.build_mcp_capability_gateway_executor("lean")
```

Add a conversion regression that feeds the same `TextContent` success and failure values through the factored conversion used by `_mcp_tool_executor` and by the new executor. Assert equal plain agent values, not MCP object identity.

- [x] **Step 6: Run the executor tests and verify behavioral RED**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_rook_tools_meta.py `
  -k "scope_bound or invalid_mcp_profile or invalid_chatrunner_scope or agent_conversion" -q
```

Expected: tests fail because `build_mcp_capability_gateway_executor` and the shared conversion seam do not exist.

- [x] **Step 7: Factor the existing conversion and implement the executor without copying policy**

In `server.py`, extract the body that converts a completed MCP content list into the current JSON-decoded agent value under this exact name and behavior. Success data may decode to an object, array, scalar, or string; do not force a uniform envelope. Have `_mcp_tool_executor` call it:

```python
def _mcp_contents_to_agent_result(result: Any) -> Any:
    if isinstance(result, list) and result:
        content = result[0]
        text = getattr(content, "text", str(content))
        if text.startswith("Error: "):
            remainder = text[len("Error: "):]
            try:
                parsed = json.loads(remainder)
            except (json.JSONDecodeError, TypeError):
                return {"success": False, "data": remainder}
            return {"success": False, "data": parsed}
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"success": True, "data": text}
    return {"success": True, "data": str(result)}
```

Implement the authority function and factory:

```python
def _effective_mcp_gateway_profile(tool_access: str, active: Profile) -> Profile:
    if tool_access not in {"full", "readonly"}:
        raise ValueError("tool_access must be 'full' or 'readonly'")
    if tool_access == "readonly" or active is Profile.READONLY:
        return Profile.READONLY
    return active


def build_mcp_capability_gateway_executor(tool_access: str):
    if tool_access not in {"full", "readonly"}:
        raise ValueError("tool_access must be 'full' or 'readonly'")
    fixed_access = tool_access

    async def execute(tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            if tool_name not in MCP_CAPABILITY_GATEWAY_NAMES:
                raise ValueError(f"Unsupported MCP capability gateway tool: {tool_name}")
            active = resolve_profile(os.environ)
            effective = _effective_mcp_gateway_profile(fixed_access, active)
            contents = await _handle_meta_tool(tool_name, arguments, effective)
            return _mcp_contents_to_agent_result(contents)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return execute
```

The executor must pass `arguments` directly to `_handle_meta_tool`; do not copy, enrich, validate, or inspect target arguments in this factory. `_handle_meta_tool` and the target `call_tool()` remain authoritative.

- [x] **Step 8: Add the policy-path regressions required at the ownership gate**

Use the real `_handle_meta_tool` with patched no-contact target dispatch to prove:

- read-only discovery hides write targets under MCP full and lean;
- read-only `rook_tools_call` refuses a write target before `_call_tool_dispatch`;
- full plus lean preserves existing lean advertisement-only call behavior;
- recursion, contained targets, unknown targets, and non-object/malformed target arguments retain their current error codes;
- `gh_library` and `gh_batch_component_info` are discoverable/readable and reach patched dispatch exactly once; and
- the target observation is recorded once under the target name with origin `meta`.

Do not mock `_handle_meta_tool` in these policy tests. Patch only `_call_tool_dispatch`, routing, or the host-call boundary needed to guarantee zero external contact.

- [x] **Step 9: Run Task 1's complete seam**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_rook_tools_meta.py `
  mcp_server\tests\test_capability_index.py `
  mcp_server\tests\test_mcp_tool_profiles.py `
  mcp_server\tests\test_server_tool_profiles.py `
  mcp_server\tests\test_containment_execution.py `
  mcp_server\tests\test_containment_catalogs.py `
  mcp_server\tests\test_containment_agent_protocols.py `
  mcp_server\tests\test_multi_instance_targeting.py `
  -q
```

Expected: all selected tests pass with no external contact.

- [x] **Step 10: Commit Task 1**

```powershell
git add -- `
  mcp_server/src/rook/mcp_capability_gateway_contract.py `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_rook_tools_meta.py
git diff --cached --check
git commit -m "feat: expose scope-bound MCP capability gateway"
```

- [x] **Step 11: Mandatory independent ownership review — stop here**

Report exact production/test line growth, Task 1 test count, commit SHA, scope, and clean status. The reviewer must confirm before Task 2:

- one schema source;
- no second capability index or dispatch table;
- all six authority intersections;
- invalid-profile refusal before handler/dispatch;
- reuse of the existing conversion;
- existing policy and targeting ownership; and
- no ChatRunner wiring yet.

Do not begin Task 2 without explicit approval.

---

### Task 2: Conditionally Expose and Dispatch the Gateway in ChatRunner

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/capability_inventory.py`
- Create: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`
- Modify: `mcp_server/tests/test_rookchat_visible_dispatchability.py`

**Interfaces:**
- Consumes: `MCP_CAPABILITY_GATEWAY_NAMES`
- Consumes: `build_mcp_capability_gateway_tools()`
- Consumes: injected async executor `(name, arguments) -> plain agent result`
- Produces: `ChatRunner(..., mcp_capability_executor=None)` conditional surface
- Preserves: the existing direct `tool_executor`, registry meta-tools, event vocabulary, conversation messages, and model loop

- [x] **Step 1: Add valid-red conditional-exposure tests**

Create focused tests using the existing minimal `ToolRegistry` pattern:

```python
@pytest.fixture
def conversation():
    return Conversation(id="gateway_test", persona="worker", model="test-model")


@pytest.fixture
def minimal_registry():
    return ToolRegistry(
        catalog={
            "rhino_ping": {
                "type": "function",
                "function": {
                    "name": "rhino_ping",
                    "description": "Check Rhino connectivity.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
        },
        tier0={"rhino_ping", "request_tools", "search_tools"},
        agent_mode=True,
    )


def _schema_map(runner):
    return {
        schema["function"]["name"]: schema
        for schema in runner._get_active_tool_schemas()
    }


def test_bare_runner_does_not_advertise_canonical_gateway(minimal_registry):
    runner = ChatRunner(tool_executor=AsyncMock(), registry=minimal_registry)
    assert MCP_CAPABILITY_GATEWAY_NAMES.isdisjoint(_schema_map(runner))


def test_executor_presence_exposes_exact_normalized_canonical_schemas(minimal_registry):
    executor = AsyncMock()
    runner = ChatRunner(
        tool_executor=AsyncMock(),
        registry=minimal_registry,
        mcp_capability_executor=executor,
    )
    expected = build_catalog_from_mcp_tools(
        list(build_mcp_capability_gateway_tools())
    )
    actual = _schema_map(runner)
    assert {name: actual[name] for name in MCP_CAPABILITY_GATEWAY_NAMES} == expected


def test_gateway_exposure_does_not_change_existing_direct_schemas(minimal_registry):
    bare = ChatRunner(tool_executor=AsyncMock(), registry=minimal_registry)
    bridged = ChatRunner(
        tool_executor=AsyncMock(),
        registry=minimal_registry,
        mcp_capability_executor=AsyncMock(),
    )
    bare_map = _schema_map(bare)
    bridged_map = _schema_map(bridged)
    for name, schema in bare_map.items():
        assert bridged_map[name] == schema


def test_chatrunner_rejects_unknown_tool_access_before_surface_construction(minimal_registry):
    with pytest.raises(ValueError, match="tool_access"):
        ChatRunner(
            tool_executor=AsyncMock(),
            registry=minimal_registry,
            tool_access="lean",
            mcp_capability_executor=AsyncMock(),
        )
```

Include a custom injected registry that already marks one `rook_tools_*` schema active. With no executor, it must still be removed. With an executor, the canonical shared schema must replace it, producing exactly one visible schema per gateway name.

- [x] **Step 2: Run the exposure tests and verify behavioral RED**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  -k "advertise or exposes or direct_schemas" -q
```

Expected: tests fail because the constructor argument and `_get_active_tool_schemas()` do not exist.

- [x] **Step 3: Implement conditional schema projection without changing ToolRegistry**

Add the optional constructor argument and retain it:

```python
def __init__(
    self,
    tool_executor: Optional[Any] = None,
    tool_access: str = "full",
    registry: Optional[ToolRegistry] = None,
    mcp_capability_executor: Optional[Any] = None,
):
    if tool_access not in {"full", "readonly"}:
        raise ValueError("tool_access must be 'full' or 'readonly'")
    self._mcp_capability_executor = mcp_capability_executor
    self._mcp_capability_schemas = tuple(
        mcp_tool_to_litellm(tool)
        for tool in build_mcp_capability_gateway_tools()
    )
```

Implement one private projection used everywhere ChatRunner asks for active schemas:

```python
def _get_active_tool_schemas(self) -> list[dict[str, Any]]:
    by_name = {
        schema["function"]["name"]: schema
        for schema in self._registry.get_active_schemas()
    }
    for name in MCP_CAPABILITY_GATEWAY_NAMES:
        by_name.pop(name, None)
    if self._mcp_capability_executor is not None:
        for schema in self._mcp_capability_schemas:
            by_name[schema["function"]["name"]] = schema
    return [by_name[name] for name in sorted(by_name)]
```

Use this method in the model request, dynamic tool section, and final `active_tools` usage count. Do not mutate the caller-owned registry.

- [x] **Step 4: Add valid-red dispatch-loop tests**

Use the existing fake LiteLLM streaming helpers to issue one gateway call followed by a final text response:

```python
def _tool_response(name, arguments, call_id="gateway_call"):
    async def stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        tool_delta = MagicMock()
        tool_delta.index = 0
        tool_delta.id = call_id
        tool_delta.function.name = name
        tool_delta.function.arguments = json.dumps(arguments)
        chunk.choices[0].delta.tool_calls = [tool_delta]
        chunk.usage = None
        yield chunk
    return stream()


def _text_response(text):
    async def stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk
    return stream()


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        new=AsyncMock(return_value={
            "rhino": {"connected": True},
            "prompt": {"available": True},
            "verified_runtime_facts": [],
        }),
    )


@pytest.mark.asyncio
async def test_gateway_call_uses_only_injected_executor(conversation, minimal_registry):
    direct = AsyncMock()
    gateway = AsyncMock(return_value={"matches": [{"name": "gh_library"}]})
    runner = ChatRunner(
        tool_executor=direct,
        registry=minimal_registry,
        mcp_capability_executor=gateway,
    )
    responses = iter([
        _tool_response("rook_tools_search", {"query": "component"}),
        _text_response("Finished"),
    ])

    async def fake_acompletion(**kwargs):
        return next(responses)

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    gateway.assert_awaited_once_with("rook_tools_search", {"query": "component"})
    direct.assert_not_awaited()
    assert [event.type for event in events] == [
        "tool_start", "tool_result", "text_delta", "done"
    ]
    assert json.loads(next(
        event.result for event in events if event.type == "tool_result"
    )) == {"matches": [{"name": "gh_library"}]}
```

Add regressions proving:

- a hallucinated `rook_tools_call` with no executor never reaches the direct executor;
- `rook_tools_ls/search/read` count toward the existing meta-only limit;
- `rook_tools_call` is treated as an execution round;
- canonical exceptions retain current `str(exception)` behavior;
- no retry or alternate dispatch occurs; and
- the tool result is appended exactly once to conversation history.

- [x] **Step 5: Run the dispatch tests and verify behavioral RED**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  -k "uses_only or hallucinated or meta_only or exception or conversation" -q
```

Expected: tests fail because ChatRunner does not intercept the canonical names.

- [x] **Step 6: Implement the narrow ChatRunner intercept**

In the existing dispatch loop, keep `request_tools` / `search_tools` on `_handle_meta_tool`. For the canonical names, select the injected executor before the direct executor:

```python
if tool_name in MCP_CAPABILITY_GATEWAY_NAMES:
    if tool_name == "rook_tools_call":
        meta_only_round = False
    if self._mcp_capability_executor is None:
        result = {
            "success": False,
            "error": "Canonical MCP capability gateway is unavailable.",
        }
    else:
        result = await self._mcp_capability_executor(tool_name, params)
else:
    meta_only_round = False
    result = await self._tool_executor(tool_name, params)
```

Route both branches into the existing result serialization, conversation append, result view, and event emission. Do not run ChatRunner substrate extraction for the gateway wrapper name; the canonical target path already owns target observations and receipts.

For meta-only accounting, keep the round meta-only only when every tool call is one of:

```text
request_tools
search_tools
rook_tools_ls
rook_tools_search
rook_tools_read
```

- [x] **Step 7: Reconcile visible-dispatchability accounting from the shared names**

In `capability_inventory.py`, form the existing intercept set without another four-name literal:

```python
INTERCEPTED_META_TOOLS = frozenset({
    "request_tools",
    "search_tools",
    "ui_block",
    "list_chat_models",
    "set_chat_model",
}) | MCP_CAPABILITY_GATEWAY_NAMES
```

Update the visible-dispatchability test context to consume the production intercepted set or union the imported shared names. Do not classify the four tools as local, transformed, bridge-routed, or excluded.

- [x] **Step 8: Run Task 2's complete seam**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  mcp_server\tests\test_chat_runner.py `
  mcp_server\tests\test_rookchat_visible_dispatchability.py `
  mcp_server\tests\test_capability_inventory.py `
  mcp_server\tests\test_registry.py `
  -q
```

Expected: all selected tests pass; LiteLLM is fully mocked and no external contact occurs.

- [x] **Step 9: Commit Task 2 and stop for review**

```powershell
git add -- `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/src/rook/agent/capability_inventory.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py
git diff --cached --check
git commit -m "feat: expose canonical MCP gateway in ChatRunner"
```

Report the active-schema delta, direct-tool invariance, exact test count, source growth, and clean status. Obtain independent approval before production composition.

---

### Task 3: Compose the Real Gateway and Prove the No-Contact Product Vertical

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`
- Modify: `mcp_server/tests/test_chat_server.py` only if the existing singleton fixture requires explicit reset coverage

**Interfaces:**
- Consumes: `build_mcp_capability_gateway_executor("full")`
- Consumes: `ChatRunner(mcp_capability_executor=...)`
- Produces: default production Chat service runner with the canonical gateway enabled
- Preserves: injected runners passed to `create_chat_app()` and bare ChatRunner behavior

- [x] **Step 1: Add a valid-red production-composition test**

Test the default runner factory while avoiding service startup and all external calls:

```python
def test_default_chat_service_runner_receives_real_scope_bound_gateway(monkeypatch):
    executor = AsyncMock()
    factory = Mock(return_value=executor)
    monkeypatch.setattr(chat_server, "_runner", None)
    monkeypatch.setattr(server, "build_mcp_capability_gateway_executor", factory)

    runner = chat_server._get_runner()

    factory.assert_called_once_with("full")
    assert runner._mcp_capability_executor is executor
    assert MCP_CAPABILITY_GATEWAY_NAMES <= set(_schema_map(runner))
```

Patch the exact lazy import seam selected in implementation; do not import `rook.server` from `chat_runner.py`.

- [x] **Step 2: Run the composition test and verify behavioral RED**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  -k "default_chat_service_runner" -q
```

Expected: the default runner has no canonical executor.

- [x] **Step 3: Wire the executor only in the Chat service composition root**

Keep the import lazy and outside ChatRunner core:

```python
def _get_runner() -> ChatRunner:
    global _runner
    if _runner is None:
        from ...server import build_mcp_capability_gateway_executor

        tool_access = "full"
        _runner = ChatRunner(
            tool_access=tool_access,
            mcp_capability_executor=(
                build_mcp_capability_gateway_executor(tool_access)
            ),
        )
    return _runner
```

Do not change `create_chat_app(runner=...)`; injected test or alternate runners remain caller-owned.

- [x] **Step 4: Add a causal full-loop gateway vertical with only approved external boundaries faked**

Drive the real ChatRunner through this sequence:

```text
rook_tools_search("gh_library")
-> rook_tools_read("gh_library")
-> rook_tools_call("gh_library", exact arguments)
-> rook_tools_search("gh_batch_component_info")
-> rook_tools_read("gh_batch_component_info")
-> rook_tools_call("gh_batch_component_info", exact arguments)
-> final text
```

Use fake LiteLLM streaming only for the model boundary. Use the real shared schemas, capability index, scope-bound executor, `_handle_meta_tool`, target validation, and `call_tool()` path. Patch `_call_tool_dispatch` at the final no-contact target boundary and derive each fake target result from the actual received target name and arguments.

Assert:

```python
assert target_calls == [
    ("gh_library", {"search": "series", "limit": 5}),
    ("gh_batch_component_info", {"names": ["Series"]}),
]
assert direct_tool_executor.await_count == 0
tool_messages = [
    message for message in conversation.messages
    if message.get("role") == "tool"
]
assert [message["tool_call_id"] for message in tool_messages] == [
    "search_library",
    "read_library",
    "call_library",
    "search_batch_info",
    "read_batch_info",
    "call_batch_info",
]
assert [json.loads(message["content"]) for message in tool_messages] == expected_agent_results
assert final_event.type == "done"
```

Define `expected_agent_results` from the six exact causal fake responses before running the turn. The assertions must inspect exact message roles, tool-call IDs, and decoded results; they must not infer success from the final prose.

- [x] **Step 5: Add targeting and refusal verticals**

Add no-contact tests proving:

- gateway arguments equal the model-decoded object at canonical executor ingress;
- a Rhino-requiring target receives the canonical frozen port/document enrichment at `_call_tool_dispatch`;
- the model cannot add `tool_access`, `profile`, or an alternate executor scope;
- read-only plus MCP full and lean blocks a write target with zero target dispatch;
- full plus MCP readonly blocks the same target;
- invalid MCP profile produces one failed tool result with zero index/target dispatch;
- recursive, contained, unknown, and malformed calls return their current canonical errors; and
- gateway failure never falls back to ChatRunner's direct executor.

Use existing targeting result types and context managers. Do not invent a target fixture format or response wrapper.

- [x] **Step 6: Run Task 3's complete seam**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  mcp_server\tests\test_chat_runner.py `
  mcp_server\tests\test_chat_server.py `
  mcp_server\tests\test_rook_tools_meta.py `
  mcp_server\tests\test_server_tool_profiles.py `
  mcp_server\tests\test_multi_instance_targeting.py `
  -q -k "not TestKnowledgeGraphRoutes"
```

Expected: all selected non-knowledge tests pass. No model, host, or Worker contact occurs.

- [x] **Step 7: Commit Task 3 and stop for review**

```powershell
git add -- `
  mcp_server/src/rook/agent/chat/server.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py `
  mcp_server/tests/test_chat_server.py
git diff --cached --check
git commit -m "feat: compose MCP gateway into RookChat"
```

If `test_chat_server.py` was unchanged, omit it from `git add`. Report exact ingress arguments, target-dispatch arguments after canonical enrichment, profile matrix, call counts, and no-contact proof.

---

### Task 4: Final Verification and Plan Reconciliation

**Files:**
- Modify: `docs/superpowers/plans/2026-08-04-chatrunner-mcp-capability-parity-bridge.md`
- No production or test changes unless a prescribed regression exposes one concrete local defect; stop before fixing such a defect.

**Interfaces:**
- Consumes: all three reviewed implementation commits
- Produces: reproducible verification ledger and final reviewed branch

- [x] **Step 1: Run the focused ownership and ChatRunner seam**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  mcp_server\tests\test_rook_tools_meta.py `
  mcp_server\tests\test_chat_runner.py `
  mcp_server\tests\test_rookchat_visible_dispatchability.py `
  mcp_server\tests\test_capability_inventory.py `
  mcp_server\tests\test_registry.py `
  -q
```

Record the exact passing count and warnings.

- [x] **Step 2: Run the broader policy, containment, targeting, and Chat service seam**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_mcp_tool_profiles.py `
  mcp_server\tests\test_server_tool_profiles.py `
  mcp_server\tests\test_containment_execution.py `
  mcp_server\tests\test_containment_catalogs.py `
  mcp_server\tests\test_containment_agent_protocols.py `
  mcp_server\tests\test_multi_instance_targeting.py `
  mcp_server\tests\test_chat_server.py `
  mcp_server\tests\test_chat_integration.py `
  -q -k "not TestKnowledgeGraphRoutes"
```

Record the exact passing and deselected counts and warnings.

- [x] **Step 3: Reproduce the known broad baseline conditions**

Run this exact broad selected command, including both known failures and excluding only the unrelated knowledge-route class:

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server\tests\test_chat_runner.py `
  mcp_server\tests\test_chat_server.py `
  mcp_server\tests\test_chat_integration.py `
  mcp_server\tests\test_rookchat_visible_dispatchability.py `
  mcp_server\tests\test_rookchat_tool_schema_golden.py `
  mcp_server\tests\test_chatrunner_mcp_capability_gateway.py `
  mcp_server\tests\test_rook_tools_meta.py `
  mcp_server\tests\test_mcp_tool_profiles.py `
  mcp_server\tests\test_server_tool_profiles.py `
  mcp_server\tests\test_containment_execution.py `
  mcp_server\tests\test_containment_catalogs.py `
  mcp_server\tests\test_containment_agent_protocols.py `
  mcp_server\tests\test_multi_instance_targeting.py `
  -q -k "not TestKnowledgeGraphRoutes"
```

Require exactly these two failures and no others:

```text
test_local_catalog_rhino_execute_intent_schema_is_actionable
KeyError: 'rhino_execute_intent'

TestChatIntegration.test_full_conversation_flow
AssertionError: assert 'text_delta' in ['done']
```

No new failure is permitted. If either ID or signature changes, stop and report rather than touching unrelated schema-golden or stale integration-mock behavior.

- [x] **Step 4: Compile the touched Python modules**

```powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m py_compile `
  mcp_server\src\rook\mcp_capability_gateway_contract.py `
  mcp_server\src\rook\server.py `
  mcp_server\src\rook\agent\chat\chat_runner.py `
  mcp_server\src\rook\agent\chat\server.py `
  mcp_server\src\rook\agent\capability_inventory.py
```

Expected: exit `0` with no output.

- [x] **Step 5: Run source-surface and scope checks**

```powershell
rg -n "from .*server import|import rook\.server" `
  mcp_server/src/rook/agent/chat/chat_runner.py

git diff --name-only 8baf325a459ec9bb53cae24b1af0fab452b3001e...HEAD
git diff --check 8baf325a459ec9bb53cae24b1af0fab452b3001e...HEAD
git status --short
```

Expected:

- the import scan has zero matches;
- production scope is limited to the five mapped modules;
- test scope is limited to focused adjacent tests;
- specification and plan are the only documentation changes;
- no `tool_dispatcher.py` or `tool_groups.py` change exists;
- diff check is clean; and
- worktree is clean before ledger editing.

- [x] **Step 6: Reconcile this ledger with exact evidence**

Mark completed checkboxes and append:

- Task commit SHAs and approvals;
- exact focused and broader counts;
- the two unchanged broad-baseline failure IDs/signatures;
- compilation result;
- final scope;
- confirmation of zero external contact;
- confirmation that gateway schemas are conditional;
- confirmation that all profile intersections passed;
- confirmation that target arguments were canonical at ingress and canonically enriched at dispatch; and
- confirmation that no direct route, fallback, capability index, or result conversion was added.

- [x] **Step 7: Commit only the reconciled plan**

```powershell
git add -- docs/superpowers/plans/2026-08-04-chatrunner-mcp-capability-parity-bridge.md
git diff --cached --check
git commit -m "docs: reconcile ChatRunner MCP gateway plan"
git status --short --branch
```

Expected: clean worktree. Stop for independent final implementation review. Do not resume qualification, push, merge, deploy, or contact any external runtime.

## Verification Ledger

### Reviewed implementation commits

- Task 1: `4229571604aa59e6e43ec7c907cc3ed72428e964` (`feat: expose scope-bound MCP capability gateway`) — independently approved after **454 passed** with 11 pre-existing warnings.
- Task 2: `337f25f78a77cc0327fe6d013a8cb7b324141d3e` (`feat: expose canonical MCP gateway in ChatRunner`) plus bounded construction repair `bd520165918aeb42c34cdf92cc397d8b21b95cd1` (`fix: reject non-callable MCP gateway executors`) — independently approved after **105 passed** with 11 pre-existing warnings.
- Task 3: `b286d11ddbf0978b8fd391dcfe7e8ee8fa54a76e` (`feat: compose MCP gateway into RookChat`) — independently approved after **252 passed, 13 deselected**, with 18 existing warnings.

### Final verification evidence

- Focused ownership and ChatRunner seam: **166 passed**, 11 pre-existing DSPy warnings.
- Broader policy, containment, targeting, and Chat service seam: **456 passed, 1 known failure, 13 deselected**, with 18 existing warnings. The sole failure was the documented stale non-streaming Chat integration mock.
- Exact broad baseline: **596 passed, 2 known failures, 13 deselected**, with 18 existing warnings. The failures and signatures remained exactly:
  - `mcp_server/tests/test_rookchat_tool_schema_golden.py::test_local_catalog_rhino_execute_intent_schema_is_actionable` — `KeyError: 'rhino_execute_intent'`.
  - `mcp_server/tests/test_chat_integration.py::TestChatIntegration::test_full_conversation_flow` — `AssertionError: assert 'text_delta' in ['done']`.
- Touched-module compilation completed with exit `0` and no output.
- Complete branch diff check passed. ChatRunner core has zero `rook.server` imports and owns no capability index or target dispatch table.

### Final scope and ownership

- Documentation: this plan and `docs/superpowers/specs/2026-08-04-chatrunner-mcp-capability-parity-bridge-design.md` only.
- Production: `mcp_server/src/rook/mcp_capability_gateway_contract.py`, `mcp_server/src/rook/server.py`, `mcp_server/src/rook/agent/chat/chat_runner.py`, `mcp_server/src/rook/agent/chat/server.py`, and `mcp_server/src/rook/agent/capability_inventory.py` only.
- Tests: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`, `mcp_server/tests/test_rook_tools_meta.py`, `mcp_server/tests/test_capability_inventory.py`, and `mcp_server/tests/test_rookchat_visible_dispatchability.py` only.
- `ToolDispatcher`, tool groups, direct routes, existing `request_tools` / `search_tools`, public MCP result wires, and exception stringification remain unchanged.
- The four gateway schemas are visible only when a callable canonical executor is supplied. Invalid executor construction refuses before schema construction.
- All six fixed ChatRunner/MCP profile intersections passed, including `lean`; invalid MCP profiles refused before capability-index or target-dispatch entry.
- Model-decoded gateway arguments reached canonical-executor ingress exactly. Existing canonical targeting then enriched target dispatch with the frozen Rhino port, process, and document context.
- Gateway calls did not fall back to direct dispatch. No duplicate capability catalog, policy allowlist, target dispatcher, direct route, result conversion, receipt system, or generalized client framework was added.
- Development and review made zero provider, Ollama, Worker, Rhino, Grasshopper, readiness, or mutation contact.

## Anti-Quagmire Stop

Stop and return for scope review if implementation requires any of the following:

- changing `ToolDispatcher` or adding individual direct tool routes;
- changing `ToolRegistry` semantics or adding a second registry;
- copying profile allowlists, target schemas, capability records, or dispatch cases into ChatRunner;
- importing `rook.server` from ChatRunner core;
- changing the MCP public result wire format;
- changing existing exception text behavior;
- adding a generalized capability client, provider abstraction, scheduler, skill loader, or runtime framework;
- changing more production modules than the five mapped above; or
- contacting a model, Worker, Rhino, or Grasshopper.

If a test reveals an existing product defect outside this bridge, preserve the valid-red evidence and stop before patching it.
