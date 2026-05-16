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
            bool isHostReady = true,
            bool isClosing = false)
        {
            return new PanelLifecycleFacts
            {
                PanelReportedVisible = panelReportedVisible,
                LastReason = reason,
                IsSelectedTab = isSelectedTab,
                IsRhinoSelectedPanelVisible = isRhinoSelectedPanelVisible,
                IsHostReady = isHostReady,
                IsClosing = isClosing,
                DeferAttempt = deferAttempt
            };
        }

        [Fact]
        public void Decide_VisibleSelectedHostReady_Shows()
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
        public void Decide_ShowOnDeactivate_DefersWhenHostNotReady()
        {
            var facts = VisibleReady(
                HostedPanelLifecycleReason.ShowOnDeactivate,
                isHostReady: false);

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
                isHostReady: true);

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
        public void Decide_VisibleButHostNotReady_Defers()
        {
            var decision = Coordinator.Decide(VisibleReady(
                isHostReady: false));

            Assert.Equal(HostedSurfaceAction.Defer, decision.Action);
        }

        [Fact]
        public void Decide_ExhaustedDefer_ReturnsNone()
        {
            var decision = Coordinator.Decide(VisibleReady(
                deferAttempt: HostedPanelLifecycleCoordinator.MaxDeferAttempts,
                isHostReady: false));

            Assert.Equal(HostedSurfaceAction.None, decision.Action);
        }

        [Fact]
        public void Decide_LaterReadyFactsAfterExhaustedDefer_CanShow()
        {
            var decision = Coordinator.Decide(VisibleReady(
                deferAttempt: HostedPanelLifecycleCoordinator.MaxDeferAttempts,
                isHostReady: true));

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
