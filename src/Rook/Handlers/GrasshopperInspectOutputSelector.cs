using System;
using System.Collections;
using System.Collections.Generic;
using System.Text.Json;

namespace Rook.Handlers
{
    internal readonly struct GhInspectOutputSelector
    {
        internal GhInspectOutputSelector(string? param, int? outputIndex)
        {
            Param = param;
            OutputIndex = outputIndex;
        }

        internal string? Param { get; }
        internal int? OutputIndex { get; }
    }

    internal sealed class GhInspectOutputSelectorError
    {
        internal GhInspectOutputSelectorError(string field, string message)
        {
            Field = field;
            Message = message;
        }

        internal string Field { get; }
        internal string Message { get; }

        internal ApiResponse ToApiResponse() => new()
        {
            Success = false,
            HttpStatus = 400,
            Data = new
            {
                code = "invalid_request",
                field = Field,
                message = Message,
            },
        };
    }

    internal readonly struct GhResolvedInspectOutput
    {
        internal GhResolvedInspectOutput(object value, int index)
        {
            Value = value;
            Index = index;
        }

        internal object? Value { get; }
        internal int Index { get; }
    }

    /// <summary>
    /// Parses and resolves the selector contract for gh_inspect_output only.
    /// This helper intentionally has no Grasshopper assembly reference.
    /// </summary>
    internal static class GhInspectOutputSelectorResolver
    {
        internal static bool TryParse(
            IReadOnlyDictionary<string, JsonElement>? args,
            out GhInspectOutputSelector selector,
            out GhInspectOutputSelectorError? error)
        {
            selector = default;
            error = null;

            var paramElement = default(JsonElement);
            var indexElement = default(JsonElement);
            var hasParam = args != null && args.TryGetValue("param", out paramElement);
            var hasOutputIndex = args != null && args.TryGetValue("outputIndex", out indexElement);
            if (hasParam && hasOutputIndex)
            {
                error = new GhInspectOutputSelectorError(
                    "selector",
                    "Specify only one of param and outputIndex");
                return false;
            }

            if (hasParam)
            {
                if (paramElement.ValueKind != JsonValueKind.String)
                {
                    error = InvalidParam();
                    return false;
                }

                selector = new GhInspectOutputSelector(paramElement.GetString(), outputIndex: null);
                return TryValidate(selector, out error);
            }

            if (!hasOutputIndex)
                return true;

            if (!TryReadNonNegativeInteger(indexElement, out var outputIndex))
            {
                error = InvalidOutputIndex();
                return false;
            }

            selector = new GhInspectOutputSelector(param: null, outputIndex);
            return true;
        }

        internal static bool TryValidate(
            GhInspectOutputSelector selector,
            out GhInspectOutputSelectorError? error)
        {
            error = null;
            if (selector.Param != null && selector.OutputIndex.HasValue)
            {
                error = new GhInspectOutputSelectorError(
                    "selector",
                    "Specify only one of param and outputIndex");
                return false;
            }

            if (selector.Param != null && string.IsNullOrWhiteSpace(selector.Param))
            {
                error = InvalidParam();
                return false;
            }

            if (selector.OutputIndex is < 0)
            {
                error = InvalidOutputIndex();
                return false;
            }

            return true;
        }

        internal static bool TryResolve(
            IList outputs,
            GhInspectOutputSelector selector,
            out GhResolvedInspectOutput resolved,
            out GhInspectOutputSelectorError? error)
        {
            resolved = default;
            if (!TryValidate(selector, out error))
                return false;

            if (selector.OutputIndex.HasValue)
                return TryResolveIndex(outputs, selector.OutputIndex.Value, "outputIndex", out resolved, out error);

            if (selector.Param != null)
            {
                if (int.TryParse(selector.Param, out var numericIndex))
                    return TryResolveIndex(outputs, numericIndex, "param", out resolved, out error);

                for (var index = 0; index < outputs.Count; index++)
                {
                    var output = outputs[index];
                    if (MatchesName(output, selector.Param))
                    {
                        resolved = BuildResolved(output, index);
                        return true;
                    }
                }

                error = new GhInspectOutputSelectorError(
                    "param",
                    "Output parameter name was not found");
                return false;
            }

            resolved = BuildResolved(outputs[0]!, 0);
            return true;
        }

        private static bool TryReadNonNegativeInteger(JsonElement element, out int value)
        {
            value = default;
            if (element.ValueKind == JsonValueKind.Number)
                return element.TryGetInt32(out value) && value >= 0;

            return element.ValueKind == JsonValueKind.String &&
                   int.TryParse(element.GetString(), out value) &&
                   value >= 0;
        }

        private static bool TryResolveIndex(
            IList outputs,
            int index,
            string field,
            out GhResolvedInspectOutput resolved,
            out GhInspectOutputSelectorError? error)
        {
            resolved = default;
            error = null;
            if (index < 0 || index >= outputs.Count)
            {
                error = new GhInspectOutputSelectorError(
                    field,
                    $"Output index {index} is out of range for {outputs.Count} outputs");
                return false;
            }

            resolved = BuildResolved(outputs[index]!, index);
            return true;
        }

        private static bool MatchesName(object? output, string param)
        {
            if (output == null)
                return false;

            var type = output.GetType();
            var name = type.GetProperty("Name")?.GetValue(output)?.ToString();
            var nickName = type.GetProperty("NickName")?.GetValue(output)?.ToString();
            return name == param || nickName == param;
        }

        private static GhResolvedInspectOutput BuildResolved(object output, int index)
        {
            return new GhResolvedInspectOutput(output, index);
        }

        private static GhInspectOutputSelectorError InvalidParam() => new(
            "param",
            "param must be a non-empty string");

        private static GhInspectOutputSelectorError InvalidOutputIndex() => new(
            "outputIndex",
            "outputIndex must be a non-negative integer");
    }
}
