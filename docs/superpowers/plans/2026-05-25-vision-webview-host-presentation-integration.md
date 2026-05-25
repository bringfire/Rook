# Vision WebView Host Presentation Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the WebView host presentation coordinator into the Vision panel only, with memory-only evidence capture and an explicit dump command.

**Architecture:** `VisionWebSurface` opts into the new coordinator path by code; Chat and Knowledge Graph keep the existing `WebViewHostVisibilityCoordinator` path. The panel layer supplies explicit presentation facts, `RookWebSurface` builds fresh execution-time WebView/Eto/HWND/controller snapshots inside one serialized UI callback, and a Vision-only in-memory ring records decisions without hot-path file I/O.

**Tech Stack:** C# net48, RhinoCommon commands/panels, Eto WebView, WebView2 via existing reflection helpers, xUnit.

---

## Hard Scope Constraints

These constraints are release-critical for PR #192:

```text
No env vars.
No Vision UI changes.
No JS probes.
No hot-path file logging.
No runtime opt-out switch.
No polling loop.
No WebView reload/re-navigation as normal recovery.
Chat/KG old path unchanged.
Snapshot built inside the serialized UI callback.
One coordinator evaluation at a time per Vision surface.
```

If implementation pressure pushes against any of these constraints, stop and ask for review rather than adding a workaround.

---

## File Structure

- Create `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`: plain panel-derived facts consumed by coordinator-enabled WebView surfaces.
- Create `src/Rook/UI/Web/WebViewHostPresentationRecorder.cs`: small recorder interface and immutable DTO for memory-only presentation entries.
- Create `src/Rook/UI/Vision/VisionPresentationStateStore.cs`: Vision-only fixed-size ring and dump serialization helper.
- Modify `src/Rook/UI/Web/RookWebSurface.cs`: add opt-in policy, facts overload, coordinator scheduling path, execution-time snapshot builder, action sink, and recorder hook. Preserve the old bool path for non-coordinator surfaces.
- Modify `src/Rook/UI/Vision/VisionWebSurface.cs`: opt into coordinator path and provide the Vision presentation recorder.
- Modify `src/Rook/UI/Vision/RookVisionPanel.cs`: use the facts overload and map hosted lifecycle decisions to explicit panel facts.
- Modify `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`: add a facts-aware `Reconcile` overload that passes the already-captured `PanelLifecycleFacts` to callers.
- Modify `src/Rook/UI/Panels/HostedPanelLifecycleTypes.cs`: expose `PanelLifecycleFacts` on `HostedSurfaceDecision` if needed by the facts-aware overload.
- Create `src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs`: explicit Rhino command to dump the Vision ring to `%TEMP%\rook`.
- Add or modify tests:
  - `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`
  - `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
  - `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`
  - `src/Rook.Tests/UI/Vision/VisionPresentationStateStoreTests.cs`
  - `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs` or command-focused equivalent for the dump command.

No `.csproj` changes are expected; SDK-style globbing should include new C# files.

---

### Task 1: Add Panel Facts And Opt-In Policy

**Files:**
- Create: `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Test: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
- Test: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`

- [ ] **Step 1: Write policy/facts tests**

Add these tests.

In `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`:

```csharp
[Fact]
public void VisionWebSurface_OptsIntoHostPresentationCoordinator()
{
    using var surface = NewSurface();

    Assert.True(surface.UsesHostPresentationCoordinatorForTest);
}
```

In `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`, inside `DefaultSurface` add:

```csharp
public bool UsesCoordinatorForTest => UsesHostPresentationCoordinatorForTest;
```

Then add:

```csharp
[Fact]
public void RookWebSurface_Default_DoesNotUseHostPresentationCoordinator()
{
    var surface = new DefaultSurface();

    Assert.False(surface.UsesCoordinatorForTest);
}

[Fact]
public void HostPresentationCoordinatorPolicy_IsNotEnvironmentControlled()
{
    var previous = Environment.GetEnvironmentVariable("ROOK_USE_HOST_PRESENTATION_COORDINATOR");
    try
    {
        Environment.SetEnvironmentVariable("ROOK_USE_HOST_PRESENTATION_COORDINATOR", "1");
        Assert.False(new DefaultSurface().UsesCoordinatorForTest);
    }
    finally
    {
        Environment.SetEnvironmentVariable("ROOK_USE_HOST_PRESENTATION_COORDINATOR", previous);
    }
}
```

In `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs` add:

```csharp
[Fact]
public void VisionWebSurface_UsesCodeOptIn_NotEnvironmentFlag()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");

    Assert.Contains("UseHostPresentationCoordinator", source);
    Assert.DoesNotContain("GetEnvironmentVariable", source);
    Assert.DoesNotContain("ROOK_USE_HOST_PRESENTATION_COORDINATOR", source);
}
```

- [ ] **Step 2: Run focused tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionWebSurface_OptsIntoHostPresentationCoordinator|FullyQualifiedName~RookWebSurface_Default_DoesNotUseHostPresentationCoordinator|FullyQualifiedName~HostPresentationCoordinatorPolicy_IsNotEnvironmentControlled|FullyQualifiedName~VisionWebSurface_UsesCodeOptIn_NotEnvironmentFlag"
```

Expected: compile failure for missing `UsesHostPresentationCoordinatorForTest` and missing opt-in override.

- [ ] **Step 3: Add panel facts type**

Create `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`:

```csharp
namespace Rook.UI.Web
{
    internal sealed record WebViewHostPanelPresentationFacts
    {
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; }
        public bool PanelSelectedVisible { get; init; }
        public string Reason { get; init; } = string.Empty;
    }
}
```

- [ ] **Step 4: Add the internal opt-in seam**

In `src/Rook/UI/Web/RookWebSurface.cs`, inside `RookWebSurface`, add:

```csharp
protected virtual bool UseHostPresentationCoordinator => false;

internal bool UsesHostPresentationCoordinatorForTest => UseHostPresentationCoordinator;
```

Do not read environment variables or settings.

- [ ] **Step 5: Opt Vision in by code**

In `src/Rook/UI/Vision/VisionWebSurface.cs`, inside `VisionWebSurface`, add:

```csharp
protected override bool UseHostPresentationCoordinator => true;
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionWebSurface_OptsIntoHostPresentationCoordinator|FullyQualifiedName~RookWebSurface_Default_DoesNotUseHostPresentationCoordinator|FullyQualifiedName~HostPresentationCoordinatorPolicy_IsNotEnvironmentControlled|FullyQualifiedName~VisionWebSurface_UsesCodeOptIn_NotEnvironmentFlag"
```

Expected: tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add .\src\Rook\UI\Web\WebViewHostPanelPresentationFacts.cs `
  .\src\Rook\UI\Web\RookWebSurface.cs `
  .\src\Rook\UI\Vision\VisionWebSurface.cs `
  .\src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs `
  .\src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs `
  .\src\Rook.Tests\UI\Vision\RookVisionPanelHostTests.cs
git commit -m "feat: opt vision into webview presentation coordinator"
```

---

### Task 2: Add Facts-Aware Vision Panel Flow

**Files:**
- Modify: `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`
- Modify: `src/Rook/UI/Panels/HostedPanelLifecycleTypes.cs`
- Modify: `src/Rook/UI/Vision/RookVisionPanel.cs`
- Test: `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`
- Test: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`

- [ ] **Step 1: Write tests for facts propagation**

In `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`, add a test that uses the new facts-aware overload:

```csharp
[Fact]
public void ReconcileFactsOverload_PassesCapturedLifecycleFacts()
{
    var visibility = new FakeVisibilityQuery { SelectedVisible = true };
    var adapter = new HostedPanelLifecycleAdapter(
        typeof(Rook.UI.Vision.RookVisionPanel),
        visibility,
        (_, action) => action());
    adapter.PanelShown(123, Rhino.UI.ShowPanelReason.Show);

    PanelLifecycleFacts? capturedFacts = null;
    HostedSurfaceDecision? capturedDecision = null;
    adapter.ReconcileForTest(
        "surface",
        isSelectedTab: true,
        isHostReady: true,
        (decision, facts) =>
        {
            capturedDecision = decision;
            capturedFacts = facts;
        });

    Assert.NotNull(capturedDecision);
    Assert.NotNull(capturedFacts);
    Assert.True(capturedFacts!.PanelReportedVisible);
    Assert.Equal(HostedPanelLifecycleReason.Show, capturedFacts.LastReason);
    Assert.True(capturedFacts.IsSelectedTab);
    Assert.True(capturedFacts.IsRhinoSelectedPanelVisible);
    Assert.True(capturedFacts.IsHostReady);
}
```

If the file already has a `FakeVisibilityQuery`, reuse it. If not, add this helper in the test class:

```csharp
private sealed class FakeVisibilityQuery : IRhinoPanelVisibilityQuery
{
    public bool SelectedVisible { get; init; } = true;
    public bool IsSelectedPanelVisible(Type panelType) => SelectedVisible;
}
```

In `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`, add source guards:

```csharp
[Fact]
public void RookVisionPanel_UsesPresentationFactsOverload()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("WebViewHostPanelPresentationFacts", source);
    Assert.Contains("ReconcileHostVisibility(BuildPresentationFacts", source);
    Assert.DoesNotContain("_surface.ReconcileHostVisibility(true, sourceReason", source);
    Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, sourceReason", source);
}

[Fact]
public void RookVisionPanel_TemporaryDeactivateKeepsDesiredVisible()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("TemporaryDeactivateHidden", source);
    Assert.Contains("DesiredVisible = !durableHidden", source);
}
```

- [ ] **Step 2: Run focused tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ReconcileFactsOverload_PassesCapturedLifecycleFacts|FullyQualifiedName~RookVisionPanel_UsesPresentationFactsOverload|FullyQualifiedName~RookVisionPanel_TemporaryDeactivateKeepsDesiredVisible"
```

Expected: compile/source failures because the facts overload and Vision mapping do not exist.

- [ ] **Step 3: Add facts-aware overloads to `HostedPanelLifecycleAdapter`**

Add public/internal overloads without changing the existing `Action<HostedSurfaceDecision>` path:

```csharp
public void Reconcile(
    string surfaceId,
    bool isSelectedTab,
    Control hostControl,
    Action<HostedSurfaceDecision, PanelLifecycleFacts> apply)
{
    if (hostControl == null)
    {
        throw new ArgumentNullException(nameof(hostControl));
    }

    ReconcileCore(
        surfaceId,
        isSelectedTab,
        () => CaptureHostReadiness(hostControl),
        apply,
        eventName: "Reconcile");
}

internal void ReconcileForTest(
    string surfaceId,
    bool isSelectedTab,
    bool isHostReady,
    Action<HostedSurfaceDecision, PanelLifecycleFacts> apply)
{
    ReconcileCore(
        surfaceId,
        isSelectedTab,
        () => HostReadiness.ForTest(isHostReady),
        apply,
        eventName: "ReconcileForTest");
}
```

Change the existing single-argument paths to wrap the new core:

```csharp
public void Reconcile(
    string surfaceId,
    bool isSelectedTab,
    Control hostControl,
    Action<HostedSurfaceDecision> apply)
{
    Reconcile(surfaceId, isSelectedTab, hostControl, (decision, _) => apply(decision));
}
```

Update `ReconcileCore` signature to:

```csharp
private void ReconcileCore(
    string surfaceId,
    bool isSelectedTab,
    Func<HostReadiness> readinessProvider,
    Action<HostedSurfaceDecision, PanelLifecycleFacts> apply,
    string eventName)
```

Inside `ReconcileCore`, invoke:

```csharp
apply(decision, facts);
```

Update `SurfaceState.LastApply` to:

```csharp
public Action<HostedSurfaceDecision, PanelLifecycleFacts>? LastApply { get; set; }
```

No existing caller should change except Vision in the next step.

- [ ] **Step 4: Map Vision panel lifecycle facts to WebView presentation facts**

In `src/Rook/UI/Vision/RookVisionPanel.cs`, add `using Rook.UI.Web;`.

Change `ReconcileSurface` to use the facts-aware overload:

```csharp
private void ReconcileSurface(string reason)
{
    _lifecycle.Reconcile(
        _surfaceId,
        isSelectedTab: true,
        this,
        (decision, facts) => ApplyDecision(decision, facts, reason));
}
```

Change `ApplyDecision`:

```csharp
private void ApplyDecision(
    HostedSurfaceDecision decision,
    PanelLifecycleFacts facts,
    string sourceReason)
{
    switch (decision.Action)
    {
        case HostedSurfaceAction.Show:
        case HostedSurfaceAction.Hide:
        case HostedSurfaceAction.Defer:
        case HostedSurfaceAction.None:
            _surface.ReconcileHostVisibility(
                BuildPresentationFacts(decision, facts, sourceReason));
            break;
        case HostedSurfaceAction.Close:
            _surface.ReconcileHostVisibility(
                BuildPresentationFacts(decision, facts, sourceReason));
            CloseSurface();
            break;
    }
}
```

Add the mapper:

```csharp
private static WebViewHostPanelPresentationFacts BuildPresentationFacts(
    HostedSurfaceDecision decision,
    PanelLifecycleFacts facts,
    string sourceReason)
{
    var durableHidden =
        decision.Action == HostedSurfaceAction.Close ||
        (decision.Action == HostedSurfaceAction.Hide &&
         string.Equals(decision.Reason, "panel-hidden", StringComparison.Ordinal));
    var temporaryDeactivateHidden =
        facts.LastReason == HostedPanelLifecycleReason.HideOnDeactivate &&
        !Application.Instance.IsActive;

    return new WebViewHostPanelPresentationFacts
    {
        DesiredVisible = !durableHidden,
        AppActive = Application.Instance.IsActive,
        TemporaryDeactivateHidden = temporaryDeactivateHidden,
        PanelVisible = facts.PanelReportedVisible,
        RequiresSelectedPanel = true,
        PanelSelectedVisible = facts.IsSelectedTab && facts.IsRhinoSelectedPanelVisible,
        Reason = sourceReason + ":" + decision.Reason
    };
}
```

Do not change Chat or Knowledge Graph panel behavior.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~HostedPanelLifecycleAdapterTests|FullyQualifiedName~RookVisionPanelHostTests"
```

Expected: focused panel and Vision host tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add .\src\Rook\UI\Panels\HostedPanelLifecycleAdapter.cs `
  .\src\Rook\UI\Vision\RookVisionPanel.cs `
  .\src\Rook.Tests\UI\Panels\HostedPanelLifecycleAdapterTests.cs `
  .\src\Rook.Tests\UI\Vision\RookVisionPanelHostTests.cs
git commit -m "feat: pass vision presentation facts to web surface"
```

---

### Task 3: Add Coordinator Scheduling Path In `RookWebSurface`

**Files:**
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Test: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`

- [ ] **Step 1: Add source-level contract tests**

In `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`, add source guards:

```csharp
[Fact]
public void CoordinatorPath_HasFactsOverloadAndKeepsBoolCompatibilityOverload()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.Contains("ReconcileHostVisibility(WebViewHostPanelPresentationFacts facts)", source);
    Assert.Contains("ReconcileHostVisibility(bool visible, string reason)", source);
}

[Fact]
public void CoordinatorPath_BuildsSnapshotInsideQueuedCallback()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.Contains("RunHostPresentationCoordinatorReconcile", source);
    Assert.Contains("BuildHostPresentationSnapshot", source);
    Assert.True(
        source.IndexOf("RunHostPresentationCoordinatorReconcile", StringComparison.Ordinal) <
        source.IndexOf("BuildHostPresentationSnapshot", StringComparison.Ordinal),
        "snapshot must be built inside the callback/run path, not at request time");
}

[Fact]
public void CoordinatorPath_DoesNotUseEnvironmentFlagsOrFileLogging()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.DoesNotContain("ROOK_USE_HOST_PRESENTATION_COORDINATOR", source);
    Assert.DoesNotContain("File.AppendAllText", ExtractCoordinatorPathSource(source));
    Assert.DoesNotContain("ExecuteScript", ExtractCoordinatorPathSource(source));
}

[Fact]
public void CoordinatorPath_ControllerConfiguredWithoutPanelFacts_DoesNotPresent()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var method = ExtractMethod(source, "RequestHostVisibleRefresh");

    Assert.Contains("_latestPresentationFacts == null", method);
    Assert.Contains("return;", method);
    Assert.DoesNotContain("CreateCompatibilityPresentationFacts(\r\n        visible: true", method);
    Assert.DoesNotContain("CreateCompatibilityPresentationFacts(visible: true", method);
}

[Fact]
public void CoordinatorPath_DisposedEvaluatesTerminalDecision()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.Contains("EvaluateDisposedHostPresentation", source);
    Assert.Contains("Disposed = true", source);
}
```

If `ReadSourceFile` is not present in `RookWebSurfaceTests.cs`, add the same helper used by other source tests:

```csharp
private static string ReadSourceFile(params string[] pathParts)
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir != null)
    {
        var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
        if (File.Exists(candidate))
            return File.ReadAllText(candidate);
        dir = dir.Parent;
    }

    throw new FileNotFoundException(
        "Could not locate source file " + string.Join("/", pathParts));
}
```

Add this conservative extractor for source assertions:

```csharp
private static string ExtractCoordinatorPathSource(string source)
{
    var start = source.IndexOf("RunHostPresentationCoordinatorReconcile", StringComparison.Ordinal);
    if (start < 0)
        return source;
    var end = source.IndexOf("private void RunHostVisibilityReconcile", StringComparison.Ordinal);
    return end > start ? source.Substring(start, end - start) : source.Substring(start);
}

private static string ExtractMethod(string source, string methodName)
{
    var start = source.IndexOf(methodName, StringComparison.Ordinal);
    Assert.True(start >= 0, "Could not find method " + methodName);
    var brace = source.IndexOf('{', start);
    Assert.True(brace >= 0, "Could not find method body for " + methodName);
    var depth = 0;
    for (var i = brace; i < source.Length; i++)
    {
        if (source[i] == '{') depth++;
        if (source[i] == '}') depth--;
        if (depth == 0) return source.Substring(start, i - start + 1);
    }

    throw new InvalidOperationException("Unbalanced method body for " + methodName);
}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CoordinatorPath_"
```

Expected: source tests fail because the new path does not exist.

- [ ] **Step 3: Add coordinator fields under `ROOK_WEBVIEW2`**

In `RookWebSurface.cs`, under the existing `ROOK_WEBVIEW2` fields, add:

```csharp
private readonly WebViewHostPresentationCoordinator _hostPresentation = new();
private WebViewHostPanelPresentationFacts? _latestPresentationFacts;
private WebViewHostPanelPresentationFacts? _queuedPresentationFacts;
private bool _presentationReconcileQueued;
```

- [ ] **Step 4: Add facts overload and route old overload conditionally**

Update `ReconcileHostVisibility(bool visible, string reason)`:

```csharp
internal void ReconcileHostVisibility(bool visible, string reason)
{
#if ROOK_WEBVIEW2
    if (UseHostPresentationCoordinator)
    {
        ReconcileHostVisibility(CreateCompatibilityPresentationFacts(visible, reason));
        return;
    }

    TraceWebViewFocus("host-visibility-reconcile-request", $"{visible};{reason}");
    ScheduleHostVisibilityReconcile(
        _hostVisibility.RecordHostVisibility(visible, reason));
#else
    _ = visible;
    _ = reason;
#endif
}
```

Add the facts overload:

```csharp
internal void ReconcileHostVisibility(WebViewHostPanelPresentationFacts facts)
{
#if ROOK_WEBVIEW2
    if (!UseHostPresentationCoordinator)
    {
        ReconcileHostVisibility(facts.DesiredVisible, facts.Reason);
        return;
    }

    ScheduleHostPresentationCoordinatorReconcile(facts);
#else
    _ = facts;
#endif
}
```

The compatibility method is a fallback only:

```csharp
private static WebViewHostPanelPresentationFacts CreateCompatibilityPresentationFacts(
    bool visible,
    string reason)
{
    return new WebViewHostPanelPresentationFacts
    {
        DesiredVisible = visible,
        AppActive = SafeApplicationActive(),
        TemporaryDeactivateHidden = false,
        PanelVisible = visible,
        RequiresSelectedPanel = false,
        PanelSelectedVisible = true,
        Reason = reason
    };
}
```

- [ ] **Step 5: Add serialized coordinator scheduling**

Add:

```csharp
private void ScheduleHostPresentationCoordinatorReconcile(
    WebViewHostPanelPresentationFacts facts)
{
    if (_disposed || _webView == null)
    {
        _latestPresentationFacts = facts;
        _queuedPresentationFacts = null;
        _presentationReconcileQueued = false;
        EvaluateDisposedHostPresentation(facts, "Disposed:" + facts.Reason);
        return;
    }

    _latestPresentationFacts = facts;
    _queuedPresentationFacts = facts;

    if (_presentationReconcileQueued)
        return;

    _presentationReconcileQueued = true;
    try
    {
        Application.Instance.AsyncInvoke(RunHostPresentationCoordinatorReconcile);
    }
    catch
    {
        _presentationReconcileQueued = false;
        RunHostPresentationCoordinatorReconcile();
    }
}

private void RunHostPresentationCoordinatorReconcile()
{
    var facts = _queuedPresentationFacts ?? _latestPresentationFacts;
    _queuedPresentationFacts = null;
    _presentationReconcileQueued = false;

    if (facts == null)
        return;

    facts = facts with
    {
        AppActive = SafeApplicationActive()
    };

    // Task 4 fills in snapshot/action logic.
}
```

Add a no-action disposed evaluator. Task 5 will record this decision in the in-memory ring; until the recorder exists, it still exercises the coordinator's terminal contract:

```csharp
private void EvaluateDisposedHostPresentation(
    WebViewHostPanelPresentationFacts facts,
    string reason)
{
    var snapshot = new WebViewHostPresentationSnapshot
    {
        DesiredVisible = facts.DesiredVisible,
        AppActive = SafeApplicationActive(),
        TemporaryDeactivateHidden = facts.TemporaryDeactivateHidden,
        PanelVisible = facts.PanelVisible,
        RequiresSelectedPanel = facts.RequiresSelectedPanel,
        PanelSelectedVisible = facts.PanelSelectedVisible,
        Disposed = true
    };
    var decision = _hostPresentation.Evaluate(snapshot, reason);
    RecordHostPresentationDecision(facts with { Reason = reason }, snapshot, decision, "none");
}
```

Provide `RecordHostPresentationDecision(...)` as a private no-op in this task if the recorder has not been added yet; Task 5 replaces the body with the ring append.

Use this helper:

```csharp
private static bool SafeApplicationActive()
{
    try { return Application.Instance.IsActive; }
    catch { return true; }
}
```

- [ ] **Step 6: Update refresh/controller events to preserve latest authoritative facts**

In `RequestHostVisibleRefresh`, if `UseHostPresentationCoordinator` is true, do not create durable visible state from scratch. Refresh only the latest authoritative panel facts. Controller, focus, activation, and WebView events must never synthesize `DesiredVisible=true` before `RookVisionPanel` has supplied facts:

```csharp
if (UseHostPresentationCoordinator)
{
    if (_latestPresentationFacts == null)
        return;

    var facts = _latestPresentationFacts with
    {
        Reason = reason,
        AppActive = SafeApplicationActive()
    };
    ScheduleHostPresentationCoordinatorReconcile(facts);
    return;
}
```

In `ConfigureVirtualHost`, replace only the coordinator-enabled controller available path:

```csharp
if (UseHostPresentationCoordinator)
{
    RequestHostVisibleRefresh("WebView2Configured");
}
else
{
    ScheduleHostVisibilityReconcile(
        _hostVisibility.RecordControllerAvailable("WebView2Configured"));
}
```

This preserves durable hidden facts when activation or controller-ready events arrive later.

- [ ] **Step 7: Run focused source tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CoordinatorPath_"
```

Expected: coordinator path source tests pass. Runtime behavior is not complete until Task 4.

- [ ] **Step 8: Commit**

Run:

```powershell
git add .\src\Rook\UI\Web\RookWebSurface.cs .\src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs
git commit -m "feat: add vision webview coordinator scheduling path"
```

---

### Task 4: Add Execution-Time Snapshot Builder And Action Sink

**Files:**
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Test: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`

- [ ] **Step 1: Add action-order tests**

In `RookWebSurfaceTests.cs`, add source tests:

```csharp
[Fact]
public void CoordinatorActionSink_OrdersBoundsVisibleNotify()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var method = ExtractMethod(source, "ApplyHostPresentationDecision");

    var boundsIndex = method.IndexOf("SetControllerBounds", StringComparison.Ordinal);
    var visibleIndex = method.IndexOf("SetControllerVisible(controller, true", StringComparison.Ordinal);
    var notifyIndex = method.IndexOf("NotifyParentWindowPositionChanged", StringComparison.Ordinal);

    Assert.True(boundsIndex >= 0, "bounds setter must be present");
    Assert.True(visibleIndex >= 0, "visible setter must be present");
    Assert.True(notifyIndex >= 0, "notify must be present");
    Assert.True(boundsIndex < visibleIndex);
    Assert.True(visibleIndex < notifyIndex);
}

[Fact]
public void CoordinatorActionSink_NotifyOnlyPresentDoesNotSetBoundsOrVisible()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var method = ExtractMethod(source, "ApplyHostPresentationDecision");

    Assert.Contains("if (decision.ShouldSetControllerBounds)", method);
    Assert.Contains("if (decision.ShouldSetControllerVisible)", method);
    Assert.Contains("NotifyParentWindowPositionChangedForPresentation(controller, reason)", method);
}

[Fact]
public void CoordinatorActionSink_ReportsNotifyFailure()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.Contains("notify-parent-failed", source);
    Assert.Contains("NotifyParentWindowPositionChangedForPresentation", source);
}

[Fact]
public void HostPresentationSnapshot_UsesSingleControllerForSnapshotAndAction()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var method = ExtractMethod(source, "RunHostPresentationCoordinatorReconcile");

    Assert.Contains("var controller = TryGetCoreWebView2Controller();", method);
    Assert.Contains("BuildHostPresentationSnapshot(facts, controller", method);
    Assert.Contains("ApplyHostPresentationDecision(decision, snapshot, controller", method);
}
```

If `ExtractMethod` is not present in `RookWebSurfaceTests.cs`, add a simple balanced-brace extractor copied from existing tests or keep this source scan helper:

```csharp
private static string ExtractMethod(string source, string methodName)
{
    var start = source.IndexOf(methodName, StringComparison.Ordinal);
    Assert.True(start >= 0, "Could not find method " + methodName);
    var brace = source.IndexOf('{', start);
    Assert.True(brace >= 0, "Could not find method body for " + methodName);
    var depth = 0;
    for (var i = brace; i < source.Length; i++)
    {
        if (source[i] == '{') depth++;
        if (source[i] == '}') depth--;
        if (depth == 0) return source.Substring(start, i - start + 1);
    }

    throw new InvalidOperationException("Unbalanced method body for " + methodName);
}
```

- [ ] **Step 2: Run action tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CoordinatorActionSink_|FullyQualifiedName~HostPresentationSnapshot_"
```

Expected: source tests fail until snapshot/action methods are added.

- [ ] **Step 3: Add snapshot target helper types**

Inside `RookWebSurface.cs` under `ROOK_WEBVIEW2`, add small private structs:

```csharp
private readonly struct HostPresentationSnapshotResult
{
    public HostPresentationSnapshotResult(
        WebViewHostPresentationSnapshot snapshot,
        object? targetBounds)
    {
        Snapshot = snapshot;
        TargetBounds = targetBounds;
    }

    public WebViewHostPresentationSnapshot Snapshot { get; }
    public object? TargetBounds { get; }
}
```

`targetBounds` is the reflected bounds object that the action sink would set.

- [ ] **Step 4: Implement execution-time snapshot builder**

Add:

```csharp
private HostPresentationSnapshotResult BuildHostPresentationSnapshot(
    WebViewHostPanelPresentationFacts facts,
    object? controller)
{
    var webView = _webView;
    var etoWidth = 0;
    var etoHeight = 0;
    var parentWindowPresent = false;

    try
    {
        if (webView != null)
        {
            var size = webView.Size;
            var boundsSize = webView.Bounds.Size;
            etoWidth = size.Width > 0 ? size.Width : boundsSize.Width;
            etoHeight = size.Height > 0 ? size.Height : boundsSize.Height;
            parentWindowPresent = webView.ParentWindow != null;
        }
    }
    catch
    {
        etoWidth = 0;
        etoHeight = 0;
        parentWindowPresent = false;
    }

    var targetBounds = controller == null
        ? null
        : CreateControllerBoundsTarget(controller, etoWidth, etoHeight);
    var controllerVisible = controller != null && ReadControllerVisible(controller);
    var controllerParentPresent = controller != null && ReadControllerParentWindowPresent(controller);
    var boundsMatch = controller != null &&
        targetBounds != null &&
        ControllerBoundsMatchTarget(controller, targetBounds);

    var hwndFacts = CaptureHwndFacts(webView);

    var snapshot = new WebViewHostPresentationSnapshot
    {
        Disposed = _disposed,
        DesiredVisible = facts.DesiredVisible,
        AppActive = SafeApplicationActive(),
        TemporaryDeactivateHidden = facts.TemporaryDeactivateHidden && !SafeApplicationActive(),
        PanelVisible = facts.PanelVisible,
        RequiresSelectedPanel = facts.RequiresSelectedPanel,
        PanelSelectedVisible = facts.PanelSelectedVisible,
        EtoLoaded = webView?.Loaded == true,
        EtoVisible = webView?.Visible == true,
        EtoWidth = etoWidth,
        EtoHeight = etoHeight,
        ParentWindowPresent = parentWindowPresent,
        HwndChainVisible = hwndFacts.ChainVisible,
        HwndClientRectNonZero = hwndFacts.ClientRectNonZero,
        ControllerAvailable = controller != null,
        ControllerParentWindowPresent = controllerParentPresent,
        ControllerVisible = controllerVisible,
        ControllerBoundsMatchHostTarget = boundsMatch
    };

    return new HostPresentationSnapshotResult(snapshot, targetBounds);
}
```

Add conservative helper methods. They must swallow failures and return false/null:

```csharp
private static bool ReadControllerVisible(object controller)
{
    try
    {
        return GetInstanceProperty(controller.GetType(), "IsVisible")?.GetValue(controller) is true;
    }
    catch { return false; }
}

private static bool ReadControllerParentWindowPresent(object controller)
{
    try
    {
        var value = GetInstanceProperty(controller.GetType(), "ParentWindow")?.GetValue(controller);
        if (value == null) return false;
        if (value is IntPtr ptr) return ptr != IntPtr.Zero;
        if (value is nint nativePtr) return nativePtr != 0;
        return true;
    }
    catch { return false; }
}
```

For `CreateControllerBoundsTarget`, use the controller's existing `Bounds` property type:

```csharp
private static object? CreateControllerBoundsTarget(
    object controller,
    int width,
    int height)
{
    if (width <= 0 || height <= 0)
        return null;

    try
    {
        var boundsProp = GetInstanceProperty(controller.GetType(), "Bounds");
        var boundsType = boundsProp?.PropertyType;
        if (boundsType == null)
            return null;

        var ctor = boundsType.GetConstructor(new[]
        {
            typeof(int), typeof(int), typeof(int), typeof(int)
        });
        return ctor?.Invoke(new object[] { 0, 0, width, height });
    }
    catch { return null; }
}
```

Add compare/set methods:

```csharp
private static bool ControllerBoundsMatchTarget(object controller, object targetBounds)
{
    try
    {
        var boundsProp = GetInstanceProperty(controller.GetType(), "Bounds");
        var current = boundsProp?.GetValue(controller);
        return current != null && current.Equals(targetBounds);
    }
    catch { return false; }
}

private bool SetControllerBounds(object controller, object targetBounds, string reason)
{
    try
    {
        var boundsProp = GetInstanceProperty(controller.GetType(), "Bounds");
        if (boundsProp == null || !boundsProp.CanWrite)
            return false;
        boundsProp.SetValue(controller, targetBounds);
        return true;
    }
    catch (Exception ex)
    {
        Log($"Rook: WebView2 controller bounds set failed for surface " +
            $"'{ResourceRoot}' (reason={reason}): {ex.GetType().Name}");
        return false;
    }
}
```

For HWND facts, keep it minimal and conservative. If there is no reliable handle path, return false facts rather than presenting from unknown state. Use `IntPtr` only; do not store handles in ring entries.

- [ ] **Step 5: Implement action sink**

Complete `RunHostPresentationCoordinatorReconcile`:

```csharp
var controller = TryGetCoreWebView2Controller();
var snapshotResult = BuildHostPresentationSnapshot(facts, controller);
var snapshot = snapshotResult.Snapshot;
var decision = _hostPresentation.Evaluate(snapshot, facts.Reason);
var actionResult = ApplyHostPresentationDecision(
    decision,
    snapshot,
    controller,
    snapshotResult.TargetBounds,
    facts.Reason);
RecordHostPresentationDecision(facts, snapshot, decision, actionResult);
```

Add action sink:

```csharp
private string ApplyHostPresentationDecision(
    WebViewHostPresentationDecision decision,
    WebViewHostPresentationSnapshot snapshot,
    object? controller,
    object? targetBounds,
    string reason)
{
    if (decision.Action == WebViewHostPresentationAction.None)
        return "none";

    if (controller == null)
        return "skipped-controller-unavailable";

    if (decision.Action == WebViewHostPresentationAction.HideController)
    {
        return SetControllerVisible(controller, false, reason)
            ? "applied"
            : "set-visible-failed:Unknown";
    }

    if (decision.Action != WebViewHostPresentationAction.PresentController)
        return "none";

    if (decision.ShouldSetControllerBounds)
    {
        if (targetBounds == null)
            return "set-bounds-failed:TargetUnavailable";
        if (!SetControllerBounds(controller, targetBounds, reason))
            return "set-bounds-failed:Unknown";
    }

    if (decision.ShouldSetControllerVisible)
    {
        if (!SetControllerVisible(controller, true, reason))
            return "set-visible-failed:Unknown";
    }

    return NotifyParentWindowPositionChangedForPresentation(controller, reason);
}
```

Add a coordinator-path notify helper that returns short sanitized results instead of swallowing the failure into `"applied"`:

```csharp
private string NotifyParentWindowPositionChangedForPresentation(object controller, string reason)
{
    try
    {
        NotifyParentWindowPositionChanged(controller, reason);
        return "applied";
    }
    catch (Exception ex)
    {
        Log($"Rook: WebView2 parent position notify failed for surface " +
            $"'{ResourceRoot}' (reason={reason}): {ex.GetType().Name}");
        return "notify-parent-failed:" + ex.GetType().Name;
    }
}
```

If the existing `NotifyParentWindowPositionChanged` currently swallows exceptions, split the reflection call into a non-throwing legacy wrapper plus the result-returning coordinator helper so the coordinator path can report `notify-parent-failed:<ExceptionType>`. If you can cheaply return exception type names from `SetControllerBounds` and `SetControllerVisible`, do so through the same small result-helper pattern. Do not store stack traces.

- [ ] **Step 6: Run focused Web tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web"
```

Expected: Web tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add .\src\Rook\UI\Web\RookWebSurface.cs .\src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs
git commit -m "feat: apply webview presentation coordinator actions"
```

---

### Task 5: Add Vision In-Memory Presentation Ring

**Files:**
- Create: `src/Rook/UI/Web/WebViewHostPresentationRecorder.cs`
- Create: `src/Rook/UI/Vision/VisionPresentationStateStore.cs`
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionPresentationStateStoreTests.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add ring tests**

Create `src/Rook.Tests/UI/Vision/VisionPresentationStateStoreTests.cs`:

```csharp
using System.Linq;
using Rook.UI.Vision;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionPresentationStateStoreTests
    {
        [Fact]
        public void Snapshot_WhenEmpty_ReturnsSurfaceAbsentMetadata()
        {
            var store = new VisionPresentationStateStore(capacity: 4);

            var snapshot = store.Snapshot();

            Assert.False(snapshot.SurfacePresent);
            Assert.Equal(0, snapshot.EntryCount);
            Assert.Equal(4, snapshot.Capacity);
            Assert.Empty(snapshot.Entries);
        }

        [Fact]
        public void SurfaceRegistration_ControlsSurfacePresentMetadata()
        {
            var store = new VisionPresentationStateStore(capacity: 4);

            Assert.False(store.Snapshot().SurfacePresent);
            using (store.RegisterSurface())
            {
                Assert.True(store.Snapshot().SurfacePresent);
            }
            Assert.False(store.Snapshot().SurfacePresent);
        }

        [Fact]
        public void Append_EvictsOldestEntriesAtCapacity()
        {
            var store = new VisionPresentationStateStore(capacity: 2);
            using var surface = store.RegisterSurface();

            store.Append(TestEntry("one"));
            store.Append(TestEntry("two"));
            store.Append(TestEntry("three"));

            var entries = store.Snapshot().Entries;
            Assert.Equal(new[] { "two", "three" }, entries.Select(e => e.Reason).ToArray());
        }

        [Fact]
        public void Append_AssignsMonotonicSequence()
        {
            var store = new VisionPresentationStateStore(capacity: 4);
            using var surface = store.RegisterSurface();

            store.Append(TestEntry("one"));
            store.Append(TestEntry("two"));

            var entries = store.Snapshot().Entries;
            Assert.True(entries[0].Sequence < entries[1].Sequence);
        }

        [Fact]
        public void Entries_ArePlainDtoFields()
        {
            var properties = typeof(WebViewHostPresentationRecord).GetProperties();

            foreach (var property in properties)
            {
                var type = property.PropertyType;
                Assert.True(
                    type.IsPrimitive ||
                    type.IsEnum ||
                    type == typeof(string) ||
                    type == typeof(System.DateTimeOffset) ||
                    type == typeof(long),
                    $"Unexpected non-DTO field {property.Name}: {type.FullName}");
            }
        }

        private static WebViewHostPresentationRecord TestEntry(string reason)
        {
            return new WebViewHostPresentationRecord
            {
                Reason = reason,
                ActionResult = "none"
            };
        }
    }
}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionPresentationStateStoreTests"
```

Expected: compile failure for missing ring/store types.

- [ ] **Step 3: Add recorder DTO and interface**

Create `src/Rook/UI/Web/WebViewHostPresentationRecorder.cs`:

```csharp
using System;

namespace Rook.UI.Web
{
    internal interface IWebViewHostPresentationRecorder
    {
        void Append(WebViewHostPresentationRecord record);
    }

    internal sealed record WebViewHostPresentationRecord
    {
        public long Sequence { get; init; }
        public DateTimeOffset Utc { get; init; }
        public long ElapsedMilliseconds { get; init; }
        public string Reason { get; init; } = string.Empty;
        public string OldState { get; init; } = string.Empty;
        public string NewState { get; init; } = string.Empty;
        public string Action { get; init; } = string.Empty;
        public string NotPresentableReason { get; init; } = string.Empty;
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; }
        public bool PanelSelectedVisible { get; init; }
        public bool EtoLoaded { get; init; }
        public bool EtoVisible { get; init; }
        public int EtoWidth { get; init; }
        public int EtoHeight { get; init; }
        public bool ParentWindowPresent { get; init; }
        public bool HwndChainVisible { get; init; }
        public bool HwndClientRectNonZero { get; init; }
        public bool ControllerAvailable { get; init; }
        public bool ControllerParentWindowPresent { get; init; }
        public bool ControllerVisible { get; init; }
        public bool ControllerBoundsMatchHostTarget { get; init; }
        public bool ShouldSetControllerBounds { get; init; }
        public bool ShouldSetControllerVisible { get; init; }
        public bool ShouldNotifyParentPositionChanged { get; init; }
        public string ActionResult { get; init; } = string.Empty;
        public int ThreadId { get; init; }
    }
}
```

- [ ] **Step 4: Add Vision ring store**

Create `src/Rook/UI/Vision/VisionPresentationStateStore.cs`:

```csharp
using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    internal sealed class VisionPresentationStateStore : IWebViewHostPresentationRecorder
    {
        public const int DefaultCapacity = 256;
        private readonly object _gate = new();
        private readonly WebViewHostPresentationRecord[] _entries;
        private readonly Stopwatch _clock = Stopwatch.StartNew();
        private int _nextIndex;
        private int _count;
        private long _sequence;
        private int _surfaceCount;

        public VisionPresentationStateStore(int capacity = DefaultCapacity)
        {
            if (capacity <= 0)
                throw new ArgumentOutOfRangeException(nameof(capacity));
            _entries = new WebViewHostPresentationRecord[capacity];
        }

        public int Capacity => _entries.Length;

        public IDisposable RegisterSurface()
        {
            Interlocked.Increment(ref _surfaceCount);
            return new SurfaceRegistration(this);
        }

        public void Append(WebViewHostPresentationRecord record)
        {
            try
            {
                var entry = record with
                {
                    Sequence = Interlocked.Increment(ref _sequence),
                    Utc = DateTimeOffset.UtcNow,
                    ElapsedMilliseconds = _clock.ElapsedMilliseconds,
                    ThreadId = Thread.CurrentThread.ManagedThreadId
                };

                lock (_gate)
                {
                    _entries[_nextIndex] = entry;
                    _nextIndex = (_nextIndex + 1) % _entries.Length;
                    if (_count < _entries.Length)
                        _count++;
                }
            }
            catch
            {
                // Diagnostics must never affect panel presentation.
            }
        }

        public VisionPresentationStateSnapshot Snapshot()
        {
            WebViewHostPresentationRecord[] copy;
            lock (_gate)
            {
                copy = new WebViewHostPresentationRecord[_count];
                for (var i = 0; i < _count; i++)
                {
                    var index = (_nextIndex - _count + i + _entries.Length) % _entries.Length;
                    copy[i] = _entries[index];
                }
            }

            return new VisionPresentationStateSnapshot
            {
                DumpRequestedUtc = DateTimeOffset.UtcNow,
                SurfacePresent = Volatile.Read(ref _surfaceCount) > 0,
                EntryCount = copy.Length,
                Capacity = Capacity,
                Entries = copy
            };
        }

        private void UnregisterSurface()
        {
            Interlocked.Decrement(ref _surfaceCount);
        }

        private sealed class SurfaceRegistration : IDisposable
        {
            private VisionPresentationStateStore? _owner;

            public SurfaceRegistration(VisionPresentationStateStore owner)
            {
                _owner = owner;
            }

            public void Dispose()
            {
                Interlocked.Exchange(ref _owner, null)?.UnregisterSurface();
            }
        }
    }

    internal sealed record VisionPresentationStateSnapshot
    {
        public DateTimeOffset DumpRequestedUtc { get; init; }
        public bool SurfacePresent { get; init; }
        public int EntryCount { get; init; }
        public int Capacity { get; init; }
        public WebViewHostPresentationRecord[] Entries { get; init; } =
            Array.Empty<WebViewHostPresentationRecord>();
    }
}
```

- [ ] **Step 5: Wire VisionWebSurface to recorder**

In `RookWebSurface.cs`, add:

```csharp
protected virtual IWebViewHostPresentationRecorder? HostPresentationRecorder => null;
```

After applying a coordinator decision, call:

```csharp
RecordHostPresentationDecision(facts, snapshot, decision, actionResult);
```

Implement:

```csharp
private void RecordHostPresentationDecision(
    WebViewHostPanelPresentationFacts facts,
    WebViewHostPresentationSnapshot snapshot,
    WebViewHostPresentationDecision decision,
    string actionResult)
{
    var recorder = HostPresentationRecorder;
    if (recorder == null)
        return;

    try
    {
        recorder.Append(new WebViewHostPresentationRecord
        {
            Reason = facts.Reason,
            OldState = decision.OldState.ToString(),
            NewState = decision.NewState.ToString(),
            Action = decision.Action.ToString(),
            NotPresentableReason = decision.NotPresentableReason.ToString(),
            DesiredVisible = snapshot.DesiredVisible,
            AppActive = snapshot.AppActive,
            TemporaryDeactivateHidden = snapshot.TemporaryDeactivateHidden,
            PanelVisible = snapshot.PanelVisible,
            RequiresSelectedPanel = snapshot.RequiresSelectedPanel,
            PanelSelectedVisible = snapshot.PanelSelectedVisible,
            EtoLoaded = snapshot.EtoLoaded,
            EtoVisible = snapshot.EtoVisible,
            EtoWidth = snapshot.EtoWidth,
            EtoHeight = snapshot.EtoHeight,
            ParentWindowPresent = snapshot.ParentWindowPresent,
            HwndChainVisible = snapshot.HwndChainVisible,
            HwndClientRectNonZero = snapshot.HwndClientRectNonZero,
            ControllerAvailable = snapshot.ControllerAvailable,
            ControllerParentWindowPresent = snapshot.ControllerParentWindowPresent,
            ControllerVisible = snapshot.ControllerVisible,
            ControllerBoundsMatchHostTarget = snapshot.ControllerBoundsMatchHostTarget,
            ShouldSetControllerBounds = decision.ShouldSetControllerBounds,
            ShouldSetControllerVisible = decision.ShouldSetControllerVisible,
            ShouldNotifyParentPositionChanged = decision.ShouldNotifyParentPositionChanged,
            ActionResult = actionResult
        });
    }
    catch
    {
        // Presentation diagnostics must never affect the surface.
    }
}
```

In `VisionWebSurface`, add a shared store and override:

```csharp
internal static VisionPresentationStateStore PresentationState { get; } = new();
private readonly IDisposable _presentationSurfaceRegistration =
    PresentationState.RegisterSurface();

protected override IWebViewHostPresentationRecorder? HostPresentationRecorder =>
    PresentationState;

protected override void Dispose(bool disposing)
{
    if (disposing)
        _presentationSurfaceRegistration.Dispose();

    base.Dispose(disposing);
}
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionPresentationStateStoreTests|FullyQualifiedName~VisionWebSurface_OptsIntoHostPresentationCoordinator"
```

Expected: tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add .\src\Rook\UI\Web\WebViewHostPresentationRecorder.cs `
  .\src\Rook\UI\Vision\VisionPresentationStateStore.cs `
  .\src\Rook\UI\Web\RookWebSurface.cs `
  .\src\Rook\UI\Vision\VisionWebSurface.cs `
  .\src\Rook.Tests\UI\Vision\VisionPresentationStateStoreTests.cs `
  .\src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat: record vision presentation decisions in memory"
```

---

### Task 6: Add `RookDumpVisionPresentationState` Command

**Files:**
- Create: `src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs`
- Modify: `src/Rook/UI/Vision/VisionPresentationStateStore.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionPresentationStateStoreTests.cs`
- Test: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`

- [ ] **Step 1: Add dump JSON tests**

In `VisionPresentationStateStoreTests.cs`, add:

```csharp
[Fact]
public void CreateDumpPayload_IncludesMetadataAndEntries()
{
    var store = new VisionPresentationStateStore(capacity: 2);
    using var surface = store.RegisterSurface();
    store.Append(TestEntry("one"));

    var payload = VisionPresentationStateDump.CreatePayload(
        store.Snapshot(),
        rookVersion: "1.2.3-test",
        rhinoVersion: "8-test",
        processId: 123,
        threadId: 456);

    Assert.Equal("1.2.3-test", payload.RookVersion);
    Assert.Equal("8-test", payload.RhinoVersion);
    Assert.Equal(123, payload.ProcessId);
    Assert.Equal(456, payload.ThreadId);
    Assert.True(payload.SurfacePresent);
    Assert.Equal(1, payload.EntryCount);
    Assert.Equal(2, payload.Capacity);
    Assert.Single(payload.Entries);
}

[Fact]
public void CreateDumpPayload_WhenNoSurface_WritesValidEmptyDump()
{
    var store = new VisionPresentationStateStore(capacity: 2);

    var payload = VisionPresentationStateDump.CreatePayload(
        store.Snapshot(),
        rookVersion: "1.2.3-test",
        rhinoVersion: "8-test",
        processId: 123,
        threadId: 456);

    Assert.False(payload.SurfacePresent);
    Assert.Equal(0, payload.EntryCount);
    Assert.Empty(payload.Entries);
}
```

In `RookPluginLifecycleSourceTests.cs`, add a source guard:

```csharp
[Fact]
public void DumpVisionPresentationStateCommand_DoesNotTouchPanelVisibility()
{
    var source = ReadSourceFile("src", "Rook", "Commands", "RookDumpVisionPresentationStateCommand.cs");

    Assert.Contains("RookDumpVisionPresentationState", source);
    Assert.Contains("VisionWebSurface.PresentationState", source);
    Assert.DoesNotContain("OpenPanel", source);
    Assert.DoesNotContain("ClosePanel", source);
    Assert.DoesNotContain("ReconcileHostVisibility", source);
    Assert.DoesNotContain("CreateWebContent", source);
}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CreateDumpPayload_|FullyQualifiedName~DumpVisionPresentationStateCommand_"
```

Expected: compile/source failures because dump payload and command do not exist.

- [ ] **Step 3: Add dump payload types**

In `VisionPresentationStateStore.cs`, add:

```csharp
internal static class VisionPresentationStateDump
{
    public static VisionPresentationStateDumpPayload CreatePayload(
        VisionPresentationStateSnapshot snapshot,
        string rookVersion,
        string rhinoVersion,
        int processId,
        int threadId)
    {
        return new VisionPresentationStateDumpPayload
        {
            RookVersion = rookVersion,
            RhinoVersion = rhinoVersion,
            ProcessId = processId,
            ThreadId = threadId,
            DumpRequestedUtc = snapshot.DumpRequestedUtc,
            SurfacePresent = snapshot.SurfacePresent,
            EntryCount = snapshot.EntryCount,
            Capacity = snapshot.Capacity,
            Entries = snapshot.Entries
        };
    }
}

internal sealed record VisionPresentationStateDumpPayload
{
    public string RookVersion { get; init; } = string.Empty;
    public string RhinoVersion { get; init; } = string.Empty;
    public int ProcessId { get; init; }
    public int ThreadId { get; init; }
    public DateTimeOffset DumpRequestedUtc { get; init; }
    public bool SurfacePresent { get; init; }
    public int EntryCount { get; init; }
    public int Capacity { get; init; }
    public WebViewHostPresentationRecord[] Entries { get; init; } =
        Array.Empty<WebViewHostPresentationRecord>();
}
```

- [ ] **Step 4: Add the Rhino dump command**

Create `src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs`:

```csharp
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using Rhino;
using Rhino.Commands;
using Rook.UI.Vision;

namespace Rook.Commands
{
    public class RookDumpVisionPresentationStateCommand : Command
    {
        public override string EnglishName => "RookDumpVisionPresentationState";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            try
            {
                var directory = Path.Combine(Path.GetTempPath(), "rook");
                Directory.CreateDirectory(directory);
                var timestamp = DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss-fff");
                var path = Path.Combine(
                    directory,
                    $"vision-presentation-state-{timestamp}.json");

                var payload = VisionPresentationStateDump.CreatePayload(
                    VisionWebSurface.PresentationState.Snapshot(),
                    GetRookVersion(),
                    RhinoApp.Version?.ToString() ?? "",
                    Process.GetCurrentProcess().Id,
                    Environment.CurrentManagedThreadId);

                var json = JsonSerializer.Serialize(
                    payload,
                    new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(path, json);
                RhinoApp.WriteLine("Rook Vision presentation state dumped to: " + path);
                return Result.Success;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine("Rook Vision presentation state dump failed: " + ex.Message);
                return Result.Failure;
            }
        }

        private static string GetRookVersion()
        {
            try
            {
                return typeof(RookPlugin).Assembly
                    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                    ?.InformationalVersion ?? "";
            }
            catch
            {
                return "";
            }
        }
    }
}
```

If a reliable `surfacePresent` tracker is added to `VisionWebSurface`, use it instead of `true`. If not, the dump remains valid because the ring can be empty and the command never touches the panel. The test for no surface is covered by the store payload.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionPresentationStateStoreTests|FullyQualifiedName~DumpVisionPresentationStateCommand_"
```

Expected: tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add .\src\Rook\Commands\RookDumpVisionPresentationStateCommand.cs `
  .\src\Rook\UI\Vision\VisionPresentationStateStore.cs `
  .\src\Rook.Tests\UI\Vision\VisionPresentationStateStoreTests.cs `
  .\src\Rook.Tests\Plugin\RookPluginLifecycleSourceTests.cs
git commit -m "feat: add vision presentation state dump command"
```

---

### Task 7: Full Managed Verification And Scope Guard

**Files:**
- Verify all changed files.

- [ ] **Step 1: Confirm only intended runtime surfaces changed**

Run:

```powershell
git diff --name-only origin/main...HEAD
```

Expected changed runtime files include Vision and shared Web plumbing, but not Chat/KG runtime files:

```text
docs/superpowers/plans/2026-05-25-vision-webview-host-presentation-integration.md
docs/superpowers/specs/2026-05-25-vision-webview-host-presentation-integration-design.md
src/Rook/Commands/RookDumpVisionPresentationStateCommand.cs
src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs
src/Rook/UI/Web/RookWebSurface.cs
src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs
src/Rook/UI/Web/WebViewHostPresentationRecorder.cs
src/Rook/UI/Vision/RookVisionPanel.cs
src/Rook/UI/Vision/VisionPresentationStateStore.cs
src/Rook/UI/Vision/VisionWebSurface.cs
```

Chat/KG test files may be changed only for source guards. Chat/KG runtime files should not be changed.

- [ ] **Step 2: Run focused managed tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web|FullyQualifiedName~Rook.Tests.UI.Vision|FullyQualifiedName~Rook.Tests.UI.Panels|FullyQualifiedName~Rook.Tests.Plugin"
```

Expected: focused tests pass.

- [ ] **Step 3: Run full managed suite**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore
```

Expected: full managed suite passes. The baseline as of PR #191 review was `2330 passed`.

- [ ] **Step 4: Run whitespace validation**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 5: Confirm no prohibited behavior**

Run:

```powershell
rg -n "ROOK_USE_HOST_PRESENTATION_COORDINATOR|ROOK_ENABLE_VISION_DARK_DIAGNOSTICS|ExecuteScript\\(|File\\.AppendAllText|Task\\.Delay\\(|ReloadAfterHostActivation|RecoverAfterHostActivation" src\Rook\UI\Web src\Rook\UI\Vision src\Rook\Commands\RookDumpVisionPresentationStateCommand.cs
```

Expected:

```text
- No runtime opt-out env var.
- No Vision dark diagnostics env dependency.
- No JS probes in the coordinator path.
- No hot-path file append logging.
- No new Task.Delay/polling loop in the coordinator path.
- No reload/recovery patch names.
```

Existing unrelated `ExecuteScript` methods in `RookWebSurface` may appear; inspect results and confirm they are not called from `RunHostPresentationCoordinatorReconcile`, `BuildHostPresentationSnapshot`, or `ApplyHostPresentationDecision`.

- [ ] **Step 6: Commit plan file if it has not already been committed**

Run:

```powershell
git add .\docs\superpowers\plans\2026-05-25-vision-webview-host-presentation-integration.md
git commit -m "docs: plan vision webview presentation integration"
```

If the plan was committed before implementation, skip this commit.

---

## Live Validation Handoff For PR #192

After implementation and local deploy, validate with diagnostics flags off:

```powershell
Remove-Item Env:\ROOK_ENABLE_VISION_DARK_DIAGNOSTICS -ErrorAction SilentlyContinue
Remove-Item Env:\ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS -ErrorAction SilentlyContinue
Remove-Item Env:\ROOK_PANEL_LIFECYCLE_TRACE -ErrorAction SilentlyContinue
```

Run the matrix:

```text
Vision docked, click away, return: 10 cycles.
Vision floating, click away, return: 10 cycles.
Vision selected tab, click away, return: 10 cycles.
Vision tabbed behind another panel, return: 10 cycles.
Vision gallery modal open, click away, return: repeated cycles, more than one.
Chat and Knowledge Graph under the same session as controls.
```

If suspicious behavior appears, run:

```text
RookDumpVisionPresentationState
```

Do not click inside Vision to dump.

Record:

```text
Rhino version
WebView2 runtime version
Rook build/commit
panel mode
Vision selected/background status
whether dump was taken
dump path if taken
```

---

## Self-Review

**Spec coverage:** The plan covers the Vision default-on policy, Chat/KG old-path controls, explicit panel facts, execution-time snapshot building, serialized coordinator evaluation, action order, memory-only ring, explicit dump command, no runtime flags, no JS probes, no hot-path file logging, automated tests, full managed suite, and live validation.

**Completeness scan:** The plan contains no deferred design sections or unresolved implementation gaps. Where implementation must choose among existing code shapes, the plan names the allowed fallback and the required verification.

**Type consistency:** The plan consistently uses `WebViewHostPanelPresentationFacts`, `WebViewHostPresentationRecord`, `IWebViewHostPresentationRecorder`, `VisionPresentationStateStore`, `VisionPresentationStateSnapshot`, `VisionPresentationStateDump`, and `RookDumpVisionPresentationStateCommand`.
