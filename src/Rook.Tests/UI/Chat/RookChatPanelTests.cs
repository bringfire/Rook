using System;
using System.IO;
using System.Reflection;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class RookChatPanelTests
    {
        [Fact]
        public void RookChatPanel_UsesHostedPanelLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(RookChatPanel)", source);
            Assert.DoesNotContain("ReconcileHostedWebSurfaces(tabControl, false, \"PanelHidden:\" + reason)", source);
        }

        [Fact]
        public void RookChatPanel_TabSelectionChanged_ReconcilesThroughLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("SelectedIndexChanged += OnTabSelectedIndexChanged", source);
            Assert.Contains("SelectedIndexChanged -= OnTabSelectedIndexChanged", source);
            Assert.Contains("ReconcileHostedWebSurfaces(tabControl, \"TabSelectionChanged\")", source);
            Assert.DoesNotContain("_panelHostVisible", source);
        }

        [Fact]
        public void RookChatPanel_ReconcilesClosingPerHostedSurface()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", source);
            Assert.Contains("ReconcileHostedWebSurfaces", source);
            Assert.Contains("HostedSurfaceAction.Close", source);
        }

        [Fact]
        public void ChatTabs_ExposeStableHostedSurfaceIds()
        {
            var chatTabSource = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var agentTabSource = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");
            var claudeTabSource = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeTab.cs");
            var visionTabSource = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionTab.cs");

            Assert.Contains("HostedSurfaceId", chatTabSource);
            Assert.Contains("Interlocked.Increment", chatTabSource);
            Assert.Contains("\"agent-chat\"", agentTabSource);
            Assert.Contains("\"claude-code\"", claudeTabSource);
            Assert.Contains("HostedSurfaceId", visionTabSource);
            Assert.Contains("Interlocked.Increment", visionTabSource);
            Assert.Contains("vision-tab", visionTabSource);
        }

        [Fact]
        public void RookChatPanel_PanelShown_DoesNotBypassSelectedTabVisibilityForLegacyVision()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.DoesNotContain("RecoverVisionSurfaceAfterPanelShown", source);
            Assert.DoesNotContain("RecoverAfterHostActivation", source);
            Assert.DoesNotContain("PanelShowReasonRecovery", source);
        }

        [Fact]
        public void ChatTab_ExposesPresentationDesiredVisibilityToOwningPanel()
        {
            // Reconciler cutover (spec 2026-06-10): Chat's TabControl is
            // authoritative for hosted tabs — selected maps to durable
            // desired-visible true (+ reconcile), unselected to false.
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var panel = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains(
                "internal void SetPresentationDesiredVisible(bool visible, string reason)",
                source);
            Assert.Contains(
                "internal void RequestPresentationReconcile(string reason)",
                source);
            Assert.Contains("_webSurface.SetPresentationDesiredVisible", source);
            Assert.Contains("_webSurface.RequestPresentationReconcile", source);

            Assert.Contains(
                "tab.SetPresentationDesiredVisible(true, sourceReason + \":\" + decision.Reason)",
                panel);
            Assert.Contains(
                "tab.RequestPresentationReconcile(sourceReason + \":\" + decision.Reason)",
                panel);
            Assert.Contains(
                "tab.SetPresentationDesiredVisible(false, sourceReason + \":\" + decision.Reason)",
                panel);
        }

        [Fact]
        public void ClaudeCodeWrapper_UsesStrictPanelMcpConfig()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

            Assert.Contains("ClaudePanelMcpConfigBuilder.WriteTempConfig", source);
            Assert.Contains("--strict-mcp-config", source);
            Assert.DoesNotContain("--mcp-config \\\"{userMcpConfig}\\\"", source);
        }

        [Fact]
        public void ClaudeCodeWrapper_PromptExplainsPanelLockedRookOnlyMode()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

            Assert.Contains("inside the Rook Rhino panel", source);
            Assert.Contains("panel-locked Rook MCP server", source);
            Assert.Contains("Do not claim access to Engram", source);
            Assert.Contains("Blueprints", source);
        }

        [Fact]
        public void ClaudeCodeWrapper_DisposeCleansTemporaryPanelConfigBestEffort()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

            Assert.Contains("_panelMcpConfigPath", source);
            Assert.Contains("DeletePanelMcpConfig", source);
            Assert.Contains("File.Delete", source);
        }

        [Fact]
        public void AgentChatClient_ChatEvent_ExposesToolStatusSeparatelyFromVerification()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatClient.cs");

            Assert.Contains("public string? ToolStatus { get; set; }", source);
            Assert.Contains("[JsonPropertyName(\"tool_status\")]", source);
            Assert.Contains("public bool? Verified { get; set; }", source);
        }

        [Fact]
        public void AgentChatTab_ToolResult_PassesToolStatusToWebView()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

            Assert.Contains("evt.ToolStatus", source);
            Assert.Contains("finalizeToolCard(", source);
            Assert.Contains("BuildToolSummary(evt)", source);
            Assert.DoesNotContain("success.GetBoolean() ? \"Success\" : \"Failed\"", source);
        }

        [Fact]
        public void AgentChatTab_ToolSummary_PrefersSuccessfulMessageBeforeGenericSuccess()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

            var messageIndex = source.IndexOf(
                "TryReadToolSummaryString(root, \"message\", out var successMessage)",
                StringComparison.Ordinal);
            var statusIndex = source.IndexOf(
                "TryReadToolSummaryString(root, \"status\", out var successStatus)",
                StringComparison.Ordinal);
            var fallbackIndex = source.IndexOf("return \"Success\";", StringComparison.Ordinal);

            Assert.True(messageIndex >= 0, "Successful tool summaries should surface root message.");
            Assert.True(statusIndex >= 0, "Successful tool summaries should surface root status.");
            Assert.True(messageIndex < fallbackIndex, "Message should be checked before generic Success.");
            Assert.True(statusIndex < fallbackIndex, "Status should be checked before generic Success.");
        }

        [Fact]
        public void AgentChatTab_ToolSummary_FailedToolNeverShowsDone()
        {
            var summary = InvokeBuildToolSummary(new ChatEvent
            {
                Type = "tool_result",
                ToolStatus = "failed"
            });

            Assert.Equal("Failed", summary);
        }

        [Theory]
        [InlineData("  build  this\r\n", "build  this")]
        [InlineData("\talpha\tbeta\t", "alpha\tbeta")]
        public void ChatTab_SubmissionNormalization_TrimsOnlyEdges(
            string input,
            string expected)
        {
            Assert.Equal(expected, ChatTab.NormalizeSubmittedMessage(input));
        }

        [Fact]
        public void ChatTab_NormalizesOnlyAtTheInputBoundary()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            Assert.Equal(2, CountOccurrences(source, "NormalizeSubmittedMessage("));
        }

        [Theory]
        [InlineData(null, false)]
        [InlineData("", false)]
        [InlineData("   ", false)]
        [InlineData("intent", true)]
        public void ChatTab_SubmissionGuard_RejectsBlankOrConcurrentWork(
            string? input,
            bool isProcessing)
        {
            var acceptedIntent = ChatTab.NormalizeSubmittedMessage(input);
            Assert.False(ChatTab.CanSubmitMessage(acceptedIntent, isProcessing));
        }

        [Theory]
        [InlineData(false, true)]
        [InlineData(true, false)]
        public void ChatTab_MessageActionsShareProcessingAvailability(
            bool isProcessing,
            bool expectedEnabled)
        {
            Assert.Equal(expectedEnabled, ChatTab.MessageActionsEnabled(isProcessing));
        }

        [Fact]
        public void AgentChatTab_BuildAction_IsHiddenWhileInternalPathRemains()
        {
            var chatTab = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");
            var agentTab = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

            Assert.DoesNotContain("ConfigureSecondaryAction(\"Build C#\", OnBuildCSharpMessage)", agentTab);
            Assert.Contains("private Task OnBuildCSharpMessage", agentTab);
            Assert.Contains("_client.SendWorkerFirstCSharpStreamingAsync", agentTab);
            Assert.Contains("_client.SendMessageStreamingAsync", agentTab);
            Assert.Contains("SubmitInputAsync(OnSendMessage)", chatTab);
            Assert.Contains("SubmitInputAsync(action)", chatTab);
            Assert.Contains("OnSendClicked(s, e)", chatTab);
            Assert.DoesNotContain("executionMode", agentTab);
        }

        [Theory]
        [InlineData(
            "{\"status\":\"success\",\"terminal_stage\":\"terminal\",\"terminal_reason\":\"terminal_node_selected:done\",\"compile_status\":\"passed\",\"error_count\":0,\"warning_count\":0,\"component_created\":true}",
            "Compiled cleanly (0 errors, 0 warnings)")]
        [InlineData(
            "{\"status\":\"failed\",\"terminal_stage\":\"verify_create\",\"terminal_reason\":\"selector_halt:none_ready\",\"compile_status\":\"failed\",\"error_count\":2,\"warning_count\":1,\"component_created\":true}",
            "Compile failed (2 errors, 1 warning)")]
        [InlineData(
            "{\"status\":\"failed\",\"terminal_stage\":\"create\",\"terminal_reason\":\"dispatch_failed\",\"compile_status\":\"unavailable\",\"error_count\":null,\"warning_count\":null,\"component_created\":null}",
            "Worker-first C# stopped before compile")]
        [InlineData(
            "{malformed sensitive-model-content",
            "Worker-first C# stopped before compile")]
        public void AgentChatTab_WorkerFirstSummary_ShowsOnlyBoundedCompileFacts(
            string result,
            string expected)
        {
            var summary = InvokeBuildToolSummary(new ChatEvent
            {
                Type = "tool_result",
                Name = "worker_first_csharp_v1",
                Result = result,
                ToolStatus = expected.StartsWith("Compiled cleanly") ? "success" : "failed",
            });

            Assert.Equal(expected, summary);
            Assert.DoesNotContain("sensitive-model-content", summary);
            Assert.DoesNotContain("dispatch_failed", summary);
            Assert.DoesNotContain("selector_halt", summary);
        }

        [Fact]
        public void AgentChatTab_WorkerFirstSummary_ReportsPassedCompileWarnings()
        {
            var summary = InvokeBuildToolSummary(new ChatEvent
            {
                Type = "tool_result",
                Name = "worker_first_csharp_v1",
                Result = "{\"status\":\"failed\",\"terminal_stage\":\"verify_create\",\"terminal_reason\":\"selector_halt:none_ready\",\"compile_status\":\"passed\",\"error_count\":0,\"warning_count\":1,\"component_created\":true}",
                ToolStatus = "failed",
            });

            Assert.Equal("Compile completed with warnings (0 errors, 1 warning)", summary);
        }

        [Fact]
        public void AgentChatTab_WorkerFirstSummary_FailedToolCannotClaimCleanCompile()
        {
            var summary = InvokeBuildToolSummary(new ChatEvent
            {
                Type = "tool_result",
                Name = "worker_first_csharp_v1",
                Result = "{\"status\":\"failed\",\"terminal_stage\":\"terminal\",\"terminal_reason\":\"terminal_node_selected:done\",\"compile_status\":\"passed\",\"error_count\":0,\"warning_count\":0,\"component_created\":true}",
                ToolStatus = "failed",
            });

            Assert.Equal("Compile passed, but build did not complete", summary);
        }

        [Fact]
        public void AgentChatTab_OtherToolSummary_RemainsGeneric()
        {
            var summary = InvokeBuildToolSummary(new ChatEvent
            {
                Type = "tool_result",
                Name = "existing_tool",
                Result = "{\"success\":true,\"message\":\"Existing summary\"}",
                ToolStatus = "success",
            });

            Assert.Equal("Existing summary", summary);
        }

        [Fact]
        public void AgentChatTab_TerminalEventsHideTypingIndicator()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "AgentChatTab.cs");

            var doneIndex = source.IndexOf("case \"done\":", StringComparison.Ordinal);
            var errorIndex = source.IndexOf("case \"error\":", StringComparison.Ordinal);
            var doneHideIndex = source.IndexOf("ShowTypingIndicator(false);", doneIndex, StringComparison.Ordinal);
            var errorHideIndex = source.IndexOf("ShowTypingIndicator(false);", errorIndex, StringComparison.Ordinal);
            var doneSetProcessingIndex = source.IndexOf("SetProcessing(false);", doneIndex, StringComparison.Ordinal);
            var errorSetProcessingIndex = source.IndexOf("SetProcessing(false);", errorIndex, StringComparison.Ordinal);

            Assert.True(doneIndex >= 0, "The done event branch should exist.");
            Assert.True(errorIndex >= 0, "The error event branch should exist.");
            Assert.True(doneHideIndex >= 0, "Done events should clear the typing indicator.");
            Assert.True(errorHideIndex >= 0, "Error events should clear the typing indicator.");
            Assert.True(doneHideIndex < doneSetProcessingIndex, "Done should clear typing before returning to idle.");
            Assert.True(errorHideIndex < errorSetProcessingIndex, "Error should clear typing before returning to idle.");
        }

        [Fact]
        public void ChatWebView_ToolCards_RenderStructuredParamsAndToolStatus()
        {
            var html = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.html");
            var css = ReadSourceFile("src", "Rook", "UI", "Chat", "Resources", "chat.css");

            Assert.Contains("formatToolValue", html);
            Assert.Contains("JSON.stringify", html);
            Assert.Contains("toolStatus", html);
            Assert.Contains("data-state=\"failed\"", html);
            Assert.Contains("done-success", html);
            Assert.Contains("badgeClass = 'success'", html);
            Assert.Contains(".verification-badge.success", css);
            Assert.DoesNotContain("parts.push(keys[i] + ': ' + val);", html);
            Assert.DoesNotContain(
                "toolStatus === 'success') {\r\n                state = 'done-verified'",
                html);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static int CountOccurrences(string source, string value)
        {
            var count = 0;
            var index = 0;
            while ((index = source.IndexOf(value, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += value.Length;
            }
            return count;
        }

        private static string InvokeBuildToolSummary(ChatEvent evt)
        {
            var method = typeof(AgentChatTab).GetMethod(
                "BuildToolSummary",
                BindingFlags.NonPublic | BindingFlags.Static);

            Assert.NotNull(method);
            return Assert.IsType<string>(method!.Invoke(null, new object[] { evt }));
        }
    }
}
