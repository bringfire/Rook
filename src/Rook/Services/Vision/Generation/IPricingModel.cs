using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Per-resolved-model pricing strategy. Generic over the request and
    /// capability shapes so a video pricing model can pattern-match on
    /// resolution × duration × tier and an image pricing model can
    /// pattern-match on token counts × modality.
    ///
    /// <para>Phase 0 binding: each implementation owns its own
    /// header/body parsing for actual-spend extraction.
    /// <see cref="MetadataLocation"/> is a documentation hint only;
    /// <see cref="ExtractActualSpend"/> is where the work happens.</para>
    /// </summary>
    public interface IPricingModel<TRequest, TCapability>
        where TRequest : GenerationRequest
        where TCapability : IModelCapability
    {
        string PricingSource { get; }
        PricingMetadataLocation MetadataLocation { get; }

        /// <summary>Estimate cost at submit time, before the call.
        /// Returns both <see cref="JobPricing"/> (audit snapshot) and
        /// <see cref="CostEstimate"/> (UI-facing range) — a single
        /// estimator call produces both so the audit + the UI cannot
        /// drift.</summary>
        PricingResult Estimate(TRequest request, TCapability capability);

        /// <summary>Optional — extract actual spend from a response.
        /// Each provider's pricing model owns its own header/body
        /// parsing. Returns null when actual spend is unknowable from
        /// the response (e.g. subscription-bundled). The provider
        /// passes through whatever the response surfaced; the pricing
        /// model interprets per-model rates.</summary>
        JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody);
    }
}
