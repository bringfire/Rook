using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Bim
{
    public enum BimTransactionCancelOutcome
    {
        /// <summary>Too late: the host thread is committing, or already decided the outcome.</summary>
        NotCancelled,

        /// <summary>The script had not been entered; it will never run.</summary>
        BeforeScript,

        /// <summary>The script is running; its transaction will be rolled back when it returns.</summary>
        DuringScript
    }

    /// <summary>
    /// Decides, exactly once, whether a run-transaction call may commit.
    /// Two threads use it: the request thread, which stops waiting after a
    /// timeout, and the host API thread, which runs the script and commits.
    ///
    /// Guarantees:
    /// - a caller that was told "cancelled" never gets a commit afterwards;
    /// - a script is never entered after the caller was told it would not run;
    /// - a script that ran longer than its budget is never committed, even if
    ///   the request thread has not noticed the timeout yet.
    ///
    /// Host-neutral (no Revit types) so these guarantees are unit-tested.
    /// </summary>
    public sealed class BimTransactionCommitGate
    {
        private const int Waiting = 0;
        private const int ScriptRunning = 1;
        private const int Committing = 2;
        private const int CancelledBeforeScript = 3;
        private const int CancelledDuringScript = 4;
        private const int OverBudget = 5;

        private readonly Func<TimeSpan> clock;
        private readonly TaskCompletionSource<bool> pickedUp =
            new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        private int state = Waiting;
        private long scriptEnteredTicks = -1;
        private long scriptEndedTicks = -1;

        public BimTransactionCommitGate(TimeSpan scriptTimeout)
            : this(scriptTimeout, MonotonicClock())
        {
        }

        internal BimTransactionCommitGate(TimeSpan scriptTimeout, Func<TimeSpan> clock)
        {
            if (scriptTimeout <= TimeSpan.Zero)
            {
                throw new ArgumentOutOfRangeException(nameof(scriptTimeout));
            }

            ScriptTimeout = scriptTimeout;
            this.clock = clock ?? throw new ArgumentNullException(nameof(clock));
        }

        public TimeSpan ScriptTimeout { get; }

        /// <summary>Completes when the host API thread has picked the work up.</summary>
        public Task PickedUp
        {
            get { return pickedUp.Task; }
        }

        /// <summary>True when the host thread refused the commit because the script ran over budget.</summary>
        public bool ScriptRanOverBudget
        {
            get { return Volatile.Read(ref state) == OverBudget; }
        }

        /// <summary>How long the script ran, once it has returned; null before that.</summary>
        public TimeSpan? ScriptDuration
        {
            get
            {
                var entered = Interlocked.Read(ref scriptEnteredTicks);
                var ended = Interlocked.Read(ref scriptEndedTicks);
                return entered < 0 || ended < 0
                    ? (TimeSpan?)null
                    : TimeSpan.FromTicks(ended - entered);
            }
        }

        /// <summary>Host thread: the work was dequeued and is being prepared.</summary>
        public void MarkPickedUp()
        {
            pickedUp.TrySetResult(true);
        }

        /// <summary>
        /// Host thread, immediately before running the script. False means the
        /// caller already stopped waiting: the script must not be run.
        /// The script budget is measured from this call.
        /// </summary>
        public bool TryEnterScript()
        {
            if (Interlocked.CompareExchange(ref state, ScriptRunning, Waiting) != Waiting)
            {
                return false;
            }

            Interlocked.Exchange(ref scriptEnteredTicks, clock().Ticks);
            return true;
        }

        /// <summary>
        /// Host thread, after the script returned and immediately before
        /// committing. False means the transaction must be rolled back:
        /// the caller cancelled, or the script ran over its budget.
        /// </summary>
        public bool TryBeginCommit()
        {
            var now = clock().Ticks;
            Interlocked.Exchange(ref scriptEndedTicks, now);
            var entered = Interlocked.Read(ref scriptEnteredTicks);
            if (entered < 0)
            {
                return false;
            }

            if (now - entered > ScriptTimeout.Ticks)
            {
                // Enforced here, not only by the waiting thread: that thread
                // may not have been scheduled yet when the script returns late.
                Interlocked.CompareExchange(ref state, OverBudget, ScriptRunning);
                return false;
            }

            return Interlocked.CompareExchange(ref state, Committing, ScriptRunning) == ScriptRunning;
        }

        /// <summary>Request thread, when it stops waiting.</summary>
        public BimTransactionCancelOutcome Cancel()
        {
            if (Interlocked.CompareExchange(ref state, CancelledBeforeScript, Waiting) == Waiting)
            {
                return BimTransactionCancelOutcome.BeforeScript;
            }

            if (Interlocked.CompareExchange(ref state, CancelledDuringScript, ScriptRunning) == ScriptRunning)
            {
                return BimTransactionCancelOutcome.DuringScript;
            }

            return BimTransactionCancelOutcome.NotCancelled;
        }

        private static Func<TimeSpan> MonotonicClock()
        {
            var stopwatch = Stopwatch.StartNew();
            return () => stopwatch.Elapsed;
        }
    }
}
