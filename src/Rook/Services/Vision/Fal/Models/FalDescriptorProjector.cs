using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>Shared discovery contract for panel and MCP; binding metadata remains authoritative.</summary>
    public sealed class FalDescriptorProjector
    {
        public FalOperationDescriptor Describe(FalOperationBinding binding, FalNormalizationResult? validation)
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (validation != null && (validation.Binding.DefinitionHash != binding.DefinitionHash || validation.Binding.OperationId != binding.OperationId))
                throw new ArgumentException("Validation must belong to the described binding.", nameof(validation));
            var ordered = binding.Fields.OrderBy(f => f.UiGroup == "advanced" ? 1 : 0).ThenBy(f => f.UiOrder).ThenBy(f => f.QualifiedKey, StringComparer.Ordinal).ToArray();
            var reasons = new JsonArray();
            if (binding.Status == "disabled") reasons.Add("disabled");
            string pricingStatus = PricingStatus(binding, validation);
            if (binding.Pricing == null) reasons.Add("pricing_unavailable");
            else if (pricingStatus == "unavailable_for_values") reasons.Add("pricing_unavailable_for_values");
            var json = new JsonObject
            {
                ["model_id"] = binding.ModelId, ["display_name"] = binding.DisplayName, ["provider"] = "fal", ["status"] = binding.Status,
                ["definition_id"] = binding.DefinitionId, ["revision"] = binding.Revision, ["definition_hash"] = binding.DefinitionHash, ["source_file"] = binding.SourceFile,
                ["operation_id"] = binding.OperationId, ["operations"] = new JsonArray(binding.OperationId), ["invocation"] = binding.Invocation,
                ["adapter"] = new JsonObject { ["id"] = binding.AdapterId, ["version"] = binding.AdapterVersion },
                ["submission_contract"] = binding.Result.MimeFamily == "image" ? "image_job" : "video_job",
                ["request_fields"] = new JsonArray(ordered.Where(f => f.Scope == "request").Select(f => (JsonNode?)DescribeField(f)).ToArray()),
                ["options"] = new JsonArray(ordered.Where(f => f.Scope == "options").Select(f => (JsonNode?)DescribeField(f)).ToArray()),
                ["media"] = new JsonArray(binding.Media.Select(m => (JsonNode?)m.ToJson()).ToArray()),
                ["constraints"] = new JsonArray(binding.Constraints.Select(c => (JsonNode?)c.ToJson()).ToArray()),
                ["capabilities"] = Capabilities(binding),
                ["pricing_available"] = binding.Pricing != null, ["pricing_status"] = pricingStatus,
                ["paid_admission_available"] = reasons.Count == 0 && pricingStatus == "available" && (validation == null || validation.Success),
                ["selectable"] = binding.Status != "disabled", ["unavailable_reasons"] = reasons,
                ["field_errors"] = new JsonArray((validation?.Errors ?? Array.Empty<FalFieldError>()).Select(e => (JsonNode?)new JsonObject { ["field"] = e.Field, ["message"] = e.Message }).ToArray()),
                ["inactive_fields"] = new JsonArray((validation?.InactiveFields ?? Array.Empty<string>()).Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
                ["evidence"] = new JsonObject { ["url"] = binding.Evidence.Url, ["reviewed_on"] = binding.Evidence.ReviewedOn, ["qualification"] = binding.Evidence.Qualification }
            };
            if (binding.Pricing != null) json["pricing"] = FalPublicPricing.Project(binding.Pricing.ToJson());
            return new FalOperationDescriptor(json);
        }

        private static string PricingStatus(FalOperationBinding binding, FalNormalizationResult? validation)
        {
            var pricing = binding.Pricing;
            if (pricing == null) return "unavailable";
            var values = new JsonObject();
            if (validation?.Request is FalNormalizedRequest normalized)
            {
                var request = normalized.EffectiveRequestFields; var options = normalized.EffectiveOptions;
                foreach (var field in binding.Fields)
                    if ((field.Scope == "request" ? request : options).TryGetPropertyValue(field.Key, out var value))
                        values.Add(field.QualifiedKey, value?.DeepClone());
            }
            else if (validation == null) values = FalModelNormalizer.DefaultEffectiveValues(binding);
            // Failed validation supplies no usable effective controls; never fall
            // back to defaults for the caller's invalid submitted configuration.
            var needed = new HashSet<string>(pricing.Rates[0].Selectors.Select(s => s.Key), StringComparer.Ordinal);
            if (pricing.Strategy == "per_output_second") needed.Add(pricing.QuantityField!);
            if (pricing.Strategy == "per_output_megapixel" && pricing.ToJson()["dimensions"] is JsonObject dimensions)
                needed.Add(dimensions["field"]!.GetValue<string>());
            if (needed.Any(k => !values.ContainsKey(k))) return "requires_inputs";
            return pricing.Rates.Any(r => r.Selectors.All(s => values.TryGetPropertyValue(s.Key, out var value) && FalModelNormalizer.SameValue(s.Value, value)))
                ? "available" : "unavailable_for_values";
        }

        private static JsonObject DescribeField(FalFieldDefinition field)
        {
            var json = field.ToJson(); json.Remove("payload");
            json["required"] = field.Required;
            json["ui"] = new JsonObject { ["group"] = field.UiGroup, ["order"] = field.UiOrder, ["hidden"] = field.Hidden };
            return json;
        }
        private static JsonObject Capabilities(FalOperationBinding binding)
        {
            var result = new JsonObject { ["operation"] = binding.OperationId, ["output_count"] = 1 };
            int references = binding.Media.FirstOrDefault(m => m.Role == "reference_image")?.MaxCount ?? 0;
            result["supports_reference_images"] = references > 0;
            result["max_reference_images"] = references;
            if (binding.Result.MimeFamily == "image")
            {
                result["supports_text_to_image"] = binding.OperationId == "text_to_image";
                result["supports_image_to_image"] = binding.OperationId == "image_to_image";
            }
            else
            {
                string mode = binding.OperationId == "text_to_video" ? "t2v" : binding.OperationId == "image_to_video" ? "i2v" : "interp";
                result["modes"] = new JsonArray(mode);
                result["must_8s_with"] = new JsonArray();
                var duration = binding.Fields.FirstOrDefault(f => f.QualifiedKey == "request.duration_seconds");
                var durations = ProjectDurations(binding, duration, out bool complete);
                result["durations"] = durations;
                result["legacy_duration_projection_complete"] = complete;
            }
            foreach (var key in new[] { "resolution", "aspect_ratio", "duration_seconds" })
            {
                var field = binding.Fields.FirstOrDefault(f => f.QualifiedKey == "request." + key);
                if (field == null) continue;
                string name = key == "resolution" ? "resolutions" : key == "aspect_ratio" ? "aspect_ratios" : "duration_seconds";
                if (field.Type == "enum") result[name] = new JsonArray(field.Values.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray());
                else result[name] = DescribeField(field);
            }
            return result;
        }

        // Compatibility-output bound only: the exact typed descriptor remains the
        // configured validation contract even when this legacy list is incomplete.
        private static JsonArray ProjectDurations(FalOperationBinding binding, FalFieldDefinition? field, out bool complete)
        {
            complete = false;
            var values = new JsonArray();
            if (field == null || field.Type != "integer" || !field.Min.HasValue || !field.Max.HasValue
                || binding.Constraints.Any(c => c.Field == field.QualifiedKey)) return values;
            decimal step = field.Step ?? 1;
            if (field.Min < int.MinValue || field.Max > int.MaxValue || step > int.MaxValue) return values;
            long minimum = (long)field.Min.Value; long maximum = (long)field.Max.Value; long increment = (long)step;
            long count = (maximum - minimum) / increment + 1;
            if (count > 256) return values;
            for (long value = minimum; value <= maximum; value += increment) values.Add((int)value);
            complete = true;
            return values;
        }
    }
}
