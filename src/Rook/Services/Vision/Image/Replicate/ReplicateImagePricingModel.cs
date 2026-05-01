using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImagePricingModel
        : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public const string Source = "replicate-flux-schnell-predict-time-2026-05-01";
        public const string Provenance = "replicate-prediction-metrics-2026-05-01";

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseBody;

        public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
        {
            return PricingResult.Ok(
                new JobPricing(
                    Currency: "USD",
                    UnitPrice: null,
                    Unit: "compute_second",
                    Quantity: null,
                    TotalUsd: null,
                    PricingSource: Source),
                new CostEstimate(
                    Min: 0m,
                    Max: 0m,
                    IsExact: false,
                    Provenance: Provenance));
        }

        public JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody)
        {
            return responseBody is null
                ? null
                : ReplicatePredictionPricing.ExtractActualSpend(responseBody, Source);
        }
    }
}
