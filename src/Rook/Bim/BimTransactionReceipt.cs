using System;
using System.Collections.Generic;
using System.Linq;

namespace Rook.Bim
{
    /// <summary>Where a host transaction is, as the host observed it.</summary>
    public enum BimTransactionStatus
    {
        /// <summary>No transaction was started. The document is unchanged.</summary>
        NotStarted,

        /// <summary>A transaction is open and the edit is running or being finished.</summary>
        Open,

        /// <summary>The host confirmed the commit.</summary>
        Committed,

        /// <summary>The host confirmed the rollback. The document is unchanged.</summary>
        RolledBack,

        /// <summary>The host could not confirm how the transaction ended.</summary>
        Unresolved
    }

    /// <summary>An immutable copy of a receipt at one moment.</summary>
    public sealed class BimTransactionReceiptSnapshot
    {
        internal BimTransactionReceiptSnapshot(
            string id,
            string name,
            BimTransactionStatus status,
            bool commitProhibited,
            BimErrorCode cause,
            string? message,
            BimDocumentIdentity? document,
            DateTime updatedUtc)
        {
            Id = id;
            Name = name;
            Status = status;
            CommitProhibited = commitProhibited;
            Cause = cause;
            Message = message;
            Document = document;
            UpdatedUtc = updatedUtc;
        }

        public string Id { get; }

        public string Name { get; }

        public BimTransactionStatus Status { get; }

        /// <summary>True once this transaction can no longer be committed.</summary>
        public bool CommitProhibited { get; }

        /// <summary>Why the edit did not commit; <see cref="BimErrorCode.None"/> when it did or has not ended.</summary>
        public BimErrorCode Cause { get; }

        public string? Message { get; }

        public BimDocumentIdentity? Document { get; }

        public DateTime UpdatedUtc { get; }

        public bool IsTerminal
        {
            get
            {
                return Status == BimTransactionStatus.NotStarted && Cause != BimErrorCode.None ||
                    Status == BimTransactionStatus.Committed ||
                    Status == BimTransactionStatus.RolledBack;
            }
        }
    }

    /// <summary>
    /// The single owner of the answer to "what happened to my edit?".
    ///
    /// The host thread that runs the transaction is the only writer of the
    /// status. Every response about the transaction, whether it comes from
    /// that thread, from a request thread that stopped waiting, or from a
    /// later lookup, is derived from a snapshot of this object, so no
    /// component can report an outcome the host did not observe, and nothing
    /// that happens after a commit (reporting, serialization) can change it.
    /// </summary>
    public sealed class BimTransactionReceipt
    {
        private readonly object sync = new object();
        private BimTransactionStatus status = BimTransactionStatus.NotStarted;
        private bool commitProhibited;
        private BimErrorCode cause = BimErrorCode.None;
        private string? message;
        private BimDocumentIdentity? document;
        private DateTime updatedUtc = DateTime.UtcNow;

        internal BimTransactionReceipt(string id, string name)
        {
            Id = id;
            Name = name;
        }

        public string Id { get; }

        public string Name { get; }

        /// <summary>The document the write is about to run on, recorded before anything is started.</summary>
        public void SetDocument(BimDocumentIdentity? identity)
        {
            lock (sync)
            {
                document = identity;
                updatedUtc = DateTime.UtcNow;
            }
        }

        /// <summary>Nothing was started, and nothing will be.</summary>
        public void Refuse(BimErrorCode why, string text)
        {
            lock (sync)
            {
                // The first refusal stands; a later, more general one does not replace it.
                if (status != BimTransactionStatus.NotStarted || cause != BimErrorCode.None)
                {
                    return;
                }

                commitProhibited = true;
                cause = why;
                message = text;
                updatedUtc = DateTime.UtcNow;
            }
        }

        /// <summary>The host started the transaction.</summary>
        public void MarkOpen()
        {
            lock (sync)
            {
                if (status == BimTransactionStatus.NotStarted)
                {
                    status = BimTransactionStatus.Open;
                    updatedUtc = DateTime.UtcNow;
                }
            }
        }

        /// <summary>
        /// The commit can no longer happen (the caller stopped waiting, the
        /// script failed or ran over budget). The transaction may still be
        /// open until the host rolls it back.
        /// </summary>
        public void ProhibitCommit(BimErrorCode why, string text)
        {
            lock (sync)
            {
                if (status == BimTransactionStatus.Committed || commitProhibited)
                {
                    return;
                }

                commitProhibited = true;
                cause = why;
                message = text;
                updatedUtc = DateTime.UtcNow;
            }
        }

        /// <summary>The host observed how the transaction ended.</summary>
        public void Settle(BimTransactionStatus observed)
        {
            lock (sync)
            {
                // A confirmed end state is never overwritten.
                if (status == BimTransactionStatus.Committed || status == BimTransactionStatus.RolledBack)
                {
                    return;
                }

                status = observed;
                if (observed == BimTransactionStatus.Committed)
                {
                    commitProhibited = false;
                    cause = BimErrorCode.None;
                    message = null;
                }

                updatedUtc = DateTime.UtcNow;
            }
        }

        public BimTransactionReceiptSnapshot Snapshot()
        {
            lock (sync)
            {
                return new BimTransactionReceiptSnapshot(
                    Id, Name, status, commitProhibited, cause, message, document, updatedUtc);
            }
        }
    }

    /// <summary>
    /// Receipts of this process's recent write transactions, so a caller that
    /// stopped waiting, or lost the response, can still ask how its edit
    /// ended. In memory only: it does not survive the host process.
    /// </summary>
    public static class BimTransactionReceiptStore
    {
        public const int Capacity = 64;
        private static readonly object Sync = new object();
        private static readonly LinkedList<BimTransactionReceipt> Receipts = new LinkedList<BimTransactionReceipt>();

        public static BimTransactionReceipt Create(string name)
        {
            var receipt = new BimTransactionReceipt(
                "tx-" + Guid.NewGuid().ToString("N").Substring(0, 12),
                name ?? string.Empty);
            lock (Sync)
            {
                Receipts.AddFirst(receipt);
                while (Receipts.Count > Capacity)
                {
                    Receipts.RemoveLast();
                }
            }

            return receipt;
        }

        public static bool TryGet(string? id, out BimTransactionReceipt? receipt)
        {
            lock (Sync)
            {
                receipt = Receipts.FirstOrDefault(
                    item => string.Equals(item.Id, id, StringComparison.Ordinal));
                return receipt != null;
            }
        }

        /// <summary>Most recent first.</summary>
        public static IReadOnlyList<BimTransactionReceiptSnapshot> Recent(int count)
        {
            lock (Sync)
            {
                return Receipts.Take(Math.Max(0, count)).Select(item => item.Snapshot()).ToList();
            }
        }

        internal static void ResetForTests()
        {
            lock (Sync)
            {
                Receipts.Clear();
            }
        }
    }
}
