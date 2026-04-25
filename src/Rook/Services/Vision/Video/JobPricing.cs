using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Audit snapshot of a job's cost as accepted at submit time.
    /// Persisted to the ledger so future cost-gate replays / audits
    /// don't depend on the live capability-table pricing.
    ///
    /// Quantity math (Codex round 4):
    /// <list type="bullet">
    ///   <item><description><see cref="PricingKind.PerSecond"/>: <c>quantity = duration_seconds × number_of_videos</c></description></item>
    ///   <item><description><see cref="PricingKind.PerGeneration"/>: <c>quantity = number_of_videos</c></description></item>
    ///   <item><description><see cref="PricingKind.External"/>: <c>quantity = number_of_videos</c>; <see cref="UnitPriceUsd"/> may be null</description></item>
    /// </list>
    ///
    /// Invariant: when both <see cref="UnitPriceUsd"/> and
    /// <see cref="TotalUsd"/> are non-null,
    /// <c>TotalUsd = Quantity × UnitPriceUsd</c>.
    /// </summary>
    public sealed record JobPricing(
        PricingKind Kind,
        string Currency,           // "USD" in v1; field-shaped for forward-compat
        int Quantity,
        decimal? UnitPriceUsd,
        decimal? TotalUsd,

        /// <summary>
        /// Free-form identifier for the rate card / pricing source in
        /// effect at submit time. E.g., "veo-rate-card-v1". Updates rates
        /// without requiring a code-version bump for replay correctness.
        /// </summary>
        string PricingSource);
}
