using System.Collections.Generic;
using System.Linq;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Provider-neutral request-shape validation against a resolved
    /// <see cref="ModelCapability"/>. Lifted from V1b's
    /// <c>VideoCapabilities.Validate</c> minus the model-existence check
    /// (now owned by <see cref="IVideoProviderRegistry.TryResolve"/>) and
    /// minus provider-specific rules (now owned by per-provider
    /// <see cref="IProviderOptionsCodec.Validate"/>, e.g. Veo's
    /// PersonGeneration matrix in <see cref="VeoOptionsCodec"/>).
    ///
    /// Caller passes the cap already obtained from
    /// <see cref="ResolvedVideoModel.Capability"/>; this validator never
    /// re-resolves models.
    /// </summary>
    public static class CapabilityValidator
    {
        public static ValidationResult Validate(
            ModelCapability cap, VideoGenerationRequest request)
        {
            if (request is null)
                return ValidationResult.Fail(nameof(request), "Request is null.");

            if (cap is null)
                return ValidationResult.Fail(nameof(cap), "Capability is null.");

            if (request.NumberOfVideos != 1)
                return ValidationResult.Fail(
                    nameof(request.NumberOfVideos),
                    $"NumberOfVideos must be 1 for v1; got {request.NumberOfVideos}.");

            if (!cap.Modes.Contains(request.Mode))
                return ValidationResult.Fail(
                    nameof(request.Mode),
                    $"{cap.Name} does not support mode {request.Mode}.");

            // Required inputs per mode
            if (request.Mode == VideoMode.T2V && string.IsNullOrWhiteSpace(request.Prompt))
                return ValidationResult.Fail(
                    nameof(request.Prompt),
                    "Text-to-video requires a prompt.");

            if (request.Mode == VideoMode.I2V && request.StartFrame is null)
                return ValidationResult.Fail(
                    nameof(request.StartFrame),
                    "Image-to-video requires a start frame.");

            if (request.Mode == VideoMode.Interp)
            {
                if (request.StartFrame is null)
                    return ValidationResult.Fail(
                        nameof(request.StartFrame),
                        "Interpolation requires a start frame.");
                if (request.EndFrame is null)
                    return ValidationResult.Fail(
                        nameof(request.EndFrame),
                        "Interpolation requires an end frame.");
            }

            if (!cap.Resolutions.Contains(request.Resolution))
                return ValidationResult.Fail(
                    nameof(request.Resolution),
                    $"{cap.Name} does not support resolution '{request.Resolution}'. " +
                    $"Supported: {string.Join(", ", cap.Resolutions)}.");

            if (!cap.Durations.Contains(request.DurationSeconds))
                return ValidationResult.Fail(
                    nameof(request.DurationSeconds),
                    $"{cap.Name} does not support duration {request.DurationSeconds}s. " +
                    $"Supported: {string.Join(", ", cap.Durations)}s.");

            if (!cap.AspectRatios.Contains(request.AspectRatio))
                return ValidationResult.Fail(
                    nameof(request.AspectRatio),
                    $"{cap.Name} does not support aspect ratio '{request.AspectRatio}'. " +
                    $"Supported: {string.Join(", ", cap.AspectRatios)}.");

            // Reference image gating
            var refCount = request.ReferenceFrames?.Count ?? 0;
            if (refCount > 0)
            {
                if (!cap.SupportsReferenceImages)
                    return ValidationResult.Fail(
                        nameof(request.ReferenceFrames),
                        $"{cap.Name} does not support reference images.");
                if (refCount > cap.MaxReferenceImages)
                    return ValidationResult.Fail(
                        nameof(request.ReferenceFrames),
                        $"{cap.Name} supports at most {cap.MaxReferenceImages} reference images; got {refCount}.");
            }

            // Must-8s coupling
            var triggers = new List<string>();
            if (cap.Must8sWith.Contains(request.Resolution))
                triggers.Add(request.Resolution);
            if (refCount > 0 && cap.Must8sWith.Contains("referenceImages"))
                triggers.Add("reference images");

            if (triggers.Count > 0 && request.DurationSeconds != 8)
                return ValidationResult.Fail(
                    nameof(request.DurationSeconds),
                    $"{cap.Name} requires 8s duration when using {string.Join(", ", triggers)}.");

            return ValidationResult.Ok();
        }
    }
}
