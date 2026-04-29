using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalFluxSchnellPricingModel
        : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public const string Source = "fal-ai/flux/schnell-megapixel-2026-04-29";
        public const string Provenance = "fal-ai/flux/schnell-pricing-page-2026-04-29";
        internal const decimal UnitPriceUsdPerMegapixel = 0.003m;

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.ResponseHeader;

        public PricingResult Estimate(ImageGenerationRequest request, ImageCapability capability)
        {
            if (request is null)
                return PricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Image generation request is null.",
                    Retryable: false,
                    Field: "request"));

            const decimal minBillableMegapixels = 1m;
            const decimal maxBillableMegapixels = 2m;

            return PricingResult.Ok(
                new JobPricing(
                    Currency: "USD",
                    UnitPrice: UnitPriceUsdPerMegapixel,
                    Unit: "megapixel",
                    Quantity: null,
                    TotalUsd: null,
                    PricingSource: Source),
                new CostEstimate(
                    Min: minBillableMegapixels * UnitPriceUsdPerMegapixel,
                    Max: maxBillableMegapixels * UnitPriceUsdPerMegapixel,
                    IsExact: false,
                    Provenance: Provenance));
        }

        public JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody)
        {
            if (!FalPricingHelpers.TryGetBillableUnits(responseHeaders, out var units))
                return null;

            return new JobPricing(
                Currency: "USD",
                UnitPrice: UnitPriceUsdPerMegapixel,
                Unit: "megapixel",
                Quantity: units,
                TotalUsd: units * UnitPriceUsdPerMegapixel,
                PricingSource: Source);
        }
    }
}
