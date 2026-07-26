# Rhino.Inside.Revit Grasshopper Document Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace orphan-producing Grasshopper document creation and Rook-owned RiR solver writes with one transactional registration lifecycle and one host-aware, immediate asynchronous scheduling path.

**Architecture:** A reflection-backed `GhDocumentLifecycle` owns create/open registration, activation, commit, reconciliation, and rollback on the existing Rhino UI callback. Separate pure scheduling policy, invocation, and standalone-suspension helpers are prepared without production use; one later atomic behavior commit cuts every production route over, removes the RiR readiness coordinator and five-second scheduler, and updates the historical doctrine. A fresh Revit/Rhino.Inside/Grasshopper run is the acceptance gate.

**Tech Stack:** C# targeting `net8.0;net7.0;net48`, reflection over the loaded Grasshopper 8 assembly, RhinoCommon's existing UI callback bridge, xUnit 2.9.2 on `net48`, and Windows PowerShell for build/deployment.

**Execution model:** After the temporary RookBIM CreationGUID probe plan has been executed, rolled back, and reviewed to an identity decision, execute Tasks 1-3 sequentially in a dedicated Grasshopper implementation worktree. Tasks 1 and 2 are preparatory, behavior-neutral commits and must not be deployed. Task 3 is the one atomic production behavior commit and must include the route cutover, solver-policy cutover, removal of every RiR `Enabled` writer, obsolete-test replacement, and doctrine supersession. Execute Task 4 inline with the operator because it stops host processes, deploys, and drives live Rhino/Revit/Grasshopper state. This order prevents the probe rollback from replacing an accepted Grasshopper build.

Before Task 1, use `superpowers:using-git-worktrees` and create the implementation branch from the reviewed plan amendment. The initial two-plan commit must directly follow the final approved spec commit; the amendment must directly follow that initial commit; both commits must change only the two plan files:

```powershell
Set-Location 'C:\Users\aryan\source\repos\Rook'
$specBaseline = '761a42af1d5c083dd69ee0908531c7d36a7b9995'
$initialPlanCommit = '2e224695783a712506286bac9943ebccfbccb572'
$ghPlan = 'docs/superpowers/plans/2026-07-26-rir-grasshopper-document-lifecycle.md'
$bimPlan = 'docs/superpowers/plans/2026-07-26-rookbim-creation-guid-probe.md'
$planCommit = (git log -1 --format=%H -- $ghPlan).Trim()

if ((git rev-parse "$initialPlanCommit^").Trim() -ne $specBaseline) {
    throw 'Initial two-plan commit does not directly follow 761a42af'
}
$initialChanged = @(git diff-tree --no-commit-id --name-only -r $initialPlanCommit)
$expected = @($bimPlan, $ghPlan) | Sort-Object
if ((Compare-Object ($initialChanged | Sort-Object) $expected)) {
    throw 'Initial plan commit changed files outside the two implementation plans'
}
if ((git rev-parse "$planCommit^").Trim() -ne $initialPlanCommit) {
    throw 'Reviewed plan amendment does not directly follow 2e224695'
}
$changed = @(git diff-tree --no-commit-id --name-only -r $planCommit)
if ((Compare-Object ($changed | Sort-Object) $expected)) {
    throw 'Reviewed plan amendment changed files outside the two implementation plans'
}

git worktree add .worktrees/rir-gh-document-lifecycle -b codex/rir-gh-document-lifecycle $planCommit
if (git -C .worktrees/rir-gh-document-lifecycle status --porcelain) {
    throw 'Grasshopper implementation worktree is not clean'
}
Set-Location (Resolve-Path '.worktrees/rir-gh-document-lifecycle')
dotnet restore src\Rook.Tests\Rook.Tests.csproj
if ($LASTEXITCODE -ne 0) {
    throw 'Grasshopper implementation worktree restore failed'
}
```

The two pre-existing FFmpeg modifications remain only in the original checkout. They must not appear in this worktree or any task commit.

## Global Constraints

- Treat `docs/superpowers/specs/2026-07-26-rir-grasshopper-document-lifecycle-design.md` as authoritative; stop for review before deviating.
- Keep registration and solver ownership one deployable change even though unused helpers and their tests land first.
- Keep all Grasshopper access reflection-based in `src/Rook`; add no Grasshopper or Revit project reference and no external dependency.
- Keep Autodesk/Revit references out of `src/Rook`.
- Run the complete document transaction on the existing Rhino UI callback. Capture one `ActiveCanvas` reference and verify that exact reference immediately before and after every mutating boundary.
- Compare server snapshots and candidates by `ReferenceEquals`; paths locate candidates but never establish transaction ownership.
- Define commit as the candidate being both registered and active on the captured canvas by reference.
- Restore the captured previous canvas document before removing a newly registered candidate. A captured `null` document is real empty-canvas state and must be assigned and verified, not skipped. Never remove a preexisting document and never dispose a document active on any discoverable canvas.
- After commit, readiness attachment, ID reset, refresh, object counting, and telemetry failures become bounded warnings on a successful response.
- Context lookup is observational. It never creates, registers, activates, removes, closes, or disposes a document.
- Inside RiR, Rook performs no `Enabled` or global `EnableSolutions` write. Standalone Rhino retains temporary instance suspension only during mutation.
- `/gh/edit` order is mutation, `ExpireSolution(false)`, structural snapshot, standalone restoration, one `ScheduleSolution(delay >= 1)` invocation, then response.
- `ScheduleAcceptance` is authoritative. `SolveScheduled` is true only for confirmed `Accepted`; false does not prove no pending schedule when acceptance is `Unknown`.
- Exact solve-evidence wire keys are `schedule_classification`, `schedule_acceptance`, `schedule_failure_code`, and retained `solve_scheduled`. Emit no camelCase duplicates.
- A scheduling target exception produces `Unknown`/`schedule_acceptance_unknown`, deferred verification, and no retry.
- Use no synchronous solve, delay zero, `NewSolution`, `Task.Run` scheduling handoff, second UI dispatch, or second Rook scheduler.
- Retain `rir_repair_attempted`, `rir_repair_held`, `rir_repair_reason`, and `rir_repair_source` only as deprecated neutral fields.
- Stage explicit paths only. Do not modify or commit unrelated files from the original checkout.
- Commit before deploy so the live report can name an exact implementation commit.

---

## File Map

New production files:

- `src/Rook/InternalBridge/GhDocumentLifecycle.cs`: reflection host adapter, process-wide reentrancy guard, reference snapshots, create/open transactions, commit, rollback, and closed lifecycle result.
- `src/Rook/Handlers/GhPostMutationSchedulePolicy.cs`: closed classification/acceptance/failure vocabularies, pure host policy, exhaustive wire mapping, and the final schedule result.
- `src/Rook/Handlers/GhScheduleInvoker.cs`: exactly-once reflected positive-delay `ScheduleSolution` invocation with conservative unknown-acceptance handling.
- `src/Rook/Handlers/GhMutationSolveSuspension.cs`: RiR no-op and standalone mutation-time suspension with explicit one-shot restoration result.

New tests:

- `src/Rook.Tests/InternalBridge/GhDocumentLifecycleTests.cs`
- `src/Rook.Tests/Handlers/GhPostMutationSchedulePolicyTests.cs`
- `src/Rook.Tests/Handlers/GhScheduleInvokerTests.cs`
- `src/Rook.Tests/Handlers/GhMutationSolveSuspensionTests.cs`

Production cutover files:

- `src/Rook/Handlers/GrasshopperHandler.cs`
- `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`
- `src/Rook/Handlers/GrasshopperHandler.Readiness.cs`
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- `src/Rook/InternalBridge/GrasshopperCore.cs`, including the `GrasshopperStatusDto` fields currently defined at the end of that file.
- `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`
- `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`
- `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`
- `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`
- `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`
- `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
- `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`
- `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- `docs/superpowers/specs/2026-06-13-rir-gh-solver-enabled-race-design.md`

Deleted in the atomic cutover:

- `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs`
- `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs`
- `src/Rook/Handlers/GhSolvePolicy.cs` after all callers use `GhPostMutationSchedulePolicy`.

Explicitly unchanged:

- `src/RookBim/**`
- `src/RookNative/**`
- native callback ABI and public route registration
- solve receipt registry/lifecycle subscriptions except their projection from the new schedule result
- unrelated Grasshopper mutation and inspection behavior

---

### Task 1: Transactional document lifecycle helper, unused by production

**Files:**
- Create: `src/Rook/InternalBridge/GhDocumentLifecycle.cs`
- Create: `src/Rook.Tests/InternalBridge/GhDocumentLifecycleTests.cs`

**Interfaces:**
- Produces `IGhDocumentLifecycleHost`, implemented privately by `ReflectionGhDocumentLifecycleHost` and faked by tests.
- Produces `GhDocumentLifecycle.CreateNew()` and `GhDocumentLifecycle.Open(string path)`, each returning `GhDocumentLifecycleResult`.
- Produces `GhDocumentRegistrationState GhDocumentLifecycle.InspectRegistration(object document)` for the Task 3 solve-policy cutover.
- Production routes do not instantiate or call this helper until Task 3.

The host/test seam is exact:

```csharp
internal interface IGhDocumentLifecycleHost
{
    object? GetActiveCanvas();
    object? GetCanvasDocument(object canvas);
    void SetCanvasDocument(object canvas, object? document);
    IReadOnlyList<object> SnapshotDocuments();
    object CreateEmptyDocument();
    bool AddNewDocument(object document); // invokes AddDocument(document, out success)
    object? OpenDocument(string path, bool makeActive);
    int IndexOf(object document);
    string? GetDocumentFilePath(object document);
    bool? IsActiveOnAnySupportedCanvas(object document, object capturedCanvas);
    void RemoveDocument(object document);
    void DisposeDocument(object document);
}

internal readonly struct GhDocumentRegistrationState
{
    public bool Known { get; init; }
    public bool Registered { get; init; }
    public int? Index { get; init; }
}
```

- [ ] **Step 1: Write the failing new-document transaction tests**

Build a fake host that records ordered calls, exposes mutable `ActiveCanvas`, `CanvasDocument`, and an object-reference server list, and can synchronously mutate the active canvas from each host callback. The first tests assert this exact success order and commit condition:

Put the suite in an xUnit collection with `DisableParallelization = true` because the production guard is intentionally process-wide; reset only fake host state between tests and never add a test-only guard reset.

```csharp
var result = lifecycle.CreateNew();

Assert.True(result.Committed);
Assert.Same(candidate, result.Document);
Assert.True(result.DocumentRegistered);
Assert.True(result.DocumentActive);
Assert.Equal(0, result.RegistrationIndex);
Assert.Equal(new[]
{
    "snapshot",
    "create_empty",
    "active_canvas_before_add_new",
    "add_new_with_out_success",
    "active_canvas_after_add_new",
    "verify_registration",
    "active_canvas_before_activation",
    "activate_candidate",
    "active_canvas_after_activation",
    "verify_commit",
}, host.Events);
```

Add cases for `out success == false`, missing `IndexOf`, mismatched server reference at the returned index, activation failure, canvas change before/after registration, canvas change before/after activation, and synchronous reentry through a second `GhDocumentLifecycle` instance. Assert the static guard rejects reentry before mutation and releases after success, exception, and rollback.

- [ ] **Step 2: Write the failing open/reconciliation/rollback tests**

Cover all ownership branches:

- duplicate path returns and activates the exact preexisting reference without growing the server;
- `AddDocument(path, true)` returns null after registering and activating exactly one new reference, which commits with warning `open_returned_null_after_commit`;
- returned, registered, and active references conflict, which cannot commit;
- ambiguous post-call additions cannot commit;
- rollback restores the previous canvas before `RemoveDocument`;
- rollback from a captured empty canvas assigns `null`, verifies the canvas is empty by reference, and only then removes a now-inactive candidate;
- a preexisting or duplicate-path document is never removed or disposed;
- a newly registered inactive candidate is removed through `RemoveDocument`, never directly disposed;
- a never-registered inactive new candidate is directly disposed;
- a candidate active on captured or current canvas is preserved;
- inability to enumerate supported canvases preserves the candidate and reports incomplete rollback;
- callback-driven canvas replacement after restore stops destructive cleanup and reports actual final state.

Include a case that captures `CanvasDocument == null`, activates the candidate, then fails commit verification. Assert rollback calls `SetCanvasDocument(capturedCanvas, null)`, observes the candidate inactive, and removes it only after the empty canvas is restored. Use event-order assertions, not only final booleans:

```csharp
Assert.True(host.Events.IndexOf("restore_previous_canvas") >= 0);
Assert.True(host.Events.IndexOf("remove_new_candidate") >
            host.Events.IndexOf("restore_previous_canvas"));
Assert.True(result.RollbackAttempted);
Assert.False(result.RollbackIncomplete);
```

- [ ] **Step 3: Verify the lifecycle tests fail for missing types**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~GhDocumentLifecycleTests --verbosity minimal
```

Expected: compile failure naming `GhDocumentLifecycle`/its contracts, not a test-host or Rhino dependency failure.

- [ ] **Step 4: Implement the closed lifecycle contracts and reflection host**

Define closed enums rather than caller-selected strings:

```csharp
internal enum GhDocumentLifecycleOperation { New, Open }

internal enum GhDocumentLifecycleCode
{
    None,
    Reentrant,
    CanvasUnavailable,
    CanvasChanged,
    RegistrationFailed,
    ActivationFailed,
    InconsistentState,
    RollbackIncomplete,
}

internal enum GhDocumentLifecycleWarning
{
    OpenReturnedNullAfterCommit,
    ReadinessAttachmentFailed,
    IdRegistryResetFailed,
    CanvasRefreshFailed,
    ObjectCountFailed,
    TelemetryProjectionFailed,
}
```

`GhDocumentLifecycleWire` maps codes exactly to `none`, `gh_document_lifecycle_reentrant`, `gh_document_canvas_unavailable`, `gh_document_canvas_changed`, `gh_document_registration_failed`, `gh_document_activation_failed`, `gh_document_inconsistent_state`, and `gh_document_rollback_incomplete`. Warning mappings are `open_returned_null_after_commit`, `readiness_attachment_failed`, `id_registry_reset_failed`, `canvas_refresh_failed`, `object_count_failed`, and `telemetry_projection_failed`. Undefined enum values throw.

`GhDocumentLifecycleResult` contains the operation, candidate/previous/captured-canvas references for same-call internal use, `PathAlreadyRegistered`, `CreatedDocument`, `RegisteredByThisCall`, `RegistrationSucceeded`, nullable `RegistrationIndex`, `ActivationSucceeded`, `Committed`, `RollbackAttempted`, `RollbackIncomplete`, observed final active/registered booleans, one code, and a bounded deduplicated warning list. It contains no raw exception.

The host adapter must reflect these exact Grasshopper members:

```text
Grasshopper.Instances.ActiveCanvas
Grasshopper.Instances.DocumentServer
GH_DocumentServer.AddDocument(GH_Document, out bool)
GH_DocumentServer.AddDocument(string, bool)
GH_DocumentServer.IndexOf(GH_Document)
GH_DocumentServer.RemoveDocument(GH_Document)
GH_Canvas.Document
GH_Document.FilePath
GH_Document.Dispose()
```

Do not use `AddNewDocument` or `GH_DocumentIO`. Snapshot the document server in order into an `object[]`; every pre/post membership and ownership comparison uses `ReferenceEquals`.

- [ ] **Step 5: Implement the transaction and conservative rollback**

Use one static `int` guard acquired with `Interlocked.CompareExchange(ref activeTransaction, 1, 0)` and released in `finally`. At each mutating boundary call `RequireSameCanvas(capturedCanvas)` before and after. For `/new`, call the out-success overload, verify `IndexOf >= 0` and `ReferenceEquals(server[index], candidate)`, then activate and reverify registration. For `/open`, snapshot the path match before the call, use `AddDocument(path, true)`, and reconcile the return with post-call additions and the active document.

Rollback follows this executable order:

```csharp
if (ReferenceEquals(host.GetActiveCanvas(), capturedCanvas))
    host.SetCanvasDocument(capturedCanvas, previousDocument);

var previousRestored = ReferenceEquals(host.GetActiveCanvas(), capturedCanvas)
    && ReferenceEquals(host.GetCanvasDocument(capturedCanvas), previousDocument);
var candidateStillActive = host.IsActiveOnAnySupportedCanvas(candidate, capturedCanvas);
if (previousRestored && registeredByThisCall && candidateStillActive == false)
    host.RemoveDocument(candidate);
else if (previousRestored && createdDocument && !everRegistered && candidateStillActive == false)
    host.DisposeDocument(candidate);
```

The assignment occurs even when `previousDocument` is `null`. Reinspect the active canvas and its document immediately after that mutation. If restoration, canvas sameness, canvas enumeration, inactivity, or ownership cannot be proven, skip removal/disposal and set `RollbackIncomplete` with the observed final state.

- [ ] **Step 6: Run lifecycle tests and the full managed suite**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter FullyQualifiedName~GhDocumentLifecycleTests --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: both pass; production route source still contains no `GhDocumentLifecycle` construction.

- [ ] **Step 7: Commit the unused helper only**

```powershell
git add -- src/Rook/InternalBridge/GhDocumentLifecycle.cs src/Rook.Tests/InternalBridge/GhDocumentLifecycleTests.cs
git commit -m "feat(grasshopper): add transactional document lifecycle helper"
```

Do not deploy this commit.

---

### Task 2: Closed scheduling policy, invocation, and host-aware suspension, unused by production

**Files:**
- Create: `src/Rook/Handlers/GhPostMutationSchedulePolicy.cs`
- Create: `src/Rook/Handlers/GhScheduleInvoker.cs`
- Create: `src/Rook/Handlers/GhMutationSolveSuspension.cs`
- Create: `src/Rook.Tests/Handlers/GhPostMutationSchedulePolicyTests.cs`
- Create: `src/Rook.Tests/Handlers/GhScheduleInvokerTests.cs`
- Create: `src/Rook.Tests/Handlers/GhMutationSolveSuspensionTests.cs`

**Interfaces:**
- Produces `GhPostMutationSchedulePolicy.Decide(GhScheduleInputs)` returning `GhScheduleDecision`.
- Produces `GhScheduleInvoker.Invoke(object document, GhScheduleDecision decision, int delayMs)` returning `GhScheduleResult`.
- Produces `GhMutationSolveSuspension.Begin(object? document, bool runningAsRhinoInside)` and one-shot `Restore()` returning `GhSolverRestoreResult`.
- Existing `GrasshopperHandler.SolvePolicy.cs` and all routes remain unchanged until Task 3.

The closed policy vocabulary is exact:

```csharp
internal enum GhScheduleClassification
{
    SolveNotRequested,
    RirDocumentUnregistered,
    RirRegistrationUnknown,
    GlobalSolverUnavailable,
    RirMediatedScheduleRequested,
    AsyncScheduleRequested,
    RirInstanceSolverStateUnknown,
    GlobalSolverStateUnknown,
    DocumentSolverDisabled,
    SolverStateUnknown,
}

internal enum GhScheduleWarning
{
    CompletionUnverified,
    RegistrationUnknown,
    GlobalSolverStateUnknown,
    InstanceSolverStateUnknown,
    ScheduleInvocationUnknown,
    StandaloneRestoreFailed,
}

internal readonly struct GhScheduleDecision
{
    public GhScheduleClassification ScheduleClassification { get; init; }
    public bool AttemptSchedule { get; init; }
    public bool VerificationDeferred { get; init; }
    public bool SolverLocked { get; init; }
    public bool SolverStateKnown { get; init; }
    public GhScheduleWarning[] Warnings { get; init; }
}

internal readonly struct GhSolverRestoreResult
{
    public bool Attempted { get; init; }
    public bool Succeeded { get; init; }
    public GhScheduleFailureCode? FailureCode { get; init; }
    public bool? ObservedDocumentEnabled { get; init; }
}
```

`GhScheduleWire` maps classifications exactly: `SolveNotRequested` → `solve_not_requested`, `RirDocumentUnregistered` → `rir_document_unregistered`, `RirRegistrationUnknown` → `rir_registration_unknown`, `GlobalSolverUnavailable` → `global_solver_unavailable`, `RirMediatedScheduleRequested` → `rir_mediated_schedule_requested`, `AsyncScheduleRequested` → `async_schedule_requested`, `RirInstanceSolverStateUnknown` → `rir_instance_solver_state_unknown`, `GlobalSolverStateUnknown` → `global_solver_state_unknown`, `DocumentSolverDisabled` → `document_solver_disabled`, and `SolverStateUnknown` → `solver_state_unknown`.

Acceptance mappings are `not_attempted`, `unavailable`, `accepted`, and `unknown`. Failure mappings are `standalone_solver_restore_failed`, `schedule_precondition_rejected`, `schedule_api_unavailable`, and `schedule_acceptance_unknown`; nullable absence is emitted as JSON null, never `none`.

- [ ] **Step 1: Write the failing exhaustive policy theory**

Create one data row for every policy-matrix row from the spec. The input remains decomposed:

```csharp
internal readonly struct GhScheduleInputs
{
    public bool SolveRequested { get; init; }
    public bool RunningAsRhinoInside { get; init; }
    public bool RegistrationKnown { get; init; }
    public bool DocumentRegistered { get; init; }
    public bool? GlobalEnableSolutions { get; init; }
    public bool? DocumentEnabled { get; init; }
}
```

Assert the exact `GhScheduleClassification`, whether an invocation is permitted, verification deferral, and compatibility `SolverLocked` projection. Include RiR's temporary global false followed by true as two decisions and prove neither mutates either input document flag.

- [ ] **Step 2: Write invocation and wire-mapping failures first**

Fakes cover:

- no `ScheduleSolution(int)` method → `Unavailable`/`ScheduleApiUnavailable`;
- `delayMs == 0` → `NotAttempted`/`SchedulePreconditionRejected`;
- returning method → one call, positive delay, `Accepted`, `SolveScheduled == true`, and completion verification deferred;
- a method that increments `CallCount`, records its delay, mutates `ScheduleArmed = true`, then throws → `Unknown`/`ScheduleAcceptanceUnknown`, `SolveScheduled == false`, one call, no retry;
- reflection ambiguity before invocation → `NotAttempted` only when target entry is conclusively impossible;
- all enum values have exhaustive exact wire mappings and undefined values throw.

Pin the public mapping:

```csharp
Assert.Equal("rir_mediated_schedule_requested",
    GhScheduleWire.ToWire(GhScheduleClassification.RirMediatedScheduleRequested));
Assert.Equal("accepted",
    GhScheduleWire.ToWire(GhScheduleAcceptance.Accepted));
Assert.Equal("schedule_acceptance_unknown",
    GhScheduleWire.ToWire(GhScheduleFailureCode.ScheduleAcceptanceUnknown));
```

- [ ] **Step 3: Write suspension/restoration failures first**

Assert RiR begin is a no-op and performs zero property sets. In standalone Rhino, enabled documents are disabled once during mutation, already-disabled or unknown documents are untouched, and `Restore()` attempts at most once. A setter that throws during restoration returns `Succeeded == false`, `Attempted == true`, `FailureCode == StandaloneSolverRestoreFailed`, and the observed post-failure state without retry.

- [ ] **Step 4: Verify all new tests fail for missing implementations**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~GhPostMutationSchedulePolicyTests|FullyQualifiedName~GhScheduleInvokerTests|FullyQualifiedName~GhMutationSolveSuspensionTests" --verbosity minimal
```

- [ ] **Step 5: Implement the closed result model and pure policy**

Use these exact authoritative members:

```csharp
internal enum GhScheduleAcceptance { NotAttempted, Unavailable, Accepted, Unknown }

internal enum GhScheduleFailureCode
{
    StandaloneSolverRestoreFailed,
    SchedulePreconditionRejected,
    ScheduleApiUnavailable,
    ScheduleAcceptanceUnknown,
}

internal readonly struct GhScheduleResult
{
    public GhScheduleClassification ScheduleClassification { get; init; }
    public GhScheduleAcceptance ScheduleAcceptance { get; init; }
    public GhScheduleFailureCode? ScheduleFailureCode { get; init; }
    public bool VerificationDeferred { get; init; }
    public bool SolverLocked { get; init; }
    public bool SolverStateKnown { get; init; }
    public string? ExceptionType { get; init; }
    public GhScheduleWarning[] Warnings { get; init; }
    public bool SolveScheduled => ScheduleAcceptance == GhScheduleAcceptance.Accepted;
}
```

`ExceptionType` contains only the bounded type name for unknown invocation acceptance; retain no exception object or message. `GhScheduleWire` maps every classification, acceptance, failure, and warning enum exhaustively. Add neutral compatibility projection for RiR repair fields only at the Task 3 route boundary, not as behavior inputs.

- [ ] **Step 6: Implement exactly-once invocation and one-shot restoration**

Resolve the public instance `ScheduleSolution(int)` method before invocation. Clamp nowhere: a nonpositive input is a conclusive pre-invocation rejection. Once `MethodInfo.Invoke` begins, any `TargetInvocationException` or ambiguous reflection exception is `Unknown`; never retry. The invoker must not reference `Task`, `Task.Run`, `RhinoApp.InvokeOnUiThread`, `NewSolution`, or delay zero.

`GhMutationSolveSuspension.Begin` reads `GhSolverState.Inspect`. When `runningAsRhinoInside` is true it returns an inactive no-op. Standalone may write instance `Enabled = false` only when the original combined and instance flags are both true. `Restore()` sets its attempted flag before reflection so a throwing setter cannot be invoked twice.

- [ ] **Step 7: Run focused and full tests, then commit unused policy helpers**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~GhPostMutationSchedulePolicyTests|FullyQualifiedName~GhScheduleInvokerTests|FullyQualifiedName~GhMutationSolveSuspensionTests" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
git add -- src/Rook/Handlers/GhPostMutationSchedulePolicy.cs src/Rook/Handlers/GhScheduleInvoker.cs src/Rook/Handlers/GhMutationSolveSuspension.cs src/Rook.Tests/Handlers/GhPostMutationSchedulePolicyTests.cs src/Rook.Tests/Handlers/GhScheduleInvokerTests.cs src/Rook.Tests/Handlers/GhMutationSolveSuspensionTests.cs
git commit -m "feat(grasshopper): add host-aware schedule policy helpers"
```

Do not deploy this commit.

---

### Task 3: Atomic production lifecycle and solver-ownership cutover

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.Readiness.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs`
- Delete: `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs`
- Delete: `src/Rook/Handlers/GhSolvePolicy.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`
- Modify: `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`
- Modify: `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`
- Modify: `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`
- Modify: `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- Delete: `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs`
- Modify: `docs/superpowers/specs/2026-06-13-rir-gh-solver-enabled-race-design.md`

**Interfaces:**
- Consumes Tasks 1-2 final helpers without adding compatibility lifecycle or scheduling branches.
- Replaces all `GhSolveOutcome` production use with `GhScheduleResult`.
- Preserves `IRookBimRuntime`, native ABI, route names, and solve-receipt schemas.
- Produces exact public keys `schedule_classification`, `schedule_acceptance`, `schedule_failure_code`, and retained `solve_scheduled` on every response that carries solve evidence.

- [ ] **Step 1: Replace obsolete source tests with failing final-contract tests**

Rewrite lifecycle source tests to require:

- `GetGrasshopper(bool requireDocument = true)` has no creation branch;
- `GrasshopperCore.ResolveContext()` has no creation parameter or `Activator.CreateInstance` branch;
- `HandleOpenDocument` parses and validates the request/file before its `RhinoApp.InvokeOnUiThread` path;
- `NewDocument` calls `GhDocumentLifecycle.CreateNew`, never `AddNewDocument`, and performs readiness/ID/refresh/count work only after `Committed`;
- `OpenDocument` calls `GhDocumentLifecycle.Open`, contains no `GH_DocumentIO`, and does not create a temporary document;
- the bridge continues to invoke both routes through `ExecuteApiResponseCallback`, which is the Rhino UI boundary;
- route failure projects actual final active/registered/rollback state;
- post-commit auxiliary catches append closed warnings and preserve `Success = true`.

Rewrite solve source tests to require the normative `/gh/edit` order and forbid the obsolete path:

```csharp
AssertOrder(method,
    "ExpirePostMutationDirtyObjects(dirtyObjects)",
    "TakeStructuralSnapshot()",
    "solveSuspension.Restore()",
    "RequestPostMutationSolve(",
    "return snapshotResult");
Assert.DoesNotContain("RequestDeferredPostMutationSolve", source);
Assert.DoesNotContain("Task.Run", solvePolicySource);
Assert.DoesNotContain("5000", method);
Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", solvePolicySource);
```

Require exact snake-case wire keys and reject `scheduleClassification`, `scheduleAcceptance`, `scheduleFailureCode`, and `solveScheduled` literals in post-mutation response construction.

Task 3 also introduces this preflight result in `GrasshopperHandler.cs`; no raw exception is retained:

```csharp
internal readonly struct GhOpenDocumentPreflightResult
{
    public bool Success { get; init; }
    public string? Path { get; init; }
    public string? ErrorCode { get; init; }
}
```

- [ ] **Step 2: Run the replacement tests red before production edits**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~GhEditSolvePathSourceTests|FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolvePolicyTests" --verbosity minimal
```

Expected: failures name the old implicit creation, orphan routes, delayed scheduler, repair coordinator, or missing final wire fields.

- [ ] **Step 3: Make context resolution observational and cut over new/open routes**

Change handler lookup to `GetGrasshopper(bool requireDocument = true)`. `/new` and `/open` pass `false`; all edit/query callers keep the default or explicitly require a document. Remove both implicit creation branches.

Add an internal pure `GrasshopperHandler.PreflightOpenDocument(string? body)` that returns a closed success/path/error result without touching Grasshopper. `NativeGhBridgeRegistrar.HandleOpenDocument` reads the UTF-8 request and calls that preflight before `ExecuteApiResponseCallback` reaches `RhinoApp.InvokeOnUiThread`; on rejection it writes the bounded response immediately. `OpenDocument` repeats the same preflight defensively for direct managed callers, then enters `GhDocumentLifecycle` on the already-established UI callback. Do not add a second UI dispatch.

Construct one lifecycle instance from the loaded Grasshopper assembly and captured canvas context. Project committed result data and bounded warnings. Run `EnsureReadinessSession`, `_idRegistry.Clear`, `RefreshCanvas`, object counting, and telemetry projection in separate post-commit `try/catch` blocks so a failure appends its closed warning and cannot reverse route success.

For `/new`, preserve the existing empty-document promise and never call the template-loading scripting method. The only production sequence is `CreateNew`'s construct → out-success registration → reference verification → canvas activation → commit.

- [ ] **Step 4: Replace scheduling integration everywhere without a second scheduler**

Rewrite `GrasshopperHandler.SolvePolicy.cs` as a thin integration layer:

```csharp
internal GhScheduleResult RequestPostMutationSolve(
    object document,
    IReadOnlyList<object> dirtyObjects,
    bool requestSolve,
    int delayMs = 1,
    bool expireDirtyObjects = true,
    GhSolverState.Result? solverStateOverride = null,
    GhSolverRestoreResult? standaloneRestore = null)
```

It may expire dirty objects first when requested, then reads registration through `GhDocumentLifecycle.InspectRegistration`, reads RiR host state through the handler's injected/default `Func<bool>`, passes the separate global/instance flags into `GhPostMutationSchedulePolicy`, applies a failed standalone restoration as `NotAttempted`/`StandaloneSolverRestoreFailed`, and otherwise calls `GhScheduleInvoker.Invoke` once. Delete `RequestDeferredPostMutationSolve`, `TryScheduleDeferred`, the five-second delay, the UI redispatch helper, and every `Task` reference from the solve-policy file.

- [ ] **Step 5: Enforce RiR no-op suspension and `/gh/edit` exit restoration**

Replace the nested `GhDocumentSolveSuspension` with Task 2's `GhMutationSolveSuspension`. Replace the constructor's `GhSolveReadinessCoordinator?` argument with `Func<bool>? runningAsRhinoInside`; the public constructor supplies `() => Rhino.Runtime.HostUtils.RunningAsRhinoInside`, and tests inject both host states. For `/gh/edit`:

1. Begin suspension; RiR performs no write.
2. Perform mutations.
3. Call `ExpireSolution(false)` on dirty objects.
4. Capture the structural snapshot.
5. Call `Restore()` exactly once.
6. If restoration failed, produce a schedule result with `schedule_failure_code = standalone_solver_restore_failed` and do not invoke.
7. Otherwise request exactly one positive-delay schedule before building/returning the response.
8. In the exception path, call `Restore()` only if it has not already been attempted and include a bounded restore outcome when it failed.

Do not use a `finally` that retries a failed restore. The suspension object itself makes restoration one-shot.

- [ ] **Step 6: Remove every RiR `Enabled` owner and neutralize compatibility telemetry**

Remove `_solveReadinessCoordinator` from fields/constructors/status/scheduling and delete its production/test files. `GetStatus` retains all four existing compatibility fields as:

```text
rir_repair_attempted = false
rir_repair_held = false
rir_repair_reason = null
rir_repair_source = null
```

Post-mutation responses retain only their three existing repair fields (`rir_repair_attempted`, `rir_repair_held`, and `rir_repair_reason`) with the same neutral values; do not add a new repair-source field to those payloads.

Search executable `src/Rook` code and prove there is no remaining reflection setter or assignment for `GH_Document.Enabled` on an RiR branch and no write to `GH_Document.EnableSolutions`. Standalone writes are allowed only inside `GhMutationSolveSuspension` behind `runningAsRhinoInside == false`.

- [ ] **Step 7: Project the authoritative schedule contract and update readiness receipts**

In `SetScript`, both `/gh/edit` response shapes, and any other response already carrying solve evidence, emit:

```csharp
schedule_classification = GhScheduleWire.ToWire(result.ScheduleClassification),
schedule_acceptance = GhScheduleWire.ToWire(result.ScheduleAcceptance),
schedule_failure_code = result.ScheduleFailureCode.HasValue
    ? GhScheduleWire.ToWire(result.ScheduleFailureCode.Value)
    : null,
    solve_scheduled = result.SolveScheduled,
```

Project `solve_warnings` with `result.Warnings.Select(GhScheduleWire.ToWire).ToArray()`. Retain existing `solver_locked`, `solver_state_known`, and `verification_deferred` only as compatibility evidence. Update `FinalizeSetValueReceipt` to mark schedule accepted only for `Accepted`; use the existing solver-locked receipt only for `GlobalSolverUnavailable` and `DocumentSolverDisabled`, and otherwise mark lifecycle unavailable with the bounded schedule failure/classification code. Do not infer non-acceptance from `solve_scheduled == false`.

- [ ] **Step 8: Replace obsolete tests and supersede doctrine in the same change**

Delete tests requiring repair writes, delayed post-response scheduling, or registration irrelevance. Preserve and strengthen tests for no synchronous expiration, no `NewSolution`, solve receipt lifecycle, status DTO compatibility fields, and native callback routing. Add a source scan across `src/Rook/Handlers/GrasshopperHandler*.cs` and `src/Rook/InternalBridge/*.cs` forbidding:

```text
RequestDeferredPostMutationSolve
Task.Run
postEditScheduleDispatchDelayMs
GhSolveReadinessCoordinator
MarkRookManagedDocument
PrepareForPostMutationSolve
EnableSolutions =
```

Add a prominent notice at the top of `2026-06-13-rir-gh-solver-enabled-race-design.md`: superseded by the July 26 lifecycle design; its rejection of `DocumentServer.AddDocument` and Rook-owned repair policy are historical and non-normative.

- [ ] **Step 9: Run focused tests, full tests, and source scans**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --filter "FullyQualifiedName~GhDocumentLifecycle|FullyQualifiedName~GhPostMutation|FullyQualifiedName~GhSchedule|FullyQualifiedName~GhMutationSolveSuspension|FullyQualifiedName~GhEditSolvePath|FullyQualifiedName~GrasshopperDocumentLifecycle|FullyQualifiedName~GrasshopperHandlerReadiness|FullyQualifiedName~GhSolverState|FullyQualifiedName~NoSyncExpire" --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
rg -n "RequestDeferredPostMutationSolve|postEditScheduleDispatchDelayMs|GhSolveReadinessCoordinator|MarkRookManagedDocument|PrepareForPostMutationSolve" src/Rook/Handlers src/Rook/InternalBridge
rg -n "scheduleClassification|scheduleAcceptance|scheduleFailureCode|solveScheduled" src/Rook/Handlers/GrasshopperHandler.cs
git diff --check
```

Expected: tests pass; both `rg` commands return no executable/response matches. The obsolete-name scan intentionally excludes `src/Rook.Tests`, whose replacement source-contract tests contain the forbidden literals as assertions. Historical spec text is allowed only in its superseded notice; `git diff --check` is clean.

- [ ] **Step 10: Commit the indivisible behavior change**

```powershell
git add -- src/Rook/Handlers/GrasshopperHandler.cs src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs src/Rook/Handlers/GrasshopperHandler.Readiness.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook/InternalBridge/GrasshopperCore.cs src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs src/Rook/Handlers/GhSolvePolicy.cs src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs src/Rook.Tests/Handlers/GhSolvePolicyTests.cs src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs docs/superpowers/specs/2026-06-13-rir-gh-solver-enabled-race-design.md
git commit -m "fix(grasshopper): own document lifecycle without fighting RiR"
```

Verify the commit contains all cutover/removal/doctrine files. Do not split or deploy only part of it.

---

### Task 4: Full build, committed deployment, and live RiR/standalone acceptance

**Files:**
- Create after the live run: `docs/superpowers/reports/2026-07-26-rir-grasshopper-document-lifecycle-acceptance.md`

**Interfaces:**
- Consumes the complete Task 1-3 commit chain.
- Produces one durable redacted acceptance report with exact commit/version/process evidence and all eleven live-gate outcomes.
- This task is operator-assisted and must run inline, not in a background subagent.

- [ ] **Step 1: Record and verify the exact implementation commit before deployment**

```powershell
$implementationCommit = (git rev-parse HEAD).Trim()
if (git status --porcelain) { throw 'Commit all implementation changes before deploy' }
git diff --check HEAD^
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet build src\Rook\Rook.csproj --configuration Release --framework net48 --no-restore
```

Expected: clean tree, clean diff, full test pass, and Release net48 build pass.

- [ ] **Step 2: Stop only the known local Rook/Rhino/Revit processes and deploy**

Ask the operator to save work and close Revit, Rhino, Grasshopper, and the Rook MCP process. Confirm exact process names/PIDs before terminating any remainder. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -Configuration Release
```

Record the script's installed `InstallRoot`, `DataRoot`, `PluginDir`, `ChirpRoot`, managed runtime paths, native build status, and RookBIM build status. A partial payload deployment is not acceptance for this atomic change.

- [ ] **Step 3: Start standalone Rhino and run the standalone matrix**

With a fresh Rhino 8 and Grasshopper process, capture exact Rhino/Grasshopper/Rook versions and verify:

1. Empty canvas `/gh/document/new` creates exactly one empty, registered, active document.
2. With a non-empty configured template, `/new` remains empty.
3. `/gh/document/open` registers and activates a fixture.
4. Reopening the same path reuses the exact reference and server count does not grow.
5. A safe controlled activation failure restores the prior canvas before removing only the new candidate.
6. Slider-to-panel edit produces later volatile output.
7. Standalone suspension restores before one scheduling invocation.
8. The response contains exact snake-case scheduling keys and neutral repair fields.

- [ ] **Step 4: Start Revit 2024.3 with Rhino.Inside and run the RiR matrix**

Open Rhino.Inside and Grasshopper, then verify:

1. New/open registration and duplicate behavior match standalone.
2. A registered document whose instance flag is temporarily false receives one positive-delay schedule request with no Rook `Enabled` write.
3. The response returns after invocation while `SolutionStart` occurs later; no synchronous solve begins in the callback.
4. RiR's temporary global disable reports `global_solver_unavailable`, performs no repair, and later host restoration remains functional.
5. Slider-to-panel yields actual volatile output, not only solution events.
6. Active Document, Document Identity, Document Worksharing, Active View, View Identity, Query Rooms, and Query Views all compute with zero Grasshopper errors/warnings.
7. No response or log claims actual RiR deferral without a later proving solution/readiness event.

- [ ] **Step 5: Prove the obsolete scheduler and writer are absent in the deployed behavior**

Capture one `/gh/edit` timeline containing callback entry, dirty expiration, structural snapshot, standalone no-op/restore state, scheduling invocation, response return, and later `SolutionStart`. Confirm exactly one invocation before response, no five-second handoff, and no second Rook scheduling attempt. Capture document `Enabled` transitions and attribute each observed write; no write may originate from Rook inside RiR.

- [ ] **Step 6: Write the durable redacted acceptance report**

The report contains:

- implementation commit and worktree branch;
- exact Revit, RevitAPI, Rhino, Grasshopper, Rhino.Inside.Revit, Rook, and RookBIM versions;
- process IDs and UTC run window;
- commands/routes used without model paths or user data;
- server counts and reference-equality outcomes using aliases such as `ghdoc-001`;
- all standalone/RiR gate outcomes;
- scheduling classification/acceptance/failure values;
- explicit proof that completion was asynchronous;
- warnings or incomplete rollback evidence;
- deployment paths and rollback result if invoked.

Do not include GH file paths, Revit model paths, document/component names, arbitrary exception messages, or raw object identifiers.

- [ ] **Step 7: Commit the report and apply the release decision**

```powershell
git add -- docs/superpowers/reports/2026-07-26-rir-grasshopper-document-lifecycle-acceptance.md
git commit -m "docs: record Grasshopper RiR lifecycle acceptance"
```

Approve release only when every live gate passes or is explicitly marked unavailable for a reason accepted by the reviewer. On failure, roll back the entire Task 1-3 implementation chain as one deployed unit; never mix old registration with new solver policy or vice versa. State that RiR Grasshopper automation remains unsupported until the corrected atomic build returns.

---

## Plan Self-Review Checklist

- [ ] The worktree baseline verifies the final approved spec commit and only the two plan files.
- [ ] Tasks 1-2 are unused and non-deployable; Task 3 is the one complete production cutover.
- [ ] `/new` uses the out-success registration overload and activates only after verified registration.
- [ ] `/open` uses `AddDocument(path, true)` and reconciles null/partial/duplicate behavior by reference.
- [ ] Canvas identity is checked before and after every mutation; one static guard blocks callback reentry across instances.
- [ ] Commit is exactly registered plus active; post-commit auxiliary failures cannot create false route failure.
- [ ] Rollback restores before removal and cannot dispose an active, preexisting, duplicate, or uncertain document.
- [ ] Rollback treats a captured `null` canvas document as real state, assigns/verifies `null`, and removes a new inactive candidate only after restoration.
- [ ] Both implicit creation branches, manual `GH_DocumentIO` open, coordinator, delayed scheduler, and obsolete tests are removed.
- [ ] RiR has zero Rook `Enabled` writers; standalone restoration is one-shot, precedes scheduling, and reports failure.
- [ ] Policy permission, invocation attempt, and acceptance are separate closed states.
- [ ] Target-entry exceptions are unknown, deferred, and never retried.
- [ ] `solve_scheduled` is only the accepted compatibility projection.
- [ ] Exact snake-case wire keys are tested and camelCase duplicates are forbidden.
- [ ] No synchronous solution, delay zero, `Task.Run`, second UI dispatch, or second scheduler remains.
- [ ] June 13 doctrine is explicitly superseded in the atomic behavior commit.
- [ ] Full tests/build pass before deploy; live output, not event counts, closes acceptance.
- [ ] The temporary CreationGUID probe was completed, rolled back, and reviewed before this Grasshopper deployment began.
