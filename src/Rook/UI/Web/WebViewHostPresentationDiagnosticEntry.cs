using System;

namespace Rook.UI.Web
{
    internal sealed record WebViewHostPresentationDiagnosticEntry
    {
        public int Sequence { get; init; }
        public DateTimeOffset TimestampUtc { get; init; }
        public string Surface { get; init; } = string.Empty;
        public string Reason { get; init; } = string.Empty;
        public WebViewHostPanelPresentationFactsDiagnostic Facts { get; init; } = new();
        public WebViewHostPresentationSnapshotDiagnostic Snapshot { get; init; } = new();
        public WebViewHostPresentationDecisionDiagnostic Decision { get; init; } = new();
        public string ActionResult { get; init; } = string.Empty;
    }

    internal sealed record WebViewHostPanelPresentationFactsDiagnostic
    {
        public long Generation { get; init; }
        public bool DesiredVisible { get; init; }
        public bool AppActive { get; init; }
        public bool TemporaryDeactivateHidden { get; init; }
        public bool PanelVisibleAnyTab { get; init; }
        public bool PanelVisibleAnyTabPriorValue { get; init; }
        public bool PanelVisibleAnyTabProbeSucceeded { get; init; }
        public string PanelVisibleAnyTabProbeStatus { get; init; } = string.Empty;
        public bool PanelVisible { get; init; }
        public bool RequiresSelectedPanel { get; init; }
        public bool PanelSelectedVisible { get; init; }
        public bool PanelSelectedVisiblePriorValue { get; init; }
        public bool PanelSelectedVisibleProbeSucceeded { get; init; }
        public string PanelSelectedVisibleProbeStatus { get; init; } = string.Empty;
        public bool Disposed { get; init; }
        public bool Authoritative { get; init; }
        public string Reason { get; init; } = string.Empty;

        public static WebViewHostPanelPresentationFactsDiagnostic From(
            WebViewHostPanelPresentationFacts facts)
        {
            return new WebViewHostPanelPresentationFactsDiagnostic
            {
                Generation = facts.Generation,
                DesiredVisible = facts.DesiredVisible,
                AppActive = facts.AppActive,
                TemporaryDeactivateHidden = facts.TemporaryDeactivateHidden,
                PanelVisibleAnyTab = facts.PanelVisibleAnyTab,
                PanelVisibleAnyTabPriorValue = facts.PanelVisibleAnyTabPriorValue,
                PanelVisibleAnyTabProbeSucceeded = facts.PanelVisibleAnyTabProbeSucceeded,
                PanelVisibleAnyTabProbeStatus = facts.PanelVisibleAnyTabProbeStatus,
                PanelVisible = facts.PanelVisible,
                RequiresSelectedPanel = facts.RequiresSelectedPanel,
                PanelSelectedVisible = facts.PanelSelectedVisible,
                PanelSelectedVisiblePriorValue = facts.PanelSelectedVisiblePriorValue,
                PanelSelectedVisibleProbeSucceeded = facts.PanelSelectedVisibleProbeSucceeded,
                PanelSelectedVisibleProbeStatus = facts.PanelSelectedVisibleProbeStatus,
                Disposed = facts.Disposed,
                Authoritative = facts.Authoritative,
                Reason = facts.Reason
            };
        }
    }

    internal sealed record WebViewHostPresentationSnapshotDiagnostic
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

        public static WebViewHostPresentationSnapshotDiagnostic From(
            WebViewHostPresentationSnapshot snapshot)
        {
            return new WebViewHostPresentationSnapshotDiagnostic
            {
                Disposed = snapshot.Disposed,
                DesiredVisible = snapshot.DesiredVisible,
                AppActive = snapshot.AppActive,
                TemporaryDeactivateHidden = snapshot.TemporaryDeactivateHidden,
                PanelVisible = snapshot.PanelVisible,
                RequiresSelectedPanel = snapshot.RequiresSelectedPanel,
                PanelSelectedVisible = snapshot.PanelSelectedVisible,
                EtoLoaded = snapshot.EtoLoaded,
                EtoVisible = snapshot.EtoVisible,
                EtoWidth = snapshot.EtoWidth,
                EtoHeight = snapshot.EtoHeight,
                ParentWindowPresent = snapshot.ParentWindowPresent,
                HwndChainVisible = snapshot.HwndChainVisible,
                HwndClientRectNonZero = snapshot.HwndClientRectNonZero,
                ControllerAvailable = snapshot.ControllerAvailable,
                ControllerParentWindowPresent = snapshot.ControllerParentWindowPresent,
                ControllerVisible = snapshot.ControllerVisible,
                ControllerBoundsMatchHostTarget = snapshot.ControllerBoundsMatchHostTarget
            };
        }
    }

    internal sealed record WebViewHostPresentationDecisionDiagnostic
    {
        public string OldState { get; init; } = string.Empty;
        public string NewState { get; init; } = string.Empty;
        public string Action { get; init; } = string.Empty;
        public string NotPresentableReason { get; init; } = string.Empty;
        public bool ShouldSetControllerBounds { get; init; }
        public bool ShouldSetControllerVisible { get; init; }
        public bool ShouldNotifyParentPositionChanged { get; init; }
        public string Reason { get; init; } = string.Empty;

        public static WebViewHostPresentationDecisionDiagnostic From(
            WebViewHostPresentationDecision decision)
        {
            return new WebViewHostPresentationDecisionDiagnostic
            {
                OldState = decision.OldState.ToString(),
                NewState = decision.NewState.ToString(),
                Action = decision.Action.ToString(),
                NotPresentableReason = decision.NotPresentableReason.ToString(),
                ShouldSetControllerBounds = decision.ShouldSetControllerBounds,
                ShouldSetControllerVisible = decision.ShouldSetControllerVisible,
                ShouldNotifyParentPositionChanged = decision.ShouldNotifyParentPositionChanged,
                Reason = decision.Reason
            };
        }
    }
}
