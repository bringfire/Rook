using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class AgentChatApplyEnableTests
    {
        [Fact]
        public void Disabled_when_no_conversation() =>
            Assert.False(AgentChatTab.ShouldEnableApply(false, false, true, "b", "a"));

        [Fact]
        public void Disabled_when_processing() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, true, true, "b", "a"));

        [Fact]
        public void Disabled_when_list_unavailable() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, false, "b", "a"));

        [Fact]
        public void Disabled_when_selection_empty() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, true, "", "a"));

        [Fact]
        public void Disabled_when_selection_equals_active() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, true, "a", "a"));

        [Fact]
        public void Enabled_when_selection_differs() =>
            Assert.True(AgentChatTab.ShouldEnableApply(true, false, true, "b", "a"));

        [Fact]
        public void Enabled_when_active_null_and_selection_present() =>
            Assert.True(AgentChatTab.ShouldEnableApply(true, false, true, "b", null));
    }
}
