using System;
using System.IO;
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
    }
}
