using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Single-pass orchestration of capability validation, options
    /// validation, and pricing. <see cref="IPricingModel.Estimate"/> is
    /// invoked exactly once per <see cref="Estimate"/> call; the
    /// resulting <see cref="JobPricing"/> rides inside
    /// <see cref="VideoCostEstimate.Pricing"/> for verbatim downstream
    /// copy by <see cref="VideoJobRecordFactory"/>. The factory must
    /// not recompute — drift here breaks the audit-snapshot contract.
    /// </summary>
    public sealed class VideoCostEstimator : IVideoCostEstimator
    {
        public VideoCostEstimateResult Estimate(
            ResolvedVideoModel model,
            VideoGenerationRequest request)
        {
            if (model is null)
                return Fail(VideoErrorCode.InvalidRequest,
                    "Resolved model is null.", "Model");

            if (request is null)
                return Fail(VideoErrorCode.InvalidRequest,
                    "Request is null.", "Request");

            // M4: fail typed early on null Options at the manager/estimator
            // boundary rather than relying on the codec to catch it.
            if (request.Options is null)
                return Fail(VideoErrorCode.InvalidRequest,
                    "Request.Options must be non-null.",
                    nameof(VideoGenerationRequest.Options));

            // F2 (review pass 2): the public estimator seam accepts
            // ResolvedVideoModel and VideoGenerationRequest as separate
            // arguments. The manager's SubmitAsync resolves them
            // together via registry, but a direct caller (test, future
            // route handler) could pair model A's ResolvedVideoModel
            // with model B's request and the estimator would silently
            // validate/price against A while VideoCostEstimate.Model
            // reports B. Guard the consistency at the boundary.
            if (!string.Equals(request.Model, model.ModelId, StringComparison.Ordinal))
                return Fail(VideoErrorCode.InvalidRequest,
                    $"Resolved model id '{model.ModelId}' does not match " +
                    $"request.Model '{request.Model}'.",
                    nameof(VideoGenerationRequest.Model));

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
            var genericPricingResult = model.PricingModel.Estimate(request, model.Capability);
            var pricingResult = VideoJobPricingTranslator.ToVideoPricingResult(
                genericPricingResult,
                VideoJobPricingTranslator.PricingKindFor(model.PricingModel));
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

        // Build the UI-facing breakdown rows. Single-row output: the
        // pricing model already produced TotalUsd for the full request
        // (quantity × unit), so the breakdown just labels it. The N>1
        // case folds the multiplier into the label so the row's dollar
        // value is always the full TotalUsd — never a partial figure
        // that a UI could mis-render as the total.
        //
        // V1c review M1: the prior shape (per-video row + remainder row)
        // was unreachable today (CapabilityValidator rejects N!=1) and
        // had a misleading "× N videos" label whose dollar value was
        // (N-1) videos. Folding into one row eliminates the dead branch
        // and the labelling ambiguity.
        private static IReadOnlyList<CostBreakdownComponent> BuildBreakdown(
            VideoCapability cap, VideoGenerationRequest request, JobPricing pricing)
        {
            var label = request.NumberOfVideos == 1
                ? $"{cap.Name} @ {request.Resolution} × {request.DurationSeconds}s"
                : $"{cap.Name} @ {request.Resolution} × {request.DurationSeconds}s × {request.NumberOfVideos} videos";

            return new[]
            {
                new CostBreakdownComponent(
                    Label: label,
                    DollarsUsd: pricing.TotalUsd ?? 0m),
            };
        }

        // Map validation failure fields onto typed VideoErrorCode values.
        // Capability-shape mismatches and Veo PersonGeneration matrix
        // failures are UnsupportedMedia (capability mismatch); framework
        // shape failures (null request, null cap, null/mismatched options)
        // and unknown fields are InvalidRequest (caller-shaped).
        //
        // Cases are explicit (no fall-through reliance) so renaming a
        // validator parameter or swapping nameof targets cannot silently
        // change error classification.
        private static VideoErrorCode ClassifyValidationFailure(string? field)
        {
            if (string.IsNullOrEmpty(field))
                return VideoErrorCode.InvalidRequest;

            return field switch
            {
                // Capability-shape mismatches.
                nameof(VideoGenerationRequest.Resolution)
                    or nameof(VideoGenerationRequest.DurationSeconds)
                    or nameof(VideoGenerationRequest.AspectRatio)
                    or nameof(VideoGenerationRequest.Mode)
                    or nameof(VideoGenerationRequest.ReferenceFrames)
                    or nameof(VideoGenerationRequest.NumberOfVideos)
                    or nameof(VeoOptions.PersonGeneration)
                    => VideoErrorCode.UnsupportedMedia,

                // Framework-shape failures (null/mismatched inputs).
                "Request" or "Cap"
                    or nameof(VideoGenerationRequest.Model)
                    or nameof(VideoGenerationRequest.Options)
                    or nameof(VideoGenerationRequest.Prompt)
                    or nameof(VideoGenerationRequest.StartFrame)
                    or nameof(VideoGenerationRequest.EndFrame)
                    => VideoErrorCode.InvalidRequest,

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
