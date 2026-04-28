using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using GenerationPricingResult = Rook.Services.Vision.Generation.PricingResult;
using VideoPricingResult = Rook.Services.Vision.Video.PricingResult;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-second video pricing model:
    /// <c>quantity = duration_seconds × number_of_videos</c>,
    /// <c>total = quantity × rate(resolution)</c>.
    /// </summary>
    public sealed class PerSecondVideoPricingModel
        : Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability>
    {
        private readonly IReadOnlyDictionary<string, decimal> _ratesPerSecondUsd;

        public PerSecondVideoPricingModel(
            IReadOnlyDictionary<string, decimal> ratesPerSecondUsd,
            string pricingSource)
        {
            _ratesPerSecondUsd = ratesPerSecondUsd
                ?? throw new ArgumentNullException(nameof(ratesPerSecondUsd));

            if (string.IsNullOrWhiteSpace(pricingSource))
                throw new ArgumentException(
                    "pricingSource must be non-empty.", nameof(pricingSource));

            PricingSource = pricingSource;
        }

        public string PricingSource { get; }

        public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;

        public GenerationPricingResult Estimate(
            VideoGenerationRequest request,
            VideoCapability capability)
        {
            if (request is null)
                return GenerationPricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            if (capability is null)
                return GenerationPricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Capability is null.",
                    Retryable: false,
                    Field: nameof(capability)));

            if (!_ratesPerSecondUsd.TryGetValue(request.Resolution, out var rate))
                return GenerationPricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.UnsupportedMedia,
                    Message: $"{capability.Name} has no published per-second price for resolution '{request.Resolution}'.",
                    Retryable: false,
                    Field: nameof(request.Resolution)));

            decimal quantity;
            try { quantity = checked(request.DurationSeconds * request.NumberOfVideos); }
            catch (OverflowException)
            {
                return GenerationPricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: $"Quantity overflow: duration={request.DurationSeconds} × " +
                             $"count={request.NumberOfVideos}.",
                    Retryable: false,
                    Field: nameof(request.NumberOfVideos)));
            }

            var total = rate * quantity;
            var pricing = new Rook.Services.Vision.Generation.JobPricing(
                Currency: "USD",
                UnitPrice: rate,
                Unit: "output_second",
                Quantity: quantity,
                TotalUsd: total,
                PricingSource: PricingSource);
            var estimate = new CostEstimate(
                Min: total,
                Max: total,
                IsExact: true,
                Provenance: PricingSource);

            return GenerationPricingResult.Ok(pricing, estimate);
        }

        public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }

    /// <summary>
    /// Transitional V1c wrapper. New registry paths use
    /// <see cref="PerSecondVideoPricingModel"/> directly; the wrapper
    /// keeps older tests and compatibility surfaces compiling until the
    /// deletion sweep removes the video-local pricing interface.
    /// </summary>
    public sealed class PerSecondPricingModel : IPricingModel
    {
        private readonly PerSecondVideoPricingModel _inner;

        public PerSecondPricingModel(
            IReadOnlyDictionary<string, decimal> ratesPerSecondUsd,
            string pricingSource)
        {
            _inner = new PerSecondVideoPricingModel(
                ratesPerSecondUsd,
                pricingSource);
        }

        public PricingKind Kind => PricingKind.PerSecond;

        public string PricingSource => _inner.PricingSource;

        public VideoPricingResult Estimate(
            VideoGenerationRequest request,
            VideoCapability cap)
        {
            var result = _inner.Estimate(request, cap);
            return VideoJobPricingTranslator.ToVideoPricingResult(
                result,
                PricingKind.PerSecond);
        }
    }
}
