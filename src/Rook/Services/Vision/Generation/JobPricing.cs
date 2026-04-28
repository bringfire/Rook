using System;

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
    public sealed record JobPricing
    {
        public JobPricing(
            string Currency,
            decimal? UnitPrice,
            string? Unit,
            decimal? Quantity,
            decimal? TotalUsd,
            string PricingSource)
        {
            if (string.IsNullOrWhiteSpace(Currency))
                throw new ArgumentException(
                    "Currency must be non-empty.", nameof(Currency));
            if (string.IsNullOrWhiteSpace(PricingSource))
                throw new ArgumentException(
                    "PricingSource must be non-empty.", nameof(PricingSource));

            // Numeric fields are nullable for external/subscription-bundled
            // pricing where the figures are unknown at submit time.
            // When non-null, they must be non-negative — negative spend
            // is never meaningful.
            if (UnitPrice is { } u && u < 0m)
                throw new ArgumentOutOfRangeException(
                    nameof(UnitPrice), u, "UnitPrice must be non-negative when set.");
            if (Quantity is { } q && q < 0m)
                throw new ArgumentOutOfRangeException(
                    nameof(Quantity), q, "Quantity must be non-negative when set.");
            if (TotalUsd is { } t && t < 0m)
                throw new ArgumentOutOfRangeException(
                    nameof(TotalUsd), t, "TotalUsd must be non-negative when set.");

            this.Currency = Currency;
            this.UnitPrice = UnitPrice;
            this.Unit = Unit;
            this.Quantity = Quantity;
            this.TotalUsd = TotalUsd;
            this.PricingSource = PricingSource;
        }

        public string Currency { get; init; }                // "USD" — fixed for Phase 1
        public decimal? UnitPrice { get; init; }             // per-unit rate at submit time
        public string? Unit { get; init; }                   // "megapixel" | "output_second" | "compute_second" | "token" | "call"
        public decimal? Quantity { get; init; }              // number of units
        public decimal? TotalUsd { get; init; }              // UnitPrice × Quantity, or null if external
        public string PricingSource { get; init; }           // human label for descriptors / audit
    }
}
