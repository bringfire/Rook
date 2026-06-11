using System;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
using Rhino.UI;
using Rook.UI.Chat;
using Rook.UI.Panels;
using Rook.UI.Web;

namespace Rook.UI.Knowledge
{
    /// <summary>
    /// Dockable Rhino panel hosting the Knowledge Graph visualizer.
    /// Uses <see cref="RookWebSurface"/> for the hardened WebView host
    /// and fetches graph data from the chat server's /knowledge/* routes.
    /// </summary>
    [System.Runtime.InteropServices.Guid("B2C3D4E5-F6A7-8901-BCDE-F12345678901")]
    public class KnowledgeGraphPanel : Panel, IPanel
    {
        private static int s_nextPanelInstanceId;

        private readonly KnowledgeGraphSurface _surface;
        private readonly KnowledgeGraphBootstrapCoordinator _bootstrap;
        private readonly HostedPanelLifecycleAdapter _lifecycle =
            new(typeof(KnowledgeGraphPanel));
        private readonly IRhinoPanelVisibilityQuery _visibilityQuery =
            new RhinoPanelVisibilityQuery();
        private readonly string _surfaceId;
        private uint _documentSerialNumber;
        private bool _closed;

        public static Guid PanelId => typeof(KnowledgeGraphPanel).GUID;

        public KnowledgeGraphPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = documentSerialNumber;
            _surface = new KnowledgeGraphSurface(OnWebViewReadyAsync);
            _surfaceId = documentSerialNumber.ToString() +
                ":knowledge-graph:" +
                Interlocked.Increment(ref s_nextPanelInstanceId).ToString();
            _bootstrap = new KnowledgeGraphBootstrapCoordinator(
                ct => ChatServiceManager.Instance.EnsureStartedAsync(ct),
                () => ChatServiceManager.Instance.SessionNonce,
                script => _surface.ExecuteScript(script),
                message => RhinoApp.WriteLine(message));

            // Use the WebView directly as panel content.  Wrapping in
            // TableLayout caused the WebView to lose its content on
            // Rhino panel redraw (when clicking outside the panel).
            Content = _surface.CreateWebContent();
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

            _ = Task.Run(() => _bootstrap.RequestBootstrapAsync(default));
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);

            // Probe failure degrades to NoChange inside the policy —
            // a registry read that throws must never durably hide.
            var change = PanelDesiredVisibilityPolicy.OnPanelHidden(
                reason,
                () => _visibilityQuery.IsPanelVisibleAnyTab(typeof(KnowledgeGraphPanel)));
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
                    _surface.RequestPresentationReconcile(
                        sourceReason + ":" + decision.Reason);
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

        private Task OnWebViewReadyAsync(CancellationToken ct)
        {
            return _bootstrap.MarkWebViewReadyAsync(ct);
        }

        /// <summary>
        /// Knowledge Graph surface — declares resource root and entry page.
        /// </summary>
        private class KnowledgeGraphSurface : RookWebSurface
        {
            private readonly Func<CancellationToken, Task> _onWebViewReady;

            public KnowledgeGraphSurface(Func<CancellationToken, Task> onWebViewReady)
            {
                _onWebViewReady = onWebViewReady;
            }

            protected override string ResourceRoot => "Rook.UI.Knowledge.Resources";
            protected override string EntryPage => "knowledge-graph.html";

            protected override void OnWebViewReady()
            {
                _ = Task.Run(() => _onWebViewReady(default));
            }

            protected override string MinimalFallbackHtml => @"<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #1e1e1e; color: #e0e0e0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
.msg { text-align: center; opacity: 0.6; }
</style></head><body>
<div class='msg'><p>Knowledge Graph</p><p>WebView unavailable. Restart Rhino to retry.</p></div>
</body></html>";
        }
    }
}
