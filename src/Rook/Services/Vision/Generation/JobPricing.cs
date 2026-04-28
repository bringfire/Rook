namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral per-job pricing snapshot. The video-namespace
    /// <c>JobPricing</c> (PR-2) ships a video-shaped projection (resolution
    /// × duration × videos) that fills the same fields; image and future
    /// modalities fill what they have signal for.
    ///
    /// <para>Used both as the audit-snapshot ledger field and as the
    /// downstream feed for <see cref="CostEstimate"/>. Fields are
    /// nullable where the provider doesn't expose the signal at submit
    /// time (e.g. external/subscription-bundled where total is unknown
    /// until usage telemetry arrives).</para>
    /// </summary>
    public sealed record JobPricing(
        string Currency,                    // "USD" — fixed for Phase 1
        decimal? UnitPrice,                 // per-unit rate at submit time
        string? Unit,                       // "megapixel" | "output_second" | "compute_second" | "token" | "call"
        decimal? Quantity,                  // number of units
        decimal? TotalUsd,                  // UnitPrice × Quantity, or null if external
        string PricingSource);              // human label for descriptors / audit
}
