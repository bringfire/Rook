using System;
using System.IO;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class RookChatPanelTests
    {
        [Fact]
        public void RookChatPanel_UsesHostedPanelLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");
            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(RookChatPanel)", source);
            Assert.Contains("SelectedIndexChanged += OnTabSelectedIndexChanged", source);
            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", source);
        }

        [Fact]
        public void ChatTabs_ExposeStableHostedSurfaceIds()
        {
            var chat = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var agent = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            Assert.Contains("HostedSurfaceId", chat);
            Assert.Contains("Interlocked.Increment", chat);
            Assert.Contains("\"agent-chat\"", agent);
        }

        [Fact]
        public void Panel_contains_no_persona_backend_or_ChatRunner_creation_path()
        {
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");
            var client = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatClient.cs");
            var tab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            var chat = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var html = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.html");
            var css = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.css");

            Assert.DoesNotContain("PersonaPicker", panel);
            Assert.DoesNotContain("AddClaudeCodeTab", panel);
            Assert.DoesNotContain("persona", client, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("persona", chat, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("persona", html, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("persona", css, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("/agent/chat/start", client);
            Assert.DoesNotContain("/agent/chat/message", client);
            Assert.DoesNotContain("/agent/chat/models", client);
            Assert.DoesNotContain("SendWorkerFirstCSharp", tab);
            Assert.DoesNotContain("SendUIResponse", tab);
        }

        [Fact]
        public void Creation_dialog_owns_optional_model_and_closed_reasoning_selection()
        {
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("PrimeConversationDialog", panel);
            Assert.Contains("RequestedModel", panel);
            Assert.Contains("RequestedReasoning", panel);
            foreach (var value in new[] { "off", "minimal", "low", "medium", "high", "xhigh", "max" })
                Assert.Contains("\"" + value + "\"", panel);
            Assert.Contains("ListAsync", panel);
            Assert.Contains("Reopen", panel);
        }

        [Fact]
        public void Saved_document_workspace_is_derived_only_from_the_bound_Rhino_document()
        {
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("RhinoDoc.FromRuntimeSerialNumber", panel);
            Assert.Contains("Path.GetDirectoryName", panel);
            Assert.Contains("SavedDocumentDirectory", panel);
            Assert.DoesNotContain("Environment.CurrentDirectory", panel);
            Assert.DoesNotContain("Directory.GetCurrentDirectory", panel);
        }

        [Fact]
        public void Reopen_renders_cache_but_never_sends_cache_to_Prime()
        {
            var tab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

            Assert.Contains("GetHistoryAsync", tab);
            Assert.Contains("RenderPresentationHistory", tab);
            Assert.Contains("ReopenAsync", tab);
            Assert.DoesNotContain("PromptAsync(_conversationId, history", tab);
            Assert.Contains("Image preview unavailable after reopen", tab);
        }

        [Fact]
        public void Stop_close_and_delete_have_distinct_owners()
        {
            var tab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            var chat = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("_client.CancelAsync", tab);
            Assert.Contains("WaitForStopSettlement => true", tab);
            Assert.Contains("SetStatus(\"Stopping...\"", chat);
            Assert.Contains("_sendButton.Visible = false", chat);
            Assert.Contains("_actionButtonLayout.Visible = true", chat);
            Assert.Contains("ConversationCloseCoordinator", tab);
            Assert.Contains(".Enqueue(", tab);
            Assert.Contains("TryPublishConversation", tab);
            Assert.Contains("lock (_lifetimeGate)", tab);
            Assert.Contains("QueueClose(view.BaseUri, view.ConversationId)", tab);
            Assert.Contains("_client.Dispose()", tab);
            Assert.Contains("MessageBox.Show", panel);
            Assert.Contains("DeleteConversationAsync", panel);
            Assert.Contains("DialogResult.Yes", panel);
        }

        [Fact]
        public void Web_composer_posts_the_closed_text_and_image_shape()
        {
            var chatTab = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var html = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.html");

            Assert.Contains("RegisterBridgeHandler(\"submit\"", chatTab);
            Assert.Contains("OnWebSubmitAsync", chatTab);
            Assert.Contains("fileName", html);
            Assert.Contains("mimeType", html);
            Assert.Contains("base64Data", html);
            Assert.Contains("rookBridge.invoke('submit'", html);
            Assert.Contains("At most 8 images may be attached.", html);
            Assert.DoesNotContain("localStorage", html);
        }

        [Fact]
        public void Tool_cards_remain_presentation_and_never_certify_Rook_mutation()
        {
            var tab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            var html = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.html");

            Assert.Contains("HandleToolUpdate", tab);
            Assert.Contains("CertifiesMutation", tab);
            Assert.Contains("renderToolCard", html);
            Assert.Contains("finalizeToolCard", html);
        }

        [Theory]
        [InlineData("  build  this\r\n", "build  this")]
        [InlineData("\talpha\tbeta\t", "alpha\tbeta")]
        public void ChatTab_SubmissionNormalization_TrimsOnlyEdges(string input, string expected)
            => Assert.Equal(expected, ChatTab.NormalizeSubmittedMessage(input));

        [Fact]
        public void ChatTab_ExposesPresentationDesiredVisibilityToOwningPanel()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");
            Assert.Contains("internal void SetPresentationDesiredVisible", source);
            Assert.Contains("internal void RequestPresentationReconcile", source);
            Assert.Contains("tab.SetPresentationDesiredVisible", panel);
            Assert.Contains("tab.RequestPresentationReconcile", panel);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate)) return File.ReadAllText(candidate);
                dir = dir.Parent;
            }
            throw new FileNotFoundException("Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
