using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral per-job pricing snapshot. Used both as the
    /// audit-snapshot ledger field and as the downstream feed for
    /// <see cref="CostEstimate"/>. Numeric fields are nullable for
    /// external/subscription-bundled pricing; when non-null they must
    /// be non-negative.
    ///
    /// <para>Sealed class with read-only properties — invariants
    /// cannot be bypassed via <c>with</c> or object initializers.</para>
    /// </summary>
    public sealed class JobPricing : IEquatable<JobPricing>
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

        public string Currency { get; }
        public decimal? UnitPrice { get; }
        public string? Unit { get; }
        public decimal? Quantity { get; }
        public decimal? TotalUsd { get; }
        public string PricingSource { get; }

        public bool Equals(JobPricing? other) =>
            other is not null
            && string.Equals(Currency, other.Currency, StringComparison.Ordinal)
            && UnitPrice == other.UnitPrice
            && string.Equals(Unit, other.Unit, StringComparison.Ordinal)
            && Quantity == other.Quantity
            && TotalUsd == other.TotalUsd
            && string.Equals(PricingSource, other.PricingSource, StringComparison.Ordinal);

        public override bool Equals(object? obj) => Equals(obj as JobPricing);

        public override int GetHashCode() =>
            (Currency, UnitPrice, Unit, Quantity, TotalUsd, PricingSource).GetHashCode();
    }
}
