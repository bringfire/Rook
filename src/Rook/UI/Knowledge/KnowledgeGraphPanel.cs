using System;
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
        private uint _documentSerialNumber;

        public static Guid PanelId => typeof(KnowledgeGraphPanel).GUID;

        public KnowledgeGraphPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = documentSerialNumber;
            _surface = new KnowledgeGraphSurface();

            var content = _surface.CreateWebContent();

            Content = new TableLayout
            {
                Rows = { new TableRow(content) { ScaleHeight = true } }
            };
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;

            // Ensure chat service is running (provides /knowledge/* routes)
            // and inject service host/port + nonce into the WebView.
            Task.Run(async () =>
            {
                try
                {
                    var health = await ChatServiceManager.Instance.EnsureStartedAsync();
                    if (!health.ServiceAvailable || health.BaseUri == null)
                    {
                        RhinoApp.WriteLine("Rook: Knowledge Graph panel — chat service unavailable");
                        return;
                    }

                    var nonce = ChatServiceManager.Instance.SessionNonce ?? "";
                    var host = health.BaseUri.Host;
                    var port = health.BaseUri.Port;

                    var escapedNonce = RookWebSurface.EscapeForJavaScript(nonce);
                    _surface.ExecuteScript(
                        $"window.__rookServiceHost = '{host}';" +
                        $"window.__rookServicePort = {port};" +
                        $"window.__rookSessionNonce = '{escapedNonce}';");
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"Rook: Knowledge Graph bootstrap failed: {ex.Message}");
                }
            });
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
        }

        /// <summary>
        /// Knowledge Graph surface — declares resource root and entry page.
        /// </summary>
        private class KnowledgeGraphSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.UI.Knowledge.Resources";
            protected override string EntryPage => "knowledge-graph.html";

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
