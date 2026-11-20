using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Rook.Bim
{
    /// <summary>
    /// The one place that turns a transaction receipt into what a caller is
    /// told: the wire code, the HTTP status, the sentence about the document,
    /// and the next step. The executor, a request thread that stopped waiting
    /// and a later lookup all go through here, so the same receipt always
    /// reads the same way, and a cause ("the script raised") can never be
    /// reported with a document state the host did not confirm.
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

        public static string WireStatus(BimTransactionStatus status)
        {
            switch (status)
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
        /// The code a caller gets. A cause is reported under its own code only
        /// when the host confirmed that nothing was committed; otherwise the
        /// answer is "outcome unknown", whatever the cause was.
        /// </summary>
        public static BimErrorCode EffectiveCode(BimTransactionReceiptSnapshot receipt)
        {
            if (receipt == null)
            {
                throw new ArgumentNullException(nameof(receipt));
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

        /// <summary>true = changed, false = confirmed unchanged, null = not confirmed either way.</summary>
        public static bool? DocumentChanged(BimTransactionReceiptSnapshot receipt, bool? committedChange)
        {
            switch (receipt.Status)
            {
                case BimTransactionStatus.NotStarted:
                case BimTransactionStatus.RolledBack:
                    return false;
                case BimTransactionStatus.Committed:
                    return committedChange ?? true;
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

        public static string Message(BimTransactionReceiptSnapshot receipt)
        {
            var code = EffectiveCode(receipt);
            var cause = string.IsNullOrWhiteSpace(receipt.Message) ? string.Empty : receipt.Message!.Trim() + " ";
            var lookup = $"Call rookbim_transaction_receipt with transactionId '{receipt.Id}' to see how it ended.";
            switch (receipt.Status)
            {
                case BimTransactionStatus.Committed:
                    return $"Transaction '{receipt.Name}' was committed.";
                case BimTransactionStatus.NotStarted:
                    return cause + "No transaction was started; the Revit document is unchanged." + NextStep(code);
                case BimTransactionStatus.RolledBack:
                    return cause + $"Transaction '{receipt.Name}' was rolled back; the Revit document is unchanged." +
                        NextStep(code);
                case BimTransactionStatus.Open:
                    if (receipt.CommitProhibited)
                    {
                        return cause + $"Transaction '{receipt.Name}' is still open on Revit's API thread. It will not be " +
                            "committed: Revit rolls it back when the script returns, and until then Revit does not " +
                            "respond. Rook cannot stop a running script. " + lookup;
                    }

                    return cause + $"Revit had not finished transaction '{receipt.Name}' when the wait ended, so whether " +
                        "it was committed is not known yet. Do not run the script again. " + lookup;
                default:
                    return cause + $"Revit did not confirm how transaction '{receipt.Name}' ended. Do not run the script " +
                        "again. " + lookup + " If it stays unresolved, read the model back (rookbim_query_elements or " +
                        "rookbim_element_parameters) in the same document before any further write.";
            }
        }

        /// <summary>Builds the response for a receipt, with optional details that can never displace it.</summary>
        public static BimApiResponse Build(
            BimTransactionReceiptSnapshot receipt,
            IDictionary<string, object?>? details = null,
            bool? committedChange = null)
        {
            var code = EffectiveCode(receipt);
            var data = new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                ["transaction"] = new Dictionary<string, object?>(StringComparer.Ordinal)
                {
                    ["id"] = receipt.Id,
                    ["name"] = receipt.Name,
                    ["status"] = WireStatus(receipt.Status),
                    ["commitProhibited"] = receipt.CommitProhibited,
                },
                ["documentChanged"] = DocumentChanged(receipt, committedChange),
                ["document"] = receipt.Document,
            };

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

        private static string NextStep(BimErrorCode code)
        {
            switch (code)
            {
                case BimErrorCode.TransactionScriptFailed:
                    return " Fix the script (see details.traceback) and call again.";
                case BimErrorCode.TransactionRolledBack:
                    return " Change the script so the model stays valid (see details.failures), then call again.";
                case BimErrorCode.TransactionTimeout:
                    return " Retry with a faster script or a larger timeoutSeconds.";
                default:
                    return string.Empty;
            }
        }
    }
}
