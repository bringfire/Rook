using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalNanoBananaPricingModel : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public FalNanoBananaPricingModel(string modelId)
        {
            if (!ImageRoutingCodec.IsFalModel(modelId)) throw new ArgumentException("Unsupported fal model.", nameof(modelId));
        }
        public string PricingSource => "fal-nano-banana-unavailable-2026-10-12";
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;
        public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability) =>
            PricingResult.Ok(new JobPricing("USD", null, "image", 1m, null, PricingSource),
                new CostEstimate(0m, 0m, false, PricingSource));
        public JobPricing? ExtractActualSpend(IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }
}
