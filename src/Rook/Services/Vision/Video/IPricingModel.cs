namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-resolved-model pricing strategy. Bound at registry
    /// construction (one instance per <see cref="ResolvedVideoModel"/>),
    /// invoked exactly once per estimate by
    /// <see cref="VideoCostEstimator"/>; the resulting
    /// <see cref="JobPricing"/> is then copied verbatim into the ledger
    /// record by <see cref="VideoJobRecordFactory"/>. Pricing is never
    /// recomputed downstream.
    ///
    /// <see cref="Kind"/> and <see cref="PricingSource"/> are exposed for
    /// catalog enumeration via <see cref="VideoModelDescriptor"/>; both
    /// must match the corresponding fields on the
    /// <see cref="JobPricing"/> emitted by <see cref="Estimate"/>.
    /// </summary>
    public interface IPricingModel
    {
        PricingKind Kind { get; }
        string PricingSource { get; }

        PricingResult Estimate(VideoGenerationRequest request, ModelCapability cap);
    }
}
