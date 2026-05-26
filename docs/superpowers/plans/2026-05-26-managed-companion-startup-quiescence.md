# Managed Companion Startup Quiescence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make managed companion load inert during Rhino startup/open and run companion startup only after Rhino reaches stable idle.

**Architecture:** Add a small fakeable startup gate that decides when idle is quiescent enough to run startup. `RookPlugin` owns Rhino hook wiring and side effects; the gate owns state transitions. `OnLoad` becomes trace/hooks only, while panels, toolbar, bridge registration, job reconcile, and backfill move behind the idle gate.

**Tech Stack:** C# / RhinoCommon / xUnit; optional native C++ message-only amendment only if validation shows the existing native bridge poll output is misleading.

---

## File Map

- Create `src/Rook/Startup/CompanionStartupGate.cs`
  - Pure state machine for idle/quiescence decisions.
  - No Rhino references.
  - Unit-tested directly.
- Modify `src/Rook/RookPlugin.cs`
  - Remove constructor idle hookup.
  - Make `OnLoad` inert.
  - Attach `RhinoApp.Idle`, `RhinoDoc.BeginOpenDocument`, `RhinoDoc.EndOpenDocument`, and `RhinoDoc.EndOpenDocumentInitialViewUpdate`.
  - Move startup side effects into deferred startup methods.
  - Replace timer retry with idle-driven bridge retry.
- Modify `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`
  - Flip existing source tests from immediate startup assertions to inert `OnLoad` assertions.
  - Keep existing non-fatal panel/reconcile/backfill tests against deferred startup methods.
- Create `src/Rook.Tests/Plugin/CompanionStartupGateTests.cs`
  - Direct unit tests for gate behavior.
- Optional, only if validation proves it is needed: modify `src/RookNative/RookNativePlugin.cpp`
  - Message-only change from hard bridge failure wording to deferred bridge availability wording.

Do not modify Vision/WebView behavior, registry scripts, installer behavior, or native dispatcher policy in this plan.

## Task 1: Pure Startup Gate

**Files:**
- Create: `src/Rook/Startup/CompanionStartupGate.cs`
- Create: `src/Rook.Tests/Plugin/CompanionStartupGateTests.cs`

- [ ] **Step 1: Write failing gate tests**

Create `src/Rook.Tests/Plugin/CompanionStartupGateTests.cs`:

```csharp
using Rook.Startup;
using Xunit;

namespace Rook.Tests.Plugin
{
    public class CompanionStartupGateTests
    {
        [Fact]
        public void CommandActive_DoesNotStartAndResetsStableIdle()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var first = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));
            var blocked = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: true,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, first.Action);
            Assert.Equal(1, first.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.None, blocked.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, blocked.BlockedReason);
            Assert.Equal(0, blocked.StableIdleCount);
        }

        [Fact]
        public void DocumentOpenActive_DoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: true,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.DocumentOpening, decision.BlockedReason);
            Assert.Equal(0, decision.StableIdleCount);
        }

        [Fact]
        public void FirstQuiescentIdle_DoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.None, decision.BlockedReason);
            Assert.Equal(1, decision.StableIdleCount);
        }

        [Fact]
        public void SecondConsecutiveQuiescentIdle_StartsOnce()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var start = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var repeated = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.RunStartup, start.Action);
            Assert.Equal(2, start.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.None, repeated.Action);
            Assert.True(repeated.StartupAlreadyRequested);
        }

        [Fact]
        public void InterruptedQuiescence_ResetsStableIdleCount()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, true, false));
            var firstAfterInterruption = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, firstAfterInterruption.Action);
            Assert.Equal(1, firstAfterInterruption.StableIdleCount);
        }

        [Fact]
        public void LoadedAfterBeginOpen_DoesNotRunUntilEndOpenOrStableIdleAfterCommandClears()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var missedBeginOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: true,
                DocumentOpening: false,
                ShutdownStarted: false));
            var openStillActive = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: true,
                ShutdownStarted: false));
            var firstStableAfterOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));
            var secondStableAfterOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, missedBeginOpen.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, missedBeginOpen.BlockedReason);
            Assert.Equal(CompanionStartupGateAction.None, openStillActive.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.DocumentOpening, openStillActive.BlockedReason);
            Assert.Equal(CompanionStartupGateAction.None, firstStableAfterOpen.Action);
            Assert.Equal(1, firstStableAfterOpen.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.RunStartup, secondStableAfterOpen.Action);
        }

        [Fact]
        public void StartupComplete_DoesNotRunAgain()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.MarkStartupComplete();
            var afterComplete = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, afterComplete.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.StartupComplete, afterComplete.BlockedReason);
        }

        [Fact]
        public void BlockedQuiescence_WaitsUntilLaterQuiescentIdle()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            for (var i = 0; i < 500; i++)
            {
                var blocked = gate.EvaluateIdle(new CompanionStartupGateSnapshot(true, false, false));
                Assert.Equal(CompanionStartupGateAction.None, blocked.Action);
                Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, blocked.BlockedReason);
            }

            var first = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var second = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, first.Action);
            Assert.Equal(CompanionStartupGateAction.RunStartup, second.Action);
        }

        [Fact]
        public void ShutdownStarted_BlocksAndDoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 1);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: true));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.ShutdownStarted, decision.BlockedReason);
        }
    }
}
```

- [ ] **Step 2: Run failing gate tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~CompanionStartupGateTests
```

Expected: fails because `Rook.Startup.CompanionStartupGate` types do not exist.

- [ ] **Step 3: Add the gate implementation**

Create `src/Rook/Startup/CompanionStartupGate.cs`:

```csharp
namespace Rook.Startup
{
    internal enum CompanionStartupGateAction
    {
        None,
        RunStartup,
    }

    internal enum CompanionStartupGateBlockedReason
    {
        None,
        CommandActive,
        DocumentOpening,
        ShutdownStarted,
        StartupComplete,
    }

    internal sealed record CompanionStartupGateSnapshot(
        bool CommandActive,
        bool DocumentOpening,
        bool ShutdownStarted);

    internal sealed record CompanionStartupGateDecision(
        CompanionStartupGateAction Action,
        CompanionStartupGateBlockedReason BlockedReason,
        int StableIdleCount,
        bool StartupAlreadyRequested,
        bool StartupComplete);

    internal sealed class CompanionStartupGate
    {
        private readonly int _requiredStableIdleTicks;
        private int _stableIdleCount;
        private bool _startupRequested;
        private bool _startupComplete;

        public CompanionStartupGate(
            int requiredStableIdleTicks = 2)
        {
            _requiredStableIdleTicks = requiredStableIdleTicks > 0
                ? requiredStableIdleTicks
                : 1;
        }

        public CompanionStartupGateDecision EvaluateIdle(
            CompanionStartupGateSnapshot snapshot)
        {
            if (_startupComplete)
            {
                return Decision(
                    CompanionStartupGateAction.None,
                    CompanionStartupGateBlockedReason.StartupComplete);
            }

            var blockedReason = GetBlockedReason(snapshot);
            if (blockedReason != CompanionStartupGateBlockedReason.None)
            {
                _stableIdleCount = 0;
                return Decision(CompanionStartupGateAction.None, blockedReason);
            }

            _stableIdleCount++;

            if (!_startupRequested && _stableIdleCount >= _requiredStableIdleTicks)
            {
                _startupRequested = true;
                return Decision(
                    CompanionStartupGateAction.RunStartup,
                    CompanionStartupGateBlockedReason.None);
            }

            return Decision(
                CompanionStartupGateAction.None,
                CompanionStartupGateBlockedReason.None);
        }

        public void MarkStartupComplete()
        {
            _startupComplete = true;
        }

        public void MarkStartupAvailableForRetry()
        {
            if (!_startupComplete)
            {
                _startupRequested = false;
                _stableIdleCount = _requiredStableIdleTicks - 1;
            }
        }

        private static CompanionStartupGateBlockedReason GetBlockedReason(
            CompanionStartupGateSnapshot snapshot)
        {
            if (snapshot.ShutdownStarted)
                return CompanionStartupGateBlockedReason.ShutdownStarted;
            if (snapshot.DocumentOpening)
                return CompanionStartupGateBlockedReason.DocumentOpening;
            if (snapshot.CommandActive)
                return CompanionStartupGateBlockedReason.CommandActive;
            return CompanionStartupGateBlockedReason.None;
        }

        private CompanionStartupGateDecision Decision(
            CompanionStartupGateAction action,
            CompanionStartupGateBlockedReason reason)
        {
            return new CompanionStartupGateDecision(
                action,
                reason,
                _stableIdleCount,
                _startupRequested,
                _startupComplete);
        }
    }
}
```

- [ ] **Step 4: Run gate tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~CompanionStartupGateTests
```

Expected: all `CompanionStartupGateTests` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src\Rook\Startup\CompanionStartupGate.cs src\Rook.Tests\Plugin\CompanionStartupGateTests.cs
git commit -m "feat: add managed companion startup gate"
```

## Task 2: Inert `OnLoad` Source Contract Tests

**Files:**
- Modify: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`

- [ ] **Step 1: Replace unsafe `OnLoad` assertions**

Modify `StartupPanelRegistration_IsWrappedAsNonFatalOnLoadStep` so it no longer asserts registration from `OnLoad`. Rename it to `StartupPanelRegistration_IsDeferredAndWrappedAsNonFatal`.

Use this test body:

```csharp
[Fact]
public void StartupPanelRegistration_IsDeferredAndWrappedAsNonFatal()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
    var registerPanels = ExtractMethod(source, "private void RegisterStartupPanels()");
    var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

    Assert.DoesNotContain("RegisterStartupPanels();", onLoad);
    Assert.Contains("RegisterStartupPanels();", deferredStartup);

    var panelBlock = ExtractTryCatchContaining(
        registerPanels,
        "Panels.RegisterPanel(this, chatPanelType, \"Rook Chat\"");

    Assert.Contains(
        "Panels.RegisterPanel(this, chatPanelType, \"Rook Chat\"",
        panelBlock.TryBody);
    Assert.Contains(
        "Panels.RegisterPanel(this, visionPanelType, \"Rook Vision\"",
        panelBlock.TryBody);
    Assert.Contains(
        "Panels.RegisterPanel(this, kgPanelType, \"Knowledge Graph\"",
        panelBlock.TryBody);
    Assert.Contains(
        "TraceStartup($\"Panel registration failed (non-fatal):",
        panelBlock.CatchBody);
    Assert.DoesNotContain("throw", panelBlock.CatchBody);
}
```

- [ ] **Step 2: Add inert `OnLoad` test**

Add this test:

```csharp
[Fact]
public void OnLoad_IsMinimalAndDoesNotStartRuntimeWork()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");

    Assert.Contains("TraceStartup(\"OnLoad minimal\");", onLoad);
    Assert.Contains("AttachStartupGateHooks();", onLoad);
    Assert.Contains("return LoadReturnCode.Success;", onLoad);

    Assert.DoesNotContain("RegisterStartupPanels();", onLoad);
    Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", onLoad);
    Assert.DoesNotContain("BeginStartupRetries();", onLoad);
    Assert.DoesNotContain("TryInitializeRuntime();", onLoad);
    Assert.DoesNotContain("NativeGhBridgeRegistrar.TryRegister", onLoad);
    Assert.DoesNotContain("EnsureToolbarLoaded();", onLoad);
    Assert.DoesNotContain("RhinoApp.WriteLine", onLoad);
}
```

- [ ] **Step 3: Update video reconcile startup test**

In `StartupVideoReconcileFailure_IsCaughtAndLoggedAsNonFatal`, remove the assertions that `OnLoad` calls `BeginStartupRetries()` and `RhinoApp.InvokeOnUiThread(...)`. Assert against `RunDeferredCompanionStartup` instead:

```csharp
[Fact]
public void StartupVideoReconcileFailure_IsCaughtAndLoggedAsNonFatal()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
    var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

    Assert.DoesNotContain("BeginStartupRetries();", onLoad);
    Assert.DoesNotContain("RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime));", onLoad);
    Assert.Contains("return LoadReturnCode.Success;", onLoad);

    var reconcileBlock = ExtractTryCatchContaining(
        deferredStartup,
        "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");

    Assert.Contains(
        "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();",
        reconcileBlock.TryBody);
    Assert.Contains(
        "TraceStartup(\"Video subsystem reconciled",
        reconcileBlock.TryBody);
    Assert.Contains(
        "TraceStartup($\"Video reconcile failed (non-fatal):",
        reconcileBlock.CatchBody);
    Assert.Contains(
        "continuing without reconcile",
        reconcileBlock.CatchBody);
    Assert.DoesNotContain("throw", reconcileBlock.CatchBody);
}
```

- [ ] **Step 4: Update sidecar backfill test**

Change `StartupVideoSidecarBackfill_IsScheduledAsSeparateNonFatalAsyncStep` to extract `RunDeferredCompanionStartup` instead of `TryInitializeRuntime`:

```csharp
var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");
```

Then use `deferredStartup` for both `ExtractTryCatchContaining` calls in that test.

- [ ] **Step 5: Add lifecycle hook source test**

Add this test:

```csharp
[Fact]
public void StartupGateHooks_UseIdleAndDocumentOpenLifecycle()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var attach = ExtractMethod(source, "private void AttachStartupGateHooks()");
    var detach = ExtractMethod(source, "private void DetachStartupGateHooks()");

    Assert.Contains("RhinoApp.Idle += OnStartupGateIdle;", attach);
    Assert.Contains("RhinoDoc.BeginOpenDocument += OnBeginOpenDocument;", attach);
    Assert.Contains("RhinoDoc.EndOpenDocument += OnEndOpenDocument;", attach);
    Assert.Contains("RhinoDoc.EndOpenDocumentInitialViewUpdate += OnEndOpenDocumentInitialViewUpdate;", attach);

    Assert.Contains("RhinoApp.Idle -= OnStartupGateIdle;", detach);
    Assert.Contains("RhinoDoc.BeginOpenDocument -= OnBeginOpenDocument;", detach);
    Assert.Contains("RhinoDoc.EndOpenDocument -= OnEndOpenDocument;", detach);
    Assert.Contains("RhinoDoc.EndOpenDocumentInitialViewUpdate -= OnEndOpenDocumentInitialViewUpdate;", detach);
}
```

- [ ] **Step 6: Run source tests and confirm expected failure**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RookPluginLifecycleSourceTests
```

Expected: fails because `RookPlugin.cs` still has old startup behavior and lacks the new methods.

Do not commit this task yet. Commit after Task 3 makes tests pass.

- [ ] **Step 7: Add constructor old-path source guard**

Add this test:

```csharp
[Fact]
public void Constructor_DoesNotSubscribeStartupIdleHandlers()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var constructor = ExtractMethod(source, "public RookPlugin()");

    Assert.DoesNotContain("RhinoApp.Idle +=", constructor);
    Assert.DoesNotContain("OnRhinoIdle", source);
    Assert.DoesNotContain("EnsureNativeGhBridgeRegistered", source);
    Assert.DoesNotContain("BeginStartupRetries", source);
    Assert.DoesNotContain("ScheduleNextStartupRetry", source);
    Assert.DoesNotContain("new Timer", source);
}
```

## Task 3: Wire `RookPlugin` To Idle-Gated Startup

**Files:**
- Modify: `src/Rook/RookPlugin.cs`
- Modify: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs` if signatures need minor alignment

- [ ] **Step 1: Add using directives and fields**

In `src/Rook/RookPlugin.cs`, add:

```csharp
using Rhino.Commands;
using Rook.Startup;
```

Replace timer retry fields:

```csharp
private const int StartupRetryIntervalMs = 250;
private const int StartupRetryLimit = 120;
private Timer? _startupRetryTimer;
private bool _startupRetriesActive = false;
```

with:

```csharp
private const int BridgeRetryLimit = 120;
private readonly CompanionStartupGate _startupGate =
    new(requiredStableIdleTicks: 2);
private int _startupRunInProgress = 0;
private int _bridgeRetryCount = 0;
private bool _documentOpening = false;
private bool _documentOpenInitialViewReady = false;
private bool _startupHooksAttached = false;
private bool _shutdownStarted = false;
private bool _deferredLocalStartupComplete = false;
private string? _lastStartupGateTraceKey;
private int _lastStartupGateTraceRepeatCount = 0;
```

Keep `_startupRetryCount` only if used for trace compatibility; otherwise remove it in this task.

- [ ] **Step 2: Make constructor inert**

Change the constructor from:

```csharp
public RookPlugin()
{
    _instance = this;
    TraceStartup("constructor");
    RhinoApp.Idle += OnRhinoIdle;
    RhinoApp.Idle += EnsureNativeGhBridgeRegistered;
}
```

to:

```csharp
public RookPlugin()
{
    _instance = this;
    TraceStartup("constructor");
}
```

- [ ] **Step 3: Replace idle methods**

Remove `OnRhinoIdle`, `EnsureNativeGhBridgeRegistered`, `BeginStartupRetries`, `StopStartupRetries`, and `ScheduleNextStartupRetry`.

Add:

```csharp
private void AttachStartupGateHooks()
{
    if (_startupHooksAttached)
    {
        return;
    }

    RhinoApp.Idle += OnStartupGateIdle;
    RhinoDoc.BeginOpenDocument += OnBeginOpenDocument;
    RhinoDoc.EndOpenDocument += OnEndOpenDocument;
    RhinoDoc.EndOpenDocumentInitialViewUpdate += OnEndOpenDocumentInitialViewUpdate;
    _startupHooksAttached = true;
}

private void DetachStartupGateHooks()
{
    if (!_startupHooksAttached)
    {
        return;
    }

    RhinoApp.Idle -= OnStartupGateIdle;
    RhinoDoc.BeginOpenDocument -= OnBeginOpenDocument;
    RhinoDoc.EndOpenDocument -= OnEndOpenDocument;
    RhinoDoc.EndOpenDocumentInitialViewUpdate -= OnEndOpenDocumentInitialViewUpdate;
    _startupHooksAttached = false;
    TraceStartup("StartupGate hooks detached");
}

private void OnBeginOpenDocument(object? sender, DocumentOpenEventArgs e)
{
    _documentOpening = true;
    _documentOpenInitialViewReady = false;
    TraceStartupThrottled("document-open-begin", "StartupGate document open begin");
}

private void OnEndOpenDocument(object? sender, DocumentOpenEventArgs e)
{
    _documentOpening = false;
    _documentOpenInitialViewReady = false;
    TraceStartupThrottled("document-open-end", "StartupGate document open end");
}

private void OnEndOpenDocumentInitialViewUpdate(object? sender, DocumentOpenEventArgs e)
{
    _documentOpening = false;
    _documentOpenInitialViewReady = true;
    TraceStartupThrottled("document-open-initial-view", "StartupGate document open initial view update");
}
```

RhinoCommon XML on this machine confirms `Rhino.DocumentOpenEventArgs` for these document-open events and confirms `RhinoDoc.EndOpenDocumentInitialViewUpdate` exists. Do not substitute guessed document-open APIs.

- [ ] **Step 4: Replace `OnLoad` body**

Change `OnLoad` so it traces and attaches hooks only:

```csharp
protected override LoadReturnCode OnLoad(ref string errorMessage)
{
    TraceStartup("OnLoad minimal");

    _isRhinoInside = Rhino.Runtime.HostUtils.RunningAsRhinoInside;
    AttachStartupGateHooks();

    return LoadReturnCode.Success;
}
```

Do not call `RhinoApp.WriteLine` from `OnLoad`.

- [ ] **Step 5: Add idle gate callback**

Add:

```csharp
private void OnStartupGateIdle(object? sender, EventArgs e)
{
    var snapshot = new CompanionStartupGateSnapshot(
        CommandActive: IsRhinoCommandActive(),
        DocumentOpening: IsDocumentOpenLifecycleBlocking(),
        ShutdownStarted: _shutdownStarted);
    var decision = _startupGate.EvaluateIdle(snapshot);

    TraceStartupGateDecision(snapshot, decision);

    if (decision.Action != CompanionStartupGateAction.RunStartup)
    {
        return;
    }

    RunDeferredStartupFromIdle();
}
```

- [ ] **Step 6: Add conservative command-state probe**

Add:

```csharp
private static bool IsRhinoCommandActive()
{
    try
    {
        if (RhinoApp.InCommand > 0)
        {
            return true;
        }
    }
    catch
    {
        return true;
    }

    try
    {
        if (RhinoDoc.ActiveDoc?.IsCommandRunning == true)
        {
            return true;
        }
    }
    catch
    {
        return true;
    }

    try
    {
        if (Command.InCommand())
        {
            return true;
        }
    }
    catch
    {
        return true;
    }

    return false;
}
```

If `Command.InCommand()` does not compile as a `bool`, remove that third probe and rely on `RhinoApp.InCommand` plus `RhinoDoc.IsCommandRunning`; do not guess another signature.

- [ ] **Step 7: Add conservative document-open blocker**

Add:

```csharp
private bool IsDocumentOpenLifecycleBlocking()
{
    if (_documentOpening)
    {
        return true;
    }

    // If this plugin loaded after BeginOpenDocument already fired, we may
    // never see the begin event. While Rhino still reports a command active,
    // avoid assuming the document-open lifecycle is stable.
    if (!_documentOpenInitialViewReady && IsRhinoCommandActive())
    {
        return true;
    }

    return false;
}
```

This is deliberately conservative for startup recent-file `_Open`: command-active plus no observed initial view update blocks startup even if `BeginOpenDocument` was missed.

- [ ] **Step 8: Add throttled trace helpers**

Add:

```csharp
private void TraceStartupGateDecision(
    CompanionStartupGateSnapshot snapshot,
    CompanionStartupGateDecision decision)
{
    var key =
        $"blocked={decision.BlockedReason};action={decision.Action};" +
        $"command={snapshot.CommandActive};docOpen={snapshot.DocumentOpening};" +
        $"stable={decision.StableIdleCount}";
    var message =
        $"StartupGate idle attempt: commandActive={snapshot.CommandActive} " +
        $"documentOpening={snapshot.DocumentOpening} " +
        $"stableIdleCount={decision.StableIdleCount} " +
        $"blockedReason={decision.BlockedReason} action={decision.Action}";
    TraceStartupThrottled(key, message);
}

private void TraceStartupThrottled(string key, string message)
{
    if (!string.Equals(_lastStartupGateTraceKey, key, StringComparison.Ordinal))
    {
        _lastStartupGateTraceKey = key;
        _lastStartupGateTraceRepeatCount = 0;
        TraceStartup(message);
        return;
    }

    _lastStartupGateTraceRepeatCount++;
    if (_lastStartupGateTraceRepeatCount % 25 == 0)
    {
        TraceStartup(message + $" repeat={_lastStartupGateTraceRepeatCount}");
    }
}
```

- [ ] **Step 9: Move startup side effects into deferred startup**

Rename `TryInitializeRuntime` to `RunDeferredCompanionStartup` and change its signature to:

```csharp
private bool RunDeferredCompanionStartup()
```

At the beginning of the method, ensure local startup runs once before bridge registration. Local startup includes panel registration, toolbar/runtime state, image/video reconcile, and sidecar backfill. These are delayed until quiescence, but they are not blocked by bridge registration failure.

```csharp
if (!_deferredLocalStartupComplete)
{
    if (ShouldRegisterStartupPanels(_isRhinoInside))
    {
        RegisterStartupPanels();
    }
    else
    {
        TraceStartup("Rhino.Inside mode: startup panel registration skipped");
    }

    if (!_serverStarted)
    {
        _serverStarted = true;
        if (!_isRhinoInside)
        {
            EnsureToolbarLoaded();
        }
        TraceStartup("Companion UI/runtime startup complete; HTTP server delegated to RookNative");
    }

    try
    {
        RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();
        TraceStartup("Video subsystem reconciled (or no-op if never used previously)");
    }
    catch (Exception ex)
    {
        TraceStartup($"Video reconcile failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
        RhinoApp.WriteLine(
            "Rook: video reconcile failed at startup; continuing without reconcile. " +
            $"Reason: {ex.GetType().Name}.");
    }

    try
    {
        RookSubsystemRoot.Instance.ReconcileImageJobsOnce();
        TraceStartup("Image job subsystem reconciled (or no-op)");
    }
    catch (Exception ex)
    {
        TraceStartup($"Image job reconcile failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
        RhinoApp.WriteLine(
            "Rook: image job reconcile failed at startup; continuing without reconcile. " +
            $"Reason: {ex.GetType().Name}.");
    }

    try
    {
        RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(
            new VideoSidecarBackfillStartupOptions(
                Enabled: true,
                ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
                OnCompleted: result =>
                    TraceStartup($"Video sidecar backfill completed: {result.ToTraceSummary()}"),
                OnFailed: ex =>
                    TraceStartup($"Video sidecar backfill failed (non-fatal): {ex.GetType().Name}: {ex.Message}")));
        TraceStartup("Video sidecar backfill scheduled (or no-op if already scheduled)");
    }
    catch (Exception ex)
    {
        TraceStartup($"Video sidecar backfill scheduling failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
        RhinoApp.WriteLine(
            "Rook: video sidecar backfill could not be scheduled at startup; continuing. " +
            $"Reason: {ex.GetType().Name}.");
    }

    _deferredLocalStartupComplete = true;
}
```

Then attempt bridge registration:

```csharp
var nativeBridgeRegistered = NativeGhBridgeRegistrar.TryRegister();
TraceStartup($"Deferred startup bridgeRegistered={nativeBridgeRegistered} bridgeRetryCount={_bridgeRetryCount}");
if (!nativeBridgeRegistered)
{
    _bridgeRetryCount++;
    if (_bridgeRetryCount >= BridgeRetryLimit)
    {
        TraceStartup("Startup bridge retries exhausted; bridge-dependent features unavailable.");
        DetachStartupGateHooks();
        return true;
    }

    _startupGate.MarkStartupAvailableForRetry();
    return false;
}
```

Remove the old duplicate video reconcile, image reconcile, and sidecar backfill blocks from after bridge registration. Those local startup steps now run before bridge registration and exactly once after quiescence.

After bridge registration succeeds, end with:

```csharp
TraceStartup("Startup complete");
return true;
```

- [ ] **Step 10: Add guarded startup runner**

Add:

```csharp
private void RunDeferredStartupFromIdle()
{
    if (Interlocked.Exchange(ref _startupRunInProgress, 1) == 1)
    {
        return;
    }

    try
    {
        TraceStartup("StartupGate quiescent: running startup");
        if (RunDeferredCompanionStartup())
        {
            _startupGate.MarkStartupComplete();
            DetachStartupGateHooks();
        }
    }
    finally
    {
        Interlocked.Exchange(ref _startupRunInProgress, 0);
    }
}
```

- [ ] **Step 11: Update shutdown**

In `OnShutdown`, replace:

```csharp
RhinoApp.Idle -= OnRhinoIdle;
RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
StopStartupRetries();
```

with:

```csharp
_shutdownStarted = true;
DetachStartupGateHooks();
```

Keep existing bridge clear, chat shutdown, video dispose, and `base.OnShutdown()` behavior unchanged.

- [ ] **Step 12: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CompanionStartupGateTests|FullyQualifiedName~RookPluginLifecycleSourceTests"
```

Expected: all focused startup lifecycle tests pass. If `Command.InCommand()` does not compile as a boolean probe, remove that one probe and rely on `RhinoApp.InCommand` plus `RhinoDoc.IsCommandRunning`; do not guess another command-state API.

- [ ] **Step 13: Commit Tasks 2-3**

```powershell
git add src\Rook\RookPlugin.cs src\Rook.Tests\Plugin\RookPluginLifecycleSourceTests.cs
git commit -m "fix: gate managed companion startup on stable idle"
```

## Task 4: Bridge Readiness And Source Guard Tests

**Files:**
- Modify: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`
- Modify: `src/Rook/RookPlugin.cs` only if Task 3 missed a source contract

- [ ] **Step 1: Add source guard for removed timer retry**

Add:

```csharp
[Fact]
public void StartupRetryTimer_IsRemovedFromManagedCompanionStartup()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");

    Assert.DoesNotContain("new Timer", source);
    Assert.DoesNotContain("_startupRetryTimer", source);
    Assert.DoesNotContain("StartupRetryIntervalMs", source);
    Assert.DoesNotContain("ScheduleNextStartupRetry", source);
}
```

- [ ] **Step 2: Add bridge retry source guard**

Add:

```csharp
[Fact]
public void BridgeUnavailableAfterQuiescence_RetriesThroughIdleOnly()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

    Assert.Contains("NativeGhBridgeRegistrar.TryRegister();", deferredStartup);
    Assert.Contains("_startupGate.MarkStartupAvailableForRetry();", deferredStartup);
    Assert.Contains("BridgeRetryLimit", source);
    Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", deferredStartup);
    Assert.DoesNotContain("new Timer", deferredStartup);
}
```

- [ ] **Step 3: Add local startup source guard**

Add:

```csharp
[Fact]
public void BridgeRetryExhausted_DoesNotSuppressDeferredUiStartup()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

    var localStartupIndex = deferredStartup.IndexOf(
        "_deferredLocalStartupComplete = true;",
        StringComparison.Ordinal);
    var bridgeIndex = deferredStartup.IndexOf(
        "NativeGhBridgeRegistrar.TryRegister();",
        StringComparison.Ordinal);
    var exhaustionIndex = deferredStartup.IndexOf(
        "Startup bridge retries exhausted",
        StringComparison.Ordinal);

    Assert.True(localStartupIndex >= 0, "Deferred local startup completion must be present.");
    Assert.True(bridgeIndex > localStartupIndex, "Bridge registration must run after local startup.");
    Assert.True(exhaustionIndex > bridgeIndex, "Bridge exhaustion must happen after bridge retry attempts.");
}
```

- [ ] **Step 4: Add local reconcile ordering source guard**

Add:

```csharp
[Fact]
public void LocalReconcileAndBackfill_RunBeforeBridgeRegistration()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

    var videoIndex = deferredStartup.IndexOf(
        "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();",
        StringComparison.Ordinal);
    var imageIndex = deferredStartup.IndexOf(
        "RookSubsystemRoot.Instance.ReconcileImageJobsOnce();",
        StringComparison.Ordinal);
    var backfillIndex = deferredStartup.IndexOf(
        "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(",
        StringComparison.Ordinal);
    var bridgeIndex = deferredStartup.IndexOf(
        "NativeGhBridgeRegistrar.TryRegister();",
        StringComparison.Ordinal);

    Assert.True(videoIndex >= 0, "Video reconcile must still run after quiescence.");
    Assert.True(imageIndex >= 0, "Image reconcile must still run after quiescence.");
    Assert.True(backfillIndex >= 0, "Video sidecar backfill must still be scheduled after quiescence.");
    Assert.True(bridgeIndex > videoIndex, "Bridge registration must not block video reconcile.");
    Assert.True(bridgeIndex > imageIndex, "Bridge registration must not block image reconcile.");
    Assert.True(bridgeIndex > backfillIndex, "Bridge registration must not block sidecar backfill.");
}
```

- [ ] **Step 5: Run plugin tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RookPluginLifecycleSourceTests
```

Expected: all `RookPluginLifecycleSourceTests` pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add src\Rook.Tests\Plugin\RookPluginLifecycleSourceTests.cs src\Rook\RookPlugin.cs
git commit -m "test: lock managed startup quiescence contract"
```

## Task 5: Native Bridge Status Review Checkpoint

**Files:**
- Optional modify: `src/RookNative/RookNativePlugin.cpp`

Do this task after Task 3 compiles. Do not change native dispatcher behavior.

- [ ] **Step 1: Inspect current native bridge wait message**

Open `src/RookNative/RookNativePlugin.cpp` and find:

```cpp
L"RookNative: managed companion loaded but GH bridge did not register.\n"
```

- [ ] **Step 2: Decide whether to amend message now**

If managed startup defers bridge registration beyond native's existing `kBridgeRetries * kBridgePollMs` window during live validation, change only the message to:

```cpp
RhinoApp().Print(
    L"RookNative: managed companion loaded; GH bridge is not registered yet.\n"
    L"  Bridge-dependent routes will report unavailable until managed startup reaches idle.\n");
```

If live validation shows no misleading native message, leave native untouched and record that in the PR description.

- [ ] **Step 3: If native message changed, build native**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds.

- [ ] **Step 4: If native message changed, commit**

```powershell
git add src\RookNative\RookNativePlugin.cpp
git commit -m "chore: clarify deferred bridge readiness message"
```

## Task 6: Full Automated Verification

**Files:**
- No edits expected.

- [ ] **Step 1: Run focused startup tests**

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CompanionStartupGateTests|FullyQualifiedName~RookPluginLifecycleSourceTests"
```

Expected: all focused tests pass.

- [ ] **Step 2: Run full managed suite**

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore
```

Expected: all tests pass. Existing warnings are acceptable; failures are not.

- [ ] **Step 3: Run diff check**

```powershell
git diff --check origin/main...HEAD
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Inspect diff scope**

```powershell
git diff --name-only origin/main...HEAD
```

Expected files should be limited to:

```text
docs/superpowers/specs/2026-05-26-managed-companion-startup-quiescence-design.md
docs/superpowers/plans/2026-05-26-managed-companion-startup-quiescence.md
src/Rook/Startup/CompanionStartupGate.cs
src/Rook/RookPlugin.cs
src/Rook.Tests/Plugin/CompanionStartupGateTests.cs
src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs
src/RookNative/RookNativePlugin.cpp   # only if Task 5 amended message
```

## Task 7: Local Deploy And Live Validation

**Files:**
- No edits expected unless live validation finds a bug.

- [ ] **Step 1: Ensure registry is restored and Rhino is closed**

Check:

```powershell
Get-Process Rhino -ErrorAction SilentlyContinue
Test-Path "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b"
Test-Path "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\a38e0e8f-e06e-40d2-a6bd-7edbc2cb1906"
```

Expected: no Rhino processes; both registry keys return `True`.

- [ ] **Step 2: Deploy managed companion for local testing**

Use the repo's local deploy path. If using the Rook deploy skill, make sure it builds/deploys the managed companion from this worktree. If running manually:

```powershell
dotnet build .\src\Rook\Rook.csproj -c Release -f net8.0
dotnet build .\src\Rook\Rook.csproj -c Release -f net7.0
dotnet build .\src\Rook\Rook.csproj -c Release -f net48
```

Expected: managed `Rook.rhp` is deployed to the installed Rhino plugin runtime folders by the project `DeployToRhino` target.

- [ ] **Step 3: Clear startup trace for clean evidence**

```powershell
$tempLog = Join-Path $env:TEMP "rook\companion-startup.log"
if (Test-Path $tempLog) {
  Rename-Item $tempLog ("companion-startup.before-quiescence-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
}
```

- [ ] **Step 4: Live recent-file `_Open` validation**

Manual steps:

1. Launch Rhino.
2. Immediately click a recent file from Rhino's startup/recent-files screen.
3. Do not interact with Rook panels during `_Open`.
4. Confirm Rhino does not wedge.
5. Wait for document open to complete.
6. Confirm Rook companion startup eventually completes.

Expected:

```text
Rhino remains responsive
_Open completes
companion-startup.log shows OnLoad minimal before startup completion
StartupGate waits until idle/quiescent
Startup complete appears after _Open/document startup
```

- [ ] **Step 5: Post-open functional checks**

After the document opens:

```text
Rook panels are available from Rhino UI
RookNative discovery JSON exists while Rhino is open
MCP rhino_ping returns pong
GH/bridge-dependent route reports available after startup complete
```

- [ ] **Step 6: Repeat**

Repeat the startup recent-file path at least 3 times. If any run wedges Rhino, stop and collect:

```powershell
Get-Content "$env:TEMP\rook\companion-startup.log" -Tail 120
Get-ChildItem "$env:TEMP\rook" | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-ChildItem "$env:LOCALAPPDATA\Rook\discovery" | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-ChildItem "$env:APPDATA\Rook\sessions" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

Do not continue to Vision validation until this gate passes.

## Task 8: PR Preparation

**Files:**
- No edits expected except PR description.

- [ ] **Step 1: Final status**

```powershell
git status --short --branch
```

Expected: clean worktree.

- [ ] **Step 2: Push branch**

```powershell
git push -u origin codex/managed-companion-startup-quiescence
```

- [ ] **Step 3: Open draft PR**

Open as draft. PR title:

```text
Fix managed companion startup quiescence during Rhino startup open
```

PR body must state:

```text
This is not a Vision dark-panel PR.
This fixes the proven startup-open boundary:
RookNative alone did not wedge; RookNative + managed companion load did.
OnLoad is now inert; startup waits for stable idle/quiescence.
Live recent-file _Open validation is required before marking ready.
```

Include validation evidence:

```text
Focused startup tests: <result>
Full managed suite: <result>
git diff --check: passed
Live recent-file _Open repeated runs: <result after validation>
```

Keep PR draft until live validation passes.
