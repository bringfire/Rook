using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimTransactionCommitGateTests
    {
        private sealed class ManualClock
        {
            public TimeSpan Now { get; set; } = TimeSpan.FromSeconds(100);

            public TimeSpan Read()
            {
                return Now;
            }
        }

        private static BimTransactionCommitGate Gate(int timeoutSeconds, ManualClock clock)
        {
            return new BimTransactionCommitGate(TimeSpan.FromSeconds(timeoutSeconds), clock.Read);
        }

        [Fact]
        public void ScriptWithinBudget_EntersAndCommits()
        {
            var clock = new ManualClock();
            var gate = Gate(60, clock);

            Assert.True(gate.TryEnterScript());
            clock.Now += TimeSpan.FromSeconds(59);
            Assert.True(gate.TryBeginCommit());

            Assert.False(gate.ScriptRanOverBudget);
            Assert.Equal(TimeSpan.FromSeconds(59), gate.ScriptDuration);
            // Once the host thread is committing, the caller can no longer cancel.
            Assert.Equal(BimTransactionCancelOutcome.NotCancelled, gate.Cancel());
        }

        [Fact]
        public void CancelBeforeScript_MeansTheScriptIsNeverEntered()
        {
            var gate = Gate(60, new ManualClock());

            Assert.Equal(BimTransactionCancelOutcome.BeforeScript, gate.Cancel());

            Assert.False(gate.TryEnterScript());
            Assert.False(gate.TryBeginCommit());
            Assert.Null(gate.ScriptDuration);
        }

        [Fact]
        public void CancelDuringScript_MeansTheScriptIsNeverCommitted()
        {
            var clock = new ManualClock();
            var gate = Gate(60, clock);
            Assert.True(gate.TryEnterScript());

            Assert.Equal(BimTransactionCancelOutcome.DuringScript, gate.Cancel());

            clock.Now += TimeSpan.FromSeconds(1);
            Assert.False(gate.TryBeginCommit());
            Assert.False(gate.ScriptRanOverBudget);
        }

        [Fact]
        public void ScriptOverBudget_IsRefusedByTheHostThreadEvenIfTheCallerHasNotCancelledYet()
        {
            // The request thread timed out but has not been scheduled to call
            // Cancel(). The host thread must not commit on that technicality.
            var clock = new ManualClock();
            var gate = Gate(1, clock);
            Assert.True(gate.TryEnterScript());

            clock.Now += TimeSpan.FromSeconds(1) + TimeSpan.FromMilliseconds(1);

            Assert.False(gate.TryBeginCommit());
            Assert.True(gate.ScriptRanOverBudget);
            Assert.Equal(TimeSpan.FromMilliseconds(1001), gate.ScriptDuration);
            // The late Cancel() from the request thread finds nothing to cancel.
            Assert.Equal(BimTransactionCancelOutcome.NotCancelled, gate.Cancel());
        }

        [Fact]
        public void ScriptExactlyOnBudget_StillCommits()
        {
            var clock = new ManualClock();
            var gate = Gate(1, clock);
            Assert.True(gate.TryEnterScript());

            clock.Now += TimeSpan.FromSeconds(1);

            Assert.True(gate.TryBeginCommit());
        }

        [Fact]
        public void TheBudgetIsMeasuredFromScriptEntryNotFromConstruction()
        {
            var clock = new ManualClock();
            var gate = Gate(5, clock);

            // Revit took a long time to pick the work up and prepare it.
            clock.Now += TimeSpan.FromSeconds(30);
            Assert.True(gate.TryEnterScript());
            clock.Now += TimeSpan.FromSeconds(4);

            Assert.True(gate.TryBeginCommit());
        }

        [Fact]
        public void CommitWithoutEnteringTheScript_IsRefused()
        {
            var gate = Gate(60, new ManualClock());

            Assert.False(gate.TryBeginCommit());
        }

        [Fact]
        public void EachTransitionHappensOnce()
        {
            var gate = Gate(60, new ManualClock());

            Assert.True(gate.TryEnterScript());
            Assert.False(gate.TryEnterScript());
            Assert.True(gate.TryBeginCommit());
            Assert.False(gate.TryBeginCommit());
        }

        [Fact]
        public void PickedUp_CompletesOnlyWhenTheHostThreadSaysSo()
        {
            var gate = Gate(60, new ManualClock());
            Assert.False(gate.PickedUp.IsCompleted);

            gate.MarkPickedUp();
            gate.MarkPickedUp();

            Assert.True(gate.PickedUp.Wait(TimeSpan.FromSeconds(5)));
        }

        [Fact]
        public void RacingCancelAndCommit_NeverBothWin()
        {
            for (var round = 0; round < 2000; round++)
            {
                var gate = new BimTransactionCommitGate(TimeSpan.FromSeconds(60));
                Assert.True(gate.TryEnterScript());
                var committed = false;
                var cancelled = BimTransactionCancelOutcome.NotCancelled;
                using (var start = new ManualResetEventSlim(false))
                {
                    var host = Task.Run(() =>
                    {
                        start.Wait();
                        committed = gate.TryBeginCommit();
                    });
                    var request = Task.Run(() =>
                    {
                        start.Wait();
                        cancelled = gate.Cancel();
                    });
                    start.Set();
                    Task.WaitAll(host, request);
                }

                // Exactly one side owns the outcome: a commit, or a caller who
                // was told there would be none.
                Assert.NotEqual(committed, cancelled == BimTransactionCancelOutcome.DuringScript);
                Assert.NotEqual(BimTransactionCancelOutcome.BeforeScript, cancelled);
            }
        }

        [Fact]
        public void RacingCancelAndScriptEntry_NeverBothWin()
        {
            for (var round = 0; round < 2000; round++)
            {
                var gate = new BimTransactionCommitGate(TimeSpan.FromSeconds(60));
                var entered = false;
                var cancelled = BimTransactionCancelOutcome.NotCancelled;
                using (var start = new ManualResetEventSlim(false))
                {
                    var host = Task.Run(() =>
                    {
                        start.Wait();
                        entered = gate.TryEnterScript();
                    });
                    var request = Task.Run(() =>
                    {
                        start.Wait();
                        cancelled = gate.Cancel();
                    });
                    start.Set();
                    Task.WaitAll(host, request);
                }

                // A caller told "the script never started" must be right.
                if (cancelled == BimTransactionCancelOutcome.BeforeScript)
                {
                    Assert.False(entered);
                }
                else
                {
                    Assert.True(entered);
                    Assert.Equal(BimTransactionCancelOutcome.DuringScript, cancelled);
                }
            }
        }

        [Fact]
        public void NonPositiveTimeout_IsRejected()
        {
            Assert.Throws<ArgumentOutOfRangeException>(
                () => new BimTransactionCommitGate(TimeSpan.Zero));
        }
    }
}
