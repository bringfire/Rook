using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Provider-neutral orchestrator for validation + pricing. V1c:
    /// renamed from V1b's <c>VeoCostEstimator</c>. Stateless; the
    /// resolved model carries all per-provider state (capability,
    /// pricing model, options codec).
    ///
    /// Order of operations on each <see cref="Estimate"/> call:
    /// <list type="number">
    ///   <item><description>Provider-neutral capability validation (<see cref="CapabilityValidator"/>).</description></item>
    ///   <item><description>Provider-specific options validation (<see cref="IProviderOptionsCodec.Validate"/>).</description></item>
    ///   <item><description>Pricing (<see cref="IPricingModel.Estimate"/>) — runs exactly once.</description></item>
    /// </list>
    /// The resulting <see cref="JobPricing"/> snapshot rides inside the
    /// returned <see cref="VideoCostEstimate.Pricing"/> for verbatim
    /// downstream copy by <see cref="VideoJobRecordFactory"/>.
    /// </summary>
    public sealed class VideoCostEstimator : IVideoCostEstimator
    {
        public VideoCostEstimateResult Estimate(
            ResolvedVideoModel model,
            VideoGenerationRequest request)
        {
            if (model is null)
                return Fail(VideoErrorCode.InvalidRequest,
                    "Resolved model is null.", nameof(model));

            if (request is null)
                return Fail(VideoErrorCode.InvalidRequest,
                    "Request is null.", nameof(request));

            // Step 1: capability validation (provider-neutral)
            var capResult = CapabilityValidator.Validate(model.Capability, request);
            if (!capResult.Success)
                return Fail(
                    ClassifyValidationFailure(capResult.Field),
                    capResult.Message ?? "Validation failed.",
                    capResult.Field);

            // Step 2: options validation (provider-specific via codec)
            var optResult = model.OptionsCodec.Validate(
                request, request.Options, model.Capability);
            if (!optResult.Success)
                return Fail(
                    ClassifyValidationFailure(optResult.Field),
                    optResult.Message ?? "Options validation failed.",
                    optResult.Field);

            // Step 3: pricing (single-pass — JobPricing snapshot rides
            // through to the factory and into the ledger record verbatim)
            var pricingResult = model.PricingModel.Estimate(request, model.Capability);
            if (!pricingResult.Success)
                return VideoCostEstimateResult.Fail(pricingResult.Error!);

            var pricing = pricingResult.Pricing!;
            var breakdown = BuildBreakdown(model.Capability, request, pricing);

            return VideoCostEstimateResult.Ok(new VideoCostEstimate(
                DollarsUsd: pricing.TotalUsd ?? 0m,
                Model: request.Model,
                Resolution: request.Resolution,
                DurationSeconds: request.DurationSeconds,
                NumberOfVideos: request.NumberOfVideos,
                Breakdown: breakdown,
                Pricing: pricing));
        }

        // Build the UI-facing breakdown rows. Per-video line uses the
        // pricing-model's UnitPriceUsd × duration; multi-video line is the
        // remainder. Mirrors V1b's VeoCostEstimator output shape so
        // existing UI consumers see identical rows.
        private static IReadOnlyList<CostBreakdownComponent> BuildBreakdown(
            ModelCapability cap, VideoGenerationRequest request, JobPricing pricing)
        {
            var perVideoCost = pricing.UnitPriceUsd.HasValue
                ? pricing.UnitPriceUsd.Value * request.DurationSeconds
                : 0m;

            var breakdown = new List<CostBreakdownComponent>
            {
                new(
                    Label: $"{cap.Name} @ {request.Resolution} × {request.DurationSeconds}s",
                    DollarsUsd: perVideoCost),
            };

            if (request.NumberOfVideos != 1)
            {
                var remainder = (pricing.TotalUsd ?? 0m) - perVideoCost;
                breakdown.Add(new CostBreakdownComponent(
                    Label: $"× {request.NumberOfVideos} videos",
                    DollarsUsd: remainder));
            }

            return breakdown;
        }

        // Map validation failure fields onto typed VideoErrorCode values.
        // Capability-shape mismatches and Veo PersonGeneration matrix
        // failures are UnsupportedMedia (capability mismatch); everything
        // else (including null request, null options, codec
        // type-mismatch) is InvalidRequest (caller-shaped).
        private static VideoErrorCode ClassifyValidationFailure(string? field)
        {
            if (string.IsNullOrEmpty(field))
                return VideoErrorCode.InvalidRequest;

            return field switch
            {
                "Resolution" or "DurationSeconds" or "AspectRatio"
                    or "Mode" or "ReferenceFrames" or "NumberOfVideos"
                    or nameof(VeoOptions.PersonGeneration)
                    => VideoErrorCode.UnsupportedMedia,
                _ => VideoErrorCode.InvalidRequest,
            };
        }

        private static VideoCostEstimateResult Fail(
            VideoErrorCode code, string message, string? field) =>
            VideoCostEstimateResult.Fail(new VideoJobError(
                Code: code,
                Message: message,
                Retryable: false,
                Field: field));
    }
}
