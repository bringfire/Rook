# RunScript P0/P1 Containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make normal RunScript-backed command execution fail closed by default and remove autonomous Rhino prompt driving from normal execution paths.

**Architecture:** This first implementation slice covers P0 `rhino_command` containment and P1 interactive start/send deprecation from the approved design. Python preflight becomes the first fail-closed gate, native `/command` gets delayed post-dispatch prompt verification plus bounded worker waits, MCP and chat tool surfaces stop advertising start/send and learning tools, SmartExecutor stops planning or falling back to interactive execution, and native `/command/start` plus `/command/send` refuse normal calls unless explicit dev learning mode is enabled. Full dispatcher modal allowlisting and shared native quarantine are preserved as the next RunScript safety slice.

**Tech Stack:** Python MCP server and tests (`pytest`), C++ RookNative handlers, nlohmann/json, httplib, Rhino 8 C++ SDK.

---

## Scope Constraints

- Treat unknown command safety as rejection, not as permission.
- P0 production safe set is empty unless command knowledge explicitly carries `safe_non_interactive` metadata.
- Tests may create fake command knowledge with safe metadata to prove the allow path.
- Remove start/send from normal tool listings and also return route-level structured refusals if those names or native endpoints remain reachable.
- Remove interactive command-learning tools from normal listings and route them through the same dev/learning refusal gate.
- Dev/learning mode must stay disabled inside the panel-locked Claude Code path even if `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1` is present.
- Do not clear any native quarantine from prompt idle alone in this slice. The stronger native-state quarantine work is a separate P2 implementation plan.
- Do not recommend `rhino_command_interactive_send` in any normal recovery guidance.

## File Structure

- Modify `mcp_server/src/rook/preflight.py`: add structured RunScript safety refusals and explicit safe command/mode classification.
- Create `mcp_server/tests/test_preflight_rhino_command_safety.py`: focused unit tests for fail-closed command preflight.
- Modify `mcp_server/src/rook/server.py`: update `rhino_command` description, remove start/send and interactive learning tools from normal listings, add direct-call refusal for start/send and interactive learning outside dev learning mode.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: remove start/send from `rhino_commands` and remove interactive learning tools from normal command-learning groups.
- Modify `mcp_server/src/rook/agent/chat/execution_policy.py`: replace send-based recovery guidance with inspect/cancel/retry-safe-path guidance.
- Modify `mcp_server/src/rook/learning/intent_planner.py`: stop emitting `fallbacks=["interactive"]`.
- Modify `mcp_server/src/rook/learning/smart_executor.py`: stop executing or falling back to `execution_route="interactive"`.
- Modify `src/RookNative/Handlers/CommandHandler.cpp`: add delayed prompt verification for `/command` and bounded worker wait with structured blocked response.
- Modify `src/RookNative/Handlers/CommandInteractiveHandler.cpp`: refuse `/command/start` and `/command/send` outside `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`.
- Modify existing tests in `mcp_server/tests/test_server_contract_hardening.py`, `mcp_server/tests/test_execution_policy.py`, `mcp_server/tests/test_intent_planner.py`, `mcp_server/tests/test_smart_executor.py`, and `mcp_server/tests/test_phase2_dispatcher.py` where they assert the old interactive execution behavior.

---

### Task 1: Add Fail-Closed Preflight Tests

**Files:**
- Create: `mcp_server/tests/test_preflight_rhino_command_safety.py`
- Test target: `mcp_server/src/rook/preflight.py`

- [ ] **Step 1: Write focused failing tests**

Create `mcp_server/tests/test_preflight_rhino_command_safety.py` with:

```python
from types import SimpleNamespace

from rook.preflight import preflight_rhino_command


class FakeKnowledgeStore:
    def __init__(self, command=None, parsed=None):
        self.command = command
        self.parsed = parsed or {
            "command": "-Box",
            "mode": "default",
            "syntax": "_-Box <corner1> <corner2> [height]",
            "parameters": {"corner1": "0,0,0", "corner2": "1,1,0"},
            "options_used": [],
        }

    def parse_command_string(self, _command_text):
        return self.parsed

    def get_command(self, _cmd_name):
        return self.command


def _command(preconditions=None, options=None, modes=None):
    return SimpleNamespace(
        preconditions=preconditions or {},
        options=options or {},
        modes=modes or {"default": SimpleNamespace(syntax="_-Box <corner1> <corner2> [height]")},
    )


def test_rejects_when_knowledge_store_unavailable():
    result = preflight_rhino_command("_-Box 0,0,0 1,1,0", None)

    assert result is not None
    assert result["success"] is False
    assert result["data"]["error"] == "run_script_safety_refusal"
    assert result["data"]["reason"] == "command_safety_unavailable"


def test_rejects_unknown_command_from_store():
    store = FakeKnowledgeStore(command=None)

    result = preflight_rhino_command("_-Box 0,0,0 1,1,0", store)

    assert result is not None
    assert result["success"] is False
    assert result["data"]["reason"] == "unknown_command"
    assert result["data"]["command"] == "-Box"


def test_rejects_known_command_without_explicit_safe_metadata():
    store = FakeKnowledgeStore(command=_command())

    result = preflight_rhino_command("_-Box 0,0,0 1,1,0", store)

    assert result is not None
    assert result["success"] is False
    assert result["data"]["reason"] == "command_not_marked_safe_non_interactive"
    assert result["data"]["mode"] == "default"


def test_allows_known_command_with_command_level_safe_metadata():
    store = FakeKnowledgeStore(command=_command(preconditions={"safe_non_interactive": True}))

    result = preflight_rhino_command("_-Box 0,0,0 1,1,0", store)

    assert result is None


def test_allows_known_command_with_mode_safe_metadata():
    store = FakeKnowledgeStore(command=_command(preconditions={"safe_non_interactive_modes": ["center"]}))
    store.parsed = {
        "command": "-Box",
        "mode": "center",
        "syntax": "_-Box _Center <center> <corner> [height]",
        "parameters": {"center": "0,0,0", "corner": "1,1,0"},
        "options_used": ["_Center"],
    }
    store.command.options = {"_Center": "Create from center"}
    store.command.modes = {
        "center": SimpleNamespace(syntax="_-Box _Center <center> <corner> [height]")
    }

    result = preflight_rhino_command("_-Box _Center 0,0,0 1,1,0", store)

    assert result is None
```

- [ ] **Step 2: Run the new tests and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py -q
```

Expected: tests fail because `preflight_rhino_command` currently allows missing knowledge stores, unknown commands, and known commands without safe metadata.

---

### Task 2: Implement Explicit Command Safety Classification

**Files:**
- Modify: `mcp_server/src/rook/preflight.py`
- Test: `mcp_server/tests/test_preflight_rhino_command_safety.py`

- [ ] **Step 1: Add structured refusal helpers**

In `mcp_server/src/rook/preflight.py`, below the imports, add:

```python
RUNSCRIPT_REFUSAL_ERROR = "run_script_safety_refusal"


def _runscript_refusal(
    reason: str,
    command: str,
    *,
    mode: str = "unknown",
    recovery: str = "Use a typed Rook tool or a known-safe fully scripted command.",
) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "error": RUNSCRIPT_REFUSAL_ERROR,
            "reason": reason,
            "command": command,
            "mode": mode,
            "verified": False,
            "recovery": recovery,
        },
    }
```

- [ ] **Step 2: Add metadata reader helpers**

Still in `preflight.py`, add:

```python
def _get_mapping_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _safe_modes_from_metadata(metadata: Any) -> set[str]:
    raw = _get_mapping_value(metadata, "safe_non_interactive_modes", [])
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, (list, tuple, set)):
        return {item for item in raw if isinstance(item, str)}
    return set()


def _is_safe_non_interactive(cmd_knowledge: Any, mode: str) -> bool:
    preconditions = _get_mapping_value(cmd_knowledge, "preconditions", {}) or {}
    if _get_mapping_value(preconditions, "safe_non_interactive", False) is True:
        return True
    if mode in _safe_modes_from_metadata(preconditions):
        return True

    modes = _get_mapping_value(cmd_knowledge, "modes", {}) or {}
    mode_data = modes.get(mode) if isinstance(modes, dict) else None
    if mode_data is not None:
        if _get_mapping_value(mode_data, "safe_non_interactive", False) is True:
            return True
        if mode in _safe_modes_from_metadata(mode_data):
            return True

    return False
```

- [ ] **Step 3: Reject unavailable and unknown safety metadata**

In `preflight_rhino_command`, replace:

```python
    if knowledge_store is None:
        return None
```

with:

```python
    if knowledge_store is None:
        return _runscript_refusal(
            "command_safety_unavailable",
            first_token,
            recovery="Rook could not load command safety metadata. Use typed tools instead of rhino_command.",
        )
```

Then replace:

```python
    if cmd_knowledge is None:
        return None
```

with:

```python
    mode = parsed.get("mode", "unknown")
    mode = mode if isinstance(mode, str) and mode else "unknown"

    if cmd_knowledge is None:
        return _runscript_refusal("unknown_command", cmd_name, mode=mode)

    if not _is_safe_non_interactive(cmd_knowledge, mode):
        return _runscript_refusal(
            "command_not_marked_safe_non_interactive",
            cmd_name,
            mode=mode,
        )
```

Keep the existing missing-required and unknown-option checks after this block.

- [ ] **Step 4: Run focused preflight tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_preflight_rhino_command_safety.py -q
```

Expected: all tests in `test_preflight_rhino_command_safety.py` pass.

- [ ] **Step 5: Run existing command contract tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py -q
```

Expected: failures where tests use fake known commands without `safe_non_interactive` metadata.

- [ ] **Step 6: Update existing fake command knowledge**

In `mcp_server/tests/test_server_contract_hardening.py`, update fake command objects that are intended to reach unknown-option validation by adding safe metadata:

```python
        get_command=lambda _cmd: SimpleNamespace(
            options={"_Center": "Create from center"},
            modes={"default": SimpleNamespace(syntax="_-Box _Center <center> <corner> [height]")},
            preconditions={"safe_non_interactive": True},
        ),
```

- [ ] **Step 7: Re-run command contract tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_preflight_rhino_command_safety.py -q
```

Expected: both files pass.

- [ ] **Step 8: Commit Task 1-2**

Run:

```powershell
git add mcp_server/src/rook/preflight.py mcp_server/tests/test_preflight_rhino_command_safety.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix: fail closed for unsafe rhino commands"
```

---

### Task 3: Deprecate MCP Start/Send and Update Tool Guidance

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Test: `mcp_server/tests/test_phase2_dispatcher.py`
- Test: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add MCP deprecation helpers**

In `mcp_server/src/rook/server.py`, near `_preflight_rhino_command`, add:

```python
def _interactive_command_learning_enabled() -> bool:
    if os.getenv("ROOK_MCP_TARGET_MODE") == "panel_locked":
        return False
    return os.getenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING") == "1"


def _interactive_command_deprecated_result(tool_name: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "error": "interactive_command_deprecated",
            "tool": tool_name,
            "verified": False,
            "recovery": (
                "Autonomous Rhino prompt driving is disabled. Use typed Rook tools, "
                "a known-safe fully scripted rhino_command, rhino_command_interactive_prompt "
                "to inspect state, or rhino_command_interactive_cancel to recover."
            ),
        },
    }
```

`server.py` already imports `os` and `Any`; if either import is missing in the current branch, add it to the existing import section instead of adding a duplicate import lower in the file.

The explicit `ROOK_MCP_TARGET_MODE == "panel_locked"` check is load-bearing: the embedded Claude Code panel must not be able to re-enable interactive prompt driving by inheriting a developer shell environment.

- [ ] **Step 2: Update `rhino_command` tool description**

In the `Tool(name="rhino_command", ...)` block, replace the description string with:

```python
description=(
    "Run a Rhino command string only when it is known-safe, non-interactive, "
    "and fully parameterized. Commands must start with '_' for locale-independent "
    "execution. Unknown, ambiguous, prompt-driven, or unclassified commands are "
    "rejected; use typed Rook tools when possible."
),
```

- [ ] **Step 3: Remove start/send and interactive learning Tool entries from normal listing**

In `server.py`, remove the two `Tool(...)` blocks whose names are:

```python
name="rhino_command_interactive_start"
name="rhino_command_interactive_send"
```

Leave `rhino_command_interactive_prompt` and `rhino_command_interactive_cancel` listed.

Also remove the `Tool(...)` block whose name is:

```python
name="rhino_learn_interactive"
```

If `rhino_learn_variations_interactive` is still listed next to it, remove that `Tool(...)` block from normal listings too because it drives the same interactive command protocol.

- [ ] **Step 4: Add direct-call refusal in `call_tool` dispatch**

In the `case "rhino_command_interactive_start":` block, wrap the existing case body in an `else`. Do not use `break`; Python `match` cases are not loops. The shape should be:

```python
        case "rhino_command_interactive_start":
            if not _interactive_command_learning_enabled():
                result = _interactive_command_deprecated_result("rhino_command_interactive_start")
            else:
                command = arguments.get("command")
                # Existing start implementation remains indented under this else.
```

In the `case "rhino_command_interactive_send":` block, use the same `if/else` shape:

```python
        case "rhino_command_interactive_send":
            if not _interactive_command_learning_enabled():
                result = _interactive_command_deprecated_result("rhino_command_interactive_send")
            else:
                input_text = arguments.get("input", "")
                # Existing send implementation remains indented under this else.
```

In the `case "rhino_learn_interactive":` block, add:

```python
        case "rhino_learn_interactive":
            if not _interactive_command_learning_enabled():
                result = _interactive_command_deprecated_result("rhino_learn_interactive")
            else:
                command = arguments.get("command")
                # Existing learn implementation remains indented under this else.
```

If `case "rhino_learn_variations_interactive":` exists, gate it the same way:

```python
        case "rhino_learn_variations_interactive":
            if not _interactive_command_learning_enabled():
                result = _interactive_command_deprecated_result("rhino_learn_variations_interactive")
            else:
                command = arguments.get("command")
                # Existing variations implementation remains indented under this else.
```

- [ ] **Step 5: Remove start/send from normal agent command group**

In `mcp_server/src/rook/agent/tool_groups.py`, change the `rhino_commands` group from:

```python
    "rhino_commands": [
        "rhino_command", "rhino_execute",
        "rhino_command_interactive_start", "rhino_command_interactive_send",
        "rhino_command_interactive_prompt", "rhino_command_interactive_cancel",
    ],
```

to:

```python
    "rhino_commands": [
        "rhino_command", "rhino_execute",
        "rhino_command_interactive_prompt", "rhino_command_interactive_cancel",
    ],
```

In the command-learning group, remove interactive learning tools from normal group loading. Change any list containing:

```python
"rhino_learn_interactive", "rhino_learn_variations_interactive"
```

so those names are absent. Keep non-interactive knowledge tools such as `rhino_command_knowledge`, `rhino_knowledge_query`, `rhino_command_knowledge_reload`, `rhino_command_observations`, `rhino_command_consolidate`, `rhino_learning_progress`, `rhino_command_select`, and `rhino_command_queue`.

This plan intentionally does not add conditional listing for dev/learning mode. Dev-gated interactive learning remains direct-call-only in this slice so normal tool discovery cannot accidentally reintroduce it.

- [ ] **Step 6: Update phase dispatcher tests**

In `mcp_server/tests/test_phase2_dispatcher.py`, update the assertion that expects start/send inside `TOOL_GROUPS["rhino_commands"]`. The group should now assert prompt/cancel remain and start/send are absent:

```python
assert "rhino_command_interactive_prompt" in TOOL_GROUPS["rhino_commands"]
assert "rhino_command_interactive_cancel" in TOOL_GROUPS["rhino_commands"]
assert "rhino_command_interactive_start" not in TOOL_GROUPS["rhino_commands"]
assert "rhino_command_interactive_send" not in TOOL_GROUPS["rhino_commands"]
assert "rhino_learn_interactive" not in TOOL_GROUPS["command_learning"]
assert "rhino_learn_variations_interactive" not in TOOL_GROUPS["command_learning"]
```

- [ ] **Step 7: Add direct-call deprecation tests**

In `mcp_server/tests/test_server_contract_hardening.py`, add:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("rhino_command_interactive_start", {"command": "_-Box"}),
        ("rhino_command_interactive_send", {"input": "0,0,0"}),
        ("rhino_learn_interactive", {"command": "_-Box", "inputs": ["0,0,0"]}),
        ("rhino_learn_variations_interactive", {"command": "_-Box", "variations": [["0,0,0"]]}),
    ],
)
async def test_interactive_start_send_are_deprecated_in_normal_mode(monkeypatch, patched_server, tool_name, args):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(tool_name, args)
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "interactive_command_deprecated"
    assert payload["data"]["tool"] == tool_name
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("rhino_learn_interactive", {"command": "_-Box", "inputs": ["0,0,0"]}),
        ("rhino_learn_variations_interactive", {"command": "_-Box", "variations": [["0,0,0"]]}),
    ],
)
async def test_interactive_learning_stays_disabled_in_panel_locked_mode(monkeypatch, patched_server, tool_name, args):
    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool(tool_name, args)
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "interactive_command_deprecated"
    assert payload["data"]["tool"] == tool_name
    call_rhino_mock.assert_not_called()


@pytest.mark.asyncio
async def test_rhino_command_rejects_when_command_safety_store_unavailable(monkeypatch, patched_server):
    monkeypatch.setattr(server, "command_learner", SimpleNamespace(knowledge_store=None))
    call_rhino_mock = AsyncMock()
    monkeypatch.setattr(server, "call_rhino", call_rhino_mock)

    response = await server.call_tool("rhino_command", {"command": "_-Box 0,0,0 1,1,0"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["error"] == "run_script_safety_refusal"
    assert payload["data"]["reason"] == "command_safety_unavailable"
    call_rhino_mock.assert_not_called()
```

If `_decode_response` assumes error payloads are strings, update it so JSON error strings decode into dicts:

```python
def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        raw = text[len("Error: "):]
        try:
            return {"success": False, "data": json.loads(raw)}
        except json.JSONDecodeError:
            return {"success": False, "data": raw}
    return {"success": True, "data": json.loads(text)}
```

- [ ] **Step 8: Run MCP surface tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_phase2_dispatcher.py -q
```

Expected: both files pass.

- [ ] **Step 9: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_phase2_dispatcher.py
git commit -m "fix: deprecate interactive command tools"
```

---

### Task 4: Remove Send-Based Recovery Guidance

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/execution_policy.py`
- Test: `mcp_server/tests/test_execution_policy.py`

- [ ] **Step 1: Update the recovery note**

In `execution_policy.py`, replace the active prompt annotation:

```python
            annotations.append(
                f"Rhino is waiting for input (prompt: {prompt_text!r}). "
                "The command did not complete. Cancel with "
                "rhino_command_interactive_cancel, or supply the required "
                "input via rhino_command_interactive_send."
            )
```

with:

```python
            annotations.append(
                f"Rhino is waiting for input (prompt: {prompt_text!r}). "
                "The command did not complete. Inspect state with "
                "rhino_command_prompt, cancel with rhino_command_interactive_cancel, "
                "then retry through typed Rook tools or a known-safe fully scripted "
                "rhino_command."
            )
```

- [ ] **Step 2: Update execution-policy tests**

In `mcp_server/tests/test_execution_policy.py`, update `test_active_prompt_overrides_to_unverified`:

```python
def test_active_prompt_overrides_to_unverified():
    prompt_state = {"success": True, "data": {"is_active": True, "prompt": "Select objects"}}
    result = annotate_result(
        "rhino_command",
        {"success": True, "data": {}},
        prompt_state=prompt_state,
    )
    note = result["verification_note"]
    assert result["verified"] is False
    assert "Select objects" in note
    assert "rhino_command_prompt" in note
    assert "rhino_command_interactive_cancel" in note
    assert "rhino_command_interactive_send" not in note
```

- [ ] **Step 3: Run execution policy tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_execution_policy.py -q
```

Expected: all execution policy tests pass.

- [ ] **Step 4: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/agent/chat/execution_policy.py mcp_server/tests/test_execution_policy.py
git commit -m "fix: remove interactive send recovery guidance"
```

---

### Task 5: Remove SmartExecutor Interactive Fallback

**Files:**
- Modify: `mcp_server/src/rook/learning/smart_executor.py`
- Test: `mcp_server/tests/test_smart_executor.py`

- [ ] **Step 1: Update module documentation**

In `smart_executor.py`, replace the top module docstring text that lists interactive execution as a normal substrate with:

```python
"""Smart Executor: ExecutionPlan -> ExecutionResult via safe substrates.

The executor is the second stage of the intent runtime. It takes a typed
ExecutionPlan (produced by IntentPlanner) and executes it through safe normal
execution routes:

  1. DIRECT API  — typed HTTP call to C++ plugin (fastest, most reliable)
  2. KNOWN COMMAND — known-safe fully scripted command string via /command

Autonomous interactive Rhino prompt driving is deprecated for normal execution.
The executor does not call /command/start or /command/send as a fallback.
"""
```

- [ ] **Step 2: Refuse interactive execution routes**

In `SmartExecutor.execute`, replace:

```python
        elif plan.execution_route == "interactive":
            result = await self._execute_interactive(plan, trace)
```

with:

```python
        elif plan.execution_route == "interactive":
            trace.append("Interactive execution route is deprecated")
            result = ExecutionResult(
                success=False,
                intent=plan.intent,
                route_taken="interactive",
                failure=ExecutionFailure(
                    layer=FailureLayer.ROUTING,
                    operation=plan.operation,
                    attempted_route="interactive",
                    error_detail="Interactive Rhino command execution is disabled for normal execution.",
                    recovery_suggestion=(
                        "Use typed Rook tools or a known-safe fully scripted command. "
                        "Use rhino_command_prompt and rhino_command_interactive_cancel only for recovery."
                    ),
                ),
            )
```

- [ ] **Step 3: Stop known-command escalation**

In `_execute_command`, replace the stalled prompt block:

```python
            # Attempt interactive fallback if available
            if "interactive" in plan.fallbacks:
                trace.append("Escalating to interactive mode")
                return await self._interactive_fallback(plan, stalled_prompt, trace)

            return ExecutionResult(
```

with:

```python
            return ExecutionResult(
```

Then change the recovery suggestion in that returned `ExecutionFailure` from:

```python
                        "The command requires interactive input. "
                        "Re-plan with execution_route='interactive' or provide missing parameters."
```

to:

```python
                        "The command requires interactive input. Cancel or inspect Rhino state, "
                        "then use typed Rook tools or provide a complete known-safe scripted command."
```

- [ ] **Step 4: Remove unused interactive helper methods**

Delete `_execute_interactive` and `_interactive_fallback` from `smart_executor.py`.

If `_poll_prompt` and `_safe_cancel` are only used by `_execute_interactive`, delete them too. Confirm with:

```powershell
rg -n "_poll_prompt|_safe_cancel|_execute_interactive|_interactive_fallback" mcp_server/src/rook/learning/smart_executor.py
```

Expected after deletion: no matches for these private method names.

- [ ] **Step 5: Update SmartExecutor tests**

In `mcp_server/tests/test_smart_executor.py`, replace `test_stalled_command_escalates_to_interactive` with:

```python
    def test_stalled_command_does_not_escalate_to_interactive(self):
        """Command stalls even with legacy fallback metadata; executor refuses instead."""
        calls = []

        async def sequenced_caller(endpoint, method="POST", data=None):
            calls.append(endpoint)
            if endpoint == "/command":
                return {"success": False, "data": {"waitingFor": "Select rail"}}
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=sequenced_caller)
        plan = ExecutionPlan(
            intent="sweep curve",
            operation="command:_-Sweep1",
            execution_route="known_command",
            command="_-Sweep1",
            syntax="_-Sweep1 _SelID curve1 _Enter",
            fallbacks=["interactive"],
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.failure.layer == FailureLayer.INTERACTIVE_PROMPT
        assert result.failure.attempted_route == "known_command"
        assert "/command/start" not in calls
        assert "/command/send" not in calls
```

Replace the whole `TestInteractiveExecution` class with:

```python
class TestInteractiveExecutionDeprecated:

    def test_interactive_route_is_refused_without_calling_rhino(self):
        calls = []

        async def caller(endpoint, method="POST", data=None):
            calls.append(endpoint)
            return {"success": True, "data": {}}

        executor = SmartExecutor(http_caller=caller)
        plan = ExecutionPlan(
            intent="loft curves",
            operation="command:_-Loft",
            execution_route="interactive",
            command="_-Loft",
            syntax="_-Loft _SelID a _SelID b _Enter",
        )
        result = run(executor.execute(plan))

        assert result.success is False
        assert result.route_taken == "interactive"
        assert result.failure.layer == FailureLayer.ROUTING
        assert "disabled" in result.failure.error_detail.lower()
        assert calls == []
```

- [ ] **Step 6: Run SmartExecutor tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_smart_executor.py -q
```

Expected: all SmartExecutor tests pass.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/learning/smart_executor.py mcp_server/tests/test_smart_executor.py
git commit -m "fix: disable interactive command fallback"
```

---

### Task 6: Stop Planning Interactive Fallbacks

**Files:**
- Modify: `mcp_server/src/rook/learning/intent_planner.py`
- Test: `mcp_server/tests/test_intent_planner.py`

- [ ] **Step 1: Remove interactive fallback emission**

In `intent_planner.py`, replace:

```python
            fallbacks=["interactive"],
```

with:

```python
            fallbacks=[],
```

- [ ] **Step 2: Update planner test**

In `mcp_server/tests/test_intent_planner.py`, update `test_falls_back_to_command_path`:

```python
    def test_falls_back_to_command_path(self, mock_knowledge_store):
        planner = IntentPlanner(knowledge_store=mock_knowledge_store)
        planner._ensure_dspy = lambda: False

        plan = run(planner.plan("loft through these curves"))
        assert plan.execution_route == "known_command"
        assert plan.command == "_-Loft"
        assert plan.syntax is not None
        assert plan.fallbacks == []
```

- [ ] **Step 3: Run planner tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_intent_planner.py -q
```

Expected: all planner tests pass.

- [ ] **Step 4: Commit Task 6**

Run:

```powershell
git add mcp_server/src/rook/learning/intent_planner.py mcp_server/tests/test_intent_planner.py
git commit -m "fix: stop planning interactive command fallback"
```

---

### Task 7: Add Native `/command` Delayed Prompt Check and Bounded Wait

**Files:**
- Modify: `src/RookNative/Handlers/CommandHandler.cpp`

- [ ] **Step 1: Add chrono include**

In `CommandHandler.cpp`, add:

```cpp
#include <chrono>
```

near the existing standard library includes.

- [ ] **Step 2: Tighten prompt idle helpers**

In the anonymous namespace, replace:

```cpp
    bool IsInteractivePrompt(const std::string& prompt)
    {
        return !prompt.empty() && prompt.find("Command") == std::string::npos;
    }
```

with:

```cpp
    bool IsIdleCommandPrompt(const std::string& prompt)
    {
        return prompt.empty()
            || prompt == "Command"
            || prompt.rfind("Command:", 0) == 0;
    }

    bool IsInteractivePrompt(const std::string& prompt)
    {
        return !IsIdleCommandPrompt(prompt);
    }

    std::string ReadCommandPromptOnMain()
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([]() -> std::string
        {
            ON_wString prompt;
            RhinoApp().GetCommandPrompt(prompt);
            return WideToUtf8(prompt);
        });

        return future.get();
    }

    void CancelCommandOnMain(unsigned int docSn)
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([docSn]()
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            const unsigned int docRuntimeSn = pDoc->RuntimeSerialNumber();
            RhinoApp().RunScript(docRuntimeSn, L"_Cancel\n", 0);
        });

        future.get();
    }
```

This aligns `/command` prompt interpretation with `/command/prompt` prefix matching and gives the worker thread a way to re-check prompt state after Rhino's message loop has a chance to process the command.

- [ ] **Step 3: Add bounded wait for the `/command` dispatch future**

In `HandleCommand`, replace:

```cpp
        auto result = future.get();
```

with:

```cpp
        const auto status = future.wait_for(std::chrono::seconds(30));
        if (status == std::future_status::timeout)
        {
            nlohmann::json data;
            data["error"] = "rhino_execution_blocked";
            data["reason"] = "rhino_command_timeout";
            data["command"] = command;
            data["verified"] = false;
            data["timeout_seconds"] = 30;
            data["recovery"] =
                "Rhino did not finish the command in time. Inspect state with "
                "rhino_command_prompt or cancel with rhino_command_interactive_cancel "
                "before sending further mutating calls.";
            CRookServer::SendErrorData(res, data);
            return;
        }

        auto result = future.get();
```

Do not claim this unwinds the UI-thread command. It only stops the HTTP worker from blocking forever and returns a structured blocked-state response.

- [ ] **Step 4: Add delayed post-dispatch prompt verification**

Still in the `try` block of `HandleCommand`, immediately after `auto result = future.get();`, add:

```cpp
        if (result.success)
        {
            std::string activePrompt;
            for (int attempt = 0; attempt < 10; ++attempt)
            {
                ::Sleep(100);
                const std::string promptStr = ReadCommandPromptOnMain();
                if (IsInteractivePrompt(promptStr))
                {
                    activePrompt = promptStr;
                    break;
                }
            }

            if (!activePrompt.empty())
            {
                CancelCommandOnMain(docSn);

                result.success = false;
                result.data = nlohmann::json::object();
                result.data["command"] = command;
                result.data["executed"] = false;
                result.data["error"] =
                    "Command went interactive after RunScript returned. "
                    "Use typed Rook tools or provide a complete known-safe scripted command.";
                result.data["waitingFor"] = activePrompt;
                result.data["verified"] = false;
                result.data["objectsCreated"] = 0;
                result.data["objectIds"] = nlohmann::json::array();
            }
        }
```

This is deliberately outside the original dispatch lambda. Sleeping inside the main-thread lambda would block Rhino's message pump and can miss the prompt transition. Polling on the worker, then dispatching prompt reads, gives Rhino up to 1 second to expose delayed modal prompts before `/command` reports success. If any poll observes an active prompt, the command is treated as failed and cancelled.

- [ ] **Step 5: Build native project if the Rhino/MFC toolchain is available**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If the Rhino SDK or MFC toolchain is unavailable, record that native build verification could not be run.

- [ ] **Step 6: Commit Task 7**

Run:

```powershell
git add src/RookNative/Handlers/CommandHandler.cpp
git commit -m "fix: bound native rhino command execution"
```

---

### Task 8: Refuse Native `/command/start` and `/command/send` Outside Dev Learning Mode

**Files:**
- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`

- [ ] **Step 1: Add native dev-gate helpers**

In `CommandInteractiveHandler.cpp`, inside the anonymous namespace after `ReadPromptOnMain`, add:

```cpp
bool IsInteractiveCommandLearningEnabled()
{
    wchar_t value[16] = {};
    DWORD len = ::GetEnvironmentVariableW(
        L"ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING",
        value,
        static_cast<DWORD>(std::size(value)));

    return len == 1 && value[0] == L'1';
}

bool RejectInteractiveCommandExecutionIfDisabled(
    httplib::Response& res,
    const char* route)
{
    if (IsInteractiveCommandLearningEnabled())
        return false;

    nlohmann::json data;
    data["error"] = "interactive_command_deprecated";
    data["route"] = route;
    data["verified"] = false;
    data["recovery"] =
        "Autonomous Rhino prompt driving is disabled. Use typed Rook tools, "
        "a known-safe fully scripted command, /command/prompt to inspect state, "
        "or /command/cancel to recover.";

    CRookServer::SendErrorData(res, data);
    return true;
}
```

If `std::size` is unavailable under the current project language settings, replace `static_cast<DWORD>(std::size(value))` with:

```cpp
static_cast<DWORD>(sizeof(value) / sizeof(value[0]))
```

- [ ] **Step 2: Gate `HandleCommandStart`**

At the top of `HandleCommandStart`, before body parsing, add:

```cpp
    if (RejectInteractiveCommandExecutionIfDisabled(res, "/command/start"))
        return;
```

- [ ] **Step 3: Gate `HandleCommandInput`**

At the top of `HandleCommandInput`, before body parsing, add:

```cpp
    if (RejectInteractiveCommandExecutionIfDisabled(res, "/command/send"))
        return;
```

- [ ] **Step 4: Verify prompt/cancel are not gated**

Inspect the file and confirm no gate was added to:

```cpp
void HandleCommandPrompt(const httplib::Request& /*req*/, httplib::Response& res)
void HandleCommandCancel(const httplib::Request& /*req*/, httplib::Response& res)
```

Run:

```powershell
Select-String -LiteralPath src/RookNative/Handlers/CommandInteractiveHandler.cpp -Pattern "RejectInteractiveCommandExecutionIfDisabled|HandleCommandPrompt|HandleCommandCancel"
```

Expected: the reject helper is called only from `HandleCommandStart` and `HandleCommandInput`.

- [ ] **Step 5: Build native project if the Rhino/MFC toolchain is available**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If the Rhino SDK or MFC toolchain is unavailable, record that native build verification could not be run and keep the code review focused on compile-visible API usage from neighboring code.

- [ ] **Step 6: Commit Task 8**

Run:

```powershell
git add src/RookNative/Handlers/CommandInteractiveHandler.cpp
git commit -m "fix: gate native interactive command routes"
```

---

### Task 9: Run Integrated Verification

**Files:**
- Verify all files changed by Tasks 1-8.

- [ ] **Step 1: Run targeted Python tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_preflight_rhino_command_safety.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_execution_policy.py `
  mcp_server/tests/test_smart_executor.py `
  mcp_server/tests/test_intent_planner.py `
  mcp_server/tests/test_phase2_dispatcher.py `
  -q
```

Expected: all targeted Python tests pass.

- [ ] **Step 2: Search for stale interactive execution guidance**

Run:

```powershell
rg -n "rhino_command_interactive_send|execution_route=\"interactive\"|fallbacks=\\[\"interactive\"\\]|Escalating to interactive|Use rhino_command_interactive_start|Use rhino_command_interactive_\\*" mcp_server/src mcp_server/tests docs/superpowers/specs docs/superpowers/plans
```

Expected: matches only in historical docs/postmortems, dev-gated refusal text, test names that assert deprecation, or approved design/spec discussion. No normal tool description or recovery note should recommend start/send.

- [ ] **Step 3: Check git diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` shows only intentional changes if any task has not yet been committed.

- [ ] **Step 4: Final commit if integration cleanup changed files**

If Task 9 required cleanup edits, commit them:

```powershell
git add <changed-files>
git commit -m "test: align RunScript safety coverage"
```

If there are no cleanup edits, do not create an empty commit.

---

## Follow-Up Slice After This Plan

Create a separate P2 implementation plan for:

- Native RunScript quarantine state.
- Strong native state checks for clearing quarantine.
- Dispatcher modal allowlist.
- Shared MCP/chat verification convergence for every RunScript-backed route.
- `rhino_execute` runtime quarantine and expanded static checks.

That slice should not reuse prompt idle alone as a quarantine-clear signal.
