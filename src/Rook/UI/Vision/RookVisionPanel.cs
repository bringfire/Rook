using System;
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
                (decision, facts) => ApplyDecision(decision, facts, reason));
        }

        private void ApplyDecision(
            HostedSurfaceDecision decision,
            PanelLifecycleFacts facts,
            string sourceReason)
        {
            _surface.ReconcileHostVisibility(BuildPresentationFacts(decision, facts, sourceReason));

            switch (decision.Action)
            {
                case HostedSurfaceAction.Close:
                    CloseSurface();
                    break;
            }
        }

        private static WebViewHostPanelPresentationFacts BuildPresentationFacts(
            HostedSurfaceDecision decision,
            PanelLifecycleFacts facts,
            string sourceReason)
        {
            var appActive = SafeApplicationActive();
            var durableHidden =
                decision.Action == HostedSurfaceAction.Close ||
                (decision.Action == HostedSurfaceAction.Hide &&
                 string.Equals(decision.Reason, "panel-hidden", StringComparison.Ordinal));
            var temporaryDeactivateHidden =
                facts.LastReason == HostedPanelLifecycleReason.HideOnDeactivate &&
                !appActive;

            return new WebViewHostPanelPresentationFacts
            {
                DesiredVisible = !durableHidden,
                AppActive = appActive,
                TemporaryDeactivateHidden = temporaryDeactivateHidden,
                PanelVisible = facts.PanelReportedVisible,
                RequiresSelectedPanel = true,
                PanelSelectedVisible = facts.IsSelectedTab && facts.IsRhinoSelectedPanelVisible,
                Reason = sourceReason + ":" + decision.Reason
            };
        }

        private static bool SafeApplicationActive()
        {
            try
            {
                return Application.Instance.IsActive;
            }
            catch
            {
                return false;
            }
        }
    }
}
