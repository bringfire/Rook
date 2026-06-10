using Rhino.UI;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class PanelDesiredVisibilityPolicyTests
    {
        [Fact]
        public void PanelClosing_IsDurableHide() =>
            Assert.Equal(DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelClosing());

        [Theory]
        [InlineData(ShowPanelReason.Show)]
        [InlineData(ShowPanelReason.ShowOnDeactivate)]
        public void PanelShown_IsVisible(ShowPanelReason reason) =>
            Assert.Equal(DesiredVisibilityChange.Visible,
                PanelDesiredVisibilityPolicy.OnPanelShown(reason));

        [Fact]
        public void HideOnDeactivate_NeverDurable() =>
            Assert.Equal(DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.HideOnDeactivate, visibleAnyTab: false));

        [Fact]
        public void Hide_WhileStillVisibleAnywhere_NotDurable() =>
            Assert.Equal(DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, visibleAnyTab: true));

        [Fact]
        public void Hide_NotVisibleAnywhere_IsDurable() =>
            Assert.Equal(DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, visibleAnyTab: false));
    }
}
