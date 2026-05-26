# Vision Return-Edge Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vision-only deterministic WebView2 return-edge path that never presents while Rhino/app/panel host is inactive or non-presentable, and presents exactly once when active selected Vision becomes host-presentable.

**Architecture:** Keep PR #191's `WebViewHostPresentationCoordinator` as the pure decision engine. Add a Vision-owned panel-facts tracker and a Vision-only `RookWebSurface` presentation path that builds fresh execution-time snapshots, applies actions in bounds -> visible -> notify order, and schedules one coalesced Rhino idle follow-up guarded by an authoritative generation token. Chat and Knowledge Graph stay on the old path.

**Tech Stack:** C# RhinoCommon/Eto/WebView2, xUnit managed tests, existing `Rook.UI.Web`, `Rook.UI.Vision`, and `Rook.UI.Panels` patterns.

---

## Source Spec

Design spec:

`docs/superpowers/specs/2026-05-26-vision-return-edge-presentation-design.md`

Key constraints from the spec:

- No runtime flags.
- No hot-path file logging.
- No JS/DOM probes.
- No reload recovery.
- No recurring idle loop.
- No Chat/KG runtime changes.
- Do not deploy PR #192 runtime wiring as-is.

---

## File Map

- Create: `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`
  - Plain DTO passed from Vision panel lifecycle to `RookWebSurface`.

- Create: `src/Rook/UI/Vision/VisionPanelPresentationState.cs`
  - Vision-owned authoritative facts/generation tracker.
  - Interprets Rhino `ShowPanelReason`, app active state, close/hide, visible-any-tab query results, and selected-tab query results.

- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
  - Add Vision-only presentation opt-in seam.
  - Add facts overload and serialized coordinator path.
  - Add fresh snapshot builder and action sink.
  - Add one-shot idle scheduling guarded by generation.
  - Preserve old behavior when `UseHostPresentationCoordinator == false`.

- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
  - Opt Vision into the new path.

- Modify: `src/Rook/UI/Vision/RookVisionPanel.cs`
  - Use `VisionPanelPresentationState`.
  - Subscribe app active changes for Vision only.
  - Query both selected-tab visibility and visible-any-tab with `RhinoPanelVisibilityQuery`.
  - Send authoritative facts to `_surface.ReconcileHostPresentation(...)`.
  - Stop sending legacy `_surface.ReconcileHostVisibility(...)` commands for Vision.

- Modify: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`
  - Add coordinator-level safety contract tests.

- Create: `src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs`
  - Unit-test durable intent, temporary hide, generation increments, and size/layout generation behavior.

- Modify: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`
  - Source/contract tests for Vision-only opt-in, no Chat/KG path changes, one-shot idle, no JS/reload/flag reliance.

- Modify: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`
  - Source/contract tests for Vision panel facts source and selected-tab visibility query.

---

## Task 1: Pin Coordinator Safety Semantics

**Files:**
- Modify: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`

- [ ] **Step 1: Add failing/locking tests for no-present inactive semantics**

Add these tests near existing inactive/temporary-deactivate coordinator tests:

```csharp
[Fact]
public void AppInactive_DoesNotPresent()
{
    var coordinator = new WebViewHostPresentationCoordinator();
    coordinator.Evaluate(ReadySnapshot(), "initial-ready");

    var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
    {
        AppActive = false
    }, "app-deactivated");

    Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
    Assert.Equal(WebViewHostNotPresentableReason.AppInactive, decision.NotPresentableReason);
    Assert.NotEqual(WebViewHostPresentationAction.PresentController, decision.Action);
    Assert.False(decision.ShouldSetControllerBounds);
    Assert.False(decision.ShouldSetControllerVisible);
    Assert.False(decision.ShouldNotifyParentPositionChanged);
}

[Fact]
public void AppDeactivated_VisibleController_HidesWithoutPresenting()
{
    var coordinator = new WebViewHostPresentationCoordinator();
    coordinator.Evaluate(ReadySnapshot(), "initial-ready");

    var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
    {
        AppActive = false
    }, "application-deactivated");

    Assert.Equal(WebViewHostPresentationState.Presenting, decision.OldState);
    Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
    Assert.Equal(WebViewHostPresentationAction.HideController, decision.Action);
    Assert.False(decision.ShouldSetControllerVisible);
    Assert.False(decision.ShouldNotifyParentPositionChanged);
}

[Fact]
public void HideOnDeactivate_DoesNotClearDesiredVisible()
{
    var coordinator = new WebViewHostPresentationCoordinator();

    var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
    {
        DesiredVisible = true,
        AppActive = false,
        TemporaryDeactivateHidden = true
    }, "hide-on-deactivate");

    Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
    Assert.Equal(WebViewHostNotPresentableReason.TemporaryDeactivateHidden, decision.NotPresentableReason);
    Assert.NotEqual(WebViewHostPresentationState.Hidden, decision.NewState);
}
```

- [ ] **Step 2: Run the focused coordinator tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~WebViewHostPresentationCoordinatorTests"
```

Expected: pass. These tests pin existing coordinator behavior and prevent reintroducing the dangerous PR #192 "present while inactive" path.

- [ ] **Step 3: Commit**

```powershell
git add src\Rook.Tests\UI\Web\WebViewHostPresentationCoordinatorTests.cs
git commit -m "test: pin inactive webview presentation safety"
```

---

## Task 2: Add Vision Panel Presentation Facts DTO

**Files:**
- Create: `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`

- [ ] **Step 1: Create the DTO**

Create `src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs`:

```csharp
namespace Rook.UI.Web
{
    internal sealed record WebViewHostPanelPresentationFacts
    {
        public long Generation { get; init; }
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisibleAnyTab { get; init; }
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; } = true;
        public bool PanelSelectedVisible { get; init; }
        public bool Disposed { get; init; }
        public bool Authoritative { get; init; } = true;
        public string Reason { get; init; } = string.Empty;
    }
}
```

Contract notes:

- `Disposed=true` is terminal. Only actual close/dispose may set it.
- `_webView == null`, controller missing, or not-yet-loaded states must not be represented as disposed.
- `TemporaryDeactivateHidden=true` must not imply `DesiredVisible=false`.
- `PanelVisibleAnyTab` distinguishes durable hidden intent from selected-tab loss. Tabbed-behind states must keep `DesiredVisible=true` when the panel is still visible anywhere.

- [ ] **Step 2: Build managed tests to verify compile**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~WebViewHostPresentationCoordinatorTests"
```

Expected: pass.

- [ ] **Step 3: Commit**

```powershell
git add src\Rook\UI\Web\WebViewHostPanelPresentationFacts.cs
git commit -m "feat: add webview panel presentation facts"
```

- [ ] **Step 4: Extend panel visibility query for visible-any-tab**

Modify `src/Rook/UI/Panels/IRhinoPanelVisibilityQuery.cs`:

```csharp
using System;

namespace Rook.UI.Panels
{
    internal interface IRhinoPanelVisibilityQuery
    {
        bool IsSelectedPanelVisible(Type panelType);
        bool IsPanelVisibleAnyTab(Type panelType);
    }
}
```

Modify `src/Rook/UI/Panels/RhinoPanelVisibilityQuery.cs`:

```csharp
using System;

namespace Rook.UI.Panels
{
    internal sealed class RhinoPanelVisibilityQuery : IRhinoPanelVisibilityQuery
    {
        public bool IsSelectedPanelVisible(Type panelType)
        {
            return Rhino.UI.Panels.IsPanelVisible(panelType, isSelectedTab: true);
        }

        public bool IsPanelVisibleAnyTab(Type panelType)
        {
            return Rhino.UI.Panels.IsPanelVisible(panelType, isSelectedTab: false);
        }
    }
}
```

Update fake test implementations of `IRhinoPanelVisibilityQuery` to return a configurable visible-any-tab value.

- [ ] **Step 5: Commit query extension**

```powershell
git add src\Rook\UI\Panels\IRhinoPanelVisibilityQuery.cs src\Rook\UI\Panels\RhinoPanelVisibilityQuery.cs src\Rook.Tests\UI\Panels\HostedPanelLifecycleAdapterTests.cs
git commit -m "feat: expose panel visible-any-tab query"
```

---

## Task 3: Add Vision Authoritative Facts Tracker

**Files:**
- Create: `src/Rook/UI/Vision/VisionPanelPresentationState.cs`
- Create: `src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs`

- [ ] **Step 1: Write tests for Vision facts/generation**

Create `src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs`:

```csharp
using Rhino.UI;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionPanelPresentationStateTests
    {
        [Fact]
        public void PanelShown_SetsDesiredVisibleAndPanelFacts()
        {
            var state = new VisionPanelPresentationState(appActive: true);

            var facts = state.PanelShown(
                ShowPanelReason.Show,
                visibleAnyTab: true,
                selectedVisible: true);

            Assert.True(facts.DesiredVisible);
            Assert.True(facts.PanelVisibleAnyTab);
            Assert.True(facts.PanelVisible);
            Assert.True(facts.PanelSelectedVisible);
            Assert.False(facts.TemporaryDeactivateHidden);
            Assert.Equal(1, facts.Generation);
        }

        [Fact]
        public void HideOnDeactivate_BlocksPresentationButDoesNotClearDesiredVisible()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);

            var facts = state.PanelHidden(
                ShowPanelReason.HideOnDeactivate,
                visibleAnyTab: true,
                selectedVisible: true);

            Assert.True(facts.DesiredVisible);
            Assert.True(facts.TemporaryDeactivateHidden);
            Assert.True(facts.PanelVisibleAnyTab);
            Assert.True(facts.PanelVisible);
            Assert.Equal(2, facts.Generation);
        }

        [Fact]
        public void PanelHiddenHide_WhenVisibleAnyTab_DoesNotClearDesiredVisible()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);

            var facts = state.PanelHidden(
                ShowPanelReason.Hide,
                visibleAnyTab: true,
                selectedVisible: false);

            Assert.True(facts.DesiredVisible);
            Assert.True(facts.PanelVisibleAnyTab);
            Assert.True(facts.PanelVisible);
            Assert.False(facts.PanelSelectedVisible);
            Assert.False(facts.TemporaryDeactivateHidden);
        }

        [Fact]
        public void PanelHiddenHide_WhenNotVisibleAnyTab_ClearsDesiredVisible()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);

            var facts = state.PanelHidden(
                ShowPanelReason.Hide,
                visibleAnyTab: false,
                selectedVisible: false);

            Assert.False(facts.DesiredVisible);
            Assert.False(facts.PanelVisibleAnyTab);
            Assert.False(facts.PanelVisible);
            Assert.False(facts.PanelSelectedVisible);
            Assert.False(facts.TemporaryDeactivateHidden);
        }

        [Fact]
        public void AppActiveChange_IncrementsAuthoritativeGeneration()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);
            var before = state.Current.Generation;

            var facts = state.SetAppActive(false);

            Assert.False(facts.AppActive);
            Assert.True(facts.Generation > before);
        }

        [Fact]
        public void SelectionRefresh_IncrementsWhenSelectionChanges()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: false);
            var before = state.Current.Generation;

            var facts = state.RefreshSelection(selectedVisible: true, reason: "selection-visible-refresh");

            Assert.True(facts.PanelSelectedVisible);
            Assert.True(facts.Generation > before);
        }

        [Fact]
        public void SizeLayoutSignal_DoesNotInvalidateAuthoritativeGenerationByItself()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);
            var before = state.Current.Generation;

            var facts = state.SizeLayoutSignal("size-changed");

            Assert.Equal(before, facts.Generation);
            Assert.Equal("size-changed", facts.Reason);
        }

        [Fact]
        public void PanelClosing_MarksDisposedAndDesiredHidden()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);

            var facts = state.PanelClosing();

            Assert.False(facts.DesiredVisible);
            Assert.True(facts.Disposed);
            Assert.False(facts.PanelVisible);
        }

        [Fact]
        public void PanelShownAfterClosing_DoesNotClearDisposed()
        {
            var state = new VisionPanelPresentationState(appActive: true);
            state.PanelShown(ShowPanelReason.Show, visibleAnyTab: true, selectedVisible: true);
            state.PanelClosing();

            var facts = state.PanelShown(
                ShowPanelReason.Show,
                visibleAnyTab: true,
                selectedVisible: true);

            Assert.True(facts.Disposed);
            Assert.False(facts.DesiredVisible);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionPanelPresentationStateTests"
```

Expected: fail because `VisionPanelPresentationState` does not exist.

- [ ] **Step 3: Implement the tracker**

Create `src/Rook/UI/Vision/VisionPanelPresentationState.cs`:

```csharp
using Rhino.UI;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    internal sealed class VisionPanelPresentationState
    {
        private long _generation;
        private bool _desiredVisible = true;
        private bool _appActive;
        private bool _temporaryDeactivateHidden;
        private bool _panelVisible = true;
        private bool _panelSelectedVisible;
        private bool _disposed;

        public VisionPanelPresentationState(bool appActive)
        {
            _appActive = appActive;
            Current = CreateFacts("initial");
        }

        public WebViewHostPanelPresentationFacts Current { get; private set; }

        public WebViewHostPanelPresentationFacts PanelShown(
            ShowPanelReason reason,
            bool visibleAnyTab,
            bool selectedVisible)
        {
            if (_disposed)
                return Update("PanelShownAfterDisposed:" + reason);

            _generation++;
            _desiredVisible = true;
            _panelVisible = visibleAnyTab;
            _panelSelectedVisible = selectedVisible;
            _temporaryDeactivateHidden = false;
            return Update("PanelShown:" + reason);
        }

        public WebViewHostPanelPresentationFacts PanelHidden(
            ShowPanelReason reason,
            bool visibleAnyTab,
            bool selectedVisible)
        {
            _generation++;
            _panelVisible = visibleAnyTab;
            _panelSelectedVisible = selectedVisible;

            if (reason == ShowPanelReason.HideOnDeactivate)
            {
                _temporaryDeactivateHidden = true;
                return Update("PanelHidden:" + reason);
            }

            _temporaryDeactivateHidden = false;
            if (!visibleAnyTab)
            {
                _desiredVisible = false;
            }
            return Update("PanelHidden:" + reason);
        }

        public WebViewHostPanelPresentationFacts PanelClosing()
        {
            _generation++;
            _desiredVisible = false;
            _temporaryDeactivateHidden = false;
            _panelVisible = false;
            _panelSelectedVisible = false;
            _disposed = true;
            return Update("PanelClosing");
        }

        public WebViewHostPanelPresentationFacts SetAppActive(bool active)
        {
            if (_appActive != active)
            {
                _generation++;
                _appActive = active;
                if (active)
                    _temporaryDeactivateHidden = false;
            }

            return Update(active ? "ApplicationActivated" : "ApplicationDeactivated");
        }

        public WebViewHostPanelPresentationFacts RefreshSelection(
            bool selectedVisible,
            string reason)
        {
            if (_panelSelectedVisible != selectedVisible)
            {
                _generation++;
                _panelSelectedVisible = selectedVisible;
            }

            return Update(reason);
        }

        public WebViewHostPanelPresentationFacts SizeLayoutSignal(string reason)
        {
            return Update(reason);
        }

        private WebViewHostPanelPresentationFacts Update(string reason)
        {
            Current = CreateFacts(reason);
            return Current;
        }

        private WebViewHostPanelPresentationFacts CreateFacts(string reason)
        {
            return new WebViewHostPanelPresentationFacts
            {
                Generation = _generation,
                DesiredVisible = _desiredVisible,
                AppActive = _appActive,
                TemporaryDeactivateHidden = _temporaryDeactivateHidden,
                PanelVisibleAnyTab = _panelVisible,
                PanelVisible = _panelVisible,
                RequiresSelectedPanel = true,
                PanelSelectedVisible = _panelSelectedVisible,
                Disposed = _disposed,
                Authoritative = true,
                Reason = reason
            };
        }
    }
}
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionPanelPresentationStateTests"
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\UI\Vision\VisionPanelPresentationState.cs src\Rook.Tests\UI\Vision\VisionPanelPresentationStateTests.cs
git commit -m "feat: track vision presentation facts"
```

---

## Task 4: Add Vision-Only Presentation Path In RookWebSurface

**Files:**
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Modify: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`

- [ ] **Step 1: Add source contract tests**

Add tests to `RookWebSurfaceTests`:

```csharp
[Fact]
public void VisionPresentationPath_IsOptInOnly()
{
    var webSurface = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var visionSurface = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");
    var chatPanel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");
    var knowledgePanel = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

    Assert.Contains("UseHostPresentationCoordinator", webSurface);
    Assert.Contains("protected override bool UseHostPresentationCoordinator => true;", visionSurface);
    Assert.DoesNotContain("ReconcileHostPresentation", chatPanel);
    Assert.DoesNotContain("ReconcileHostPresentation", knowledgePanel);
}

[Fact]
public void VisionPresentationPath_UsesOneShotIdleAndNoPersistentIdleLoop()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var schedule = ExtractMethod(source, "private void ScheduleHostPresentationIdleFollowUp");
    var idle = ExtractMethod(source, "private void OnHostPresentationIdle");

    Assert.Contains("ScheduleHostPresentationIdleFollowUp", source);
    Assert.Contains("RhinoApp.Idle += OnHostPresentationIdle", source);
    Assert.Contains("RhinoApp.Idle -= OnHostPresentationIdle", source);
    Assert.Contains("_hostPresentationIdlePending = false", source);
    Assert.DoesNotContain("while (", schedule + idle);
}

[Fact]
public void VisionPresentationPath_DoesNotUseReloadOrJsProbeForRecovery()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var run = ExtractMethod(source, "private void RunHostPresentationCoordinatorReconcile");
    var apply = ExtractMethod(source, "private string ApplyHostPresentationDecision");
    var idle = ExtractMethod(source, "private void OnHostPresentationIdle");
    var presentationMethods = run + apply + idle;

    Assert.DoesNotContain("ExecuteScript", presentationMethods);
    Assert.DoesNotContain("Reload", presentationMethods);
    Assert.DoesNotContain("ROOK_ENABLE", presentationMethods);
}
```

These are source guards. Behavior tests follow in later tasks.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookWebSurfaceTests.VisionPresentationPath"
```

Expected: fail because the new path does not exist.

- [ ] **Step 3: Add opt-in seam and fields**

In `RookWebSurface.cs`, add under existing virtual hooks:

```csharp
protected virtual bool UseHostPresentationCoordinator => false;
```

Under `#if ROOK_WEBVIEW2` fields, add:

```csharp
private readonly WebViewHostPresentationCoordinator _hostPresentation = new();
private WebViewHostPanelPresentationFacts? _latestPresentationFacts;
private bool _hostPresentationQueued;
private bool _hostPresentationIdlePending;
private long _hostPresentationIdleGeneration;
private string _hostPresentationIdleReason = "";
```

In `VisionWebSurface.cs`, add:

```csharp
protected override bool UseHostPresentationCoordinator => true;
```

- [ ] **Step 4: Add facts overload and serialized direct reconcile**

In `RookWebSurface.cs`, add an internal overload:

```csharp
internal void ReconcileHostPresentation(
    WebViewHostPanelPresentationFacts facts,
    bool scheduleIdleFollowUp)
{
#if ROOK_WEBVIEW2
    if (!UseHostPresentationCoordinator)
    {
        ReconcileHostVisibility(facts.DesiredVisible, facts.Reason);
        return;
    }

    if (!facts.Authoritative)
        return;

    _latestPresentationFacts = facts;
    ScheduleHostPresentationCoordinatorReconcile(
        facts.Reason,
        scheduleIdleFollowUp);
#else
    _ = facts;
    _ = scheduleIdleFollowUp;
#endif
}
```

Add the scheduler:

```csharp
#if ROOK_WEBVIEW2
private void ScheduleHostPresentationCoordinatorReconcile(
    string reason,
    bool scheduleIdleFollowUp)
{
    if (_disposed)
        return;

    if (_hostPresentationQueued)
    {
        if (scheduleIdleFollowUp)
            ScheduleHostPresentationIdleFollowUp(reason);
        return;
    }

    _hostPresentationQueued = true;

    try
    {
        Application.Instance.AsyncInvoke(() =>
        {
            _hostPresentationQueued = false;
            RunHostPresentationCoordinatorReconcile(reason);
            if (scheduleIdleFollowUp)
                ScheduleHostPresentationIdleFollowUp(reason);
        });
    }
    catch
    {
        _hostPresentationQueued = false;
        RunHostPresentationCoordinatorReconcile(reason);
        if (scheduleIdleFollowUp)
            ScheduleHostPresentationIdleFollowUp(reason);
    }
}
#endif
```

Do not call this from Chat/KG.

- [ ] **Step 5: Add one-shot idle follow-up**

In `RookWebSurface.cs`, add:

```csharp
#if ROOK_WEBVIEW2
private void ScheduleHostPresentationIdleFollowUp(string reason)
{
    if (_disposed || _latestPresentationFacts == null)
        return;

    if (_hostPresentationIdlePending)
        return;

    _hostPresentationIdlePending = true;
    _hostPresentationIdleGeneration = _latestPresentationFacts.Generation;
    _hostPresentationIdleReason = reason;
    RhinoApp.Idle += OnHostPresentationIdle;
}

private void OnHostPresentationIdle(object? sender, EventArgs e)
{
    RhinoApp.Idle -= OnHostPresentationIdle;

    if (!_hostPresentationIdlePending)
        return;

    _hostPresentationIdlePending = false;
    var capturedGeneration = _hostPresentationIdleGeneration;
    var reason = _hostPresentationIdleReason;
    _hostPresentationIdleReason = "";

    if (_disposed || _latestPresentationFacts == null)
        return;

    if (_latestPresentationFacts.Generation != capturedGeneration)
        return;

    if (!_latestPresentationFacts.DesiredVisible)
        return;

    RunHostPresentationCoordinatorReconcile("IdleFollowUp:" + reason);
}
#endif
```

In `DisposeWebView()`, add before disposing `_webView`:

```csharp
try { RhinoApp.Idle -= OnHostPresentationIdle; } catch { }
_hostPresentationIdlePending = false;
```

- [ ] **Step 6: Route WebView/app events correctly**

In `CreateWebContent`, keep `GotFocus` and old app active subscriptions for old path only. Use this shape:

```csharp
_webView.GotFocus += OnWebViewGotFocus;
_webView.Shown += OnWebViewShown;
_webView.SizeChanged += OnWebViewSizeChanged;
Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;
```

Then make handlers branch:

```csharp
private void OnWebViewGotFocus(object? sender, EventArgs e)
{
    TraceWebViewFocus("webview-got-focus");
    if (UseHostPresentationCoordinator)
        return;
    RequestHostVisibleRefresh("WebViewGotFocus");
}

private void OnWebViewShown(object? sender, EventArgs e)
{
    TraceWebViewFocus("webview-shown");
    if (UseHostPresentationCoordinator)
    {
        ScheduleHostPresentationFromLatest("WebViewShown", scheduleIdleFollowUp: true);
        return;
    }
    ReconcileHostVisibility(true, "WebViewShown");
}

private void OnWebViewSizeChanged(object? sender, EventArgs e)
{
    if (!UseHostPresentationCoordinator)
        return;
    ScheduleHostPresentationFromLatest("WebViewSizeChanged", scheduleIdleFollowUp: true);
}
```

Add:

```csharp
private void ScheduleHostPresentationFromLatest(
    string reason,
    bool scheduleIdleFollowUp)
{
#if ROOK_WEBVIEW2
    if (_latestPresentationFacts == null)
        return;

    _latestPresentationFacts = _latestPresentationFacts with { Reason = reason };
    ScheduleHostPresentationCoordinatorReconcile(reason, scheduleIdleFollowUp);
#else
    _ = reason;
    _ = scheduleIdleFollowUp;
#endif
}
```

For `OnApplicationIsActiveChanged`, Vision must not invent panel facts in `RookWebSurface`. Keep app active authoritative facts in `RookVisionPanel` in Task 6. Therefore branch:

```csharp
if (UseHostPresentationCoordinator)
    return;
```

before old active/inactive visibility refresh behavior.

In `DisposeWebView`, unsubscribe:

```csharp
try { _webView!.SizeChanged -= OnWebViewSizeChanged; } catch { }
```

- [ ] **Step 7: Run source tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookWebSurfaceTests.VisionPresentationPath"
```

Expected: pass after the opt-in path exists.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\UI\Web\RookWebSurface.cs src\Rook\UI\Vision\VisionWebSurface.cs src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs
git commit -m "feat: add vision webview presentation scheduler"
```

---

## Task 5: Add Fresh Snapshot Builder And Action Sink

**Files:**
- Modify: `src/Rook/UI/Web/RookWebSurface.cs`
- Modify: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`

- [ ] **Step 1: Add source tests for action order and no disposed misuse**

Add:

```csharp
[Fact]
public void VisionPresentationPath_AppliesPresentInBoundsVisibleNotifyOrder()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");
    var method = ExtractMethod(source, "private string ApplyHostPresentationDecision");

    var boundsIndex = method.IndexOf("SetControllerBounds", StringComparison.Ordinal);
    var visibleIndex = method.IndexOf("SetControllerVisible(controller, true", StringComparison.Ordinal);
    var notifyIndex = method.IndexOf("NotifyParentWindowPositionChanged", StringComparison.Ordinal);

    Assert.True(boundsIndex >= 0);
    Assert.True(visibleIndex >= 0);
    Assert.True(notifyIndex >= 0);
    Assert.True(boundsIndex < visibleIndex);
    Assert.True(visibleIndex < notifyIndex);
}

[Fact]
public void VisionPresentationPath_DoesNotMarkMissingWebViewAsDisposed()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.DoesNotContain("Disposed = _webView == null", source);
    Assert.Contains("Disposed = facts.Disposed", source);
}
```

Add this helper to `RookWebSurfaceTests` if it is not already present:

```csharp
private static string ExtractMethod(string source, string signature)
{
    var start = source.IndexOf(signature, StringComparison.Ordinal);
    if (start < 0)
        return string.Empty;

    var brace = source.IndexOf('{', start);
    if (brace < 0)
        return source.Substring(start);

    var depth = 0;
    for (var i = brace; i < source.Length; i++)
    {
        if (source[i] == '{') depth++;
        if (source[i] == '}') depth--;
        if (depth == 0)
            return source.Substring(start, i - start + 1);
    }

    return source.Substring(start);
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookWebSurfaceTests.VisionPresentationPath"
```

Expected: fail until snapshot/action methods exist.

- [ ] **Step 3: Implement snapshot builder**

In `RookWebSurface.cs`, add:

```csharp
#if ROOK_WEBVIEW2
private void RunHostPresentationCoordinatorReconcile(string reason)
{
    if (_latestPresentationFacts == null)
        return;

    var facts = _latestPresentationFacts;
    var probe = CaptureHostPresentationProbe(facts);
    var decision = _hostPresentation.Evaluate(probe.Snapshot, reason);
    ApplyHostPresentationDecision(decision, probe.Controller, reason);
}

private HostPresentationProbe CaptureHostPresentationProbe(
    WebViewHostPanelPresentationFacts facts)
{
    var controller = TryGetCoreWebView2Controller();
    var controllerAvailable = controller != null;
    var controllerVisible = controllerAvailable &&
        TryGetControllerVisible(controller!, out var isVisible) &&
        isVisible;
    var targetBounds = TryBuildControllerTargetBounds();

    return new HostPresentationProbe(
        controller,
        targetBounds,
        new WebViewHostPresentationSnapshot
        {
            Disposed = facts.Disposed,
            DesiredVisible = facts.DesiredVisible,
            AppActive = facts.AppActive,
            TemporaryDeactivateHidden = facts.TemporaryDeactivateHidden,
            PanelVisible = facts.PanelVisible,
            RequiresSelectedPanel = facts.RequiresSelectedPanel,
            PanelSelectedVisible = facts.PanelSelectedVisible,
            EtoLoaded = _webView?.Loaded == true,
            EtoVisible = _webView?.Visible == true,
            EtoWidth = _webView?.Size.Width ?? 0,
            EtoHeight = _webView?.Size.Height ?? 0,
            ParentWindowPresent = _webView?.ParentWindow != null,
            HwndChainVisible = IsHostHwndChainVisible(),
            HwndClientRectNonZero = IsHostHwndClientRectNonZero(),
            ControllerAvailable = controllerAvailable,
            ControllerParentWindowPresent = controllerAvailable &&
                TryGetControllerParentWindow(controller!, out var parent) &&
                parent != IntPtr.Zero,
            ControllerVisible = controllerVisible,
            ControllerBoundsMatchHostTarget = targetBounds == null ||
                (controllerAvailable &&
                 TryControllerBoundsMatch(controller!, targetBounds))
        });
}

private readonly record struct HostPresentationProbe(
    object? Controller,
    object? TargetBounds,
    WebViewHostPresentationSnapshot Snapshot);
#endif
```

Unknown facts must be conservative false, except unavailable target bounds must be non-blocking as shown above (`ControllerBoundsMatchHostTarget = true` when target is unavailable) so the action sink can still set visible/notify.

- [ ] **Step 4: Add controller helpers**

Add helper methods:

```csharp
#if ROOK_WEBVIEW2
private static bool TryGetControllerVisible(object controller, out bool visible)
{
    visible = false;
    var prop = GetInstanceProperty(controller.GetType(), "IsVisible");
    if (prop == null || !prop.CanRead)
        return false;
    try
    {
        visible = prop.GetValue(controller) is bool b && b;
        return true;
    }
    catch { return false; }
}

private static bool TryGetControllerParentWindow(object controller, out IntPtr hwnd)
{
    hwnd = IntPtr.Zero;
    var prop = GetInstanceProperty(controller.GetType(), "ParentWindow");
    if (prop == null || !prop.CanRead)
        return false;
    try
    {
        var value = prop.GetValue(controller);
        if (value is IntPtr ptr)
        {
            hwnd = ptr;
            return true;
        }
        if (value is nint n)
        {
            hwnd = n;
            return true;
        }
        return false;
    }
    catch { return false; }
}

private object? TryBuildControllerTargetBounds()
{
    var size = _webView?.Size ?? Size.Empty;
    if (size.Width <= 0 || size.Height <= 0)
        return null;

    return new System.Drawing.Rectangle(0, 0, size.Width, size.Height);
}

private static bool TryControllerBoundsMatch(object controller, object targetBounds)
{
    var prop = GetInstanceProperty(controller.GetType(), "Bounds");
    if (prop == null || !prop.CanRead)
        return true;
    try
    {
        return Equals(prop.GetValue(controller), targetBounds);
    }
    catch { return true; }
}
#endif
```

- [ ] **Step 5: Add Win32 HWND chain probes**

Add using:

```csharp
using System.Runtime.InteropServices;
```

Add methods under `#if ROOK_WEBVIEW2`:

```csharp
[DllImport("user32.dll")]
private static extern IntPtr GetParent(IntPtr hWnd);

[DllImport("user32.dll")]
private static extern bool IsWindowVisible(IntPtr hWnd);

[DllImport("user32.dll")]
private static extern bool GetClientRect(IntPtr hWnd, out NativeRect lpRect);

[DllImport("user32.dll")]
private static extern bool GetWindowRect(IntPtr hWnd, out NativeRect lpRect);

private struct NativeRect
{
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
}

private bool IsHostHwndChainVisible()
{
    var hwnd = TryGetHostHwnd();
    if (hwnd == IntPtr.Zero)
        return false;

    var guard = 0;
    while (hwnd != IntPtr.Zero && guard++ < 32)
    {
        if (!IsWindowVisible(hwnd))
            return false;
        hwnd = GetParent(hwnd);
    }

    return true;
}

private bool IsHostHwndClientRectNonZero()
{
    var hwnd = TryGetHostHwnd();
    if (hwnd == IntPtr.Zero)
        return false;

    var guard = 0;
    while (hwnd != IntPtr.Zero && guard++ < 32)
    {
        if (!HasNonZeroRect(hwnd))
            return false;
        hwnd = GetParent(hwnd);
    }

    return true;
}

private IntPtr TryGetHostHwnd()
{
    var nativeControl = _webView?.ControlObject;
    if (nativeControl == null)
        return IntPtr.Zero;

    if (TryReadHandle(nativeControl, out var hwnd))
        return hwnd;

    var webView2 = GetWebView2NativeControl(nativeControl);
    if (webView2 != null && !ReferenceEquals(webView2, nativeControl) &&
        TryReadHandle(webView2, out hwnd))
        return hwnd;

    return IntPtr.Zero;
}

private static bool TryReadHandle(object target, out IntPtr hwnd)
{
    hwnd = IntPtr.Zero;
    var handleProp = GetInstanceProperty(target.GetType(), "Handle");
    if (handleProp == null || !handleProp.CanRead)
        return false;

    try
    {
        var value = handleProp.GetValue(target);
        if (value is IntPtr ptr)
        {
            hwnd = ptr;
            return hwnd != IntPtr.Zero;
        }
        if (value is nint n)
        {
            hwnd = n;
            return hwnd != IntPtr.Zero;
        }
        return false;
    }
    catch { return false; }
}

private static bool HasNonZeroRect(IntPtr hwnd)
{
    if (GetClientRect(hwnd, out var client) &&
        client.Right > client.Left &&
        client.Bottom > client.Top)
    {
        return true;
    }

    if (GetWindowRect(hwnd, out var window) &&
        window.Right > window.Left &&
        window.Bottom > window.Top)
    {
        return true;
    }

    return false;
}
#endif
```

If this exact handle fallback is awkward during implementation, keep the same contract: unknown/failure returns false and never forces presentation.

- [ ] **Step 6: Implement action sink**

Add:

```csharp
#if ROOK_WEBVIEW2
private string ApplyHostPresentationDecision(
    WebViewHostPresentationDecision decision,
    object? controller,
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
            : "set-visible-failed";
    }

    if (decision.Action != WebViewHostPresentationAction.PresentController)
        return "none";

    if (decision.ShouldSetControllerBounds)
    {
        var target = TryBuildControllerTargetBounds();
        if (target != null && !SetControllerBounds(controller, target, reason))
            return "set-bounds-failed";
    }

    if (decision.ShouldSetControllerVisible &&
        !SetControllerVisible(controller, true, reason))
    {
        return "set-visible-failed";
    }

    return NotifyParentWindowPositionChangedWithResult(controller, reason)
        ? "applied"
        : "notify-parent-failed";
}

private bool SetControllerBounds(object controller, object bounds, string reason)
{
    var prop = GetInstanceProperty(controller.GetType(), "Bounds");
    if (prop == null || !prop.CanWrite)
        return false;
    try
    {
        prop.SetValue(controller, bounds);
        return true;
    }
    catch (Exception ex)
    {
        Log($"Rook: WebView2 bounds set failed for surface '{ResourceRoot}' " +
            $"(reason={reason}): {ex.Message}");
        return false;
    }
}

private bool NotifyParentWindowPositionChangedWithResult(
    object controller,
    string reason)
{
    var notifyMethod = controller.GetType().GetMethod(
        "NotifyParentWindowPositionChanged",
        Type.EmptyTypes);
    if (notifyMethod == null)
        return false;
    try
    {
        notifyMethod.Invoke(controller, null);
        return true;
    }
    catch (Exception ex)
    {
        Log($"Rook: WebView2 parent-position notification failed for surface " +
            $"'{ResourceRoot}' (reason={reason}): {ex.Message}");
        return false;
    }
}
#endif
```

Do not call present-side effects outside `ApplyHostPresentationDecision`.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookWebSurfaceTests.VisionPresentationPath"
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add src\Rook\UI\Web\RookWebSurface.cs src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs
git commit -m "feat: evaluate vision webview presentation snapshots"
```

---

## Task 6: Wire RookVisionPanel To Authoritative Facts

**Files:**
- Modify: `src/Rook/UI/Vision/RookVisionPanel.cs`
- Modify: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`

- [ ] **Step 1: Add source contract tests**

Add tests to `RookVisionPanelHostTests`:

```csharp
[Fact]
public void RookVisionPanel_SuppliesPresentationFactsToSurface()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("VisionPanelPresentationState", source);
    Assert.Contains("_surface.ReconcileHostPresentation", source);
    Assert.Contains("RhinoPanelVisibilityQuery", source);
    Assert.Contains("IsSelectedPanelVisible(typeof(RookVisionPanel))", source);
    Assert.Contains("IsPanelVisibleAnyTab(typeof(RookVisionPanel))", source);
}

[Fact]
public void RookVisionPanel_HandlesAppActiveAsAuthoritativeFacts()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged", source);
    Assert.Contains("Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged", source);
    Assert.Contains("_presentationState.SetAppActive", source);
}

[Fact]
public void RookVisionPanel_PanelHiddenAndClosingSendNoPresentFacts()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("_presentationState.PanelHidden", source);
    Assert.Contains("_presentationState.PanelClosing", source);
    Assert.Contains("scheduleIdleFollowUp: false", source);
}

[Fact]
public void RookVisionPanel_DoesNotSendLegacyHostVisibilityCommands()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.DoesNotContain("_surface.ReconcileHostVisibility", source);
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookVisionPanelHostTests"
```

Expected: fail until Vision is wired.

- [ ] **Step 3: Wire state/query in RookVisionPanel**

Modify fields:

```csharp
private readonly IRhinoPanelVisibilityQuery _visibilityQuery =
    new RhinoPanelVisibilityQuery();
private readonly VisionPanelPresentationState _presentationState =
    new(Application.Instance.IsActive);
private Control? _content;
```

In constructor:

```csharp
_content = _surface.CreateWebContent();
_content.SizeChanged += OnContentSizeChanged;
Content = _content;
Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;
```

Panel shown:

```csharp
public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
{
    _documentSerialNumber = documentSerialNumber;
    _lifecycle.PanelShown(documentSerialNumber, reason);
    var facts = _presentationState.PanelShown(
        reason,
        IsVisibleAnyTab(),
        IsSelectedVisible());
    _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: true);
    ReconcileSurface("PanelShown:" + reason);
}
```

Panel hidden:

```csharp
public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
{
    _documentSerialNumber = documentSerialNumber;
    _lifecycle.PanelHidden(documentSerialNumber, reason);
    var facts = _presentationState.PanelHidden(
        reason,
        IsVisibleAnyTab(),
        IsSelectedVisible());
    _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: false);
    ReconcileSurface("PanelHidden:" + reason);
}
```

Panel closing:

```csharp
public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
{
    _documentSerialNumber = documentSerialNumber;
    _lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
    _surface.ReconcileHostPresentation(
        _presentationState.PanelClosing(),
        scheduleIdleFollowUp: false);
    ReconcileSurface("PanelClosing");
}
```

App active:

```csharp
private void OnApplicationIsActiveChanged(object? sender, EventArgs e)
{
    var facts = _presentationState.SetAppActive(Application.Instance.IsActive);
    _surface.ReconcileHostPresentation(
        facts,
        scheduleIdleFollowUp: facts.AppActive);
}
```

Content size/layout:

```csharp
private void OnContentSizeChanged(object? sender, EventArgs e)
{
    var facts = _presentationState.RefreshSelection(
        IsSelectedVisible(),
        "ContentSizeChanged");
    _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: true);
}
```

Helper:

```csharp
private bool IsSelectedVisible()
{
    try { return _visibilityQuery.IsSelectedPanelVisible(typeof(RookVisionPanel)); }
    catch { return false; }
}

private bool IsVisibleAnyTab()
{
    try { return _visibilityQuery.IsPanelVisibleAnyTab(typeof(RookVisionPanel)); }
    catch { return false; }
}
```

Dispose/close:

```csharp
if (_content != null)
{
    try { _content.SizeChanged -= OnContentSizeChanged; } catch { }
    _content = null;
}
try { Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged; } catch { }
```

Keep the existing `_lifecycle` path so old host lifecycle still protects non-presentation behavior. This PR adds Vision's presentation facts; it does not delete the lifecycle adapter.

However, change Vision `ApplyDecision` so it no longer calls `_surface.ReconcileHostVisibility(...)`. For Vision, old lifecycle decisions may close the surface, but visibility/presentation commands must flow only through `_surface.ReconcileHostPresentation(...)`.

Use:

```csharp
private void ApplyDecision(HostedSurfaceDecision decision, string sourceReason)
{
    _ = sourceReason;
    if (decision.Action == HostedSurfaceAction.Close)
    {
        CloseSurface();
    }
}
```

Do not copy this change to Chat or Knowledge Graph.

- [ ] **Step 4: Run Vision panel tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookVisionPanelHostTests|FullyQualifiedName~VisionPanelPresentationStateTests"
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\UI\Vision\RookVisionPanel.cs src\Rook.Tests\UI\Vision\RookVisionPanelHostTests.cs
git commit -m "feat: wire vision presentation facts"
```

---

## Task 7: Behavior Tests For Stale Idle And Durable Hide

**Files:**
- Create: `src/Rook.Tests/UI/Web/WebViewHostPresentationSchedulerTests.cs` if a small testable helper is extracted.
- Or modify: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs` with source contract tests if extraction is not possible.

Recommended implementation: extract the idle token gate into a small pure helper so the critical stale-idle tests are behavioral.

- [ ] **Step 1: Create helper type tests**

If using a helper, create `src/Rook/UI/Web/WebViewHostPresentationIdleGate.cs`:

```csharp
namespace Rook.UI.Web
{
    internal sealed class WebViewHostPresentationIdleGate
    {
        private bool _pending;
        private long _generation;

        public bool TrySchedule(long generation)
        {
            if (_pending)
                return false;
            _pending = true;
            _generation = generation;
            return true;
        }

        public bool ShouldRun(long currentGeneration, bool disposed, bool desiredVisible)
        {
            if (!_pending)
                return false;
            _pending = false;
            return !disposed &&
                desiredVisible &&
                currentGeneration == _generation;
        }

        public void Clear()
        {
            _pending = false;
        }
    }
}
```

Create tests:

```csharp
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class WebViewHostPresentationIdleGateTests
    {
        [Fact]
        public void DelayedIdleAfterHide_DoesNotPresent()
        {
            var gate = new WebViewHostPresentationIdleGate();
            Assert.True(gate.TrySchedule(10));

            Assert.False(gate.ShouldRun(
                currentGeneration: 11,
                disposed: false,
                desiredVisible: false));
        }

        [Fact]
        public void StaleIdleAfterNewerPanelFacts_DoesNotPresent()
        {
            var gate = new WebViewHostPresentationIdleGate();
            Assert.True(gate.TrySchedule(10));

            Assert.False(gate.ShouldRun(
                currentGeneration: 11,
                disposed: false,
                desiredVisible: true));
        }

        [Fact]
        public void MatchingGenerationVisibleSurface_RunsOnce()
        {
            var gate = new WebViewHostPresentationIdleGate();
            Assert.True(gate.TrySchedule(10));

            Assert.True(gate.ShouldRun(
                currentGeneration: 10,
                disposed: false,
                desiredVisible: true));
            Assert.False(gate.ShouldRun(
                currentGeneration: 10,
                disposed: false,
                desiredVisible: true));
        }

        [Fact]
        public void ExistingPendingIdle_Coalesces()
        {
            var gate = new WebViewHostPresentationIdleGate();
            Assert.True(gate.TrySchedule(10));
            Assert.False(gate.TrySchedule(10));
        }
    }
}
```

- [ ] **Step 2: Run tests and verify helper behavior**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~WebViewHostPresentationIdleGateTests"
```

Expected: pass.

- [ ] **Step 3: Use helper in RookWebSurface**

Replace `_hostPresentationIdlePending` / `_hostPresentationIdleGeneration` gate logic with:

```csharp
private readonly WebViewHostPresentationIdleGate _hostPresentationIdleGate = new();
private string _hostPresentationIdleReason = "";
```

Schedule:

```csharp
if (!_hostPresentationIdleGate.TrySchedule(_latestPresentationFacts.Generation))
    return;
_hostPresentationIdleReason = reason;
RhinoApp.Idle += OnHostPresentationIdle;
```

Idle:

```csharp
if (!_hostPresentationIdleGate.ShouldRun(
    _latestPresentationFacts.Generation,
    _disposed || _latestPresentationFacts.Disposed,
    _latestPresentationFacts.DesiredVisible))
{
    return;
}
```

Dispose:

```csharp
_hostPresentationIdleGate.Clear();
```

- [ ] **Step 4: Run focused Web tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web"
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\UI\Web\WebViewHostPresentationIdleGate.cs src\Rook\UI\Web\RookWebSurface.cs src\Rook.Tests\UI\Web\WebViewHostPresentationIdleGateTests.cs
git commit -m "feat: guard vision presentation idle follow-up"
```

---

## Task 8: Focused Validation And PR Preparation

**Files:**
- Verify only.

- [ ] **Step 1: Run focused UI tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web|FullyQualifiedName~Rook.Tests.UI.Vision|FullyQualifiedName~Rook.Tests.UI.Panels|FullyQualifiedName~Rook.Tests.Plugin"
```

Expected: pass.

- [ ] **Step 2: Run full managed suite**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore
```

Expected: pass. Existing warnings are acceptable; failures are not.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no output.

- [ ] **Step 4: Confirm no forbidden runtime changes**

Run:

```powershell
git diff --name-only origin/main...HEAD
```

Expected files should be limited to:

```text
docs/superpowers/specs/2026-05-26-vision-return-edge-presentation-design.md
docs/superpowers/plans/2026-05-26-vision-return-edge-presentation.md
src/Rook/UI/Web/WebViewHostPanelPresentationFacts.cs
src/Rook/UI/Web/WebViewHostPresentationIdleGate.cs
src/Rook/UI/Web/RookWebSurface.cs
src/Rook/UI/Vision/VisionPanelPresentationState.cs
src/Rook/UI/Vision/VisionWebSurface.cs
src/Rook/UI/Vision/RookVisionPanel.cs
src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs
src/Rook.Tests/UI/Web/WebViewHostPresentationIdleGateTests.cs
src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs
src/Rook.Tests/UI/Vision/VisionPanelPresentationStateTests.cs
src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs
```

Chat/KG runtime files must not be modified.

- [ ] **Step 5: Commit plan if not already committed**

```powershell
git add docs\superpowers\plans\2026-05-26-vision-return-edge-presentation.md
git commit -m "docs: plan vision return-edge presentation"
```

- [ ] **Step 6: Push and create draft PR**

Push:

```powershell
git push -u origin codex/vision-return-edge-presentation
```

Create a draft PR against `main`.

PR title:

```text
Deterministic Vision return-edge presentation
```

PR body must state:

- PR #192 remains failed evidence and is not reused as-is.
- Vision opts into the new path; Chat/KG stay old path.
- No flags, reloads, JS probes, or hot-path file logging.
- Live validation is required before ready/merge.

---

## Live Validation Gate

Do not mark the PR ready until live validation passes with diagnostic flags unset.

Before deployment/testing:

```powershell
[Environment]::SetEnvironmentVariable("ROOK_ENABLE_VISION_DARK_DIAGNOSTICS", $null, "User")
[Environment]::SetEnvironmentVariable("ROOK_ENABLE_WEBVIEW_FOCUS_DIAGNOSTICS", $null, "User")
[Environment]::SetEnvironmentVariable("ROOK_PANEL_LIFECYCLE_TRACE", $null, "User")
```

Deploy only after automated tests pass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Required live matrix:

- Vision docked selected tab: repeated click-away/return cycles.
- Vision tabbed behind another panel, then reselect Vision without app refocus.
- Vision gallery/modal path.
- Vision floating/undocked.
- Chat and Knowledge Graph in same Rhino session as old-path controls.

If Rhino becomes unresponsive, stop testing and redeploy `main`.

If Vision goes dark, collect evidence before clicking inside Vision.

---

## Plan Self-Review

Spec coverage:

- App deactivated direct reconcile: Task 6 via `OnApplicationIsActiveChanged`.
- Panel hidden/closing direct reconcile: Task 6.
- Selection-visible concrete source: Task 6 uses `RhinoPanelVisibilityQuery.IsSelectedPanelVisible(typeof(RookVisionPanel))`.
- One-shot idle: Task 4 and Task 7.
- Authoritative generation split from size/layout: Task 3.
- Disposed only on actual close/dispose: Task 3 and Task 5.
- No Chat/KG changes: Task 8 file list gate.
- No flags/logging/JS/reload: Task 4/5 source guards and Task 8.

Placeholder scan:

- No `TBD` or `TODO`.
- Implementation snippets use concrete type and method names.

Type consistency:

- `WebViewHostPanelPresentationFacts` is the shared DTO.
- `VisionPanelPresentationState` owns generation.
- `RookWebSurface.ReconcileHostPresentation(...)` consumes facts.
- `VisionWebSurface` opts in through `UseHostPresentationCoordinator`.
