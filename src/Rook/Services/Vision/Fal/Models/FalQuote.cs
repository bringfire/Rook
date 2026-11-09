using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalQuote
    {
        private readonly JsonObject _canonical;
        public FalPricingSnapshot Pricing { get; }
        public string Fingerprint { get; }
        public decimal MaximumEstimatedCostUsd { get; }
        public string Currency => "USD";
        public decimal? ActualUsd => null;
        internal FalQuote(JsonObject canonical, FalPricingSnapshot pricing)
        { _canonical = (JsonObject)canonical.DeepClone(); Pricing = pricing; Fingerprint = Video.VideoEstimateFingerprint.ComputeConfigured(canonical); MaximumEstimatedCostUsd = PublicCeiling(pricing.EstimateMaxUsd); }
        internal static decimal PublicCeiling(decimal upper)
        {
            if (upper < 0 || upper > 1000000000m) throw new ArgumentOutOfRangeException(nameof(upper));
            return decimal.Ceiling(upper * 1000000m) / 1000000m;
        }
        public JsonObject ToJson()
        {
            var candidate = (JsonObject)_canonical.DeepClone();
            candidate["pricing"] = Pricing.ToPublicJson();
            if (candidate["binding"]?["pricing"] is JsonObject bindingPricing)
                candidate["binding"]!["pricing"] = FalPublicPricing.Project(bindingPricing);
            return new() { ["quote_fingerprint"] = Fingerprint, ["max_estimated_cost_usd"] = MaximumEstimatedCostUsd,
                ["currency"] = Currency, ["actual_usd"] = null, ["pricing"] = Pricing.ToPublicJson(), ["candidates"] = new JsonArray(candidate) };
        }
    }

    public sealed class FalSubmitConfirmation
    {
        public string Fingerprint { get; }
        public decimal MaxEstimatedCostUsd { get; }
        public FalSubmitConfirmation(string fingerprint, decimal maxEstimatedCostUsd)
        {
            if (string.IsNullOrWhiteSpace(fingerprint)) throw new ArgumentException("A quote fingerprint is required.", nameof(fingerprint));
            if (maxEstimatedCostUsd < 0 || maxEstimatedCostUsd > 1000000000m || maxEstimatedCostUsd != decimal.Round(maxEstimatedCostUsd, 6))
                throw new ArgumentOutOfRangeException(nameof(maxEstimatedCostUsd));
            Fingerprint = fingerprint; MaxEstimatedCostUsd = maxEstimatedCostUsd;
        }
        public static Rook.Services.Vision.Generation.GenerationError? TryParse(JsonObject json, out FalSubmitConfirmation? confirmation)
        {
            confirmation = null;
            if (json["quote_fingerprint"]?.GetValueKind() != System.Text.Json.JsonValueKind.String ||
                !FalCanonicalJson.TryExactDecimal(json["max_estimated_cost_usd"], out var cap)) return FalQuoteService.ConfirmationRequired();
            var fingerprint = json["quote_fingerprint"]!.GetValue<string>();
            if (fingerprint.Length != 69 || !fingerprint.StartsWith("fal1:", StringComparison.Ordinal) ||
                System.Linq.Enumerable.Any(fingerprint.Substring(5), c => !Uri.IsHexDigit(c)) || cap < 0 || cap > 1000000000m || cap != decimal.Round(cap, 6))
                return new(Rook.Services.Vision.Generation.GenerationErrorCode.InvalidRequest, "Invalid configured fal confirmation.", false, "quote_fingerprint", "quote_confirmation_invalid");
            confirmation = new FalSubmitConfirmation(fingerprint, cap); return null;
        }
    }

    /// <summary>Only pricing provenance is text-encoded; user controls retain their declared numeric types.</summary>
    internal static class FalPublicPricing
    {
        internal static JsonObject Project(JsonObject value)
        {
            var copy = (JsonObject)value.DeepClone();
            Convert(copy); return copy;
        }
        private static void Convert(JsonNode node)
        {
            if (node is JsonObject obj)
            {
                foreach (var key in obj.Select(pair => pair.Key).ToArray())
                {
                    var value = obj[key];
                    if (FalCanonicalJson.TryExactDecimal(value, out var number) && (number < -1000000000m || number > 1000000000m || number != decimal.Round(number, 6)))
                        obj[key] = number.ToString("0.############################", CultureInfo.InvariantCulture);
                    else if (value is JsonObject || value is JsonArray) Convert(value);
                }
            }
            else if (node is JsonArray array) foreach (var child in array) if (child != null) Convert(child);
        }
    }
}
