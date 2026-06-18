# GH Script Compile Status Truthfulness Design

## Problem

RookChat now exposes the correct Grasshopper script creation tools up front, but the live one-box smoke still exposed a status ambiguity.

`gh_create_csharp_script` and `gh_update_script` can return top-level `success: true` when the placement/write operation completed even though the script component still has component-specific compile errors. The compile errors are present in nested fields such as `data.compilation_errors` or `data.component_errors`, but weaker local models treat the green success signal as task completion and may falsely report that the component is fixed.

The intended distinction is:

- Placement/write milestone: the component was placed or source was written.
- Script operation success: the component compiled cleanly, or verification was explicitly deferred/unavailable.

The first is useful feedback, but it must not be confused with the second. "Success, the stove is on" does not mean "Success, the omelet is cooked."

## Goals

- Make top-level tool success mean the requested script operation reached its verified compile goal when verification is available.
- Preserve milestone details so the model and UI can still say what happened, for example "component was created but has compile errors."
- Preserve GUIDs and pin/error details on failures so the model can repair the existing component instead of creating duplicates.
- Keep unrelated canvas errors separate from target-component script errors.
- Keep schemas strict and do not add prompt-only workarounds.

## Non-Goals

- No broad prompt/model behavior guardrail PR.
- No schema loosening.
- No dispatcher rerouting.
- No C# chat panel visual redesign.
- No Workbench, launcher, or topology changes.
- No live Rhino requirement for automated tests.

## Target Behavior

### `gh_create_csharp_script`

When the component is created and pins/source are injected:

- If the created component has no component-specific compile errors, return top-level `success: true`.
- If the created component has component-specific compile errors, return top-level `success: false`.
- The failure payload must still include:
  - `component_guid`
  - `pins_in`
  - `pins_out`
  - `position`
  - `name`
  - `code_length`
  - `compilation_errors`
  - a concise `message` or `data.message` explaining that the component was created but did not compile.

This lets the model continue with `gh_update_script` against the same component.

The same behavior applies to the unified `gh_create_script(language="csharp")` path because it delegates to the same helper.

### `gh_update_script`

When source is written and `check_errors` is true:

- If the target component has no component-specific errors or warnings, keep top-level `success: true`.
- If the target component has component-specific errors, return top-level `success: false`.
- The failure payload must still include:
  - `guid`
  - `detected_runtime`
  - `detected_language`
  - `mode_used`
  - `wrapped`
  - `inputs_used`
  - `outputs_used`
  - `component_errors`
  - `component_warnings`
  - `canvas_error_count`
  - `canvas_warning_count`
  - `unrelated_error_count`
  - `unrelated_warning_count`
  - existing `recovery_hint` when applicable
  - a concise message explaining that the source was written but the component still has compile errors.

Unrelated canvas errors must not flip the update result to failed. They remain diagnostic fields.

If verification is deferred because the solver is locked or state is unknown, keep the current deferred semantics: source-write success can be reported, but the payload must continue to make verification deferral explicit.

If `check_errors` is false, do not infer compile success or failure from absent checks.

## Model-Visible Result Semantics

`ChatRunner._classify_tool_status()` should classify these compile-error payloads as `failed` because top-level `success` will be false. This should make the chat panel card red/failed and the next model turn receive an unambiguous failed tool result.

The nested payload should remain rich enough that the model can repair instead of restarting:

- "Component created but has compile errors" plus `component_guid`
- "Source written but component still has compile errors" plus `guid`

## Testing

Add failing tests first.

Server/helper tests:

- `gh_create_csharp_script` mocked flow returns `success: false` when `/gh/errors` reports errors for the created component, while preserving `component_guid`.
- `gh_create_script(language="csharp")` shares the same failure shape.
- `gh_update_script` mocked flow returns `success: false` when `/gh/errors` reports errors for the target component.
- `gh_update_script` remains `success: true` when only unrelated canvas errors are present.
- `gh_update_script` preserves existing deferred verification behavior when solver verification is deferred.

Chat runner transcript tests:

- A failed `gh_update_script` repair with component errors emits `tool_status="failed"`.
- A failed create-with-compile-errors result keeps the component GUID visible in the tool message.

UI tests, if needed:

- Existing failed tool-status rendering should be sufficient. Add a focused summary test only if the structured failure message is not surfaced clearly.

Verification:

- Focused Python tests for server contract and RookChat transcript behavior.
- Existing RookChat prompt/runner tests.
- `git diff --check`.
- Manual Rhino smoke after merge/deploy:
  - Prompt: "Create a Grasshopper C# script component that outputs one box. After creating it, check the canvas for errors and fix the existing component if needed. Report what you created and the exact error-check result."
  - Required: model does not report completion while the target component still has errors.

## Rollout

This should be a small follow-up PR after the Tier 0 affordance hotfix. It should not bundle prompt rewrites or additional model-specific tuning. If a model still writes bad C#, the tool result should make that failure explicit and keep the repair path anchored to the existing component.
