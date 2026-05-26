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

            _content = _surface.CreateWebContent();
            _content.SizeChanged += OnContentSizeChanged;
            Content = _content;
            Application.Instance.IsActiveChanged += OnApplicationIsActiveChanged;
        }

        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelShown(documentSerialNumber, reason);
            var facts = _presentationState.PanelShown(
                reason,
                IsVisibleAnyTab(),
                IsSelectedVisible());
            _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: true);
            ReconcileSurface("PanelShown:" + reason);
        }

        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);
            var facts = _presentationState.PanelHidden(
                reason,
                IsVisibleAnyTab(),
                IsSelectedVisible());
            _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: false);
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
            var facts = _presentationState.RefreshSelection(
                IsSelectedVisible(),
                reason);
            _surface.ReconcileHostPresentation(facts, scheduleIdleFollowUp: true);
        }

        private bool IsSelectedVisible()
        {
            try { return _visibilityQuery.IsSelectedPanelVisible(typeof(RookVisionPanel)); }
            catch { return false; }
        }

        private bool IsVisibleAnyTab()
        {
            try { return _visibilityQuery.IsPanelVisibleAnyTab(typeof(RookVisionPanel)); }
            catch { return false; }
        }
    }
}
