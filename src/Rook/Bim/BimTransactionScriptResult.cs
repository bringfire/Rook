using System;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Bim
{
    /// <summary>
    /// How one script run ended, built from two independent observations:
    /// what the host saw (its own call into the script engine returned, or
    /// threw), and what the script wrapper reported through the host channel
    /// (it reached its end, or caught an exception).
    ///
    /// A run counts as successful only when both agree. Host-neutral, so the
    /// decision "may this be committed?" is unit-tested without Revit.
    /// </summary>
    public sealed class BimTransactionScriptResult
    {
        public const int MaxStreamLength = 20000;

        // Bounded so a committed response always fits the 1 MiB native bridge
        // buffer, even when every character is escaped to six bytes.
        public const int MaxResultJsonLength = 50000;

        public const int MaxTracebackLength = 20000;

        public const int MaxErrorLength = 2000;

        // Well below the JSON reader's own nesting limit, with room for the
        // envelopes the result is wrapped in on the way out.
        public const int MaxResultDepth = 32;

        private BimTransactionScriptResult()
        {
        }

        /// <summary>True only when the host saw the engine return AND the wrapper reported completion.</summary>
        public bool Success { get; private set; }

        /// <summary>The host's own call into the script engine returned without throwing.</summary>
        public bool HostObservedReturn { get; private set; }

        /// <summary>The script itself raised (as opposed to never running, or the engine failing).</summary>
        public bool ScriptRaised { get; private set; }

        /// <summary>Last stage the wrapper reported: none, bind, compile, run, result, done.</summary>
        public string Stage { get; private set; } = "none";

        public string Output { get; private set; } = string.Empty;

        public bool OutputTruncated { get; private set; }

        public string Stderr { get; private set; } = string.Empty;

        public bool StderrTruncated { get; private set; }

        public string Error { get; private set; } = string.Empty;

        public string Traceback { get; private set; } = string.Empty;

        /// <summary>The JSON value the script assigned to <c>result</c>, or null.</summary>
        public JsonNode? Result { get; private set; }

        /// <summary>Why <see cref="Result"/> is null although the script set one.</summary>
        public string? ResultOmittedReason { get; private set; }

        /// <summary>The script was never invoked (the engine could not be reached, for example).</summary>
        public static BimTransactionScriptResult NotRun(string reason)
        {
            return new BimTransactionScriptResult
            {
                Error = TruncateTail(reason, MaxErrorLength)
            };
        }

        public static BimTransactionScriptResult FromHostRun(
            bool hostObservedReturn,
            string? hostError,
            bool scriptReportedCompletion,
            string? stage,
            string? scriptError,
            string? scriptTraceback,
            string? output,
            bool outputTruncated,
            string? stderr,
            bool stderrTruncated,
            string? resultJson,
            string? resultOmittedReason)
        {
            var result = new BimTransactionScriptResult
            {
                HostObservedReturn = hostObservedReturn,
                Stage = string.IsNullOrWhiteSpace(stage) ? "none" : stage!,
                ScriptRaised = !string.IsNullOrWhiteSpace(scriptError),
                ResultOmittedReason = resultOmittedReason
            };

            result.Output = Truncate(output, out var cutOutput);
            result.OutputTruncated = cutOutput || outputTruncated;
            result.Stderr = Truncate(stderr, out var cutStderr);
            result.StderrTruncated = cutStderr || stderrTruncated;

            result.Success = hostObservedReturn && scriptReportedCompletion && !result.ScriptRaised;
            if (!result.Success)
            {
                if (result.ScriptRaised)
                {
                    result.Error = TruncateTail(scriptError, MaxErrorLength);
                    result.Traceback = TruncateTail(
                        string.IsNullOrWhiteSpace(scriptTraceback) ? hostError : scriptTraceback,
                        MaxTracebackLength);
                }
                else if (!hostObservedReturn)
                {
                    result.Error = TruncateTail(
                        string.IsNullOrWhiteSpace(hostError)
                            ? "The script engine failed without a message."
                            : hostError,
                        MaxErrorLength);
                    result.Traceback = TruncateTail(hostError, MaxTracebackLength);
                }
                else
                {
                    result.Error =
                        $"The script engine returned, but the script did not reach its end (stage '{result.Stage}').";
                }

                return result;
            }

            result.ReadResult(resultJson);
            return result;
        }

        /// <summary>
        /// The return value is optional detail: whatever is wrong with it, the
        /// script still succeeded. It is omitted with a reason, never a failure.
        /// </summary>
        private void ReadResult(string? resultJson)
        {
            if (string.IsNullOrWhiteSpace(resultJson))
            {
                return;
            }

            if (resultJson!.Length > MaxResultJsonLength)
            {
                ResultOmittedReason =
                    $"result was {resultJson.Length} characters of JSON; the limit is {MaxResultJsonLength}. " +
                    "Return a smaller value (for example ids and counts).";
                return;
            }

            try
            {
                Result = JsonNode.Parse(
                    resultJson,
                    documentOptions: new JsonDocumentOptions { MaxDepth = MaxResultDepth });
            }
            catch (JsonException ex)
            {
                ResultOmittedReason =
                    "result could not be read back as JSON (" + ex.Message + "). Return a flatter, plain value: " +
                    $"numbers, strings, lists and dicts nested at most {MaxResultDepth} deep.";
            }
        }

        /// <summary>Keeps the end of a long text: the end of a traceback names the error.</summary>
        private static string TruncateTail(string? value, int limit)
        {
            if (string.IsNullOrEmpty(value))
            {
                return string.Empty;
            }

            return value!.Length <= limit
                ? value
                : "[...truncated...] " + value.Substring(value.Length - limit);
        }

        private static string Truncate(string? value, out bool truncated)
        {
            truncated = false;
            if (string.IsNullOrEmpty(value))
            {
                return string.Empty;
            }

            if (value!.Length <= MaxStreamLength)
            {
                return value;
            }

            truncated = true;
            return value.Substring(0, MaxStreamLength);
        }
    }
}
