# GH Edit Partial Failure Contract Design

Date: 2026-05-14

## Context

The RookChat box-array session exposed a failure cascade across agent reasoning,
Grasshopper health checks, and `gh_edit` result interpretation. The most damaging
contract bug was that `gh_edit` could partially apply a batch, report nested
`edit_summary.errors`, and still present a top-level success shape that agents
could continue building on.

For agent-facing contracts, `success` must eventually mean that the requested
operation fully applied and is safe to build on. Partial mutation is not full
success. It is also not the same as no mutation: recovery code needs retained
snapshot, count, temp-map, and instance-GUID data to inspect and remediate.

This design defines the final `gh_edit` contract, a compatibility landing phase,
a caller audit required before flipping `success`, and adjacent Grasshopper
health semantics to prevent phantom-canvas workflows.

## Decision

Adopt strict failure semantics for partial `gh_edit` batches, implemented in
phases.

The final contract is:

- Full batch applied: `success: true`, no `partial_success`, no promoted
  top-level `errors`.
- Partial mutation: `success: false`, `partial_success: true`,
  `verified: false`, top-level `errors`, and retained `data.edit_summary`,
  snapshot data, counts, temp maps, and instance GUIDs.
- Total failure before mutation: `success: false`, no `partial_success` unless
  mutation evidence exists.

Phase 1 preserves raw transport compatibility by allowing top-level
`success: true` for partial edits, but it must be behaviorally impossible to
confuse with a successful edit in the chat and agent paths.

Invariant:

```text
If data.edit_summary.errors is non-empty:
- Phase 1: success may remain true for compatibility, but partial_success=true,
  verified=false, and top-level errors are mandatory.
- Phase 3: success=false, partial_success=true, verified=false, and top-level
  errors remain mandatory.
```

`verified` is part of the agent-visible tool result contract, not chat
decoration. `partial_success: true` implies `verified: false`, and callers must
not override that back to true just because `success` is true.

Phase 1 partial result shape:

```json
{
  "success": true,
  "partial_success": true,
  "verified": false,
  "errors": ["connect T19.O0>T20.I2: param not found"],
  "verification_note": "gh_edit partially applied. Inspect edit_summary.errors and remediate before continuing.",
  "data": {
    "partial_success": true,
    "warnings": ["connect T19.O0>T20.I2: param not found"],
    "edit_summary": {
      "created": 19,
      "connected": 12,
      "errors": ["connect T19.O0>T20.I2: param not found"]
    }
  }
}
```

Phase 3 changes only the top-level success semantics for this shape:

```json
{
  "success": false,
  "partial_success": true,
  "verified": false,
  "errors": ["connect T19.O0>T20.I2: param not found"],
  "verification_note": "gh_edit partially applied. Inspect edit_summary.errors and remediate before continuing.",
  "data": {
    "partial_success": true,
    "edit_summary": {
      "created": 19,
      "connected": 12,
      "errors": ["connect T19.O0>T20.I2: param not found"]
    }
  }
}
```

## Phases

### Phase 1: Compatibility Patch

Promote nested `data.edit_summary.errors` to top-level `errors`, set
`partial_success: true`, set `verified: false`, and include a
`verification_note` that tells agents to inspect and remediate before
continuing.

Duplicate `partial_success` under `data` for payload locality. Preserve existing
snapshot data, edit summary counts, temp maps, and instance GUIDs. Existing
`data.warnings` may also include the promoted errors for legacy UI surfaces that
already render warning lists.

Tests must prove that partial `gh_edit` results are visible in:

- Chat/agent dispatcher results.
- Direct MCP tool responses where the response shape permits it.
- Session recording as a partial outcome.

Phase 1 is temporary compatibility scaffolding. New callers must not optimize
around `success: true` for partial edits.

### Phase 2: Caller Audit

Before flipping `success`, enumerate every caller that branches on `gh_edit`
success or records `gh_edit` outcomes. The audit deliverable is a table with
file/function reference, current behavior, partial-edit behavior, retry policy,
and test coverage.

Required audit table rows:

| Area | Partial Mutation Handling | Retry Policy |
| --- | --- | --- |
| Chat dispatcher/tool card | Render top-level `partial_success`, `verified: false`, `errors`, and `verification_note` as an unverified partial edit. | Do not retry automatically. Ask the agent to inspect snapshot/edit summary first. |
| Session history recording | Preserve top-level errors and record outcome as partial, not successful completion. | No retry. History is evidence for remediation. |
| Recipe replay / fallback sequential path | Branch on `partial_success` and inspect counts/temp maps before deciding fallback. | Partial mutation is not automatically retryable because retrying the same batch can duplicate created components. Remediate incrementally, undo, clean up, or retry deliberately with duplicate prevention. |
| GH session learning/history | Record the specific operation errors so learning does not treat the batch as a success pattern. | No retry. Store direct trace data for future correction. |
| Direct MCP tool response | Surface promoted partial fields where possible so external agents see the same failure semantics. | Caller must inspect partial metadata before issuing another edit. |
| Tests asserting `success` | Identify tests that encode compatibility behavior and migrate them to strict Phase 3 expectations. | Test updates must distinguish no-mutation failures from partial-mutation failures. |

The audit is part of the contract migration, not optional follow-up work.

### Phase 3: Strict Contract Flip

When `data.edit_summary.errors` is non-empty, set top-level `success: false`
while retaining `partial_success: true`, `verified: false`, top-level `errors`,
`verification_note`, and all partial mutation metadata.

Migration tests must prove audited callers still behave correctly:

- Chat/tool card surfaces partial failure prominently.
- Session history records partial outcomes.
- Recipe replay avoids duplicate-producing blind retries.
- Direct MCP calls expose strict failure with retained edit summary.
- Existing tests no longer rely on partial `gh_edit` as top-level success.

## Grasshopper Health Semantics

Grasshopper health is adjacent to the `gh_edit` contract work and should not
block Phase 1. It should be designed alongside the contract migration because it
closes the phantom-canvas path from the post-mortem.

`gh_status.success` means only that the status endpoint executed. It does not
mean Grasshopper is healthy or ready for editing.

Pinned `gh_status` data shape:

```text
gh_status:
- success: true if the status endpoint executed
- data.available: Grasshopper assembly/runtime is loaded
- data.has_active_canvas: active canvas exists
- data.canvas_visible: canvas/window visibility if detectable
- data.has_active_document: active document exists
- data.document_id/name/path: when available
- data.ready_for_edit: true only when canvas + document are present
```

`gh_status` must be read-only. It must not create a Grasshopper document or
otherwise move the runtime toward readiness by side effect.

Add or design `gh_ensure_open` as the imperative counterpart. It is the only
tool allowed to move from `ready_for_edit: false` to `true` by side effect. It
should explicitly report what it did, then verify postconditions with
`ready_for_edit` semantics.

`gh_snapshot` and `gh_edit` must require `ready_for_edit: true` semantics. If
Grasshopper is unavailable, headless, missing a real active canvas, or missing
an active document, query and mutation tools must fail closed:

```text
success: false
verified: false
error/errors: actionable reason
```

For `gh_snapshot`, inability to observe a real editable canvas/document is a
plain failure, not an unverified success. The obvious recovery path is:
`gh_status`, then `gh_ensure_open` only if Grasshopper is the right substrate.

## Agent Prompting

The chat prompt should treat spatial references like "here in chat", "in this
panel", or "UI elements here" as direct signals for `ui_block`, not Grasshopper
sliders. Grasshopper remains appropriate only when the user asks for a
Grasshopper definition, canvas, or GH-native parametric workflow.

Agents must also be told that any tool result with `partial_success: true` or
`verified: false` is not safe to build on. The next action is inspection and
remediation, not continued construction.

## Testing

Phase 1 tests:

- Unit test partial `gh_edit` result promotion from `data.edit_summary.errors`.
- Chat dispatcher test proving partial edits produce top-level `errors`,
  `partial_success: true`, `verified: false`, and `verification_note`.
- MCP response test proving direct callers can see partial failure details.
- Prompt-builder regression test for "here in chat" -> `ui_block` guidance.

Phase 2 tests:

- Audit-driven tests for each row in the caller table.
- Existing test inventory updated to identify compatibility assertions that
  must change in Phase 3.

Phase 3 tests:

- Strict `success: false` for non-empty `edit_summary.errors`.
- No-mutation failures remain distinguishable from partial-mutation failures.
- Recipe replay/fallback does not blindly retry a partially applied batch.
- Session learning/history records partial trace data.

GH health tests:

- `gh_status` is read-only and does not create a document.
- `gh_status.success` only indicates endpoint execution.
- `ready_for_edit` is false without both active canvas and active document.
- `gh_snapshot` and `gh_edit` fail closed when `ready_for_edit` is false.
- `gh_ensure_open` is the only readiness-changing tool.

## Non-Goals

- Do not move block-definition mutation routes across the native/managed
  boundary.
- Do not make Grasshopper the preferred substrate for chat-native UI requests.
- Do not hide partial mutation metadata when returning strict failure.
- Do not implement automatic retry for partial `gh_edit`; retry requires an
  explicit remediation choice.
