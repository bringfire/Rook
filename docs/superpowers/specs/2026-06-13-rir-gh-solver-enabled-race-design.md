# RIR Grasshopper Solver Enabled Race Design

Date: 2026-06-13

## Purpose

Fix issue #247: Grasshopper definitions driven by Rook inside
Rhino.Inside.Revit can stop auto-solving because the active `GH_Document`
settles, or later re-settles, with `document.Enabled == false`. Rook then
reports `solverEnabled=false`, and post-mutation solves either defer or schedule
into a disabled document. Edits commit, but downstream volatile data does not
update.

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

A follow-up focus probe showed that the activation gate is not limited to the
document-replacement window. After a one-shot post-create repair window expired,
focusing Revit left the active document with `solverEnabled=false`; the passive
event logger recorded repeated `ActivationGate_Enter`/`ActivationGate_Exit`
toggles. With Revit still foreground, a `gh_edit` changed a slider from 7 to 9
and returned success, but `gh_status` stayed `solverEnabled=false` and direct
inspection showed both slider and panel volatile data empty. Focusing
Grasshopper later could re-enable the document, but Rook cannot rely on that
because agents often drive edits while Revit remains foreground.

The load-bearing async assumption was then spiked directly. With Revit
foreground and `solverEnabled=false`, `gh_edit` changed the slider to 4 and
cleared both slider and panel volatile data. A script then set
`GH_Document.EnableSolutions=true`, set `document.Enabled=true`, expired the
objects with `ExpireSolution(false)`, and called `ScheduleSolution(1)`. No
`NewSolution` was used. `SolutionEnd` fired and the panel volatile data became
`["4"]`; later `ActivationGate_Exit` disabled the document again, but the async
solve had already completed. This proves schedule-time repair plus async
schedule can recompute while Revit remains foreground.

The solver-lock discriminator was also checked at the Grasshopper flag level:
setting `GH_Document.EnableSolutions=false` left `document.Enabled=true` but
made `solverEnabled=false`; resetting the static flag restored
`solverEnabled=true`. That supports using the static flag as the no-repair guard
for user solver lock, while still making UI-lock classification an upfront
implementation task.

## Safety Invariant

The PR #208 safe-solve invariant remains unchanged:

> No HTTP-driven Grasshopper mutation may force a synchronous recompute on a
> disabled or locked solver. Post-mutation recompute must use asynchronous
> `ScheduleSolution(delay >= 1)` only when the document is legitimately
> schedulable.

The #247 fix must not call `NewSolution`, must not call `ExpireSolution(true)`,
and must not treat every disabled document as schedulable. The fix is to make a
Rook-managed RIR document legitimately enabled at the point Rook is about to
schedule an async post-mutation solve, then let the existing async solve path
run.

## Host Safety

This design does override one RIR-controlled state transition, so the host
safety boundary must be explicit.

Rhino.Inside.Revit disables the Grasshopper document around its activation
gate so Grasshopper does not freely solve while Revit owns the execution
context. Rook's repair is safe only because it is narrow and because it does not
run a solution inside that gate. Rook's GH mutations are Rhino-side canvas,
geometry, and parameter edits. The repair restores `document.Enabled=true` for a
Rook-managed document immediately before a Rook-driven async solve schedule,
then uses Grasshopper's existing asynchronous schedule on the Rhino message
loop.

If a Grasshopper definition contains Revit-touching components, normal
Rhino.Inside.Revit and Revit transaction rules still govern those components.
The normalizer does not open Revit transactions, does not bypass component-level
guards, and does not force a synchronous solve while Revit API work is active.

## Design

### RIR solve-readiness coordinator

Add a small managed helper for Rook-owned GH solve readiness. The helper is
RIR-gated and should live near the existing GH bridge internals, not in native
code. It owns four responsibilities:

1. Detect RIR host context.
2. Mark the current Rook-created/opened/replaced active document as
   Rook-managed.
3. Optionally run a bounded transition-settle repair after document
   replacement.
4. Perform the load-bearing schedule-time repair immediately before Rook
   schedules a post-mutation solve.

The Rook-managed document mark is updated only after a Rook-initiated document
transition:

- `gh_document_new`;
- `gh_document_open`;
- any future Rook path that intentionally replaces the active canvas document.

The mark point should be the post-replacement active-document transition:
`DocumentChanged` landing on the new active document, on the UI thread. This
avoids marking the outgoing disabled document and makes the helper operate on
the same active document that later `gh_status` and `gh_edit` should inspect.

### Primary schedule-time repair

The primary hook is the post-mutation safe-solve path, including `gh_edit`.
When Rook is about to schedule an async solve for a committed mutation, the
helper inspects the current active document on the UI thread.

If all of the following are true, it performs one repair attempt for that
mutation:

- host is Rhino.Inside.Revit;
- the document is the current active canvas document;
- the document is Rook-managed, or the current mutation is a Rook-driven edit on
  the current active document;
- static `GH_Document.EnableSolutions` is true;
- instance `document.Enabled` is false;
- the caller requested a post-mutation solve.

When the condition matches, set `document.Enabled=true`, then re-read the
current active document before scheduling. This repair is inserted into the
existing post-mutation safe-solve path; it must not create a second independent
`ExpireSolution(false)` or `ScheduleSolution(...)` call. The single shared
scheduler remains responsible for dirtying the mutated objects once and calling
`ScheduleSolution(delay >= 1)` once. Do not call `NewSolution`.

If the re-read is still false, or if RIR disables the document again before the
schedule is accepted, do not loop. Return a deferred solve outcome and log that
the schedule-time repair did not hold.

The immediate UI-thread re-read is a guard against obvious failed assignment,
not proof that the repair held long enough for a solve. The meaningful live
verification is that the scheduled async solve reaches `SolutionEnd` and
volatile data updates before any later `ActivationGate_Exit` disables the
document again.

Stack attribution to `ActivationGate_Exit` is telemetry, not a hard precondition
for schedule-time repair. Runtime stack walking is brittle and should not be the
reason a needed RIR repair is skipped. The load-bearing discriminator is the
combination of RIR host, static solver enabled, current Rook-managed/Rook-driven
document, and a pending Rook post-mutation solve.

Ordinary Grasshopper solver locks remain preserved because the standard solver
lock flag is `GH_Document.EnableSolutions == false`. If Task 0 finds a
user-accessible path that deliberately sets only the instance
`document.Enabled=false` while the static flag remains true, that path must be
classified before any implementation proceeds and added to the no-repair
predicate.

### Bounded transition-settle repair

The post-document transition repair is still useful for the tight
`gh_document_new` -> immediate edit burst, but the focus probe proves it is not
sufficient as the primary architecture. Treat it as early normalization and
diagnostic surface.

The transition repair must not be a persistent watcher. It subscribes only to
the new active document during a bounded settle window after Rook replacement.

Concrete bound:

- maximum subscription window: 5 seconds after the Rook document transition;
- maximum repairs per armed document: 1;
- teardown: unsubscribe immediately after the first repair attempt, or when the
  5 second window expires, or when another canvas `DocumentChanged` replaces the
  tracked document.

The transition repair condition is intentionally narrow:

- host is Rhino.Inside.Revit;
- tracked document is still the current active canvas document;
- static `GH_Document.EnableSolutions` is true;
- instance `document.Enabled` changed to false.

`ActivationGate_Exit` stack attribution should be recorded when available, but
it must not be a hard precondition for this bounded repair. Within this narrow
Rook-initiated settle window, a user hand-lock is not the expected source of the
instance disable; the static solver flag remains the user-lock guard.

When the condition matches, set `document.Enabled=true`. If there is already
pending post-mutation work for that document, schedule through the same
schedule-time helper rather than duplicating scheduling logic. Outside the armed
settle window, never change `document.Enabled`.

All arm, repair, re-read, schedule, and teardown operations run on the UI thread.
Teardown must be idempotent because first repair, timeout expiry, and
`DocumentChanged` replacement can race.

### Did-not-stick outcome

Repairs are one-shot per context: once per document-transition window and once
per post-mutation solve attempt. If RIR disables the document again after a
repair, Rook accepts the disabled state for that context and logs it. It must
not loop, repeatedly fight the host, or keep an open subscription.

Telemetry should distinguish:

- repair attempted;
- repair held after a post-repair re-read;
- repair did not hold;
- no repair was attempted because static `GH_Document.EnableSolutions` was
  false;
- no repair was attempted because the helper was outside its settle window.

The held check should re-read the current active document after the repair on
the UI thread. For transition-settle repair, a practical implementation can
record an immediate re-read plus one delayed re-read within the same 5 second
settle budget. For schedule-time repair, the immediate re-read decides whether
Rook schedules the async solve or returns a deferred outcome.

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
produce a recompute. The #247 implementation must route post-mutation solve
scheduling through the RIR-aware safe-scheduling surface. In that surface,
schedule-time repair happens before the policy decides the solve is deferred.

This is still a solve-scheduling fix, not a mutation-readiness fix. A disabled
solver should not make `ready_for_edit=false`; edits can still commit while the
solver is locked or deferred.

## Standalone Behavior

Standalone Rhino already works and must be a no-op path for this normalizer.

When `rhinoInside=false`, the helper must not subscribe, repair, or emit
normalization actions, including at schedule time. Standalone
`gh_document_new` and `gh_edit` should keep their existing behavior: active
document enabled, async solve scheduled, panel volatile data populated.

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
`solver_state_known`, `rir_repair_attempted`, and `rir_repair_held`. It should
not hard-code a blocking "wait until solved" contract. That leaves room for
#246 to decouple mutation acknowledgment from solve completion without undoing
the #247 work.

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
coupled to Rhino.Inside.Revit internals than a schedule-time repair that uses
Rook's existing async solve policy, so this design chooses the narrower
normalizer.

Using only a bounded post-document transition normalizer as the primary fix is
rejected. The 2026-06-13 focus probe showed RIR can disable the current document
after the transition window, when Revit becomes foreground. A later Rook
`gh_edit` can then commit successfully but leave volatile data empty unless the
solve-schedule path repairs the document before scheduling.

## Tests

Automated/unit tests:

- RIR-gated normalizer does not arm when `rhinoInside=false`.
- A Rook-initiated document transition marks the new active document as
  Rook-managed and arms a one-shot settle window.
- `EnabledChanged=false` during the settle window repairs once and unsubscribes.
- `EnabledChanged=false` outside the settle window is not repaired.
- `EnabledChanged=false` when static `GH_Document.EnableSolutions=false` is not
  repaired.
- A second false after the one-shot repair is logged as did-not-stick and is
  not repaired again.
- Schedule-time repair runs once for a RIR, Rook-driven post-mutation solve
  when static solver is true and instance document enabled is false.
- Schedule-time repair does not run for standalone Rhino.
- Schedule-time repair does not run when static `GH_Document.EnableSolutions`
  is false.
- The post-mutation safe-solve path has exactly one owner for dirtying and
  scheduling; schedule-time repair only prepares the document before that
  shared scheduler runs.
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
5. Confirm the panel has populated volatile data without any manual
   `NewSolution`.
6. Focus Revit so `gh_status.solverEnabled=false` on the active GH document.
7. While Revit remains foreground, run `gh_edit` to change the slider value.
8. Confirm schedule-time repair runs and the panel volatile data updates without
   manual `NewSolution`.
9. Confirm DocumentServer registration remains irrelevant and can still be 0.
10. Confirm telemetry records whether RIR normalization repaired and whether the
   repair held.
11. Confirm a `SolutionEnd` or equivalent solve-completion signal is observed
    before treating the async schedule as verified.

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

Task 0 gate: classify the user solver-lock path before code changes. Confirm
the actual Grasshopper user lock sets `GH_Document.EnableSolutions=false`, and
stop if a normal user action can set only `document.Enabled=false` while the
static flag remains true.

Implementation order after Task 0:

1. Add the RIR-gated normalizer and diagnostics behind tests.
2. Wire document ownership marking and bounded transition-settle repair into
   Rook document creation/open/replacement.
3. Audit and adjust `gh_status`/`GhSolverState` to read the current active
   document.
4. Route `gh_edit` post-mutation scheduling through the RIR-aware safe schedule
   surface, with schedule-time repair as the primary hook.
5. Run automated tests.
6. Rebuild and deploy the managed companion with Rhino and Revit closed.
7. Run the deliberate RIR replacement-window and Revit-foreground live
   verification.
8. Run standalone and user-lock regressions.

If the deliberate repeated-replacement sequence stops reproducing during
implementation, the PR must say so plainly and describe the change as defensive
hardening plus telemetry, not as a conclusively live-verified fix.
