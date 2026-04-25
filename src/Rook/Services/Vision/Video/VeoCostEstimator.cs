using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Veo cost estimator. Validates the request against the injected
    /// capability catalog (fail-closed on unknown model / unsupported
    /// combination), then computes pricing as PricePerSecond × duration.
    /// NumberOfVideos &gt; 1 is rejected at validation, so this estimator
    /// only ever returns a single-video cost in v1; the breakdown
    /// preserves the multiplier explicitly so V1b can lift the limit
    /// without contract churn.
    /// </summary>
    public sealed class VeoCostEstimator : IVideoCostEstimator
    {
        private readonly IVideoCapabilityCatalog _catalog;

        public VeoCostEstimator(IVideoCapabilityCatalog catalog)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
        }

        public VideoCostEstimateResult Estimate(VideoGenerationRequest request)
        {
            if (request is null)
            {
                return VideoCostEstimateResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));
            }

            var validation = _catalog.Validate(request);
            if (!validation.Success)
            {
                return VideoCostEstimateResult.Fail(new VideoJobError(
                    Code: ClassifyValidationFailure(validation.Field, request),
                    Message: validation.Message ?? "Validation failed.",
                    Retryable: false,
                    Field: validation.Field));
            }

            // Validate() above guarantees model is known.
            _catalog.TryGetModel(request.Model, out var cap);

            if (!cap.PricePerSecondUsd.TryGetValue(request.Resolution, out var rate))
            {
                return VideoCostEstimateResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.UnsupportedMedia,
                    Message: $"{cap.Name} has no published price for resolution '{request.Resolution}'.",
                    Retryable: false,
                    Field: nameof(request.Resolution)));
            }

            var perVideoCost = rate * request.DurationSeconds;
            var totalCost = perVideoCost * request.NumberOfVideos;

            var breakdown = new List<CostBreakdownComponent>
            {
                new(
                    Label: $"{cap.Name} @ {request.Resolution} × {request.DurationSeconds}s",
                    DollarsUsd: perVideoCost),
            };

            if (request.NumberOfVideos != 1)
            {
                breakdown.Add(new CostBreakdownComponent(
                    Label: $"× {request.NumberOfVideos} videos",
                    DollarsUsd: totalCost - perVideoCost));
            }

            return VideoCostEstimateResult.Ok(new VideoCostEstimate(
                DollarsUsd: totalCost,
                Model: request.Model,
                Resolution: request.Resolution,
                DurationSeconds: request.DurationSeconds,
                NumberOfVideos: request.NumberOfVideos,
                Breakdown: breakdown));
        }

        // Map validation failure fields onto typed VideoErrorCode values.
        // The catalog returns ValidationResult; the estimator owns the
        // mapping from "what failed" to "which D3 error code surfaces."
        // Unknown-model and missing-required-input are InvalidRequest
        // (caller-shaped); resolution/duration/aspect/mode mismatches
        // and reference-image overruns are UnsupportedMedia (capability
        // shape mismatch). NumberOfVideos > 1 is UnsupportedMedia in v1
        // because the limit is a v1 policy, not a per-call invariant.
        private static VideoErrorCode ClassifyValidationFailure(
            string? field, VideoGenerationRequest request)
        {
            if (field is null) return VideoErrorCode.InvalidRequest;

            return field switch
            {
                nameof(request.Resolution) => VideoErrorCode.UnsupportedMedia,
                nameof(request.DurationSeconds) => VideoErrorCode.UnsupportedMedia,
                nameof(request.AspectRatio) => VideoErrorCode.UnsupportedMedia,
                nameof(request.Mode) => VideoErrorCode.UnsupportedMedia,
                nameof(request.ReferenceFrames) => VideoErrorCode.UnsupportedMedia,
                nameof(request.NumberOfVideos) => VideoErrorCode.UnsupportedMedia,
                nameof(request.PersonGeneration) => VideoErrorCode.UnsupportedMedia,
                _ => VideoErrorCode.InvalidRequest,
            };
        }
    }
}
