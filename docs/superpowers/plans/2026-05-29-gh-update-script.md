# GH Update Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gh_update_script` as the default agent-facing source edit tool for existing Grasshopper script components while keeping `gh_set_script` as the raw source escape hatch.

**Architecture:** Implement the feature entirely in the Python MCP layer (`mcp_server/src/rook/server.py`) by orchestrating existing `/gh/script`, `/gh/component`, and `/gh/errors` routes. Reuse the existing script pin conversion, C# wrapper, and Python preamble/postamble helpers from the create path. Update agent prompts/tool groups so normal script edits route to `gh_update_script`, with tests that prevent future prompt drift back to `gh_set_script`.

**Tech Stack:** Python 3 MCP server, pytest/pytest-asyncio tests, existing Rook Grasshopper companion HTTP routes, Markdown persona prompts.

---

## File Map

- Modify: `mcp_server/src/rook/server.py`
  - Add runtime classification helpers for the exact `/gh/script` type values.
  - Add source preparation helpers for `body`, `full_source`, and `auto`.
  - Add component/canvas error summarization for `/gh/errors`.
  - Register `gh_update_script` in `list_tools()`.
  - Dispatch `gh_update_script` in `call_tool()`.

- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add a local agent tool wrapper that delegates to `server._execute_gh_update_script`.
  - Keep `gh_set_script` available as raw source read/write.

- Modify: `mcp_server/src/rook/agent/tool_groups.py`
  - Include `gh_update_script` in the `gh_canvas` group.

- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Add a concise description for `gh_update_script`.
  - Reword `gh_set_script` as raw source read/write, not normal edit.

- Modify: `mcp_server/src/rook/agent/personas/scripter/role.md`
  - Make `gh_update_script` the normal existing-script edit path.
  - Document the two-step signature flow: `gh_set_script_pins`, then `gh_update_script`.
  - Keep `gh_set_script` as raw read/write and GH1 C# escape hatch.

- Modify: `mcp_server/src/rook/agent/personas/worker/role.md`
  - Update tool list and script-component gotcha guidance.

- Modify: `mcp_server/src/rook/agent/personas/architect/role.md`
  - Update tool list and script-component gotcha guidance.

- Modify: `mcp_server/src/rook/agent/prompts/WORKER.md`
  - Update display snapshot guidance so it matches runtime personas.

- Modify: `mcp_server/tests/test_server_contract_hardening.py`
  - Add MCP schema/dispatch/source-preparation/error-summary contract tests.

- Modify: `mcp_server/tests/test_chat_prompt_builder.py`
  - Add persona prompt drift tests for `gh_update_script` as the default edit path.

- Optional live validation: `mcp_server/tests/test_gh_update_script_live.py`
  - Add marked `requires_rhino` tests only after the mocked contract tests pass.

---

### Task 1: Add Contract Tests For Tool Registration And Runtime Classification

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add failing schema and runtime tests**

Append this block near the existing `gh_create_script` contract tests after the alias/error-prefix tests:

```python
# ---------- gh_update_script — source update tool contract ----------


@pytest.mark.asyncio
async def test_gh_update_script_input_schema_and_description():
    tools = {tool.name: tool for tool in await server.list_tools()}
    tool = tools.get("gh_update_script")

    assert tool is not None, "gh_update_script tool missing from registered tools"
    props = tool.inputSchema["properties"]
    required = tool.inputSchema["required"]

    assert required == ["guid", "code"]
    assert props["mode"]["enum"] == ["auto", "body", "full_source"]
    assert props["language"]["enum"] == ["auto", "python", "csharp"]
    assert props["check_errors"]["default"] is True
    assert props["python_preamble"]["default"] is True

    desc = tool.description
    assert "normal source edits" in desc
    assert "gh_set_script_pins" in desc
    assert "raw source" in desc


@pytest.mark.parametrize(
    ("script_type", "expected_runtime", "expected_language", "supports_update"),
    [
        ("Python3Component", "RhinoCode Python 3", "python", True),
        ("GhPythonComponent", "GH1 legacy Python", "python", True),
        ("CSharpScriptComponent", "RhinoCode C#", "csharp", True),
        ("Component_CSNET_Script", "GH1 legacy C#/.NET Script", "csharp", False),
    ],
)
def test_gh_update_script_runtime_classifier_exact_script_types(
    script_type,
    expected_runtime,
    expected_language,
    supports_update,
):
    runtime = server._classify_gh_update_script_runtime(
        {"Type": script_type},
        {"type": "snapshot-display-label"},
        "auto",
    )

    assert runtime["script_type"] == script_type
    assert runtime["detected_runtime"] == expected_runtime
    assert runtime["detected_language"] == expected_language
    assert runtime["supports_update"] is supports_update


def test_gh_update_script_runtime_classifier_language_mismatch_fails():
    with pytest.raises(ValueError, match="language.*csharp.*python"):
        server._classify_gh_update_script_runtime(
            {"Type": "CSharpScriptComponent"},
            {},
            "python",
        )


def test_gh_update_script_runtime_classifier_does_not_trust_snapshot_label():
    with pytest.raises(ValueError, match="Unsupported script component runtime"):
        server._classify_gh_update_script_runtime(
            {"Type": "UnknownComponent"},
            {"type": "CSharpComponent"},
            "auto",
        )
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_input_schema_and_description or gh_update_script_runtime_classifier" -q
Pop-Location
```

Expected: failures naming missing `gh_update_script` and missing `_classify_gh_update_script_runtime`.

- [ ] **Step 3: Implement runtime constants and classifier**

In `mcp_server/src/rook/server.py`, add this near `_GH_SCRIPT_LANGUAGE_CONFIGS`:

```python
_GH_UPDATE_SCRIPT_MODES: tuple[str, ...] = ("auto", "body", "full_source")
_GH_UPDATE_SCRIPT_LANGUAGES: tuple[str, ...] = ("auto", "python", "csharp")

_GH_UPDATE_SCRIPT_RUNTIME_BY_TYPE: dict[str, dict[str, Any]] = {
    "Python3Component": {
        "detected_runtime": "RhinoCode Python 3",
        "detected_language": "python",
        "supports_update": True,
        "legacy": False,
    },
    "GhPythonComponent": {
        "detected_runtime": "GH1 legacy Python",
        "detected_language": "python",
        "supports_update": True,
        "legacy": True,
    },
    "CSharpScriptComponent": {
        "detected_runtime": "RhinoCode C#",
        "detected_language": "csharp",
        "supports_update": True,
        "legacy": False,
    },
    "Component_CSNET_Script": {
        "detected_runtime": "GH1 legacy C#/.NET Script",
        "detected_language": "csharp",
        "supports_update": False,
        "legacy": True,
    },
}
```

Then add these helpers below that block:

```python
def _gh_case_get(data: dict[str, Any] | None, *names: str) -> Any:
    if not isinstance(data, dict):
        return None
    for name in names:
        if name in data:
            return data[name]
    lowered = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def _classify_gh_update_script_runtime(
    script_data: dict[str, Any] | None,
    component_data: dict[str, Any] | None,
    requested_language: Any = "auto",
) -> dict[str, Any]:
    script_type = _gh_case_get(script_data, "Type", "type")
    if not isinstance(script_type, str) or not script_type.strip():
        script_type = _gh_case_get(component_data, "Type", "type")
    if not isinstance(script_type, str) or not script_type.strip():
        raise ValueError("Unsupported script component runtime: missing /gh/script Type")

    script_type = script_type.strip()
    runtime = _GH_UPDATE_SCRIPT_RUNTIME_BY_TYPE.get(script_type)
    if runtime is None:
        raise ValueError(
            f"Unsupported script component runtime: {script_type}. "
            "Use raw gh_set_script for exact source if this component supports it."
        )

    requested = "auto" if requested_language in (None, "") else str(requested_language).strip().lower()
    if requested not in _GH_UPDATE_SCRIPT_LANGUAGES:
        raise ValueError(
            f"Invalid language {requested_language!r}. Choose 'auto', 'python', or 'csharp'."
        )
    detected_language = runtime["detected_language"]
    if requested != "auto" and requested != detected_language:
        raise ValueError(
            f"Requested language {requested!r} conflicts with detected language "
            f"{detected_language!r} for {script_type}."
        )

    return {"script_type": script_type, **runtime}
```

- [ ] **Step 4: Register the tool schema**

In `list_tools()` in `mcp_server/src/rook/server.py`, insert a `Tool(...)` after `gh_set_script`:

```python
Tool(
    name="gh_update_script",
    description="""Update source code on an existing Grasshopper script component.

Use this for normal source edits. It reads the component runtime and current
pins, prepares the source, writes it through the existing /gh/script route, and
checks /gh/errors by default.

For RhinoCode C#, body code is wrapped using current pins. For signature
changes, call gh_set_script_pins first, then retry gh_update_script. Use
gh_set_script only for raw source read/write, unsupported GH1 C# exact source,
or advanced escape-hatch workflows.""",
    inputSchema={
        "type": "object",
        "properties": {
            "guid": {
                "type": "string",
                "description": "Component instance GUID or short ID (C1, C2...) from gh_snapshot",
            },
            "code": {
                "type": "string",
                "description": "Body code or full source depending on mode",
            },
            "mode": {
                "type": "string",
                "enum": list(_GH_UPDATE_SCRIPT_MODES),
                "default": "auto",
                "description": "auto, body, or full_source. Default auto.",
            },
            "language": {
                "type": "string",
                "enum": list(_GH_UPDATE_SCRIPT_LANGUAGES),
                "default": "auto",
                "description": "Optional validator for detected runtime; does not override detection.",
            },
            "python_preamble": {
                "type": "boolean",
                "default": True,
                "description": "For RhinoCode Python 3 body-like source, add generated Rook preamble/postamble when not already present.",
            },
            "check_errors": {
                "type": "boolean",
                "default": True,
                "description": "Check /gh/errors after writing source and report component plus unrelated canvas diagnostics.",
            },
        },
        "required": ["guid", "code"],
    },
),
```

- [ ] **Step 5: Run the tests and commit**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_input_schema_and_description or gh_update_script_runtime_classifier" -q
Pop-Location
```

Expected: the schema/classifier tests pass.

Commit:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "test: cover gh_update_script schema and runtime classification"
```

---

### Task 2: Add Source Preparation Tests And Helpers

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add failing source preparation tests**

Append these tests below the runtime classifier tests:

```python
def test_gh_update_script_csharp_body_wraps_with_current_pins_and_skips_out():
    prepared = server._prepare_gh_update_script_source(
        code="var r = Convert.ToDouble(R);\nA = r * 2;",
        mode="body",
        runtime={
            "script_type": "CSharpScriptComponent",
            "detected_runtime": "RhinoCode C#",
            "detected_language": "csharp",
            "supports_update": True,
            "legacy": False,
        },
        inputs=[{"name": "R", "type": "double"}],
        outputs=[{"name": "A", "type": "double"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "body"
    assert prepared["wrapped"] is True
    assert "class Script_Instance" in prepared["source"]
    assert "private void RunScript(object R, ref object A)" in prepared["source"]
    assert "ref object out" not in prepared["source"]


def test_gh_update_script_csharp_auto_full_source_passes_through():
    full = "public class Script_Instance : GH_ScriptInstance { void RunScript() {} }"
    prepared = server._prepare_gh_update_script_source(
        code=full,
        mode="auto",
        runtime={
            "script_type": "CSharpScriptComponent",
            "detected_runtime": "RhinoCode C#",
            "detected_language": "csharp",
            "supports_update": True,
            "legacy": False,
        },
        inputs=[],
        outputs=[],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "full_source"
    assert prepared["wrapped"] is False
    assert prepared["source"] == full


def test_gh_update_script_python_full_source_never_adds_generated_blocks():
    source = "A = R"
    prepared = server._prepare_gh_update_script_source(
        code=source,
        mode="full_source",
        runtime={
            "script_type": "Python3Component",
            "detected_runtime": "RhinoCode Python 3",
            "detected_language": "python",
            "supports_update": True,
            "legacy": False,
        },
        inputs=[{"name": "R", "type": "double"}],
        outputs=[{"name": "A", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "full_source"
    assert prepared["wrapped"] is False
    assert prepared["source"] == source
    assert "Auto-generated GH input coercion" not in prepared["source"]
    assert "Auto-generated GH output coercion" not in prepared["source"]


def test_gh_update_script_python_body_adds_generated_blocks_once():
    prepared = server._prepare_gh_update_script_source(
        code="Points = [rg.Point3d(0, 0, 0)]",
        mode="body",
        runtime={
            "script_type": "Python3Component",
            "detected_runtime": "RhinoCode Python 3",
            "detected_language": "python",
            "supports_update": True,
            "legacy": False,
        },
        inputs=[{"name": "R", "type": "double"}],
        outputs=[{"name": "Points", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "body"
    assert prepared["wrapped"] is True
    assert prepared["source"].count("Auto-generated GH input coercion") == 1
    assert prepared["source"].count("Auto-generated GH output coercion") == 1


def test_gh_update_script_python_existing_sentinels_prevent_duplication():
    source = (
        "# ── Auto-generated GH input coercion (do not edit) ──────────\n"
        "R = 1\n"
        "# ── Auto-generated GH output coercion (do not edit) ─────────\n"
        "A = R\n"
    )
    prepared = server._prepare_gh_update_script_source(
        code=source,
        mode="auto",
        runtime={
            "script_type": "Python3Component",
            "detected_runtime": "RhinoCode Python 3",
            "detected_language": "python",
            "supports_update": True,
            "legacy": False,
        },
        inputs=[{"name": "R", "type": "double"}],
        outputs=[{"name": "A", "type": "Point3d", "access": "list"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "body"
    assert prepared["source"].count("Auto-generated GH input coercion") == 1
    assert prepared["source"].count("Auto-generated GH output coercion") == 1


def test_gh_update_script_gh1_python_is_raw_direct():
    prepared = server._prepare_gh_update_script_source(
        code="a = x",
        mode="auto",
        runtime={
            "script_type": "GhPythonComponent",
            "detected_runtime": "GH1 legacy Python",
            "detected_language": "python",
            "supports_update": True,
            "legacy": True,
        },
        inputs=[{"name": "x", "type": "double"}],
        outputs=[{"name": "a", "type": "double"}],
        python_preamble=True,
    )

    assert prepared["mode_used"] == "full_source"
    assert prepared["wrapped"] is False
    assert prepared["source"] == "a = x"


def test_gh_update_script_gh1_csharp_fails_closed_all_modes():
    runtime = {
        "script_type": "Component_CSNET_Script",
        "detected_runtime": "GH1 legacy C#/.NET Script",
        "detected_language": "csharp",
        "supports_update": False,
        "legacy": True,
    }

    for mode in ("auto", "body", "full_source"):
        with pytest.raises(ValueError, match="gh_set_script"):
            server._prepare_gh_update_script_source(
                code="A = R;",
                mode=mode,
                runtime=runtime,
                inputs=[],
                outputs=[],
                python_preamble=True,
            )
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_csharp or gh_update_script_python or gh_update_script_gh1" -q
Pop-Location
```

Expected: failures naming missing `_prepare_gh_update_script_source`.

- [ ] **Step 3: Implement source preparation helpers**

In `mcp_server/src/rook/server.py`, below `_classify_gh_update_script_runtime`, add:

```python
_GH_PYTHON_INPUT_SENTINEL = "# ── Auto-generated GH input coercion"
_GH_PYTHON_OUTPUT_SENTINEL = "# ── Auto-generated GH output coercion"


def _gh_is_full_csharp_source(code: str) -> bool:
    return "class Script_Instance" in code or "void RunScript" in code


def _normalize_gh_update_mode(mode: Any) -> str:
    normalized = "auto" if mode in (None, "") else str(mode).strip().lower()
    if normalized not in _GH_UPDATE_SCRIPT_MODES:
        raise ValueError("Invalid mode. Choose 'auto', 'body', or 'full_source'.")
    return normalized


def _prepare_gh_update_script_source(
    *,
    code: str,
    mode: Any,
    runtime: dict[str, Any],
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    python_preamble: bool,
) -> dict[str, Any]:
    if not isinstance(code, str) or not code:
        raise ValueError("Missing required parameter: code")

    mode = _normalize_gh_update_mode(mode)
    language = runtime["detected_language"]
    script_type = runtime["script_type"]

    if not runtime.get("supports_update", False):
        raise ValueError(
            f"{script_type} is not supported by gh_update_script v1. "
            "Use raw gh_set_script with exact source."
        )

    if script_type == "GhPythonComponent":
        return {
            "source": code,
            "mode_used": "full_source",
            "wrapped": False,
        }

    if language == "csharp":
        if mode == "full_source":
            if not _gh_is_full_csharp_source(code):
                raise ValueError(
                    "mode='full_source' for RhinoCode C# requires a full "
                    "Script_Instance or RunScript source. Use mode='body' for body code."
                )
            return {"source": code, "mode_used": "full_source", "wrapped": False}

        is_full = _gh_is_full_csharp_source(code)
        if mode == "auto" and is_full:
            return {"source": code, "mode_used": "full_source", "wrapped": False}

        if mode in ("auto", "body"):
            return {
                "source": _build_gh_csharp_wrapper(code, inputs, outputs),
                "mode_used": "body",
                "wrapped": True,
            }

    if language == "python":
        if mode == "full_source":
            return {"source": code, "mode_used": "full_source", "wrapped": False}

        if script_type == "Python3Component":
            source = code
            wrapped = False
            if python_preamble:
                if _GH_PYTHON_INPUT_SENTINEL not in source:
                    preamble = _build_gh_python_preamble(inputs)
                    if preamble:
                        source = preamble + source
                        wrapped = True
                if _GH_PYTHON_OUTPUT_SENTINEL not in source:
                    postamble = _build_gh_python_output_postamble(outputs)
                    if postamble:
                        source = source + postamble
                        wrapped = True
            return {"source": source, "mode_used": "body", "wrapped": wrapped}

    raise ValueError(
        f"Unsupported script component runtime: {script_type}. "
        "Use raw gh_set_script for exact source."
    )
```

- [ ] **Step 4: Run the source tests and commit**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_csharp or gh_update_script_python or gh_update_script_gh1" -q
Pop-Location
```

Expected: source preparation tests pass.

Commit:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: prepare gh_update_script source by runtime"
```

---

### Task 3: Implement Error Summary Helpers

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add failing error summary tests**

Append:

```python
def test_gh_update_script_summarizes_component_and_unrelated_errors():
    summary = server._summarize_gh_update_script_errors(
        {
            "errors": [
                {"guid": "target", "errors": ["CS0103: missing R"]},
                {"guid": "other", "errors": ["Other failed"]},
            ],
            "warnings": [
                {"guid": "target", "warnings": ["Target warning"]},
                {"guid": "warn-only", "warnings": ["Canvas warning"]},
            ],
        },
        "target",
    )

    assert summary == {
        "component_errors": ["CS0103: missing R"],
        "component_warnings": ["Target warning"],
        "canvas_error_count": 2,
        "canvas_warning_count": 2,
        "unrelated_error_count": 1,
        "unrelated_warning_count": 1,
    }


def test_gh_update_script_error_summary_accepts_wrapped_response():
    summary = server._summarize_gh_update_script_errors(
        {"success": True, "data": {"errors": [], "warnings": []}},
        "target",
    )

    assert summary["component_errors"] == []
    assert summary["component_warnings"] == []
    assert summary["canvas_error_count"] == 0
    assert summary["canvas_warning_count"] == 0
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_summarizes or gh_update_script_error_summary" -q
Pop-Location
```

Expected: failures naming missing `_summarize_gh_update_script_errors`.

- [ ] **Step 3: Implement the summary helper**

In `mcp_server/src/rook/server.py`, add below the source preparation helper:

```python
def _unwrap_gh_response_data(response: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    if isinstance(data, dict):
        return data
    return response


def _summarize_gh_update_script_errors(
    errors_response: dict[str, Any] | None,
    guid: str,
) -> dict[str, Any]:
    data = _unwrap_gh_response_data(errors_response)
    error_entries = data.get("errors", []) if isinstance(data.get("errors"), list) else []
    warning_entries = data.get("warnings", []) if isinstance(data.get("warnings"), list) else []

    component_errors: list[Any] = []
    component_warnings: list[Any] = []
    unrelated_error_count = 0
    unrelated_warning_count = 0

    for entry in error_entries:
        if not isinstance(entry, dict):
            continue
        messages = entry.get("errors", [])
        if not isinstance(messages, list):
            messages = [messages]
        if entry.get("guid") == guid:
            component_errors.extend(messages)
        else:
            unrelated_error_count += len(messages)

    for entry in warning_entries:
        if not isinstance(entry, dict):
            continue
        messages = entry.get("warnings", [])
        if not isinstance(messages, list):
            messages = [messages]
        if entry.get("guid") == guid:
            component_warnings.extend(messages)
        else:
            unrelated_warning_count += len(messages)

    return {
        "component_errors": component_errors,
        "component_warnings": component_warnings,
        "canvas_error_count": len(component_errors) + unrelated_error_count,
        "canvas_warning_count": len(component_warnings) + unrelated_warning_count,
        "unrelated_error_count": unrelated_error_count,
        "unrelated_warning_count": unrelated_warning_count,
    }
```

- [ ] **Step 4: Run the tests and commit**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_summarizes or gh_update_script_error_summary" -q
Pop-Location
```

Expected: error summary tests pass.

Commit:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: summarize gh_update_script diagnostics"
```

---

### Task 4: Implement `gh_update_script` Execution And Dispatch

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add failing end-to-end mocked dispatch tests**

Append:

```python
@pytest.mark.asyncio
async def test_gh_update_script_csharp_body_orchestrates_existing_routes(monkeypatch, patched_server):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload))
        if route == "/gh/script" and "script" not in payload:
            return {
                "success": True,
                "data": {
                    "guid": "C20",
                    "Type": "CSharpScriptComponent",
                    "script": "old source",
                },
            }
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "guid": "C20",
                    "params": {
                        "inputs": [{"name": "R", "typeName": "double"}],
                        "outputs": [
                            {"name": "out"},
                            {"name": "A", "typeName": "double"},
                        ],
                    },
                },
            }
        if route == "/gh/script" and "script" in payload:
            assert "class Script_Instance" in payload["script"]
            assert "private void RunScript(object R, ref object A)" in payload["script"]
            assert "ref object out" not in payload["script"]
            return {"success": True, "data": {"Guid": "C20"}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [],
                    "warnings": [{"guid": "other", "warnings": ["pre-existing"]}],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"Unexpected route {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {
            "guid": "C20",
            "code": "A = Convert.ToDouble(R);",
            "mode": "body",
            "language": "csharp",
        },
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["guid"] == "C20"
    assert data["detected_runtime"] == "RhinoCode C#"
    assert data["detected_language"] == "csharp"
    assert data["mode_used"] == "body"
    assert data["wrapped"] is True
    assert data["inputs_used"] == [{"name": "R", "type": "double"}]
    assert data["outputs_used"] == [{"name": "A", "type": "double"}]
    assert data["component_errors"] == []
    assert data["canvas_warning_count"] == 1
    assert data["unrelated_warning_count"] == 1
    assert [call[0] for call in calls].count("/gh/script") == 2
    assert any(call[0] == "/gh/component" for call in calls)
    assert any(call[0] == "/gh/errors" for call in calls)


@pytest.mark.asyncio
async def test_gh_update_script_check_errors_false_skips_errors_route(monkeypatch, patched_server):
    routes = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        routes.append(route)
        if route == "/gh/script" and "script" not in payload:
            return {"success": True, "data": {"Type": "Python3Component", "script": "old"}}
        if route == "/gh/component":
            return {"success": True, "data": {"params": {"inputs": [], "outputs": []}}}
        if route == "/gh/script" and "script" in payload:
            return {"success": True, "data": {"Guid": "C9"}}
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"Unexpected route {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "C9", "code": "A = 1", "check_errors": False},
    ))

    assert payload["success"] is True
    assert "/gh/errors" not in routes
    assert payload["data"]["canvas_error_count"] == 0
    assert payload["data"]["canvas_warning_count"] == 0


@pytest.mark.asyncio
async def test_gh_update_script_compile_failure_adds_pin_recovery_hint(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in payload:
            return {"success": True, "data": {"Type": "CSharpScriptComponent", "script": "old"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "params": {
                        "inputs": [{"name": "R", "typeName": "double"}],
                        "outputs": [{"name": "out"}, {"name": "A", "typeName": "double"}],
                    },
                },
            }
        if route == "/gh/script" and "script" in payload:
            return {"success": True, "data": {"Guid": "C20"}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": "C20", "errors": ["CS0103: The name 'N' does not exist"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "unknown.gh", "path": ""}}
        raise AssertionError(f"Unexpected route {route!r}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "C20", "code": "A = N;", "mode": "body"},
    ))

    assert payload["success"] is True
    assert payload["data"]["component_errors"] == ["CS0103: The name 'N' does not exist"]
    assert "Current inputs are R; outputs are A" in payload["data"]["recovery_hint"]
    assert "gh_set_script_pins" in payload["data"]["recovery_hint"]
```

- [ ] **Step 2: Run the dispatch tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_csharp_body_orchestrates or gh_update_script_check_errors_false or gh_update_script_compile_failure" -q
Pop-Location
```

Expected: failures because `call_tool` has no `gh_update_script` case and no executor.

- [ ] **Step 3: Implement executor**

In `mcp_server/src/rook/server.py`, add below `_execute_gh_set_script_pins`:

```python
def _build_gh_update_script_recovery_hint(
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> str:
    input_names = ", ".join(pin["name"] for pin in inputs) or "(none)"
    output_names = ", ".join(pin["name"] for pin in outputs) or "(none)"
    return (
        f"Current inputs are {input_names}; outputs are {output_names}. "
        "To change the signature, call gh_set_script_pins first, then retry gh_update_script."
    )


async def _execute_gh_update_script(arguments: dict[str, Any], port: int) -> dict[str, Any]:
    guid = arguments.get("guid")
    code = arguments.get("code")
    if not guid:
        return {"success": False, "data": "Missing required parameter: guid"}
    if not isinstance(code, str) or not code:
        return {"success": False, "data": "Missing required parameter: code"}

    mode = arguments.get("mode", "auto")
    language = arguments.get("language", "auto")
    python_preamble = bool(arguments.get("python_preamble", True))
    check_errors = bool(arguments.get("check_errors", True))

    try:
        script_result = await call_rhino("/gh/script", "POST", {"guid": guid}, port=port)
        if not script_result.get("success"):
            return script_result
        script_data = _unwrap_gh_response_data(script_result)

        component_result = await call_rhino("/gh/component", "GET", {"guid": guid}, port=port)
        if not component_result.get("success"):
            return component_result
        component_data = _unwrap_gh_response_data(component_result)

        runtime = _classify_gh_update_script_runtime(script_data, component_data, language)

        params = _gh_case_get(component_data, "Params", "params")
        inputs, outputs = _gh_component_params_to_script_pin_defs(params)
        if runtime["detected_language"] == "csharp" and runtime.get("supports_update") and not isinstance(params, dict):
            raise ValueError(
                "Current pins could not be read for C# wrapping. "
                "Use raw gh_set_script with full source or inspect the component."
            )

        prepared = _prepare_gh_update_script_source(
            code=code,
            mode=mode,
            runtime=runtime,
            inputs=inputs,
            outputs=outputs,
            python_preamble=python_preamble,
        )

        write_result = await call_rhino(
            "/gh/script",
            "POST",
            {"guid": guid, "script": prepared["source"]},
            port=port,
        )
        if not write_result.get("success"):
            return write_result

        error_summary = {
            "component_errors": [],
            "component_warnings": [],
            "canvas_error_count": 0,
            "canvas_warning_count": 0,
            "unrelated_error_count": 0,
            "unrelated_warning_count": 0,
        }
        if check_errors:
            await asyncio.sleep(0.3)
            errors_result = await call_rhino("/gh/errors", "GET", {}, port=port)
            if errors_result.get("success"):
                error_summary = _summarize_gh_update_script_errors(errors_result, guid)

        data = {
            "guid": guid,
            "detected_runtime": runtime["detected_runtime"],
            "detected_language": runtime["detected_language"],
            "mode_used": prepared["mode_used"],
            "wrapped": prepared["wrapped"],
            "inputs_used": inputs,
            "outputs_used": outputs,
            "script_length": len(prepared["source"]),
            **error_summary,
        }
        if (
            runtime["detected_language"] == "csharp"
            and prepared["mode_used"] == "body"
            and error_summary["component_errors"]
        ):
            data["recovery_hint"] = _build_gh_update_script_recovery_hint(inputs, outputs)

        return {"success": True, "data": data}
    except Exception as exc:
        return {"success": False, "data": f"gh_update_script failed: {exc}"}
```

- [ ] **Step 4: Add the dispatch case**

In `call_tool()` near the `gh_set_script` case, insert before `case "gh_set_script_pins":`

```python
        case "gh_update_script":
            guid = arguments.get("guid")
            result = await _execute_gh_update_script(arguments, port)
            await _record_gh_to_session(
                action="gh_update_script",
                params={k: v for k, v in arguments.items() if k != "code"},
                result=result,
                port=port,
                components_affected=[guid] if guid else [],
            )
```

- [ ] **Step 5: Run dispatch tests and commit**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script_csharp_body_orchestrates or gh_update_script_check_errors_false or gh_update_script_compile_failure" -q
Pop-Location
```

Expected: dispatch tests pass.

Commit:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "feat: add gh_update_script executor"
```

---

### Task 5: Roll Out Agent Tooling And Prompt Guidance

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/personas/scripter/role.md`
- Modify: `mcp_server/src/rook/agent/personas/worker/role.md`
- Modify: `mcp_server/src/rook/agent/personas/architect/role.md`
- Modify: `mcp_server/src/rook/agent/prompts/WORKER.md`
- Modify: `mcp_server/tests/test_chat_prompt_builder.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add failing prompt and tool group drift tests**

In `mcp_server/tests/test_chat_prompt_builder.py`, append:

```python
@pytest.mark.parametrize("persona", ["worker", "architect", "scripter"])
def test_persona_prompt_uses_gh_update_script_for_existing_script_edits(persona):
    prompt = PromptBuilder().build_system(persona)

    assert "gh_update_script" in prompt
    assert "Use `gh_update_script` for normal source edits" in prompt
    assert "gh_set_script_pins" in prompt
    assert "then retry `gh_update_script`" in prompt
    assert "Use `gh_set_script` only for raw source" in prompt

    assert "Use `gh_set_script` to set/get source" not in prompt
    assert "Set new source: `gh_set_script" not in prompt
```

In `mcp_server/tests/test_server_contract_hardening.py`, append:

```python
def test_gh_canvas_tool_group_includes_update_script():
    from rook.agent.tool_groups import TOOL_GROUPS

    gh_canvas = TOOL_GROUPS["gh_canvas"]
    assert "gh_update_script" in gh_canvas
    assert "gh_set_script" in gh_canvas
    assert gh_canvas.index("gh_update_script") < gh_canvas.index("gh_set_script_pins")
```

- [ ] **Step 2: Run prompt/tool-group tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_chat_prompt_builder.py -k gh_update_script -q
uv run --extra test pytest tests/test_server_contract_hardening.py -k gh_canvas_tool_group_includes_update_script -q
Pop-Location
```

Expected: tests fail because prompts/tool group still route normal edits through `gh_set_script`.

- [ ] **Step 3: Add local agent tool wrapper**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add below `_local_gh_set_script_pins`:

```python
async def _local_gh_update_script(port: int | None = None, **kwargs) -> dict:
    from ..server import _execute_gh_update_script

    return await _execute_gh_update_script(kwargs, port)
```

Then add in `build_local_tools()` near `gh_set_script_pins`:

```python
    tools["gh_update_script"] = _local_gh_update_script
```

Keep `_transform_gh_set_script` unchanged because `gh_set_script` remains raw.

- [ ] **Step 4: Update the `gh_canvas` tool group**

In `mcp_server/src/rook/agent/tool_groups.py`, change the `gh_canvas` list from:

```python
        "gh_errors", "gh_set_script", "gh_set_script_pins",
```

to:

```python
        "gh_errors", "gh_update_script", "gh_set_script", "gh_set_script_pins",
```

- [ ] **Step 5: Update chat runner short descriptions**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, replace:

```python
    "gh_set_script": "Set the script content of a C#/Python script component",
```

with:

```python
    "gh_update_script": "Update source on an existing supported C#/Python script component",
    "gh_set_script": "Raw source read/write for C#/Python/GH1 script components",
```

- [ ] **Step 6: Update persona prompt tool lists**

In each of these files:

- `mcp_server/src/rook/agent/personas/worker/role.md`
- `mcp_server/src/rook/agent/personas/architect/role.md`

Replace the script tool bullet:

```markdown
- `gh_set_script` -- set/get source on any GH script component (Python 3, C#, or GH1-legacy — duck-typed on capability)
```

with:

```markdown
- `gh_update_script` -- normal source edits on existing supported GH script components; wraps RhinoCode C# body code using current pins
- `gh_set_script` -- raw source read/write for GH script components, including unsupported GH1 C# exact-source edits
```

Then replace the script-components gotcha bullet:

```markdown
- **Script components**: Use `gh_set_script` to set/get source on any script-component type (Python 3, C#, GH1-legacy); use `gh_create_script(language=...)` (or its `gh_create_python_script` / `gh_create_csharp_script` aliases) for creation — NOT `gh_edit` with component-name strings
```

with:

```markdown
- **Script components**: Use `gh_update_script` for normal source edits on existing supported script components. If the signature must change, call `gh_set_script_pins` first, then retry `gh_update_script`. Use `gh_set_script` only for raw source read/write, unsupported GH1 C# exact-source edits, or advanced escape-hatch workflows. Use `gh_create_script(language=...)` (or its `gh_create_python_script` / `gh_create_csharp_script` aliases) for creation — NOT `gh_edit` with component-name strings.
```

- [ ] **Step 7: Update scripter edit workflow**

In `mcp_server/src/rook/agent/personas/scripter/role.md`, replace the existing `### Editing an existing script component` list with:

```markdown
### Editing an existing script component
1. Inspect the component via `gh_snapshot` or `gh_set_script(guid)` if you need to read exact current source. `gh_set_script(guid)` with no `script` argument is the raw read path.
2. For normal source edits, call `gh_update_script(guid, code, mode="auto")`. For RhinoCode C#, body code is wrapped using the component's current pins.
3. If the signature must change, call `gh_set_script_pins(guid, ...)` first. Then call `gh_update_script` so wrapping uses the verified current pins.
4. Use `gh_set_script(guid, script)` only for raw source writes, unsupported GH1 C# exact-source edits, or advanced escape-hatch workflows.
5. Verify: `gh_errors`.
```

Replace the error recovery bullet:

```markdown
- If `gh_set_script` fails, verify the component supports source editing (the handler duck-types on capability — component types like simple params don't have `SetSource` or `ScriptSource`)
```

with:

```markdown
- If `gh_update_script` says a body edit references unknown pin names, call `gh_set_script_pins` first when the signature must change, then retry `gh_update_script`.
- If raw `gh_set_script` fails, verify the component supports source editing (the handler duck-types on capability — component types like simple params don't have `SetSource` or `ScriptSource`).
```

- [ ] **Step 8: Update `WORKER.md` display snapshot**

In `mcp_server/src/rook/agent/prompts/WORKER.md`, replace the tool list bullet:

```markdown
- `gh_set_script` — set/get source on any GH script component (Python 3, C#, or GH1-legacy — duck-typed on capability)
```

with:

```markdown
- `gh_update_script` — normal source edits on existing supported GH script components; wraps RhinoCode C# body code using current pins
- `gh_set_script` — raw source read/write for GH script components, including unsupported GH1 C# exact-source edits
```

Replace the script-components gotcha with the same text used for worker/architect persona roles.

- [ ] **Step 9: Run prompt/tool-group tests and commit**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_chat_prompt_builder.py -k "script_tool_language or gh_update_script" -q
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_canvas_tool_group_includes_update_script or gh_set_script_description" -q
Pop-Location
```

Expected: prompt/tool-group drift tests pass.

Commit:

```powershell
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/src/rook/agent/personas/scripter/role.md mcp_server/src/rook/agent/personas/worker/role.md mcp_server/src/rook/agent/personas/architect/role.md mcp_server/src/rook/agent/prompts/WORKER.md mcp_server/tests/test_chat_prompt_builder.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "docs: route agents to gh_update_script"
```

---

### Task 6: Run Focused And Full Python MCP Verification

**Files:**
- No code changes expected unless tests reveal a defect.

- [ ] **Step 1: Run all focused GH script contract tests**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -k "gh_update_script or gh_create_script or gh_set_script_pins or gh_set_script_description" -q
uv run --extra test pytest tests/test_chat_prompt_builder.py -q
Pop-Location
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the broader MCP test file if focused tests pass**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests/test_server_contract_hardening.py -q
Pop-Location
```

Expected: pass.

- [ ] **Step 3: Run targeted live validation if Rhino/GH is available**

Only run this when Rhino and Grasshopper are open with a writable test document.

Manual MCP validation sequence:

```text
1. gh_status
2. gh_snapshot
3. Pick or create a RhinoCode C# Script component with inputs R and output A.
4. gh_update_script(guid=<component>, code="A = Convert.ToDouble(R) * 2;", mode="body", language="csharp")
5. Verify result.data.mode_used == "body" and result.data.wrapped == true.
6. gh_errors
7. gh_update_script(guid=<component>, code=<full Script_Instance source>, mode="full_source", language="csharp")
8. Verify no component errors.
9. gh_update_script(guid=<component>, code="A = N;", mode="body")
10. Verify component_errors contains the compile error and recovery_hint names current inputs/outputs.
```

Expected: C# body edits work without agents manually reconstructing `Script_Instance`; compile errors are component-filtered and include the pin-signature recovery hint.

- [ ] **Step 4: Final cleanup commit if verification fixes were needed**

If verification required fixes:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_chat_prompt_builder.py
git commit -m "fix: stabilize gh_update_script verification"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Code-only v1: covered by executor accepting only `guid`, `code`, mode/language flags and by prompt guidance that routes signature changes through `gh_set_script_pins`.
- Python MCP layer only: covered by `server.py` orchestration; no native or C# files are touched.
- `gh_set_script` raw semantics unchanged: no task changes its dispatcher or handler behavior; docs only reframe it as raw.
- Runtime mapping: Task 1 tests the exact `/gh/script` type names.
- RhinoCode C# body/full/auto: Task 2 and Task 4 tests cover wrapping, pass-through, and `out` skipping.
- RhinoCode Python 3 preamble semantics: Task 2 covers full-source no-op, body insertion, and sentinel duplication prevention.
- GH1 Python raw/direct: Task 2 covers raw/direct behavior.
- GH1 C# fail closed all modes: Task 2 covers all modes.
- Result shape and diagnostics: Task 3 and Task 4 cover `{ success, data }` and component/unrelated counts.
- Agent rollout/drift tests: Task 5 covers personas, tool group, chat text, and prompt drift.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or unspecified "add tests" steps.
- Each code-changing task includes concrete test code, implementation code, commands, and expected results.

Type consistency:

- Runtime helper name is consistently `_classify_gh_update_script_runtime`.
- Source helper name is consistently `_prepare_gh_update_script_source`.
- Error helper name is consistently `_summarize_gh_update_script_errors`.
- Executor name is consistently `_execute_gh_update_script`.
