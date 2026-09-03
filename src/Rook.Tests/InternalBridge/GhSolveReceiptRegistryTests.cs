using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public sealed class GhSolveReceiptRegistryTests
    {
        private static readonly object DocumentA = new object();
        private static readonly object DocumentB = new object();
        private const string GhDocumentA = "11111111-1111-1111-1111-111111111111";
        private const string GhDocumentB = "22222222-2222-2222-2222-222222222222";

        [Fact]
        public void MutationReceipt_BindsActualGhDocumentAndFenceRejectsChangedGhDocument()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA, GhDocumentA);
            var receipt = issue.Receipt!;
            registry.MarkScheduleAccepted(receipt.ReceiptId);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);

            var same = registry.CheckFencedRead(receipt.ReceiptId, DocumentA, GhDocumentA);
            var changed = registry.CheckFencedRead(receipt.ReceiptId, DocumentA, GhDocumentB);

            Assert.Equal(GhDocumentA, receipt.GhDocumentId);
            Assert.True(same.Allowed);
            Assert.False(changed.Allowed);
            Assert.Equal("gh_target_changed", changed.Error);
        }

        [Fact]
        public void MatchingStartThenEnd_MarksLatestReceiptReady()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA);
            Assert.True(issue.Issued);
            var receipt = issue.Receipt!;
            registry.MarkScheduleAccepted(receipt.ReceiptId);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);

            var current = registry.Get(receipt.ReceiptId);

            Assert.True(current.Found);
            Assert.Equal(GhSolveReadinessStatus.Ready, current.Receipt!.Status);
            Assert.Equal(1, current.Receipt.SolutionRunEpoch);
            Assert.Equal(1, current.Receipt.CompletedSolutionRunEpoch);
            Assert.Equal("solution_end", current.Receipt.CompletionSignal);
        }

        [Fact]
        public void SolutionEndWithoutBoundStart_LeavesReceiptPending()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);

            registry.OnSolutionEnd(DocumentA);

            var current = registry.Get(receipt.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Pending, current.Receipt!.Status);
            Assert.Null(current.Receipt.SolutionRunEpoch);
            Assert.Equal(0, current.Receipt.CompletedSolutionRunEpoch);
        }

        [Fact]
        public void DuplicateStartBeforeCompletion_MarksReceiptUnknownInsteadOfAdvancingIt()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);

            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);

            var current = registry.Get(receipt.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Unknown, current.Receipt!.Status);
            Assert.Equal("lifecycle_correlation_ambiguous", current.Receipt.Reason);
        }

        [Fact]
        public void SolutionStartBeforeScheduleAcceptance_DoesNotBindReceipt()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA);
            var receipt = issue.Receipt!;

            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);
            registry.MarkScheduleAccepted(receipt.ReceiptId);

            var current = registry.Get(receipt.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Pending, current.Receipt!.Status);
            Assert.Null(current.Receipt.SolutionRunEpoch);
        }

        [Fact]
        public void MarkScheduleAccepted_AtPendingExpiryBoundary_ExpiresReceiptBeforeAcceptance()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            var issue = registry.IssueMutation(DocumentA);
            clock.Advance(TimeSpan.FromMinutes(10));

            var accepted = registry.MarkScheduleAccepted(issue.Receipt!.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, accepted.Status);
            Assert.Equal("receipt_expired", accepted.Reason);
        }

        [Fact]
        public void MarkScheduleAccepted_AfterPendingExpiryBoundary_ExpiresReceiptBeforeAcceptance()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            var issue = registry.IssueMutation(DocumentA);
            clock.Advance(TimeSpan.FromMinutes(10).Add(TimeSpan.FromTicks(1)));

            var accepted = registry.MarkScheduleAccepted(issue.Receipt!.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, accepted.Status);
            Assert.Equal("receipt_expired", accepted.Reason);
        }

        [Fact]
        public void ReadyReceipt_AllowsSameSessionFencedRead()
        {
            var registry = CreateReadyRegistry(out var receipt);

            var gate = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);

            Assert.True(gate.Allowed);
            Assert.Null(gate.Error);
            Assert.Equal(1, gate.Receipt!.SolutionRunEpoch);
        }

        [Fact]
        public void FencedReadObserver_ReceivesExactOwnedGateOncePerCheck()
        {
            var observed = new List<GhFencedReadGate>();
            var registry = new GhSolveReceiptRegistry(fencedReadObserver: gate => observed.Add(gate));
            var receipt = IssueScheduled(registry, DocumentA);

            var pending = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);
            var ready = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);

            Assert.Equal(2, observed.Count);
            Assert.Same(pending, observed[0]);
            Assert.Same(ready, observed[1]);
            Assert.False(observed[0].Allowed);
            Assert.True(observed[1].Allowed);
        }

        [Fact]
        public void LaterCompletedRun_RejectsEarlierFencedRead()
        {
            var registry = CreateReadyRegistry(out var receipt);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);

            var gate = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);

            Assert.False(gate.Allowed);
            Assert.Equal("readiness_receipt_stale_solution_run", gate.Error);
        }

        [Fact]
        public void LaterStartedRun_RejectsEarlierFencedReadBeforeCompletion()
        {
            var registry = CreateReadyRegistry(out var receipt);
            registry.OnSolutionStart(DocumentA);

            var gate = registry.CheckFencedRead(receipt.ReceiptId, DocumentA);

            Assert.False(gate.Allowed);
            Assert.Equal("readiness_receipt_stale_solution_run", gate.Error);
        }

        [Fact]
        public void WaitTimeout_LeavesReceiptPending_AndReleasesOwnership()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);

            var result = registry.Wait(receipt.ReceiptId, TimeSpan.FromMilliseconds(1), CancellationToken.None);

            Assert.Equal(GhReadinessWaitStatus.Timeout, result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.Pending, result.Receipt!.Status);
            Assert.True(registry.CanAcquireWaiterForTests(receipt.ReceiptId));
        }

        [Fact]
        public void Wait_BlocksUntilMatchingCompletionSignal()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);
            var waitTask = Task.Run(() => registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(5), CancellationToken.None));

            Assert.True(SpinWait.SpinUntil(() => !registry.CanAcquireWaiterForTests(receipt.ReceiptId), TimeSpan.FromSeconds(1)));
            Assert.False(waitTask.Wait(TimeSpan.FromMilliseconds(50)));

            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);

            Assert.True(waitTask.Wait(TimeSpan.FromSeconds(1)));
            Assert.Equal(GhReadinessWaitStatus.Ready, waitTask.Result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.Ready, waitTask.Result.Receipt!.Status);
        }

        [Fact]
        public void Wait_SecondPendingWaiter_IsRejectedWithoutTakingOwnership()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);
            var firstWait = Task.Run(() => registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(5), CancellationToken.None));
            Assert.True(SpinWait.SpinUntil(() => !registry.CanAcquireWaiterForTests(receipt.ReceiptId), TimeSpan.FromSeconds(1)));

            var secondWait = registry.Wait(receipt.ReceiptId, TimeSpan.FromMilliseconds(1), CancellationToken.None);

            Assert.Null(secondWait.WaitStatus);
            Assert.Equal("readiness_wait_already_active", secondWait.Error);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);
            Assert.True(firstWait.Wait(TimeSpan.FromSeconds(1)));
        }

        [Fact]
        public void Wait_Cancellation_ReleasesOwnership()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);
            using var cancellation = new CancellationTokenSource();
            cancellation.Cancel();

            Assert.Throws<OperationCanceledException>(() => registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(1), cancellation.Token));

            Assert.True(registry.CanAcquireWaiterForTests(receipt.ReceiptId));
        }

        [Fact]
        public void NewerMutation_SupersedesOlderReceiptImmediately()
        {
            var registry = CreateRegistry();
            var older = IssueScheduled(registry, DocumentA);

            var newerIssue = registry.IssueMutation(DocumentA);

            Assert.True(newerIssue.Issued);
            var olderLookup = registry.Get(older.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Superseded, olderLookup.Receipt!.Status);
            Assert.Equal("superseded", olderLookup.Receipt.Reason);
            Assert.Equal(2, newerIssue.Receipt!.MutationEpoch);
        }

        [Fact]
        public void Supersession_SignalsPendingWaiterAndReleasesOwnership()
        {
            var registry = CreateRegistry();
            var older = IssueScheduled(registry, DocumentA);
            var waitTask = Task.Run(() => registry.Wait(older.ReceiptId, TimeSpan.FromSeconds(5), CancellationToken.None));
            Assert.True(SpinWait.SpinUntil(() => !registry.CanAcquireWaiterForTests(older.ReceiptId), TimeSpan.FromSeconds(1)));

            registry.IssueMutation(DocumentA);

            Assert.True(waitTask.Wait(TimeSpan.FromSeconds(1)));
            Assert.Equal(GhReadinessWaitStatus.Terminal, waitTask.Result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.Superseded, waitTask.Result.Receipt!.Status);
            Assert.True(registry.CanAcquireWaiterForTests(older.ReceiptId));
        }

        [Fact]
        public void ReplaceDocument_TombstonesReceiptAndSignalsWaiter()
        {
            var registry = CreateRegistry();
            var receipt = IssueScheduled(registry, DocumentA);
            var waitTask = Task.Run(() => registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(5), CancellationToken.None));
            Assert.True(SpinWait.SpinUntil(() => !registry.CanAcquireWaiterForTests(receipt.ReceiptId), TimeSpan.FromSeconds(1)));

            registry.ReplaceDocument(DocumentB);

            Assert.True(waitTask.Wait(TimeSpan.FromSeconds(1)));
            Assert.Equal(GhReadinessWaitStatus.Terminal, waitTask.Result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.DocumentReplaced, waitTask.Result.Receipt!.Status);
        }

        [Fact]
        public void ReplaceDocument_ReadyReceiptInvalidatesStatusWaitAndFence()
        {
            var registry = CreateReadyRegistry(out var receipt);

            registry.ReplaceDocument(DocumentB);

            var lookup = registry.Get(receipt.ReceiptId);
            var wait = registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(1), CancellationToken.None);
            var gate = registry.CheckFencedRead(receipt.ReceiptId, DocumentB);
            Assert.Equal(GhSolveReadinessStatus.DocumentReplaced, lookup.Receipt!.Status);
            Assert.Equal("document_replaced", lookup.Receipt.Reason);
            Assert.Equal(GhReadinessWaitStatus.Terminal, wait.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.DocumentReplaced, wait.Receipt!.Status);
            Assert.False(gate.Allowed);
            Assert.Equal("readiness_receipt_document_replaced", gate.Error);
        }

        [Fact]
        public void ReplaceDocument_ReterminalizesEveryRetainedReceiptFromReplacedSession()
        {
            var registry = CreateRegistry();
            var failed = registry.IssueMutation(DocumentA).Receipt!;
            registry.MarkMutationFailed(failed.ReceiptId);
            var locked = registry.IssueMutation(DocumentA).Receipt!;
            registry.MarkSolverLocked(locked.ReceiptId);
            var superseded = IssueScheduled(registry, DocumentA);
            var pending = registry.IssueMutation(DocumentA).Receipt!;

            registry.ReplaceDocument(DocumentB);

            foreach (var receiptId in new[] { failed.ReceiptId, locked.ReceiptId, superseded.ReceiptId, pending.ReceiptId })
            {
                var retained = registry.Get(receiptId);
                Assert.Equal(GhSolveReadinessStatus.DocumentReplaced, retained.Receipt!.Status);
                Assert.Equal("document_replaced", retained.Receipt.Reason);
            }
        }

        [Fact]
        public void ReplaceDocument_PreservesUnrelatedTerminalReceiptState()
        {
            var registry = CreateRegistry();
            registry.ReplaceDocument(DocumentA);
            var unrelated = registry.IssueMutation(DocumentB).Receipt!;
            registry.MarkMutationFailed(unrelated.ReceiptId);

            registry.ReplaceDocument(new object());

            var retained = registry.Get(unrelated.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Unknown, retained.Receipt!.Status);
            Assert.Equal("mutation_failed", retained.Receipt.Reason);
        }

        [Fact]
        public void ReplaceDocument_DoesNotExtendUnrelatedTerminalRetentionAge()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            registry.ReplaceDocument(DocumentA);
            var issue = registry.IssueMutation(DocumentB);
            registry.MarkMutationFailed(issue.Receipt!.ReceiptId);
            clock.Advance(TimeSpan.FromMinutes(14));

            registry.ReplaceDocument(new object());
            clock.Advance(TimeSpan.FromMinutes(1).Add(TimeSpan.FromTicks(1)));

            Assert.False(registry.Get(issue.Receipt.ReceiptId).Found);
        }

        [Fact]
        public void LifecycleUnavailable_MarksReceiptUnknownWithStableReason()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA);
            var receipt = issue.Receipt!;

            registry.MarkLifecycleUnavailable(receipt.ReceiptId, "schedule_unavailable");

            var current = registry.Get(receipt.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Unknown, current.Receipt!.Status);
            Assert.Equal("schedule_unavailable", current.Receipt.Reason);
        }

        [Fact]
        public void NoSolveRelevantMutation_MarksReceiptUnknownWithExactReason()
        {
            var registry = CreateRegistry();
            var receipt = registry.IssueMutation(DocumentA).Receipt!;

            var terminal = registry.MarkNoSolveRelevantMutation(receipt.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, terminal.Status);
            Assert.Equal("no_solve_relevant_mutation_committed", terminal.Reason);
        }

        [Fact]
        public void UnknownMutationCommit_MarksReceiptUnknownWithExactReason()
        {
            var registry = CreateRegistry();
            var receipt = registry.IssueMutation(DocumentA).Receipt!;

            var terminal = registry.MarkMutationCommitUnknown(receipt.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, terminal.Status);
            Assert.Equal("mutation_commit_unknown", terminal.Reason);
        }

        [Fact]
        public void MutationFailure_CannotLeakPendingReceipt()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA);

            registry.MarkMutationFailed(issue.Receipt!.ReceiptId);

            var current = registry.Get(issue.Receipt.ReceiptId);
            Assert.Equal(GhSolveReadinessStatus.Unknown, current.Receipt!.Status);
            Assert.Equal("mutation_failed", current.Receipt.Reason);
        }

        [Fact]
        public void PendingReceipt_ExpiresToUnknown()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            var receipt = IssueScheduled(registry, DocumentA);
            clock.Advance(TimeSpan.FromMinutes(10).Add(TimeSpan.FromTicks(1)));

            var current = registry.Get(receipt.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, current.Receipt!.Status);
            Assert.Equal("receipt_expired", current.Receipt.Reason);
        }

        [Fact]
        public void TerminalReceipt_ExpiresFromLookupRetention()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            var issue = registry.IssueMutation(DocumentA);
            registry.MarkMutationFailed(issue.Receipt!.ReceiptId);
            clock.Advance(TimeSpan.FromMinutes(15).Add(TimeSpan.FromTicks(1)));

            var current = registry.Get(issue.Receipt.ReceiptId);

            Assert.False(current.Found);
            Assert.Equal("readiness_receipt_not_found_or_evicted_or_process_restarted", current.Error);
        }

        [Fact]
        public void TerminalCapacity_EvictsOldestTerminalWithoutBlockingNewMutation()
        {
            var registry = CreateRegistry();
            string? oldestReceiptId = null;
            string? nextOldestReceiptId = null;

            for (var index = 0; index < 257; index++)
            {
                var issue = registry.IssueMutation(DocumentA);
                Assert.True(issue.Issued);
                registry.MarkMutationFailed(issue.Receipt!.ReceiptId);
                if (index == 0)
                {
                    oldestReceiptId = issue.Receipt.ReceiptId;
                }
                else if (index == 1)
                {
                    nextOldestReceiptId = issue.Receipt.ReceiptId;
                }
            }

            Assert.False(registry.Get(oldestReceiptId!).Found);
            Assert.True(registry.Get(nextOldestReceiptId!).Found);
        }

        [Fact]
        public void Wait_EvictedSignaledReceipt_ReturnsCapturedTerminalResult()
        {
            using var waiterReachedReacquire = new ManualResetEventSlim(false);
            using var releaseWaiter = new ManualResetEventSlim(false);
            var registry = CreateRegistry(
                beforeWaiterReacquire: () =>
                {
                    waiterReachedReacquire.Set();
                    releaseWaiter.Wait(TimeSpan.FromSeconds(1));
                });
            var receipt = IssueScheduled(registry, DocumentA);
            var waitTask = Task.Run(() => registry.Wait(receipt.ReceiptId, TimeSpan.FromSeconds(5), CancellationToken.None));
            Assert.True(SpinWait.SpinUntil(() => !registry.CanAcquireWaiterForTests(receipt.ReceiptId), TimeSpan.FromSeconds(1)));

            registry.MarkMutationFailed(receipt.ReceiptId);
            Assert.True(waiterReachedReacquire.Wait(TimeSpan.FromSeconds(1)));
            for (var index = 0; index < 256; index++)
            {
                var issue = registry.IssueMutation(DocumentA);
                registry.MarkMutationFailed(issue.Receipt!.ReceiptId);
            }

            releaseWaiter.Set();

            Assert.True(waitTask.Wait(TimeSpan.FromSeconds(1)));
            Assert.Equal(GhReadinessWaitStatus.Terminal, waitTask.Result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.Unknown, waitTask.Result.Receipt!.Status);
            Assert.Equal("mutation_failed", waitTask.Result.Receipt.Reason);
        }

        [Fact]
        public void ExpiredTerminalReceipt_RemovesInactiveDocumentSessionWhilePreservingCurrentSession()
        {
            var clock = new TestClock();
            var registry = CreateRegistry(clock);
            registry.ReplaceDocument(DocumentA);
            var issue = registry.IssueMutation(DocumentB);
            registry.MarkMutationFailed(issue.Receipt!.ReceiptId);
            clock.Advance(TimeSpan.FromMinutes(15).Add(TimeSpan.FromTicks(1)));

            registry.Get(issue.Receipt.ReceiptId);

            Assert.Equal(1, registry.SessionCountForTests());
        }

        [Fact]
        public void ActiveCapacity_RejectsBeforeIssuingAnotherReceipt()
        {
            var registry = CreateRegistry();
            for (var index = 0; index < 64; index++)
            {
                Assert.True(registry.IssueMutation(new object()).Issued);
            }

            var rejected = registry.IssueMutation(new object());

            Assert.False(rejected.Issued);
            Assert.Null(rejected.Receipt);
            Assert.Equal("readiness_registry_capacity_exceeded", rejected.Error);
        }

        [Fact]
        public void TerminalReceipt_WaitReturnsImmediately()
        {
            var registry = CreateRegistry();
            var issue = registry.IssueMutation(DocumentA);
            registry.MarkSolverLocked(issue.Receipt!.ReceiptId);

            var result = registry.Wait(issue.Receipt.ReceiptId, TimeSpan.FromSeconds(1), CancellationToken.None);

            Assert.Equal(GhReadinessWaitStatus.Terminal, result.WaitStatus);
            Assert.Equal(GhSolveReadinessStatus.SolverLocked, result.Receipt!.Status);
            Assert.True(registry.CanAcquireWaiterForTests(issue.Receipt.ReceiptId));
        }

        [Fact]
        public void RegistrySource_UsesOnlySignalBasedWaits()
        {
            var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "GhSolveReceiptRegistry.cs"));

            Assert.Contains("WaitHandle.WaitAny", source);
            Assert.DoesNotContain("Thread.Sleep", source);
            Assert.DoesNotContain("Task.Delay", source);
            Assert.DoesNotContain("System.Threading.Timer", source);
            Assert.DoesNotContain("System.Timers", source);
            Assert.DoesNotContain("DispatcherTimer", source);
        }

        private static GhSolveReceiptRegistry CreateReadyRegistry(out GhSolveReadinessReceipt receipt)
        {
            var registry = CreateRegistry();
            receipt = IssueScheduled(registry, DocumentA);
            registry.OnSolutionStart(DocumentA);
            registry.OnSolutionEnd(DocumentA);
            return registry;
        }

        private static GhSolveReadinessReceipt IssueScheduled(GhSolveReceiptRegistry registry, object document)
        {
            var issue = registry.IssueMutation(document);
            Assert.True(issue.Issued);
            var receipt = issue.Receipt!;
            registry.MarkScheduleAccepted(receipt.ReceiptId);
            return receipt;
        }

        private static GhSolveReceiptRegistry CreateRegistry(
            TestClock? clock = null,
            Action? beforeWaiterReacquire = null)
        {
            clock ??= new TestClock();
            var nextId = 0;
            return new GhSolveReceiptRegistry(
                () => clock.Elapsed,
                () => "test-id-" + ++nextId,
                () => new DateTimeOffset(2026, 7, 9, 12, 0, 0, TimeSpan.Zero).Add(clock.Elapsed),
                beforeWaiterReacquire);
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory is not null)
            {
                if (Directory.Exists(Path.Combine(directory.FullName, "src", "Rook")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new DirectoryNotFoundException("Repository root was not found.");
        }

        private sealed class TestClock
        {
            internal TimeSpan Elapsed { get; private set; }

            internal void Advance(TimeSpan elapsed) => Elapsed = Elapsed.Add(elapsed);
        }
    }
}
