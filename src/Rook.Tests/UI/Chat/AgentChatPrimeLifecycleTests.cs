using System;
using System.IO;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class AgentChatPrimeLifecycleTests
    {
        [Fact]
        public void Prime_defers_local_stop_until_broker_settlement()
        {
            Assert.True(AgentChatTab.DefersLocalStopCompletion("prime"));
            Assert.False(AgentChatTab.DefersLocalStopCompletion("legacy"));
        }

        [Theory]
        [InlineData("done", true)]
        [InlineData("cancelled", true)]
        [InlineData("error", true)]
        [InlineData("status", false)]
        [InlineData("agent_end", false)]
        public void Only_closed_terminal_rows_settle_Prime_processing(
            string eventType,
            bool expected)
        {
            Assert.Equal(expected, AgentChatTab.IsSettledTerminalEvent(eventType));
        }

        [Theory]
        [InlineData("legacy", true)]
        [InlineData("prime", true)]
        [InlineData("", false)]
        [InlineData("unknown", false)]
        public void Backend_must_be_authenticated_and_closed(string backend, bool expected)
        {
            Assert.Equal(expected, AgentChatTab.IsSupportedBackend(backend));
        }

        [Fact]
        public void Prime_reconnect_preserves_stable_identity_and_selects_reopen()
        {
            Assert.Equal("reopen", AgentChatTab.SelectPrimeStartAction(reconnecting: true));
            Assert.Equal("create", AgentChatTab.SelectPrimeStartAction(reconnecting: false));
        }

        [Fact]
        public void Prime_tab_close_transfers_delivery_to_the_service_manager()
        {
            var source = ReadSourceFile(
                "src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            var start = source.IndexOf(
                "public override void OnTabClosed()", StringComparison.Ordinal);
            Assert.True(start >= 0);
            var method = source.Substring(start, Math.Min(1200, source.Length - start));

            Assert.Contains(
                "ChatServiceManager.Instance.ClosePrimeConversationAsync", method);
            Assert.Contains("if (_backend == \"prime\")", method);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null &&
                   !Directory.Exists(Path.Combine(directory.FullName, "src", "Rook")))
            {
                directory = directory.Parent;
            }
            Assert.NotNull(directory);
            return File.ReadAllText(Path.Combine(
                directory!.FullName,
                Path.Combine(pathParts)));
        }
    }
}
