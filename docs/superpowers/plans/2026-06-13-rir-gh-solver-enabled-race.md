# RIR Grasshopper Solver Enabled Race Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix issue #247 so Rook-driven Grasshopper edits inside Rhino.Inside.Revit can async-solve after RIR disables the active `GH_Document` instance, without weakening the PR #208 no-sync-solve invariant or re-enabling a user-locked solver.

**Architecture:** Add a managed, RIR-gated solve-readiness coordinator that marks Rook-managed GH documents, repairs only the instance `document.Enabled` flag at solve-schedule time when static `GH_Document.EnableSolutions` remains true, and feeds repair telemetry into the existing safe-solve policy. Route `gh_edit` post-mutation scheduling through that single shared scheduler; no `NewSolution`, no `ExpireSolution(true)`, no writes to the static solver flag.

**Tech Stack:** C# managed companion (`src/Rook`, net48), RhinoCommon/Grasshopper reflection, xUnit tests in `src/Rook.Tests`, PowerShell live verification through the Rook MCP/HTTP surface, Rhino.Inside.Revit and standalone Rhino for final smoke.

---

## Source Material

- Spec: `docs/superpowers/specs/2026-06-13-rir-gh-solver-enabled-race-design.md`
- Safe-solve policy background: `docs/superpowers/specs/2026-06-02-gh-locked-solver-crash-design.md`
- Issues: `gh issue view 247 -R bringfire/Rook`, `gh issue view 246 -R bringfire/Rook`
- Key invariant: HTTP-driven GH mutations must never force a synchronous recompute on a disabled or locked solver.
- Implementation note from review: the repair writes only instance `document.Enabled=true`; it never writes `GH_Document.EnableSolutions`.

## Scope Check

This plan implements #247 only. #246 remains deferred. The only #246-facing work here is to return structured solve outcome metadata without creating a blocking "wait until solved" contract.

The first execution task is a live gate. If the ordinary Grasshopper user solver lock can set only `document.Enabled=false` while static `GH_Document.EnableSolutions` remains true, stop before code changes and revise the design with a stronger discriminator.

## File Structure

- Create `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs`
  - Owns RIR-gated document marking, bounded transition repair, schedule-time instance repair, and latest repair telemetry.
  - Injects host detection and active-document lookup for tests.
  - Writes only the instance `Enabled` property on a `GH_Document` object.

- Modify `src/Rook/InternalBridge/GhSolverState.cs`
  - Preserve existing `Enabled` behavior.
  - Add separate nullable diagnostics for static `GH_Document.EnableSolutions` and instance `document.Enabled`.

- Modify `src/Rook/InternalBridge/GrasshopperCore.cs`
  - Extend `GrasshopperStatusDto` with solver-flag diagnostics and latest RIR repair telemetry fields.
  - Keep status reads anchored to `Grasshopper.Instances.ActiveCanvas.Document`.

- Modify `src/Rook/Handlers/GhSolvePolicy.cs`
  - Extend `GhSolveOutcome` with repair metadata.
  - Keep the policy pure and keep locked/deferred decisions based on the post-repair `GhSolverState`.

- Modify `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`
  - Insert schedule-time repair before `GhSolvePolicy.Decide`.
  - Continue dirtying objects once and calling `ScheduleSolution(delay >= 1)` once through the existing shared path.

- Modify `src/Rook/Handlers/GrasshopperHandler.cs`
  - Add one coordinator field.
  - Mark Rook-created/opened documents after canvas replacement.
  - Route `gh_edit` post-mutation solve through `RequestPostMutationSolve`.
  - Add solve outcome fields to the `gh_edit` response summary.

- Modify `src/Rook.Tests/InternalBridge/GhSolverStateTests.cs`
  - Cover static-vs-instance diagnostics.

- Create `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs`
  - Cover RIR gating, static user-lock guard, instance-only repair, one-shot transition repair, and telemetry.

- Modify `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`
  - Cover new DTO fields.

- Modify `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`
  - Cover repair metadata pass-through and unchanged locked-solver decisions.

- Modify `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`
  - Cover schedule-time repair, standalone no-op, static user-lock no-repair, and single scheduling.

- Create `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`
  - Source-guard that `ApplyEdit` routes through `RequestPostMutationSolve` and does not use the direct `ScheduleDocumentSolution(gh.Document!)` path.

- Modify `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`
  - Extend the source guard to reject `NewSolution`, `ExpireSolution(true)`, and assignments to `GH_Document.EnableSolutions` in the new coordinator and GH mutation scheduling files.

---

### Task 0: User Solver-Lock Classification Gate

**Files:**
- Read: `docs/superpowers/specs/2026-06-13-rir-gh-solver-enabled-race-design.md`
- No source edits in this task.

- [ ] **Step 1: Confirm RIR/GH is the active verification host**

Run this from PowerShell, replacing `$Port` if the live Rook port differs:

```powershell
$Port = 64702
$Base = "http://127.0.0.1:$Port"
(Invoke-RestMethod "$Base/capabilities").rhinoInside
```

Expected: `True`.

- [ ] **Step 2: Create a throwaway GH document**

Use the Rook MCP `gh_document_new` tool, then run:

```powershell
$status = Invoke-RestMethod "$Base/gh/status"
$status.solverEnabled
$status.solverStateKnown
```

Expected: the status call succeeds. `solverEnabled` may be true or false depending on RIR focus state; this step only establishes a current document.

- [ ] **Step 3: Lock the solver through the Grasshopper user interface**

In the open Grasshopper window, use the normal user solver-lock path from the GH UI. Do not use a script for this step.

- [ ] **Step 4: Inspect the actual flags produced by the user lock**

Run a Rook script execution that reads both flags from the active GH document. Use the existing repo/live script-execution tool or route that was used during the spike; the script body is:

```csharp
var canvas = Grasshopper.Instances.ActiveCanvas;
var doc = canvas?.Document;
return new
{
    static_enable_solutions = Grasshopper.Kernel.GH_Document.EnableSolutions,
    document_enabled = doc?.Enabled,
    has_document = doc != null
};
```

Expected: `has_document=true`, `static_enable_solutions=false`. `document_enabled` may be true or false.

- [ ] **Step 5: Stop if the discriminator fails**

If Step 4 reports `static_enable_solutions=true` and `document_enabled=false`, stop the implementation. Record the observation in the PR notes and revise the design before changing source files.

- [ ] **Step 6: Unlock the solver and reset the live session**

Unlock the solver through the Grasshopper UI, then run:

```powershell
$status = Invoke-RestMethod "$Base/gh/status"
$status.solverEnabled
```

Expected: the status call succeeds and the static solver flag is no longer locked. If RIR focus leaves `solverEnabled=false`, focus Grasshopper once and re-check before moving to code.

---

### Task 1: Extend Solver-State Diagnostics

**Files:**
- Modify: `src/Rook/InternalBridge/GhSolverState.cs`
- Modify: `src/Rook.Tests/InternalBridge/GhSolverStateTests.cs`

- [ ] **Step 1: Write failing tests for separate static and instance flags**

Add this fake document type and tests to `src/Rook.Tests/InternalBridge/GhSolverStateTests.cs`:

```csharp
private sealed class FakeFlagDocument
{
    public static bool EnableSolutions { get; set; } = true;
    public bool Enabled { get; set; } = true;
    public string SolutionState { get; set; } = "PreProcess";
}

[Fact]
public void Inspect_ReportsStaticAndInstanceFlagsSeparately()
{
    FakeFlagDocument.EnableSolutions = true;
    var document = new FakeFlagDocument { Enabled = false };

    var result = GhSolverState.Inspect(document);

    Assert.True(result.Known);
    Assert.True(result.GlobalEnableSolutions);
    Assert.False(result.DocumentEnabled);
    Assert.False(result.Enabled);
}

[Fact]
public void Inspect_StaticSolverLockDisablesSolverWithoutChangingInstanceFlag()
{
    FakeFlagDocument.EnableSolutions = false;
    var document = new FakeFlagDocument { Enabled = true };

    var result = GhSolverState.Inspect(document);

    Assert.True(result.Known);
    Assert.False(result.GlobalEnableSolutions);
    Assert.True(result.DocumentEnabled);
    Assert.False(result.Enabled);

    FakeFlagDocument.EnableSolutions = true;
}
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolverStateTests" -v minimal
```

Expected: fail because `GhSolverState.Result` does not expose `GlobalEnableSolutions` or `DocumentEnabled`.

- [ ] **Step 3: Add nullable flag diagnostics to `GhSolverState.Result`**

Change `src/Rook/InternalBridge/GhSolverState.cs` so `Result` has these properties and constructor parameters:

```csharp
internal readonly struct Result
{
    public Result(
        bool? enabled,
        bool known,
        string? solutionState,
        bool? globalEnableSolutions,
        bool? documentEnabled)
    {
        Enabled = enabled;
        Known = known;
        SolutionState = solutionState;
        GlobalEnableSolutions = globalEnableSolutions;
        DocumentEnabled = documentEnabled;
    }

    public bool? Enabled { get; }
    public bool Known { get; }
    public string? SolutionState { get; }
    public bool? GlobalEnableSolutions { get; }
    public bool? DocumentEnabled { get; }
}
```

Update `Inspect(object? document)` so it computes:

```csharp
bool? globalEnableSolutions = ReadStaticBoolean(document.GetType(), "EnableSolutions");
bool? documentEnabled = ReadInstanceBoolean(document, "Enabled");
bool? enabled = CombineSolverFlags(globalEnableSolutions, documentEnabled);

return new Result(
    enabled,
    enabled.HasValue,
    ReadSolutionState(document),
    globalEnableSolutions,
    documentEnabled);
```

Add private helpers in the same file:

```csharp
private static bool? CombineSolverFlags(bool? globalEnableSolutions, bool? documentEnabled)
{
    if (globalEnableSolutions.HasValue && documentEnabled.HasValue)
    {
        return globalEnableSolutions.Value && documentEnabled.Value;
    }

    if (globalEnableSolutions == false || documentEnabled == false)
    {
        return false;
    }

    return null;
}
```

Keep the existing reflection error handling. For a null document, return `new Result(null, false, null, null, null)`.

- [ ] **Step 4: Run solver-state tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolverStateTests" -v minimal
```

Expected: pass.

- [ ] **Step 5: Commit diagnostics**

Run:

```powershell
git add src\Rook\InternalBridge\GhSolverState.cs src\Rook.Tests\InternalBridge\GhSolverStateTests.cs
git commit -m "test: expose grasshopper solver flag diagnostics"
```

---

### Task 2: Add RIR Solve-Readiness Coordinator

**Files:**
- Create: `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs`
- Create: `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs`

- [ ] **Step 1: Write failing coordinator tests**

Create `src/Rook.Tests/InternalBridge/GhSolveReadinessCoordinatorTests.cs` with this test scaffold:

```csharp
using System;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge;

public sealed class GhSolveReadinessCoordinatorTests
{
    private sealed class FakeGhDocument
    {
        public static bool EnableSolutions { get; set; } = true;
        public bool Enabled { get; set; } = true;
        public event EventHandler? EnabledChanged;

        public void DisableThroughHost()
        {
            Enabled = false;
            EnabledChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    [Fact]
    public void PrepareForPostMutationSolve_Standalone_DoesNotRepair()
    {
        FakeGhDocument.EnableSolutions = true;
        var document = new FakeGhDocument { Enabled = false };
        var coordinator = new GhSolveReadinessCoordinator(
            isRhinoInside: () => false,
            getActiveDocument: () => document,
            runOnUiThread: action => action());

        var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

        Assert.False(result.RepairAttempted);
        Assert.False(document.Enabled);
        Assert.Equal("standalone", result.Reason);
    }

    [Fact]
    public void PrepareForPostMutationSolve_StaticSolverLock_DoesNotRepair()
    {
        FakeGhDocument.EnableSolutions = false;
        var document = new FakeGhDocument { Enabled = false };
        var coordinator = new GhSolveReadinessCoordinator(
            isRhinoInside: () => true,
            getActiveDocument: () => document,
            runOnUiThread: action => action());

        var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

        Assert.False(result.RepairAttempted);
        Assert.False(document.Enabled);
        Assert.Equal("static_solver_disabled", result.Reason);

        FakeGhDocument.EnableSolutions = true;
    }

    [Fact]
    public void PrepareForPostMutationSolve_RirRookDrivenDisabledDocument_RepairsInstanceOnly()
    {
        FakeGhDocument.EnableSolutions = true;
        var document = new FakeGhDocument { Enabled = false };
        var coordinator = new GhSolveReadinessCoordinator(
            isRhinoInside: () => true,
            getActiveDocument: () => document,
            runOnUiThread: action => action());

        var result = coordinator.PrepareForPostMutationSolve(document, requestSolve: true, currentMutationIsRookDriven: true);

        Assert.True(result.RepairAttempted);
        Assert.True(result.RepairHeld);
        Assert.True(document.Enabled);
        Assert.True(FakeGhDocument.EnableSolutions);
    }

[Fact]
public void ArmDocumentTransitionRepair_RepairsOnceAndDisarms()
{
        FakeGhDocument.EnableSolutions = true;
        var document = new FakeGhDocument { Enabled = true };
        var coordinator = new GhSolveReadinessCoordinator(
            isRhinoInside: () => true,
            getActiveDocument: () => document,
            runOnUiThread: action => action(),
            utcNow: () => new DateTimeOffset(2026, 6, 13, 12, 0, 0, TimeSpan.Zero));

        coordinator.MarkRookManagedDocument(document, "gh_document_new");

        document.DisableThroughHost();
        Assert.True(document.Enabled);
        Assert.True(coordinator.LatestTelemetry.RepairAttempted);

        document.DisableThroughHost();
        Assert.False(document.Enabled);
        Assert.Equal("transition_first_repair", coordinator.LatestTelemetry.Reason);
    }
}
```

- [ ] **Step 2: Run the coordinator tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolveReadinessCoordinatorTests" -v minimal
```

Expected: fail because `GhSolveReadinessCoordinator` does not exist.

- [ ] **Step 3: Implement the coordinator public surface**

Create `src/Rook/InternalBridge/GhSolveReadinessCoordinator.cs` with these public types and method signatures:

```csharp
using System;
using System.Reflection;
using Rhino;

namespace Rook.InternalBridge;

internal sealed class GhSolveReadinessCoordinator
{
    private static readonly TimeSpan TransitionWindow = TimeSpan.FromSeconds(5);
    private readonly Func<bool> _isRhinoInside;
    private readonly Func<object?> _getActiveDocument;
    private readonly Action<Action> _runOnUiThread;
    private readonly Func<DateTimeOffset> _utcNow;
    private readonly object _sync = new();
    private object? _managedDocument;
    private object? _transitionDocument;
    private EventInfo? _transitionEnabledChangedEvent;
    private Delegate? _transitionEnabledChangedHandler;
    private DateTimeOffset _transitionExpiresAt;
    private bool _transitionRepairConsumed;
    private GhSolveReadinessTelemetry _latestTelemetry = GhSolveReadinessTelemetry.None;

    public GhSolveReadinessCoordinator(
        Func<bool>? isRhinoInside = null,
        Func<object?>? getActiveDocument = null,
        Action<Action>? runOnUiThread = null,
        Func<DateTimeOffset>? utcNow = null)
    {
        _isRhinoInside = isRhinoInside ?? (() => Rhino.Runtime.HostUtils.RunningAsRhinoInside);
        _getActiveDocument = getActiveDocument ?? GetGrasshopperActiveDocument;
        _runOnUiThread = runOnUiThread ?? (action => RhinoApp.InvokeOnUiThread(new Action(action)));
        _utcNow = utcNow ?? (() => DateTimeOffset.UtcNow);
    }

    public GhSolveReadinessTelemetry LatestTelemetry
    {
        get
        {
            lock (_sync)
            {
                return _latestTelemetry;
            }
        }
    }

    public GhSolveReadinessResult PrepareForPostMutationSolve(
        object? document,
        bool requestSolve,
        bool currentMutationIsRookDriven)
    {
        GhSolveReadinessResult result = GhSolveReadinessResult.NoAction("not_run");
        _runOnUiThread(() => result = PrepareOnUiThread(document, requestSolve, currentMutationIsRookDriven));
        return result;
    }

    public void MarkRookManagedDocument(object? document, string reason)
    {
        _runOnUiThread(() => MarkRookManagedDocumentOnUiThread(document, reason));
    }
}

internal readonly record struct GhSolveReadinessResult(
    bool RepairAttempted,
    bool RepairHeld,
    string Reason)
{
    public static GhSolveReadinessResult NoAction(string reason) => new(false, false, reason);
    public static GhSolveReadinessResult Repaired(bool held, string reason) => new(true, held, reason);
}

internal readonly record struct GhSolveReadinessTelemetry(
    bool RepairAttempted,
    bool RepairHeld,
    string Reason,
    string? Source,
    DateTimeOffset TimestampUtc)
{
    public static GhSolveReadinessTelemetry None =>
        new(false, false, "none", null, DateTimeOffset.MinValue);
}
```

- [ ] **Step 4: Implement schedule-time repair without touching the static flag**

Add the private implementation in the same file:

```csharp
private GhSolveReadinessResult PrepareOnUiThread(object? document, bool requestSolve, bool currentMutationIsRookDriven)
{
    if (!_isRhinoInside())
    {
        return Record(GhSolveReadinessResult.NoAction("standalone"), "schedule_time");
    }

    if (!requestSolve)
    {
        return Record(GhSolveReadinessResult.NoAction("solve_not_requested"), "schedule_time");
    }

    if (document is null)
    {
        return Record(GhSolveReadinessResult.NoAction("no_document"), "schedule_time");
    }

    var activeDocument = _getActiveDocument();
    if (!ReferenceEquals(document, activeDocument))
    {
        return Record(GhSolveReadinessResult.NoAction("not_active_document"), "schedule_time");
    }

    if (!currentMutationIsRookDriven && !ReferenceEquals(document, _managedDocument))
    {
        return Record(GhSolveReadinessResult.NoAction("not_rook_managed"), "schedule_time");
    }

    var state = GhSolverState.Inspect(document);
    if (state.GlobalEnableSolutions == false)
    {
        return Record(GhSolveReadinessResult.NoAction("static_solver_disabled"), "schedule_time");
    }

    if (state.DocumentEnabled != false)
    {
        return Record(GhSolveReadinessResult.NoAction("document_already_enabled"), "schedule_time");
    }

    if (!WriteInstanceEnabled(document, true))
    {
        return Record(GhSolveReadinessResult.Repaired(false, "instance_enabled_write_failed"), "schedule_time");
    }

    var after = GhSolverState.Inspect(_getActiveDocument());
    var held = ReferenceEquals(document, _getActiveDocument()) && after.DocumentEnabled == true;
    return Record(GhSolveReadinessResult.Repaired(held, held ? "schedule_time_repair_held" : "schedule_time_repair_did_not_hold"), "schedule_time");
}
```

Add the helper that writes only the instance property:

```csharp
private static bool WriteInstanceEnabled(object document, bool enabled)
{
    try
    {
        var property = document.GetType().GetProperty("Enabled", BindingFlags.Instance | BindingFlags.Public);
        if (property is null || !property.CanWrite)
        {
            return false;
        }

        property.SetValue(document, enabled);
        return true;
    }
    catch
    {
        return false;
    }
}
```

- [ ] **Step 5: Implement Rook document marking and bounded transition repair**

Add this private implementation in the same file:

```csharp
private void MarkRookManagedDocumentOnUiThread(object? document, string reason)
{
    TeardownTransitionSubscriptionOnUiThread("document_replaced");

    if (!_isRhinoInside() || document is null)
    {
        lock (_sync)
        {
            _managedDocument = document;
            _latestTelemetry = new GhSolveReadinessTelemetry(false, false, _isRhinoInside() ? "no_document" : "standalone", reason, _utcNow());
        }
        return;
    }

    lock (_sync)
    {
        _managedDocument = document;
        _transitionDocument = document;
        _transitionExpiresAt = _utcNow().Add(TransitionWindow);
        _transitionRepairConsumed = false;
        _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "transition_armed", reason, _utcNow());
    }

    SubscribeTransitionEnabledChangedOnUiThread(document);
}

private void SubscribeTransitionEnabledChangedOnUiThread(object document)
{
    var enabledChanged = document.GetType().GetEvent("EnabledChanged", BindingFlags.Instance | BindingFlags.Public);
    if (enabledChanged is null || enabledChanged.EventHandlerType is null)
    {
        lock (_sync)
        {
            _latestTelemetry = new GhSolveReadinessTelemetry(false, false, "enabled_changed_event_missing", "transition", _utcNow());
        }
        return;
    }

    EventHandler handler = (_, _) => OnTransitionEnabledChangedOnUiThread(document);
    var typedHandler = Delegate.CreateDelegate(enabledChanged.EventHandlerType, handler.Target, handler.Method);
    enabledChanged.AddEventHandler(document, typedHandler);

    lock (_sync)
    {
        _transitionEnabledChangedEvent = enabledChanged;
        _transitionEnabledChangedHandler = typedHandler;
    }
}

private void OnTransitionEnabledChangedOnUiThread(object document)
{
    if (_utcNow() > _transitionExpiresAt)
    {
        TeardownTransitionSubscriptionOnUiThread("transition_window_expired");
        return;
    }

    if (_transitionRepairConsumed || !ReferenceEquals(document, _transitionDocument))
    {
        TeardownTransitionSubscriptionOnUiThread("transition_window_disarmed");
        return;
    }

    var activeDocument = _getActiveDocument();
    var state = GhSolverState.Inspect(activeDocument);
    if (!ReferenceEquals(document, activeDocument) || state.GlobalEnableSolutions == false || state.DocumentEnabled != false)
    {
        return;
    }

    _transitionRepairConsumed = true;
    var wrote = WriteInstanceEnabled(document, true);
    var after = GhSolverState.Inspect(_getActiveDocument());
    var held = wrote && ReferenceEquals(document, _getActiveDocument()) && after.DocumentEnabled == true;
    Record(GhSolveReadinessResult.Repaired(held, held ? "transition_repair_held" : "transition_repair_did_not_hold"), "transition");
    TeardownTransitionSubscriptionOnUiThread("transition_first_repair");
}

private void TeardownTransitionSubscriptionOnUiThread(string reason)
{
    object? document;
    EventInfo? eventInfo;
    Delegate? handler;

    lock (_sync)
    {
        document = _transitionDocument;
        eventInfo = _transitionEnabledChangedEvent;
        handler = _transitionEnabledChangedHandler;
        _transitionDocument = null;
        _transitionEnabledChangedEvent = null;
        _transitionEnabledChangedHandler = null;
        _transitionRepairConsumed = false;
        _latestTelemetry = new GhSolveReadinessTelemetry(_latestTelemetry.RepairAttempted, _latestTelemetry.RepairHeld, reason, _latestTelemetry.Source, _utcNow());
    }

    if (document is not null && eventInfo is not null && handler is not null)
    {
        eventInfo.RemoveEventHandler(document, handler);
    }
}
```

Add the telemetry and active-doc helpers:

```csharp
private GhSolveReadinessResult Record(GhSolveReadinessResult result, string source)
{
    lock (_sync)
    {
        _latestTelemetry = new GhSolveReadinessTelemetry(result.RepairAttempted, result.RepairHeld, result.Reason, source, _utcNow());
    }

    return result;
}

private static object? GetGrasshopperActiveDocument()
{
    try
    {
        var instancesType = Type.GetType("Grasshopper.Instances, Grasshopper");
        var activeCanvas = instancesType?.GetProperty("ActiveCanvas", BindingFlags.Static | BindingFlags.Public)?.GetValue(null);
        return activeCanvas?.GetType().GetProperty("Document", BindingFlags.Instance | BindingFlags.Public)?.GetValue(activeCanvas);
    }
    catch
    {
        return null;
    }
}
```

- [ ] **Step 6: Run coordinator tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolveReadinessCoordinatorTests" -v minimal
```

Expected: pass.

- [ ] **Step 7: Commit coordinator**

Run:

```powershell
git add src\Rook\InternalBridge\GhSolveReadinessCoordinator.cs src\Rook.Tests\InternalBridge\GhSolveReadinessCoordinatorTests.cs
git commit -m "feat: add rir grasshopper solve readiness coordinator"
```

---

### Task 3: Wire Coordinator Into the Shared Safe-Solve Path

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`
- Modify: `src/Rook/Handlers/GhSolvePolicy.cs`
- Modify: `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs`
- Modify: `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`

- [ ] **Step 1: Write failing safe-solve tests**

Extend `src/Rook.Tests/Handlers/RequestPostMutationSolveTests.cs` with fake doc static flags and these tests:

```csharp
[Fact]
public void RequestPostMutationSolve_RirDisabledInstanceRepairsBeforeScheduling()
{
    FakeDoc.EnableSolutions = true;
    var document = new FakeDoc { Enabled = false };
    var dirty = new FakeObj();
    var handler = CreateHandlerForRirRepair(
        isRhinoInside: () => true,
        getActiveDocument: () => document);

    var outcome = handler.RequestPostMutationSolve(document, new[] { dirty }, requestSolve: true, delayMs: 1);

    Assert.True(outcome.RirRepairAttempted);
    Assert.True(outcome.RirRepairHeld);
    Assert.True(document.Enabled);
    Assert.True(outcome.SolveScheduled);
    Assert.Single(document.Scheduled);
    Assert.Equal(new[] { false }, dirty.Expire);
}

[Fact]
public void RequestPostMutationSolve_StaticSolverDisabledDoesNotRepairOrSchedule()
{
    FakeDoc.EnableSolutions = false;
    var document = new FakeDoc { Enabled = false };
    var handler = CreateHandlerForRirRepair(
        isRhinoInside: () => true,
        getActiveDocument: () => document);

    var outcome = handler.RequestPostMutationSolve(document, Array.Empty<object>(), requestSolve: true, delayMs: 1);

    Assert.False(outcome.RirRepairAttempted);
    Assert.False(document.Enabled);
    Assert.False(outcome.SolveScheduled);
    Assert.True(outcome.SolverLocked);

    FakeDoc.EnableSolutions = true;
}

[Fact]
public void RequestPostMutationSolve_StandaloneDisabledInstanceDoesNotRepair()
{
    FakeDoc.EnableSolutions = true;
    var document = new FakeDoc { Enabled = false };
    var handler = CreateHandlerForRirRepair(
        isRhinoInside: () => false,
        getActiveDocument: () => document);

    var outcome = handler.RequestPostMutationSolve(document, Array.Empty<object>(), requestSolve: true, delayMs: 1);

    Assert.False(outcome.RirRepairAttempted);
    Assert.False(document.Enabled);
    Assert.False(outcome.SolveScheduled);
}

private static GrasshopperHandler CreateHandlerForRirRepair(Func<bool> isRhinoInside, Func<object?> getActiveDocument)
{
    var coordinator = new GhSolveReadinessCoordinator(
        isRhinoInside: isRhinoInside,
        getActiveDocument: getActiveDocument,
        runOnUiThread: action => action());

    return new GrasshopperHandler(solveReadinessCoordinator: coordinator);
}
```

Update the local fake doc in the same test file:

```csharp
private sealed class FakeDoc
{
    public static bool EnableSolutions { get; set; } = true;
    public bool Enabled { get; set; } = true;
    public List<int> Scheduled { get; } = new();

    public void ScheduleSolution(int delay)
    {
        Scheduled.Add(delay);
    }
}
```

- [ ] **Step 2: Extend policy tests for metadata**

Add this test to `src/Rook.Tests/Handlers/GhSolvePolicyTests.cs`:

```csharp
[Fact]
public void Decide_PreservesRepairMetadata()
{
    var state = new GhSolverState.Result(
        enabled: true,
        known: true,
        solutionState: "PreProcess",
        globalEnableSolutions: true,
        documentEnabled: true);

    var outcome = GhSolvePolicy.Decide(
        state,
        requestSolve: true,
        scheduleAttempted: true,
        scheduleSucceeded: true,
        repairAttempted: true,
        repairHeld: true,
        repairReason: "schedule_time_repair_held");

    Assert.True(outcome.RirRepairAttempted);
    Assert.True(outcome.RirRepairHeld);
    Assert.Equal("schedule_time_repair_held", outcome.RirRepairReason);
    Assert.True(outcome.SolveScheduled);
}
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolvePolicyTests" -v minimal
```

Expected: fail because the handler has no coordinator injection/test seam and `GhSolveOutcome` lacks repair fields.

- [ ] **Step 4: Add repair fields to `GhSolveOutcome` and `GhSolvePolicy.Decide`**

In `src/Rook/Handlers/GhSolvePolicy.cs`, extend `GhSolveOutcome`:

```csharp
internal readonly struct GhSolveOutcome
{
    public GhSolveOutcome(
        bool solveScheduled,
        bool solverLocked,
        bool solverStateKnown,
        bool verificationDeferred,
        IReadOnlyList<string> warnings,
        bool rirRepairAttempted,
        bool rirRepairHeld,
        string? rirRepairReason)
    {
        SolveScheduled = solveScheduled;
        SolverLocked = solverLocked;
        SolverStateKnown = solverStateKnown;
        VerificationDeferred = verificationDeferred;
        Warnings = warnings;
        RirRepairAttempted = rirRepairAttempted;
        RirRepairHeld = rirRepairHeld;
        RirRepairReason = rirRepairReason;
    }

    public bool SolveScheduled { get; }
    public bool SolverLocked { get; }
    public bool SolverStateKnown { get; }
    public bool VerificationDeferred { get; }
    public IReadOnlyList<string> Warnings { get; }
    public bool RirRepairAttempted { get; }
    public bool RirRepairHeld { get; }
    public string? RirRepairReason { get; }
}
```

Add optional parameters to `Decide` with default values so existing callers compile during the edit:

```csharp
public static GhSolveOutcome Decide(
    GhSolverState.Result solverState,
    bool requestSolve,
    bool scheduleAttempted,
    bool scheduleSucceeded,
    bool repairAttempted = false,
    bool repairHeld = false,
    string? repairReason = null)
```

Pass the repair values into every `new GhSolveOutcome(...)` call. Do not change the locked-solver branch logic.

- [ ] **Step 5: Add the coordinator field and test seam to `GrasshopperHandler`**

In `src/Rook/Handlers/GrasshopperHandler.cs`, replace the `_bridgeCore` field initializer and add a private coordinator field beside `_idRegistry`:

```csharp
private readonly IGrasshopperCore _bridgeCore;
private readonly GhSolveReadinessCoordinator _solveReadinessCoordinator;
```

Add constructors that preserve the existing public construction path and provide an internal test seam:

```csharp
public GrasshopperHandler()
    : this(null, null)
{
}

internal GrasshopperHandler(
    IGrasshopperCore? bridgeCore = null,
    GhSolveReadinessCoordinator? solveReadinessCoordinator = null)
{
    _bridgeCore = bridgeCore ?? new GrasshopperCore();
    _solveReadinessCoordinator = solveReadinessCoordinator ?? new GhSolveReadinessCoordinator();
}
```

Keep the public construction behavior unchanged.

- [ ] **Step 6: Insert schedule-time repair before policy decision**

In `src/Rook/Handlers/GrasshopperHandler.SolvePolicy.cs`, update `RequestPostMutationSolve` so the sequence is:

```csharp
foreach (var dirtyObject in dirtyObjects.Where(obj => obj is not null).Distinct())
{
    TryExpireSolution(dirtyObject, recompute: false);
}

var readiness = _solveReadinessCoordinator.PrepareForPostMutationSolve(
    document,
    requestSolve,
    currentMutationIsRookDriven: true);

var solverState = GhSolverState.Inspect(document);
var scheduleAttempted = false;
var scheduleSucceeded = false;

if (requestSolve && solverState.Enabled == true)
{
    scheduleAttempted = true;
    scheduleSucceeded = TrySchedule(document, delayMs);
}

return GhSolvePolicy.Decide(
    solverState,
    requestSolve,
    scheduleAttempted,
    scheduleSucceeded,
    readiness.RepairAttempted,
    readiness.RepairHeld,
    readiness.Reason);
```

Do not add another `ExpireSolution(false)` or `ScheduleSolution(...)` call outside this method.

- [ ] **Step 7: Run safe-solve tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolvePolicyTests" -v minimal
```

Expected: pass.

- [ ] **Step 8: Commit safe-solve wiring**

Run:

```powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook\Handlers\GrasshopperHandler.SolvePolicy.cs src\Rook\Handlers\GhSolvePolicy.cs src\Rook.Tests\Handlers\RequestPostMutationSolveTests.cs src\Rook.Tests\Handlers\GhSolvePolicyTests.cs
git commit -m "fix: repair rir grasshopper document before async solve scheduling"
```

---

### Task 4: Mark Rook Documents and Surface Status Telemetry

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs`
- Modify: `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`
- Create or modify: `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`

- [ ] **Step 1: Write lifecycle source tests**

Create `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class GrasshopperDocumentLifecycleSourceTests
{
    [Fact]
    public void NewDocument_MarksRookManagedDocument()
    {
        var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
        Assert.Contains("_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, \"gh_document_new\")", source);
    }

    [Fact]
    public void OpenDocument_MarksRookManagedDocument()
    {
        var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
        Assert.Contains("_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, \"gh_document_open\")", source);
    }

    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
        {
            dir = dir.Parent;
        }

        Assert.NotNull(dir);
        return dir!.FullName;
    }
}
```

- [ ] **Step 2: Write DTO tests for diagnostics**

In `src/Rook.Tests/InternalBridge/GrasshopperStatusDtoTests.cs`, add:

```csharp
[Fact]
public void GrasshopperStatusDto_IncludesSolverFlagAndRirRepairDiagnostics()
{
    var dto = new GrasshopperStatusDto
    {
        SolverEnabled = false,
        SolverStateKnown = true,
        SolverGlobalEnableSolutions = true,
        SolverDocumentEnabled = false,
        RirRepairAttempted = true,
        RirRepairHeld = false,
        RirRepairReason = "schedule_time_repair_did_not_hold"
    };

    Assert.False(dto.SolverEnabled);
    Assert.True(dto.SolverGlobalEnableSolutions);
    Assert.False(dto.SolverDocumentEnabled);
    Assert.True(dto.RirRepairAttempted);
    Assert.False(dto.RirRepairHeld);
    Assert.Equal("schedule_time_repair_did_not_hold", dto.RirRepairReason);
}
```

- [ ] **Step 3: Run lifecycle/status tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~GrasshopperStatusDtoTests" -v minimal
```

Expected: fail because the lifecycle marks and DTO fields do not exist.

- [ ] **Step 4: Mark Rook-managed documents after canvas replacement**

In `src/Rook/Handlers/GrasshopperHandler.cs`, after `gh.Canvas.Document = newDocument;` and registry reset in `NewDocument()`, add:

```csharp
_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, "gh_document_new");
```

In `OpenDocument()`, after the loaded `document` is assigned to `gh.Canvas.Document` and the registry is reset, add:

```csharp
_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, "gh_document_open");
```

Do not call `DocumentServer.AddDocument`.

- [ ] **Step 5: Add status DTO fields**

In `src/Rook/InternalBridge/GrasshopperCore.cs`, add nullable diagnostics to `GrasshopperStatusDto`:

```csharp
public bool? SolverGlobalEnableSolutions { get; set; }
public bool? SolverDocumentEnabled { get; set; }
public bool RirRepairAttempted { get; set; }
public bool RirRepairHeld { get; set; }
public string? RirRepairReason { get; set; }
public string? RirRepairSource { get; set; }
```

When `ObserveStatus()` builds the DTO from `GhSolverState.Inspect(activeDocument)`, assign:

```csharp
SolverGlobalEnableSolutions = solverState.GlobalEnableSolutions,
SolverDocumentEnabled = solverState.DocumentEnabled,
```

- [ ] **Step 6: Merge latest coordinator telemetry into `gh_status`**

In `src/Rook/Handlers/GrasshopperHandler.cs`, change `GetStatus()` from a direct return to:

```csharp
private ApiResponse GetStatus()
{
    var status = _bridgeCore.GetStatus();
    var telemetry = _solveReadinessCoordinator.LatestTelemetry;

    status.RirRepairAttempted = telemetry.RepairAttempted;
    status.RirRepairHeld = telemetry.RepairHeld;
    status.RirRepairReason = telemetry.Reason;
    status.RirRepairSource = telemetry.Source;

    return ToApiResponse(status);
}
```

- [ ] **Step 7: Run lifecycle/status tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests|FullyQualifiedName~GrasshopperStatusDtoTests" -v minimal
```

Expected: pass.

- [ ] **Step 8: Commit lifecycle and status telemetry**

Run:

```powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook\InternalBridge\GrasshopperCore.cs src\Rook.Tests\InternalBridge\GrasshopperStatusDtoTests.cs src\Rook.Tests\Handlers\GrasshopperDocumentLifecycleSourceTests.cs
git commit -m "feat: surface rir grasshopper solve readiness telemetry"
```

---

### Task 5: Route `gh_edit` Through the Shared Safe-Solve Scheduler

**Files:**
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Create: `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`

- [ ] **Step 1: Write source guard for `gh_edit` scheduling**

Create `src/Rook.Tests/Handlers/GhEditSolvePathSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class GhEditSolvePathSourceTests
{
    [Fact]
    public void ApplyEdit_UsesSharedPostMutationSolveScheduler()
    {
        var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
        Assert.Contains("RequestPostMutationSolve(gh.Document!", source);
        Assert.DoesNotContain("ScheduleDocumentSolution(gh.Document!)", source);
    }

    [Fact]
    public void ApplyEdit_ReturnsSolveOutcomeMetadata()
    {
        var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
        Assert.Contains("solve_scheduled", source);
        Assert.Contains("solver_locked", source);
        Assert.Contains("rir_repair_attempted", source);
        Assert.Contains("rir_repair_held", source);
    }

    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
        {
            dir = dir.Parent;
        }

        Assert.NotNull(dir);
        return dir!.FullName;
    }
}
```

- [ ] **Step 2: Run source guard and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhEditSolvePathSourceTests" -v minimal
```

Expected: fail because `ApplyEdit` still calls `ScheduleDocumentSolution(gh.Document!)` directly.

- [ ] **Step 3: Track dirty objects during `ApplyEdit`**

Near the existing counters in `ApplyEdit`, add:

```csharp
var dirtyObjects = new List<object>();

void AddDirty(object? candidate)
{
    if (candidate is not null && !dirtyObjects.Any(existing => ReferenceEquals(existing, candidate)))
    {
        dirtyObjects.Add(candidate);
    }
}
```

After a successful value or nickname mutation, call:

```csharp
AddDirty(obj);
```

After a successful create, call:

```csharp
AddDirty(obj);
```

After a successful connect or disconnect operation, call:

```csharp
AddDirty(targetParam);
```

Do not add group-only edits to this dirty list because the current scheduling condition does not include group edits.

- [ ] **Step 4: Replace direct document scheduling with `RequestPostMutationSolve`**

Replace the direct schedule block:

```csharp
if (valuesSet > 0 || connected > 0 || disconnected > 0 || created > 0 || deleted > 0)
{
    ScheduleDocumentSolution(gh.Document!);
}
```

with:

```csharp
var changedObjects = valuesSet > 0 || connected > 0 || disconnected > 0 || created > 0 || deleted > 0;
var solveOutcome = RequestPostMutationSolve(
    gh.Document!,
    dirtyObjects,
    requestSolve: changedObjects,
    delayMs: 1);
```

For delete-only edits, `dirtyObjects` can be empty. `RequestPostMutationSolve` must still inspect and schedule the document when `requestSolve=true`.

- [ ] **Step 5: Return solve outcome metadata in the edit summary**

Where `ApplyEdit` builds the response dictionary, add these fields to the existing edit summary object:

```csharp
["solve_scheduled"] = solveOutcome.SolveScheduled,
["solver_locked"] = solveOutcome.SolverLocked,
["solver_state_known"] = solveOutcome.SolverStateKnown,
["verification_deferred"] = solveOutcome.VerificationDeferred,
["rir_repair_attempted"] = solveOutcome.RirRepairAttempted,
["rir_repair_held"] = solveOutcome.RirRepairHeld,
["rir_repair_reason"] = solveOutcome.RirRepairReason,
["solve_warnings"] = solveOutcome.Warnings.ToArray(),
```

Keep returning mutation success once the batch is committed. Do not wait for solve completion; #246 owns the later async-ack cleanup.

- [ ] **Step 6: Run source guard**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhEditSolvePathSourceTests" -v minimal
```

Expected: pass.

- [ ] **Step 7: Commit `gh_edit` scheduling route**

Run:

```powershell
git add src\Rook\Handlers\GrasshopperHandler.cs src\Rook.Tests\Handlers\GhEditSolvePathSourceTests.cs
git commit -m "fix: route gh_edit through safe grasshopper solve scheduling"
```

---

### Task 6: Add Sync-Solve and Static-Flag Source Guards

**Files:**
- Modify: `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`

- [ ] **Step 1: Extend source guards**

Add these tests to `src/Rook.Tests/Handlers/NoSyncExpireInScriptPathTests.cs`:

```csharp
[Fact]
public void GrasshopperMutationPaths_DoNotCallNewSolution()
{
    var files = new[]
    {
        Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"),
        Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"),
        Path.Combine(RepoRoot(), "src", "Rook", "InternalBridge", "GhSolveReadinessCoordinator.cs")
    };

    foreach (var file in files)
    {
        var source = File.ReadAllText(file);
        Assert.DoesNotContain(".NewSolution(", source);
    }
}

[Fact]
public void GrasshopperMutationPaths_DoNotUseSynchronousExpireSolution()
{
    var files = new[]
    {
        Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"),
        Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.SolvePolicy.cs"),
        Path.Combine(RepoRoot(), "src", "Rook", "InternalBridge", "GhSolveReadinessCoordinator.cs")
    };

    foreach (var file in files)
    {
        var source = File.ReadAllText(file);
        Assert.DoesNotContain("ExpireSolution(true", source);
    }
}

[Fact]
public void RirSolveReadinessCoordinator_DoesNotWriteStaticEnableSolutions()
{
    var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "InternalBridge", "GhSolveReadinessCoordinator.cs"));
    Assert.DoesNotContain("EnableSolutions =", source);
    Assert.DoesNotContain("SetValue(null", source);
}

private static string RepoRoot()
{
    var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
    while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
    {
        dir = dir.Parent;
    }

    Assert.NotNull(dir);
    return dir!.FullName;
}
```

- [ ] **Step 2: Run guard tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~NoSyncExpireInScriptPathTests" -v minimal
```

Expected: pass.

- [ ] **Step 3: Commit source guards**

Run:

```powershell
git add src\Rook.Tests\Handlers\NoSyncExpireInScriptPathTests.cs
git commit -m "test: guard grasshopper rir repair against sync solves"
```

---

### Task 7: Run Automated Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~GhSolverStateTests|FullyQualifiedName~GhSolveReadinessCoordinatorTests|FullyQualifiedName~RequestPostMutationSolveTests|FullyQualifiedName~GhSolvePolicyTests|FullyQualifiedName~GrasshopperStatusDtoTests|FullyQualifiedName~GhEditSolvePathSourceTests|FullyQualifiedName~NoSyncExpireInScriptPathTests|FullyQualifiedName~GrasshopperDocumentLifecycleSourceTests" -v minimal
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full managed test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -v minimal
```

Expected: pass. If unrelated pre-existing tests fail, record the failing test names and run the focused suite again before live verification.

- [ ] **Step 3: Review diff for forbidden patterns**

Run:

```powershell
git diff -- src/Rook src/Rook.Tests
```

Expected:

- no `NewSolution` added;
- no `ExpireSolution(true)` added;
- no assignment to `GH_Document.EnableSolutions`;
- `gh_edit` uses `RequestPostMutationSolve`;
- `RequestPostMutationSolve` has one `TrySchedule` decision point.

---

### Task 8: Build and Deploy the Managed Companion for Live Testing

**Files:**
- Build outputs only.

- [ ] **Step 1: Close Rhino and Revit before building**

Close standalone Rhino, Rhino.Inside.Revit, Grasshopper, and Revit so the managed plugin files are not locked.

- [ ] **Step 2: Build the managed companion**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -c Release -f net48
```

Expected: build succeeds.

- [ ] **Step 3: Build RookBim after Rook**

Run:

```powershell
dotnet build src\RookBim\RookBim.csproj -c Release -f net48
```

Expected: build succeeds and copies `RookBim.dll` into `src\Rook\bin\Release\net48`.

- [ ] **Step 4: Confirm local plugin output changed**

Run:

```powershell
Get-ChildItem src\Rook\bin\Release\net48 -Filter Rook*.dll | Select-Object Name, LastWriteTime
```

Expected: `Rook.dll` has a timestamp from this build. `RookBim.dll` is present after Step 3.

---

### Task 9: Live Verify in Rhino.Inside.Revit

**Files:**
- No source edits expected.

- [ ] **Step 1: Start RIR with Grasshopper open**

Open Revit, start Rhino.Inside.Revit, and open Grasshopper. Confirm Rook is serving:

```powershell
$Base = "http://127.0.0.1:64702"
Invoke-RestMethod "$Base/capabilities" | Select-Object version, rhinoInside
```

Expected: version includes the local build and `rhinoInside=True`. Adjust `$Base` to the live port if discovery reports a different port.

- [ ] **Step 2: Create an existing canvas, then replace it repeatedly**

Use `gh_document_new` three times over the existing canvas. After the final call:

```powershell
$status = Invoke-RestMethod "$Base/gh/status"
$status.solverGlobalEnableSolutions
$status.solverDocumentEnabled
$status.rirRepairReason
```

Expected: the call succeeds and reports separate static/instance flags.

- [ ] **Step 3: Build a slider-to-panel graph through `gh_edit`**

Use the Rook MCP `gh_edit` tool to create a Number Slider, create a Panel, and connect slider output to panel input in one committed edit batch. Inspect the edit response.

Expected:

- `edit_summary.solve_scheduled=true`;
- `edit_summary.solver_locked=false`;
- `edit_summary.rir_repair_attempted` is true if RIR had disabled the document, false if the document was already enabled;
- no callback waits for solve completion.

- [ ] **Step 4: Confirm volatile panel data without manual solve**

Run `gh_snapshot` or the direct inspection route used during the spike.

Expected: the panel volatile data contains the slider value. No `NewSolution` command or manual Grasshopper recompute was used.

- [ ] **Step 5: Verify Revit-foreground schedule-time repair**

Focus Revit so Grasshopper is not foreground. Confirm the activation gate has disabled the instance document:

```powershell
$status = Invoke-RestMethod "$Base/gh/status"
$status.solverEnabled
$status.solverGlobalEnableSolutions
$status.solverDocumentEnabled
```

Expected before edit: `solverGlobalEnableSolutions=True`; `solverDocumentEnabled` may be `False`.

Use `gh_edit` to change the slider value while Revit remains foreground.

Expected:

- mutation succeeds;
- `edit_summary.rir_repair_attempted=true` when `solverDocumentEnabled` was false;
- `edit_summary.rir_repair_held=true`;
- `edit_summary.solve_scheduled=true`;
- follow-up `gh_snapshot` shows the panel volatile data updated to the new slider value;
- no manual `NewSolution`.

- [ ] **Step 6: Verify async solve completion, not only immediate re-read**

Use the event-probe script from the spec session, or a follow-up `gh_snapshot` loop, to observe the solved data after the scheduled delay.

Expected: `SolutionEnd` or equivalent completed-solve evidence appears before the test is counted as passed.

- [ ] **Step 7: Verify user-lock preservation in RIR**

Lock the solver through the Grasshopper UI. Run a small `gh_edit` mutation.

Expected:

- Rook does not set `GH_Document.EnableSolutions=true`;
- `edit_summary.rir_repair_attempted=false`;
- `edit_summary.solver_locked=true`;
- `edit_summary.verification_deferred=true` or equivalent deferred metadata;
- no panel data update occurs until the user unlocks the solver or manually solves.

---

### Task 10: Live Verify Standalone Rhino Regression

**Files:**
- No source edits expected.

- [ ] **Step 1: Start standalone Rhino with Grasshopper open**

Confirm Rook is serving and not inside RIR:

```powershell
$Base = "http://127.0.0.1:64702"
Invoke-RestMethod "$Base/capabilities" | Select-Object version, rhinoInside
```

Expected: `rhinoInside=False`.

- [ ] **Step 2: Run the slider-to-panel edit**

Use `gh_document_new`, then `gh_edit` to create a Number Slider, create a Panel, and wire them.

Expected:

- `edit_summary.solve_scheduled=true`;
- `edit_summary.rir_repair_attempted=false`;
- panel volatile data populates through the existing async solve behavior.

- [ ] **Step 3: Confirm no standalone transition repair**

Run:

```powershell
$status = Invoke-RestMethod "$Base/gh/status"
$status.rirRepairAttempted
$status.rirRepairReason
```

Expected: no RIR repair was attempted. The reason may be `standalone`, `none`, or the latest non-repair reason from the coordinator; it must not report a held repair.

---

### Task 11: Final Review and PR Prep

**Files:**
- No source edits expected unless review finds a defect.

- [ ] **Step 1: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional #247 changes are present. The unrelated `knowledge/gh/operations_knowledge.json` file may remain dirty and must not be staged for this PR.

- [ ] **Step 2: Review commits**

Run:

```powershell
git log --oneline --decorate -n 12
```

Expected: the branch contains the spec commits and the implementation commits from this plan.

- [ ] **Step 3: Create the PR body variable**

Run:

```powershell
$PrBody = @"
## Summary
- fixes RIR Grasshopper solve scheduling by repairing the active document instance flag at async schedule time
- preserves PR #208 by avoiding NewSolution, ExpireSolution(true), and static solver flag writes
- adds diagnostics for static vs instance solver flags and RIR repair outcome

## Verification
- dotnet test src\Rook.Tests\Rook.Tests.csproj -v minimal
- RIR live: repeated gh_document_new replacement + slider-to-panel solve
- RIR live: Revit foreground edit repaired instance flag and async-solved without manual NewSolution
- RIR live: user solver lock stayed locked and deferred solve
- Standalone Rhino live: no RIR repair, slider-to-panel still solved
"@
```

- [ ] **Step 4: Push branch and open draft PR**

Run:

```powershell
git push -u origin fix/247-rir-gh-solver-enabled-race
gh pr create -R bringfire/Rook --draft --title "Fix RIR Grasshopper solver enable race" --body $PrBody
```

Expected: draft PR opens for issue #247 only.
