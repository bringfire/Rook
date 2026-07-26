# Rhino.Inside.Revit Grasshopper Document Lifecycle Design

**Date:** 2026-07-26

**Status:** Draft specification awaiting review

**Target:** `src/Rook` managed Grasshopper bridge and its tests

**Deployment unit:** One atomic Grasshopper lifecycle-and-solver behavior release

## Purpose

Replace Rook's orphaned Grasshopper document creation and competing Rhino.Inside.Revit solver-state ownership with one transactional document lifecycle and one host-aware asynchronous solve policy.

The production invariant is indivisible:

> Every Rook-created or Rook-opened top-level Grasshopper document is registered with `Grasshopper.Instances.DocumentServer` before Rook treats it as active, and Rook never writes the active document's `Enabled` property while running inside Revit.

Registration and solver ownership may be prepared in separate non-deployable commits, but the production route cutover, solver-policy cutover, removal of direct RiR `Enabled` writers, and doctrine update ship as one atomic behavior commit and one local/release deployment.

## Linked incident

This design and [RookBIM File-Workshared Document Identity Design](2026-07-26-rookbim-file-workshared-identity-design.md) came from the same Revit 2024.3 investigation but correct different runtime boundaries.

The RookBIM incident exposed an invalid document-identity assumption. During live acceptance work, a separate Grasshopper/RiR failure appeared: Rook reported scheduled solutions while components remained blank. Exact-source inspection and a live A/B test showed that Rook assigned documents directly to `GH_Canvas.Document` without first registering them. Registering the same failing document caused ordinary Grasshopper and real RiR components to compute through RiR's activation-gated replay.

The two designs have separate implementation plans, deployments, acceptance reports, and rollback paths. Neither is a prerequisite for understanding or rolling back the other.

## Evidence

The diagnosis is based on the exact loaded runtime:

- Revit 2024.3, `RevitAPI` 24.3.40.0;
- Rhino and Grasshopper 8.33.26188.13001;
- Rhino.Inside.Revit 1.35.9651.15514 at source revision `e1d9c58a9fc2770aa8c977b09f44338d3955057f`;
- Rook 1.5.16.0.

The relevant source behavior is:

- Rook's `NewDocument`, `OpenDocument`, and implicit context path construct or load a `GH_Document` and assign it to the canvas without `DocumentServer.AddDocument`.
- `GH_Canvas.Document` calls `DocumentServer.PromoteDocument`; promotion does not add an unknown document.
- `GH_DocumentServer.AddDocument` adds by object reference and raises `DocumentAdded`.
- RiR subscribes to `DocumentAdded` and attaches its solution, transaction, and pending-replay handlers there.
- Grasshopper may raise `SolutionStart` and `SolutionEnd` while `document.Enabled == false` prevents `SolveAllObjects`.
- Grasshopper's global solver guard applies to registered documents; an unregistered document can bypass part of normal global lock behavior.

The decisive live A/B used the same active graph and deployed Rook path:

- unregistered: solution events occurred, but slider and panel remained blank;
- registered with only `DocumentServer.AddDocument(document)`: the same edit computed;
- registered and intentionally `Enabled == false`: RiR observed the disabled attempt and replayed it under `ActivationGate` without a Rook `Enabled` write;
- seven real RiR components computed with zero Grasshopper errors or warnings.

The eventual acceptance report must preserve the commands, timestamps, exact versions, registration observations, solver observations, and component results in a durable redacted artifact. Conversation history alone is not an acceptance artifact.

## Goals

This design will:

- remove implicit and duplicate Grasshopper document creation;
- preserve the genuinely empty `/gh/document/new` contract;
- give `/gh/document/open` duplicate-safe standard path behavior;
- make registration and canvas activation one reconciled transaction;
- define commit, rollback, ownership, and partial-failure semantics;
- prevent reentrant lifecycle mutations;
- make RiR registration state an explicit solve-policy input;
- make scheduling capability and invocation failure explicit solve outcomes;
- let RiR own `GH_Document.Enabled` inside Revit;
- preserve the standalone Rhino suspension and solver policy;
- preserve the global solver's unavailable state without calling it a proven user lock;
- retain existing `rir_repair_*` response fields temporarily as neutral deprecated fields;
- supersede source contracts and design doctrine that say `DocumentServer` registration is irrelevant;
- delete replaced implementation and tests rather than layering a second lifecycle over them.

## Non-goals

This design will not:

- add Autodesk/Revit references to `src/Rook`;
- add a new Revit external-event dispatcher for Grasshopper solutions;
- synchronize HTTP completion with final RiR computation;
- claim that scheduling proves component execution;
- redesign Grasshopper's multi-document user interface;
- change the `/gh/document/new` route to load a Grasshopper template;
- change unrelated Grasshopper mutation, undo, readiness-receipt, or component-inspection contracts;
- fix the separate `/gh/inspect-output` ambiguous-reflection defect;
- retain obsolete code solely to keep old source-contract tests green.

## Existing defects to remove

### Implicit creation

`GrasshopperHandler.GetGrasshopper()` currently defaults to `createDocumentIfMissing: true`. Both `NewDocument` and `OpenDocument` call it with that default. On an empty canvas, either route therefore creates and activates a temporary orphan before creating or opening the requested document.

`GrasshopperCore.ResolveContext` contains a second implicit creation branch. Its current callers pass `false`, so the branch is dormant and should be deleted rather than repaired.

Context resolution after this change is observational only. It may resolve the loaded Grasshopper assembly, current `ActiveCanvas`, current canvas document, and registration state. It never creates, registers, activates, closes, removes, or disposes a document.

### Competing `Enabled` owners

`GhSolveReadinessCoordinator` currently writes `document.Enabled = true` and subscribes to `EnabledChanged` to repeat that repair during a transition window.

`GhDocumentSolveSuspension` also writes `Enabled = false` and restores `true` after the five-second deferred scheduling handoff. RiR may close its activation gate during that interval, so the delayed restore can overwrite host-owned state.

Both RiR write paths are removed. RiR's registered-document handlers and activation gate remain the only `Enabled` owner inside Revit.

## Architecture

### `GhDocumentLifecycle`

A focused internal reflection-based helper under `src/Rook/InternalBridge` owns document creation, path opening, registration verification, canvas activation, reconciliation, rollback, and bounded lifecycle results. It has no Rhino.Inside.Revit or Autodesk references.

The helper operates on closed internal types rather than arbitrary dictionaries. Its result distinguishes:

- operation: `new` or `open`;
- candidate document reference, when observable;
- previous document reference;
- captured canvas reference;
- whether the path was already registered;
- whether this invocation created or registered a document;
- registration success and verified server index;
- activation success;
- commit status;
- rollback attempted/completed;
- observed final active and registered state;
- bounded lifecycle code and warnings.

The helper never returns an unverified candidate as a successful document.

### Rhino UI-thread boundary

The complete lifecycle transaction executes on the Rhino UI thread. The route must enter the UI thread once and keep creation/opening, server reconciliation, activation, and rollback inside that invocation.

The transaction captures `Grasshopper.Instances.ActiveCanvas` at entry. The same canvas must remain active immediately before and immediately after every mutating boundary. Object reference, not window title or document path, defines sameness.

Mutating boundaries are:

- `AddDocument(document, out success)` for new;
- `AddDocument(path, true)` for open;
- `canvas.Document = candidate` for new activation;
- `canvas.Document = previous` during rollback;
- `DocumentServer.RemoveDocument(candidate)` during rollback.

Host callbacks raised by `DocumentAdded`, `DocumentRemoved`, and canvas assignment may run synchronously and may change the active canvas even though execution remains on the UI thread. The helper therefore checks the captured canvas immediately before and after each boundary.

### Reentrancy guard

Lifecycle operations use one process-wide, UI-thread reentrancy guard shared by every `GhDocumentLifecycle` and handler instance. The guard is static process state, not an instance field. A nested Rook lifecycle call through the same or a different helper/handler instance fails with `gh_document_lifecycle_reentrant` before performing any mutation.

The guard is not a general cross-thread lock and must not block the Rhino UI thread waiting for another lifecycle call. Existing route marshaling serializes normal entry; the guard protects synchronous callback reentry. It is always released in `finally`, including rollback and exception paths.

### Server snapshots

Before mutation, the helper snapshots the server's registered top-level documents by object reference in server order. It also records:

- the previous captured-canvas document;
- the document currently registered for the requested open path, if any;
- the candidate's preexisting server index, if a candidate already exists;
- the active canvas reference.

After each mutation, it snapshots the same values again. Filepath comparisons help locate the open-path entry, but ownership and rollback decisions use reference membership in the pre-transaction snapshot.

## New-document transaction

The `/gh/document/new` route preserves empty-document semantics and does not call `AddNewDocument`, because that method loads the configured Grasshopper template when one exists.

The required sequence is:

```text
capture canvas/server/previous document
→ construct exactly one empty GH_Document
→ verify captured ActiveCanvas unchanged
→ DocumentServer.AddDocument(candidate, out success)
→ verify captured ActiveCanvas unchanged
→ verify success == true
→ verify IndexOf(candidate) >= 0 and server[index] is candidate
→ verify captured ActiveCanvas unchanged
→ capturedCanvas.Document = candidate
→ verify captured ActiveCanvas unchanged
→ verify capturedCanvas.Document is candidate
→ verify candidate remains registered by reference
→ commit
```

`registered + active on the captured canvas` is the commit point. Registration alone is not success, and canvas assignment alone is not success.

If construction succeeds but registration does not, the candidate is directly disposed only after verifying it was never registered and is not active on the captured or current active canvas.

## Open-document transaction

The `/gh/document/open` route uses `DocumentServer.AddDocument(path, makeActive: true)` because it preserves Grasshopper's duplicate-path behavior: an already registered path returns and activates the existing registered document.

The required sequence is:

```text
validate the requested file before UI dispatch
→ capture canvas/server/previous document/path registration
→ verify captured ActiveCanvas unchanged
→ call AddDocument(path, true)
→ immediately recapture ActiveCanvas and server references
→ resolve the returned and observed path document
→ verify one candidate reference is registered
→ verify capturedCanvas.Document is that same candidate
→ verify captured ActiveCanvas is still current
→ commit
```

If the path was registered before the call, the returned candidate must be the same preexisting reference. The transaction never removes or disposes that document, even if activation or a later check fails.

If the returned document and the observed registered/active path document are both non-null but differ by reference, the result is inconsistent and cannot commit. If the method returns `null` but reconciliation finds exactly one newly registered candidate which is active on the captured canvas, the registered-and-active state is authoritative and may commit with a bounded `open_returned_null_after_commit` warning. Any ambiguous set of new candidates fails and enters conservative reconciliation.

`AddDocument(path, true)` catches its own exceptions and can return `null` after performing part of the operation. A null return is therefore not sufficient evidence that nothing changed. The helper reconciles pre/post server reference sets and both the captured and current active canvas before choosing rollback actions.

## Commit and post-commit behavior

Commit occurs only after the candidate is both registered and active on the captured canvas by reference.

After commit, the following are auxiliary:

- readiness-session attachment;
- ID-registry reset;
- canvas refresh;
- object counting;
- registration telemetry projection;
- deprecated-field projection.

An auxiliary exception cannot turn the route into a failure while the new document remains active. The route returns success with a bounded warning code and the actual known committed state. Object count may be `null` when unavailable.

This prevents a false failure response that invites a caller to retry an operation which already committed.

## Rollback and partial state

Rollback applies only before commit or when a post-mutation verification proves that the intended commit state was never reached.

The rollback order is mandatory:

1. Inspect the captured canvas, current active canvas, previous document, candidate, and server reference set.
2. Restore the previous document on the captured canvas before removing the candidate.
3. Reinspect both known canvases and the server.
4. If this invocation newly registered the candidate, and the candidate is no longer active on either known canvas, remove it through `DocumentServer.RemoveDocument`.
5. Reinspect final state.

`RemoveDocument` owns disposal for a registered document. Rook never directly disposes a registered candidate.

Rook never removes:

- a document present in the pre-transaction reference snapshot;
- an existing duplicate-path document;
- a document still active on the captured canvas;
- a document observed active on the current `ActiveCanvas` after callback reentry.

Before removal or direct disposal, the helper checks every canvas reference discoverable through the supported Grasshopper API, including at minimum the captured and current active canvas. If it cannot establish that the candidate is inactive, it preserves the document and reports incomplete rollback. Uncertainty never authorizes disposal.

If previous-canvas restoration fails or the active canvas changes during rollback, the helper stops destructive cleanup, preserves the still-active candidate, and returns a failure with `rollbackIncomplete = true` and bounded observed state. It does not claim that the old document was restored or the candidate removed.

Failure results use bounded codes such as:

- `gh_document_lifecycle_reentrant`;
- `gh_document_registration_failed`;
- `gh_document_activation_failed`;
- `gh_document_canvas_changed`;
- `gh_document_rollback_incomplete`.

No result contains arbitrary exception objects. Existing route error conventions may include bounded exception type/message only where already allowed; diagnostics and telemetry must not add paths or document contents.

## Solver ownership and policy

### Required inputs

The pure post-mutation solve decision receives independent evidence:

- solve requested;
- running inside Rhino.Inside.Revit;
- document registration known;
- document registered;
- global `GH_Document.EnableSolutions` state;
- instance `document.Enabled` state;
- scheduling API availability.

It does not collapse the global and instance flags before applying host policy.

### Policy matrix

| Host and state | Decision | Classification |
|---|---|---|
| Solve not requested | Do not schedule | `solve_not_requested` |
| RiR, registration known false | Do not schedule | `rir_document_unregistered` |
| RiR, registration unknown | Do not schedule or claim useful scheduling | `rir_registration_unknown`; verification deferred |
| RiR, registered, global false | Do not schedule; allow later host restoration to remain authoritative | `global_solver_unavailable`; verification deferred |
| RiR, registered, global true, instance false | Schedule asynchronously without changing `Enabled` | `rir_mediated_schedule_requested`; verification deferred |
| RiR, registered, global true, instance true | Schedule asynchronously | `async_schedule_requested`; verification deferred until observed |
| RiR, registered, global true, instance unknown | Request one safe asynchronous schedule without changing either solver flag | `rir_instance_solver_state_unknown`; verification deferred |
| RiR, registered, global unknown | Request one safe asynchronous schedule without changing either solver flag | `global_solver_state_unknown`; verification deferred |
| Standalone, global false | Do not schedule | `global_solver_unavailable` |
| Standalone, global true, instance false | Do not schedule | `document_solver_disabled` |
| Standalone, global true, instance true | Preserve current safe asynchronous schedule | `async_schedule_requested` |
| Standalone, global unknown, instance false | Do not schedule | `document_solver_disabled` |
| Standalone, global unknown, instance true or unknown | Preserve current safe asynchronous fail-open behavior | `solver_state_unknown`; verification deferred |
| Standalone, global true, instance unknown | Preserve current safe asynchronous fail-open behavior | `solver_state_unknown`; verification deferred |
| Any host, state otherwise permits scheduling, scheduling API absent | Do not schedule | `schedule_api_unavailable`; `solveScheduled = false` |
| Any host, scheduling adapter rejects or invocation throws | No schedule was accepted | `schedule_request_failed`; `solveScheduled = false` |

The table first decides whether host and solver state permit a schedule attempt. Scheduling capability is then applied only to rows which would schedule:

- if the reflected `ScheduleSolution(int)` API is absent, do not invoke anything and return `schedule_api_unavailable` with `solveScheduled = false`;
- if the scheduling adapter rejects the request or invocation throws, return `schedule_request_failed` with `solveScheduled = false` and a bounded warning;
- if invocation returns without rejection or exception, `solveScheduled = true` means only that Grasshopper accepted the asynchronous scheduling call. It never means that a solution completed or that RiR deferred/replayed it.

API-unavailable and invocation-failure outcomes are conclusive about Rook's attempt and do not set verification-deferred merely because a schedule did not occur. The bounded failure result may contain the exception type already allowed by route conventions, but never a raw exception, stack trace, arbitrary message, path, or document content. A missing scheduling API or failed invocation never causes an `Enabled` write or a synchronous fallback.

`global_solver_unavailable` is deliberately neutral. The public getter returns false when Grasshopper cannot solve as well as when its underlying global flag is disabled, and RiR temporarily disables that flag during document registration. Rook must not label every false result a user lock.

`rir_mediated_schedule_requested` is observationally precise: Rook requested an asynchronous solution on a registered RiR document. It does not claim RiR queued or replayed the solution. Actual RiR deferral may be reported only by a later observable readiness or solution event that proves it.

### RiR batch suspension

Inside RiR, `GhDocumentSolveSuspension.Begin` is a no-op and never writes `document.Enabled`. The normal mutation path continues to use non-synchronous expiration and one asynchronous schedule request.

Standalone Rhino retains the current batch suspension behavior in this change. Any later attempt to simplify standalone suspension requires its own evidence and design; it is outside this incident boundary.

### Removal of readiness repair

`GhSolveReadinessCoordinator`, its transition subscription, its direct `Enabled` writes, and its Rook-managed-document state are removed from production construction and scheduling.

Existing `rir_repair_attempted`, `rir_repair_held`, `rir_repair_reason`, and `rir_repair_source` fields remain temporarily for wire compatibility. They are marked deprecated and emitted as neutral values (`false`, `false`, `null`, `null`). They do not drive behavior. New registration and schedule-classification fields are additive.

## Rejected alternatives

- `Grasshopper.Instances.DocumentServer.AddNewDocument()` is rejected for `/new` because it can load the configured template and therefore violates the route's intentionally empty-document contract.
- Reimplementing path opening with `GH_DocumentIO` is rejected because it duplicates Grasshopper's registered-path and duplicate-document policy while making partial ownership harder to reconcile.
- Grasshopper scripting APIs are not inherently RiR-specific, but they are rejected for this deterministic API route because they can activate the editor, surface recovery prompts, and provide weaker machine-readable failure evidence than the document-server transaction.
- Keeping the readiness coordinator as a fallback is rejected because it would preserve a second `Enabled` owner and make the RiR policy unverifiable.

## Route result contract

New/open success data includes bounded evidence equivalent to:

- `lifecycleCommitted`;
- `documentRegistered`;
- `documentActive`;
- `registrationIndex`, when known;
- `existingDocumentReused` for open;
- `rollbackAttempted` and `rollbackIncomplete` only when relevant;
- `warnings` as closed codes.

Post-mutation responses add a neutral schedule classification and registration-known/registered evidence. They retain existing fields unless removal is separately versioned.

The result shape must not expose internal document objects, raw filesystem paths beyond the route's existing response, arbitrary callback data, or exception objects.

## Cleanup and doctrine

The implementation deletes or supersedes:

- implicit creation in `GrasshopperHandler.GetGrasshopper`;
- dormant implicit creation in `GrasshopperCore.ResolveContext`;
- manual open through `GH_DocumentIO` in the route;
- `GhSolveReadinessCoordinator` and its tests;
- RiR delayed `Enabled` restoration;
- tests that require successful RiR repair writes;
- tests that assert registration is irrelevant;
- the claim in `2026-06-13-rir-gh-solver-enabled-race-design.md` that `DocumentServer.AddDocument` is rejected.

The June 13 design remains as historical evidence but receives a prominent superseded notice linking to this specification. Replacement tests must land in the same behavior change that removes obsolete tests.

Cleanup stays inside document lifecycle, solver ownership, and their response evidence. It does not authorize unrelated Grasshopper refactoring.

## Commit and deployment boundaries

Reviewable commits may be:

1. Preparatory lifecycle helper plus isolated tests, unused by production routes.
2. Additional pure solver-policy tests or compatibility DTO preparation, still behavior-neutral.
3. One atomic behavior commit containing route cutover, solver-policy cutover, direct-writer removal, deprecated telemetry neutralization, obsolete-test replacement, and doctrine supersession.

Only commit 3 and its prerequisites together are deployable. No local deployment, release artifact, or live acceptance run may contain registered production routes with the old RiR repair coordinator, or the new solver policy with orphan-producing routes.

Build and deployment use the normal local-testing workflow. `src/RookBim` need not change for this design.

## Testing

### Lifecycle unit and source-contract tests

Tests must prove:

- context resolution cannot create documents;
- `/new` constructs exactly one empty document;
- `/new` calls the registration overload with an out success value;
- template-loading `AddNewDocument` is not used;
- registration succeeds before canvas assignment;
- `DocumentAdded` precedes activation;
- candidate identity and `IndexOf` are verified by reference;
- commit requires registered and active;
- `/open` uses the path overload;
- duplicate-path open reuses the preexisting reference;
- a null `AddDocument(path, true)` return after partial registration is reconciled from reference snapshots rather than treated as no-op;
- conflicting returned, registered, and active candidate references cannot commit;
- a preexisting document is never removed or disposed;
- a rejected unregistered new document is disposed;
- a registered rollback uses `RemoveDocument`, not direct disposal;
- previous canvas restoration precedes removal;
- an active document is never removed or disposed;
- active-canvas change is detected before and after every mutating boundary;
- disposal/removal is withheld when any discoverable canvas still owns the candidate or canvas enumeration is uncertain;
- synchronous callback reentry is rejected;
- nested entry through two different lifecycle-helper or handler instances is rejected by the same process-wide guard;
- the reentrancy guard is released on every exit;
- incomplete rollback reports actual final state;
- auxiliary post-commit failures return success with warnings;
- no implicit creation remains in either context resolver.

### Solver tests

Tests must cover every policy row, including:

- registered RiR plus instance disabled schedules without an `Enabled` write;
- global false produces `global_solver_unavailable`, not `solver_locked` or `user_lock`;
- RiR's temporary global disable followed by gate restoration does not trigger a repair write;
- unregistered RiR does not pretend scheduling is useful;
- unknown registration cannot be reported as registered;
- registered RiR with known-global/unknown-instance state makes one safe asynchronous request without flag writes and reports `rir_instance_solver_state_unknown`;
- a missing scheduling method reports `schedule_api_unavailable` and `solveScheduled = false`;
- a scheduling adapter rejection or thrown invocation reports `schedule_request_failed` and `solveScheduled = false` without synchronous fallback;
- `solveScheduled = true` proves only accepted asynchronous invocation, never completed computation;
- `rir_mediated_schedule_requested` remains verification-deferred;
- no response claims actual RiR deferral without a later proving event;
- standalone combined-state and suspension behavior remains unchanged;
- the global solver flag is never written by Rook;
- instance `Enabled` is never written on an RiR path;
- deprecated repair fields remain present and neutral.

### Live acceptance gate

Acceptance requires a fresh Revit/Rhino/RiR process and records exact versions and the deployed Rook commit. It must cover:

1. Empty canvas, `/gh/document/new`: exactly one registered active empty document.
2. A configured Grasshopper template: `/new` remains empty.
3. `/gh/document/open`: registered and active document with correct path.
4. Reopen the same path: the existing reference is reused; document count does not grow.
5. Failure/rollback exercise using a controlled test seam or safe fixture: previous canvas restored and new registration removed.
6. Ordinary slider-to-panel mutation: actual volatile output, not events alone.
7. Registered RiR document with instance disabled: asynchronous request, disabled attempt, activation-gated successful replay.
8. Real RiR components: Active Document, Document Identity, Document Worksharing, Active View, View Identity, Query Rooms, and Query Views compute without errors.
9. Global solver unavailable and restored: no forced `Enabled` write, no crash, and later host restoration remains functional.
10. Standalone Rhino new/open/mutation behavior.

Source-contract tests and event counts alone cannot satisfy this gate. Component phase and output data must prove execution.

## Rollback

Rollback is the complete atomic Grasshopper behavior release. It must restore the previous route and solver implementation together. Operators must not mix binaries that contain only registration or only solver-ownership changes.

Because rollback restores a known orphan-document defect and competing RiR `Enabled` ownership, it is an emergency compatibility action, not a safe steady state. The rollback report must state that RiR Grasshopper automation is unsupported until the corrected atomic release is restored.

## Approval gate

This specification is definitive but does not authorize implementation until reviewed and approved. After approval it receives its own implementation plan. The separate RookBIM identity specification and its CreationGUID decision gate do not block this plan.
