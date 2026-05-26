using System;

namespace Rook.UI.Web
{
    internal interface IWebViewHostPresentationRecorder
    {
        void Append(WebViewHostPresentationRecord record);
    }

    internal sealed record WebViewHostPresentationRecord
    {
        public long Sequence { get; init; }
        public DateTimeOffset Utc { get; init; }
        public long ElapsedMilliseconds { get; init; }
        public string Reason { get; init; } = string.Empty;
        public WebViewHostPresentationState OldState { get; init; }
        public WebViewHostPresentationState NewState { get; init; }
        public WebViewHostPresentationAction Action { get; init; }
        public WebViewHostNotPresentableReason NotPresentableReason { get; init; }
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
        public bool ShouldSetControllerBounds { get; init; }
        public bool ShouldSetControllerVisible { get; init; }
        public bool ShouldNotifyParentPositionChanged { get; init; }
        public string ActionResult { get; init; } = string.Empty;
        public int ThreadId { get; init; }
    }
}
