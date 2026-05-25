# WebView Host Presentation Coordinator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, testable WebView host presentation state machine that defines when Rook may present WebView2 inside a Rhino/Eto host.

**Architecture:** This PR adds a coordinator contract beside `RookWebSurface` without wiring it into runtime behavior. The coordinator consumes plain snapshot data from future adapters, retains only its previous state, and emits action intent plus correction flags. Existing `WebViewHostVisibilityCoordinator`, Vision, Chat, and Knowledge Graph runtime behavior remain unchanged in this PR.

**Tech Stack:** C# net48, xUnit, Rook managed companion, WebView2 concepts modeled as plain data only.

---

## File Structure

- Create `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`: internal coordinator, snapshot, decision, state, action, and reason types.
- Create `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`: fake-snapshot tests for transitions, gate priority, idempotency, and action flags.
- Modify `docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md`: already refined with the combined correction test and `HideController` flag semantics.

No `.csproj` changes are expected. SDK-style project globbing should include the new C# files automatically.

---

### Task 1: Add Coordinator Contract Tests

**Files:**
- Create: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`

- [ ] **Step 1: Create the failing test file**

Create `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs` with this complete content:

```csharp
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class WebViewHostPresentationCoordinatorTests
    {
        private static WebViewHostPresentationSnapshot ReadySnapshot(
            bool controllerVisible = true,
            bool boundsMatch = true)
        {
            return new WebViewHostPresentationSnapshot
            {
                DesiredVisible = true,
                AppActive = true,
                TemporaryDeactivateHidden = false,
                PanelVisible = true,
                RequiresSelectedPanel = true,
                PanelSelectedVisible = true,
                EtoLoaded = true,
                EtoVisible = true,
                EtoWidth = 640,
                EtoHeight = 480,
                ParentWindowPresent = true,
                HwndChainVisible = true,
                HwndClientRectNonZero = true,
                ControllerAvailable = true,
                ControllerParentWindowPresent = true,
                ControllerVisible = controllerVisible,
                ControllerBoundsMatchHostTarget = boundsMatch
            };
        }

        private static void AssertPresentAction(
            WebViewHostPresentationDecision decision,
            bool setBounds,
            bool setVisible)
        {
            Assert.Equal(WebViewHostPresentationState.Presenting, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.PresentController, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.None, decision.NotPresentableReason);
            Assert.Equal(setBounds, decision.ShouldSetControllerBounds);
            Assert.Equal(setVisible, decision.ShouldSetControllerVisible);
            Assert.True(decision.ShouldNotifyParentPositionChanged);
        }

        [Fact]
        public void UserHide_HidesAndEntersHidden()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot() with
            {
                DesiredVisible = false,
                ControllerVisible = true
            };

            var decision = coordinator.Evaluate(snapshot, "user-hide");

            Assert.Equal(WebViewHostPresentationState.Hidden, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.HideController, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.None, decision.NotPresentableReason);
            Assert.False(decision.ShouldSetControllerBounds);
            Assert.False(decision.ShouldSetControllerVisible);
            Assert.False(decision.ShouldNotifyParentPositionChanged);
        }

        [Fact]
        public void PanelNotSelected_WhenSelectionRequired_EntersPendingHost()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: false) with
            {
                PanelSelectedVisible = false
            };

            var decision = coordinator.Evaluate(snapshot, "panel-not-selected");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.PanelNotSelected, decision.NotPresentableReason);
        }

        [Fact]
        public void PanelNotSelected_WithVisibleController_HidesControllerButKeepsDesiredVisible()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: true) with
            {
                PanelSelectedVisible = false
            };

            var decision = coordinator.Evaluate(snapshot, "panel-not-selected");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.HideController, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.PanelNotSelected, decision.NotPresentableReason);
            Assert.False(decision.ShouldSetControllerVisible);
        }

        [Fact]
        public void PanelSelectedAgain_WithHostReady_Presents()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                PanelSelectedVisible = false
            }, "panel-not-selected");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false), "panel-selected");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.OldState);
            AssertPresentAction(decision, setBounds: false, setVisible: true);
        }

        [Fact]
        public void InactiveTemporaryDeactivate_BlocksPresentation()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: false) with
            {
                AppActive = false,
                TemporaryDeactivateHidden = true
            };

            var decision = coordinator.Evaluate(snapshot, "hide-on-deactivate");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostNotPresentableReason.TemporaryDeactivateHidden, decision.NotPresentableReason);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
        }

        [Fact]
        public void ActiveTemporaryDeactivateWithHostReady_Presents()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: false) with
            {
                AppActive = true,
                TemporaryDeactivateHidden = true
            };

            var decision = coordinator.Evaluate(snapshot, "activated-after-temporary-hide");

            AssertPresentAction(decision, setBounds: false, setVisible: true);
        }

        [Fact]
        public void ActiveTemporaryDeactivateWithHostStillHidden_PendingHost_HwndChainHidden()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: false) with
            {
                AppActive = true,
                TemporaryDeactivateHidden = true,
                HwndChainVisible = false
            };

            var decision = coordinator.Evaluate(snapshot, "activated-host-still-hidden");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostNotPresentableReason.HwndChainHidden, decision.NotPresentableReason);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
        }

        [Fact]
        public void HostReady_ControllerBoundsMismatch_PresentsAndRequestsBoundsCorrection()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(boundsMatch: false), "bounds-mismatch");

            AssertPresentAction(decision, setBounds: true, setVisible: false);
        }

        [Fact]
        public void HostReady_ControllerHiddenAndBoundsMismatch_PresentsWithBothCorrections()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(
                ReadySnapshot(controllerVisible: false, boundsMatch: false),
                "hidden-and-bounds-mismatch");

            AssertPresentAction(decision, setBounds: true, setVisible: true);
        }

        [Fact]
        public void TransitionIntoPresenting_NotifiesParentEvenWhenAlreadyVisibleAndBoundsMatch()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            Assert.Equal(WebViewHostPresentationState.Hidden, decision.OldState);
            AssertPresentAction(decision, setBounds: false, setVisible: false);
        }

        [Fact]
        public void RepeatedPresentingHealthy_NoAction()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(), "steady-state");

            Assert.Equal(WebViewHostPresentationState.Presenting, decision.OldState);
            Assert.Equal(WebViewHostPresentationState.Presenting, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.None, decision.NotPresentableReason);
            Assert.False(decision.ShouldSetControllerBounds);
            Assert.False(decision.ShouldSetControllerVisible);
            Assert.False(decision.ShouldNotifyParentPositionChanged);
        }

        [Fact]
        public void RepeatedPresentingBoundsMismatch_PresentsWithBoundsAndNotify()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(boundsMatch: false), "bounds-drift");

            AssertPresentAction(decision, setBounds: true, setVisible: false);
        }

        [Fact]
        public void RepeatedPresentingControllerHidden_PresentsWithVisibleAndNotify()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false), "visibility-drift");

            AssertPresentAction(decision, setBounds: false, setVisible: true);
        }

        [Fact]
        public void PresentingToPendingHost_WithVisibleController_HidesController()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                HwndChainVisible = false
            }, "host-hidden");

            Assert.Equal(WebViewHostPresentationState.Presenting, decision.OldState);
            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.HideController, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.HwndChainHidden, decision.NotPresentableReason);
        }

        [Fact]
        public void PresentingToPendingHost_WithHiddenController_NoAction()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                HwndChainVisible = false
            }, "host-hidden");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.HwndChainHidden, decision.NotPresentableReason);
        }

        [Fact]
        public void PendingHostToPresenting_WhenHostRecovers_PresentsAndNotifies()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                HwndChainVisible = false
            }, "host-hidden");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false), "host-recovered");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.OldState);
            AssertPresentAction(decision, setBounds: false, setVisible: true);
        }

        [Fact]
        public void ControllerUnavailableOnlyAfterHostPasses()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                HwndChainVisible = false,
                ControllerAvailable = false
            }, "host-and-controller-blocked");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostNotPresentableReason.HwndChainHidden, decision.NotPresentableReason);
        }

        [Fact]
        public void ControllerUnavailable_KeepsPendingControllerWithoutThrowing()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                ControllerAvailable = false
            }, "controller-missing");

            Assert.Equal(WebViewHostPresentationState.PendingController, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.ControllerUnavailable, decision.NotPresentableReason);
        }

        [Fact]
        public void ControllerParentWindowMissing_KeepsPendingController()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                ControllerParentWindowPresent = false
            }, "controller-parent-missing");

            Assert.Equal(WebViewHostPresentationState.PendingController, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.ControllerParentWindowMissing, decision.NotPresentableReason);
        }

        [Fact]
        public void Disposed_IsTerminal()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var disposeDecision = coordinator.Evaluate(ReadySnapshot() with
            {
                Disposed = true
            }, "disposed");

            var laterDecision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false), "after-disposed");

            Assert.Equal(WebViewHostPresentationState.Disposed, disposeDecision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, disposeDecision.Action);
            Assert.Equal(WebViewHostPresentationState.Disposed, laterDecision.OldState);
            Assert.Equal(WebViewHostPresentationState.Disposed, laterDecision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, laterDecision.Action);
        }

        [Fact]
        public void HideAfterPendingVisible_CancelsPendingShow()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                HwndChainVisible = false
            }, "pending-host");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                DesiredVisible = false
            }, "user-hide");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.OldState);
            Assert.Equal(WebViewHostPresentationState.Hidden, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.HideController, decision.Action);
        }

        [Fact]
        public void TemporaryDeactivateWinsOverAppInactive()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                AppActive = false,
                TemporaryDeactivateHidden = true,
                PanelVisible = false
            }, "inactive-temporary-hide");

            Assert.Equal(WebViewHostNotPresentableReason.TemporaryDeactivateHidden, decision.NotPresentableReason);
        }

        [Fact]
        public void PanelNotSelectedIgnoredWhenSelectionNotRequired()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                RequiresSelectedPanel = false,
                PanelSelectedVisible = false
            }, "selection-not-required");

            AssertPresentAction(decision, setBounds: false, setVisible: true);
        }

        [Fact]
        public void EtoSizeZeroWinsBeforeParentWindowMissing()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                EtoWidth = 0,
                ParentWindowPresent = false
            }, "size-zero-and-parent-missing");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostNotPresentableReason.EtoSizeZero, decision.NotPresentableReason);
        }
    }
}
```

- [ ] **Step 2: Run the focused test and confirm it fails before implementation**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~WebViewHostPresentationCoordinatorTests"
```

Expected result: build failure because `WebViewHostPresentationCoordinator`, `WebViewHostPresentationSnapshot`, `WebViewHostPresentationDecision`, and the enum types do not exist yet.

- [ ] **Step 3: Commit the failing tests only if the team wants strict TDD history**

Default for this repo should be to avoid committing a deliberately failing build. If using strict TDD commits, run:

```powershell
git add .\src\Rook.Tests\UI\Web\WebViewHostPresentationCoordinatorTests.cs
git commit -m "test: define webview host presentation coordinator contract"
```

If not using strict TDD commits, keep the tests unstaged until Task 2 passes.

---

### Task 2: Add the Pure Coordinator Implementation

**Files:**
- Create: `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`
- Test: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`

- [ ] **Step 1: Add the coordinator file**

Create `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs` with this complete content:

```csharp
namespace Rook.UI.Web
{
    internal enum WebViewHostPresentationState
    {
        Hidden,
        PendingHost,
        PendingController,
        Presenting,
        Disposed
    }

    internal enum WebViewHostPresentationAction
    {
        None,
        HideController,
        PresentController
    }

    internal enum WebViewHostNotPresentableReason
    {
        None,
        Disposed,
        TemporaryDeactivateHidden,
        AppInactive,
        PanelNotVisible,
        PanelNotSelected,
        EtoNotLoaded,
        EtoNotVisible,
        EtoSizeZero,
        ParentWindowMissing,
        HwndChainHidden,
        HwndClientRectZero,
        ControllerUnavailable,
        ControllerParentWindowMissing
    }

    internal sealed record WebViewHostPresentationSnapshot
    {
        public bool Disposed { get; init; }
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
    }

    internal sealed record WebViewHostPresentationDecision
    {
        public WebViewHostPresentationState OldState { get; init; }
        public WebViewHostPresentationState NewState { get; init; }
        public WebViewHostPresentationAction Action { get; init; }
        public WebViewHostNotPresentableReason NotPresentableReason { get; init; }
        public bool ShouldSetControllerBounds { get; init; }
        public bool ShouldSetControllerVisible { get; init; }
        public bool ShouldNotifyParentPositionChanged { get; init; }
        public string Reason { get; init; } = string.Empty;
    }

    internal sealed class WebViewHostPresentationCoordinator
    {
        private WebViewHostPresentationState _state = WebViewHostPresentationState.Hidden;

        public WebViewHostPresentationDecision Evaluate(
            WebViewHostPresentationSnapshot snapshot,
            string reason)
        {
            var oldState = _state;
            var safeReason = reason ?? string.Empty;

            if (_state == WebViewHostPresentationState.Disposed || snapshot.Disposed)
            {
                _state = WebViewHostPresentationState.Disposed;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.Disposed,
                    WebViewHostPresentationAction.None,
                    WebViewHostNotPresentableReason.Disposed,
                    safeReason);
            }

            if (!snapshot.DesiredVisible)
            {
                _state = WebViewHostPresentationState.Hidden;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.Hidden,
                    snapshot.ControllerVisible
                        ? WebViewHostPresentationAction.HideController
                        : WebViewHostPresentationAction.None,
                    WebViewHostNotPresentableReason.None,
                    safeReason);
            }

            var hostBlocker = FirstHostBlocker(snapshot);
            if (hostBlocker != WebViewHostNotPresentableReason.None)
            {
                _state = WebViewHostPresentationState.PendingHost;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.PendingHost,
                    snapshot.ControllerVisible
                        ? WebViewHostPresentationAction.HideController
                        : WebViewHostPresentationAction.None,
                    hostBlocker,
                    safeReason);
            }

            var controllerBlocker = FirstControllerBlocker(snapshot);
            if (controllerBlocker != WebViewHostNotPresentableReason.None)
            {
                _state = WebViewHostPresentationState.PendingController;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.PendingController,
                    WebViewHostPresentationAction.None,
                    controllerBlocker,
                    safeReason);
            }

            _state = WebViewHostPresentationState.Presenting;

            var enteringPresenting = oldState != WebViewHostPresentationState.Presenting;
            var shouldSetBounds = !snapshot.ControllerBoundsMatchHostTarget;
            var shouldSetVisible = !snapshot.ControllerVisible;
            var shouldPresent = enteringPresenting || shouldSetBounds || shouldSetVisible;

            return CreateDecision(
                oldState,
                WebViewHostPresentationState.Presenting,
                shouldPresent
                    ? WebViewHostPresentationAction.PresentController
                    : WebViewHostPresentationAction.None,
                WebViewHostNotPresentableReason.None,
                safeReason,
                shouldSetBounds,
                shouldSetVisible,
                shouldPresent);
        }

        private static WebViewHostNotPresentableReason FirstHostBlocker(
            WebViewHostPresentationSnapshot snapshot)
        {
            if (snapshot.TemporaryDeactivateHidden && !snapshot.AppActive)
                return WebViewHostNotPresentableReason.TemporaryDeactivateHidden;

            if (!snapshot.AppActive)
                return WebViewHostNotPresentableReason.AppInactive;

            if (!snapshot.PanelVisible)
                return WebViewHostNotPresentableReason.PanelNotVisible;

            if (snapshot.RequiresSelectedPanel && !snapshot.PanelSelectedVisible)
                return WebViewHostNotPresentableReason.PanelNotSelected;

            if (!snapshot.EtoLoaded)
                return WebViewHostNotPresentableReason.EtoNotLoaded;

            if (!snapshot.EtoVisible)
                return WebViewHostNotPresentableReason.EtoNotVisible;

            if (snapshot.EtoWidth <= 0 || snapshot.EtoHeight <= 0)
                return WebViewHostNotPresentableReason.EtoSizeZero;

            if (!snapshot.ParentWindowPresent)
                return WebViewHostNotPresentableReason.ParentWindowMissing;

            if (!snapshot.HwndChainVisible)
                return WebViewHostNotPresentableReason.HwndChainHidden;

            if (!snapshot.HwndClientRectNonZero)
                return WebViewHostNotPresentableReason.HwndClientRectZero;

            return WebViewHostNotPresentableReason.None;
        }

        private static WebViewHostNotPresentableReason FirstControllerBlocker(
            WebViewHostPresentationSnapshot snapshot)
        {
            if (!snapshot.ControllerAvailable)
                return WebViewHostNotPresentableReason.ControllerUnavailable;

            if (!snapshot.ControllerParentWindowPresent)
                return WebViewHostNotPresentableReason.ControllerParentWindowMissing;

            return WebViewHostNotPresentableReason.None;
        }

        private static WebViewHostPresentationDecision CreateDecision(
            WebViewHostPresentationState oldState,
            WebViewHostPresentationState newState,
            WebViewHostPresentationAction action,
            WebViewHostNotPresentableReason reasonCode,
            string reason,
            bool shouldSetControllerBounds = false,
            bool shouldSetControllerVisible = false,
            bool shouldNotifyParentPositionChanged = false)
        {
            return new WebViewHostPresentationDecision
            {
                OldState = oldState,
                NewState = newState,
                Action = action,
                NotPresentableReason = reasonCode,
                ShouldSetControllerBounds = shouldSetControllerBounds,
                ShouldSetControllerVisible = action == WebViewHostPresentationAction.PresentController
                    && shouldSetControllerVisible,
                ShouldNotifyParentPositionChanged = action == WebViewHostPresentationAction.PresentController
                    && shouldNotifyParentPositionChanged,
                Reason = reason
            };
        }
    }
}
```

- [ ] **Step 2: Run the focused coordinator tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~WebViewHostPresentationCoordinatorTests"
```

Expected result: all `WebViewHostPresentationCoordinatorTests` pass.

- [ ] **Step 3: Fix only coordinator/test compile issues if the repo compiler exposes a language compatibility detail**

Allowed adjustments:

```text
If record init syntax fails unexpectedly, keep the same properties and convert records to sealed classes with settable properties.
If the xUnit filter returns zero tests, run the exact class by namespace using:
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web.WebViewHostPresentationCoordinatorTests"
```

Do not add runtime calls from `RookWebSurface` in this task.

---

### Task 3: Verify Scope and Commit

**Files:**
- Verify: `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`
- Verify: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`
- Verify: `docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md`

- [ ] **Step 1: Confirm no runtime behavior files were modified**

Run:

```powershell
git diff --name-only
```

Expected output includes only:

```text
docs/superpowers/plans/2026-05-25-webview-host-presentation-coordinator.md
docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md
src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs
src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs
```

If `src/Rook/UI/Web/RookWebSurface.cs`, `src/Rook/UI/Vision/RookVisionPanel.cs`, `src/Rook/UI/Chat`, or `src/Rook/UI/Knowledge` appears, revert only the unintended edits from this branch after inspecting them.

- [ ] **Step 2: Run focused Web UI tests**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web"
```

Expected result: all Web UI tests pass, including existing `RookWebSurfaceTests` and the new coordinator tests.

- [ ] **Step 3: Run panel lifecycle tests as a nearby regression guard**

Run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Panels"
```

Expected result: all panel lifecycle tests pass.

- [ ] **Step 4: Run whitespace validation**

Run:

```powershell
git diff --check
```

Expected result: no output and exit code `0`.

- [ ] **Step 5: Commit the implementation**

Run:

```powershell
git add .\docs\superpowers\plans\2026-05-25-webview-host-presentation-coordinator.md `
  .\docs\superpowers\specs\2026-05-25-webview-host-presentation-coordinator-design.md `
  .\src\Rook\UI\Web\WebViewHostPresentationCoordinator.cs `
  .\src\Rook.Tests\UI\Web\WebViewHostPresentationCoordinatorTests.cs
git commit -m "feat: add webview host presentation coordinator contract"
```

Expected result: commit succeeds on `codex/webview-host-presentation-coordinator`.

---

### Task 4: Prepare Review Handoff

**Files:**
- Inspect: `docs/superpowers/specs/2026-05-25-webview-host-presentation-coordinator-design.md`
- Inspect: `docs/superpowers/plans/2026-05-25-webview-host-presentation-coordinator.md`
- Inspect: `src/Rook/UI/Web/WebViewHostPresentationCoordinator.cs`
- Inspect: `src/Rook.Tests/UI/Web/WebViewHostPresentationCoordinatorTests.cs`

- [ ] **Step 1: Inspect the final diff**

Run:

```powershell
git show --stat --oneline --decorate HEAD
git show --name-only --oneline HEAD
```

Expected result: commit contains only the plan/spec, coordinator implementation, and coordinator tests.

- [ ] **Step 2: Record verification commands for the PR body**

Use these exact verification lines:

```text
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Web"
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Rook.Tests.UI.Panels"
git diff --check
```

- [ ] **Step 3: Keep the PR description scoped**

Use this summary:

```text
Adds a pure WebView host presentation coordinator contract and fake-driven tests. This PR does not wire the coordinator into RookWebSurface runtime behavior and does not change Vision, Chat, or Knowledge Graph behavior.
```

Use this test summary:

```text
Verified the new coordinator state machine and nearby existing Web/Panel lifecycle tests. No live Rhino behavior change is included in this PR.
```

---

## Self-Review

**Spec coverage:** The plan implements the approved PR 1 scope: coordinator types, snapshot/decision model, deterministic host/controller gates, terminal disposed behavior, temporary deactivate semantics, selected-tab policy, corrective bounds actions, idempotent presenting behavior, protective hide transitions, and fake-driven tests. Runtime integration is explicitly excluded.

**Incomplete-marker scan:** The plan contains concrete file paths, full test and implementation content, exact commands, and expected outcomes. It does not rely on deferred design decisions.

**Type consistency:** The test file and implementation file use the same names: `WebViewHostPresentationCoordinator`, `WebViewHostPresentationSnapshot`, `WebViewHostPresentationDecision`, `WebViewHostPresentationState`, `WebViewHostPresentationAction`, and `WebViewHostNotPresentableReason`. Decision flags match the spec: `ShouldSetControllerBounds`, `ShouldSetControllerVisible`, and `ShouldNotifyParentPositionChanged`.
