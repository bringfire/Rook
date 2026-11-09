using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalQuoteService
    {
        public FalQuoteResult Estimate(FalNormalizedRequest request, FalMediaSnapshot media)
        {
            if (request == null || media == null) throw new ArgumentNullException();
            if (media.Validate(request) is { } invalid) return FalQuoteResult.Fail(invalid);
            var pricing = new FalDeclarativePricing().Estimate(request);
            if (!pricing.Success) return FalQuoteResult.Fail(pricing.Error!);
            var canonical = new JsonObject { ["policy"] = "configured-fal-v1", ["model"] = request.Binding.ModelId,
                ["definition_hash"] = request.Binding.DefinitionHash, ["binding"] = request.Binding.ToJson(),
                ["effective_request"] = request.EffectiveRequestFields, ["effective_options"] = request.EffectiveOptions,
                ["media"] = FalExecutionSnapshot.Create(request, media).MediaProvenance,
                ["pricing"] = pricing.Pricing!.ToJson(), ["rate_selectors"] = pricing.RateSelectors };
            return FalQuoteResult.Ok(new FalQuote(canonical, pricing.Pricing));
        }
        public GenerationError? Validate(FalQuote quote, FalNormalizedRequest request, FalMediaSnapshot media, FalSubmitConfirmation? confirmation)
        {
            if (confirmation == null) return ConfirmationRequired();
            var current = Estimate(request, media);
            if (!current.Success) return current.Error;
            if (quote.Fingerprint != current.Quote!.Fingerprint || confirmation.Fingerprint != current.Quote.Fingerprint)
                return new GenerationError(GenerationErrorCode.InvalidRequest, "Quote inputs changed; obtain and confirm a new quote.", false, "quote_fingerprint", "quote_stale");
            if (confirmation.MaxEstimatedCostUsd < current.Quote.MaximumEstimatedCostUsd)
                return new GenerationError(GenerationErrorCode.InvalidRequest, "Estimated cost exceeds the confirmed upper bound.", false, "max_estimated_cost_usd", "cost_cap_exceeded");
            return null;
        }
        public static GenerationError ConfirmationRequired() => new(GenerationErrorCode.InvalidRequest,
            "Configured fal work requires a fresh quote fingerprint and numeric cost cap.", false, "quote_fingerprint", "quote_confirmation_required");
    }

    public sealed class FalQuoteResult
    {
        public FalQuote? Quote { get; }
        public GenerationError? Error { get; }
        public bool Success => Quote != null && Error == null;
        private FalQuoteResult(FalQuote? quote, GenerationError? error) { Quote = quote; Error = error; }
        internal static FalQuoteResult Ok(FalQuote quote) => new(quote, null);
        internal static FalQuoteResult Fail(GenerationError error) => new(null, error);
    }
}
