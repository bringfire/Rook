using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalModelNormalizer
    {
        public FalNormalizationResult Normalize(FalOperationBinding binding, FalModelInput input)
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (input == null) throw new ArgumentNullException(nameof(input));
            var errors = new List<FalFieldError>();
            var inactive = new List<string>();
            if (input.OutputCount != 1) errors.Add(new FalFieldError("output_count", "Configured operations produce exactly one output."));
            if (input.OperationId != null && input.OperationId != binding.OperationId)
                errors.Add(new FalFieldError("operation", "The selected operation does not match the resolved binding."));

            var supplied = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            var fields = binding.Fields.ToDictionary(f => f.QualifiedKey, StringComparer.Ordinal);
            ReadSupplied(input.RequestFields, "request", fields, supplied, errors);
            ReadSupplied(input.Options, "options", fields, supplied, errors);
            var values = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            foreach (var field in binding.Fields)
            {
                bool explicitValue = supplied.TryGetValue(field.QualifiedKey, out var value);
                if (!explicitValue && !field.HasDefault) continue;
                if (!explicitValue) value = field.Default;
                var error = ValidateValue(field, value, out var canonical);
                if (error != null) errors.Add(new FalFieldError(field.QualifiedKey, error));
                else values.Add(field.QualifiedKey, canonical);
            }
            var media = ValidateMedia(binding, input, errors);
            // Invalid controls never enter condition evaluation or a partially usable request.
            if (errors.Count != 0) return new FalNormalizationResult(binding, null, errors, inactive);

            var active = binding.Constraints.Select(c => new { Constraint = c, Matches = c.When.All(p => Matches(p, values, input.Media)) }).ToArray();
            foreach (var field in binding.Fields)
            {
                string name = field.QualifiedKey;
                bool present = values.TryGetValue(name, out var value);
                var restrictions = active.Where(a => a.Constraint.Field == name).ToArray();
                bool omitted = restrictions.Any(a => a.Matches && a.Constraint.Kind == "omit_when");
                bool required = field.Required || restrictions.Any(a => a.Matches && a.Constraint.Kind == "required_when");
                if (omitted)
                {
                    inactive.Add(name);
                    if (present && supplied.ContainsKey(name)) errors.Add(new FalFieldError(name, "The supplied value is inapplicable under the selected controls."));
                    if (required) errors.Add(new FalFieldError(name, "The selected controls both require and omit this field."));
                    continue;
                }
                if (required && !present) errors.Add(new FalFieldError(name, "A value is required under the selected controls."));
                if (!present) continue;
                if (restrictions.Any(a => a.Constraint.Kind == "allowed_when" && !a.Matches))
                    errors.Add(new FalFieldError(name, "This field is not allowed under the selected controls."));
                foreach (var restriction in restrictions.Where(a => a.Matches && a.Constraint.Kind == "allowed_values"))
                    if (!restriction.Constraint.Values!.Any(v => SameValue(v, value)))
                        errors.Add(new FalFieldError(name, "The value is outside the intersection of active allowed values."));
            }
            if (errors.Count != 0) return new FalNormalizationResult(binding, null, errors, inactive);

            var requestFields = new JsonObject(); var options = new JsonObject();
            foreach (var field in binding.Fields)
                if (!inactive.Contains(field.QualifiedKey) && values.TryGetValue(field.QualifiedKey, out var value))
                    (field.Scope == "request" ? requestFields : options).Add(field.Key, value?.DeepClone());
            var selectors = new JsonObject();
            foreach (string name in (binding.Pricing?.Rates.SelectMany(r => r.Selectors.Select(s => s.Key)) ?? Enumerable.Empty<string>()).Distinct(StringComparer.Ordinal))
                if (!inactive.Contains(name) && values.TryGetValue(name, out var value)) selectors.Add(name, value?.DeepClone());
            return new FalNormalizationResult(binding, new FalNormalizedRequest(binding, input, requestFields, options, inactive, media, selectors), errors, inactive);
        }

        private static void ReadSupplied(JsonObject input, string scope, Dictionary<string, FalFieldDefinition> fields,
            Dictionary<string, JsonNode?> supplied, List<FalFieldError> errors)
        {
            foreach (var pair in input)
            {
                string name = scope + "." + pair.Key;
                if (!fields.ContainsKey(name)) errors.Add(new FalFieldError(name, "Unknown field for this operation."));
                else supplied.Add(name, pair.Value);
            }
        }

        private static string? ValidateValue(FalFieldDefinition field, JsonNode? value, out JsonNode? canonical)
        {
            canonical = null;
            if (!(value is JsonValue scalar)) return "Expected a non-null scalar JSON value.";
            if (field.QualifiedKey != "request.prompt" && !FalScalarLiteralPolicy.IsAllowed(value))
                return "Scalar controls cannot contain media source locators. Use artifact media roles.";
            var kind = scalar.GetValueKind();
            switch (field.Type)
            {
                case "boolean":
                    if (kind != JsonValueKind.True && kind != JsonValueKind.False) return "Expected a JSON boolean.";
                    break;
                case "integer":
                case "number":
                    if (!FalCanonicalJson.TryExactDecimal(value, out decimal number)) return "Expected an exact finite JSON number; strings and rounding are not supported.";
                    if (field.Type == "integer")
                    {
                        if (decimal.Truncate(number) != number || number < -9007199254740991m || number > 9007199254740991m)
                            return "Expected an integer in [-9007199254740991, 9007199254740991].";
                    }
                    else if (Math.Abs(number) > 1000000000m || decimal.Round(number, 6) != number)
                        return "Numbers require magnitude at most 1000000000 and at most six normalized fractional places.";
                    if (number < field.Min || number > field.Max) return "Value is outside the declared bounds.";
                    if (field.Step.HasValue && (number - (field.Min ?? 0)) % field.Step.Value != 0) return "Value is off the declared step grid.";
                    canonical = JsonNode.Parse(number.ToString("G29", CultureInfo.InvariantCulture));
                    return null;
                case "string":
                case "enum":
                    if (kind != JsonValueKind.String) return "Expected a JSON string.";
                    string text = scalar.GetValue<string>();
                    if (text.Any(char.IsControl)) return "Expected plain text without control characters.";
                    if (field.Type == "enum" && !field.Values.Contains(text, StringComparer.Ordinal)) return "Value is not a declared enum choice.";
                    if (field.Type == "string" && (text.Length < (field.MinLength ?? 0) || text.Length > field.MaxLength)) return "Value violates the declared string length bounds.";
                    break;
                default: return "Unsupported compiled scalar type.";
            }
            canonical = value.DeepClone();
            return null;
        }

        private static List<FalMediaInstruction> ValidateMedia(FalOperationBinding binding, FalModelInput input, List<FalFieldError> errors)
        {
            var instructions = new List<FalMediaInstruction>();
            foreach (var item in input.Media)
            {
                if (!binding.Media.Any(m => m.Role == item.Role)) errors.Add(new FalFieldError("media." + item.Role, "Unknown semantic media role."));
                if (item.Source.Kind != MediaRefKind.Artifact) errors.Add(new FalFieldError("media." + item.Role, "Configured media requires an artifact reference."));
            }
            foreach (var definition in binding.Media)
            {
                var items = input.Media.Where(m => m.Role == definition.Role).OrderBy(m => m.Ordinal).ToArray();
                if (items.Length < definition.MinCount || items.Length > definition.MaxCount)
                    errors.Add(new FalFieldError("media." + definition.Role, "Media count is outside the declared role cardinality."));
                if (!items.Select(m => m.Ordinal).SequenceEqual(Enumerable.Range(0, items.Length)))
                    errors.Add(new FalFieldError("media." + definition.Role, "Role ordinals must be unique and consecutive, beginning at zero."));
                instructions.AddRange(items.Select(i => new FalMediaInstruction(definition, i)));
            }
            return instructions;
        }

        private static bool Matches(FalConditionDefinition condition, Dictionary<string, JsonNode?> values, IReadOnlyList<FalMediaInput> media)
        {
            if (condition.Role != null) return media.Any(m => m.Role == condition.Role) == condition.Present;
            if (!values.TryGetValue(condition.Field!, out var value)) return false;
            return condition.Operator == "eq" ? SameValue(value, condition.Value) : condition.Values!.Any(v => SameValue(value, v));
        }
        internal static bool SameValue(JsonNode? left, JsonNode? right)
            => left != null && right != null && FalCanonicalJson.Hash(left) == FalCanonicalJson.Hash(right);
    }
    public sealed class FalNormalizationResult
    {
        public FalOperationBinding Binding { get; }
        public bool Success => Request != null;
        public FalNormalizedRequest? Request { get; }
        public IReadOnlyList<FalFieldError> Errors { get; }
        public IReadOnlyList<string> InactiveFields { get; }
        internal FalNormalizationResult(FalOperationBinding binding, FalNormalizedRequest? request, IEnumerable<FalFieldError> errors, IEnumerable<string> inactive)
        {
            Binding = binding; Request = request; Errors = Array.AsReadOnly(errors.ToArray()); InactiveFields = Array.AsReadOnly(inactive.ToArray());
            if ((Request != null) == (Errors.Count != 0)) throw new ArgumentException("A normalized request or field errors are required.");
        }
    }
    public sealed class FalFieldError
    {
        public string Field { get; }
        public string Message { get; }
        internal FalFieldError(string field, string message) { Field = field; Message = message; }
    }
}
