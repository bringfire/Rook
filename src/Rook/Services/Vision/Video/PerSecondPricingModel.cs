using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-second pricing model: <c>quantity = duration_seconds × number_of_videos</c>,
    /// <c>total = quantity × rate(resolution)</c>. Rates are bound at
    /// construction (one instance per model since Veo 3.1 / 3.1 Lite /
    /// 3.0 etc. all charge differently at the same resolution).
    /// </summary>
    public sealed class PerSecondPricingModel : IPricingModel
    {
        private readonly IReadOnlyDictionary<string, decimal> _ratesPerSecondUsd;

        public PerSecondPricingModel(
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

        public PricingKind Kind => PricingKind.PerSecond;

        public string PricingSource { get; }

        public PricingResult Estimate(VideoGenerationRequest request, ModelCapability cap)
        {
            if (request is null)
                return PricingResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            if (cap is null)
                return PricingResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Capability is null.",
                    Retryable: false,
                    Field: nameof(cap)));

            if (!_ratesPerSecondUsd.TryGetValue(request.Resolution, out var rate))
                return PricingResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.UnsupportedMedia,
                    Message: $"{cap.Name} has no published per-second price for resolution '{request.Resolution}'.",
                    Retryable: false,
                    Field: nameof(request.Resolution)));

            // L4: checked-arithmetic for the int multiplication. Today
            // both factors are validator-bounded (duration in {4,5,6,8},
            // count == 1) so overflow is impossible; the checked block
            // is insurance for when the N==1 limit lifts in V2+ and a
            // pathological caller submits a huge count.
            int quantity;
            try { quantity = checked(request.DurationSeconds * request.NumberOfVideos); }
            catch (OverflowException)
            {
                return PricingResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Quantity overflow: duration={request.DurationSeconds} × " +
                             $"count={request.NumberOfVideos}.",
                    Retryable: false,
                    Field: nameof(request.NumberOfVideos)));
            }

            var total = rate * quantity;

            return PricingResult.Ok(new JobPricing(
                Kind: PricingKind.PerSecond,
                Currency: "USD",
                Quantity: quantity,
                UnitPriceUsd: rate,
                TotalUsd: total,
                PricingSource: PricingSource));
        }
    }
}
