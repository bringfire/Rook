namespace Rook.UI.Web
{
    internal enum WebViewHostPresentationState
    {
        Hidden,
        PendingHost,
        PendingController,
        Presenting,
        Disposed
    }

    internal enum WebViewHostPresentationAction
    {
        None,
        HideController,
        PresentController
    }

    internal enum WebViewHostNotPresentableReason
    {
        None,
        Disposed,
        TemporaryDeactivateHidden,
        AppInactive,
        PanelNotVisible,
        PanelNotSelected,
        EtoNotLoaded,
        EtoNotVisible,
        EtoSizeZero,
        ParentWindowMissing,
        HwndChainHidden,
        HwndClientRectZero,
        ControllerUnavailable,
        ControllerParentWindowMissing
    }

    internal sealed record WebViewHostPresentationSnapshot
    {
        public bool Disposed { get; init; }
        public bool DesiredVisible { get; init; }

        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; }
        public bool PanelSelectedVisible { get; init; }

        public bool EtoLoaded { get; init; }
        public bool EtoVisible { get; init; }
        public int EtoWidth { get; init; }
        public int EtoHeight { get; init; }
        public bool ParentWindowPresent { get; init; }
        public bool HwndChainVisible { get; init; }
        public bool HwndClientRectNonZero { get; init; }

        public bool ControllerAvailable { get; init; }
        public bool ControllerParentWindowPresent { get; init; }
        public bool ControllerVisible { get; init; }
        public bool ControllerBoundsMatchHostTarget { get; init; }
    }

    internal sealed record WebViewHostPresentationDecision
    {
        public WebViewHostPresentationState OldState { get; init; }
        public WebViewHostPresentationState NewState { get; init; }
        public WebViewHostPresentationAction Action { get; init; }
        public WebViewHostNotPresentableReason NotPresentableReason { get; init; }
        public bool ShouldSetControllerBounds { get; init; }
        public bool ShouldSetControllerVisible { get; init; }
        public bool ShouldNotifyParentPositionChanged { get; init; }
        public string Reason { get; init; } = string.Empty;
    }

    /// <summary>
    /// Stateful presentation decision engine for one WebView host surface.
    /// Not thread-safe: runtime integration must call <see cref="Evaluate" />
    /// from one serialized UI/lifecycle owner.
    /// </summary>
    internal sealed class WebViewHostPresentationCoordinator
    {
        private WebViewHostPresentationState _state = WebViewHostPresentationState.Hidden;

        public WebViewHostPresentationDecision Evaluate(
            WebViewHostPresentationSnapshot snapshot,
            string reason)
        {
            var oldState = _state;
            var safeReason = reason ?? string.Empty;

            if (_state == WebViewHostPresentationState.Disposed || snapshot.Disposed)
            {
                _state = WebViewHostPresentationState.Disposed;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.Disposed,
                    WebViewHostPresentationAction.None,
                    WebViewHostNotPresentableReason.Disposed,
                    safeReason);
            }

            if (!snapshot.DesiredVisible)
            {
                _state = WebViewHostPresentationState.Hidden;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.Hidden,
                    HideControllerAction(snapshot),
                    WebViewHostNotPresentableReason.None,
                    safeReason);
            }

            var hostBlocker = FirstHostBlocker(snapshot);
            if (hostBlocker != WebViewHostNotPresentableReason.None)
            {
                _state = WebViewHostPresentationState.PendingHost;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.PendingHost,
                    HideControllerAction(snapshot),
                    hostBlocker,
                    safeReason);
            }

            var controllerBlocker = FirstControllerBlocker(snapshot);
            if (controllerBlocker != WebViewHostNotPresentableReason.None)
            {
                _state = WebViewHostPresentationState.PendingController;
                return CreateDecision(
                    oldState,
                    WebViewHostPresentationState.PendingController,
                    WebViewHostPresentationAction.None,
                    controllerBlocker,
                    safeReason);
            }

            _state = WebViewHostPresentationState.Presenting;

            var enteringPresenting = oldState != WebViewHostPresentationState.Presenting;
            var shouldSetBounds = !snapshot.ControllerBoundsMatchHostTarget;
            var shouldSetVisible = !snapshot.ControllerVisible;
            var shouldPresent = enteringPresenting || shouldSetBounds || shouldSetVisible;

            return CreateDecision(
                oldState,
                WebViewHostPresentationState.Presenting,
                shouldPresent
                    ? WebViewHostPresentationAction.PresentController
                    : WebViewHostPresentationAction.None,
                WebViewHostNotPresentableReason.None,
                safeReason,
                shouldSetBounds,
                shouldSetVisible,
                shouldPresent);
        }

        private static WebViewHostPresentationAction HideControllerAction(
            WebViewHostPresentationSnapshot snapshot)
        {
            return snapshot.ControllerAvailable && snapshot.ControllerVisible
                ? WebViewHostPresentationAction.HideController
                : WebViewHostPresentationAction.None;
        }

        private static WebViewHostNotPresentableReason FirstHostBlocker(
            WebViewHostPresentationSnapshot snapshot)
        {
            if (snapshot.TemporaryDeactivateHidden && !snapshot.AppActive)
                return WebViewHostNotPresentableReason.TemporaryDeactivateHidden;

            if (!snapshot.AppActive)
                return WebViewHostNotPresentableReason.AppInactive;

            if (!snapshot.PanelVisible)
                return WebViewHostNotPresentableReason.PanelNotVisible;

            if (snapshot.RequiresSelectedPanel && !snapshot.PanelSelectedVisible)
                return WebViewHostNotPresentableReason.PanelNotSelected;

            if (!snapshot.EtoLoaded)
                return WebViewHostNotPresentableReason.EtoNotLoaded;

            if (!snapshot.EtoVisible)
                return WebViewHostNotPresentableReason.EtoNotVisible;

            if (snapshot.EtoWidth <= 0 || snapshot.EtoHeight <= 0)
                return WebViewHostNotPresentableReason.EtoSizeZero;

            if (!snapshot.ParentWindowPresent)
                return WebViewHostNotPresentableReason.ParentWindowMissing;

            if (!snapshot.HwndChainVisible)
                return WebViewHostNotPresentableReason.HwndChainHidden;

            if (!snapshot.HwndClientRectNonZero)
                return WebViewHostNotPresentableReason.HwndClientRectZero;

            return WebViewHostNotPresentableReason.None;
        }

        private static WebViewHostNotPresentableReason FirstControllerBlocker(
            WebViewHostPresentationSnapshot snapshot)
        {
            if (!snapshot.ControllerAvailable)
                return WebViewHostNotPresentableReason.ControllerUnavailable;

            if (!snapshot.ControllerParentWindowPresent)
                return WebViewHostNotPresentableReason.ControllerParentWindowMissing;

            return WebViewHostNotPresentableReason.None;
        }

        private static WebViewHostPresentationDecision CreateDecision(
            WebViewHostPresentationState oldState,
            WebViewHostPresentationState newState,
            WebViewHostPresentationAction action,
            WebViewHostNotPresentableReason reasonCode,
            string reason,
            bool shouldSetControllerBounds = false,
            bool shouldSetControllerVisible = false,
            bool shouldNotifyParentPositionChanged = false)
        {
            return new WebViewHostPresentationDecision
            {
                OldState = oldState,
                NewState = newState,
                Action = action,
                NotPresentableReason = reasonCode,
                ShouldSetControllerBounds = shouldSetControllerBounds,
                ShouldSetControllerVisible = action == WebViewHostPresentationAction.PresentController
                    && shouldSetControllerVisible,
                ShouldNotifyParentPositionChanged = action == WebViewHostPresentationAction.PresentController
                    && shouldNotifyParentPositionChanged,
                Reason = reason
            };
        }
    }
}
