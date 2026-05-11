using System;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
using Rhino.UI;
using Rook.UI.Chat;
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
        private readonly KnowledgeGraphSurface _surface;
        private readonly KnowledgeGraphBootstrapCoordinator _bootstrap;
        private uint _documentSerialNumber;
        private bool _closed;

        public static Guid PanelId => typeof(KnowledgeGraphPanel).GUID;

        public KnowledgeGraphPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = documentSerialNumber;
            _surface = new KnowledgeGraphSurface(OnWebViewReadyAsync);
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
            _surface.ReconcileHostVisibility(true, "PanelShown:" + reason);

            _ = Task.Run(() => _bootstrap.RequestBootstrapAsync(default));
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _surface.ReconcileHostVisibility(false, "PanelHidden:" + reason);
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            CloseSurface();
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
