namespace Rook.UI.Panels
{
    internal sealed class HostedPanelLifecycleCoordinator
    {
        public const int MaxDeferAttempts = 3;

        public HostedSurfaceDecision Decide(PanelLifecycleFacts facts)
        {
            if (facts.IsClosing)
            {
                return Decision(HostedSurfaceAction.Close, "closing", facts);
            }

            if (facts.LastReason == HostedPanelLifecycleReason.HideOnDeactivate)
            {
                if (!facts.IsHostReady)
                {
                    return DeferOrNone("temporary-deactivate-waiting-for-layout", facts);
                }

                return Decision(HostedSurfaceAction.None, "temporary-deactivate", facts);
            }

            if (!facts.IsSelectedTab)
            {
                return Decision(HostedSurfaceAction.Hide, "tab-unselected", facts);
            }

            if (!facts.IsRhinoSelectedPanelVisible)
            {
                return Decision(HostedSurfaceAction.Hide, "rhino-panel-tab-unselected", facts);
            }

            if (!facts.PanelReportedVisible)
            {
                return Decision(HostedSurfaceAction.Hide, "panel-hidden", facts);
            }

            if (!facts.IsHostReady)
            {
                return DeferOrNone("host-not-ready", facts);
            }

            return Decision(HostedSurfaceAction.Show, "show-ready", facts);
        }

        private static HostedSurfaceDecision DeferOrNone(
            string reason,
            PanelLifecycleFacts facts)
        {
            if (facts.DeferAttempt >= MaxDeferAttempts)
            {
                return Decision(HostedSurfaceAction.None, reason + ":defer-exhausted", facts);
            }

            return Decision(HostedSurfaceAction.Defer, reason, facts);
        }

        private static HostedSurfaceDecision Decision(
            HostedSurfaceAction action,
            string reason,
            PanelLifecycleFacts facts)
        {
            return new HostedSurfaceDecision
            {
                Action = action,
                Reason = reason,
                DeferAttempt = facts.DeferAttempt
            };
        }
    }
}
