using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace Rook.Handlers
{
    internal static class GhParameterContract
    {
        internal static bool IsStandaloneParameter(object candidate)
        {
            var type = candidate.GetType();
            if (type.GetProperty("Params") != null)
                return false;

            return type.GetProperty("Sources") != null &&
                   type.GetProperty("Recipients") != null;
        }

        internal static bool TryGetParameters(
            object component,
            bool isInput,
            out IReadOnlyList<object> parameters)
        {
            parameters = Array.Empty<object>();
            var paramsProperty = component.GetType().GetProperty("Params");
            if (paramsProperty == null)
            {
                if (!IsStandaloneParameter(component))
                    return false;

                parameters = new[] { component };
                return true;
            }

            var parameterServer = paramsProperty.GetValue(component);
            var listProperty = parameterServer?.GetType().GetProperty(isInput ? "Input" : "Output");
            var values = listProperty?.GetValue(parameterServer) as IEnumerable;
            if (values == null)
                return false;

            parameters = values.Cast<object>().ToList();
            return true;
        }
    }

    internal readonly struct GhConnectionSelector
    {
        internal GhConnectionSelector(int? index, string? name)
        {
            Index = index;
            Name = name;
        }

        internal int? Index { get; }
        internal string? Name { get; }
        internal bool IsSpecified => Index.HasValue || Name != null;
    }

    internal sealed class GhConnectionRequest
    {
        internal GhConnectionRequest(
            string sourceGuid,
            GhConnectionSelector sourceSelector,
            string targetGuid,
            GhConnectionSelector targetSelector)
        {
            SourceGuid = sourceGuid;
            SourceSelector = sourceSelector;
            TargetGuid = targetGuid;
            TargetSelector = targetSelector;
        }

        internal string SourceGuid { get; }
        internal GhConnectionSelector SourceSelector { get; }
        internal string TargetGuid { get; }
        internal GhConnectionSelector TargetSelector { get; }
    }

    internal readonly struct GhResolvedConnectionParameter
    {
        internal GhResolvedConnectionParameter(object value, int index, string? name)
        {
            Value = value;
            Index = index;
            Name = name;
        }

        internal object? Value { get; }
        internal int Index { get; }
        internal string? Name { get; }
    }

    /// <summary>
    /// Parses and resolves the narrow selector contract shared by /gh/connect and
    /// /gh/disconnect. This class intentionally has no Grasshopper assembly reference.
    /// </summary>
    internal static class GhConnectionSelectorResolver
    {
        internal static bool TryParseRequest(
            string body,
            out GhConnectionRequest? request,
            out string? error)
        {
            request = null;
            error = null;

            Dictionary<string, JsonElement>? args;
            try
            {
                args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            }
            catch
            {
                error = "Invalid JSON body";
                return false;
            }

            if (args == null ||
                !TryReadRequiredString(args, "sourceGuid", out var sourceGuid) ||
                !TryReadRequiredString(args, "targetGuid", out var targetGuid))
            {
                error = "sourceGuid and targetGuid are required";
                return false;
            }

            if (!TryParseSelector(args, "sourceParam", "sourceIndex", out var sourceSelector, out error) ||
                !TryParseSelector(args, "targetParam", "targetIndex", out var targetSelector, out error))
            {
                return false;
            }

            request = new GhConnectionRequest(
                sourceGuid!,
                sourceSelector,
                targetGuid!,
                targetSelector);
            return true;
        }

        internal static bool TryResolve(
            object component,
            bool isInput,
            GhConnectionSelector selector,
            out GhResolvedConnectionParameter resolved,
            out string? error)
        {
            resolved = default;
            error = null;

            var side = isInput ? "Target input" : "Source output";
            var singular = isInput ? "input" : "output";
            var plural = isInput ? "inputs" : "outputs";

            try
            {
                if (!GhParameterContract.TryGetParameters(component, isInput, out var parameterList))
                {
                    error = $"{side} parameter not found";
                    return false;
                }

                if (selector.Index.HasValue)
                {
                    var index = selector.Index.Value;
                    if (index < 0 || index >= parameterList.Count)
                    {
                        var countLabel = parameterList.Count == 1 ? singular : plural;
                        error = $"{side} index {index} is out of range for {parameterList.Count} {countLabel}";
                        return false;
                    }

                    resolved = BuildResolved(parameterList[index], index);
                    return true;
                }

                if (selector.Name != null)
                {
                    for (var index = 0; index < parameterList.Count; index++)
                    {
                        var parameter = parameterList[index];
                        if (MatchesName(parameter, selector.Name))
                        {
                            resolved = BuildResolved(parameter, index);
                            return true;
                        }
                    }

                    error = $"{side} parameter not found: {selector.Name}";
                    return false;
                }

                if (parameterList.Count == 1)
                {
                    resolved = BuildResolved(parameterList[0], 0);
                    return true;
                }

                error = parameterList.Count == 0
                    ? $"{side} parameter not found"
                    : $"{side} selector is required because the component has {parameterList.Count} {plural}";
                return false;
            }
            catch
            {
                error = $"{side} parameter resolution failed";
                return false;
            }
        }

        private static bool TryReadRequiredString(
            IReadOnlyDictionary<string, JsonElement> args,
            string key,
            out string? value)
        {
            value = null;
            if (!args.TryGetValue(key, out var element) || element.ValueKind != JsonValueKind.String)
                return false;

            value = element.GetString();
            return !string.IsNullOrWhiteSpace(value);
        }

        private static bool TryParseSelector(
            IReadOnlyDictionary<string, JsonElement> args,
            string parameterKey,
            string indexKey,
            out GhConnectionSelector selector,
            out string? error)
        {
            selector = default;
            error = null;

            var hasParameter = args.TryGetValue(parameterKey, out var parameterElement);
            var hasIndex = args.TryGetValue(indexKey, out var indexElement);
            if (hasParameter && hasIndex)
            {
                error = $"Specify only one of {parameterKey} and {indexKey}";
                return false;
            }

            if (hasIndex)
            {
                if (!TryReadNonNegativeInteger(indexElement, out var index))
                {
                    error = $"{indexKey} must be a non-negative integer";
                    return false;
                }

                selector = new GhConnectionSelector(index, null);
                return true;
            }

            if (!hasParameter)
                return true;

            if (parameterElement.ValueKind == JsonValueKind.Number)
            {
                if (!TryReadNonNegativeInteger(parameterElement, out var legacyIndex))
                {
                    error = $"{parameterKey} must be a non-empty name or non-negative integer";
                    return false;
                }

                selector = new GhConnectionSelector(legacyIndex, null);
                return true;
            }

            if (parameterElement.ValueKind == JsonValueKind.String)
            {
                var name = parameterElement.GetString();
                if (!string.IsNullOrWhiteSpace(name))
                {
                    selector = new GhConnectionSelector(null, name);
                    return true;
                }
            }

            error = $"{parameterKey} must be a non-empty name or non-negative integer";
            return false;
        }

        private static bool TryReadNonNegativeInteger(JsonElement element, out int value)
        {
            value = default;
            return element.ValueKind == JsonValueKind.Number &&
                   element.TryGetInt32(out value) &&
                   value >= 0;
        }

        private static GhResolvedConnectionParameter BuildResolved(object parameter, int index)
        {
            return new GhResolvedConnectionParameter(parameter, index, ReadCanonicalName(parameter));
        }

        private static bool MatchesName(object parameter, string requestedName)
        {
            var type = parameter.GetType();
            var name = type.GetProperty("Name")?.GetValue(parameter)?.ToString();
            var nickName = type.GetProperty("NickName")?.GetValue(parameter)?.ToString();
            return string.Equals(name, requestedName, StringComparison.OrdinalIgnoreCase) ||
                   string.Equals(nickName, requestedName, StringComparison.OrdinalIgnoreCase);
        }

        private static string? ReadCanonicalName(object parameter)
        {
            var type = parameter.GetType();
            var name = type.GetProperty("Name")?.GetValue(parameter)?.ToString();
            if (!string.IsNullOrWhiteSpace(name))
                return name;

            var nickName = type.GetProperty("NickName")?.GetValue(parameter)?.ToString();
            return string.IsNullOrWhiteSpace(nickName) ? null : nickName;
        }
    }
}
