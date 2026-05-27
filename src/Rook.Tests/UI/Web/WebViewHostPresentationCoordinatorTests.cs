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
        public void PresentationFacts_Defaults_PinReturnEdgeContract()
        {
            var facts = new WebViewHostPanelPresentationFacts();

            Assert.True(facts.RequiresSelectedPanel);
            Assert.True(facts.Authoritative);
            Assert.Equal(string.Empty, facts.Reason);
        }

        [Fact]
        public void UserHide_ControllerUnavailable_NoAction()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot() with
            {
                DesiredVisible = false,
                ControllerAvailable = false,
                ControllerVisible = true
            };

            var decision = coordinator.Evaluate(snapshot, "user-hide-controller-unavailable");

            Assert.Equal(WebViewHostPresentationState.Hidden, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.None, decision.NotPresentableReason);
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
        public void PanelNotSelected_WithVisibleController_EntersPendingHostWithoutHiding()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            var snapshot = ReadySnapshot(controllerVisible: true) with
            {
                PanelSelectedVisible = false
            };

            var decision = coordinator.Evaluate(snapshot, "panel-not-selected");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
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

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true), "panel-selected");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.OldState);
            AssertPresentAction(decision, setBounds: false, setVisible: false);
        }

        [Fact]
        public void PanelSelectedAgain_WithTransientHiddenHwnd_DoesNotHideVisibleController()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");
            coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                PanelSelectedVisible = false,
                HwndChainVisible = false,
                HwndClientRectNonZero = false
            }, "panel-hidden");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                HwndChainVisible = false,
                HwndClientRectNonZero = true
            }, "webview-shown");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.OldState);
            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.HwndChainHidden, decision.NotPresentableReason);
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
        public void AppInactive_DoesNotPresent()
        {
            var coordinator = new WebViewHostPresentationCoordinator();

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: false) with
            {
                AppActive = false
            }, "app-inactive");

            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostNotPresentableReason.AppInactive, decision.NotPresentableReason);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.False(decision.ShouldSetControllerBounds);
            Assert.False(decision.ShouldSetControllerVisible);
            Assert.False(decision.ShouldNotifyParentPositionChanged);
        }

        [Fact]
        public void AppDeactivated_VisibleController_EntersPendingHostWithoutHiding()
        {
            var coordinator = new WebViewHostPresentationCoordinator();
            coordinator.Evaluate(ReadySnapshot(), "initial-ready");

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                AppActive = false
            }, "application-deactivated");

            Assert.Equal(WebViewHostPresentationState.Presenting, decision.OldState);
            Assert.Equal(WebViewHostPresentationState.PendingHost, decision.NewState);
            Assert.Equal(WebViewHostPresentationAction.None, decision.Action);
            Assert.Equal(WebViewHostNotPresentableReason.AppInactive, decision.NotPresentableReason);
            Assert.False(decision.ShouldSetControllerVisible);
            Assert.False(decision.ShouldNotifyParentPositionChanged);
        }

        [Fact]
        public void HideOnDeactivate_WhileInactiveEntersPendingHostWithoutPresenting()
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
        public void PendingHost_ControllerUnavailable_NoAction()
        {
            var coordinator = new WebViewHostPresentationCoordinator();

            var decision = coordinator.Evaluate(ReadySnapshot(controllerVisible: true) with
            {
                HwndChainVisible = false,
                ControllerAvailable = false
            }, "host-hidden-controller-unavailable");

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
