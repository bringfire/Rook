using System;
using System.Threading;
using Eto.Forms;
using Rhino.UI;
using Rook.UI.Panels;

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

        private readonly VisionWebSurface _surface;
        private readonly HostedPanelLifecycleAdapter _lifecycle =
            new(typeof(RookVisionPanel));
        private readonly string _surfaceId;
        private uint _documentSerialNumber;
        private bool _closed;

        public static Guid PanelId => typeof(RookVisionPanel).GUID;

        public RookVisionPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = documentSerialNumber;
            _surface = new VisionWebSurface();
            _surfaceId = documentSerialNumber.ToString() +
                ":vision-panel:" +
                Interlocked.Increment(ref s_nextPanelInstanceId).ToString();

            Content = _surface.CreateWebContent();
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelShown(documentSerialNumber, reason);
            ReconcileSurface("PanelShown:" + reason);
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);
            ReconcileSurface("PanelHidden:" + reason);
        }

        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
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
                    _surface.ReconcileHostVisibility(true, sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Hide:
                    _surface.ReconcileHostVisibility(false, sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Close:
                    CloseSurface();
                    break;
            }
        }
    }
}
