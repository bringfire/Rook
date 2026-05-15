# Hosted Panel Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared hosted panel lifecycle coordinator so Chat, Claude Code, Vision, and Knowledge browser surfaces survive Rhino docking, floating, activation, tab switching, and reparenting without blanking.

**Architecture:** Add pure lifecycle decision types under `src/Rook/UI/Panels/`, then add a Rhino/Eto adapter that gathers panel facts, handles bounded deferred retries, and emits final decisions to existing hosted surfaces. `RookWebSurface` remains the low-level WebView sink; panel lifecycle truth moves above it.

**Tech Stack:** C# net48, Eto.Forms, RhinoCommon `Rhino.UI.Panels`, xUnit, existing Rook managed test project.

---

## Source Spec

Implement from:

`docs/superpowers/specs/2026-05-15-hosted-panel-lifecycle-design.md`

## File Map

Create:

- `src/Rook/UI/Panels/HostedPanelLifecycleTypes.cs`
  - Pure enums and DTOs: `HostedPanelLifecycleReason`, `HostedSurfaceAction`, `PanelLifecycleFacts`, `HostedSurfaceDecision`.
- `src/Rook/UI/Panels/HostedPanelLifecycleCoordinator.cs`
  - Pure `Decide(...)` implementation and `MaxDeferAttempts`.
- `src/Rook/UI/Panels/IRhinoPanelVisibilityQuery.cs`
  - Test seam for selected Rhino panel visibility.
- `src/Rook/UI/Panels/RhinoPanelVisibilityQuery.cs`
  - Production `Panels.IsPanelVisible(panelType, isSelectedTab: true)` implementation.
- `src/Rook/UI/Panels/HostedPanelLifecycleTrace.cs`
  - Gated, bounded panel lifecycle diagnostics.
- `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`
  - Rhino/Eto adapter, fact capture, coalesced deferred scheduling, trace calls, and decision application.
- `src/Rook.Tests/UI/Panels/HostedPanelLifecycleCoordinatorTests.cs`
  - Rhino-free coordinator unit tests.
- `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`
  - Adapter tests using injected visibility query and direct scheduler hooks.

Modify:

- `src/Rook/UI/Chat/ChatTab.cs`
  - Add stable per-tab hosted surface ID and expose host control identity for lifecycle reconciliation.
- `src/Rook/UI/Vision/VisionTab.cs`
  - Add stable hosted surface ID and lifecycle apply helper if needed.
- `src/Rook/UI/Chat/RookChatPanel.cs`
  - Replace raw `_panelHostVisible`/`PanelHidden -> false` lifecycle with `HostedPanelLifecycleAdapter`.
- `src/Rook/UI/Vision/RookVisionPanel.cs`
  - Replace direct raw lifecycle calls with adapter reconciliation.
- `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
  - Replace direct raw lifecycle calls with adapter reconciliation.
- `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`
  - Update source contract tests for adapter and stable IDs.
- `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`
  - Update source contract tests for Vision and Knowledge adapter usage.
- `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`
  - Update expectations so WebView remains lower-level and does not inspect panel reasons.

Do not modify:

- `src/Rook/UI/Web/RookWebSurface.cs` unless tests reveal a compile-only signature adjustment is required. The intended lifecycle change is above this file.
- Native C++ files.
- Project files.

---

### Task 1: Pure Lifecycle Coordinator

**Files:**
- Create: `src/Rook/UI/Panels/HostedPanelLifecycleTypes.cs`
- Create: `src/Rook/UI/Panels/HostedPanelLifecycleCoordinator.cs`
- Create: `src/Rook.Tests/UI/Panels/HostedPanelLifecycleCoordinatorTests.cs`

- [ ] **Step 1: Write the failing coordinator tests**

Create `src/Rook.Tests/UI/Panels/HostedPanelLifecycleCoordinatorTests.cs`:

```csharp
using Rook.UI.Panels;
using Xunit;

namespace Rook.Tests.UI.Panels
{
    public class HostedPanelLifecycleCoordinatorTests
    {
        private static readonly HostedPanelLifecycleCoordinator Coordinator = new();

        private static PanelLifecycleFacts VisibleReady(
            HostedPanelLifecycleReason reason = HostedPanelLifecycleReason.Show,
            int deferAttempt = 0,
            bool panelReportedVisible = true,
            bool isSelectedTab = true,
            bool isRhinoSelectedPanelVisible = true,
            bool isAttachedToParentWindow = true,
            bool hasNonZeroClientSize = true,
            bool isClosing = false)
        {
            return new PanelLifecycleFacts
            {
                PanelReportedVisible = panelReportedVisible,
                LastReason = reason,
                IsSelectedTab = isSelectedTab,
                IsRhinoSelectedPanelVisible = isRhinoSelectedPanelVisible,
                IsAttachedToParentWindow = isAttachedToParentWindow,
                HasNonZeroClientSize = hasNonZeroClientSize,
                IsClosing = isClosing,
                DeferAttempt = deferAttempt
            };
        }

        [Fact]
        public void Decide_VisibleSelectedAttachedAndSized_Shows()
        {
            var decision = Coordinator.Decide(VisibleReady());

            Assert.Equal(HostedSurfaceAction.Show, decision.Action);
            Assert.Contains("show", decision.Reason.ToLowerInvariant());
        }

        [Fact]
        public void Decide_HideOnDeactivate_NeverHides()
        {
            var facts = VisibleReady(HostedPanelLifecycleReason.HideOnDeactivate);

            var decision = Coordinator.Decide(facts);

            Assert.NotEqual(HostedSurfaceAction.Hide, decision.Action);
            Assert.NotEqual(HostedSurfaceAction.Close, decision.Action);
        }

        [Fact]
        public void Decide_ShowOnDeactivate_ShowsWhenReady()
        {
            var decision = Coordinator.Decide(
                VisibleReady(HostedPanelLifecycleReason.ShowOnDeactivate));

            Assert.Equal(HostedSurfaceAction.Show, decision.Action);
        }

        [Fact]
        public void Decide_ShowOnDeactivate_DefersWhenZeroSize()
        {
            var facts = VisibleReady(
                HostedPanelLifecycleReason.ShowOnDeactivate,
                hasNonZeroClientSize: false);

            var decision = Coordinator.Decide(facts);

            Assert.Equal(HostedSurfaceAction.Defer, decision.Action);
        }

        [Fact]
        public void Decide_RealHide_Hides()
        {
            var facts = VisibleReady(
                HostedPanelLifecycleReason.Hide,
                panelReportedVisible: false);

            var decision = Coordinator.Decide(facts);

            Assert.Equal(HostedSurfaceAction.Hide, decision.Action);
        }

        [Fact]
        public void Decide_RealHideAfterTemporaryDeactivate_Hides()
        {
            var facts = VisibleReady(
                HostedPanelLifecycleReason.Hide,
                panelReportedVisible: false,
                isAttachedToParentWindow: true,
                hasNonZeroClientSize: true);

            var decision = Coordinator.Decide(facts);

            Assert.Equal(HostedSurfaceAction.Hide, decision.Action);
        }

        [Fact]
        public void Decide_UnselectedTab_Hides()
        {
            var decision = Coordinator.Decide(VisibleReady(isSelectedTab: false));

            Assert.Equal(HostedSurfaceAction.Hide, decision.Action);
        }

        [Fact]
        public void Decide_RhinoDockGroupVisibleButPanelTabNotSelected_DoesNotShow()
        {
            var decision = Coordinator.Decide(VisibleReady(
                isRhinoSelectedPanelVisible: false));

            Assert.NotEqual(HostedSurfaceAction.Show, decision.Action);
        }

        [Fact]
        public void Decide_Closing_Closes()
        {
            var decision = Coordinator.Decide(VisibleReady(isClosing: true));

            Assert.Equal(HostedSurfaceAction.Close, decision.Action);
        }

        [Fact]
        public void Decide_VisibleButNoParentWindow_Defers()
        {
            var decision = Coordinator.Decide(VisibleReady(
                isAttachedToParentWindow: false));

            Assert.Equal(HostedSurfaceAction.Defer, decision.Action);
        }

        [Fact]
        public void Decide_VisibleButZeroSize_Defers()
        {
            var decision = Coordinator.Decide(VisibleReady(
                hasNonZeroClientSize: false));

            Assert.Equal(HostedSurfaceAction.Defer, decision.Action);
        }

        [Fact]
        public void Decide_ExhaustedDefer_ReturnsNone()
        {
            var decision = Coordinator.Decide(VisibleReady(
                deferAttempt: HostedPanelLifecycleCoordinator.MaxDeferAttempts,
                hasNonZeroClientSize: false));

            Assert.Equal(HostedSurfaceAction.None, decision.Action);
        }

        [Fact]
        public void Decide_LaterReadyFactsAfterExhaustedDefer_CanShow()
        {
            var decision = Coordinator.Decide(VisibleReady(
                deferAttempt: HostedPanelLifecycleCoordinator.MaxDeferAttempts,
                hasNonZeroClientSize: true));

            Assert.Equal(HostedSurfaceAction.Show, decision.Action);
        }

        [Fact]
        public void Decide_ClosingWinsOverHideOnDeactivate()
        {
            var decision = Coordinator.Decide(
                VisibleReady(
                    HostedPanelLifecycleReason.HideOnDeactivate,
                    isClosing: true));

            Assert.Equal(HostedSurfaceAction.Close, decision.Action);
        }
    }
}
```

- [ ] **Step 2: Run the coordinator tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycleCoordinatorTests"
```

Expected: FAIL because `Rook.UI.Panels` types do not exist.

- [ ] **Step 3: Add the pure lifecycle types**

Create `src/Rook/UI/Panels/HostedPanelLifecycleTypes.cs`:

```csharp
namespace Rook.UI.Panels
{
    internal enum HostedPanelLifecycleReason
    {
        Unknown,
        Show,
        Hide,
        HideOnDeactivate,
        ShowOnDeactivate
    }

    internal enum HostedSurfaceAction
    {
        None,
        Show,
        Hide,
        Defer,
        Close
    }

    internal sealed class PanelLifecycleFacts
    {
        public bool PanelReportedVisible { get; init; }
        public HostedPanelLifecycleReason LastReason { get; init; }
        public bool IsSelectedTab { get; init; }
        public bool IsRhinoSelectedPanelVisible { get; init; }
        public bool IsAttachedToParentWindow { get; init; }
        public bool HasNonZeroClientSize { get; init; }
        public bool IsClosing { get; init; }
        public int DeferAttempt { get; init; }
    }

    internal sealed class HostedSurfaceDecision
    {
        public HostedSurfaceAction Action { get; init; }
        public string Reason { get; init; } = "";
        public int DeferAttempt { get; init; }
    }
}
```

- [ ] **Step 4: Add the coordinator implementation**

Create `src/Rook/UI/Panels/HostedPanelLifecycleCoordinator.cs`:

```csharp
namespace Rook.UI.Panels
{
    internal sealed class HostedPanelLifecycleCoordinator
    {
        public const int MaxDeferAttempts = 3;

        public HostedSurfaceDecision Decide(PanelLifecycleFacts facts)
        {
            if (facts.IsClosing)
            {
                return Decision(HostedSurfaceAction.Close, "closing", facts);
            }

            if (facts.LastReason == HostedPanelLifecycleReason.HideOnDeactivate)
            {
                if (!facts.IsAttachedToParentWindow || !facts.HasNonZeroClientSize)
                    return DeferOrNone("temporary-deactivate-waiting-for-layout", facts);

                return Decision(HostedSurfaceAction.None, "temporary-deactivate", facts);
            }

            if (!facts.IsSelectedTab)
            {
                return Decision(HostedSurfaceAction.Hide, "tab-unselected", facts);
            }

            if (!facts.IsRhinoSelectedPanelVisible)
            {
                return Decision(HostedSurfaceAction.Hide, "rhino-panel-tab-unselected", facts);
            }

            if (!facts.PanelReportedVisible)
            {
                return Decision(HostedSurfaceAction.Hide, "panel-hidden", facts);
            }

            if (!facts.IsAttachedToParentWindow)
            {
                return DeferOrNone("parent-window-not-attached", facts);
            }

            if (!facts.HasNonZeroClientSize)
            {
                return DeferOrNone("zero-client-size", facts);
            }

            return Decision(HostedSurfaceAction.Show, "show-ready", facts);
        }

        private static HostedSurfaceDecision DeferOrNone(
            string reason,
            PanelLifecycleFacts facts)
        {
            if (facts.DeferAttempt >= MaxDeferAttempts)
            {
                return Decision(HostedSurfaceAction.None, reason + ":defer-exhausted", facts);
            }

            return Decision(HostedSurfaceAction.Defer, reason, facts);
        }

        private static HostedSurfaceDecision Decision(
            HostedSurfaceAction action,
            string reason,
            PanelLifecycleFacts facts)
        {
            return new HostedSurfaceDecision
            {
                Action = action,
                Reason = reason,
                DeferAttempt = facts.DeferAttempt
            };
        }
    }
}
```

- [ ] **Step 5: Run the coordinator tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycleCoordinatorTests"
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src\Rook\UI\Panels\HostedPanelLifecycleTypes.cs src\Rook\UI\Panels\HostedPanelLifecycleCoordinator.cs src\Rook.Tests\UI\Panels\HostedPanelLifecycleCoordinatorTests.cs
git commit -m "feat: add hosted panel lifecycle coordinator"
```

---

### Task 2: Adapter, Visibility Query, And Diagnostics

**Files:**
- Create: `src/Rook/UI/Panels/IRhinoPanelVisibilityQuery.cs`
- Create: `src/Rook/UI/Panels/RhinoPanelVisibilityQuery.cs`
- Create: `src/Rook/UI/Panels/HostedPanelLifecycleTrace.cs`
- Create: `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`
- Create: `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`

- [ ] **Step 1: Write the failing adapter tests**

Create `src/Rook.Tests/UI/Panels/HostedPanelLifecycleAdapterTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using Eto.Forms;
using Rhino.UI;
using Rook.UI.Panels;
using Xunit;

namespace Rook.Tests.UI.Panels
{
    public class HostedPanelLifecycleAdapterTests
    {
        private sealed class FakeVisibilityQuery : IRhinoPanelVisibilityQuery
        {
            public bool Visible { get; set; } = true;
            public Type? LastPanelType { get; private set; }

            public bool IsSelectedPanelVisible(Type panelType)
            {
                LastPanelType = panelType;
                return Visible;
            }
        }

        private sealed class TestScheduler
        {
            private readonly Dictionary<string, Action> _pending = new();

            public int ScheduleCount { get; private set; }
            public int PendingCount => _pending.Count;

            public void Schedule(string surfaceId, Action action)
            {
                ScheduleCount++;
                _pending[surfaceId] = action;
            }

            public void Run(string surfaceId)
            {
                var action = _pending[surfaceId];
                _pending.Remove(surfaceId);
                action();
            }
        }

        [Fact]
        public void MapReason_HideOnDeactivate_MapsToHostedReason()
        {
            Assert.Equal(
                HostedPanelLifecycleReason.HideOnDeactivate,
                HostedPanelLifecycleAdapter.MapReasonForTest(ShowPanelReason.HideOnDeactivate));
        }

        [Fact]
        public void MapReason_ShowOnDeactivate_MapsToHostedReason()
        {
            Assert.Equal(
                HostedPanelLifecycleReason.ShowOnDeactivate,
                HostedPanelLifecycleAdapter.MapReasonForTest(ShowPanelReason.ShowOnDeactivate));
        }

        [Fact]
        public void Reconcile_UsesInjectedVisibilityQuery()
        {
            var visibility = new FakeVisibilityQuery { Visible = false };
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), visibility);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: true,
                hasNonZeroClientSize: true,
                decisions.Add);

            Assert.Equal(typeof(Form), visibility.LastPanelType);
            Assert.Single(decisions);
            Assert.NotEqual(HostedSurfaceAction.Show, decisions[0].Action);
        }

        [Fact]
        public void PanelHidden_HideOnDeactivate_DoesNotHideOrCleanup()
        {
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), new FakeVisibilityQuery());
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelHidden(10, ShowPanelReason.HideOnDeactivate);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: true,
                hasNonZeroClientSize: true,
                decisions.Add);

            Assert.Single(decisions);
            Assert.NotEqual(HostedSurfaceAction.Hide, decisions[0].Action);
            Assert.NotEqual(HostedSurfaceAction.Close, decisions[0].Action);
        }

        [Fact]
        public void PanelClosing_ClosesOnlyWhenSurfaceIsReconciled()
        {
            var adapter = new HostedPanelLifecycleAdapter(typeof(Form), new FakeVisibilityQuery());
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelClosing(10, onCloseDocument: false);
            Assert.Empty(decisions);

            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: true,
                hasNonZeroClientSize: true,
                decisions.Add);

            Assert.Single(decisions);
            Assert.Equal(HostedSurfaceAction.Close, decisions[0].Action);
        }

        [Fact]
        public void Reconcile_Defer_CoalescesPendingRetryPerSurface()
        {
            var scheduler = new TestScheduler();
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: false,
                hasNonZeroClientSize: false,
                decisions.Add);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: true,
                hasNonZeroClientSize: false,
                decisions.Add);

            Assert.Equal(1, scheduler.PendingCount);
            Assert.Equal(1, scheduler.ScheduleCount);
        }

        [Fact]
        public void Reconcile_DeferAttemptIncrementsWhenRetryExecutes()
        {
            var scheduler = new TestScheduler();
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: false,
                hasNonZeroClientSize: false,
                decisions.Add);
            scheduler.Run("10:test:1");

            Assert.Contains(decisions, d =>
                d.Action == HostedSurfaceAction.Defer && d.DeferAttempt == 1);
        }

        [Fact]
        public void Reconcile_LaterLifecycleEventResetsDeferBudget()
        {
            var scheduler = new TestScheduler();
            var adapter = new HostedPanelLifecycleAdapter(
                typeof(Form),
                new FakeVisibilityQuery(),
                scheduler.Schedule);
            var decisions = new List<HostedSurfaceDecision>();

            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.SetDeferAttemptForTest("10:test:1", HostedPanelLifecycleCoordinator.MaxDeferAttempts);
            adapter.PanelShown(10, ShowPanelReason.Show);
            adapter.ReconcileForTest(
                "10:test:1",
                isSelectedTab: true,
                isAttachedToParentWindow: false,
                hasNonZeroClientSize: false,
                decisions.Add);

            var last = decisions[decisions.Count - 1];
            Assert.Equal(HostedSurfaceAction.Defer, last.Action);
            Assert.Equal(0, last.DeferAttempt);
        }

        [Fact]
        public void Trace_IsDisabledByDefault()
        {
            Assert.False(HostedPanelLifecycleTrace.IsEnabled());
        }
    }
}
```

- [ ] **Step 2: Run the adapter tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycleAdapterTests"
```

Expected: FAIL because adapter/query/trace types do not exist.

- [ ] **Step 3: Add the visibility query types**

Create `src/Rook/UI/Panels/IRhinoPanelVisibilityQuery.cs`:

```csharp
using System;

namespace Rook.UI.Panels
{
    internal interface IRhinoPanelVisibilityQuery
    {
        bool IsSelectedPanelVisible(Type panelType);
    }
}
```

Create `src/Rook/UI/Panels/RhinoPanelVisibilityQuery.cs`:

```csharp
using System;
using Rhino.UI;

namespace Rook.UI.Panels
{
    internal sealed class RhinoPanelVisibilityQuery : IRhinoPanelVisibilityQuery
    {
        public bool IsSelectedPanelVisible(Type panelType)
        {
            return Panels.IsPanelVisible(panelType, isSelectedTab: true);
        }
    }
}
```

- [ ] **Step 4: Add the gated lifecycle trace**

Create `src/Rook/UI/Panels/HostedPanelLifecycleTrace.cs`:

```csharp
using System;
using System.Globalization;
using System.IO;

namespace Rook.UI.Panels
{
    internal static class HostedPanelLifecycleTrace
    {
        private const long MaxBytes = 512 * 1024;
        private const string FileName = "panel-lifecycle.log";

        public static bool IsEnabled()
        {
            return string.Equals(
                Environment.GetEnvironmentVariable("ROOK_PANEL_LIFECYCLE_TRACE"),
                "1",
                StringComparison.Ordinal);
        }

        public static void Record(
            string panelType,
            uint documentSerial,
            string surfaceId,
            string eventName,
            PanelLifecycleFacts facts,
            HostedSurfaceDecision decision,
            string detail = "")
        {
            if (!IsEnabled())
                return;

            try
            {
                var logDir = GetLogDirectory();
                Directory.CreateDirectory(logDir);
                var path = Path.Combine(logDir, FileName);
                RotateIfNeeded(path);
                var line =
                    DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture) +
                    "\tpanel=" + Sanitize(panelType) +
                    "\tdoc=" + documentSerial.ToString(CultureInfo.InvariantCulture) +
                    "\tsurface=" + Sanitize(surfaceId) +
                    "\tevent=" + Sanitize(eventName) +
                    "\treason=" + facts.LastReason +
                    "\treportedVisible=" + facts.PanelReportedVisible +
                    "\tselectedTab=" + facts.IsSelectedTab +
                    "\trhinoSelectedVisible=" + facts.IsRhinoSelectedPanelVisible +
                    "\tattached=" + facts.IsAttachedToParentWindow +
                    "\tnonzeroSize=" + facts.HasNonZeroClientSize +
                    "\tclosing=" + facts.IsClosing +
                    "\tdeferAttempt=" + facts.DeferAttempt.ToString(CultureInfo.InvariantCulture) +
                    "\taction=" + decision.Action +
                    "\tdecisionReason=" + Sanitize(decision.Reason) +
                    "\tdetail=" + Sanitize(detail) +
                    Environment.NewLine;
                File.AppendAllText(path, line);
            }
            catch
            {
                // Diagnostics must never affect panel behavior.
            }
        }

        private static string GetLogDirectory()
        {
            var root = Environment.GetEnvironmentVariable("ROOK_DATA_DIR");
            if (string.IsNullOrWhiteSpace(root))
            {
                root = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "Rook");
            }

            return Path.Combine(root, "logs");
        }

        private static void RotateIfNeeded(string path)
        {
            var info = new FileInfo(path);
            if (!info.Exists || info.Length < MaxBytes)
                return;

            var rotated = path + ".1";
            if (File.Exists(rotated))
                File.Delete(rotated);
            File.Move(path, rotated);
        }

        private static string Sanitize(string value)
        {
            return value
                .Replace('\t', ' ')
                .Replace('\r', ' ')
                .Replace('\n', ' ');
        }
    }
}
```

- [ ] **Step 5: Add the lifecycle adapter**

Create `src/Rook/UI/Panels/HostedPanelLifecycleAdapter.cs`:

```csharp
using System;
using System.Collections.Generic;
using Eto.Forms;
using Rhino.UI;

namespace Rook.UI.Panels
{
    internal sealed class HostedPanelLifecycleAdapter
    {
        private readonly Type _panelType;
        private readonly IRhinoPanelVisibilityQuery _visibilityQuery;
        private readonly Action<string, Action> _schedule;
        private readonly HostedPanelLifecycleCoordinator _coordinator = new();
        private readonly Dictionary<string, SurfaceState> _surfaces = new();
        private uint _documentSerialNumber;
        private bool _panelReportedVisible;
        private bool _closing;
        private HostedPanelLifecycleReason _lastReason = HostedPanelLifecycleReason.Unknown;
        private int _transitionVersion;

        public HostedPanelLifecycleAdapter(Type panelType)
            : this(panelType, new RhinoPanelVisibilityQuery())
        {
        }

        internal HostedPanelLifecycleAdapter(
            Type panelType,
            IRhinoPanelVisibilityQuery visibilityQuery)
            : this(panelType, visibilityQuery, ScheduleOnUiThread)
        {
        }

        internal HostedPanelLifecycleAdapter(
            Type panelType,
            IRhinoPanelVisibilityQuery visibilityQuery,
            Action<string, Action> schedule)
        {
            _panelType = panelType ?? throw new ArgumentNullException(nameof(panelType));
            _visibilityQuery = visibilityQuery ?? throw new ArgumentNullException(nameof(visibilityQuery));
            _schedule = schedule ?? throw new ArgumentNullException(nameof(schedule));
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _panelReportedVisible = true;
            _closing = false;
            _lastReason = MapReason(reason);
            BeginNewTransition();
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lastReason = MapReason(reason);
            if (_lastReason != HostedPanelLifecycleReason.HideOnDeactivate)
                _panelReportedVisible = false;
            BeginNewTransition();
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            _ = onCloseDocument;
            _documentSerialNumber = documentSerialNumber;
            _closing = true;
            BeginNewTransition();
        }

        public void Reconcile(
            string surfaceId,
            bool isSelectedTab,
            Control hostControl,
            Action<HostedSurfaceDecision> apply)
        {
            if (hostControl == null)
                throw new ArgumentNullException(nameof(hostControl));

            ReconcileCore(
                surfaceId,
                isSelectedTab,
                IsAttached(hostControl),
                HasNonZeroClientSize(hostControl),
                apply,
                eventName: "Reconcile");
        }

        internal void ReconcileForTest(
            string surfaceId,
            bool isSelectedTab,
            bool isAttachedToParentWindow,
            bool hasNonZeroClientSize,
            Action<HostedSurfaceDecision> apply)
        {
            ReconcileCore(
                surfaceId,
                isSelectedTab,
                isAttachedToParentWindow,
                hasNonZeroClientSize,
                apply,
                eventName: "ReconcileForTest");
        }

        internal void SetDeferAttemptForTest(string surfaceId, int deferAttempt)
        {
            GetState(surfaceId).DeferAttempt = deferAttempt;
        }

        internal static HostedPanelLifecycleReason MapReasonForTest(ShowPanelReason reason)
        {
            return MapReason(reason);
        }

        private void ReconcileCore(
            string surfaceId,
            bool isSelectedTab,
            bool isAttachedToParentWindow,
            bool hasNonZeroClientSize,
            Action<HostedSurfaceDecision> apply,
            string eventName)
        {
            if (string.IsNullOrWhiteSpace(surfaceId))
                throw new ArgumentException("Surface id is required.", nameof(surfaceId));
            if (apply == null)
                throw new ArgumentNullException(nameof(apply));

            var state = GetState(surfaceId);
            state.LastSelectedTab = isSelectedTab;
            state.LastAttached = isAttachedToParentWindow;
            state.LastNonZeroSize = hasNonZeroClientSize;
            state.LastApply = apply;
            state.LastEventName = eventName;
            state.TransitionVersion = _transitionVersion;

            var facts = CaptureFacts(state);
            var decision = _coordinator.Decide(facts);
            HostedPanelLifecycleTrace.Record(
                _panelType.Name,
                _documentSerialNumber,
                surfaceId,
                eventName,
                facts,
                decision);

            if (decision.Action == HostedSurfaceAction.Defer)
            {
                ScheduleDeferred(surfaceId, state);
                apply(decision);
                return;
            }

            state.PendingRetry = false;
            apply(decision);
        }

        private PanelLifecycleFacts CaptureFacts(SurfaceState state)
        {
            return new PanelLifecycleFacts
            {
                PanelReportedVisible = _panelReportedVisible,
                LastReason = _lastReason,
                IsSelectedTab = state.LastSelectedTab,
                IsRhinoSelectedPanelVisible = _visibilityQuery.IsSelectedPanelVisible(_panelType),
                IsAttachedToParentWindow = state.LastAttached,
                HasNonZeroClientSize = state.LastNonZeroSize,
                IsClosing = _closing,
                DeferAttempt = state.DeferAttempt
            };
        }

        private void ScheduleDeferred(string surfaceId, SurfaceState state)
        {
            if (state.PendingRetry)
                return;

            state.PendingRetry = true;
            var transitionVersion = _transitionVersion;

            _schedule(surfaceId, () =>
            {
                state.PendingRetry = false;
                if (state.TransitionVersion != transitionVersion)
                    return;

                state.DeferAttempt++;
                if (state.LastApply == null)
                    return;

                ReconcileCore(
                    surfaceId,
                    state.LastSelectedTab,
                    state.LastAttached,
                    state.LastNonZeroSize,
                    state.LastApply,
                    "DeferredRetry");
            });
        }

        private void BeginNewTransition()
        {
            _transitionVersion++;
            foreach (var state in _surfaces.Values)
            {
                state.DeferAttempt = 0;
                state.PendingRetry = false;
                state.TransitionVersion = _transitionVersion;
            }
        }

        private SurfaceState GetState(string surfaceId)
        {
            if (!_surfaces.TryGetValue(surfaceId, out var state))
            {
                state = new SurfaceState
                {
                    TransitionVersion = _transitionVersion
                };
                _surfaces.Add(surfaceId, state);
            }

            return state;
        }

        private static bool IsAttached(Control control)
        {
            return control.ParentWindow != null || control.Parent != null;
        }

        private static bool HasNonZeroClientSize(Control control)
        {
            return control.ClientSize.Width > 0 && control.ClientSize.Height > 0;
        }

        private static HostedPanelLifecycleReason MapReason(ShowPanelReason reason)
        {
            return reason switch
            {
                ShowPanelReason.Show => HostedPanelLifecycleReason.Show,
                ShowPanelReason.Hide => HostedPanelLifecycleReason.Hide,
                ShowPanelReason.HideOnDeactivate => HostedPanelLifecycleReason.HideOnDeactivate,
                ShowPanelReason.ShowOnDeactivate => HostedPanelLifecycleReason.ShowOnDeactivate,
                _ => HostedPanelLifecycleReason.Unknown
            };
        }

        private static void ScheduleOnUiThread(string surfaceId, Action action)
        {
            _ = surfaceId;
            try
            {
                Application.Instance.AsyncInvoke(action);
            }
            catch
            {
                action();
            }
        }

        private sealed class SurfaceState
        {
            public bool LastSelectedTab { get; set; }
            public bool LastAttached { get; set; }
            public bool LastNonZeroSize { get; set; }
            public Action<HostedSurfaceDecision>? LastApply { get; set; }
            public string LastEventName { get; set; } = "";
            public int DeferAttempt { get; set; }
            public bool PendingRetry { get; set; }
            public int TransitionVersion { get; set; }
        }
    }
}
```

- [ ] **Step 6: Run the adapter tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycleAdapterTests"
```

Expected: PASS.

- [ ] **Step 7: Run coordinator and adapter tests together**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycle"
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add src\Rook\UI\Panels src\Rook.Tests\UI\Panels
git commit -m "feat: add hosted panel lifecycle adapter"
```

---

### Task 3: Chat Panel Migration

**Files:**
- Modify: `src/Rook/UI/Chat/ChatTab.cs`
- Modify: `src/Rook/UI/Vision/VisionTab.cs`
- Modify: `src/Rook/UI/Chat/RookChatPanel.cs`
- Modify: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

- [ ] **Step 1: Replace obsolete Chat source contract tests with failing adapter contract tests**

Modify `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`.

Remove these obsolete tests because `HostedPanelLifecycleCoordinator` now owns the old tab-visibility decision:

```csharp
HostedWebSurfaceVisibility_PanelShownWithMultipleTabs_OnlyShowsSelectedPage
HostedWebSurfaceVisibility_TabSwitch_HidesOldPageAndShowsNewPage
HostedWebSurfaceVisibility_PanelHidden_HidesEveryPage
```

Replace `RookChatPanel_PanelLifecycle_ReconcilesHostedWebSurfaces` with:

```csharp
[Fact]
public void RookChatPanel_UsesHostedPanelLifecycleAdapter()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

    Assert.Contains("HostedPanelLifecycleAdapter", source);
    Assert.Contains("typeof(RookChatPanel)", source);
    Assert.DoesNotContain("ReconcileHostedWebSurfaces(tabControl, false, \"PanelHidden:\" + reason)", source);
}
```

Replace `RookChatPanel_TabSelectionChanged_ReconcilesHostedWebSurfaces` with:

```csharp
[Fact]
public void RookChatPanel_TabSelectionChanged_ReconcilesThroughLifecycleAdapter()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

    Assert.Contains("SelectedIndexChanged += OnTabSelectedIndexChanged", source);
    Assert.Contains("SelectedIndexChanged -= OnTabSelectedIndexChanged", source);
    Assert.Contains("ReconcileHostedWebSurfaces(tabControl, \"TabSelectionChanged\")", source);
    Assert.DoesNotContain("_panelHostVisible", source);
}
```

Add:

```csharp

[Fact]
public void RookChatPanel_ReconcilesClosingPerHostedSurface()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

    Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", source);
    Assert.Contains("ReconcileHostedWebSurfaces", source);
    Assert.Contains("HostedSurfaceAction.Close", source);
}

[Fact]
public void ChatTabs_ExposeStableHostedSurfaceIds()
{
    var chatTabSource = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
    var visionTabSource = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionTab.cs");

    Assert.Contains("HostedSurfaceId", chatTabSource);
    Assert.Contains("Interlocked.Increment", chatTabSource);
    Assert.Contains("HostedSurfaceId", visionTabSource);
    Assert.Contains("Interlocked.Increment", visionTabSource);
}
```

- [ ] **Step 2: Run the Chat tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RookChatPanelTests"
```

Expected: FAIL because Chat has not migrated to the adapter and tab IDs do not exist.

- [ ] **Step 3: Add stable hosted surface ID to `ChatTab`**

Modify `src/Rook/UI/Chat/ChatTab.cs`:

Add this using:

```csharp
using System.Threading;
```

Inside `public abstract class ChatTab : Panel`, add:

```csharp
private static int s_nextHostedSurfaceId;

internal string HostedSurfaceId { get; } =
    "chat-tab:" + Interlocked.Increment(ref s_nextHostedSurfaceId).ToString();
```

Leave existing `ReconcileHostVisibility(bool visible, string reason)` intact.

- [ ] **Step 4: Add stable hosted surface ID to `VisionTab`**

Modify `src/Rook/UI/Vision/VisionTab.cs`:

Add this using:

```csharp
using System.Threading;
```

Inside `public sealed class VisionTab : Panel`, add:

```csharp
private static int s_nextHostedSurfaceId;

internal string HostedSurfaceId { get; } =
    "vision-tab:" + Interlocked.Increment(ref s_nextHostedSurfaceId).ToString();
```

Leave existing `ReconcileHostVisibility(bool visible, string reason)` intact.

- [ ] **Step 5: Add adapter field and decision application in `RookChatPanel`**

Modify `src/Rook/UI/Chat/RookChatPanel.cs`:

Add using:

```csharp
using Rook.UI.Panels;
```

Add a field near the existing fields:

```csharp
private readonly HostedPanelLifecycleAdapter _lifecycle =
    new(typeof(RookChatPanel));
```

Replace `ReconcileHostedWebSurfaces(...)` with:

```csharp
private void ReconcileHostedWebSurfaces(
    TabControl tabControl,
    string reason)
{
    for (var i = 0; i < tabControl.Pages.Count; i++)
    {
        var page = tabControl.Pages[i];
        var selected = i == tabControl.SelectedIndex;

        if (page.Content is ChatTab chatTab)
        {
            var surfaceId = BuildSurfaceId(chatTab.HostedSurfaceId);
            _lifecycle.Reconcile(
                surfaceId,
                selected,
                chatTab,
                decision => ApplyHostedSurfaceDecision(chatTab, decision, reason));
        }
        else if (page.Content is VisionTab visionTab)
        {
            var surfaceId = BuildSurfaceId(visionTab.HostedSurfaceId);
            _lifecycle.Reconcile(
                surfaceId,
                selected,
                visionTab,
                decision => ApplyHostedSurfaceDecision(visionTab, decision, reason));
        }
    }
}

private string BuildSurfaceId(string tabSurfaceId)
{
    return _documentSerialNumber.ToString() + ":" + tabSurfaceId;
}

private void ApplyHostedSurfaceDecision(
    ChatTab tab,
    HostedSurfaceDecision decision,
    string sourceReason)
{
    switch (decision.Action)
    {
        case HostedSurfaceAction.Show:
            tab.ReconcileHostVisibility(true, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Hide:
            tab.ReconcileHostVisibility(false, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Close:
            tab.OnTabClosed();
            break;
    }
}

private void ApplyHostedSurfaceDecision(
    VisionTab tab,
    HostedSurfaceDecision decision,
    string sourceReason)
{
    switch (decision.Action)
    {
        case HostedSurfaceAction.Show:
            tab.ReconcileHostVisibility(true, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Hide:
            tab.ReconcileHostVisibility(false, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Close:
            tab.OnTabClosed();
            break;
    }
}
```

If `_documentSerialNumber` is not already a field, add:

```csharp
private uint _documentSerialNumber;
```

and keep it updated in `ShowDocumentTabs(...)` or `PanelShown(...)` with the normalized serial.

- [ ] **Step 6: Wire Chat panel lifecycle events to the adapter**

In `RookChatPanel.PanelShown(...)`, after normalizing document serial:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelShown(documentSerialNumber, reason);
```

Replace the final raw reconciliation call with:

```csharp
ReconcileHostedWebSurfaces(tabControl, "PanelShown:" + reason);
```

In `RookChatPanel.PanelHidden(...)`, replace raw visibility mutation and false reconciliation with:

```csharp
documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelHidden(documentSerialNumber, reason);
if (_tabControlsByDocument.TryGetValue(documentSerialNumber, out var tabControl))
{
    ReconcileHostedWebSurfaces(tabControl, "PanelHidden:" + reason);
}
```

In `RookChatPanel.PanelClosing(...)`, replace the no-op body with:

```csharp
documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
if (_tabControlsByDocument.TryGetValue(documentSerialNumber, out var tabControl))
{
    ReconcileHostedWebSurfaces(tabControl, "PanelClosing");
}
```

Replace other call sites:

```csharp
ReconcileHostedWebSurfaces(owner, "TabRemoved");
ReconcileHostedWebSurfaces(tabControl, "TabSelectionChanged");
```

Remove `_panelHostVisible` if it is no longer used.

Remove the old `HostedWebSurfaceVisibility` helper from `RookChatPanel.cs` once the panel delegates per-surface decisions to `HostedPanelLifecycleAdapter`.

- [ ] **Step 7: Run Chat panel tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RookChatPanelTests"
```

Expected: PASS.

- [ ] **Step 8: Run lifecycle and Chat tests together**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycle|FullyQualifiedName~RookChatPanelTests"
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

Run:

```powershell
git add src\Rook\UI\Chat\ChatTab.cs src\Rook\UI\Vision\VisionTab.cs src\Rook\UI\Chat\RookChatPanel.cs src\Rook.Tests\UI\Chat\RookChatPanelTests.cs
git commit -m "feat: route chat hosted surfaces through lifecycle adapter"
```

---

### Task 4: Dedicated Vision And Knowledge Panel Migration

**Files:**
- Modify: `src/Rook/UI/Vision/RookVisionPanel.cs`
- Modify: `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
- Modify: `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs`

- [ ] **Step 1: Add failing source contract tests for dedicated panels**

Modify `src/Rook.Tests/UI/Vision/RookVisionPanelHostTests.cs` by adding or updating tests:

```csharp
[Fact]
public void RookVisionPanel_UsesHostedPanelLifecycleAdapter()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

    Assert.Contains("HostedPanelLifecycleAdapter", source);
    Assert.Contains("typeof(RookVisionPanel)", source);
    Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, \"PanelHidden:\" + reason)", source);
}

[Fact]
public void KnowledgeGraphPanel_UsesHostedPanelLifecycleAdapter()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

    Assert.Contains("HostedPanelLifecycleAdapter", source);
    Assert.Contains("typeof(KnowledgeGraphPanel)", source);
    Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, \"PanelHidden:\" + reason)", source);
}

[Fact]
public void DedicatedPanels_ReconcileClosingThroughLifecycleAdapter()
{
    var visionSource = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
    var knowledgeSource = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

    Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", visionSource);
    Assert.Contains("HostedSurfaceAction.Close", visionSource);
    Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", knowledgeSource);
    Assert.Contains("HostedSurfaceAction.Close", knowledgeSource);
}
```

- [ ] **Step 2: Run dedicated panel tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RookVisionPanelHostTests"
```

Expected: FAIL because Vision and Knowledge do not yet use the adapter.

- [ ] **Step 3: Migrate `RookVisionPanel`**

Modify `src/Rook/UI/Vision/RookVisionPanel.cs`:

Add using:

```csharp
using System.Threading;
using Rook.UI.Panels;
```

Add fields:

```csharp
private static int s_nextPanelInstanceId;
private readonly HostedPanelLifecycleAdapter _lifecycle =
    new(typeof(RookVisionPanel));
private readonly string _surfaceId;
```

In constructor, initialize before `Content = ...`:

```csharp
_surfaceId = documentSerialNumber.ToString() +
    ":vision-panel:" +
    Interlocked.Increment(ref s_nextPanelInstanceId).ToString();
```

Replace `PanelShown(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelShown(documentSerialNumber, reason);
ReconcileSurface("PanelShown:" + reason);
```

Replace `PanelHidden(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelHidden(documentSerialNumber, reason);
ReconcileSurface("PanelHidden:" + reason);
```

Replace `PanelClosing(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
ReconcileSurface("PanelClosing");
```

Add:

```csharp
private void ReconcileSurface(string reason)
{
    _lifecycle.Reconcile(
        _surfaceId,
        isSelectedTab: true,
        this,
        decision => ApplyDecision(decision, reason));
}

private void ApplyDecision(HostedSurfaceDecision decision, string sourceReason)
{
    switch (decision.Action)
    {
        case HostedSurfaceAction.Show:
            _surface.ReconcileHostVisibility(true, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Hide:
            _surface.ReconcileHostVisibility(false, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Close:
            CloseSurface();
            break;
    }
}
```

- [ ] **Step 4: Migrate `KnowledgeGraphPanel`**

Modify `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`:

Add using:

```csharp
using Rook.UI.Panels;
```

`System.Threading` already exists in this file. Add fields:

```csharp
private static int s_nextPanelInstanceId;
private readonly HostedPanelLifecycleAdapter _lifecycle =
    new(typeof(KnowledgeGraphPanel));
private readonly string _surfaceId;
```

In constructor, initialize before `Content = ...`:

```csharp
_surfaceId = documentSerialNumber.ToString() +
    ":knowledge-graph:" +
    Interlocked.Increment(ref s_nextPanelInstanceId).ToString();
```

Replace `PanelShown(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelShown(documentSerialNumber, reason);
ReconcileSurface("PanelShown:" + reason);

_ = Task.Run(() => _bootstrap.RequestBootstrapAsync(default));
```

Replace `PanelHidden(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelHidden(documentSerialNumber, reason);
ReconcileSurface("PanelHidden:" + reason);
```

Replace `PanelClosing(...)` body with:

```csharp
_documentSerialNumber = documentSerialNumber;
_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
ReconcileSurface("PanelClosing");
```

Add:

```csharp
private void ReconcileSurface(string reason)
{
    _lifecycle.Reconcile(
        _surfaceId,
        isSelectedTab: true,
        this,
        decision => ApplyDecision(decision, reason));
}

private void ApplyDecision(HostedSurfaceDecision decision, string sourceReason)
{
    switch (decision.Action)
    {
        case HostedSurfaceAction.Show:
            _surface.ReconcileHostVisibility(true, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Hide:
            _surface.ReconcileHostVisibility(false, sourceReason + ":" + decision.Reason);
            break;
        case HostedSurfaceAction.Close:
            CloseSurface();
            break;
    }
}
```

- [ ] **Step 5: Run dedicated panel tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RookVisionPanelHostTests"
```

Expected: PASS.

- [ ] **Step 6: Run all UI panel lifecycle tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycle|FullyQualifiedName~RookChatPanelTests|FullyQualifiedName~RookVisionPanelHostTests"
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src\Rook\UI\Vision\RookVisionPanel.cs src\Rook\UI\Knowledge\KnowledgeGraphPanel.cs src\Rook.Tests\UI\Vision\RookVisionPanelHostTests.cs
git commit -m "feat: route dedicated hosted panels through lifecycle adapter"
```

---

### Task 5: WebView Boundary And Regression Tests

**Files:**
- Modify: `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs`
- Optionally inspect: `src/Rook/UI/Web/RookWebSurface.cs`

- [ ] **Step 1: Add boundary tests that keep WebView lower-level**

Modify `src/Rook.Tests/UI/Web/RookWebSurfaceTests.cs` by adding:

```csharp
[Fact]
public void RookWebSurface_DoesNotOwnRhinoPanelLifecycleReasons()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Web", "RookWebSurface.cs");

    Assert.DoesNotContain("ShowPanelReason", source);
    Assert.DoesNotContain("HideOnDeactivate", source);
    Assert.DoesNotContain("ShowOnDeactivate", source);
}
```

- [ ] **Step 2: Run Web surface tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~RookWebSurfaceTests"
```

Expected: PASS. If this fails because `RookWebSurface` already contains any Rhino panel reason strings, remove that coupling and keep reason interpretation in `HostedPanelLifecycleAdapter`.

- [ ] **Step 3: Run full managed UI test subset**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI"
```

Expected: PASS.

- [ ] **Step 4: Commit Task 5**

Run:

```powershell
git add src\Rook.Tests\UI\Web\RookWebSurfaceTests.cs src\Rook\UI\Web\RookWebSurface.cs
git commit -m "test: pin hosted panel lifecycle boundary"
```

If `src\Rook\UI\Web\RookWebSurface.cs` was not changed, omit it from `git add`.

---

### Task 6: Verification, Build, Deploy, And Manual Rhino Smoke

**Files:**
- No planned source changes.

- [ ] **Step 1: Run focused managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~HostedPanelLifecycle|FullyQualifiedName~RookChatPanelTests|FullyQualifiedName~RookVisionPanelHostTests|FullyQualifiedName~RookWebSurfaceTests"
```

Expected: PASS.

- [ ] **Step 2: Run broader managed UI tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI"
```

Expected: PASS.

- [ ] **Step 3: Build and auto-deploy managed plugin**

Verify Rhino is closed:

```powershell
Get-Process -Name "Rhino","Rhinoceros" -ErrorAction SilentlyContinue
```

Expected: no Rhino/Rhinoceros processes. If any are listed, close Rhino before building so the plugin files are not locked.

Run the net7.0 managed build. `src\Rook\Rook.csproj` has an existing `DeployToRhino` target that copies `Rook.rhp`, `Rook.deps.json`, `Rook.runtimeconfig.json`, and `Rook.pdb` into `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative` when that folder exists:

```powershell
dotnet build src\Rook\Rook.csproj -c Debug -f net7.0
```

Expected: build succeeds and logs `Deployed Rook.rhp to ...\Plug-ins\RookNative`.

- [ ] **Step 4: Verify deployed managed plugin artifacts**

Run:

```powershell
$deploy = "C:\Users\aryan\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
Get-Item "$deploy\Rook.rhp", "$deploy\Rook.deps.json", "$deploy\Rook.runtimeconfig.json" |
    Select-Object FullName, Length, LastWriteTime
```

Expected: all three files exist, have nonzero length, and `LastWriteTime` matches the current build.

- [ ] **Step 5: Run manual smoke with lifecycle trace enabled**

Set:

```powershell
$env:ROOK_PANEL_LIFECYCLE_TRACE = "1"
```

Then launch Rhino and test:

1. Open Rook Chat.
2. Open an Agent Chat tab.
3. Open a Claude Code tab.
4. Open dedicated Rook Vision panel.
5. Open Knowledge Graph panel.
6. Float, dock, undock, resize, and switch Rhino dock tabs.
7. Deactivate and reactivate Rhino.
8. Switch Chat tabs repeatedly.
9. Confirm surfaces do not blank.
10. Confirm trace shows `HideOnDeactivate` did not produce `Hide`.
11. Confirm docking/reparenting shows bounded `Defer -> Show` rather than reload/teardown.

- [ ] **Step 6: Inspect lifecycle trace**

Expected log:

```text
%APPDATA%\Rook\logs\panel-lifecycle.log
```

Verify entries contain metadata only: panel type, document serial, surface id, event, lifecycle reason, visibility facts, defer attempt, action, and final reason.

Verify entries do not contain prompts, chat messages, model output, WebView content, or user file contents.

- [ ] **Step 7: Final status check**

Run:

```powershell
git status --short
```

Expected: clean.

If manual-smoke notes need to be captured, add them to the PR description instead of committing temporary logs.
