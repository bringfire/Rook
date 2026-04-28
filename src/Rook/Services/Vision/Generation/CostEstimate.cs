using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral cost estimate. Phase 0 evidence: pricing varies
    /// fundamentally across providers (per-MP, per-output-second × tier,
    /// per-call flat + add-ons, per-compute-second, per-token-by-modality).
    /// The shared shape is a min/max range with a flag for exactness and
    /// a provenance tag identifying the rate table version.
    ///
    /// <para><b>Sealed class with read-only properties</b> (not a record).
    /// Records would expose <c>init</c> setters that let callers bypass
    /// constructor validation via <c>with</c> expressions and object
    /// initializers — a valid <c>CostEstimate</c> could be cloned with
    /// <c>Min = -1m</c>. Read-only properties make construction the
    /// only entry point.</para>
    /// </summary>
    public sealed class CostEstimate : IEquatable<CostEstimate>
    {
        public CostEstimate(decimal Min, decimal Max, bool IsExact, string Provenance)
        {
            if (Min < 0m)
                throw new ArgumentOutOfRangeException(
                    nameof(Min), Min, "CostEstimate.Min must be non-negative.");
            if (Max < Min)
                throw new ArgumentOutOfRangeException(
                    nameof(Max), Max,
                    $"CostEstimate.Max ({Max}) must be greater than or equal to Min ({Min}).");
            if (IsExact && Min != Max)
                throw new ArgumentException(
                    $"CostEstimate.IsExact=true requires Min == Max; got Min={Min}, Max={Max}.",
                    nameof(IsExact));
            if (string.IsNullOrWhiteSpace(Provenance))
                throw new ArgumentException(
                    "Provenance must be non-empty — every cost estimate must " +
                    "name the rate table version it was computed from.",
                    nameof(Provenance));

            this.Min = Min;
            this.Max = Max;
            this.IsExact = IsExact;
            this.Provenance = Provenance;
        }

        public decimal Min { get; }
        public decimal Max { get; }
        public bool IsExact { get; }
        public string Provenance { get; }

        // Value equality — useful for golden-fixture asserts in PR-2/PR-3.
        public bool Equals(CostEstimate? other) =>
            other is not null
            && Min == other.Min
            && Max == other.Max
            && IsExact == other.IsExact
            && string.Equals(Provenance, other.Provenance, StringComparison.Ordinal);

        public override bool Equals(object? obj) => Equals(obj as CostEstimate);
        public override int GetHashCode() => (Min, Max, IsExact, Provenance).GetHashCode();
    }
}
