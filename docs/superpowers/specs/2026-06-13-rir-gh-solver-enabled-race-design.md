# RIR Grasshopper Solver Enabled Race Design

Date: 2026-06-13

## Purpose

Fix issue #247: Grasshopper definitions created or replaced by Rook inside
Rhino.Inside.Revit can stop auto-solving because the active `GH_Document`
settles with `document.Enabled == false`. Rook then reports
`solverEnabled=false`, and post-mutation solves either defer or schedule into a
disabled document. Edits commit, but downstream volatile data does not update.

This design is scoped to #247 only. It deliberately leaves the #246
`gh_edit`/Chirp callback timeout for a later PR, while keeping the solve
lifecycle shape compatible with that follow-up.

## Evidence

The corrected root cause is not DocumentServer registration. Standalone Rhino
and RIR can both have `DocumentServer.DocumentCount == 0` and an active canvas
document that is not registered in the server. The working differentiator is the
instance flag:

- standalone: `GH_Document.EnableSolutions == true` and
  `document.Enabled == true`;
- failing RIR sequence: `GH_Document.EnableSolutions == true` and
  `document.Enabled == false`.

The failure is sequence-dependent but reproducible. Repeated `gh_document_new`
over an existing RIR canvas, followed by tight `gh_status` and `gh_edit`
calls, can leave the new active document disabled. In that state, a
Number Slider -> Panel edit mutates the canvas, but the panel's volatile data
stays empty until a manual forced solve.

Live event probes identified the reset source. Replacing the canvas document
fires `EnabledChanged=false` on the outgoing document, then
`DocumentChanged` to a new document that initially reports `Enabled=true`.
Inside RIR, Rhino.Inside.Revit's activation gate can then fire
`EnabledChanged` on the new active document and leave it disabled. Stack traces
for those toggles showed:

- `RhinoInside.Revit.GH.Guest.ActivationGate_Enter` for the true side;
- `RhinoInside.Revit.GH.Guest.ActivationGate_Exit` for the false side.

This answers the previously open "what resets `document.Enabled`?" question:
the source is the RIR activation-gate exit path during or after document
replacement, not an unknown create-time state or DocumentServer behavior.

## Safety Invariant

The PR #208 safe-solve invariant remains unchanged:

> No HTTP-driven Grasshopper mutation may force a synchronous recompute on a
> disabled or locked solver. Post-mutation recompute must use asynchronous
> `ScheduleSolution(delay >= 1)` only when the document is legitimately
> schedulable.

The #247 fix must not call `NewSolution`, must not call `ExpireSolution(true)`,
and must not treat every disabled document as schedulable. The fix is to make a
Rook-created RIR document legitimately enabled after the RIR replacement window
settles, then let the existing async solve path run.

## Host Safety

This design does override one RIR-controlled state transition, so the host
safety boundary must be explicit.

Rhino.Inside.Revit disables the Grasshopper document around its activation
gate so Grasshopper does not freely solve while Revit owns the execution
context. Rook's repair is safe only because it is narrow and because it does not
run a solution inside that gate. Rook's GH mutations are Rhino-side canvas,
geometry, and parameter edits. The repair restores `document.Enabled=true` for a
Rook-managed document after the replacement/activation transition, then uses
Grasshopper's existing asynchronous schedule on the Rhino message loop.

If a Grasshopper definition contains Revit-touching components, normal
Rhino.Inside.Revit and Revit transaction rules still govern those components.
The normalizer does not open Revit transactions, does not bypass component-level
guards, and does not force a synchronous solve while Revit API work is active.

## Design

### RIR lifecycle normalizer

Add a small managed helper for Rook-owned GH document lifecycle normalization.
The helper is RIR-gated and should live near the existing GH bridge internals,
not in native code. It owns three responsibilities:

1. Detect RIR host context.
2. Track the current Rook-created/opened/replaced active document during a
   bounded settle window.
3. Repair one RIR activation-gate disable event, then tear itself down.

The helper arms only after a Rook-initiated document transition:

- `gh_document_new`;
- `gh_document_open`;
- any future Rook path that intentionally replaces the active canvas document.

The arm point should be the post-replacement active-document transition:
`DocumentChanged` landing on the new active document, on the UI thread. This
avoids repairing the outgoing disabled document and makes the helper operate on
the same active document that later `gh_status` and `gh_edit` should inspect.

### Bounded one-shot repair

The normalizer must not be a persistent watcher. It subscribes only to the new
active document during a bounded settle window after Rook replacement.

Concrete bound:

- maximum subscription window: 5 seconds after the Rook document transition;
- maximum repairs per armed document: 1;
- teardown: unsubscribe immediately after the first repair attempt, or when the
  5 second window expires, or when another canvas `DocumentChanged` replaces the
  tracked document.

The repair condition is intentionally narrow:

- host is Rhino.Inside.Revit;
- tracked document is still the current active canvas document;
- static `GH_Document.EnableSolutions` is true;
- instance `document.Enabled` changed to false;
- the disable source is the RIR activation-gate exit path, identified from the
  event context/stack or an equivalent RIR-specific signal.

When the condition matches, set `document.Enabled=true`. If there is pending
post-mutation work for that document, mark the document dirty as needed and
schedule through the existing async solve path with
`ScheduleSolution(delay >= 1)`. Do not call `NewSolution`.

Outside the armed settle window, never change `document.Enabled`. This is what
preserves a later user lock.

### Did-not-stick outcome

The repair is one-shot. If RIR disables the document again after the repair or
after the settle window closes, Rook accepts the disabled state and logs it. It
must not loop, repeatedly fight the host, or keep an open subscription.

Telemetry should distinguish:

- repair attempted;
- repair held after a post-repair re-read;
- repair did not hold;
- no repair was attempted because the disable was not recognized as the RIR
  activation-gate exit path;
- no repair was attempted because the helper was outside its settle window.

The held check should re-read the current active document after the repair on
the UI thread. A practical implementation can record an immediate re-read plus
one delayed re-read within the same 5 second settle budget. If the second read
is false, the solve remains deferred and the telemetry explains that the RIR
gate re-disabled the document after repair.

### Read-path audit

`GhSolverState.Inspect` and `gh_status` must read the current
`ActiveCanvas.Document` on the UI thread at inspection time. They must not use a
cached document reference captured before replacement. The status surface should
continue to compute:

```text
solverEnabled = GH_Document.EnableSolutions && activeDocument.Enabled
```

but it should also expose enough diagnostic detail to tell whether false came
from the global static flag or the instance document flag.

The implementation should add or preserve diagnostics for:

- active document id;
- `GH_Document.EnableSolutions`;
- active `document.Enabled`;
- `SolutionState`;
- RIR/standalone host context;
- latest RIR normalization action and whether the repair held.

These diagnostics can live in `gh_status`, structured logs, or both, but they
must be available during live RIR verification.

### Post-mutation solve path

The affected customer path is:

```text
gh_document_new -> gh_edit -> post-mutation solve
```

`gh_edit` currently commits the mutation and schedules a document solution. If
the active document has settled disabled under RIR, that schedule does not
produce a recompute. The #247 implementation should route post-mutation solve
scheduling through the same RIR-aware safe-scheduling surface, or otherwise
ensure that `gh_edit` consults the normalizer before deciding the solve is
deferred.

This is still a solve-scheduling fix, not a mutation-readiness fix. A disabled
solver should not make `ready_for_edit=false`; edits can still commit while the
solver is locked or deferred.

## Standalone Behavior

Standalone Rhino already works and must be a no-op path for this normalizer.

When `rhinoInside=false`, the helper must not subscribe, repair, or emit
normalization actions. Standalone `gh_document_new` and `gh_edit` should keep
their existing behavior: active document enabled, async solve scheduled, panel
volatile data populated.

Add an explicit regression test or live assertion that no RIR normalization is
armed under standalone Rhino.

## Solve Lifecycle And #246

#247 and #246 both touch the post-mutation solve/callback surface, but they fix
different failures:

- #247: whether a solve is legitimately schedulable after RIR document
  replacement;
- #246: whether `gh_edit` blocks the callback while a long solve, such as a
  Chirp/LLM cascade, is still running.

The #247 helper should therefore expose outcome metadata such as
`mutation_committed`, `solve_scheduled`, `solve_deferred`,
`solver_state_known`, and `rir_normalization_action`. It should not hard-code a
blocking "wait until solved" contract. That leaves room for #246 to decouple
mutation acknowledgment from solve completion without undoing the #247 work.

## Considered And Rejected

`DocumentServer.AddDocument` as the fix is rejected. The corrected A/B evidence
shows DocumentServer registration is not the differentiator.

Treating `document.Enabled=false` as schedulable is rejected. It weakens the
PR #208 invariant and cannot distinguish RIR host-default disabled state from a
real user lock.

Forcing `NewSolution` is rejected. It reintroduces the synchronous recompute
class that PR #208 intentionally removed.

Working directly inside the RIR activation gate was considered. That would mean
trying to drive Rook GH operations inside the correct RIR activation context
instead of repairing after the gate exits. It is more invasive and more tightly
coupled to Rhino.Inside.Revit internals than a bounded post-replacement repair,
so this design chooses the narrower normalizer.

## Tests

Automated/unit tests:

- RIR-gated normalizer does not arm when `rhinoInside=false`.
- A Rook-initiated document transition arms a one-shot settle window.
- `EnabledChanged=false` from the RIR activation-gate exit path repairs once
  and unsubscribes.
- `EnabledChanged=false` outside the settle window is not repaired.
- `EnabledChanged=false` from a non-RIR/user-lock source is not repaired.
- A second false after the one-shot repair is logged as did-not-stick and is
  not repaired again.
- `GhSolverState.Inspect` reads the current active document, not a cached
  outgoing document.
- Source/static guard continues to reject `NewSolution`,
  `ExpireSolution(true)`, and synchronous solve re-entry in HTTP mutation paths.

Live RIR verification:

1. Start Rhino.Inside.Revit with Grasshopper open.
2. Create an initial GH canvas document.
3. Repeatedly call `gh_document_new` over the existing document to exercise the
   replacement window.
4. Immediately call `gh_status` and `gh_edit` for a Number Slider -> Panel
   graph.
5. Confirm `gh_status.solverEnabled=true` after the bounded settle.
6. Confirm the panel has populated volatile data without any manual
   `NewSolution`.
7. Confirm DocumentServer registration remains irrelevant and can still be 0.
8. Confirm telemetry records whether RIR normalization repaired and whether the
   repair held.

Standalone regression:

1. Run the same `gh_document_new` and slider -> panel edit in standalone Rhino.
2. Confirm the panel solves.
3. Confirm no RIR normalization subscription or repair occurred.

User-lock regression:

1. Lock/disable the solver through the ordinary Grasshopper user path.
2. Run a Rook mutation.
3. Confirm Rook does not re-enable the solver.
4. Confirm the response/status reports a deferred solve rather than forcing a
   recompute.

## Rollout

This is the #247 PR and should use a `fix/` branch. It should land before any
#246 implementation.

Implementation order:

1. Add the RIR-gated normalizer and diagnostics behind tests.
2. Wire it into Rook document creation/open/replacement.
3. Audit and adjust `gh_status`/`GhSolverState` to read the current active
   document.
4. Route `gh_edit` post-mutation scheduling through the RIR-aware safe schedule
   surface.
5. Run automated tests.
6. Rebuild and deploy the managed companion with Rhino and Revit closed.
7. Run the deliberate RIR replacement-window live verification.
8. Run standalone and user-lock regressions.

If the deliberate repeated-replacement sequence stops reproducing during
implementation, the PR must say so plainly and describe the change as defensive
hardening plus telemetry, not as a conclusively live-verified fix.
