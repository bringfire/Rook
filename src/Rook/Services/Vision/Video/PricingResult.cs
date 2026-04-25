namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Envelope returned by <see cref="IPricingModel.Estimate"/>. Failure
    /// surfaces as a typed <see cref="VideoJobError"/> (e.g. the
    /// requested resolution has no published rate); the estimator wraps
    /// it into <see cref="VideoCostEstimateResult.Fail"/> at the call
    /// site without recomputing.
    /// </summary>
    public sealed record PricingResult(
        JobPricing? Pricing,
        VideoJobError? Error)
    {
        public bool Success => Pricing is not null;

        public static PricingResult Ok(JobPricing pricing) => new(pricing, null);

        public static PricingResult Fail(VideoJobError error) => new(null, error);
    }
}
