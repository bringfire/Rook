using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionOptionsResult(
    bool Success,
    JsonObject Options,
    ReconstructionFailure? Failure);

/// <summary>
/// Validates and normalizes a submit-options object against a model's catalog option descriptors:
/// rejects unknown keys, range/enum-checks present values, fills defaults for absent options, and
/// omits options whose <c>ignored_when</c> condition is satisfied. Only applies to models that
/// declare an <c>options</c> block; callers keep verbatim pass-through for models without one.
/// </summary>
public static class ReconstructionOptionsValidator
{
    public static ReconstructionOptionsResult Validate(JsonObject submitted, ReconstructionModelEntry model)
    {
        var descriptors = model.Options ?? Array.Empty<ReconstructionOptionDescriptor>();
        var byKey = descriptors.ToDictionary(d => d.Key, StringComparer.Ordinal);

        // Reject unknown keys.
        foreach (var kvp in submitted)
        {
            if (!byKey.ContainsKey(kvp.Key))
                return Fail($"Unknown option '{kvp.Key}'.", "options", "unknown_option");
        }

        // Validate present values.
        foreach (var d in descriptors)
        {
            if (!submitted.TryGetPropertyValue(d.Key, out var node) || node is null)
                continue;
            var error = ValidateValue(d, node);
            if (error is not null)
                return Fail(error, $"options.{d.Key}", "invalid_option_value");
        }

        // Build the effective (default-filled) set first so ignored_when sees final values.
        var effective = new JsonObject();
        foreach (var d in descriptors)
        {
            var value = submitted.TryGetPropertyValue(d.Key, out var node) && node is not null
                ? node.DeepClone()
                : d.Default?.DeepClone();
            if (value is not null)
                effective[d.Key] = value;
        }

        // Omit ignored options (type-aware gate: string e.g. generate_type=="Geometry", or bool e.g.
        // should_texture==false).
        foreach (var d in descriptors)
        {
            if (d.IgnoredWhen is null) continue;
            if (effective.TryGetPropertyValue(d.IgnoredWhen.Key, out var gate)
                && gate is JsonValue gv
                && JsonValueEquals(gv, d.IgnoredWhen.EqualsValue))
            {
                effective.Remove(d.Key);
            }
        }

        return new ReconstructionOptionsResult(true, effective, null);
    }

    private static string? ValidateValue(ReconstructionOptionDescriptor d, JsonNode node)
    {
        switch (d.Kind)
        {
            case "enum":
                if (node is not JsonValue ev || !ev.TryGetValue<string>(out var s))
                    return $"'{d.Key}' must be a string.";
                if (d.AllowedValues is not null && !d.AllowedValues.Contains(s, StringComparer.Ordinal))
                    return $"'{d.Key}' must be one of: {string.Join(", ", d.AllowedValues)}.";
                return null;
            case "boolean":
                if (node is not JsonValue bv || !bv.TryGetValue<bool>(out _))
                    return $"'{d.Key}' must be a boolean.";
                return null;
            case "integer":
                if (node is not JsonValue iv || !TryGetLong(iv, out var i))
                    return $"'{d.Key}' must be an integer.";
                if (d.Min is not null && i < d.Min) return $"'{d.Key}' must be >= {d.Min}.";
                if (d.Max is not null && i > d.Max) return $"'{d.Key}' must be <= {d.Max}.";
                return null;
            case "string":
                if (node is not JsonValue sv || !sv.TryGetValue<string>(out _))
                    return $"'{d.Key}' must be a string.";
                return null;
            default:
                return $"'{d.Key}' has an unsupported option kind '{d.Kind}'.";
        }
    }

    // A JsonValue can be JSON-element-backed (parser path) or CLR-backed (int from a test/literal).
    // Try long first, then int, so both representations validate identically.
    private static bool TryGetLong(JsonValue value, out long result)
    {
        if (value.TryGetValue<long>(out result)) return true;
        if (value.TryGetValue<int>(out var i)) { result = i; return true; }
        result = 0;
        return false;
    }

    // Type-aware equality for an ignored_when gate: matches a string gate (generate_type=="Geometry")
    // or a boolean gate (should_texture==false). Any other JSON kind never matches.
    private static bool JsonValueEquals(JsonValue gate, JsonNode? expected)
    {
        if (expected is not JsonValue ev) return false;
        if (gate.TryGetValue<string>(out var gs) && ev.TryGetValue<string>(out var es))
            return string.Equals(gs, es, StringComparison.Ordinal);
        if (gate.TryGetValue<bool>(out var gb) && ev.TryGetValue<bool>(out var eb))
            return gb == eb;
        return false;
    }

    private static ReconstructionOptionsResult Fail(string message, string field, string reason)
        => new(false, new JsonObject(),
            new ReconstructionFailure("invalid_request", message, false, field,
                new Dictionary<string, object?> { ["reason"] = reason }));
}
