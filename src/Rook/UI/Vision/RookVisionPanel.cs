using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using Eto.Forms;
using Rhino.UI;
using Rook.UI.Panels;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    /// <summary>
    /// Native Rhino panel host for Rook Vision. This intentionally mirrors
    /// the Knowledge Graph host shape instead of embedding Vision inside
    /// RookChatPanel's Eto tab control: the Vision WebView owns one native
    /// panel surface and does not reload on host activation.
    /// </summary>
    [System.Runtime.InteropServices.Guid("C3D4E5F6-A7B8-9012-CDEF-123456789012")]
    public class RookVisionPanel : Panel, IPanel
    {
        private static int s_nextPanelInstanceId;
        private static readonly object s_instancesLock = new();
        private static readonly List<RookVisionPanel> s_instances = new();

        private readonly VisionWebSurface _surface;
        private readonly HostedPanelLifecycleAdapter _lifecycle =
            new(typeof(RookVisionPanel));
        private readonly IRhinoPanelVisibilityQuery _visibilityQuery =
            new RhinoPanelVisibilityQuery();
        private readonly VisionPanelPresentationState _presentationState =
            new(Application.Instance.IsActive);
        private readonly string _surfaceId;
        private uint _documentSerialNumber;
        private bool _closed;
        private Control? _content;

        public static Guid PanelId => typeof(RookVisionPanel).GUID;

        public RookVisionPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = documentSerialNumber;
            _surface = new VisionWebSurface();
            _surfaceId = documentSerialNumber.ToString() +
                ":vision-panel:" +
                Interlocked.Increment(ref s_nextPanelInstanceId).ToString();

            _surface.SetPresentationFactsRefresher(RefreshPresentationFactsForDecision);
            _content = _surface.CreateWebContent();
            _content.SizeChanged += OnContentSizeChanged;
            Content = _content;
            Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;
            lock (s_instancesLock)
            {
                s_instances.Add(this);
            }
        }

        internal static string DumpPresentationDiagnostics()
        {
            lock (s_instancesLock)
            {
                var dumps = new List<VisionPanelPresentationDiagnosticDump>();
                foreach (var panel in s_instances)
                {
                    dumps.Add(new VisionPanelPresentationDiagnosticDump
                    {
                        SurfaceId = panel._surfaceId,
                        DocumentSerialNumber = panel._documentSerialNumber,
                        Closed = panel._closed,
                        SurfaceDisposed = panel._surface.IsDisposed,
                        Entries = panel._surface.GetHostPresentationDiagnosticEntries()
                    });
                }

                return JsonSerializer.Serialize(
                    dumps,
                    new JsonSerializerOptions { WriteIndented = true });
            }
        }

        internal static string DumpPresentationDiagnosticsSummary(int tailCount)
        {
            lock (s_instancesLock)
            {
                var builder = new StringBuilder();
                foreach (var panel in s_instances)
                {
                    var allEntries = panel._surface.GetHostPresentationDiagnosticEntries();
                    var count = Math.Max(1, tailCount);
                    var entries = allEntries
                        .Skip(Math.Max(0, allEntries.Length - count))
                        .ToArray();

                    builder.Append("panel surface=");
                    builder.Append(panel._surfaceId);
                    builder.Append("; doc=");
                    builder.Append(panel._documentSerialNumber);
                    builder.Append("; closed=");
                    builder.Append(panel._closed);
                    builder.Append("; disposed=");
                    builder.Append(panel._surface.IsDisposed);
                    builder.Append("; entries=");
                    builder.Append(entries.Length);
                    builder.AppendLine();

                    foreach (var entry in entries)
                    {
                        builder.Append('#');
                        builder.Append(entry.Sequence);
                        builder.Append(' ');
                        builder.Append(entry.Reason);
                        builder.Append("; facts=");
                        builder.Append("app:");
                        builder.Append(entry.Facts.AppActive);
                        builder.Append(",any:");
                        builder.Append(entry.Facts.PanelVisibleAnyTab);
                        builder.Append(",sel:");
                        builder.Append(entry.Facts.PanelSelectedVisible);
                        builder.Append(",tmp:");
                        builder.Append(entry.Facts.TemporaryDeactivateHidden);
                        builder.Append("; snap=");
                        builder.Append("app:");
                        builder.Append(entry.Snapshot.AppActive);
                        builder.Append(",panel:");
                        builder.Append(entry.Snapshot.PanelVisible);
                        builder.Append(",sel:");
                        builder.Append(entry.Snapshot.PanelSelectedVisible);
                        builder.Append(",hwnd:");
                        builder.Append(entry.Snapshot.HwndChainVisible);
                        builder.Append(",rect:");
                        builder.Append(entry.Snapshot.HwndClientRectNonZero);
                        builder.Append(",ctl:");
                        builder.Append(entry.Snapshot.ControllerVisible);
                        builder.Append("; decision=");
                        builder.Append(entry.Decision.OldState);
                        builder.Append("->");
                        builder.Append(entry.Decision.NewState);
                        builder.Append('/');
                        builder.Append(entry.Decision.Action);
                        builder.Append('/');
                        builder.Append(entry.Decision.NotPresentableReason);
                        builder.Append("; result=");
                        builder.Append(entry.ActionResult);
                        builder.AppendLine();
                    }
                }

                return builder.ToString();
            }
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelShown(documentSerialNumber, reason);
            var visibleAnyTab = ProbeVisibleAnyTab(_presentationState.Current.PanelVisibleAnyTab);
            var selectedVisible = ProbeSelectedVisible(_presentationState.Current.PanelSelectedVisible);
            var facts = _presentationState.PanelShown(
                reason,
                visibleAnyTab.CoordinatorValue,
                selectedVisible.CoordinatorValue);
            _surface.ReconcileHostPresentation(
                ApplyProbeStatus(facts, visibleAnyTab, selectedVisible),
                scheduleIdleFollowUp: true);
            ReconcileSurface("PanelShown:" + reason);
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);
            var visibleAnyTab = ProbeVisibleAnyTab(_presentationState.Current.PanelVisibleAnyTab);
            var selectedVisible = ProbeSelectedVisible(_presentationState.Current.PanelSelectedVisible);
            var facts = _presentationState.PanelHidden(
                reason,
                visibleAnyTab.CoordinatorValue,
                selectedVisible.CoordinatorValue);
            _surface.ReconcileHostPresentation(
                ApplyProbeStatus(facts, visibleAnyTab, selectedVisible),
                scheduleIdleFollowUp: false);
            ReconcileSurface("PanelHidden:" + reason);
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
            _surface.ReconcileHostPresentation(
                _presentationState.PanelClosing(),
                scheduleIdleFollowUp: false);
            ReconcileSurface("PanelClosing");
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                CloseSurface();
            }
            base.Dispose(disposing);
        }

        private void CloseSurface()
        {
            if (_closed) return;
            _closed = true;
            _surface.ReconcileHostPresentation(
                _presentationState.PanelClosing(),
                scheduleIdleFollowUp: false);
            if (_content != null)
            {
                try { _content.SizeChanged -= OnContentSizeChanged; } catch { }
                _content = null;
            }
            try { Application.Instance.IsActiveChanged -= OnApplicationIsActiveChanged; } catch { }
            lock (s_instancesLock)
            {
                s_instances.Remove(this);
            }
            Content = null;
            _surface.Dispose();
        }

        private void ReconcileSurface(string reason)
        {
            _lifecycle.Reconcile(
                _surfaceId,
                isSelectedTab: true,
                this,
                decision => ApplyDecision(decision, reason));
        }

        private void ApplyDecision(HostedSurfaceDecision decision, string sourceReason)
        {
            switch (decision.Action)
            {
                case HostedSurfaceAction.Show:
                    RefreshSelectionVisible(sourceReason + ":Show");
                    break;
                case HostedSurfaceAction.Close:
                    CloseSurface();
                    break;
            }
        }

        private void OnApplicationIsActiveChanged(object? sender, EventArgs e)
        {
            var facts = _presentationState.SetAppActive(Application.Instance.IsActive);
            _surface.ReconcileHostPresentation(
                facts,
                scheduleIdleFollowUp: facts.AppActive);
        }

        private void OnContentSizeChanged(object? sender, EventArgs e)
        {
            RefreshSelectionVisible("ContentSizeChanged");
        }

        private void RefreshSelectionVisible(string reason)
        {
            var visibleAnyTab = ProbeVisibleAnyTab(_presentationState.Current.PanelVisibleAnyTab);
            var selectedVisible = ProbeSelectedVisible(_presentationState.Current.PanelSelectedVisible);
            var facts = _presentationState.RefreshSelection(
                selectedVisible.CoordinatorValue,
                reason);
            _surface.ReconcileHostPresentation(
                ApplyProbeStatus(
                    facts with
                    {
                        PanelVisibleAnyTab = visibleAnyTab.CoordinatorValue,
                        PanelVisible = visibleAnyTab.CoordinatorValue
                    },
                    visibleAnyTab,
                    selectedVisible),
                scheduleIdleFollowUp: true);
        }

        private WebViewHostPanelPresentationFacts RefreshPresentationFactsForDecision(
            WebViewHostPanelPresentationFacts facts,
            string reason)
        {
            if (!facts.Authoritative || facts.Disposed)
                return facts with { Reason = reason };

            var visibleAnyTab = ProbeVisibleAnyTab(facts.PanelVisibleAnyTab);
            var selectedVisible = ProbeSelectedVisible(facts.PanelSelectedVisible);
            return ApplyProbeStatus(
                facts with
                {
                    PanelVisibleAnyTab = visibleAnyTab.CoordinatorValue,
                    PanelVisible = visibleAnyTab.CoordinatorValue,
                    PanelSelectedVisible = selectedVisible.CoordinatorValue,
                    Reason = reason
                },
                visibleAnyTab,
                selectedVisible);
        }

        private static WebViewHostPanelPresentationFacts ApplyProbeStatus(
            WebViewHostPanelPresentationFacts facts,
            PanelVisibilityProbe visibleAnyTab,
            PanelVisibilityProbe selectedVisible)
        {
            return facts with
            {
                PanelVisibleAnyTabPriorValue = visibleAnyTab.PriorValue,
                PanelVisibleAnyTabProbeSucceeded = visibleAnyTab.Succeeded,
                PanelVisibleAnyTabProbeStatus = visibleAnyTab.Status,
                PanelSelectedVisiblePriorValue = selectedVisible.PriorValue,
                PanelSelectedVisibleProbeSucceeded = selectedVisible.Succeeded,
                PanelSelectedVisibleProbeStatus = selectedVisible.Status
            };
        }

        private PanelVisibilityProbe ProbeSelectedVisible(bool fallback)
        {
            try
            {
                return PanelVisibilityProbe.Success(
                    _visibilityQuery.IsSelectedPanelVisible(typeof(RookVisionPanel)));
            }
            catch (Exception ex)
            {
                return PanelVisibilityProbe.Failure(fallback, ex);
            }
        }

        private PanelVisibilityProbe ProbeVisibleAnyTab(bool fallback)
        {
            try
            {
                return PanelVisibilityProbe.Success(
                    _visibilityQuery.IsPanelVisibleAnyTab(typeof(RookVisionPanel)));
            }
            catch (Exception ex)
            {
                return PanelVisibilityProbe.Failure(fallback, ex);
            }
        }

        private sealed record VisionPanelPresentationDiagnosticDump
        {
            public string SurfaceId { get; init; } = string.Empty;
            public uint DocumentSerialNumber { get; init; }
            public bool Closed { get; init; }
            public bool SurfaceDisposed { get; init; }
            public IReadOnlyList<WebViewHostPresentationDiagnosticEntry> Entries { get; init; } =
                Array.Empty<WebViewHostPresentationDiagnosticEntry>();
        }

        private readonly record struct PanelVisibilityProbe(
            bool CoordinatorValue,
            bool PriorValue,
            bool Succeeded,
            string Status)
        {
            public static PanelVisibilityProbe Success(bool value)
            {
                return new PanelVisibilityProbe(value, value, true, "ok");
            }

            public static PanelVisibilityProbe Failure(bool fallback, Exception ex)
            {
                return new PanelVisibilityProbe(
                    false,
                    fallback,
                    false,
                    "exception:" + ex.GetType().Name);
            }
        }
    }
}
