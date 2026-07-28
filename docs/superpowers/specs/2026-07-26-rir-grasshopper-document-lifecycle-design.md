# Rhino.Inside.Revit Grasshopper Document Lifecycle Design

**Date:** 2026-07-26

**Status:** Implemented and live accepted for PR #508

**Scope:** Grasshopper lifecycle, solver ownership, scheduling evidence, and the MCP scheduling consumer

## Purpose

Rook must have one authoritative path for creating or opening a top-level Grasshopper document and one host-aware path for requesting a post-mutation solution. The lifecycle and solver-policy cutovers are one deployable behavior change because registration and Rhino.Inside.Revit (RiR) solver ownership form one runtime invariant:

> Every Rook-created or Rook-opened top-level Grasshopper document is registered with `Grasshopper.Instances.DocumentServer` before Rook treats it as active, and Rook never writes the active document's `Enabled` property while running inside Revit.

This specification is Grasshopper-only. Revit and RiR are host fixtures for the live matrix. RookBIM document identity, diagnostics, routes, DTOs, and deployment decisions are outside this design and PR #508.

## Incident summary

Rook previously assigned constructed or loaded `GH_Document` objects directly to `GH_Canvas.Document`. An unknown document is not registered merely because the canvas promotes it. RiR attaches solution, transaction, and replay handlers through document-server registration, so an orphaned active document could emit solution events while producing no component data.

Rook also competed with RiR by writing `GH_Document.Enabled` and by restoring it after a five-second deferred handoff. Live source inspection and an A/B test established the corrected boundary:

- register the document through Grasshopper's document server;
- let RiR own document enablement inside Revit;
- restore standalone suspension before scheduling;
- invoke Grasshopper's positive-delay scheduler exactly once before returning;
- report invocation acceptance separately from eventual solve completion.

The original full standalone/RiR matrix and the split-branch MCP consumer smoke are recorded in [the acceptance report](../reports/2026-07-26-rir-grasshopper-document-lifecycle-acceptance.md).

## Normative invariants

1. Lifecycle mutation runs on the Rhino UI thread against one captured `ActiveCanvas`.
2. Server membership is compared by object reference. A filepath is lookup evidence, not ownership evidence.
3. `registered + active on the captured canvas` is the lifecycle commit point.
4. Rollback restores the prior canvas document before removing a newly registered candidate.
5. Rook never removes an existing duplicate-path document and never disposes a document that is registered or active on any known canvas.
6. After commit, readiness attachment, refresh, telemetry, object counting, and compatibility projection may warn but cannot turn the route into a false failure.
7. RiR performs no Rook-owned suspension and no Rook `Enabled` or global `EnableSolutions` write.
8. Post-mutation recompute uses only `ExpireSolution(false)` plus one `ScheduleSolution(delay >= 1)` invocation. There is no synchronous fallback, second scheduler, or five-second Rook handoff.
9. Schedule policy, invocation acceptance, and solve completion are separate states.
10. A thrown scheduling invocation is `unknown`, verification-deferred, and never retried.

## Transactional document lifecycle

### Shared lifecycle owner

`GhDocumentLifecycle` is the sole owner of new/open creation, document-server registration, canvas activation, reconciliation, rollback, and bounded lifecycle results. Context resolution is observational and cannot create a document.

The helper captures:

- the active canvas by reference;
- the prior canvas document;
- the pre-mutation server documents by reference and order;
- any document already registered for an open path;
- whether this invocation constructed or newly registered a candidate;
- the observed active and registered state after each mutation.

A process-wide UI-thread reentrancy guard rejects synchronous lifecycle reentry before mutation and is released in `finally`.

### New document

`/gh/document/new` preserves intentionally empty semantics and does not call the template-loading `AddNewDocument` API.

```text
capture canvas/server/previous document
→ construct exactly one empty GH_Document
→ verify captured ActiveCanvas unchanged
→ DocumentServer.AddDocument(candidate, out success)
→ verify captured ActiveCanvas unchanged
→ verify success and reference registration
→ capturedCanvas.Document = candidate
→ verify captured ActiveCanvas unchanged
→ verify registered + active by reference
→ commit
```

A conclusively unsuccessful, never-registered, inactive candidate may be disposed once. Unknown membership, a registration-call exception, or any positive registration evidence permanently makes cleanup ownership ambiguous; a later absent observation cannot erase that history. Ambiguous candidates are preserved and rollback is reported incomplete.

### Open document

`/gh/document/open` uses `DocumentServer.AddDocument(path, makeActive: true)` so Grasshopper owns duplicate-path behavior.

```text
validate file
→ capture canvas/server/previous/path registration
→ verify captured ActiveCanvas unchanged
→ AddDocument(path, true)
→ recapture canvas and server membership
→ reconcile returned, registered, and active references
→ verify one registered candidate is active on the captured canvas
→ commit
```

The path overload may return `null` after partially mutating the server. The helper therefore reconciles reference snapshots before deciding whether anything changed. A preexisting path document is never removed or disposed.

### Rollback and post-commit warnings

Before commit, rollback:

1. reinspects the captured and current canvases plus server membership;
2. restores the prior captured-canvas document and verifies that state;
3. removes a newly registered candidate only through `DocumentServer.RemoveDocument` and only after proving it inactive;
4. directly disposes only a candidate proven never registered and inactive;
5. reports the actual final state when restoration or cleanup is incomplete.

After commit, auxiliary failures return success with bounded warnings. They do not invite a retry while leaving the newly active document in place.

## Solver ownership and scheduling

### Host-aware policy

The pure policy receives solve intent, RiR/standalone host state, registration-known/registered evidence, global `GH_Document.EnableSolutions`, and instance `document.Enabled` independently.

Important classifications are:

| Condition | `schedule_classification` | Attempt |
|---|---|---|
| Solve not requested | `solve_not_requested` | no |
| RiR document unregistered | `rir_document_unregistered` | no |
| RiR registration unknown | `rir_registration_unknown` | no |
| Global solver unavailable | `global_solver_unavailable` | no |
| RiR registered, global true, instance false | `rir_mediated_schedule_requested` | yes |
| Known schedulable state | `async_schedule_requested` | yes |
| Safe but incomplete solver evidence | host-specific unknown classification | one asynchronous attempt |
| Standalone document disabled | `document_solver_disabled` | no |

`global_solver_unavailable` is neutral. Grasshopper can report global unavailability because it cannot currently solve, and RiR temporarily disables the underlying flag during registration. Rook does not call it a proven user lock.

### Standalone and RiR ownership

In standalone Rhino, mutation-time document suspension is restored on every exit path. Successful restoration is verified before scheduling. A failed restoration produces `not_attempted` with `standalone_solver_restore_failed`; it is visible and never retried.

In RiR, the suspension helper is a no-op. Rook does not write instance `Enabled` or global `EnableSolutions`. RiR's activation gate remains the solver-state owner.

### Exact scheduling order

For `/gh/edit` and equivalent post-mutation routes:

```text
perform mutation
→ ExpireSolution(false)
→ capture structural result/snapshot
→ restore standalone suspension
→ inspect post-restoration policy
→ invoke ScheduleSolution(delay >= 1) exactly once
→ project acceptance and build response
```

`ScheduleSolution` arms Grasshopper's asynchronous timer; it does not synchronously solve during the callback. Rook does not call `NewSolution`, use delay zero, retry, or schedule through `Task.Run`.

### Acceptance contract

| Invocation result | `schedule_acceptance` | `schedule_failure_code` | Meaning |
|---|---|---|---|
| Policy/precondition rejects | `not_attempted` | nullable bounded code | target not entered |
| Scheduling method absent | `unavailable` | `schedule_api_unavailable` | no invocation |
| Invocation returns | `accepted` | `null` | accepted; completion still unverified |
| Invocation begins and throws | `unknown` | `schedule_acceptance_unknown` | may have partially scheduled; no retry |

The compatibility field `solve_scheduled` is true only for `accepted`. A false value is not proof of no pending schedule when acceptance is `unknown`.

## Wire and MCP consumer contract

The exact public keys are snake_case:

- `schedule_classification`
- `schedule_acceptance`
- `schedule_failure_code`
- retained `solve_scheduled`
- `verification_deferred`

`verification_deferred` in the managed response means solve completion was not observed before callback return. It does not mean scheduling was rejected.

The `gh_update_script` Python consumer therefore treats `schedule_acceptance` as authoritative:

- `accepted`: wait briefly, call `/gh/errors`, and build a verified MCP script receipt;
- `unknown`, `unavailable`, or `not_attempted`: keep verification deferred, issue no retry, and return neutral inspection guidance;
- legacy payload with no acceptance field: retain the preexisting `verification_deferred` interpretation.

The existing settle is a 300 ms best-effort delay before `/gh/errors`. A very slow solution could still be observed too early. This repair does not introduce a solve-completion protocol; doing so requires a separate design. Conservative acceptance handling plus the live MCP smoke is the accepted boundary for PR #508.

## Cleanup and compatibility

The behavior change removes:

- both implicit document-creation branches;
- manual `GH_DocumentIO` route opening;
- `GhSolveReadinessCoordinator` and delayed repair ownership;
- the legacy `GhSolvePolicy` implementation;
- `RequestDeferredPostMutationSolve`;
- the five-second `Task.Run`/UI-redispatch scheduler;
- source tests that encode registration irrelevance or RiR repair writes.

The deprecated `rir_repair_*` response fields remain temporarily present and neutral. They do not drive behavior.

## Verification and rollback

Automated coverage includes lifecycle commit/rollback and ambiguous ownership, duplicate open behavior, reentrancy, post-commit warnings, every solver-policy and acceptance row, exact scheduling order, no RiR flag writes, wire casing, and Python accepted/deferred consumption.

Live acceptance requires standalone and RiR document new/open/duplicate/rollback behavior, real volatile output, temporary global unavailability, real RiR components, and one MCP `gh_update_script` smoke proving accepted scheduling proceeds to error verification.

Rollback is atomic across lifecycle registration and solver ownership. Mixing only one half restores an invalid runtime. RookBIM is not part of this rollback unit.

## Appendix A: Rook2 reimplementation index

### Changed production paths

- `src/Rook/InternalBridge/GhDocumentLifecycle.cs` — transactional create/open, ownership latches, reconciliation, and rollback.
- `src/Rook/InternalBridge/GrasshopperCore.cs` — observational context resolution; no implicit creation.
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` — route dispatch through the lifecycle owner.
- `src/Rook/Handlers/GrasshopperHandler.cs` — route cutover, lifecycle results, scheduling wire fields, and neutral compatibility fields.
- `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs` — one post-mutation scheduling integration path.
- `src/Rook/Handlers/GrasshopperHandler.Readiness.cs` — readiness evidence derived from acceptance without repair ownership.
- `src/Rook/Handlers/GhMutationSolveSuspension.cs` — standalone-only, one-shot suspension and verified restoration.
- `src/Rook/Handlers/GhPostMutationSchedulePolicy.cs` — closed host policy, acceptance, failure, warning, and wire vocabularies.
- `src/Rook/Handlers/GhScheduleInvoker.cs` — one positive-delay invocation with conservative unknown handling.
- `mcp_server/src/rook/server.py` — `gh_update_script` consumes authoritative schedule acceptance before MCP error verification.

### Deleted legacy paths and mechanisms

- `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs`
- `src/Rook/Handlers/GhSolvePolicy.cs`
- `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs` — deliberately deleted coverage for the retired coordinator and its Rook-owned RiR repair behavior.
- implicit creation in handler/core context resolution
- manual document opening through `GH_DocumentIO`
- delayed `RequestDeferredPostMutationSolve` and its five-second scheduler
- RiR-side Rook `Enabled` repair writes

### Public wire fields

| Field | Role |
|---|---|
| `schedule_classification` | host/policy decision |
| `schedule_acceptance` | authoritative invocation acceptance |
| `schedule_failure_code` | nullable bounded failure |
| `solve_scheduled` | compatibility projection for `accepted` only |
| `verification_deferred` | completion was not yet proven at callback return |

### Behavioral test index

- `src/Rook.Tests/InternalBridge/GhDocumentLifecycleTests.cs`
- `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`
- `src/Rook.Tests/Handlers/GhMutationSolveSuspensionTests.cs`
- `src/Rook.Tests/Handlers/GhPostMutationSchedulePolicyTests.cs`
- `src/Rook.Tests/Handlers/GhScheduleInvokerTests.cs`
- `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`
- `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`
- `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`
- `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
- `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`
- `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`
- `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- `mcp_server/tests/test_gh_update_script_defer.py`
- `mcp_server/tests/test_server_contract_hardening.py`
