namespace Rook.UI.Web
{
    internal sealed record WebViewHostPanelPresentationFacts
    {
        public long Generation { get; init; }
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisibleAnyTab { get; init; }
        public bool PanelVisibleAnyTabPriorValue { get; init; }
        public bool PanelVisibleAnyTabProbeSucceeded { get; init; } = true;
        public string PanelVisibleAnyTabProbeStatus { get; init; } = "ok";
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; } = true;
        public bool PanelSelectedVisible { get; init; }
        public bool PanelSelectedVisiblePriorValue { get; init; }
        public bool PanelSelectedVisibleProbeSucceeded { get; init; } = true;
        public string PanelSelectedVisibleProbeStatus { get; init; } = "ok";
        public bool Disposed { get; init; }
        public bool Authoritative { get; init; } = true;
        public string Reason { get; init; } = string.Empty;
    }
}
