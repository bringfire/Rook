using Rhino.UI;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    internal sealed class VisionPanelPresentationState
    {
        private long _generation;
        private bool _desiredVisible;
        private bool _appActive;
        private bool _temporaryDeactivateHidden;
        private bool _panelVisible;
        private bool _panelSelectedVisible;
        private bool _disposed;
        private bool _authoritative;

        public VisionPanelPresentationState(bool appActive)
        {
            _appActive = appActive;
            Current = CreateFacts("initial");
        }

        public WebViewHostPanelPresentationFacts Current { get; private set; }

        public WebViewHostPanelPresentationFacts PanelShown(
            ShowPanelReason reason,
            bool visibleAnyTab,
            bool selectedVisible)
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            _generation++;
            _authoritative = true;
            _desiredVisible = true;
            _panelVisible = visibleAnyTab;
            _panelSelectedVisible = selectedVisible;
            _temporaryDeactivateHidden = false;
            return Update("PanelShown:" + reason);
        }

        public WebViewHostPanelPresentationFacts PanelHidden(
            ShowPanelReason reason,
            bool visibleAnyTab,
            bool selectedVisible)
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            _generation++;
            _authoritative = true;
            _panelVisible = visibleAnyTab;
            _panelSelectedVisible = selectedVisible;

            if (reason == ShowPanelReason.HideOnDeactivate)
            {
                _temporaryDeactivateHidden = true;
                return Update("PanelHidden:" + reason);
            }

            _temporaryDeactivateHidden = false;
            if (!visibleAnyTab)
            {
                _desiredVisible = false;
            }
            return Update("PanelHidden:" + reason);
        }

        public WebViewHostPanelPresentationFacts PanelClosing()
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            _generation++;
            _authoritative = true;
            _desiredVisible = false;
            _temporaryDeactivateHidden = false;
            _panelVisible = false;
            _panelSelectedVisible = false;
            _disposed = true;
            return Update("PanelClosing");
        }

        public WebViewHostPanelPresentationFacts SetAppActive(bool active)
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            if (_appActive != active)
            {
                _generation++;
                _appActive = active;
                if (active)
                    _temporaryDeactivateHidden = false;
            }

            return Update(active ? "ApplicationActivated" : "ApplicationDeactivated");
        }

        public WebViewHostPanelPresentationFacts RefreshSelection(
            bool selectedVisible,
            string reason)
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            if (_panelSelectedVisible != selectedVisible)
            {
                _generation++;
                _panelSelectedVisible = selectedVisible;
            }

            return Update(reason);
        }

        public WebViewHostPanelPresentationFacts SizeLayoutSignal(string reason)
        {
            if (TryGetDisposedFacts(out var disposedFacts))
                return disposedFacts;

            return Update(reason);
        }

        private bool TryGetDisposedFacts(out WebViewHostPanelPresentationFacts facts)
        {
            facts = Current;
            return _disposed;
        }

        private WebViewHostPanelPresentationFacts Update(string reason)
        {
            Current = CreateFacts(reason);
            return Current;
        }

        private WebViewHostPanelPresentationFacts CreateFacts(string reason)
        {
            return new WebViewHostPanelPresentationFacts
            {
                Generation = _generation,
                DesiredVisible = _desiredVisible,
                AppActive = _appActive,
                TemporaryDeactivateHidden = _temporaryDeactivateHidden,
                PanelVisibleAnyTab = _panelVisible,
                PanelVisible = _panelVisible,
                RequiresSelectedPanel = true,
                PanelSelectedVisible = _panelSelectedVisible,
                Disposed = _disposed,
                Authoritative = _authoritative,
                Reason = reason
            };
        }
    }
}
