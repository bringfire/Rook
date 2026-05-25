using System;
using System.IO;
using Rook.Commands;
using Rook.UI.Chat;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class RookVisionPanelHostTests
    {
        [Fact]
        public void RookVisionPanel_UsesDedicatedPanelId()
        {
            Assert.NotEqual(RookChatPanel.PanelId, RookVisionPanel.PanelId);
        }

        [Fact]
        public void ShowRookVisionCommand_TargetsDedicatedVisionPanel()
        {
            Assert.Equal(RookVisionPanel.PanelId, ShowRookVisionCommand.TargetPanelId);
        }

        [Fact]
        public void RookPlugin_RegistersDedicatedVisionPanel()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");

            Assert.Contains("typeof(UI.Vision.RookVisionPanel)", source);
            Assert.Contains("\"Rook Vision\"", source);
        }

        [Fact]
        public void VisionTab_DoesNotExposeHostActivationVisibilityBypass()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionTab.cs");

            Assert.DoesNotContain("ReloadAfterHostActivation", source);
            Assert.DoesNotContain("RequestWebViewRepaint", source);
            Assert.DoesNotContain("RecoverAfterHostActivation", source);
            Assert.DoesNotContain("HostActivation:", source);
            Assert.Contains("internal void ReconcileHostVisibility(bool visible, string reason)", source);
        }

        [Fact]
        public void RookVisionPanel_UsesHostedPanelLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(RookVisionPanel)", source);
            Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, \"PanelHidden:\" + reason)", source);
        }

        [Fact]
        public void KnowledgeGraphPanel_UsesHostedPanelLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(KnowledgeGraphPanel)", source);
            Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, \"PanelHidden:\" + reason)", source);
        }

        [Fact]
        public void RookVisionPanel_UsesPresentationFactsOverload()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("WebViewHostPanelPresentationFacts", source);
            Assert.Contains("ReconcileHostVisibility(BuildPresentationFacts", source);
            Assert.DoesNotContain("_surface.ReconcileHostVisibility(true, sourceReason", source);
            Assert.DoesNotContain("_surface.ReconcileHostVisibility(false, sourceReason", source);
        }

        [Fact]
        public void RookVisionPanel_TemporaryDeactivateKeepsDesiredVisible()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("TemporaryDeactivateHidden", source);
            Assert.Contains("DesiredVisible = !durableHidden", source);
            Assert.Contains("var appActive = SafeApplicationActive();", source);
            Assert.Contains("AppActive = appActive", source);
            Assert.Contains("return false;", ExtractMethod(source, "private static bool SafeApplicationActive"));
        }

        [Fact]
        public void DedicatedPanels_ReconcileClosingThroughLifecycleAdapter()
        {
            var visionSource = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var knowledgeSource = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", visionSource);
            Assert.Contains("HostedSurfaceAction.Close", visionSource);
            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", knowledgeSource);
            Assert.Contains("HostedSurfaceAction.Close", knowledgeSource);
        }

        [Fact]
        public void VisionWebSurface_UiBridgeOps_RequestHostRefreshAfterModalReturn()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");

            Assert.Contains("RequestHostVisibleRefresh(\"VisionUiOpCompleted:\" + op)", source);
        }

        [Fact]
        public void VisionWebSurface_UsesCodeOptIn_NotEnvironmentFlag()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");

            Assert.Contains("UseHostPresentationCoordinator", source);
            Assert.DoesNotContain("GetEnvironmentVariable", source);
            Assert.DoesNotContain("ROOK_USE_HOST_PRESENTATION_COORDINATOR", source);
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

        private static string ExtractMethod(string source, string methodName)
        {
            var start = source.IndexOf(methodName, StringComparison.Ordinal);
            Assert.True(start >= 0, "Could not find method " + methodName);
            var brace = source.IndexOf('{', start);
            Assert.True(brace >= 0, "Could not find method body for " + methodName);
            var depth = 0;
            for (var i = brace; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                if (source[i] == '}') depth--;
                if (depth == 0) return source.Substring(start, i - start + 1);
            }

            throw new InvalidOperationException("Unbalanced method body for " + methodName);
        }
    }
}
