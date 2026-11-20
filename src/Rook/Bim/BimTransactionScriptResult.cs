using System;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Bim
{
    /// <summary>
    /// The payload the run-transaction Python wrapper writes after it ran the
    /// caller's script. Host-neutral: parsing it needs no Revit types, so the
    /// decision "commit or roll back" is testable without Revit.
    /// </summary>
    public sealed class BimTransactionScriptResult
    {
        public const int MaxStreamLength = 20000;

        public const int MaxResultJsonLength = 100000;

        private BimTransactionScriptResult()
        {
        }

        /// <summary>True only when the wrapper reported that the script ran to its end.</summary>
        public bool Success { get; private set; }

        /// <summary>False when no usable payload was produced at all.</summary>
        public bool PayloadPresent { get; private set; }

        /// <summary>Wrapper stage reached: bind, read, compile, run, result, done.</summary>
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

        public static BimTransactionScriptResult Missing(string reason)
        {
            return new BimTransactionScriptResult
            {
                Success = false,
                PayloadPresent = false,
                Error = reason
            };
        }

        public static BimTransactionScriptResult Parse(string? json)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return Missing("The script wrapper wrote an empty result payload.");
            }

            JsonNode? root;
            try
            {
                root = JsonNode.Parse(json!);
            }
            catch (JsonException ex)
            {
                return Missing("The script wrapper wrote an unreadable result payload: " + ex.Message);
            }

            if (!(root is JsonObject payload))
            {
                return Missing("The script wrapper result payload was not a JSON object.");
            }

            var result = new BimTransactionScriptResult
            {
                PayloadPresent = true,
                Stage = ReadString(payload, "stage") ?? "none",
                Error = ReadString(payload, "error") ?? string.Empty,
                Traceback = ReadString(payload, "traceback") ?? string.Empty,
                ResultOmittedReason = ReadString(payload, "resultOmittedReason")
            };

            result.Output = Truncate(ReadString(payload, "output"), out var outputTruncated);
            result.OutputTruncated = outputTruncated;
            result.Stderr = Truncate(ReadString(payload, "stderr"), out var stderrTruncated);
            result.StderrTruncated = stderrTruncated;

            // Success must be the literal JSON true; anything else rolls back.
            result.Success =
                payload.TryGetPropertyValue("success", out var success) &&
                success is JsonValue successValue &&
                successValue.TryGetValue<bool>(out var succeeded) &&
                succeeded;
            if (!result.Success && result.Error.Length == 0)
            {
                result.Error = "The script wrapper did not report success.";
            }

            if (payload.TryGetPropertyValue("result", out var value) && value != null)
            {
                var text = value.ToJsonString();
                if (text.Length > MaxResultJsonLength)
                {
                    result.ResultOmittedReason =
                        $"result was {text.Length} characters of JSON; the limit is {MaxResultJsonLength}. " +
                        "Return a smaller value (for example ids and counts).";
                }
                else
                {
                    // Re-parse so the node has no parent and can be attached to a response.
                    result.Result = JsonNode.Parse(text);
                }
            }

            return result;
        }

        private static string? ReadString(JsonObject payload, string name)
        {
            if (!payload.TryGetPropertyValue(name, out var node) || !(node is JsonValue value))
            {
                return null;
            }

            return value.TryGetValue<string>(out var text) ? text : null;
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
