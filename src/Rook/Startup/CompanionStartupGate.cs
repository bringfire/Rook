namespace Rook.Startup
{
    internal enum CompanionStartupGateAction
    {
        None,
        RunStartup,
    }

    internal enum CompanionStartupGateBlockedReason
    {
        None,
        CommandActive,
        DocumentOpening,
        ShutdownStarted,
        StartupComplete,
    }

    internal sealed record CompanionStartupGateSnapshot(
        bool CommandActive,
        bool DocumentOpening,
        bool ShutdownStarted);

    internal sealed record CompanionStartupGateDecision(
        CompanionStartupGateAction Action,
        CompanionStartupGateBlockedReason BlockedReason,
        int StableIdleCount,
        bool StartupAlreadyRequested,
        bool StartupComplete);

    internal sealed class CompanionStartupGate
    {
        private readonly int _requiredStableIdleTicks;
        private int _stableIdleCount;
        private bool _startupRequested;
        private bool _startupComplete;

        public CompanionStartupGate(
            int requiredStableIdleTicks = 2)
        {
            _requiredStableIdleTicks = requiredStableIdleTicks > 0
                ? requiredStableIdleTicks
                : 1;
        }

        public CompanionStartupGateDecision EvaluateIdle(
            CompanionStartupGateSnapshot snapshot)
        {
            if (_startupComplete)
            {
                return Decision(
                    CompanionStartupGateAction.None,
                    CompanionStartupGateBlockedReason.StartupComplete);
            }

            var blockedReason = GetBlockedReason(snapshot);
            if (blockedReason != CompanionStartupGateBlockedReason.None)
            {
                _stableIdleCount = 0;
                return Decision(CompanionStartupGateAction.None, blockedReason);
            }

            _stableIdleCount++;

            if (!_startupRequested && _stableIdleCount >= _requiredStableIdleTicks)
            {
                _startupRequested = true;
                return Decision(
                    CompanionStartupGateAction.RunStartup,
                    CompanionStartupGateBlockedReason.None);
            }

            return Decision(
                CompanionStartupGateAction.None,
                CompanionStartupGateBlockedReason.None);
        }

        public void MarkStartupComplete()
        {
            _startupComplete = true;
        }

        public void MarkStartupAvailableForRetry()
        {
            if (!_startupComplete)
            {
                _startupRequested = false;
                _stableIdleCount = _requiredStableIdleTicks - 1;
            }
        }

        private static CompanionStartupGateBlockedReason GetBlockedReason(
            CompanionStartupGateSnapshot snapshot)
        {
            if (snapshot.ShutdownStarted)
                return CompanionStartupGateBlockedReason.ShutdownStarted;
            if (snapshot.DocumentOpening)
                return CompanionStartupGateBlockedReason.DocumentOpening;
            if (snapshot.CommandActive)
                return CompanionStartupGateBlockedReason.CommandActive;
            return CompanionStartupGateBlockedReason.None;
        }

        private CompanionStartupGateDecision Decision(
            CompanionStartupGateAction action,
            CompanionStartupGateBlockedReason reason)
        {
            return new CompanionStartupGateDecision(
                action,
                reason,
                _stableIdleCount,
                _startupRequested,
                _startupComplete);
        }
    }
}
