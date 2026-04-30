using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalWanT2vPricingModel
        : IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        public const string Source = "fal-ai/wan/v2.7/text-to-video-output-second-2026-04-29";

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

            var total = 0.10m * quantity;
            var pricing = new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: 0.10m,
                Unit: "output_second",
                Quantity: quantity,
                TotalUsd: total,
                PricingSource: Source);
            var estimate = new CostEstimate(
                Min: total,
                Max: total,
                IsExact: true,
                Provenance: Source);

            return PricingResult.Ok(pricing, estimate);
        }

        public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }
}
