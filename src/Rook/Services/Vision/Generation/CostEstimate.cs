namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral cost estimate. Phase 0 evidence: pricing varies
    /// fundamentally across providers (per-MP, per-output-second × tier,
    /// per-call flat + add-ons, per-compute-second, per-token-by-modality).
    /// The shared shape is a min/max range with a flag for exactness and
    /// a provenance tag identifying the rate table version.
    ///
    /// <list type="bullet">
    ///   <item><see cref="IsExact"/> true: deterministic at submit time
    ///         (Veo per-second, fal flat-call). <see cref="Min"/> equals
    ///         <see cref="Max"/>.</item>
    ///   <item><see cref="IsExact"/> false: estimate (Replicate
    ///         per-compute-second varies with hardware contention;
    ///         aggregator margin not measured). <see cref="Min"/> /
    ///         <see cref="Max"/> bracket the expected range.</item>
    /// </list>
    ///
    /// <para><see cref="Provenance"/> identifies the rate table version
    /// (e.g. <c>"veo-per-second-2026-04-15"</c>,
    /// <c>"gemini-stub-2026-04-27"</c>) so audit / cost-gate
    /// explanations can read which rate was in effect at submit time
    /// even if the rate table changes later.</para>
    /// </summary>
    public sealed record CostEstimate(
        decimal Min,
        decimal Max,
        bool IsExact,
        string Provenance);
}
