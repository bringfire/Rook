using System;

namespace Rook.Bim
{
    /// <summary>
    /// One run-transaction call: the receipt that records what happened to
    /// it, and the gate that decides whether it may still commit. Created by
    /// the request thread before any work is queued, so every way the call
    /// can end has a receipt to report from.
    /// </summary>
    public sealed class BimTransactionCall
    {
        public BimTransactionCall(BimTransactionReceipt receipt, BimTransactionCommitGate gate)
        {
            Receipt = receipt ?? throw new ArgumentNullException(nameof(receipt));
            Gate = gate ?? throw new ArgumentNullException(nameof(gate));
        }

        public BimTransactionReceipt Receipt { get; }

        public BimTransactionCommitGate Gate { get; }

        public static BimTransactionCall Begin(string name, TimeSpan scriptTimeout)
        {
            return new BimTransactionCall(
                BimTransactionReceiptStore.Create(name),
                new BimTransactionCommitGate(scriptTimeout));
        }
    }
}
