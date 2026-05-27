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
        public void DumpVisionPresentationCommand_WritesFileAndPrintsCompactTail()
        {
            var command = ReadSourceFile(
                "src",
                "Rook",
                "Commands",
                "RookDumpVisionPresentationStateCommand.cs");
            var panel = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("RookDumpVisionPresentationState", command);
            Assert.Contains("RookVisionPanel.DumpPresentationDiagnostics()", command);
            Assert.Contains("RookVisionPanel.DumpPresentationDiagnosticsSummary(16)", command);
            Assert.Contains("RhinoApp.WriteLine", command);
            Assert.Contains("File.WriteAllText", command);
            Assert.Contains("try", command);
            Assert.Contains("catch (Exception ex)", command);
            Assert.Contains("Guid.NewGuid().ToString(\"N\")", command);
            Assert.Contains("internal static string DumpPresentationDiagnostics()", panel);
            Assert.Contains("internal static string DumpPresentationDiagnosticsSummary(int tailCount)", panel);
            Assert.Contains("Skip(Math.Max(0, allEntries.Length - count))", panel);
            Assert.Contains("VisionPanelPresentationDiagnosticDump", panel);
            Assert.Contains("SurfaceId = panel._surfaceId", panel);
            Assert.Contains("DocumentSerialNumber = panel._documentSerialNumber", panel);
            Assert.Contains("Closed = panel._closed", panel);
            Assert.Contains("SurfaceDisposed = panel._surface.IsDisposed", panel);
            Assert.Contains("Entries = panel._surface.GetHostPresentationDiagnosticEntries()", panel);
            Assert.Contains("JsonSerializer.Serialize", panel);
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
        public void RookVisionPanel_SuppliesPresentationFactsToSurface()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("VisionPanelPresentationState", source);
            Assert.Contains("_surface.ReconcileHostPresentation", source);
            Assert.Contains("_surface.SetPresentationFactsRefresher", source);
            Assert.Contains("RhinoPanelVisibilityQuery", source);
            Assert.Contains("IsSelectedPanelVisible(typeof(RookVisionPanel))", source);
            Assert.Contains("IsPanelVisibleAnyTab(typeof(RookVisionPanel))", source);
        }

        [Fact]
        public void RookVisionPanel_RefreshesVolatilePanelFactsAtDecisionTime()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var method = ExtractMethod(
                source,
                "private WebViewHostPanelPresentationFacts RefreshPresentationFactsForDecision");

            Assert.Contains("ProbeVisibleAnyTab(facts.PanelVisibleAnyTab)", method);
            Assert.Contains("ProbeSelectedVisible(facts.PanelSelectedVisible)", method);
            Assert.Contains("PanelVisibleAnyTab = visibleAnyTab.CoordinatorValue", method);
            Assert.Contains("PanelVisible = visibleAnyTab.CoordinatorValue", method);
            Assert.Contains("PanelSelectedVisible = selectedVisible.CoordinatorValue", method);
            Assert.Contains("ApplyProbeStatus", method);
            Assert.DoesNotContain("DesiredVisible =", method);
        }

        [Fact]
        public void RookVisionPanel_VisibilityProbeFailuresRemainDistinctFromFalse()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var facts = ReadSourceFile("src", "Rook", "UI", "Web", "WebViewHostPanelPresentationFacts.cs");
            var diagnostic = ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Web",
                "WebViewHostPresentationDiagnosticEntry.cs");
            var failure = ExtractMethod(
                source,
                "public static PanelVisibilityProbe Failure");

            Assert.Contains("PanelVisibilityProbe Failure(bool fallback, Exception ex)", source);
            Assert.Contains("\"exception:\" + ex.GetType().Name", source);
            Assert.Contains("return new PanelVisibilityProbe(", failure);
            Assert.Contains("false,", failure);
            Assert.Contains("fallback,", failure);
            Assert.Contains("PanelVisibleAnyTabPriorValue", facts);
            Assert.Contains("PanelVisibleAnyTabProbeSucceeded", facts);
            Assert.Contains("PanelVisibleAnyTabProbeStatus", facts);
            Assert.Contains("PanelSelectedVisiblePriorValue", facts);
            Assert.Contains("PanelSelectedVisibleProbeSucceeded", facts);
            Assert.Contains("PanelSelectedVisibleProbeStatus", facts);
            Assert.Contains("PanelVisibleAnyTabPriorValue", diagnostic);
            Assert.Contains("PanelVisibleAnyTabProbeSucceeded", diagnostic);
            Assert.Contains("PanelSelectedVisiblePriorValue", diagnostic);
            Assert.Contains("PanelSelectedVisibleProbeStatus", diagnostic);
            Assert.DoesNotContain("catch { return false; }", source);
        }

        [Fact]
        public void RookVisionPanel_HandlesAppActiveAsAuthoritativeFacts()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged", source);
            Assert.Contains("Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged", source);
            Assert.Contains("_presentationState.SetAppActive", source);
        }

        [Fact]
        public void RookVisionPanel_PanelHiddenAndClosingSendNoPresentFacts()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("_presentationState.PanelHidden", source);
            Assert.Contains("_presentationState.PanelClosing", source);
            Assert.Contains("scheduleIdleFollowUp: false", source);
        }

        [Fact]
        public void RookVisionPanel_ShowDecisionRefreshesSelectionFactsOnly()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var apply = ExtractMethod(source, "private void ApplyDecision");

            Assert.Contains("case HostedSurfaceAction.Show:", apply);
            Assert.Contains("RefreshSelectionVisible", apply);
            Assert.DoesNotContain("ReconcileHostVisibility", apply);
        }

        [Fact]
        public void RookVisionPanel_CloseSurfaceSendsTerminalPresentationFacts()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var close = ExtractMethod(source, "private void CloseSurface");

            Assert.Contains("_presentationState.PanelClosing()", close);
            Assert.Contains("_surface.ReconcileHostPresentation", close);
            Assert.Contains("scheduleIdleFollowUp: false", close);
        }

        [Fact]
        public void RookVisionPanel_DoesNotSendLegacyHostVisibilityCommands()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.DoesNotContain("_surface.ReconcileHostVisibility", source);
        }

        [Fact]
        public void VisionWebSurface_UiBridgeOps_DoNotUseLegacyHostVisibilityRefresh()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");

            Assert.DoesNotContain("VisionUiOpCompleted", source);
            Assert.DoesNotContain("RequestHostVisibleRefresh", source);
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
        public void DedicatedPanels_ReconcileClosingThroughLifecycleAdapter()
        {
            var visionSource = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var knowledgeSource = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");

            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", visionSource);
            Assert.Contains("HostedSurfaceAction.Close", visionSource);
            Assert.Contains("_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)", knowledgeSource);
            Assert.Contains("HostedSurfaceAction.Close", knowledgeSource);
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

        private static string ExtractMethod(string source, string signature)
        {
            var start = source.IndexOf(signature, StringComparison.Ordinal);
            if (start < 0)
                return string.Empty;

            var brace = source.IndexOf('{', start);
            if (brace < 0)
                return source.Substring(start);

            var depth = 0;
            for (var i = brace; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                if (source[i] == '}') depth--;
                if (depth == 0)
                    return source.Substring(start, i - start + 1);
            }

            return source.Substring(start);
        }
    }
}
