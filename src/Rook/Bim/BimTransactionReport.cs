using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Rook.Bim
{
    /// <summary>
    /// The one place that turns a transaction receipt into what a caller is
    /// told: the wire status and code, the HTTP status, the sentence about
    /// the document, and the next step. The executor, a request thread that
    /// stopped waiting and a later lookup all go through here, so the same
    /// receipt always reads the same way, and a cause ("the script raised")
    /// can never be reported with a document state the host did not confirm.
    /// </summary>
    public static class BimTransactionReport
    {
        /// <summary>
        /// Budget for the serialized data. The native bridge buffer is 1 MiB
        /// and replaces an oversize response with an unrelated error; staying
        /// well under it keeps a committed receipt deliverable.
        /// </summary>
        public const int MaxDataBytes = 600000;

        private static readonly string[] OptionalFieldsInDropOrder =
        {
            "elements",
            "result",
            "output",
            "stderr",
            "traceback",
            "warnings",
            "failures",
        };

        private static readonly JsonSerializerOptions MeasureOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        };

        /// <summary>
        /// queued, open, committed, rolled_back, not_started, unresolved.
        /// "queued" is a write the host has not picked up yet: it has not
        /// failed, and it is not the same as "not_started", which is final.
        /// </summary>
        public static string WireStatus(BimTransactionReceiptSnapshot receipt)
        {
            if (receipt == null)
            {
                throw new ArgumentNullException(nameof(receipt));
            }

            if (receipt.IsQueued)
            {
                return "queued";
            }

            switch (receipt.Status)
            {
                case BimTransactionStatus.NotStarted:
                    return "not_started";
                case BimTransactionStatus.Open:
                    return "open";
                case BimTransactionStatus.Committed:
                    return "committed";
                case BimTransactionStatus.RolledBack:
                    return "rolled_back";
                default:
                    return "unresolved";
            }
        }

        /// <summary>
        /// True while the transaction may still commit and nothing has gone
        /// wrong: waiting in the queue, or open with the commit still permitted.
        /// </summary>
        public static bool IsInProgress(BimTransactionReceiptSnapshot receipt)
        {
            return receipt.IsQueued ||
                (receipt.Status == BimTransactionStatus.Open && !receipt.CommitProhibited && !receipt.ObservationEnded);
        }

        /// <summary>
        /// The code the write call itself returns. A cause is reported under
        /// its own code only when the host confirmed that nothing was
        /// committed, or that nothing can be; otherwise the answer is
        /// "outcome unknown", whatever the cause was.
        /// </summary>
        public static BimErrorCode EffectiveCode(BimTransactionReceiptSnapshot receipt)
        {
            if (receipt == null)
            {
                throw new ArgumentNullException(nameof(receipt));
            }

            if (receipt.IsQueued)
            {
                return BimErrorCode.TransactionOutcomeUnknown;
            }

            switch (receipt.Status)
            {
                case BimTransactionStatus.Committed:
                    return BimErrorCode.None;
                case BimTransactionStatus.NotStarted:
                case BimTransactionStatus.RolledBack:
                    return receipt.Cause == BimErrorCode.None ? BimErrorCode.InternalError : receipt.Cause;
                case BimTransactionStatus.Open:
                    if (!receipt.CommitProhibited)
                    {
                        return BimErrorCode.TransactionOutcomeUnknown;
                    }

                    return receipt.Cause == BimErrorCode.None ? BimErrorCode.TransactionTimeout : receipt.Cause;
                default:
                    return BimErrorCode.TransactionOutcomeUnknown;
            }
        }

        /// <summary>
        /// The code a lookup shows. A transaction that is simply still in
        /// progress has no error: the write call that stopped waiting for it
        /// had to say "unknown", but someone asking later is told "not yet".
        /// </summary>
        public static BimErrorCode LookupCode(BimTransactionReceiptSnapshot receipt)
        {
            return IsInProgress(receipt) ? BimErrorCode.None : EffectiveCode(receipt);
        }

        /// <summary>true = changed, false = confirmed unchanged, null = not confirmed either way.</summary>
        public static bool? DocumentChanged(BimTransactionReceiptSnapshot receipt)
        {
            if (receipt.IsQueued)
            {
                // It may still run.
                return null;
            }

            switch (receipt.Status)
            {
                case BimTransactionStatus.NotStarted:
                case BimTransactionStatus.RolledBack:
                    return false;
                case BimTransactionStatus.Committed:
                    // What the host saw at the commit; null if it saw nothing either way.
                    return receipt.ChangeObserved;
                default:
                    return null;
            }
        }

        public static int HttpStatus(BimErrorCode code)
        {
            switch (code)
            {
                case BimErrorCode.None:
                    return 200;
                case BimErrorCode.InvalidRequest:
                    return 400;
                case BimErrorCode.TransactionScriptFailed:
                    return 422;
                case BimErrorCode.RevitNotIdle:
                case BimErrorCode.RevitOperationTimeout:
                case BimErrorCode.NotRhinoInside:
                case BimErrorCode.RookBimUnavailable:
                    return 503;
                case BimErrorCode.TransactionTimeout:
                    return 504;
                case BimErrorCode.InternalError:
                    return 500;
                default:
                    // document_mismatch, document_not_modifiable, no_active_document,
                    // transaction_rolled_back, transaction_outcome_unknown
                    return 409;
            }
        }

        /// <summary>
        /// The sentence a caller reads. <paramref name="withDetails"/> is true
        /// for the write call's own answer, which carries traceback and
        /// failure details; a lookup has none, so it must not point at them.
        /// </summary>
        public static string Message(BimTransactionReceiptSnapshot receipt, bool withDetails = true)
        {
            var code = EffectiveCode(receipt);
            var cause = string.IsNullOrWhiteSpace(receipt.Message) ? string.Empty : receipt.Message!.Trim() + " ";
            var lookup = $"Call rookbim_transaction_receipt with transactionId '{receipt.Id}' to see how it ended.";
            var readBack =
                "Read the model back (rookbim_query_elements or rookbim_element_parameters) in " +
                DocumentPhrase(receipt) + " before any further write.";

            if (receipt.IsQueued)
            {
                return $"Transaction '{receipt.Name}' is queued: Revit has not picked it up yet. An open dialog or an " +
                    "active command in Revit delays it. It has not failed and it may still run, so do not submit " +
                    "it again. " + lookup;
            }

            switch (receipt.Status)
            {
                case BimTransactionStatus.Committed:
                    return $"Transaction '{receipt.Name}' was committed.";
                case BimTransactionStatus.NotStarted:
                    return cause + "No transaction was started; the Revit document is unchanged." +
                        NextStep(code, withDetails);
                case BimTransactionStatus.RolledBack:
                    return cause + $"Transaction '{receipt.Name}' was rolled back; the Revit document is unchanged." +
                        NextStep(code, withDetails);
                case BimTransactionStatus.Open:
                    if (receipt.CommitProhibited)
                    {
                        return cause + $"Transaction '{receipt.Name}' is still open on Revit's API thread. It will not be " +
                            "committed: Revit rolls it back when the script returns, and until then Revit does not " +
                            "respond. Rook cannot stop a running script. " + lookup;
                    }

                    return cause + $"Revit has not recorded the end of transaction '{receipt.Name}' yet. The script may " +
                        "still be running, or it has returned and Revit is committing or rolling back. Do not run " +
                        "the script again. " + lookup;
                default:
                    if (receipt.ObservationEnded)
                    {
                        return cause + $"Revit did not confirm how transaction '{receipt.Name}' ended, and RookBIM is no " +
                            "longer watching it, so this receipt will not change. Do not run the script again. " +
                            readBack;
                    }

                    return cause + $"Revit has not confirmed how transaction '{receipt.Name}' ended. Do not run the " +
                        "script again. " + lookup + " If it is final and still unresolved: " + readBack;
            }
        }

        /// <summary>
        /// Builds the write call's response for a receipt, with optional
        /// details that can never displace it.
        /// </summary>
        public static BimApiResponse Build(
            BimTransactionReceiptSnapshot receipt,
            IDictionary<string, object?>? details = null)
        {
            var code = EffectiveCode(receipt);
            var data = Describe(receipt);

            if (details != null)
            {
                foreach (var pair in details)
                {
                    if (!data.ContainsKey(pair.Key))
                    {
                        data[pair.Key] = pair.Value;
                    }
                }
            }

            FitToBudget(data, MaxDataBytes);

            if (code == BimErrorCode.None)
            {
                return BimApiResponse.Ok(data);
            }

            var response = BimApiResponse.Fail(code, Message(receipt), HttpStatus(code));
            response.Data = data;
            return response;
        }

        /// <summary>
        /// The receipt fields, identical in the write call's answer and in a
        /// lookup: transaction {id, name, status, commitProhibited}, final,
        /// documentChanged, document.
        /// </summary>
        public static Dictionary<string, object?> Describe(BimTransactionReceiptSnapshot receipt)
        {
            return new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                ["transaction"] = new Dictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["id"] = receipt.Id,
                    ["name"] = receipt.Name,
                    ["status"] = WireStatus(receipt),
                    ["commitProhibited"] = receipt.CommitProhibited,
                },
                ["final"] = receipt.IsFinal,
                ["documentChanged"] = DocumentChanged(receipt),
                ["document"] = receipt.Document,
            };
        }

        /// <summary>
        /// Drops optional fields, largest concern first, until the data
        /// serializes within the budget. Receipt fields are never dropped.
        /// Every dropped field is named with the reason.
        /// </summary>
        internal static void FitToBudget(Dictionary<string, object?> data, int maxBytes)
        {
            var omitted = new List<object>();
            foreach (var field in OptionalFieldsInDropOrder)
            {
                var problem = Measure(data, maxBytes);
                if (problem == null)
                {
                    break;
                }

                if (!data.ContainsKey(field) || data[field] == null)
                {
                    continue;
                }

                data[field] = null;
                omitted.Add(new Dictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["field"] = field,
                    ["reason"] = problem,
                });
            }

            if (omitted.Count > 0)
            {
                data["omitted"] = omitted;
            }
        }

        private static string? Measure(Dictionary<string, object?> data, int maxBytes)
        {
            try
            {
                var size = JsonSerializer.SerializeToUtf8Bytes(data, MeasureOptions).Length;
                return size <= maxBytes
                    ? null
                    : $"The response was {size} bytes; the limit is {maxBytes}. The transaction status above is complete.";
            }
            catch (Exception ex)
            {
                return $"The response could not be serialized ({ex.GetType().Name}: {ex.Message}). " +
                    "The transaction status above is complete.";
            }
        }

        private static string DocumentPhrase(BimTransactionReceiptSnapshot receipt)
        {
            var title = receipt.Document?.Title;
            return string.IsNullOrWhiteSpace(title) ? "the same document" : $"document '{title}'";
        }

        private static string NextStep(BimErrorCode code, bool withDetails)
        {
            switch (code)
            {
                case BimErrorCode.TransactionScriptFailed:
                    return withDetails
                        ? " Fix the script (see details.traceback) and call again."
                        : " Fix the script and call again.";
                case BimErrorCode.TransactionRolledBack:
                    return withDetails
                        ? " Change the script so the model stays valid (see details.failures), then call again."
                        : " Change the script so the model stays valid, then call again.";
                case BimErrorCode.TransactionTimeout:
                    return " Retry with a faster script or a larger timeoutSeconds.";
                default:
                    return string.Empty;
            }
        }
    }
}
