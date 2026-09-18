using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class RookChatPanelTests
    {
        [Theory]
        [InlineData("anthropic/claude", true)]
        [InlineData("openrouter/anthropic/claude-sonnet-4.5", true)]
        [InlineData("provider/vendor/family/model", true)]
        [InlineData("provider", false)]
        [InlineData("/model", false)]
        [InlineData("provider/", false)]
        [InlineData("provider/  ", false)]
        [InlineData(" /model", false)]
        public void Requested_model_splits_only_the_provider_separator(string model, bool valid)
        {
            Assert.Equal(valid, RookChatPanel.IsQualifiedRequestedModel(model));
        }

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
            Assert.Contains("rookBridge.invoke('submit'", html);
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
        [InlineData("{\"pluginType\":1,\"processId\":42,\"hostGenerationId\":\"11111111-1111-1111-1111-111111111111\"}")]
        [InlineData("{\"pluginType\":\"native\",\"processId\":\"42\",\"hostGenerationId\":\"11111111-1111-1111-1111-111111111111\"}")]
        [InlineData("{\"pluginType\":\"native\",\"processId\":42,\"hostGenerationId\":false}")]
        public void Discovery_parser_ignores_well_formed_unrelated_records(string json)
        {
            using var document = JsonDocument.Parse(json);
            Assert.Null(RookChatPanel.ReadNativeHostGenerationId(document.RootElement, 42));
        }

        [Fact]
        public void Discovery_parser_accepts_only_the_canonical_matching_native_identity()
        {
            const string expected = "11111111-1111-1111-1111-111111111111";
            using var document = JsonDocument.Parse(
                "{\"pluginType\":\"native\",\"processId\":42,\"hostGenerationId\":\"" + expected + "\"}");

            Assert.Equal(expected, RookChatPanel.ReadNativeHostGenerationId(document.RootElement, 42));
            Assert.Null(RookChatPanel.ReadNativeHostGenerationId(document.RootElement, 43));
        }

        [Fact]
        public void Presentation_history_projects_bounded_tool_meaning_and_non_normal_terminal_status()
        {
            using var tool = JsonDocument.Parse(
                "{\"kind\":\"tool_call_update\",\"content\":\"{\\\"kind\\\":\\\"tool_call_update\\\",\\\"text\\\":\\\"Inspect definition\\\",\\\"payload\\\":{\\\"status\\\":\\\"completed\\\"}}\",\"originalBytes\":128}");
            var history = new PresentationHistory
            {
                Available = true,
                Turns = new List<PresentationTurn>
                {
                    new()
                    {
                        Sequence = 1,
                        UserText = "inspect",
                        AssistantText = "partial answer",
                        StopReason = "max_tokens",
                        ToolCards = new List<JsonElement> { tool.RootElement.Clone() },
                    },
                },
            };

            var messages = PresentationHistoryFormatter.Format(history);

            Assert.Contains(messages, item => item.Role == "system" && item.Text == "Tool: Inspect definition (completed)");
            Assert.Contains(messages, item => item.Role == "system" && item.Text == "Turn ended: max_tokens");
        }

        [Fact]
        public void Presentation_history_tool_summary_is_bounded_in_utf8()
        {
            var label = new string('\u00e9', 600);
            using var tool = JsonDocument.Parse(
                "{\"kind\":\"tool_call_update\",\"content\":" +
                JsonSerializer.Serialize("{\"text\":" + JsonSerializer.Serialize(label) + "}") + "}");
            var history = new PresentationHistory
            {
                Available = true,
                Turns = new List<PresentationTurn>
                {
                    new() { StopReason = "end_turn", ToolCards = new List<JsonElement> { tool.RootElement.Clone() } },
                },
            };

            var messages = PresentationHistoryFormatter.Format(history);

            Assert.True(Encoding.UTF8.GetByteCount(Assert.Single(messages).Text) <= 512);
        }

        [Fact]
        public void Presentation_history_renders_image_metadata_without_claiming_a_reopened_preview()
        {
            var history = new PresentationHistory
            {
                Available = true,
                Turns = new List<PresentationTurn>
                {
                    new()
                    {
                        StopReason = "end_turn",
                        Images = new List<PresentationImage>
                        {
                            new()
                            {
                                FileName = "paste.png",
                                MimeType = "image/png",
                                BinaryByteCount = 68,
                                Width = 1,
                                Height = 1,
                                Sha256 = new string('a', 64),
                            },
                        },
                    },
                },
            };

            var message = Assert.Single(PresentationHistoryFormatter.Format(history));

            Assert.Equal("system", message.Role);
            Assert.Equal(
                "Image preview unavailable after reopen: paste.png (image/png, 68 bytes).",
                message.Text);
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
