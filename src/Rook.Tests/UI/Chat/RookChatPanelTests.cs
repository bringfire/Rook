using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class RookChatPanelTests
    {
        [Theory]
        [InlineData("Show", true)]
        [InlineData("ShowOnDeactivate", true)]
        [InlineData("Hide", false)]
        [InlineData("HideOnDeactivate", false)]
        public void ShouldRecoverVisionSurfaceOnPanelShown_OnlyForShowReasons(
            string reasonName,
            bool expected)
        {
            Assert.Equal(expected, PanelShowReasonRecovery.ShouldRecoverVisionSurface(reasonName));
        }
    }
}
