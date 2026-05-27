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
