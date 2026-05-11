using System;
using System.IO;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class RookChatPanelTests
    {
        [Fact]
        public void HostedWebSurfaceVisibility_PanelShownWithMultipleTabs_OnlyShowsSelectedPage()
        {
            var visibility = HostedWebSurfaceVisibility.Resolve(
                pageCount: 3,
                selectedIndex: 1,
                panelVisible: true);

            Assert.Equal(new[] { false, true, false }, visibility);
        }

        [Fact]
        public void HostedWebSurfaceVisibility_TabSwitch_HidesOldPageAndShowsNewPage()
        {
            var before = HostedWebSurfaceVisibility.Resolve(
                pageCount: 2,
                selectedIndex: 0,
                panelVisible: true);
            var after = HostedWebSurfaceVisibility.Resolve(
                pageCount: 2,
                selectedIndex: 1,
                panelVisible: true);

            Assert.Equal(new[] { true, false }, before);
            Assert.Equal(new[] { false, true }, after);
        }

        [Fact]
        public void HostedWebSurfaceVisibility_PanelHidden_HidesEveryPage()
        {
            var visibility = HostedWebSurfaceVisibility.Resolve(
                pageCount: 3,
                selectedIndex: 1,
                panelVisible: false);

            Assert.Equal(new[] { false, false, false }, visibility);
        }

        [Fact]
        public void RookChatPanel_PanelLifecycle_ReconcilesHostedWebSurfaces()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("ReconcileHostedWebSurfaces(tabControl, true, \"PanelShown:\" + reason)", source);
            Assert.Contains("ReconcileHostedWebSurfaces(tabControl, false, \"PanelHidden:\" + reason)", source);
            Assert.Contains("ChatTab chatTab", source);
            Assert.Contains("VisionTab visionTab", source);
        }

        [Fact]
        public void RookChatPanel_TabSelectionChanged_ReconcilesHostedWebSurfaces()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "RookChatPanel.cs");

            Assert.Contains("SelectedIndexChanged += OnTabSelectedIndexChanged", source);
            Assert.Contains("SelectedIndexChanged -= OnTabSelectedIndexChanged", source);
            Assert.Contains("ReconcileHostedWebSurfaces(tabControl, _panelHostVisible, \"TabSelectionChanged\")", source);
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
