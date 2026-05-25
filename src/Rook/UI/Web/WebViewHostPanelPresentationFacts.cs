namespace Rook.UI.Web
{
    internal sealed record WebViewHostPanelPresentationFacts
    {
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; }
        public bool PanelSelectedVisible { get; init; }
        public string Reason { get; init; } = string.Empty;
    }
}
