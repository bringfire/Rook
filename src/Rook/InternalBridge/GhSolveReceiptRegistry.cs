using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading;
using System.Runtime.CompilerServices;

namespace Rook.InternalBridge
{
    internal enum GhSolveReadinessStatus
    {
        Pending,
        Ready,
        Superseded,
        DocumentReplaced,
        SolverLocked,
        Unknown,
    }

    internal sealed record GhSolveReadinessReceipt(
        string ReceiptId,
        string DocumentSessionId,
        long MutationEpoch,
        long? SolutionRunEpoch,
        long CompletedSolutionRunEpoch,
        GhSolveReadinessStatus Status,
        string? Reason,
        string? CompletionSignal,
        DateTimeOffset IssuedAt,
        DateTimeOffset? CompletedAt,
        string? GhDocumentId = null);

    internal sealed record GhReadinessIssueResult(
        bool Issued,
        GhSolveReadinessReceipt? Receipt,
        string? Error);

    internal sealed record GhReadinessLookup(
        bool Found,
        GhSolveReadinessReceipt? Receipt,
        string? Error);

    internal enum GhReadinessWaitStatus
    {
        Ready,
        Timeout,
        Terminal,
    }

    internal sealed record GhReadinessWaitResult(
        GhReadinessWaitStatus? WaitStatus,
        GhSolveReadinessReceipt? Receipt,
        string? Error);

    internal sealed record GhFencedReadGate(
        bool Allowed,
        GhSolveReadinessReceipt? Receipt,
        string? Error);

    internal sealed class GhSolveReceiptRegistry
    {
        private const int ActiveCapacity = 64;
        private const int TerminalCapacity = 256;
        private static readonly TimeSpan PendingRetention = TimeSpan.FromMinutes(10);
        private static readonly TimeSpan TerminalRetention = TimeSpan.FromMinutes(15);
        private const string NotFoundError = "readiness_receipt_not_found_or_evicted_or_process_restarted";

        private readonly object _sync = new();
        private readonly Func<TimeSpan> _monotonicNow;
        private readonly Func<string> _idFactory;
        private readonly Func<DateTimeOffset> _utcNow;
        private readonly Action? _beforeWaiterReacquire;
        private readonly Action<GhFencedReadGate>? _fencedReadObserver;
        private readonly Dictionary<string, ReceiptEntry> _entries = new(StringComparer.Ordinal);
        private readonly Dictionary<object, DocumentSession> _sessions = new(ObjectReferenceComparer.Instance);
        private long _nextInsertionOrder;
        private object? _currentDocument;

        internal GhSolveReceiptRegistry(
            Func<TimeSpan>? monotonicNow = null,
            Func<string>? idFactory = null,
            Func<DateTimeOffset>? utcNow = null,
            Action? beforeWaiterReacquire = null,
            Action<GhFencedReadGate>? fencedReadObserver = null)
        {
            _monotonicNow = monotonicNow ?? GetMonotonicNow;
            _idFactory = idFactory ?? CreateSecureId;
            _utcNow = utcNow ?? (() => DateTimeOffset.UtcNow);
            _beforeWaiterReacquire = beforeWaiterReacquire;
            _fencedReadObserver = fencedReadObserver;
        }

        internal GhReadinessIssueResult IssueMutation(object document, string? ghDocumentId = null)
        {
            if (document is null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            lock (_sync)
            {
                var now = _monotonicNow();
                Purge(now);
                if (CountPending() >= ActiveCapacity)
                {
                    return new GhReadinessIssueResult(false, null, "readiness_registry_capacity_exceeded");
                }

                _currentDocument ??= document;
                var session = GetOrCreateSession(document);
                SupersedeSessionReceipts(session, now);

                var receipt = new GhSolveReadinessReceipt(
                    _idFactory(),
                    session.SessionId,
                    ++session.MutationEpoch,
                    null,
                    session.CompletedSolutionRunEpoch,
                    GhSolveReadinessStatus.Pending,
                    null,
                    null,
                    _utcNow(),
                    null,
                    ghDocumentId);
                var entry = new ReceiptEntry(receipt, now, ++_nextInsertionOrder);
                _entries.Add(receipt.ReceiptId, entry);
                session.LatestReceiptId = receipt.ReceiptId;
                return new GhReadinessIssueResult(true, receipt, null);
            }
        }

        internal GhSolveReadinessReceipt MarkMutationFailed(string receiptId) =>
            MarkPendingTerminal(receiptId, GhSolveReadinessStatus.Unknown, "mutation_failed");

        internal GhSolveReadinessReceipt MarkNoSolveRelevantMutation(string receiptId) =>
            MarkPendingTerminal(
                receiptId,
                GhSolveReadinessStatus.Unknown,
                "no_solve_relevant_mutation_committed");

        internal GhSolveReadinessReceipt MarkMutationCommitUnknown(string receiptId) =>
            MarkPendingTerminal(receiptId, GhSolveReadinessStatus.Unknown, "mutation_commit_unknown");

        internal GhSolveReadinessReceipt MarkSolverLocked(string receiptId) =>
            MarkPendingTerminal(receiptId, GhSolveReadinessStatus.SolverLocked, "solver_locked");

        internal GhSolveReadinessReceipt MarkScheduleAccepted(string receiptId)
        {
            lock (_sync)
            {
                Purge(_monotonicNow());
                var entry = GetRequiredEntry(receiptId);
                if (entry.Receipt.Status == GhSolveReadinessStatus.Pending)
                {
                    entry.ScheduleAccepted = true;
                }

                return entry.Receipt;
            }
        }

        internal void MarkLifecycleUnavailable(string receiptId, string reason)
        {
            if (string.IsNullOrWhiteSpace(reason))
            {
                throw new ArgumentException("A lifecycle-unavailable reason is required.", nameof(reason));
            }

            MarkPendingTerminal(receiptId, GhSolveReadinessStatus.Unknown, reason);
        }

        internal void OnSolutionStart(object document)
        {
            if (document is null)
            {
                return;
            }

            lock (_sync)
            {
                var now = _monotonicNow();
                Purge(now);
                if (!_sessions.TryGetValue(document, out var session))
                {
                    return;
                }

                if (session.ActiveSolutionRunEpoch.HasValue)
                {
                    if (session.BoundReceiptId is not null &&
                        _entries.TryGetValue(session.BoundReceiptId, out var priorEntry) &&
                        priorEntry.Receipt.Status == GhSolveReadinessStatus.Pending)
                    {
                        TransitionTerminal(
                            priorEntry,
                            GhSolveReadinessStatus.Unknown,
                            "lifecycle_correlation_ambiguous",
                            null,
                            now);
                    }

                    session.BoundReceiptId = null;
                    TrimTerminalEntries();
                }

                var runEpoch = ++session.SolutionRunEpoch;
                session.ActiveSolutionRunEpoch = runEpoch;
                if (session.LatestReceiptId is null ||
                    !_entries.TryGetValue(session.LatestReceiptId, out var entry) ||
                    entry.Receipt.Status != GhSolveReadinessStatus.Pending ||
                    !entry.ScheduleAccepted ||
                    entry.Receipt.SolutionRunEpoch.HasValue)
                {
                    return;
                }

                entry.Receipt = entry.Receipt with
                {
                    SolutionRunEpoch = runEpoch,
                    CompletedSolutionRunEpoch = session.CompletedSolutionRunEpoch,
                };
                session.BoundReceiptId = entry.Receipt.ReceiptId;
            }
        }

        internal void OnSolutionEnd(object document)
        {
            if (document is null)
            {
                return;
            }

            lock (_sync)
            {
                var now = _monotonicNow();
                Purge(now);
                if (!_sessions.TryGetValue(document, out var session) || !session.ActiveSolutionRunEpoch.HasValue)
                {
                    return;
                }

                var completedRunEpoch = session.ActiveSolutionRunEpoch.Value;
                var boundReceiptId = session.BoundReceiptId;
                session.ActiveSolutionRunEpoch = null;
                session.BoundReceiptId = null;
                session.CompletedSolutionRunEpoch = completedRunEpoch;

                if (boundReceiptId is null ||
                    !_entries.TryGetValue(boundReceiptId, out var entry) ||
                    entry.Receipt.Status != GhSolveReadinessStatus.Pending ||
                    entry.Receipt.SolutionRunEpoch != completedRunEpoch)
                {
                    return;
                }

                entry.Receipt = entry.Receipt with { CompletedSolutionRunEpoch = completedRunEpoch };
                TransitionTerminal(entry, GhSolveReadinessStatus.Ready, null, "solution_end", now);
                TrimTerminalEntries();
            }
        }

        internal GhReadinessLookup Get(string receiptId)
        {
            lock (_sync)
            {
                Purge(_monotonicNow());
                return _entries.TryGetValue(receiptId, out var entry)
                    ? new GhReadinessLookup(true, entry.Receipt, null)
                    : new GhReadinessLookup(false, null, NotFoundError);
            }
        }

        internal GhReadinessWaitResult Wait(string receiptId, TimeSpan timeout, CancellationToken cancellationToken)
        {
            ReceiptEntry entry;
            WaitHandle completionSignal;
            lock (_sync)
            {
                Purge(_monotonicNow());
                if (!_entries.TryGetValue(receiptId, out entry!))
                {
                    return new GhReadinessWaitResult(null, null, NotFoundError);
                }

                if (entry.Receipt.Status != GhSolveReadinessStatus.Pending)
                {
                    return ResultForTerminal(entry.Receipt);
                }

                if (entry.WaiterActive)
                {
                    return new GhReadinessWaitResult(null, entry.Receipt, "readiness_wait_already_active");
                }

                entry.WaiterActive = true;
                completionSignal = entry.CompletionSignal;
            }

            try
            {
                var waitResult = WaitHandle.WaitAny(new[] { completionSignal, cancellationToken.WaitHandle }, timeout);
                if (waitResult == 1)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                }

                GhSolveReadinessReceipt? capturedTerminalReceipt = null;
                if (waitResult == 0)
                {
                    _beforeWaiterReacquire?.Invoke();
                    if (entry.Receipt.Status != GhSolveReadinessStatus.Pending)
                    {
                        capturedTerminalReceipt = entry.Receipt;
                    }
                }

                lock (_sync)
                {
                    Purge(_monotonicNow());
                    if (!_entries.TryGetValue(receiptId, out var current))
                    {
                        return capturedTerminalReceipt is not null
                            ? ResultForTerminal(capturedTerminalReceipt)
                            : new GhReadinessWaitResult(null, null, NotFoundError);
                    }

                    return current.Receipt.Status == GhSolveReadinessStatus.Pending
                        ? new GhReadinessWaitResult(GhReadinessWaitStatus.Timeout, current.Receipt, null)
                        : ResultForTerminal(current.Receipt);
                }
            }
            finally
            {
                lock (_sync)
                {
                    entry.WaiterActive = false;
                    DisposeEvictedSignalIfUnused(entry);
                }
            }
        }

        internal GhFencedReadGate CheckFencedRead(
            string receiptId,
            object activeDocument,
            string? activeGhDocumentId = null)
        {
            GhFencedReadGate gate;
            lock (_sync)
            {
                Purge(_monotonicNow());
                if (!_entries.TryGetValue(receiptId, out var entry))
                {
                    gate = new GhFencedReadGate(false, null, NotFoundError);
                }
                else
                {
                    var receipt = entry.Receipt;
                    if (receipt.Status != GhSolveReadinessStatus.Ready)
                    {
                        gate = new GhFencedReadGate(false, receipt, FenceErrorFor(receipt));
                    }
                    else if (receipt.GhDocumentId is not null &&
                        !string.Equals(
                            receipt.GhDocumentId,
                            activeGhDocumentId,
                            StringComparison.Ordinal))
                    {
                        gate = new GhFencedReadGate(false, receipt, "gh_target_changed");
                    }
                    else if (activeDocument is null ||
                        !_sessions.TryGetValue(activeDocument, out var session) ||
                        session.SessionId != receipt.DocumentSessionId)
                    {
                        gate = new GhFencedReadGate(false, receipt, "readiness_receipt_document_replaced");
                    }
                    else if (session.MutationEpoch != receipt.MutationEpoch)
                    {
                        gate = new GhFencedReadGate(false, receipt, "readiness_receipt_superseded");
                    }
                    else if (!receipt.SolutionRunEpoch.HasValue ||
                        receipt.CompletedSolutionRunEpoch != receipt.SolutionRunEpoch.Value ||
                        session.CompletedSolutionRunEpoch != receipt.SolutionRunEpoch.Value ||
                        session.SolutionRunEpoch != receipt.SolutionRunEpoch.Value ||
                        session.ActiveSolutionRunEpoch.HasValue)
                    {
                        gate = new GhFencedReadGate(false, receipt, "readiness_receipt_stale_solution_run");
                    }
                    else
                    {
                        gate = new GhFencedReadGate(true, receipt, null);
                    }
                }
            }

            _fencedReadObserver?.Invoke(gate);
            return gate;
        }

        internal void ReplaceDocument(object? newDocument)
        {
            lock (_sync)
            {
                var now = _monotonicNow();
                Purge(now);
                var replacedSessionId = _currentDocument is not null &&
                    _sessions.TryGetValue(_currentDocument, out var replacedSession)
                        ? replacedSession.SessionId
                        : null;
                if (replacedSessionId is not null)
                {
                    foreach (var entry in _entries.Values)
                    {
                        if (entry.Receipt.DocumentSessionId == replacedSessionId)
                        {
                            TransitionTerminal(entry, GhSolveReadinessStatus.DocumentReplaced, "document_replaced", null, now);
                        }
                    }
                }

                _sessions.Clear();
                _currentDocument = newDocument;
                if (newDocument is not null)
                {
                    GetOrCreateSession(newDocument);
                }

                TrimTerminalEntries();
            }
        }

        internal bool CanAcquireWaiterForTests(string receiptId)
        {
            lock (_sync)
            {
                Purge(_monotonicNow());
                return _entries.TryGetValue(receiptId, out var entry) &&
                    (entry.Receipt.Status != GhSolveReadinessStatus.Pending || !entry.WaiterActive);
            }
        }

        internal int SessionCountForTests()
        {
            lock (_sync)
            {
                Purge(_monotonicNow());
                return _sessions.Count;
            }
        }

        private GhSolveReadinessReceipt MarkPendingTerminal(
            string receiptId,
            GhSolveReadinessStatus status,
            string reason)
        {
            lock (_sync)
            {
                var now = _monotonicNow();
                Purge(now);
                var entry = GetRequiredEntry(receiptId);
                if (entry.Receipt.Status == GhSolveReadinessStatus.Pending)
                {
                    TransitionTerminal(entry, status, reason, null, now);
                    TrimTerminalEntries();
                }

                return entry.Receipt;
            }
        }

        private void SupersedeSessionReceipts(DocumentSession session, TimeSpan now)
        {
            foreach (var entry in _entries.Values)
            {
                if (entry.Receipt.DocumentSessionId == session.SessionId &&
                    (entry.Receipt.Status == GhSolveReadinessStatus.Pending ||
                     entry.Receipt.Status == GhSolveReadinessStatus.Ready))
                {
                    TransitionTerminal(entry, GhSolveReadinessStatus.Superseded, "superseded", null, now);
                }
            }

            TrimTerminalEntries();
        }

        private void Purge(TimeSpan now)
        {
            var expiredPending = new List<ReceiptEntry>();
            foreach (var entry in _entries.Values)
            {
                if (entry.Receipt.Status == GhSolveReadinessStatus.Pending && now - entry.IssuedAtMonotonic >= PendingRetention)
                {
                    expiredPending.Add(entry);
                }
            }

            foreach (var entry in expiredPending)
            {
                TransitionTerminal(entry, GhSolveReadinessStatus.Unknown, "receipt_expired", null, now);
            }

            var expiredTerminalIds = new List<string>();
            foreach (var pair in _entries)
            {
                var terminalizedAt = pair.Value.TerminalizedAtMonotonic;
                if (terminalizedAt.HasValue && now - terminalizedAt.Value > TerminalRetention)
                {
                    expiredTerminalIds.Add(pair.Key);
                }
            }

            foreach (var receiptId in expiredTerminalIds)
            {
                RemoveEntry(receiptId);
            }

            TrimTerminalEntries();
            TrimInactiveSessions();
        }

        private void TrimTerminalEntries()
        {
            while (CountTerminal() > TerminalCapacity)
            {
                ReceiptEntry? oldest = null;
                foreach (var entry in _entries.Values)
                {
                    if (!entry.TerminalizedAtMonotonic.HasValue ||
                        (oldest is not null && CompareTerminalAge(entry, oldest) >= 0))
                    {
                        continue;
                    }

                    oldest = entry;
                }

                if (oldest is null)
                {
                    return;
                }

                RemoveEntry(oldest.Receipt.ReceiptId);
            }

        }

        private void RemoveEntry(string receiptId)
        {
            if (!_entries.TryGetValue(receiptId, out var entry))
            {
                return;
            }

            _entries.Remove(receiptId);
            entry.Evicted = true;
            DisposeEvictedSignalIfUnused(entry);
        }

        private static void DisposeEvictedSignalIfUnused(ReceiptEntry entry)
        {
            if (entry.Evicted && !entry.WaiterActive)
            {
                entry.CompletionSignal.Dispose();
            }
        }

        private void TrimInactiveSessions()
        {
            var documentsToRemove = new List<object>();
            foreach (var pair in _sessions)
            {
                if (ReferenceEquals(pair.Key, _currentDocument) ||
                    pair.Value.ActiveSolutionRunEpoch.HasValue ||
                    HasReceiptForSession(pair.Value.SessionId))
                {
                    continue;
                }

                documentsToRemove.Add(pair.Key);
            }

            foreach (var document in documentsToRemove)
            {
                _sessions.Remove(document);
            }
        }

        private bool HasReceiptForSession(string sessionId)
        {
            foreach (var entry in _entries.Values)
            {
                if (entry.Receipt.DocumentSessionId == sessionId)
                {
                    return true;
                }
            }

            return false;
        }

        private static int CompareTerminalAge(ReceiptEntry left, ReceiptEntry right)
        {
            var timestampComparison = left.TerminalizedAtMonotonic!.Value.CompareTo(right.TerminalizedAtMonotonic!.Value);
            return timestampComparison != 0 ? timestampComparison : left.InsertionOrder.CompareTo(right.InsertionOrder);
        }

        private void TransitionTerminal(
            ReceiptEntry entry,
            GhSolveReadinessStatus status,
            string? reason,
            string? completionSignal,
            TimeSpan now)
        {
            entry.Receipt = entry.Receipt with
            {
                Status = status,
                Reason = reason,
                CompletionSignal = completionSignal,
                CompletedAt = _utcNow(),
            };
            entry.TerminalizedAtMonotonic = now;
            entry.CompletionSignal.Set();
        }

        private int CountPending()
        {
            var count = 0;
            foreach (var entry in _entries.Values)
            {
                if (entry.Receipt.Status == GhSolveReadinessStatus.Pending)
                {
                    count++;
                }
            }

            return count;
        }

        private int CountTerminal()
        {
            var count = 0;
            foreach (var entry in _entries.Values)
            {
                if (entry.TerminalizedAtMonotonic.HasValue)
                {
                    count++;
                }
            }

            return count;
        }

        private DocumentSession GetOrCreateSession(object document)
        {
            if (!_sessions.TryGetValue(document, out var session))
            {
                session = new DocumentSession(_idFactory());
                _sessions.Add(document, session);
            }

            return session;
        }

        private ReceiptEntry GetRequiredEntry(string receiptId)
        {
            if (!_entries.TryGetValue(receiptId, out var entry))
            {
                throw new ArgumentException(NotFoundError, nameof(receiptId));
            }

            return entry;
        }

        private static GhReadinessWaitResult ResultForTerminal(GhSolveReadinessReceipt receipt)
        {
            return receipt.Status == GhSolveReadinessStatus.Ready
                ? new GhReadinessWaitResult(GhReadinessWaitStatus.Ready, receipt, null)
                : new GhReadinessWaitResult(GhReadinessWaitStatus.Terminal, receipt, null);
        }

        private static string FenceErrorFor(GhSolveReadinessReceipt receipt)
        {
            return receipt.Status switch
            {
                GhSolveReadinessStatus.Pending => "readiness_receipt_not_ready",
                GhSolveReadinessStatus.Superseded => "readiness_receipt_superseded",
                GhSolveReadinessStatus.DocumentReplaced => "readiness_receipt_document_replaced",
                GhSolveReadinessStatus.SolverLocked => "readiness_receipt_solver_locked",
                GhSolveReadinessStatus.Unknown when receipt.Reason == "receipt_expired" => "readiness_receipt_expired",
                _ => "readiness_receipt_unknown",
            };
        }

        private static TimeSpan GetMonotonicNow() =>
            TimeSpan.FromSeconds((double)Stopwatch.GetTimestamp() / Stopwatch.Frequency);

        private static string CreateSecureId()
        {
            var bytes = new byte[16];
            using (var random = RandomNumberGenerator.Create())
            {
                random.GetBytes(bytes);
            }

            return BitConverter.ToString(bytes).Replace("-", string.Empty).ToLowerInvariant();
        }

        private sealed class ReceiptEntry
        {
            internal ReceiptEntry(GhSolveReadinessReceipt receipt, TimeSpan issuedAtMonotonic, long insertionOrder)
            {
                Receipt = receipt;
                IssuedAtMonotonic = issuedAtMonotonic;
                InsertionOrder = insertionOrder;
                CompletionSignal = new ManualResetEvent(false);
            }

            internal GhSolveReadinessReceipt Receipt { get; set; }
            internal TimeSpan IssuedAtMonotonic { get; }
            internal long InsertionOrder { get; }
            internal ManualResetEvent CompletionSignal { get; }
            internal TimeSpan? TerminalizedAtMonotonic { get; set; }
            internal bool ScheduleAccepted { get; set; }
            internal bool WaiterActive { get; set; }
            internal bool Evicted { get; set; }
        }

        private sealed class DocumentSession
        {
            internal DocumentSession(string sessionId)
            {
                SessionId = sessionId;
            }

            internal string SessionId { get; }
            internal long MutationEpoch { get; set; }
            internal long SolutionRunEpoch { get; set; }
            internal long CompletedSolutionRunEpoch { get; set; }
            internal long? ActiveSolutionRunEpoch { get; set; }
            internal string? BoundReceiptId { get; set; }
            internal string? LatestReceiptId { get; set; }
        }

        private sealed class ObjectReferenceComparer : IEqualityComparer<object>
        {
            internal static readonly ObjectReferenceComparer Instance = new();

            bool IEqualityComparer<object>.Equals(object? x, object? y) => ReferenceEquals(x, y);

            int IEqualityComparer<object>.GetHashCode(object obj) => RuntimeHelpers.GetHashCode(obj);
        }
    }
}
