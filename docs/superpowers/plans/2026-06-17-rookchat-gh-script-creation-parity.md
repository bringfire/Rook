# RookChat GH Script Creation Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RookChat panel's direct dispatcher able to execute the `gh_create_script`, `gh_create_python_script`, and `gh_create_csharp_script` tools it already advertises to agents.

**Architecture:** Add thin local dispatcher wrappers that delegate to the existing `server._execute_gh_create_script` helper, preserving unified and alias semantics. Add typed ChatRunner local schemas beside the existing `_GH_UPDATE_SCRIPT_SCHEMA` so fallback/local catalogs give models the same required fields as the MCP/server surface.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, Rook MCP server modules under `mcp_server/src/rook`.

---

## Branch And Hygiene

- Current branch should be `codex/rookchat-gh-script-creation-parity`.
- Before execution, run `git fetch origin` and compare `origin/main`; if it moved, pause and rebase/merge only after reviewing overlap.
- Do not stage or revert:
  - `knowledge/contextual_mab.pkl`
  - `knowledge/substrate_observations.jsonl`
- No Rhino, native, deploy, Workbench, launcher, session-topology, prompt-behavior, or `.vcxproj` changes in this slice.

## File Map

- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add local wrappers for the three `gh_create_*` tools.
  - Register them from `build_local_tools()`.
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Add typed local catalog schemas for the three `gh_create_*` tools.
  - Teach `_build_local_tool_catalog()` to use those schemas.
- Create: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
  - Focused non-live tests for dispatcher reachability and schema parity.

## Task 1: Dispatcher Reachability Tests

**Files:**
- Create: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Read: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Read: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Write failing dispatcher tests**

Create `mcp_server/tests/test_rookchat_gh_script_creation_parity.py` with this initial content:

```python
import pytest


def test_build_local_tools_registers_script_creation_tools():
    from rook.agent.tool_dispatcher import build_local_tools

    local_tools = build_local_tools()

    assert "gh_create_script" in local_tools
    assert "gh_create_python_script" in local_tools
    assert "gh_create_csharp_script" in local_tools


@pytest.mark.asyncio
async def test_dispatcher_unified_gh_create_script_reaches_server_helper(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(
            {
                "language": language,
                "arguments": dict(arguments),
                "port": port,
                "tool_name": tool_name,
            }
        )
        return {
            "success": True,
            "data": {
                "component_guid": "script-guid",
                "name": "Script",
                "pins_in": arguments.get("pins_in", []),
                "pins_out": arguments.get("pins_out", []),
            },
        }

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9876, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "A = 1;",
            "pins_in": [],
            "pins_out": ["A:int"],
            "name": "Unified C#",
        },
    )

    assert result["success"] is True
    assert calls == [
        {
            "language": "csharp",
            "arguments": {
                "language": "csharp",
                "code": "A = 1;",
                "pins_in": [],
                "pins_out": ["A:int"],
                "name": "Unified C#",
            },
            "port": 9876,
            "tool_name": "gh_create_script",
        }
    ]


@pytest.mark.parametrize(
    ("tool_name", "expected_language"),
    [
        ("gh_create_python_script", "python"),
        ("gh_create_csharp_script", "csharp"),
    ],
)
@pytest.mark.asyncio
async def test_dispatcher_aliases_force_language_and_preserve_tool_name(
    monkeypatch,
    tool_name,
    expected_language,
):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(
            {
                "language": language,
                "arguments": dict(arguments),
                "port": port,
                "tool_name": tool_name,
            }
        )
        return {"success": True, "data": {"component_guid": f"{language}-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        tool_name,
        {
            "code": "A = 1;",
            "pins_in": ["R:double"],
            "pins_out": ["A:int"],
            "name": "Alias Script",
        },
    )

    assert result["success"] is True
    assert calls == [
        {
            "language": expected_language,
            "arguments": {
                "code": "A = 1;",
                "pins_in": ["R:double"],
                "pins_out": ["A:int"],
                "name": "Alias Script",
            },
            "port": 9877,
            "tool_name": tool_name,
        }
    ]
```

The alias calls deliberately pass `pins_in` and `pins_out` so the tests verify routing and `tool_name` semantics instead of tripping schema/input-validation behavior.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: failures showing the tools are missing from `build_local_tools()` or dispatch returns the unknown-tool path.

- [ ] **Step 3: Commit checkpoint is not allowed yet**

Do not commit red tests alone unless the execution process explicitly wants red-test commits. Continue to Task 2.

## Task 2: Local Dispatcher Wrappers

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Test: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Add local wrappers**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, place these wrappers next to `_local_gh_update_script` and `_local_gh_set_script_pins`:

```python
async def _local_gh_create_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    return await _execute_gh_create_script(
        kwargs.get("language"),
        kwargs,
        port,
        tool_name="gh_create_script",
    )


async def _local_gh_create_python_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    return await _execute_gh_create_script(
        "python",
        kwargs,
        port,
        tool_name="gh_create_python_script",
    )


async def _local_gh_create_csharp_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_create_script

    return await _execute_gh_create_script(
        "csharp",
        kwargs,
        port,
        tool_name="gh_create_csharp_script",
    )
```

- [ ] **Step 2: Register the wrappers**

In `build_local_tools()`, immediately beside the existing script registrations:

```python
    tools["gh_create_script"] = _local_gh_create_script
    tools["gh_create_python_script"] = _local_gh_create_python_script
    tools["gh_create_csharp_script"] = _local_gh_create_csharp_script
    tools["gh_update_script"] = _local_gh_update_script
    tools["gh_set_script_pins"] = _local_gh_set_script_pins
```

- [ ] **Step 3: Run focused dispatcher tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: dispatcher tests pass, unless later schema tests have already been added and are still red.

- [ ] **Step 4: Commit dispatcher change**

If the dispatcher tests pass:

```powershell
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py
git commit -m "fix(agent): expose gh script creation to chat dispatcher"
```

Confirm `git status --short` still shows only the known `knowledge/*` runtime files outside tracked task files.

## Task 3: ChatRunner Local Schema Tests

**Files:**
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Read: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Read: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add local-catalog schema tests**

Append these tests to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
def _local_tool_schema(tool_name):
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({tool_name: object()})
    return catalog[tool_name]["function"]["parameters"]


def test_local_catalog_schema_for_unified_create_script_matches_server_contract():
    schema = _local_tool_schema("gh_create_script")

    assert schema["required"] == ["language", "code"]
    assert schema["properties"]["language"]["enum"] == ["python", "csharp"]
    assert "pins_in" in schema["properties"]
    assert "pins_out" in schema["properties"]
    assert schema.get("additionalProperties") is not True


@pytest.mark.parametrize("tool_name", ["gh_create_python_script", "gh_create_csharp_script"])
def test_local_catalog_schema_for_create_aliases_matches_server_required_fields(tool_name):
    schema = _local_tool_schema(tool_name)

    assert schema["required"] == ["code", "pins_in", "pins_out"]
    assert "language" not in schema["properties"]
    assert "name" in schema["properties"]
    assert "x" in schema["properties"]
    assert "y" in schema["properties"]
    assert schema.get("additionalProperties") is not True


@pytest.mark.asyncio
async def test_local_create_script_required_fields_match_mcp_server_schemas():
    from rook import server
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    local_catalog = _build_local_tool_catalog(
        {
            "gh_create_script": object(),
            "gh_create_python_script": object(),
            "gh_create_csharp_script": object(),
        }
    )
    mcp_tools = {tool.name: tool for tool in await server.list_tools()}

    for tool_name in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    ):
        local_schema = local_catalog[tool_name]["function"]["parameters"]
        server_schema = mcp_tools[tool_name].inputSchema
        assert local_schema["required"] == server_schema["required"]

    local_language = local_catalog["gh_create_script"]["function"]["parameters"]["properties"]["language"]
    server_language = mcp_tools["gh_create_script"].inputSchema["properties"]["language"]
    assert local_language["enum"] == server_language["enum"]
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: schema tests fail because `_build_local_tool_catalog()` still emits generic open schemas for the create tools.

## Task 4: ChatRunner Local Schemas

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Test: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Add shared pin-array schema and create schemas**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, add these constants after `_GH_UPDATE_SCRIPT_SCHEMA`:

```python
_GH_SCRIPT_PIN_ARRAY_SCHEMA: dict = {
    "type": "array",
    "items": {
        "oneOf": [
            {"type": "string"},
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "access": {
                        "type": "string",
                        "enum": ["item", "list", "tree"],
                    },
                    "optional": {"type": "boolean"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": True,
            },
        ]
    },
}


def _gh_create_script_schema(
    name: str,
    description: str,
    *,
    required: list[str],
    include_language: bool,
) -> dict:
    properties: dict = {
        "code": {
            "type": "string",
            "description": "Script source code for the script component.",
        },
        "pins_in": {
            **_GH_SCRIPT_PIN_ARRAY_SCHEMA,
            "description": 'Input pin definitions as "Name:Type" strings or pin objects.',
        },
        "pins_out": {
            **_GH_SCRIPT_PIN_ARRAY_SCHEMA,
            "description": 'Output pin definitions as "Name:Type" strings or pin objects.',
        },
        "name": {
            "type": "string",
            "description": "Display name for the component.",
        },
        "x": {
            "type": "number",
            "description": "Canvas X position.",
        },
        "y": {
            "type": "number",
            "description": "Canvas Y position.",
        },
    }
    if include_language:
        properties = {
            "language": {
                "type": "string",
                "enum": ["python", "csharp"],
                "description": "Script language: python or csharp.",
            },
            **properties,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_GH_CREATE_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_script",
        "Create a Python 3 or C# Script component with pins and code.",
    ),
    required=["language", "code"],
    include_language=True,
)

_GH_CREATE_PYTHON_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_python_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_python_script",
        'Alias for gh_create_script(language="python").',
    ),
    required=["code", "pins_in", "pins_out"],
    include_language=False,
)

_GH_CREATE_CSHARP_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_csharp_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_csharp_script",
        'Alias for gh_create_script(language="csharp").',
    ),
    required=["code", "pins_in", "pins_out"],
    include_language=False,
)

_GH_CREATE_SCRIPT_SCHEMAS: Dict[str, dict] = {
    "gh_create_script": _GH_CREATE_SCRIPT_SCHEMA,
    "gh_create_python_script": _GH_CREATE_PYTHON_SCRIPT_SCHEMA,
    "gh_create_csharp_script": _GH_CREATE_CSHARP_SCRIPT_SCHEMA,
}
```

- [ ] **Step 2: Use create schemas in `_build_local_tool_catalog()`**

In `_build_local_tool_catalog()`, add this branch immediately after the `gh_update_script` branch:

```python
        if name in _GH_CREATE_SCRIPT_SCHEMAS:
            catalog[name] = _GH_CREATE_SCRIPT_SCHEMAS[name]
            continue
```

- [ ] **Step 3: Run schema tests**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: all tests in the new file pass.

- [ ] **Step 4: Commit schema change**

```powershell
git add mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py
git commit -m "fix(agent): add gh create script chat schemas"
```

Confirm `git status --short` still shows only the known `knowledge/*` runtime files outside tracked task files.

## Task 5: Tool-Group Dispatchability Guard

**Files:**
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Read: `mcp_server/src/rook/agent/tool_groups.py`
- Read: `mcp_server/src/rook/agent/tool_dispatcher.py`

- [ ] **Step 1: Add dispatchability guard**

Append this test to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
def test_gh_canvas_script_create_tools_are_dispatcher_reachable():
    from rook.agent.tool_dispatcher import BRIDGE_ROUTES, TRANSFORM_FUNCTIONS, build_local_tools
    from rook.agent.tool_groups import TOOL_GROUPS

    local_tools = build_local_tools()
    dispatchable = set(local_tools) | set(TRANSFORM_FUNCTIONS) | set(BRIDGE_ROUTES)
    script_create_tools = {
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    }

    assert script_create_tools <= set(TOOL_GROUPS["gh_canvas"])
    assert script_create_tools <= dispatchable
```

- [ ] **Step 2: Run the new guard**

Run:

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py::test_gh_canvas_script_create_tools_are_dispatcher_reachable -q
```

Expected: pass.

- [ ] **Step 3: Commit guard**

```powershell
git add mcp_server/tests/test_rookchat_gh_script_creation_parity.py
git commit -m "test(agent): guard gh script creation dispatch parity"
```

## Task 6: Focused Verification

**Files:**
- No new source edits expected.

- [ ] **Step 1: Run focused parity tests**

```powershell
cd mcp_server
python -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: all tests in the new file pass.

- [ ] **Step 2: Run existing script contract tests**

```powershell
cd mcp_server
python -m pytest tests/test_server_contract_hardening.py -k "gh_create_script or gh_create_python_script or gh_create_csharp_script" -q
```

Expected: pass.

- [ ] **Step 3: Run prompt/catalog regression tests**

```powershell
cd mcp_server
python -m pytest tests/test_chat_prompt_builder.py -q
```

Expected: pass.

- [ ] **Step 4: Run diff whitespace check**

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 5: Final branch status**

```powershell
git status --short --branch
```

Expected: only the known unstaged runtime artifacts remain outside committed work:

```text
 M knowledge/contextual_mab.pkl
 M knowledge/substrate_observations.jsonl
```

Do not claim live Rhino verification. This slice exposes an existing server helper to RookChat and is verified with non-live tests.

## Self-Review Notes

- Spec coverage: dispatcher wrappers are covered by Tasks 1-2; local schema parity by Tasks 3-4; prompt/tool-group/catalog/dispatcher consistency by Task 5 and verification; non-goals are preserved.
- Red-flag scan: no open-ended implementation gaps are intentionally left in this plan.
- Type consistency: wrapper names, tool names, schema required fields, and test expectations match the approved spec and current server MCP schemas.
