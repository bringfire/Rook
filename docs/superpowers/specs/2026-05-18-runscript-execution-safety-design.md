# RunScript Execution Safety Design

Date: 2026-05-18

## Summary

Rook's RunScript-backed execution paths must become fail-closed, observable, timeout-bounded, and state-aware. The immediate incident was triggered through `rhino_command`, but the unsafe shape is broader: any tool that can enqueue Rhino command execution, infer completion from a weak prompt signal, and allow later mutations while Rhino may be waiting in a modal command loop can cause the same cascade.

The staged direction is:

1. Contain `rhino_command` first.
2. Deprecate autonomous interactive command execution while retaining prompt/cancel recovery primitives.
3. Apply the same RunScript safety policy to all normal execution paths that depend on Rhino command execution.

The new architectural rule is: interactive Rhino command driving is not a safe autonomous execution substrate. If an operation cannot be expressed through typed APIs or a known-safe, fully scripted command string, Rook refuses with a useful error instead of trying to drive Rhino prompts.

## Existing Context

The copied post mortem is tracked in `docs/postmortems/POST_MORTEM_interactive_command_cascade.md`. It identifies a silent cascade where Claude Code uses `rhino_command`, Rhino enters an interactive prompt, the agent receives weak or stale success signals, and later tool calls execute or queue while Rhino is modal.

The live code confirms the relevant seams:

- `src/RookNative/Handlers/CommandHandler.cpp` implements `/command` and `/execute`. Both use `RhinoApp().RunScript`, immediately inspect `RhinoApp().GetCommandPrompt`, and wait on the dispatched future with `future.get()`.
- `src/RookNative/Threading/MainThreadDispatcher.cpp` drains `WM_ROOK_DISPATCH` during modal loops. This is useful for prompt/cancel recovery, but unsafe if arbitrary mutation work can run inside an accidental modal command state.
- `mcp_server/src/rook/preflight.py` rejects malformed `rhino_command` strings and incomplete known syntax, but does not yet require explicit safe command/mode classification.
- `mcp_server/src/rook/agent/chat/execution_policy.py` has a stronger prompt-verification layer for the chat-service dispatcher, but the embedded Claude Code panel uses the strict MCP config path into `server.py`, where `rhino_command` reaches `/command` after preflight without the same post-dispatch verification behavior.
- `mcp_server/src/rook/learning/smart_executor.py` still models `execution_route="interactive"` and auto-escalates from a stalled known command to `/command/start` and `/command/send`.
- `mcp_server/src/rook/server.py` and `mcp_server/src/rook/agent/tool_groups.py` still expose `rhino_command_interactive_start`, `rhino_command_interactive_send`, `rhino_command_interactive_prompt`, and `rhino_command_interactive_cancel` together as normal command tools.

## Goals

- Make `rhino_command` fail closed for unknown, ambiguous, or potentially interactive commands.
- Keep `rhino_command_prompt` and `rhino_command_interactive_cancel` as normal recovery and observability tools.
- Remove `/command/start` and `/command/send` from normal autonomous execution surfaces.
- Prevent arbitrary queued mutation work from executing during an active or suspected Rhino modal prompt.
- Treat command timeouts as an uncertain Rhino state that quarantines future mutation until recovery confirms idle.
- Preserve a path for development-only command-learning experiments only if it is explicitly gated and named as learning/diagnostic, not normal execution.
- Update agent-facing tool descriptions and recovery messages so they direct agents toward typed APIs, complete scripted command strings, prompt inspection, or cancel recovery.
- Cover `rhino_execute` with the same runtime state gates and post-checks, recognizing that static checks cannot catch every blocking script path.

## Non-Goals

- No attempt to make autonomous prompt driving reliable.
- No broad rewrite of Rhino command knowledge consolidation in the P0 slice.
- No `.vcxproj` or `.vcxproj.filters` changes unless a later implementation step proves they are required and receives explicit approval.
- No claim that static analysis can fully prove a Python script is non-blocking.
- No removal of native recovery endpoints that are needed to inspect or cancel a stuck Rhino command state.

## Safety Policy

### Normal Execution

Normal execution includes MCP tools visible to Claude Code, the panel-locked Claude Code tab, chat-service agent execution, and `rhino_execute_intent`.

Normal execution may use:

- Typed native or managed HTTP APIs.
- `rhino_command` only for explicitly known-safe command/mode forms with complete scripted parameters and satisfied preconditions.
- `rhino_execute` only for scripts that pass static safety checks and runtime state checks.
- `rhino_command_prompt` to inspect current Rhino prompt state.
- `rhino_command_interactive_cancel` to recover from an active prompt.

Normal execution may not use:

- `rhino_command_interactive_start`.
- `rhino_command_interactive_send`.
- SmartExecutor `execution_route="interactive"`.
- Automatic fallback from known command execution to interactive command driving.
- Any mutation route while Rhino is known or suspected to be in a modal prompt state, except the explicit recovery primitives.

### Known-Safe Command Rule

`rhino_command` safety is explicit, not inferred from missing danger metadata.

A command is allowed only when all of the following are true:

- The command exists in the command knowledge store.
- The selected mode is marked safe for non-interactive scripted execution.
- Required arguments are present and complete.
- Options used are known for the command/mode.
- Any selection or preselection assumptions are explicit and satisfied by the command string or current state policy.
- The command is not flagged as interactive, modal, UI-opening, or requiring prompt-driven input.

Unknown commands are rejected. Known commands without an explicit safe non-interactive mode are rejected. Ambiguous commands are rejected.

### RunScript Quarantine

Timeout is not recovery. If a RunScript-backed request times out at the HTTP worker or bridge layer, the Rhino UI thread may still be inside a command or dialog. Rook must enter a state such as `execution_blocked` or `rhino_state_uncertain`.

While quarantined:

- Mutating routes are rejected before dispatch.
- Prompt/state inspection is allowed.
- Cancel recovery is allowed.
- Quarantine clears only after the strongest available native state check says Rhino is safe for mutation. Prompt idle is necessary but not always sufficient; if native code can observe command activity, modal/dialog state, dispatcher drain state, or recent cancel completion, those signals must be included before clearing quarantine.
- A failed prompt/state check preserves quarantine.

This prevents a timeout from becoming a false "done" signal that lets the agent continue mutating the document.

### Modal Dispatch Allowlist

`WM_ROOK_DISPATCH` may still need to drain during modal loops so recovery can work. The unsafe part is draining arbitrary work.

When Rhino is known or suspected to be in an active prompt, the dispatcher should allow only:

- Prompt/state reads.
- Cancel/recovery commands.
- Minimal internal bookkeeping required to return a structured refusal.

Mutation routes, `RunScript` execution, document edits, selection changes, geometry creation, and other state-changing work must not execute inside that modal loop. They should remain queued only if the caller has a clear wait contract, or preferably be refused quickly with a structured "Rhino execution blocked" response.

## Staged Design

### P0: `rhino_command` Containment

P0 reduces the immediate blast radius without requiring a full command-knowledge redesign.

Required behavior:

- `preflight_rhino_command` rejects unknown commands.
- `preflight_rhino_command` rejects known commands unless their command/mode metadata explicitly allows non-interactive scripted execution.
- P0 ships with an empty production safe set unless explicit `safe_non_interactive` metadata is present. Tests may use fake stores with safe metadata to prove the allow path, but production must not infer safety from existing command knowledge that lacks the field. A curated seed allowlist can be added later as reviewed metadata, not as a hidden migration assumption.
- Rejection messages say to use typed tools or provide a complete known-safe command string. They do not recommend interactive start/send.
- Native `/command` performs delayed prompt verification after `RunScript` instead of relying only on an immediate prompt read.
- Native `/command` uses bounded waits from worker threads.
- If `/command` times out or cannot verify idle state, it sets the global RunScript quarantine.
- `rhino_command` tool description warns that it is fail-closed and only for known safe fully scripted command strings.
- The panel-locked MCP path and chat-service dispatcher receive consistent error shape and verification metadata.

The P0 goal is containment, not perfect classification. The correct failure mode is false-positive rejection with a useful error.

### P1: Interactive Execution Deprecation

P1 removes the architectural trap where agents can rebuild autonomous prompt driving through another surface.

Required behavior:

- MCP `rhino_command_interactive_start` and `rhino_command_interactive_send` are removed from normal tool listings.
- If still reachable by direct MCP name, `rhino_command_interactive_start` and `rhino_command_interactive_send` return a structured deprecation/refusal error unless explicit dev/learning mode is enabled.
- Native `/command/start` and `/command/send` return the same structured deprecation/refusal error outside explicit dev/learning mode.
- `rhino_command_interactive_prompt` remains exposed as a state query.
- `rhino_command_interactive_cancel` remains exposed as emergency recovery.
- `rhino_commands` tool group no longer contains start/send.
- `execution_policy.py` no longer suggests `rhino_command_interactive_send` as recovery.
- SmartExecutor no longer plans or executes `execution_route="interactive"` for normal execution.
- SmartExecutor no longer escalates from known-command stalls into interactive fallback.
- `IntentPlanner` stops adding `fallbacks=["interactive"]` for normal execution plans.
- Existing tests that assert interactive fallback success are rewritten to assert refusal, recovery guidance, or dev-gated behavior.

If command-learning experiments remain useful, they move behind an explicit dev/learning gate. That mode must be opt-in, clearly named, unavailable to the embedded panel by default, and excluded from normal autonomous execution groups.

### P2: Shared RunScript Safety Architecture

P2 applies the same safety model to every normal RunScript-backed substrate.

Required behavior:

- A shared state gate checks prompt/quarantine before mutating dispatch.
- A shared result annotation records whether the prompt was verified idle after execution.
- `rhino_execute` keeps static checks for obvious blocking APIs, but also receives runtime state gates and post-execution prompt verification.
- Static script checks expand beyond `rhinoscriptsyntax.Get*` to flag obvious `rs.Command`, `RhinoApp.RunScript`, RhinoCommon input APIs, modal dialogs, and direct UI prompts where practical.
- The bridge/MCP path and chat-service dispatcher converge on the same modal-risk verification semantics.
- Timeouts and prompt-poll failures are treated as unverified and quarantined for mutation.
- Route metadata exposes enough state for agents to understand "refused before Rhino", "executed and verified idle", "executed but unverified", and "Rhino quarantined".

## Components

### Command Safety Classifier

The classifier lives at the Python preflight layer first, backed by command knowledge metadata.

Responsibilities:

- Normalize command name and mode using existing knowledge-store parsing.
- Require known command/mode metadata.
- Require explicit `safe_non_interactive` or equivalent positive metadata.
- Reject unknown or ambiguous options.
- Reject incomplete required parameters.
- Reject commands with interactive/modal/UI flags.
- Return structured refusal data with command, mode, reason, and recommended safer substrate.

The knowledge store can evolve later, but the classifier must remain fail-closed when metadata is missing.

### Native RunScript Guard

The native guard surrounds `/command` first and later `/execute`.

Responsibilities:

- Check current prompt/quarantine before starting new RunScript-backed work.
- Run the script/command.
- Allow Rhino's message loop enough time to expose prompt state.
- Re-read prompt state using the same idle detection convention as `/command/prompt`.
- Use the strongest native state signals available before declaring Rhino safe for mutation; prompt idle alone should not clear quarantine when a modal dialog, blocked UI state, or uncertain dispatcher state is still detectable.
- Cancel if an active prompt is detected.
- Return structured `waitingFor`, `verified=false`, or quarantine metadata instead of success.
- Convert timeouts into global execution quarantine.

The guard must not pretend that timeout cancels UI-thread work. It only marks state uncertain and refuses future mutation until recovery proves idle.

### Dispatcher Modal Allowlist

The dispatcher gains a policy layer for modal or suspected-modal states.

Responsibilities:

- Distinguish recovery/observability dispatch from mutation dispatch.
- Allow prompt/cancel/state checks during modal loops.
- Refuse or defer mutation work during active or suspected modal states.
- Avoid executing arbitrary queued tasks inside Rhino's modal loop.

The design should preserve the ability to cancel a stuck command, because recovery must remain possible even when idle notifications stop.

### Tool Surface and Agent Guidance

The MCP and chat surfaces must make the safe path obvious.

Responsibilities:

- Remove or deprecate interactive start/send from normal tool groups and descriptions.
- Keep prompt/cancel descriptions focused on observability and recovery.
- Update `rhino_command` description to say unknown or ambiguous commands are rejected.
- Update recovery notes to say "cancel, inspect, retry through typed APIs or a complete known-safe command", not "send prompt input".
- Ensure panel-locked Claude Code receives the same safety messages as other MCP clients.

### Dev/Learning Gate

If retained, interactive command learning is a separate mode.

Responsibilities:

- Require explicit environment/config opt-in.
- Exclude from panel-locked Claude Code.
- Exclude from normal tool groups.
- Use names and descriptions that indicate diagnostic learning, not production execution.
- Never serve as SmartExecutor fallback.

## Data and Error Shape

Safety refusals should be structured enough for agents and tests:

```json
{
  "success": false,
  "data": {
    "error": "run_script_safety_refusal",
    "reason": "unknown_command",
    "command": "_-SomeCommand",
    "mode": "unknown",
    "verified": false,
    "recovery": "Use a typed Rook tool or a known-safe fully scripted command."
  }
}
```

Quarantine responses should be distinct:

```json
{
  "success": false,
  "data": {
    "error": "rhino_execution_blocked",
    "reason": "previous_runscript_timeout",
    "verified": false,
    "prompt": "Select objects",
    "recovery": "Call rhino_command_prompt to inspect state or rhino_command_interactive_cancel to cancel the active command."
  }
}
```

## Testing Strategy

P0 tests:

- Python unit tests for `preflight_rhino_command` rejecting unknown commands.
- Python unit tests for rejecting known commands without explicit safe metadata.
- Python unit tests for allowing known safe complete command/mode examples.
- MCP contract tests proving `rhino_command` refusals do not call `call_rhino`.
- Native-adjacent tests where feasible for idle-prompt parsing helper behavior.
- Manual/live Rhino validation for delayed prompt checks and timeout quarantine, because generic sandbox builds cannot prove Rhino/MFC behavior.

P1 tests:

- Tool listing tests prove normal `rhino_commands` no longer includes start/send.
- MCP call tests prove start/send return structured deprecation errors in normal mode if still registered.
- Native route tests or live validation prove `/command/start` and `/command/send` are disabled outside dev/learning mode.
- SmartExecutor tests prove known-command stalls fail with recovery guidance and do not call `/command/start` or `/command/send`.
- Planner tests prove normal plans do not include interactive fallback.
- Execution-policy tests prove recovery notes mention prompt/cancel, not send.

P2 tests:

- Dispatcher policy unit tests for modal allowlist classification if extracted into testable helpers.
- Bridge/MCP tests proving prompt-poll failure on modal-risk tools returns unverified/quarantine metadata.
- `rhino_execute` safety tests for obvious blocking script calls beyond `Get*`.
- Live tests for quarantine clearing only after prompt/cancel confirms idle.

## Rollout

P0 should land first and may reject some previously accepted scripted commands. That is acceptable. The release note should call this out as a safety hardening change.

P1 can land next once the tool surface and SmartExecutor tests are updated. If a dev/learning gate is retained, it should default off.

P2 can be split into smaller implementation PRs: native guard/quarantine, dispatcher allowlist, shared MCP/chat verification, and expanded script safety.

## Open Decisions

- The exact metadata name for safe command/mode classification. Candidate: `safe_non_interactive`.
- Whether `rhino_learn_interactive` is retained behind a dev gate or deprecated entirely.
- The exact native storage point for quarantine state. It likely belongs near the dispatcher or a small shared RunScript state component, not in individual handlers.

## Approval Boundary

Approved design direction:

- Broad RunScript safety redesign.
- Staged with P0 `rhino_command` containment first.
- Deprecate autonomous interactive execution.
- Keep prompt/cancel recovery.
- Quarantine native start/send outside dev/learning mode.
- Add dispatcher modal allowlist.
- Treat timeout as uncertain-state quarantine.
- Require explicit known-safe command classification.
- Treat `rhino_execute` as a runtime modal-risk path even with static checks.
