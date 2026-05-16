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
        public void ChatTab_ExposesHostVisibilityReconciliationToOwningPanel()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatTab.cs");

            Assert.Contains("internal void ReconcileHostVisibility", source);
            Assert.Contains("_webSurface.ReconcileHostVisibility", source);
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
        }

        [Fact]
        public void ClaudeCodeWrapper_DisposeCleansTemporaryPanelConfigBestEffort()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

            Assert.Contains("_panelMcpConfigPath", source);
            Assert.Contains("DeletePanelMcpConfig", source);
            Assert.Contains("File.Delete", source);
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
