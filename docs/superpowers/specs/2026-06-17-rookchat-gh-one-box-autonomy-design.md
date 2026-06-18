# RookChat GH One-Box Autonomy Design

Date: 2026-06-17
Branch: `codex/rookchat-gh-one-box-autonomy`

## Context

Recent live testing moved RookChat forward but exposed a new layer of issues. The `gh_canvas` group can now be requested, and `gh_create_csharp_script` is executable from the chat panel. A heavily guided one-box C# script prompt succeeded and `gh_errors` reported no canvas errors.

That success is not yet a usable product behavior. The model needed explicit instruction to use body-only RhinoCode C# Script code, avoid `GH_Component`, create a `B:Brep` output, and verify with `gh_errors`. The panel also rendered confusing tool cards: repeated `request_tools` calls, concatenated-looking tool names, `pins_out: [object Object]`, and neutral/green completion for cases where the tool transport completed but the application payload reported failure.

This slice makes the small one-box script task work naturally enough to be a reliable local-model smoke test. The original 10x10 box-grid task remains a manual stretch regression, not the merge gate.

## Goal

A local RookChat model should handle a natural prompt like:

> Create a Grasshopper C# script component that outputs one box. Check the canvas for errors.

without hand-holding. It should load the necessary Grasshopper tools once, create a RhinoCode C# Script component with valid body code, and show truthful tool feedback in the panel.

## Non-Goals

- No attempt to make the full 10x10 grid-with-sliders prompt a merge gate.
- No broad model prompt tuning unrelated to Grasshopper script creation.
- No Workbench, session topology, launcher, or Rhino process lifecycle changes.
- No new external dependencies.
- No live Rhino requirement for ordinary automated tests.
- No staging or reverting `knowledge/*` runtime artifacts.

## Design

### 1. Stronger Local Script-Creation Schemas

The MCP server schema for `gh_create_csharp_script` already explains the RhinoCode contract: body code is preferred, full source must be `Script_Instance : GH_ScriptInstance`, input values arrive as `object`, outputs are assigned directly, and `GH_Component` subclass code is not appropriate.

The local ChatRunner fallback schemas should carry the same essential guidance. This keeps RookChat truthful when it builds schemas from local dispatch instead of the cached MCP catalog.

Required local schema behavior:

- Both C# creation paths, `gh_create_csharp_script` and `gh_create_script` when `language="csharp"`, expose the same essential C# contract guidance. The unified tool may describe both languages, but its C# section must still be explicit.
- C# guidance explicitly says:
  - create a RhinoCode C# Script component, not a Grasshopper plugin component
  - pass body-only `RunScript` code by default
  - do not provide a `GH_Component` subclass
  - use `Script_Instance : GH_ScriptInstance` only when sending full-source mode
  - assign outputs directly by output pin name
- `code` property descriptions for both the alias and unified tool repeat the body-code default and `GH_Component` prohibition for C# use.
- `pins_out` examples show at least `["B:Brep"]`.
- Required fields remain parity-compatible with server schemas:
  - `gh_create_script`: `language`, `code`
  - aliases: `code`, `pins_in`, `pins_out`

### 2. Tool-Discovery De-Dupe

Repeated `request_tools("gh_canvas")` calls should not create confusing loops. If a requested group is already active, the result should make that explicit and should not imply new work occurred.

Required behavior:

- The registry/meta-tool path reports `already_loaded` or equivalent structured status when all requested tools are already active.
- The result gives the model a clear next action, for example: "gh_canvas is already loaded; call the needed Grasshopper tool directly."
- The tool call still succeeds from a transport perspective, but the payload should let both the model and UI distinguish first-load from no-op load.

### 3. Tool Card Truthfulness

The panel must distinguish "the tool call transport completed" from "the tool operation succeeded." A tool result with `success: false`, `ok: false`, or a structured error payload must render as failed or warning, not as neutral green "Done."

Required behavior:

- Parse JSON result strings when possible in `BuildToolSummary` and/or `chat.html`.
- Treat application-level failure as a failed card/result state, even when the server streamed a normal `tool_result` event.
- Do not overload `verified=false` to mean application failure. Verification remains about post-dispatch evidence: "ran but unverified" is different from "tool operation failed."
- Add or derive a separate result status such as `tool_success`, `tool_status`, or equivalent rendering input so the UI can display failed/warning/success separately from verification.
- Preserve verification states when present, but do not default unknown results to verified success.
- Show a concise error or failure message from `error`, `message`, `data`, or `verification_note` fields.

### 4. Structured Parameter Rendering

Tool cards should render nested arguments as readable compact JSON rather than JavaScript object stringification.

Required behavior:

- Nested arrays/objects render as compact JSON snippets, not `[object Object]`.
- Long strings remain truncated.
- Large arrays/objects are clipped predictably so the panel stays compact.
- The one-box prompt should display `pins_out` in a readable form such as `["B:Brep"]` or `[{"name":"B","type":"Brep"}]`.

### 5. Tool Event Boundary Guard

The live transcript showed tool names that appeared visually concatenated, such as `request_toolsgh_errors`. The implementation should identify whether this is actual event data, missing spacing in the rendered transcript, or fallback-card targeting.

Required behavior:

- Add a Python-side `ChatRunner` test proving multiple streamed tool calls emit distinct, exact `tool_start` names before C# rendering sees them.
- Add tests around tool-card rendering and `AgentChatTab` script calls so each `tool_start` creates one card with one tool name.
- `tool_result` updates should target by `tool_call_id` when available.
- If `tool_call_id` is missing, fallback behavior should be conservative and should not visually merge names.

### 6. Repair Guidance

When the model calls `gh_errors` after creating/updating a script and sees script errors, the desired next action is to call `gh_update_script` or `gh_set_script_pins` as appropriate, not paste code into chat.

This slice should add narrow guidance in the Grasshopper/script-specific prompt or schema descriptions. It should not attempt a broad behavior training pass across all tools.

## Acceptance Criteria

Automated:

- Local schema tests prove `gh_create_csharp_script` carries RhinoCode C# Script guidance, including "body code" and "do not use `GH_Component`."
- Local schema tests prove unified `gh_create_script` also carries the C# body-code / no-`GH_Component` guidance for `language="csharp"` use.
- Schema parity tests still prove required fields match the MCP server contract.
- Meta-tool tests prove repeated `request_tools("gh_canvas")` reports an already-loaded/no-op status.
- ChatRunner tests prove multiple streamed tool calls preserve exact distinct tool names in emitted `tool_start` events.
- Tool-card tests prove nested params render without `[object Object]`.
- Tool-card tests prove application-level `success: false` renders as failed/warning through a result-status path distinct from verification.
- Existing chat runner and chat panel focused tests pass.

Manual Rhino smoke:

1. Start Rhino, open Grasshopper, open a new RookChat conversation with a local model.
2. Prompt: "Create a Grasshopper C# script component that outputs one box. Check the canvas for errors."
3. Expected:
   - `gh_canvas` is requested at most once.
   - The model uses `gh_create_csharp_script` or `gh_create_script(language="csharp")`.
   - The created component uses valid RhinoCode C# Script body/source, not `GH_Component`.
   - The component has one Brep output and no compile errors.
   - `gh_errors` is called or an equivalent canvas verification is reported.
   - Tool cards render readable params/results and no misleading success state.

Manual stretch:

- Re-run the original "10x10 grid of boxes with gradient heights controlled by sliders" prompt and record outcome. Failures here should inform later planning, but should not block this slice.

## Open Implementation Choices

- Whether tool-card result-state parsing lives mainly in C# `BuildToolSummary`, in `chat.html`, or split between the two.
- Whether local script schema text should be copied from server descriptions verbatim, shortened into shared constants, or generated from a small helper to reduce drift.
- Whether repeated `request_tools` de-dupe belongs in `ToolRegistry`, `ChatRunner._handle_meta_tool`, or both.

Recommended choices for planning:

- Put result-state classification in C# so streamed events carry an explicit result-status signal to the UI without reusing verification semantics.
- Use short shared local schema constants in `chat_runner.py`; do not build a broad schema-sharing abstraction in this slice.
- Implement already-loaded status in the meta-tool handler, using registry state as the source of truth.

## Spec Self-Review

- Placeholders: none.
- Consistency: required fields remain aligned with the existing server contract.
- Scope: focused on one-box C# script autonomy, tool feedback, and de-duped tool discovery.
- Ambiguity: original grid prompt is explicitly manual/stretch only, not a merge gate.
