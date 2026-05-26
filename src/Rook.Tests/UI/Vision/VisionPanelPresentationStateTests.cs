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
