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
        public void RookVisionPanel_PanelLifecycle_ReconcilesHostVisibility()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("_surface.ReconcileHostVisibility(true", source);
            Assert.Contains("PanelShown", source);
            Assert.Contains("_surface.ReconcileHostVisibility(false", source);
            Assert.Contains("PanelHidden", source);
        }

        [Fact]
        public void KnowledgeGraphPanel_PanelLifecycle_ReconcilesHostVisibility()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

            Assert.Contains("_surface.ReconcileHostVisibility(true", source);
            Assert.Contains("PanelShown", source);
            Assert.Contains("_surface.ReconcileHostVisibility(false", source);
            Assert.Contains("PanelHidden", source);
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
