using System;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>Accepted decimal pricing provenance, independent of legacy integer quantities.</summary>
    public sealed class FalPricingSnapshot
    {
        public string Unit { get; }
        public string Revision { get; }
        public string Source { get; }
        public decimal QuantityMin { get; }
        public decimal QuantityMax { get; }
        public decimal RateUsd { get; }
        public decimal EstimateMinUsd { get; }
        public decimal EstimateMaxUsd { get; }
        public FalPricingSnapshot(string unit, string revision, string source, decimal quantityMin, decimal quantityMax,
            decimal rateUsd, decimal estimateMinUsd, decimal estimateMaxUsd)
        {
            if (string.IsNullOrWhiteSpace(unit) || string.IsNullOrWhiteSpace(revision) || string.IsNullOrWhiteSpace(source)
                || quantityMin < 0 || quantityMax < quantityMin || rateUsd < 0 || estimateMinUsd < 0 || estimateMaxUsd < estimateMinUsd)
                throw new ArgumentException("Invalid pricing snapshot.");
            Unit = unit; Revision = revision; Source = source; QuantityMin = quantityMin; QuantityMax = quantityMax;
            RateUsd = rateUsd; EstimateMinUsd = estimateMinUsd; EstimateMaxUsd = estimateMaxUsd;
        }
        internal JsonObject ToJson() => new() { ["unit"] = Unit, ["revision"] = Revision, ["source"] = Source,
            ["quantity_min"] = QuantityMin, ["quantity_max"] = QuantityMax, ["rate_usd"] = RateUsd,
            ["estimate_min_usd"] = EstimateMinUsd, ["estimate_max_usd"] = EstimateMaxUsd };
        internal static FalPricingSnapshot FromJson(JsonObject json) => new(json["unit"]!.GetValue<string>(), json["revision"]!.GetValue<string>(),
            json["source"]!.GetValue<string>(), json["quantity_min"]!.GetValue<decimal>(), json["quantity_max"]!.GetValue<decimal>(),
            json["rate_usd"]!.GetValue<decimal>(), json["estimate_min_usd"]!.GetValue<decimal>(), json["estimate_max_usd"]!.GetValue<decimal>());
    }
}
