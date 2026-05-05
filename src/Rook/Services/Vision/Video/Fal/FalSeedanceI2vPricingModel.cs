using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalSeedanceI2vPricingModel
        : IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        public const string Source = "fal-bytedance-seedance-2.0-i2v-output-second-2026-05-05";
        private const decimal UnitPriceUsd = 0.3024m;

        public string PricingSource => Source;

        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

        public PricingResult Estimate(
            VideoGenerationRequest request,
            VideoCapability capability)
        {
            if (request is null)
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            if (capability is null)
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Capability is null.",
                    Retryable: false,
                    Field: nameof(capability)));

            decimal quantity;
            try { quantity = checked(request.DurationSeconds * request.NumberOfVideos); }
            catch (OverflowException)
            {
                return PricingResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    $"Quantity overflow: duration={request.DurationSeconds} x count={request.NumberOfVideos}.",
                    Retryable: false,
                    Field: nameof(request.NumberOfVideos)));
            }

            var total = UnitPriceUsd * quantity;
            var pricing = new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: UnitPriceUsd,
                Unit: "output_second",
                Quantity: quantity,
                TotalUsd: total,
                PricingSource: Source);
            var estimate = new CostEstimate(
                Min: total,
                Max: total,
                IsExact: false,
                Provenance: Source);

            return PricingResult.Ok(pricing, estimate);
        }

        public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }
}
