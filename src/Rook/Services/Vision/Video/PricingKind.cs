namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Discriminator for how a job's cost is computed. Persisted into
    /// the ledger so audit / replay / cost-gate explanations can read
    /// the exact pricing model in effect at submit time, even if the
    /// capability table changes later.
    /// </summary>
    public enum PricingKind
    {
        PerSecond = 0,        // total = quantity (= duration_s × number_of_videos) × unit_price
        PerGeneration = 1,    // total = quantity (= number_of_videos) × unit_price
        External = 2,         // subscription-bundled / unknown; unit_price + total_usd may be null
    }
}
