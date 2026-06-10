using Rhino.UI;

namespace Rook.UI.Web
{
    internal enum DesiredVisibilityChange { NoChange, Visible, DurablyHidden }

    /// <summary>
    /// Per-surface durable desired-visible mapping (spec table, f28db78).
    /// Dedicated panels only — Chat internal tabs are governed by Chat's
    /// own TabControl.SelectedIndex, not by this policy.
    /// Probe-driven/selected-tab/HWND readings NEVER reach this policy.
    /// </summary>
    internal static class PanelDesiredVisibilityPolicy
    {
        public static DesiredVisibilityChange OnPanelShown(ShowPanelReason reason)
            => DesiredVisibilityChange.Visible;

        public static DesiredVisibilityChange OnPanelHidden(
            ShowPanelReason reason, bool visibleAnyTab)
        {
            if (reason == ShowPanelReason.HideOnDeactivate)
                return DesiredVisibilityChange.NoChange;
            return visibleAnyTab
                ? DesiredVisibilityChange.NoChange
                : DesiredVisibilityChange.DurablyHidden;
        }

        public static DesiredVisibilityChange OnPanelClosing()
            => DesiredVisibilityChange.DurablyHidden;
    }
}
