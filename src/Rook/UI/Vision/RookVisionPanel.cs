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
    ///
    /// Presentation contract (reconciler spec 2026-06-10): the panel maps
    /// Rhino lifecycle events to durable desired-visible intent via
    /// <see cref="PanelDesiredVisibilityPolicy"/> and level-triggered
    /// reconcile requests on the surface. The surface owns app-active
    /// edges and all probe/repair behavior — the panel never reads
    /// HWND/controller state and never hides on probe failure.
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

            _content = _surface.CreateWebContent();
            _content.SizeChanged += OnContentSizeChanged;
            Content = _content;
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
            if (PanelDesiredVisibilityPolicy.OnPanelShown(reason) ==
                DesiredVisibilityChange.Visible)
            {
                _surface.SetPresentationDesiredVisible(true, "PanelShown:" + reason);
            }

            ReconcileSurface("PanelShown:" + reason);
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);

            // Probe failure degrades to NoChange inside the policy —
            // a registry read that throws must never durably hide.
            var change = PanelDesiredVisibilityPolicy.OnPanelHidden(
                reason,
                () => _visibilityQuery.IsPanelVisibleAnyTab(typeof(RookVisionPanel)));
            if (change == DesiredVisibilityChange.DurablyHidden)
            {
                _surface.SetPresentationDesiredVisible(false, "PanelHidden:" + reason);
            }
            else
            {
                _surface.RecordPresentationAnnotation(
                    "panel-hidden-nondurable", reason.ToString());
            }

            ReconcileSurface("PanelHidden:" + reason);
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
            _surface.SetPresentationDesiredVisible(false, "PanelClosing");
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
            if (_content != null)
            {
                try { _content.SizeChanged -= OnContentSizeChanged; } catch { }
                _content = null;
            }
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
                    _surface.RequestPresentationReconcile(sourceReason + ":Show");
                    break;
                case HostedSurfaceAction.Hide:
                    // Annotation only — lifecycle Hide is NEVER a durable
                    // desired-visibility edge (the policy owns durability).
                    _surface.RecordPresentationAnnotation(
                        "lifecycle-hide", decision.Reason);
                    break;
                case HostedSurfaceAction.Close:
                    CloseSurface();
                    break;
            }
        }

        private void OnContentSizeChanged(object? sender, EventArgs e)
        {
            _surface.RequestPresentationReconcile("ContentSizeChanged");
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
    }
}
