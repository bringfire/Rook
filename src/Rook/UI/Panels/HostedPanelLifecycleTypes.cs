namespace Rook.UI.Panels
{
    internal enum HostedPanelLifecycleReason
    {
        Unknown,
        Show,
        Hide,
        HideOnDeactivate,
        ShowOnDeactivate
    }

    internal enum HostedSurfaceAction
    {
        None,
        Show,
        Hide,
        Defer,
        Close
    }

    internal sealed class PanelLifecycleFacts
    {
        public bool PanelReportedVisible { get; init; }
        public HostedPanelLifecycleReason LastReason { get; init; }
        public bool IsSelectedTab { get; init; }
        public bool IsRhinoSelectedPanelVisible { get; init; }
        public bool IsHostReady { get; init; }
        public bool IsClosing { get; init; }
        public int DeferAttempt { get; init; }
    }

    internal sealed class HostedSurfaceDecision
    {
        public HostedSurfaceAction Action { get; init; }
        public string Reason { get; init; } = "";
        public int DeferAttempt { get; init; }
    }
}
