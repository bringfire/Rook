using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Envelope returned by
    /// <see cref="IPricingModel{TRequest, TCapability}.Estimate"/>.
    /// Failure surfaces as a typed <see cref="GenerationError"/> (e.g.
    /// the requested resolution has no published rate); the cost
    /// estimator wraps this into the modality-specific result type at
    /// the call site without recomputing.
    /// </summary>
    public sealed record PricingResult
    {
        public JobPricing? Pricing { get; }
        public CostEstimate? Estimate { get; }
        public GenerationError? Error { get; }

        public bool Success => Error is null && Pricing is not null && Estimate is not null;

        private PricingResult(
            JobPricing? pricing, CostEstimate? estimate, GenerationError? error)
        {
            Pricing = pricing;
            Estimate = estimate;
            Error = error;
        }

        public static PricingResult Ok(JobPricing pricing, CostEstimate estimate)
        {
            if (pricing is null) throw new ArgumentNullException(nameof(pricing));
            if (estimate is null) throw new ArgumentNullException(nameof(estimate));
            return new PricingResult(pricing, estimate, error: null);
        }

        public static PricingResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new PricingResult(pricing: null, estimate: null, error);
        }
    }
}
