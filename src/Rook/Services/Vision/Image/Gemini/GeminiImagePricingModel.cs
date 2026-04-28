using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Gemini
{
    public sealed class GeminiImagePricingModel
        : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public const string Source = "gemini-per-token-by-modality-stub";
        public const string StubProvenance = "gemini-stub-2026-04-27";

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseBody;

        public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
        {
            return PricingResult.Ok(
                new JobPricing(
                    Currency: "USD",
                    UnitPrice: 0m,
                    Unit: "token",
                    Quantity: null,
                    TotalUsd: 0m,
                    PricingSource: Source),
                new CostEstimate(
                    Min: 0m,
                    Max: 0m,
                    IsExact: false,
                    Provenance: StubProvenance));
        }

        public JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody)
        {
            var usage = responseBody?["usageMetadata"] ?? responseBody;
            var prompt = DecimalFromNode(usage?["promptTokenCount"]);
            var candidates = DecimalFromNode(usage?["candidatesTokenCount"]);
            if (prompt is null && candidates is null) return null;

            return new JobPricing(
                Currency: "USD",
                UnitPrice: 0m,
                Unit: "token",
                Quantity: (prompt ?? 0m) + (candidates ?? 0m),
                TotalUsd: 0m,
                PricingSource: Source);
        }

        private static decimal? DecimalFromNode(JsonNode? node)
        {
            if (node is null) return null;
            try { return node.GetValue<decimal>(); }
            catch { }
            try { return node.GetValue<int>(); }
            catch { }
            try { return node.GetValue<long>(); }
            catch { }
            try { return (decimal)node.GetValue<double>(); }
            catch { return null; }
        }
    }
}
