using Rook.Startup;
using Xunit;

namespace Rook.Tests.Plugin
{
    public class CompanionStartupGateTests
    {
        [Fact]
        public void CommandActive_DoesNotStartAndResetsStableIdle()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var first = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));
            var blocked = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: true,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, first.Action);
            Assert.Equal(1, first.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.None, blocked.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, blocked.BlockedReason);
            Assert.Equal(0, blocked.StableIdleCount);
        }

        [Fact]
        public void DocumentOpenActive_DoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: true,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.DocumentOpening, decision.BlockedReason);
            Assert.Equal(0, decision.StableIdleCount);
        }

        [Fact]
        public void FirstQuiescentIdle_DoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.None, decision.BlockedReason);
            Assert.Equal(1, decision.StableIdleCount);
        }

        [Fact]
        public void SecondConsecutiveQuiescentIdle_StartsOnce()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var start = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var repeated = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.RunStartup, start.Action);
            Assert.Equal(2, start.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.None, repeated.Action);
            Assert.True(repeated.StartupAlreadyRequested);
        }

        [Fact]
        public void InterruptedQuiescence_ResetsStableIdleCount()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, true, false));
            var firstAfterInterruption = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, firstAfterInterruption.Action);
            Assert.Equal(1, firstAfterInterruption.StableIdleCount);
        }

        [Fact]
        public void LoadedAfterBeginOpen_DoesNotRunUntilEndOpenOrStableIdleAfterCommandClears()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            var missedBeginOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: true,
                DocumentOpening: false,
                ShutdownStarted: false));
            var openStillActive = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: true,
                ShutdownStarted: false));
            var firstStableAfterOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));
            var secondStableAfterOpen = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: false));

            Assert.Equal(CompanionStartupGateAction.None, missedBeginOpen.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, missedBeginOpen.BlockedReason);
            Assert.Equal(CompanionStartupGateAction.None, openStillActive.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.DocumentOpening, openStillActive.BlockedReason);
            Assert.Equal(CompanionStartupGateAction.None, firstStableAfterOpen.Action);
            Assert.Equal(1, firstStableAfterOpen.StableIdleCount);
            Assert.Equal(CompanionStartupGateAction.RunStartup, secondStableAfterOpen.Action);
        }

        [Fact]
        public void StartupComplete_DoesNotRunAgain()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            gate.MarkStartupComplete();
            var afterComplete = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, afterComplete.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.StartupComplete, afterComplete.BlockedReason);
        }

        [Fact]
        public void BlockedQuiescence_WaitsUntilLaterQuiescentIdle()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 2);

            for (var i = 0; i < 500; i++)
            {
                var blocked = gate.EvaluateIdle(new CompanionStartupGateSnapshot(true, false, false));
                Assert.Equal(CompanionStartupGateAction.None, blocked.Action);
                Assert.Equal(CompanionStartupGateBlockedReason.CommandActive, blocked.BlockedReason);
            }

            var first = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));
            var second = gate.EvaluateIdle(new CompanionStartupGateSnapshot(false, false, false));

            Assert.Equal(CompanionStartupGateAction.None, first.Action);
            Assert.Equal(CompanionStartupGateAction.RunStartup, second.Action);
        }

        [Fact]
        public void ShutdownStarted_BlocksAndDoesNotStart()
        {
            var gate = new CompanionStartupGate(requiredStableIdleTicks: 1);

            var decision = gate.EvaluateIdle(new CompanionStartupGateSnapshot(
                CommandActive: false,
                DocumentOpening: false,
                ShutdownStarted: true));

            Assert.Equal(CompanionStartupGateAction.None, decision.Action);
            Assert.Equal(CompanionStartupGateBlockedReason.ShutdownStarted, decision.BlockedReason);
        }
    }
}
