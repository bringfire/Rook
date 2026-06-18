# GH Script Compile Status Truthfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Grasshopper script create/update tool success truthful: placement/write milestones remain visible, but top-level `success` is false when the target script component still has compile errors.

**Architecture:** Change result shaping in `mcp_server/src/rook/server.py` at the script helper layer, not in ChatRunner or the C# UI. Preserve rich payloads on failure so the model can repair the existing component by GUID. Add focused Python tests that prove target-component errors fail, warnings and unrelated canvas errors do not, and deferred verification remains unchanged.

**Tech Stack:** Python aio MCP server helpers, pytest async tests, existing RookChat transcript test harness.

---

## Scope And File Map

**Modify**
- `mcp_server/src/rook/server.py`
  - `_execute_gh_create_script(...)`: when component-specific compile errors are detected after placement/source injection, return `success: false` while preserving component milestone data.
  - `_execute_gh_update_script(...)`: when `check_errors=true` and target component errors are present, return `success: false` while preserving write milestone and diagnostic data.
- `mcp_server/tests/test_server_contract_hardening.py`
  - Flip existing compile-error update test.
  - Add create-path and update edge-case tests.
- `mcp_server/tests/test_rookchat_tool_transcripts.py`
  - Add transcript coverage that compile-error payloads emit `tool_status="failed"` and keep GUIDs visible.

**Do not modify**
- `mcp_server/src/rook/agent/chat/chat_runner.py` except if tests prove result classification cannot be driven by top-level `success`; current design expects no ChatRunner code change.
- `src/Rook/UI/Chat/*`
- schemas/tool groups/dispatcher routing
- prompt/persona files
- `knowledge/*` runtime artifacts

**Wire-shape constraint**
- `server.call_tool()` formats internal failures through `_format_tool_result()`, which serializes only `result["data"]` after the `Error: ` prefix. Any model-visible or test-visible failure message must therefore be present inside `data["message"]`. Helpers may also include a top-level `message` internally, but tests that call `server.call_tool()` must assert `payload["data"]["message"]`, not `payload["message"]`.

**Explicit defer**
- This slice does not change session-history `components_created` recording for "created but compile-failed" results. The failure payload preserves `component_guid` for the current repair turn; broader session-history milestone recording can be handled separately if it proves necessary.

---

## Task 1: Update-Script Compile Errors Become Failed Tool Results

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Rename and flip the existing failing test expectation**

In `mcp_server/tests/test_server_contract_hardening.py`, rename:

```python
async def test_gh_update_script_compile_failure_returns_component_errors_and_recovery_hint(
```

to:

```python
async def test_gh_update_script_compile_failure_returns_failed_with_component_errors_and_recovery_hint(
```

Then change the expectation block from:

```python
    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == ["The name X does not exist"]
    assert data["recovery_hint"] == (
        "Current inputs are R; outputs are A. To change the signature, call "
        "gh_set_script_pins first, then retry gh_update_script."
    )
```

to:

```python
    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Source was written, but the target script component still has compile errors."
    )
    assert data["guid"] == "cs-guid"
    assert data["component_errors"] == ["The name X does not exist"]
    assert data["component_warnings"] == []
    assert data["canvas_error_count"] == 1
    assert data["unrelated_error_count"] == 0
    assert data["recovery_hint"] == (
        "Current inputs are R; outputs are A. To change the signature, call "
        "gh_set_script_pins first, then retry gh_update_script."
    )
```

- [ ] **Step 2: Run the renamed test and verify RED**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py::test_gh_update_script_compile_failure_returns_failed_with_component_errors_and_recovery_hint -q
```

Expected: `FAILED` because current code still returns `success: True`.

- [ ] **Step 3: Add a tiny response-shaping helper in `server.py`**

In `mcp_server/src/rook/server.py`, immediately before `_execute_gh_update_script`, add:

```python
def _gh_update_script_has_target_compile_errors(data: dict[str, Any]) -> bool:
    return bool(data.get("component_errors"))


def _gh_update_script_result_from_data(data: dict[str, Any]) -> dict[str, Any]:
    if _gh_update_script_has_target_compile_errors(data):
        data["message"] = "Source was written, but the target script component still has compile errors."
        return {
            "success": False,
            "message": data["message"],
            "data": data,
        }
    return {"success": True, "data": data}
```

This helper intentionally ignores warnings and unrelated canvas errors.

- [ ] **Step 4: Use the helper at the end of `_execute_gh_update_script`**

In `_execute_gh_update_script`, replace:

```python
        return {"success": True, "data": data}
```

with:

```python
        return _gh_update_script_result_from_data(data)
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py::test_gh_update_script_compile_failure_returns_failed_with_component_errors_and_recovery_hint -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit Task 1**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix(chat): fail gh_update_script on target compile errors"
```

Confirm `knowledge/*` is not staged.

---

## Task 2: Preserve Non-Fatal Update Outcomes

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add test for unrelated canvas errors staying successful**

Add this test immediately after the Task 1 update compile-failure test:

```python
@pytest.mark.asyncio
async def test_gh_update_script_unrelated_canvas_errors_remain_success(
    monkeypatch, patched_server
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [{"Name": "R"}],
                        "Outputs": [{"Name": "out"}, {"Name": "A"}],
                    }
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": "other-guid", "errors": ["Other component is broken"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "A = R;", "mode": "body"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == []
    assert data["canvas_error_count"] == 1
    assert data["unrelated_error_count"] == 1
```

- [ ] **Step 2: Add test for target warnings staying successful**

Add this test after the unrelated-error test:

```python
@pytest.mark.asyncio
async def test_gh_update_script_target_warnings_remain_success(
    monkeypatch, patched_server
):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/script" and "script" not in (payload or {}):
            return {"success": True, "data": {"Type": "CSharpScriptComponent"}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": "cs-guid"}}
        if route == "/gh/component":
            return {
                "success": True,
                "data": {
                    "Params": {
                        "Inputs": [],
                        "Outputs": [{"Name": "out"}, {"Name": "B"}],
                    }
                },
            }
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [],
                    "warnings": [{"guid": "cs-guid", "warnings": ["Unused using directive"]}],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_update_script",
        {"guid": "cs-guid", "code": "B = 1;", "mode": "body"},
    ))

    assert payload["success"] is True
    data = payload["data"]
    assert data["component_errors"] == []
    assert data["component_warnings"] == ["Unused using directive"]
    assert data["canvas_warning_count"] == 1
```

- [ ] **Step 3: Run the update-script focused tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py -k "gh_update_script_compile_failure_returns_failed or gh_update_script_unrelated_canvas_errors_remain_success or gh_update_script_target_warnings_remain_success or gh_update_script_error_check_failure_is_visible or gh_update_script_check_errors_false_skips_gh_errors" -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit Task 2**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short
git add mcp_server/tests/test_server_contract_hardening.py
git commit -m "test(chat): preserve nonfatal gh_update_script outcomes"
```

Confirm `knowledge/*` is not staged.

---

## Task 3: Create-Script Compile Errors Become Failed Tool Results

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add failing test for alias create compile errors**

Add this test near the existing `gh_create_csharp_script` tests in `mcp_server/tests/test_server_contract_hardening.py`:

```python
@pytest.mark.asyncio
async def test_gh_create_csharp_script_compile_errors_fail_but_preserve_component_guid(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": component_guid, "errors": ["The name Boxx does not exist"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = Boxx;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is False
    data = payload["data"]
    assert data["message"] == (
        "Component was created, but the target script component has compile errors."
    )
    assert data["component_guid"] == component_guid
    assert data["name"] == "Box Maker"
    assert data["pins_out"] == [{"name": "B", "type": "Brep", "access": "item"}]
    assert data["compilation_errors"] == ["The name Boxx does not exist"]
```

- [ ] **Step 2: Run the alias create test and verify RED**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py::test_gh_create_csharp_script_compile_errors_fail_but_preserve_component_guid -q
```

Expected: `FAILED` because current create helper returns `success: True` with a warning.

- [ ] **Step 3: Add helper for create result shaping**

In `mcp_server/src/rook/server.py`, immediately before `_execute_gh_create_script`, add:

```python
def _gh_create_script_result_from_data(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("compilation_errors"):
        data["message"] = "Component was created, but the target script component has compile errors."
        return {
            "success": False,
            "message": data["message"],
            "data": data,
        }
    return {"success": True, "data": data}
```

- [ ] **Step 4: Use helper in `_execute_gh_create_script`**

In `_execute_gh_create_script`, replace:

```python
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "component_guid": component_guid,
                "pins_in": pin_defs_in,
                "pins_out": pin_defs_out,
                "position": {"x": x, "y": y},
                "name": name or config["default_name"],
                "code_length": len(full_script),
            },
        }
        if component_errors:
            result["data"]["compilation_errors"] = component_errors
            result["data"]["warning"] = "Component placed but has compilation errors"
        return result
```

with:

```python
        data: dict[str, Any] = {
            "component_guid": component_guid,
            "pins_in": pin_defs_in,
            "pins_out": pin_defs_out,
            "position": {"x": x, "y": y},
            "name": name or config["default_name"],
            "code_length": len(full_script),
        }
        if component_errors:
            data["compilation_errors"] = component_errors
            data["warning"] = "Component placed but has compilation errors"
        return _gh_create_script_result_from_data(data)
```

- [ ] **Step 5: Run alias create test and verify GREEN**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py::test_gh_create_csharp_script_compile_errors_fail_but_preserve_component_guid -q
```

Expected: `1 passed`.

- [ ] **Step 6: Add unified C# parity test**

Add this test immediately after the alias create compile-error test:

```python
@pytest.mark.asyncio
async def test_gh_create_script_csharp_compile_errors_share_failure_shape(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "data": {
                    "errors": [{"guid": component_guid, "errors": ["Cannot convert Box to Brep"]}],
                    "warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "B = new Box();",
            "pins_in": [],
            "pins_out": ["B:Brep"],
            "name": "Box Maker",
        },
    ))

    assert payload["success"] is False
    assert payload["data"]["message"] == (
        "Component was created, but the target script component has compile errors."
    )
    assert payload["data"]["component_guid"] == component_guid
    assert payload["data"]["compilation_errors"] == ["Cannot convert Box to Brep"]
```

- [ ] **Step 7: Add capitalized live-shape create error test**

Add this test immediately after the unified C# parity test:

```python
@pytest.mark.asyncio
async def test_gh_create_csharp_script_compile_errors_match_capitalized_live_shape(
    monkeypatch, patched_server
):
    component_guid = "12345678-1234-4234-9234-123456789abc"

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/create-component":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/script-params":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/script":
            return {"success": True, "data": {"Guid": component_guid}}
        if route == "/gh/errors":
            return {
                "success": True,
                "Data": {
                    "Errors": [{"Guid": component_guid, "Errors": ["capitalized compile"]}],
                    "Warnings": [],
                },
            }
        if route == "/gh/document":
            return {"success": True, "data": {"name": "contract.gh", "path": ""}}
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    payload = _decode_response(await server.call_tool(
        "gh_create_csharp_script",
        {
            "code": "B = MissingSymbol;",
            "pins_in": [],
            "pins_out": ["B:Brep"],
        },
    ))

    assert payload["success"] is False
    assert payload["data"]["component_guid"] == component_guid
    assert payload["data"]["compilation_errors"] == ["capitalized compile"]
```

- [ ] **Step 8: Replace create compile-error extraction with case-insensitive helper**

In `mcp_server/src/rook/server.py`, immediately before `_gh_create_script_result_from_data`, add:

```python
def _gh_create_script_component_errors(errors_result: Any, component_guid: str) -> list[Any]:
    data = errors_result
    if isinstance(errors_result, dict):
        wrapped_data = _dict_get_ci(errors_result, "data")
        if wrapped_data is not None:
            data = wrapped_data
    if not isinstance(data, dict):
        return []

    errors = _dict_get_ci(data, "errors", [])
    if not isinstance(errors, list):
        return []

    component_guid_lower = str(component_guid).lower()
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        entry_guid = _dict_get_ci(entry, "guid")
        if isinstance(entry_guid, str) and entry_guid.lower() == component_guid_lower:
            messages = _dict_get_ci(entry, "errors", [])
            return _gh_update_script_messages(messages)
    return []
```

Then in `_execute_gh_create_script`, replace:

```python
        component_errors: list[Any] = []
        if errors_result.get("success"):
            edata = errors_result.get("data", {})
            for err in edata.get("errors", []):
                if err.get("guid") == component_guid:
                    component_errors = err.get("errors", [])
                    break
```

with:

```python
        component_errors: list[Any] = []
        if errors_result.get("success"):
            component_errors = _gh_create_script_component_errors(
                errors_result,
                component_guid,
            )
```

- [ ] **Step 9: Run create-focused tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py -k "gh_create_csharp_script_compile_errors_fail or gh_create_script_csharp_compile_errors_share_failure_shape or gh_create_csharp_script_compile_errors_match_capitalized_live_shape or gh_create_csharp_script_accepts_rich_pin_objects or gh_create_aliases_share_response_shape_with_unified_tool" -q
```

Expected: selected tests pass.

- [ ] **Step 10: Commit Task 3**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix(chat): fail gh script creation on target compile errors"
```

Confirm `knowledge/*` is not staged.

---

## Task 4: ChatRunner Transcript Status Regression

**Files:**
- Modify: `mcp_server/tests/test_rookchat_tool_transcripts.py`

- [ ] **Step 1: Add transcript test for failed update preserving GUID**

Add this test after `test_csharp_script_creation_can_run_first_round_without_request_tools`:

```python
@pytest.mark.asyncio
async def test_gh_update_script_compile_errors_emit_failed_status_with_guid():
    tool_results = {
        "gh_update_script": {
            "success": False,
            "message": "Source was written, but the target script component still has compile errors.",
            "data": {
                "message": "Source was written, but the target script component still has compile errors.",
                "guid": "script-guid",
                "component_errors": ["The name Boxx does not exist"],
                "component_warnings": [],
                "canvas_error_count": 1,
                "canvas_warning_count": 0,
                "recovery_hint": "Current inputs are (none); outputs are B.",
            },
        },
    }

    async def executor(name, params):
        return tool_results[name]

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(
            _ToolCall(
                "call_update",
                "gh_update_script",
                {
                    "guid": "script-guid",
                    "code": "B = Boxx;",
                    "mode": "body",
                },
            )
        ),
        _text_stream("The update still has compile errors, so I need to repair script-guid."),
    ]

    events, conv = await _collect_events(runner, responses)

    update_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_update_script"
    ][0]
    assert update_result.tool_status == "failed"
    assert "script-guid" in update_result.result
    assert "The name Boxx does not exist" in update_result.result
    assert conv.messages[-1]["role"] == "assistant"
    assert "repair script-guid" in conv.messages[-1]["content"]
```

- [ ] **Step 2: Add transcript test for failed create preserving component GUID**

Add this test after the update transcript test:

```python
@pytest.mark.asyncio
async def test_gh_create_script_compile_errors_emit_failed_status_with_component_guid():
    tool_results = {
        "gh_create_csharp_script": {
            "success": False,
            "message": "Component was created, but the target script component has compile errors.",
            "data": {
                "message": "Component was created, but the target script component has compile errors.",
                "component_guid": "created-guid",
                "name": "Box Maker",
                "compilation_errors": ["Cannot convert Box to Brep"],
                "pins_out": [{"name": "B", "type": "Brep", "access": "item"}],
            },
        },
    }

    async def executor(name, params):
        return tool_results[name]

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {
                    "code": "B = new Box();",
                    "pins_in": [],
                    "pins_out": ["B:Brep"],
                },
            )
        ),
        _text_stream("The component exists as created-guid, but I need to fix its compile error."),
    ]

    events, conv = await _collect_events(runner, responses)

    create_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_create_csharp_script"
    ][0]
    assert create_result.tool_status == "failed"
    assert "created-guid" in create_result.result
    assert "Cannot convert Box to Brep" in create_result.result
    assert "created-guid" in conv.messages[-1]["content"]
```

- [ ] **Step 3: Run transcript tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_transcripts.py -q
```

Expected: all transcript tests pass.

- [ ] **Step 4: Commit Task 4**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short
git add mcp_server/tests/test_rookchat_tool_transcripts.py
git commit -m "test(chat): preserve failed script compile status in transcripts"
```

Confirm `knowledge/*` is not staged.

---

## Task 5: Verification And Review Handoff

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused server and transcript tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py -k "gh_update_script or gh_create_script or gh_create_csharp_script" -q
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_transcripts.py tests/test_rookchat_gh_script_creation_parity.py tests/test_rookchat_tool_schema_golden.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader RookChat regressions**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_prompt_builder.py tests/test_chat_runner.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Check branch hygiene and whitespace**

Run:

```powershell
cd C:\UDEV\Rook
git fetch origin --prune
git rev-list --left-right --count origin/main...HEAD
git diff --check origin/main...HEAD
git status --short --branch
git diff --name-only origin/main...HEAD
```

Expected:
- branch is not behind `origin/main`
- diff check is clean
- working tree contains only expected files plus unstaged `knowledge/*` runtime artifacts
- branch diff includes only the spec, plan, `mcp_server/src/rook/server.py`, and Python tests

- [ ] **Step 4: Do not deploy or run live Rhino in this task**

Manual smoke comes after review/merge/deploy. Report explicitly that live Rhino was not run.

- [ ] **Step 5: Request review**

Summarize:
- top-level `success` now represents target compile success for create/update when verification is available
- placement/write milestone data remains preserved in failure payloads
- model-visible failure messages are included in `data["message"]` because `server.call_tool()` drops top-level failure siblings
- target warnings and unrelated canvas errors remain non-fatal
- deferred verification unchanged
- session-history `components_created` recording for compile-failed creates is explicitly deferred
- tests run and results

Do not push/open PR unless the user asks after review.

---

## Self-Review

Spec coverage:
- Target-component errors flip create/update to failed: Tasks 1 and 3.
- Warnings stay non-fatal: Task 2.
- Unrelated canvas errors stay non-fatal: Task 2.
- Deferred verification unchanged: Task 2/5 focused regression command includes existing deferred/error-check tests; implementation helper only keys on `component_errors`.
- Payload preservation: Tasks 1, 3, and 4 assert GUIDs and diagnostic fields.
- No ChatRunner/UI/schema/prompt changes: File map and tasks avoid them.
- Public failure message wire shape: Tasks 1, 3, and 4 include `data["message"]`; tests using `server.call_tool()` assert `payload["data"]["message"]`.
- Capitalized live `/gh/errors` shape for create: Task 3 covers `Guid` / `Errors` and adds case-insensitive extraction.
- Session history milestone recording: explicitly deferred in scope, not silently ignored.

Placeholder scan:
- No placeholder tokens or copy-forward instructions.

Type consistency:
- Uses existing response fields: `component_guid`, `guid`, `component_errors`, `component_warnings`, `compilation_errors`, `recovery_hint`, `tool_status`.
- Uses existing helper/test patterns: `_decode_response`, `patched_server`, `ChatRunner`, `_tool_stream`, `_ToolCall`.
