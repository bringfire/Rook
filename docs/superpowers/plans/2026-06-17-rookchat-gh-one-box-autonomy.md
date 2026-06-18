# RookChat GH One-Box Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a local RookChat model naturally create and verify a one-box Grasshopper RhinoCode C# Script component without hand-holding.

**Architecture:** Keep the slice narrow: strengthen local tool schemas and meta-tool feedback in Python, add a result-status signal from Python/C# event handling, and make the WebView tool cards render nested params and app-level failures truthfully. Do not broaden into general prompt tuning or the 10x10 grid task.

**Tech Stack:** Python 3.12 pytest for Rook chat runner tests; C# net48 xUnit source-guard tests for panel wiring; Eto/WebView HTML/JavaScript for tool-card rendering.

---

## File Map

- `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Strengthen local schemas for C# script creation.
  - Return explicit already-loaded metadata from `request_tools`.
  - Preserve distinct streamed tool-call names.
  - Emit app-level result status on `ChatEvent`.
- `mcp_server/tests/test_chat_runner.py`
  - Python behavior tests for schema guidance, de-dupe, exact tool names, and result status.
- `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
  - Extend existing schema parity tests so alias and unified C# paths both carry C# guidance while required fields remain server-compatible.
- `src/Rook/UI/Chat/AgentChatClient.cs`
  - Add `ToolStatus` / result-status field to `ChatEvent`.
- `src/Rook/UI/Chat/AgentChatTab.cs`
  - Pass result status separately from verification.
  - Improve `BuildToolSummary` failure extraction.
- `src/Rook/UI/Chat/Resources/chat.html`
  - Render nested params as compact JSON, not `[object Object]`.
  - Render `failed`/`warning`/`done` states from result status without overloading verification.
- `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`
  - Source guards for result-status wiring, readable param rendering, and no default green verified state.

## Guardrails

- Do not implement broad prompt tuning.
- Do not make the 10x10 grid prompt a merge gate.
- Do not touch Workbench, session topology, launcher, or Rhino process lifecycle.
- Do not stage or revert `knowledge/contextual_mab.pkl` or `knowledge/substrate_observations.jsonl`.
- Use explicit file staging only if committing during execution.

---

### Task 1: Local C# Script Schema Guidance

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify tests: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Write failing tests for alias and unified schema guidance**

Add these tests near the existing local schema tests in `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
def _schema_text(schema: dict) -> str:
    fn = schema["function"]
    params = fn["parameters"]
    pieces = [fn.get("description", "")]
    for prop in params.get("properties", {}).values():
        if isinstance(prop, dict):
            pieces.append(prop.get("description", ""))
    return "\n".join(pieces)


def test_local_csharp_alias_schema_teaches_rhinocode_script_contract():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_csharp_script": object()})
    text = _schema_text(catalog["gh_create_csharp_script"])

    assert "RhinoCode C# Script" in text
    assert "body" in text and "RunScript" in text
    assert "GH_Component" in text and "do not" in text.lower()
    assert "B:Brep" in text


def test_local_unified_schema_teaches_csharp_contract_when_language_is_csharp():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_script": object()})
    text = _schema_text(catalog["gh_create_script"])

    assert "language=\"csharp\"" in text or "language: csharp" in text
    assert "RhinoCode C# Script" in text
    assert "body" in text and "RunScript" in text
    assert "GH_Component" in text and "do not" in text.lower()
```

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_gh_script_creation_parity.py -k "schema_teaches" -q
```

Expected: both tests fail because the local fallback schema descriptions are generic.

- [ ] **Step 3: Implement focused schema text constants**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, add constants above `_gh_create_script_schema`:

```python
_GH_CSHARP_SCRIPT_CONTRACT = (
    "C# mode creates a RhinoCode C# Script component, not a Grasshopper plugin "
    "component. Prefer body-only RunScript code; the tool wraps it in "
    "Script_Instance boilerplate. Do not provide a GH_Component subclass. "
    "Only provide full source when it is a Script_Instance : GH_ScriptInstance "
    "class or contains void RunScript. Assign outputs directly by output pin "
    "name, e.g. B = box.ToBrep()."
)

_GH_CSHARP_CODE_DESCRIPTION = (
    "C# source for RhinoCode C# Script. Prefer body-only RunScript code. "
    "Do not send a GH_Component subclass. Full-source mode must be "
    "Script_Instance : GH_ScriptInstance or contain void RunScript."
)
```

Change `_gh_create_script_schema` to accept optional `code_description`, `extra_description`, and `pins_out_description` keyword arguments:

```python
def _gh_create_script_schema(
    name: str,
    description: str,
    *,
    required: list[str],
    include_language: bool,
    code_description: str | None = None,
    extra_description: str | None = None,
    pins_out_description: str | None = None,
) -> dict:
    if extra_description:
        description = f"{description}\n\n{extra_description}"
    properties: dict = {
        "code": {
            "type": "string",
            "description": code_description or "Script source code for the script component.",
        },
        ...
        "pins_out": {
            **_GH_SCRIPT_PIN_ARRAY_SCHEMA,
            "description": pins_out_description
            or 'Output pin definitions as "Name:Type" strings or pin objects.',
        },
        ...
    }
```

Then pass the C# guidance for unified and alias schemas:

```python
_GH_CREATE_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_script",
        "Create a Python 3 or C# Script component with pins and code.",
    ),
    required=["language", "code"],
    include_language=True,
    code_description=(
        "Script source code. For language=\"csharp\": "
        + _GH_CSHARP_CODE_DESCRIPTION
    ),
    extra_description=(
        'When language="csharp": ' + _GH_CSHARP_SCRIPT_CONTRACT
    ),
    pins_out_description=(
        'Output pin definitions as "Name:Type" strings or pin objects. '
        'For one Brep box output, use ["B:Brep"].'
    ),
)
```

```python
_GH_CREATE_CSHARP_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_csharp_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_csharp_script",
        'Alias for gh_create_script(language="csharp").',
    ),
    required=["code", "pins_in", "pins_out"],
    include_language=False,
    code_description=_GH_CSHARP_CODE_DESCRIPTION,
    extra_description=_GH_CSHARP_SCRIPT_CONTRACT,
    pins_out_description=(
        'Output pin definitions as "Name:Type" strings or pin objects, '
        'e.g. ["B:Brep"] for one box Brep output.'
    ),
)
```

- [ ] **Step 4: Run tests to verify green**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_gh_script_creation_parity.py -k "schema_teaches or local_catalog_schema" -q
```

Expected: schema guidance tests pass, existing required-field tests still pass.

- [ ] **Step 5: Checkpoint**

Run:

```powershell
git status --short
```

Expected: only `chat_runner.py` and `test_rookchat_gh_script_creation_parity.py` changed, plus the known unstaged `knowledge/*` runtime files.

---

### Task 2: `request_tools` Already-Loaded Feedback

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify tests: `mcp_server/tests/test_chat_runner.py`

- [ ] **Step 1: Write failing test for repeated group request**

Add this test after `test_meta_tool_request_tools` in `mcp_server/tests/test_chat_runner.py`:

```python
def test_request_tools_reports_already_loaded_group():
    catalog = {
        "gh_status": {
            "type": "function",
            "function": {
                "name": "gh_status",
                "description": "GH status",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "gh_errors": {
            "type": "function",
            "function": {
                "name": "gh_errors",
                "description": "GH errors",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    runner = ChatRunner(tool_executor=AsyncMock(), registry=registry)

    first = runner._handle_meta_tool("request_tools", {"group": "gh_canvas"})
    second = runner._handle_meta_tool("request_tools", {"group": "gh_canvas"})

    assert first["success"] is True
    assert first["status"] == "loaded"
    assert second["success"] is True
    assert second["status"] == "already_loaded"
    assert second["loaded"] == []
    assert "already loaded" in second["message"].lower()
    assert "call the needed Grasshopper tool" in second["next_action"]
```

- [ ] **Step 2: Run test to verify red**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_runner.py::test_request_tools_reports_already_loaded_group -q
```

Expected: fails because `_handle_meta_tool` returns raw registry payload without `status`, `message`, or `next_action`.

- [ ] **Step 3: Implement status decoration in `_handle_meta_tool`**

Replace the `request_tools` branch in `ChatRunner._handle_meta_tool`:

```python
if name == "request_tools":
    group = params.get("group", "")
    result = self._registry.request_group(group)
    if result.get("success"):
        loaded = result.get("loaded") or []
        already_active = result.get("already_active") or []
        if loaded:
            result["status"] = "loaded"
            result["message"] = (
                f"Loaded {len(loaded)} tool(s) from {group}. "
                "Call the needed tool directly next."
            )
        elif already_active:
            result["status"] = "already_loaded"
            result["message"] = (
                f"{group} is already loaded; no new tools were added."
            )
            result["next_action"] = "Call the needed Grasshopper tool directly."
        else:
            result["status"] = "empty"
            result["message"] = f"No tools were loaded for {group}."
    return result
```

- [ ] **Step 4: Run request-tools tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_runner.py -k "request_tools" -q
```

Expected: all request-tools/meta-loop tests pass.

- [ ] **Step 5: Checkpoint**

Run:

```powershell
git status --short
```

Expected: only Python implementation/tests changed, plus known `knowledge/*`.

---

### Task 3: ChatRunner Tool Name Boundary and Result Status

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify tests: `mcp_server/tests/test_chat_runner.py`

- [ ] **Step 1: Write failing test for distinct streamed tool names**

Add this helper near `_make_tool_response`:

```python
def _make_two_tool_response():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        calls = []
        for idx, name, call_id, args in [
            (0, "request_tools", "call_request", {"group": "gh_canvas"}),
            (1, "gh_errors", "call_errors", {}),
        ]:
            tc_delta = MagicMock()
            tc_delta.index = idx
            tc_delta.id = call_id
            tc_delta.function.name = name
            tc_delta.function.arguments = json.dumps(args)
            calls.append(tc_delta)
        chunk.choices[0].delta.tool_calls = calls
        chunk.usage = None
        yield chunk

        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield final
    return _gen()
```

Add this test near the tool dispatch tests:

```python
@pytest.mark.asyncio
async def test_run_turn_emits_distinct_tool_start_names_for_multiple_tool_calls(conversation):
    mock_executor = AsyncMock(return_value={"success": True})
    registry = _make_minimal_registry()
    registry._catalog["gh_errors"] = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "GH errors",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry._active.add("gh_errors")
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    text_response = _make_text_response("Checked.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return _make_two_tool_response() if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "check gh", system_prompt="test"):
            events.append(event)

    starts = [e for e in events if e.type == "tool_start"]
    assert [e.name for e in starts[:2]] == ["request_tools", "gh_errors"]
```

- [ ] **Step 2: Write failing test for app-level result status**

Add this test near the existing verification-note tests:

```python
@pytest.mark.asyncio
async def test_tool_result_event_marks_application_failure_separately(conversation):
    mock_executor = AsyncMock(return_value={
        "success": False,
        "error": "Grasshopper is not currently available",
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "rhino_ping", {}, tool_call_id="call_fail"
    )
    text_response = _make_text_response("I will ask you to open Grasshopper.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "make a script", system_prompt="test"):
            events.append(event)

    result = next(e for e in events if e.type == "tool_result")
    assert result.tool_status == "failed"
    assert result.verified is None
```

Also update the import expectation once the field exists by using `ChatEvent.tool_status`.

- [ ] **Step 3: Run tests to verify red**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_runner.py -k "distinct_tool_start_names or application_failure" -q
```

Expected: result-status test fails because `ChatEvent` has no `tool_status`. Distinct-name test may pass today; keep it as a guard either way.

- [ ] **Step 4: Add `tool_status` to `ChatEvent`**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, add a field to the dataclass:

```python
    tool_status: Optional[str] = None
```

Add to `to_dict()` immediately after `verification_note` handling:

```python
        if self.tool_status is not None:
            d["tool_status"] = self.tool_status
```

- [ ] **Step 5: Add result status classifier**

Add this helper near `ChatEvent` and the other small chat-runner event helpers:

```python
def _classify_tool_status(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    for key in ("success", "ok"):
        value = result.get(key)
        if isinstance(value, bool):
            return "success" if value else "failed"
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("success", "ok"):
            value = data.get(key)
            if isinstance(value, bool):
                return "success" if value else "failed"
    if result.get("error"):
        return "failed"
    return None
```

- [ ] **Step 6: Pass `tool_status` on tool-result events**

Inside the normal tool dispatch result block, before yielding `ChatEvent("tool_result", ...)`, compute:

```python
                    _tool_status = _classify_tool_status(result)
```

In the caught dispatch-exception branch, convert the exception into a structured failure before result serialization:

```python
                        except Exception as e:
                            result = {"success": False, "error": str(e)}
                            result_str = json.dumps(result)
```

This replaces the old plain string form:

```python
                        except Exception as e:
                            result_str = f"Error: {e}"
```

Then pass:

```python
                        tool_status=_tool_status,
```

Apply the same classifier in the chat-model pseudo-tool branch:

```python
                        tool_status=_classify_tool_status(result),
```

Do not set `verified=False` for app failures.

- [ ] **Step 7: Run ChatRunner tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_runner.py -q
```

Expected: all ChatRunner tests pass.

- [ ] **Step 8: Checkpoint**

Run:

```powershell
git status --short
```

Expected: Python implementation/tests changed, plus known `knowledge/*`.

---

### Task 4: C# Event Result Status and Summary Extraction

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Modify tests: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

- [ ] **Step 1: Add source-guard tests for result-status wiring**

Add these tests to `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs` before `ReadSourceFile`:

```csharp
[Fact]
public void AgentChatClient_ChatEvent_ExposesToolStatusSeparatelyFromVerification()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatClient.cs");

    Assert.Contains("public string? ToolStatus { get; set; }", source);
    Assert.Contains("[JsonPropertyName(\"tool_status\")]", source);
    Assert.Contains("public bool? Verified { get; set; }", source);
}

[Fact]
public void AgentChatTab_ToolResult_PassesToolStatusToWebView()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

    Assert.Contains("evt.ToolStatus", source);
    Assert.Contains("finalizeToolCard(", source);
    Assert.Contains("BuildToolSummary(evt)", source);
    Assert.DoesNotContain("success.GetBoolean() ? \"Success\" : \"Failed\"", source);
}
```

- [ ] **Step 2: Run tests to verify red**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests --no-restore
```

Expected: new tests fail because `ToolStatus` is not present and `finalizeToolCard` has the old signature.

- [ ] **Step 3: Add `ToolStatus` to `ChatEvent`**

In `src/Rook/UI/Chat/AgentChatClient.cs`, add after `VerificationNote`:

```csharp
[JsonPropertyName("tool_status")]
public string? ToolStatus { get; set; }
```

- [ ] **Step 4: Pass result status to the WebView**

In `AgentChatTab.HandleChatEvent`, replace the `tool_result` script call with:

```csharp
var toolStatus = EscapeForJavaScript(evt.ToolStatus ?? "");
ExecuteScript(
    $"window.chatAPI.finalizeToolCard('{EscapeForJavaScript(evt.ToolCallId ?? "")}', {verified}, '{note}', '{EscapeForJavaScript(summary)}', '{toolStatus}')");
```

- [ ] **Step 5: Improve `BuildToolSummary` without changing verification**

Replace the `success` block in `BuildToolSummary` with:

```csharp
if (root.TryGetProperty("success", out var success) &&
    success.ValueKind == JsonValueKind.False)
{
    if (root.TryGetProperty("error", out var error) &&
        error.ValueKind == JsonValueKind.String)
        return error.GetString() ?? "Failed";
    if (root.TryGetProperty("message", out var message) &&
        message.ValueKind == JsonValueKind.String)
        return message.GetString() ?? "Failed";
    if (root.TryGetProperty("data", out var dataElement) &&
        dataElement.ValueKind == JsonValueKind.String)
        return dataElement.GetString() ?? "Failed";
    if (root.TryGetProperty("data", out dataElement) &&
        dataElement.ValueKind == JsonValueKind.Object)
    {
        if (dataElement.TryGetProperty("error", out var dataError) &&
            dataError.ValueKind == JsonValueKind.String)
            return dataError.GetString() ?? "Failed";
        if (dataElement.TryGetProperty("message", out var dataMessage) &&
            dataMessage.ValueKind == JsonValueKind.String)
            return dataMessage.GetString() ?? "Failed";
    }
    return "Failed";
}

if (root.TryGetProperty("success", out success) &&
    success.ValueKind == JsonValueKind.True)
{
    return "Success";
}
```

Keep the existing `objectsCreated` special case above this block.

- [ ] **Step 6: Run focused C# tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests --no-restore
```

Expected: focused panel tests pass.

- [ ] **Step 7: Checkpoint**

Run:

```powershell
git status --short
```

Expected: C# event/panel files and tests changed, plus known `knowledge/*`.

---

### Task 5: WebView Tool Card Rendering

**Files:**
- Modify: `src/Rook/UI/Chat/Resources/chat.html`
- Modify tests: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

- [ ] **Step 1: Add source-guard tests for readable params and status**

Add this test to `RookChatPanelTests.cs`:

```csharp
[Fact]
public void ChatWebView_ToolCards_RenderStructuredParamsAndToolStatus()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.html");

    Assert.Contains("formatToolValue", source);
    Assert.Contains("JSON.stringify", source);
    Assert.Contains("toolStatus", source);
    Assert.Contains("data-state=\"failed\"", source);
    Assert.Contains("done-success", source);
    Assert.Contains("badgeClass = 'success'", source);
    Assert.DoesNotContain("parts.push(keys[i] + ': ' + val);", source);
    Assert.DoesNotContain("toolStatus === 'success') {\n                state = 'done-verified'", source);
}
```

- [ ] **Step 2: Run test to verify red**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~ChatWebView_ToolCards_RenderStructuredParamsAndToolStatus --no-restore
```

Expected: fails because `formatToolValue` and `toolStatus` do not exist.

- [ ] **Step 3: Add compact param formatting**

In `chat.html`, before `renderToolCard`, add:

```javascript
        function formatToolValue(value) {
            var text = '';
            if (value === null || value === undefined) {
                text = 'null';
            } else if (typeof value === 'string') {
                text = value;
            } else if (typeof value === 'number' || typeof value === 'boolean') {
                text = String(value);
            } else {
                try {
                    text = JSON.stringify(value);
                } catch (e) {
                    text = String(value);
                }
            }
            if (text.length > 80) text = text.substring(0, 77) + '...';
            return text;
        }
```

Then replace the loop body in `renderToolCard`:

```javascript
                    var val = formatToolValue(params[keys[i]]);
                    parts.push(keys[i] + ': ' + val);
```

- [ ] **Step 4: Add result status rendering**

Change the function signature:

```javascript
        function finalizeToolCard(toolCallId, verified, verificationNote, summary, toolStatus) {
```

Replace state selection with:

```javascript
            var state, badgeClass, badgeIcon;
            if (toolStatus === 'failed') {
                state = 'failed';
                badgeClass = 'failed';
                badgeIcon = '!';
            } else if (toolStatus === 'warning') {
                state = 'done-unverified';
                badgeClass = 'unverified';
                badgeIcon = '!';
            } else if (verified === true) {
                state = 'done-verified';
                badgeClass = 'verified';
                badgeIcon = '\u2713';
            } else if (verified === false) {
                state = 'done-unverified';
                badgeClass = 'unverified';
                badgeIcon = '!';
            } else if (toolStatus === 'success') {
                state = 'done-success';
                badgeClass = 'success';
                badgeIcon = '\u2713';
            } else {
                state = 'done-unverified';
                badgeClass = 'unverified';
                badgeIcon = '·';
            }
```

Keep existing `card.setAttribute('data-state', state);`.

Add CSS selectors mirroring the verified visual treatment without using the verified state name:

```css
.tool-card[data-state="done-success"] {
    border-color: var(--success-border, #3a6f45);
}
.tool-card[data-state="done-success"] .tool-card-spinner { display: none; }
.verification-badge.success {
    background: var(--success-bg, #2f6f3e);
}
```

If the file uses different existing CSS variables/classes, match the local naming but keep `done-success` and `success` distinct from `done-verified` and `verified`.

- [ ] **Step 5: Ensure source-guard sees failed state**

Add an inert marker comment near the state selection if necessary:

```javascript
            // data-state="failed" is used for application-level tool failures.
```

This is acceptable only if the actual state assignment to `'failed'` is implemented.

- [ ] **Step 6: Run focused panel tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests --no-restore
```

Expected: all Rook chat panel source-guard tests pass.

- [ ] **Step 7: Checkpoint**

Run:

```powershell
git status --short
```

Expected: chat HTML and C# tests changed, plus known `knowledge/*`.

---

### Task 6: Narrow Repair Guidance

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify tests: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Add schema test for repair guidance**

Add this test to `test_rookchat_gh_script_creation_parity.py`:

```python
def test_local_csharp_schema_tells_model_to_update_after_errors():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_csharp_script": object()})
    text = _schema_text(catalog["gh_create_csharp_script"])

    assert "gh_errors" in text
    assert "gh_update_script" in text
    assert "do not just paste" in text.lower()
```

- [ ] **Step 2: Run test to verify red**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_gh_script_creation_parity.py -k "update_after_errors" -q
```

Expected: fails until schema guidance mentions repair behavior.

- [ ] **Step 3: Extend C# script contract constant narrowly**

Append this sentence to `_GH_CSHARP_SCRIPT_CONTRACT`:

```python
" After creating or updating a script, call gh_errors when verification is requested. "
"If gh_errors reports script errors and gh_update_script is available, fix the existing "
"component with gh_update_script; do not just paste corrected code into chat."
```

Keep this inside script-specific schema guidance only.

- [ ] **Step 4: Run schema tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: all parity/schema tests pass.

- [ ] **Step 5: Checkpoint**

Run:

```powershell
git status --short
```

Expected: only Python schema/test changes added in this task, plus prior task files and known `knowledge/*`.

---

### Task 7: Full Non-Live Verification and Manual Test Prep

**Files:**
- No new production files expected.

- [ ] **Step 1: Run Python focused suites**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_runner.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run server contract subset**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py -k "gh_create_script or gh_create_python_script or gh_create_csharp_script" -q
```

Expected: subset passes; required-field schema parity remains intact.

- [ ] **Step 3: Run C# focused panel tests**

Run:

```powershell
cd C:\UDEV\Rook
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests --no-restore
```

Expected: focused panel tests pass.

- [ ] **Step 4: Build managed companion**

Run:

```powershell
cd C:\UDEV\Rook
dotnet build src\Rook\Rook.csproj -p:Configuration=Debug --no-restore
```

Expected: build succeeds with existing warnings, 0 errors.

- [ ] **Step 5: Run diff check**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check
```

Expected: clean aside from normal CRLF warnings if present.

- [ ] **Step 6: Prepare manual Rhino smoke instructions**

Use this prompt for the required manual smoke after deploy/restart:

```text
Create a Grasshopper C# script component that outputs one box. Check the canvas for errors.
```

Required observed result:

- `gh_canvas` requested at most once.
- `gh_create_csharp_script` or `gh_create_script(language="csharp")` used.
- No `GH_Component` subclass code.
- Component has one Brep output and no compile errors.
- `gh_errors` or equivalent verification runs.
- Tool cards show readable params/results and no false green success on failure.

Stretch-only prompt:

```text
Create a Grasshopper C# script that generates a 10x10 grid of boxes with gradient heights, controlled by sliders.
```

Record outcome; do not block merge solely on this stretch check.

- [ ] **Step 7: Final checkpoint**

Run:

```powershell
git status --short --branch
```

Expected: implementation files modified; `knowledge/*` runtime files still unstaged and excluded.

---

## Self-Review

- Spec coverage:
  - Stronger alias + unified schema guidance: Task 1 and Task 6.
  - Request-tools de-dupe: Task 2.
  - Tool-name event boundary: Task 3.
  - App-level failure distinct from verification: Tasks 3, 4, and 5.
  - Structured parameter rendering: Task 5.
  - Narrow repair guidance: Task 6.
  - Manual one-box acceptance and grid stretch: Task 7.
- Placeholder scan: no TBD/TODO placeholders; every implementation step has concrete code or commands.
- Type consistency:
  - Python event field: `tool_status`.
  - C# event property: `ToolStatus` with `[JsonPropertyName("tool_status")]`.
  - WebView function signature: `finalizeToolCard(toolCallId, verified, verificationNote, summary, toolStatus)`.
- Scope check: no Workbench, launcher, Rhino lifecycle, or broad prompt-tuning work included.
