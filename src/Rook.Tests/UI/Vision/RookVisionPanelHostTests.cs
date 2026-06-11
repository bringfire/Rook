using System;
using System.IO;
using Rhino.UI;
using Rook.Commands;
using Rook.UI.Chat;
using Rook.UI.Vision;
using Rook.UI.Web;
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
        public void DumpVisionPresentationCommand_DumpsRegistryAndOffersRepairToggle()
        {
            // Reconciler spec 2026-06-10: the dump comes from the
            // substrate-wide WebSurfacePresentationRegistry (all surfaces,
            // not Vision-only) and the Repair toggle (default No)
            // schedules an accepted-and-scheduled forced repair.
            var command = ReadSourceFile(
                "src",
                "Rook",
                "Commands",
                "RookDumpVisionPresentationStateCommand.cs");

            Assert.Contains("RookDumpVisionPresentationState", command);
            Assert.Contains("WebSurfacePresentationRegistry.DumpAll()", command);
            Assert.Contains("WebSurfacePresentationRegistry.ScheduleRepairAll(", command);
            Assert.Contains("\"command-repair\"", command);
            Assert.Contains("OptionToggle(false, \"No\", \"Yes\")", command);
            Assert.Contains("AddOptionToggle(\"Repair\"", command);
            Assert.Contains("run the command again", command);
            Assert.Contains("RhinoApp.WriteLine", command);
            Assert.Contains("File.WriteAllText", command);
            Assert.Contains("try", command);
            Assert.Contains("catch (Exception ex)", command);
            Assert.Contains("Guid.NewGuid().ToString(\"N\")", command);
        }

        [Fact]
        public void RookPlugin_RegistersDedicatedVisionPanel()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");

            Assert.Contains("typeof(UI.Vision.RookVisionPanel)", source);
            Assert.Contains("\"Rook Vision\"", source);
        }

        // ─── Desired-visibility mapping (behavioral, via the policy
        //     seam both dedicated panels route lifecycle through) ──────

        [Theory]
        [InlineData(ShowPanelReason.Show)]
        [InlineData(ShowPanelReason.ShowOnDeactivate)]
        public void PanelShown_MapsToDesiredVisibleTrue(ShowPanelReason reason)
        {
            Assert.Equal(
                DesiredVisibilityChange.Visible,
                PanelDesiredVisibilityPolicy.OnPanelShown(reason));
        }

        [Fact]
        public void PanelHidden_HideOnDeactivate_IsNoChange()
        {
            // Transient app-deactivation hide must not touch durable
            // desired visibility regardless of what the probe reads.
            Assert.Equal(
                DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.HideOnDeactivate, () => false));
        }

        [Fact]
        public void PanelHidden_Hide_WhileVisibleAnyTab_IsNoChange()
        {
            Assert.Equal(
                DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, () => true));
        }

        [Fact]
        public void PanelHidden_Hide_NotVisibleAnywhere_IsDurablyHidden()
        {
            Assert.Equal(
                DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide, () => false));
        }

        [Fact]
        public void PanelHidden_ProbeException_IsNoChange_NeverDurable()
        {
            // A throwing visibility probe must NEVER durably hide.
            Assert.Equal(
                DesiredVisibilityChange.NoChange,
                PanelDesiredVisibilityPolicy.OnPanelHidden(
                    ShowPanelReason.Hide,
                    () => throw new InvalidOperationException("probe failed")));
        }

        [Fact]
        public void PanelClosing_IsDurablyHidden()
        {
            Assert.Equal(
                DesiredVisibilityChange.DurablyHidden,
                PanelDesiredVisibilityPolicy.OnPanelClosing());
        }

        // ─── Panel wiring (source pins: lifecycle → policy →
        //     reconciler desired state) ───────────────────────────────

        [Fact]
        public void RookVisionPanel_PanelShown_SetsDesiredVisibleThroughPolicy()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var shown = ExtractMethod(source, "public void PanelShown");

            Assert.Contains("_lifecycle.PanelShown(documentSerialNumber, reason)", shown);
            Assert.Contains("PanelDesiredVisibilityPolicy.OnPanelShown(reason)", shown);
            Assert.Contains(
                "_surface.SetPresentationDesiredVisible(true, \"PanelShown:\" + reason)",
                shown);
            Assert.Contains("ReconcileSurface(\"PanelShown:\" + reason)", shown);
        }

        [Fact]
        public void RookVisionPanel_PanelHidden_RoutesProbeThroughPolicy()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var hidden = ExtractMethod(source, "public void PanelHidden");

            Assert.Contains("_lifecycle.PanelHidden(documentSerialNumber, reason)", hidden);
            Assert.Contains("PanelDesiredVisibilityPolicy.OnPanelHidden(", hidden);
            Assert.Contains(
                "_visibilityQuery.IsPanelVisibleAnyTab(typeof(RookVisionPanel))",
                hidden);
            Assert.Contains("DesiredVisibilityChange.DurablyHidden", hidden);
            Assert.Contains(
                "_surface.SetPresentationDesiredVisible(false, \"PanelHidden:\" + reason)",
                hidden);
            Assert.Contains("\"panel-hidden-nondurable\"", hidden);
        }

        [Fact]
        public void RookVisionPanel_PanelClosing_IsDurableHide()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var closing = ExtractMethod(source, "public void PanelClosing");

            Assert.Contains(
                "_lifecycle.PanelClosing(documentSerialNumber, onCloseDocument)",
                closing);
            Assert.Contains(
                "_surface.SetPresentationDesiredVisible(false, \"PanelClosing\")",
                closing);
            Assert.Contains("ReconcileSurface(\"PanelClosing\")", closing);
        }

        [Fact]
        public void RookVisionPanel_LifecycleDecision_ShowReconciles_HideAnnotatesOnly()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var apply = ExtractMethod(source, "private void ApplyDecision");

            Assert.Contains("case HostedSurfaceAction.Show:", apply);
            Assert.Contains(
                "_surface.RequestPresentationReconcile(sourceReason + \":Show\")",
                apply);
            Assert.Contains("case HostedSurfaceAction.Hide:", apply);
            Assert.Contains(
                "_surface.RecordPresentationAnnotation(",
                apply);
            Assert.Contains("\"lifecycle-hide\"", apply);
            Assert.Contains("case HostedSurfaceAction.Close:", apply);
            Assert.Contains("CloseSurface()", apply);
            // Lifecycle Hide must never become a durable desired-hide.
            Assert.DoesNotContain("SetPresentationDesiredVisible(false", apply);
        }

        [Fact]
        public void RookVisionPanel_ContentSizeChanged_RequestsReconcile()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");
            var handler = ExtractMethod(source, "private void OnContentSizeChanged");

            Assert.Contains("SizeChanged += OnContentSizeChanged", source);
            Assert.Contains("SizeChanged -= OnContentSizeChanged", source);
            Assert.Contains(
                "_surface.RequestPresentationReconcile(\"ContentSizeChanged\")",
                handler);
        }

        [Fact]
        public void RookVisionPanel_HasNoProbeFactsPlumbing()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            // The surface owns app-active edges and all probe/repair
            // behavior now (reconciler spec 2026-06-10).
            Assert.DoesNotContain("SetPresentationFactsRefresher", source);
            Assert.DoesNotContain("RefreshPresentationFactsForDecision", source);
            Assert.DoesNotContain("RefreshSelectionVisible", source);
            Assert.DoesNotContain("PanelVisibilityProbe", source);
            Assert.DoesNotContain("OnApplicationIsActiveChanged", source);
        }

        [Fact]
        public void RookVisionPanel_UsesHostedPanelLifecycleAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "RookVisionPanel.cs");

            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(RookVisionPanel)", source);
        }

        [Fact]
        public void VisionWebSurface_HasNoLegacyCoordinatorOptInOrFactsRefresher()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionWebSurface.cs");

            Assert.DoesNotContain("RefreshHostPresentationFacts", source);
            Assert.DoesNotContain("SetPresentationFactsRefresher", source);
            Assert.DoesNotContain("VisionUiOpCompleted", source);
            Assert.DoesNotContain("RequestHostVisibleRefresh", source);
        }

        [Fact]
        public void VisionTab_ForwardsDesiredVisibilityWithoutHostActivationBypass()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Vision", "VisionTab.cs");

            Assert.DoesNotContain("ReloadAfterHostActivation", source);
            Assert.DoesNotContain("RequestWebViewRepaint", source);
            Assert.DoesNotContain("RecoverAfterHostActivation", source);
            Assert.DoesNotContain("HostActivation:", source);
            Assert.Contains(
                "internal void SetPresentationDesiredVisible(bool visible, string reason)",
                source);
            Assert.Contains(
                "internal void RequestPresentationReconcile(string reason)",
                source);
        }

        [Fact]
        public void KnowledgeGraphPanel_UsesSameDedicatedPanelMapping()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Knowledge", "KnowledgeGraphPanel.cs");
            var shown = ExtractMethod(source, "public void PanelShown");
            var hidden = ExtractMethod(source, "public void PanelHidden");
            var closing = ExtractMethod(source, "public void PanelClosing");
            var apply = ExtractMethod(source, "private void ApplyDecision");

            Assert.Contains("HostedPanelLifecycleAdapter", source);
            Assert.Contains("typeof(KnowledgeGraphPanel)", source);
            Assert.Contains("PanelDesiredVisibilityPolicy.OnPanelShown(reason)", shown);
            Assert.Contains(
                "_surface.SetPresentationDesiredVisible(true, \"PanelShown:\" + reason)",
                shown);
            Assert.Contains("PanelDesiredVisibilityPolicy.OnPanelHidden(", hidden);
            Assert.Contains(
                "_visibilityQuery.IsPanelVisibleAnyTab(typeof(KnowledgeGraphPanel))",
                hidden);
            Assert.Contains("\"panel-hidden-nondurable\"", hidden);
            Assert.Contains(
                "_surface.SetPresentationDesiredVisible(false, \"PanelClosing\")",
                closing);
            Assert.Contains("_surface.RequestPresentationReconcile(", apply);
            Assert.Contains("\"lifecycle-hide\"", apply);
            Assert.Contains("CloseSurface()", apply);
            Assert.DoesNotContain("SetPresentationDesiredVisible(false", apply);
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
