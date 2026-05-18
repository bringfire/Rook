# Post-Mortem: Interactive Rhino Command Cascade Failure

**Date:** 2026-05-18
**Severity:** High — silently blocks Rhino UI, causes cascading tool failures
**Status:** Documented, pending code fixes
**Owner:** Rook tooling (`rhino_command` / `CommandHandler.cpp`)

---

## 1. Executive Summary

When an AI agent (Claude) uses the `rhino_command` MCP tool to run a Rhino command, certain commands trigger **interactive prompts** (GetPoint, GetObject, option dialogs) that the agent cannot see or respond to. The current architecture has a post-hoc detection mechanism that attempts to catch this, but it has fundamental gaps. When detection fails, Rhino's UI thread blocks waiting for input that will never arrive, and the agent — unaware anything is wrong — continues issuing more tool calls that pile up behind the blocked thread.

The result is a **silent cascade**: Rhino hangs, all subsequent MCP calls queue up behind the blocked main thread, and the agent has no signal that anything has gone wrong. The user must manually switch to Rhino and dismiss the dialog/cancel the command.

---

## 2. Architecture Overview

### The Command Execution Pipeline

```
Claude Code (agent)
    │
    ▼
MCP Server (Python, server.py)
    │  preflight_rhino_command() — validates syntax, underscore prefix, known options
    │
    ▼
HTTP POST /command → RookNative (C++, CommandHandler.cpp)
    │
    ▼
MainThreadDispatcher.Dispatch(lambda)
    │  Posts WM_ROOK_DISPATCH to Rhino's main window
    │  Queues lambda for execution on Rhino's UI thread
    │
    ▼
RhinoApp().RunScript(docSn, command, echo)
    │
    ▼
Post-hoc interactive detection:
    RhinoApp().GetCommandPrompt(prompt)
    if prompt doesn't contain "Command" → cancel + return error
```

### Key Files

| Layer | File | Role |
|-------|------|------|
| MCP Server | `mcp_server/src/rook/server.py:11747` | Routes `rhino_command` → `call_rhino("/command", "POST", args)` |
| Preflight | `mcp_server/src/rook/preflight.py` | Pre-dispatch validation: underscore prefix, known options, missing params |
| C++ Handler | `src/RookNative/Handlers/CommandHandler.cpp:142-265` | `HandleCommand()` — runs script, checks prompt, cancels if interactive |
| C++ Interactive | `src/RookNative/Handlers/CommandInteractiveHandler.cpp` | Separate endpoints for step-by-step command interaction |
| Threading | `src/RookNative/Threading/MainThreadDispatcher.cpp` | Queues tasks for Rhino's UI thread via idle watcher + WndProc subclass |

---

## 3. The Incident: What Happened

### Timeline (reconstructed from session data)

The session log shows a pattern of many short-lived sessions throughout 2026-05-18 (20+ sessions in a single day), most with 0-3 commands. This is consistent with repeated connection loss / restart cycles caused by Rhino becoming unresponsive.

The agent issued a `rhino_command` call with a command string that was syntactically valid (passed preflight) but triggered an interactive prompt at runtime. The command hung, the agent received no response (or received a timeout), and — crucially — **did not know why**. Without understanding the cause, the agent continued issuing more tool calls, each of which queued behind the blocked main thread.

### The Cascade

1. **Agent sends command** via `rhino_command` — e.g., a command that unexpectedly requires object selection or point input
2. **`HandleCommand()` runs `RhinoApp().RunScript()`** — the command starts and enters an interactive prompt (GetPoint, GetObject, modal dialog)
3. **Post-hoc detection fires** (`GetCommandPrompt` check on line 207-221) — BUT:
   - This detection runs *immediately* after `RunScript` returns
   - `RunScript` is **fire-and-forget** for commands that enter modal loops — it returns *before* the modal prompt appears
   - The prompt check may read "Command:" (idle state) because the modal hasn't engaged yet
   - **Result: detection misses the interactive state**
4. **Command reports success** — `HandleCommand` returns `{"success": true}` to the MCP server
5. **Meanwhile, Rhino is now in a modal loop** — waiting for user input (point pick, object selection, dialog confirmation)
6. **Agent sends next command** — dispatched via `MainThreadDispatcher`
7. **WndProc subclass fires** (line 163 in MainThreadDispatcher.cpp) — because the modal loop pumps messages, `WM_ROOK_DISPATCH` is processed, and `DrainQueue()` runs...
8. **...which calls `RunScript` inside the modal loop** — this either:
   - Gets interpreted as input to the current modal command (wrong command gets wrong input)
   - Gets rejected/ignored, leaving the modal loop still active
   - Triggers a *nested* modal command inside the first one
9. **Each subsequent agent call compounds the problem** — the agent sees timeouts or garbled results, has no model of what went wrong, and keeps trying

---

## 4. Root Cause Analysis

### Root Cause 1: The `RunScript` Timing Gap (Critical)

**File:** `CommandHandler.cpp:200-221`

```cpp
// Line 200: RunScript fires the command
RhinoApp().RunScript(docRuntimeSn, wCommand, echo ? 1 : 0);

// Lines 207-221: Immediately check the prompt
ON_wString prompt;
RhinoApp().GetCommandPrompt(prompt);
std::string promptStr = WideToUtf8(prompt);

bool isInteractive = false;
if (!promptStr.empty() && promptStr.find("Command") == std::string::npos)
{
    RhinoApp().RunScript(docRuntimeSn, L"_Cancel", 0);
    isInteractive = true;
}
```

**The problem:** `RunScript` is asynchronous for commands that enter modal loops. The command is *queued* into Rhino's command pipeline but the modal prompt (GetPoint, GetObject) only activates when control returns to Rhino's message loop. The `GetCommandPrompt` call on line 208 reads the prompt *before* the modal has started, sees "Command:" (idle), and concludes everything is fine.

**The fix comment in CommandInteractiveHandler.cpp acknowledges this explicitly:**
> "C24 fix: RunScript is asynchronous — reading the prompt immediately after _Cancel returns the OLD prompt because the cancel hasn't processed yet."

The same timing issue applies to the *start* of a command, not just to cancel.

### Root Cause 2: No Command Classification (Design Gap)

**Files:** `preflight.py`, `CommandHandler.cpp`

The preflight system validates syntax (underscore prefix, known options, parameter count) but has **no classification of whether a command will go interactive**. The knowledge store (`rhino_command_knowledge`) has 196 learned commands with mode/option data, but this information is not used to predict or prevent interactive behavior.

Commands like `-Orient`, `-CageEdit`, `-Trim`, `-CurveBoolean` (without `_AllRegions`), and many others require interactive input by design. The system has no allowlist/blocklist of which commands are safe for fire-and-forget execution.

### Root Cause 3: No Timeout on `future.get()` (Missing Safety Net)

**File:** `CommandHandler.cpp:255`

```cpp
auto result = future.get();  // Blocks indefinitely
```

If `RunScript` enters a modal loop and doesn't return, the `future.get()` call on the httplib worker thread blocks forever. There is no timeout. The HTTP connection eventually times out on the client side, but:
- The main thread remains blocked in the modal loop
- The C++ handler thread remains blocked on `future.get()`
- No error is returned to the MCP server

### Root Cause 4: Modal Loop + WndProc Dispatch Interaction (Dangerous)

**File:** `MainThreadDispatcher.cpp:159-169`

The `WndProc` subclass is explicitly designed to drain the queue during modal loops:

```cpp
if (uMsg == WM_ROOK_DISPATCH)
{
    auto* self = reinterpret_cast<CMainThreadDispatcher*>(dwRefData);
    self->DrainQueue();  // Executes queued tasks during modal loop!
    return 0;
}
```

This is intentional — it allows the interactive command workflow (`/command/start`, `/command/send`) to work during GetPoint/GetObject. But it also means that **any** dispatched task (including another `rhino_command` call) will execute *inside* the modal loop. This can cause:
- Stacked modal loops
- Input being consumed by the wrong command
- Rhino internal state corruption

### Root Cause 5: Agent Has No Model of Rhino's State (Observability Gap)

The agent (Claude) operates in a request-response loop. It sends a tool call, gets a result, and plans the next action. There is no mechanism for:
- The MCP server to proactively notify the agent that Rhino is in a modal state
- The agent to query Rhino's current state before sending a command
- The agent to detect that a previous command silently went interactive

The `rhino_command_interactive_prompt` tool exists but the agent doesn't know to use it unprompted, and there's no hook that triggers it automatically.

---

## 5. Why the Existing Safeguards Failed

| Safeguard | Why It Failed |
|-----------|---------------|
| **Preflight validation** (`preflight.py`) | Only checks syntax. No classification of interactive vs non-interactive commands. |
| **Post-hoc prompt check** (`CommandHandler.cpp:207-221`) | Timing gap: `GetCommandPrompt` reads before the modal prompt activates. |
| **`_Cancel` fallback** (`CommandHandler.cpp:219`) | Only fires if the prompt check detects interactive mode — which it doesn't due to the timing gap. |
| **Knowledge store** (`rhino_command_knowledge`) | Has 196 commands with observations but this data isn't used for interactive classification. |
| **Interactive tool descriptions** (MCP tool descriptions) | The `rhino_command` description says nothing about the interactive risk. The agent doesn't know to prefer dedicated tools. |

---

## 6. Proposed Fixes

### Fix 1: Command Classification in Preflight (High Priority)

**Where:** `preflight.py` + knowledge store

Add a `requires_interaction` field to the command knowledge store. During preflight, if a command is classified as interactive and the caller is using the fire-and-forget `/command` endpoint, **reject it with a clear error** pointing to the interactive workflow.

```python
# In preflight_rhino_command():
if cmd_knowledge.requires_interaction:
    return {
        "success": False,
        "data": (
            f"Command {cmd_name} requires interactive input. "
            "Use rhino_command_interactive_start/send instead of rhino_command."
        ),
    }
```

The `preconditions` field already exists in the knowledge store (e.g., `requires_selection`, `clear_pending`). Extend it with `is_interactive: bool`.

### Fix 2: Delayed Prompt Check with Retry (High Priority)

**Where:** `CommandHandler.cpp`, `HandleCommand()`

After `RunScript`, wait briefly (e.g., 100ms) and re-read the prompt, similar to how `HandleCommandCancel` already does:

```cpp
// After RunScript:
RhinoApp().RunScript(docRuntimeSn, wCommand, echo ? 1 : 0);

// Allow Rhino's message loop to process the command
::Sleep(100);

// Re-read prompt
ON_wString prompt;
RhinoApp().GetCommandPrompt(prompt);
std::string promptStr = WideToUtf8(prompt);
```

This doesn't guarantee detection (some modals take longer), but it catches the majority of cases. Consider a retry loop with increasing delays (100ms, 200ms) up to a cap.

### Fix 3: Timeout on `future.get()` (Medium Priority)

**Where:** `CommandHandler.cpp:255`

Replace the indefinite block with a timeout:

```cpp
auto status = future.wait_for(std::chrono::seconds(30));
if (status == std::future_status::timeout) {
    // Command is hanging — likely in a modal loop
    // Post _Cancel via a separate dispatch and return error
    CRookServer::SendErrorData(res, {
        {"command", command},
        {"error", "Command timed out — likely waiting for interactive input. "
                  "Use rhino_command_interactive_start for multi-step commands."},
        {"timeout_seconds", 30}
    });
    return;
}
auto result = future.get();
```

### Fix 4: Block WndProc Dispatch During Fire-and-Forget Commands (Medium Priority)

**Where:** `MainThreadDispatcher`, `CommandHandler.cpp`

When `HandleCommand` dispatches a fire-and-forget command, set a flag that prevents `DrainQueue()` from executing other tasks until the command completes. This prevents subsequent MCP calls from executing inside an accidental modal loop.

```cpp
// In HandleCommand's lambda:
auto guard = dispatcher.ScopedExclusiveLock();
RhinoApp().RunScript(...);
// guard destructor re-enables normal dispatch
```

### Fix 5: State-Aware Tool Description (Low Priority but Important)

**Where:** `server.py`, `rhino_command` tool description

Update the tool description to warn the agent:

```python
description=(
    "Run a Rhino command string. Use underscore prefix for language-independent "
    "commands (e.g., '_Line'). WARNING: This tool is for non-interactive commands "
    "only. Commands that require point picking, object selection, or option dialogs "
    "will fail silently. Use rhino_command_interactive_start for multi-step commands. "
    "When in doubt, query rhino_command_knowledge first."
)
```

### Fix 6: Automatic `is_interactive` Inference from Knowledge Store (Medium Priority)

**Where:** Knowledge store / consolidation pipeline

The knowledge store already has `observations_count` and `preconditions` per command. During consolidation (`/consolidate`), automatically infer `is_interactive` from:
- `preconditions.requires_selection: true` → interactive unless selection is pre-provided
- Command has multiple modes with multi-step syntax → likely interactive
- Command has been observed going interactive in learning sessions → mark it

### Fix 7: Post-Command State Check Endpoint (Low Priority)

**Where:** New MCP tool or enhancement to `rhino_command`

Add a `rhino_state` tool (or include state in every `rhino_command` response) that returns:
```json
{
    "idle": true,
    "active_command": null,
    "prompt": "Command:",
    "modal_dialog_open": false
}
```

This gives the agent a way to detect and recover from interactive states.

---

## 7. The Specific `RunScript` Timing Problem — Deep Dive

The core issue is a **race condition** between `RunScript` and `GetCommandPrompt`:

```
Timeline (working correctly — non-interactive command):

    RunScript("_-Box 0,0,0 10,10,10 5")
    ├── Command parses all args inline
    ├── Creates geometry
    └── Returns to idle state
    GetCommandPrompt() → "Command:"  ← correct, command finished
    Result: success=true ✓

Timeline (failing — interactive command):

    RunScript("_-Box")  ← no parameters, needs point input
    ├── Queues the command
    └── Returns immediately (async for modal commands)
    GetCommandPrompt() → "Command:"  ← WRONG — modal hasn't started yet
    Result: success=true ✗ (false positive)

    ... 50-200ms later ...

    Rhino message loop processes the queued command
    ├── GetPoint() modal loop starts
    └── Prompt changes to "First corner of base (Diagonal 3Point...)"

    ← Nobody is listening anymore
    ← Rhino is now stuck waiting for a point pick
```

The `CommandInteractiveHandler.cpp` file documents this exact problem at line 248:
> "C24 fix: RunScript is asynchronous — reading the prompt immediately after _Cancel returns the OLD prompt because the cancel hasn't processed yet."

The cancel endpoint solved this with `Sleep(100)` — the same fix needs to be applied to `HandleCommand`.

---

## 8. Commands Known to Be Interactive

From the knowledge store's `preconditions` and observation data, these command categories are known or likely to require interactive input:

| Risk Level | Commands | Why |
|------------|----------|-----|
| **Always interactive** | `-Orient`, `-CageEdit`, `-Trim`, `-Flow`, `-Bend`, `-Taper`, `-Twist`, `-Shear`, `-Stretch`, `-Maelstrom`, `-SetPt`, `-Project`, `-Pull` | Require point selection or object picking that can't be fully scripted |
| **Interactive without full params** | `-Box`, `-Sphere`, `-Cylinder`, `-Line`, `-Circle`, `-Rectangle`, `-Polyline`, `-Arc`, etc. | Safe when all coordinates are inline; interactive when any are missing |
| **Interactive depending on mode** | `-CurveBoolean` (without `_AllRegions`), `-Loft` (dialog mode), `-Sweep1`/`-Sweep2` | Some modes require clicks, others don't |
| **Always safe** | `-SelAll`, `-SelNone`, `-SelCrv`, `-Join`, `-Explode`, `-Layer _New`, `-Zoom _Extents`, `-BooleanUnion` (pre-selected) | Selection commands, layer ops, zoom commands with full params |

---

## 9. Immediate Mitigations (Before Code Fixes)

1. **Agent-side guidance** (already saved to memory): Prefer dedicated MCP tools (`rhino_create`, `rhino_boolean`, `rhino_transform`) over `rhino_command`. These tools handle parameters programmatically.

2. **Query knowledge before command**: Use `rhino_command_knowledge` to check if a command requires selection or has interactive modes.

3. **Use interactive workflow when uncertain**: `rhino_command_interactive_start` → `_send` → `_cancel` gives the agent visibility into prompts.

4. **Watch for silence**: If a `rhino_command` call takes unusually long, assume a modal dialog and alert the user.

---

## 10. Files to Modify (Fix Implementation Guide)

| Priority | File | Change |
|----------|------|--------|
| P0 | `src/RookNative/Handlers/CommandHandler.cpp:200-221` | Add `Sleep(100)` + re-read prompt after `RunScript`; add `future.wait_for` timeout |
| P0 | `mcp_server/src/rook/preflight.py` | Add `requires_interaction` check using knowledge store |
| P1 | Knowledge store (consolidation pipeline) | Infer and persist `is_interactive` flag per command |
| P1 | `src/RookNative/Threading/MainThreadDispatcher.h` | Add scoped exclusive lock to prevent dispatch during command execution |
| P2 | `mcp_server/src/rook/server.py:2189-2202` | Update `rhino_command` tool description with interactive warning |
| P2 | New endpoint or enhancement | Add `rhino_state` / idle check tool |

---

## 11. Lessons Learned

1. **Fire-and-forget + post-hoc detection is fragile.** Asynchronous command execution means the detection window is a race condition. Pre-dispatch classification is more reliable than post-dispatch prompt checking.

2. **Silent failures are worse than loud failures.** The system returns `success: true` for commands that didn't actually complete. A timeout with a clear error message is far better than a false positive.

3. **The agent's blindness is the multiplier.** The root bug (one command going interactive) would be minor if the agent could detect and recover. The cascade happens because the agent has no model of Rhino's state and no signal that something went wrong.

4. **Existing safeguards were close but not connected.** The knowledge store has command metadata. The interactive handler has prompt parsing. The preflight has rejection logic. But these pieces aren't wired together — the knowledge store doesn't inform the preflight about interactivity, and the preflight doesn't use the interactive handler's detection logic.

---

*This post-mortem is intended as a starting point for Codex to implement the fixes. The source code locations, line numbers, and architectural context are current as of 2026-05-18.*
