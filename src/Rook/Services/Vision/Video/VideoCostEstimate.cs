using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    public sealed record CostBreakdownComponent(
        string Label,
        decimal DollarsUsd);

    /// <summary>
    /// Single-pass cost estimate. <see cref="Pricing"/> is the
    /// audit-grade <see cref="JobPricing"/> snapshot computed once by the
    /// resolved model's <see cref="IPricingModel"/>; downstream consumers
    /// (cost-confirmation UI, <see cref="VideoJobRecordFactory"/>) read
    /// from this single value rather than recomputing pricing.
    /// </summary>
    public sealed record VideoCostEstimate(
        decimal DollarsUsd,
        string Model,
        string Resolution,
        int DurationSeconds,
        int NumberOfVideos,
        IReadOnlyList<CostBreakdownComponent> Breakdown,
        JobPricing Pricing);
}
