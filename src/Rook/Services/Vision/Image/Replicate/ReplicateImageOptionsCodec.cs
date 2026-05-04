using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageOptionsCodec
        : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
    {
        public ValidationResult Validate(
            ImageGenerationRequest request,
            ProviderOptions options,
            ImageCapability capability)
        {
            if (request is null)
                return ValidationResult.Fail("Request is null.", "request");
            if (capability is null)
                return ValidationResult.Fail("Capability is null.", "capability");
            if (options is not ReplicateImageOptions)
                return ValidationResult.Fail(
                    $"Replicate image provider requires {nameof(ReplicateImageOptions)}; got " +
                    $"{options?.GetType().Name ?? "null"}.",
                    "options");
            if (request.NumberOfImages != 1)
                return ValidationResult.Fail(
                    "number_of_images must be 1 for Replicate image generation.",
                    "number_of_images");

            var resolution = string.IsNullOrWhiteSpace(request.Resolution)
                ? "1K"
                : request.Resolution.ToUpperInvariant();
            if (!capability.Resolutions.Contains(resolution, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    $"resolution must be one of: {string.Join(", ", capability.Resolutions)} " +
                    $"for model '{capability.Id}'.",
                    "resolution");
            }

            var refCount = request.ReferenceImages?.Count ?? 0;
            if (refCount > 0)
            {
                return ValidationResult.Fail(
                    $"reference_image_paths are not supported for {capability.Name}.",
                    "reference_image_paths");
            }

            if (!string.IsNullOrWhiteSpace(request.AspectRatio)
                && !capability.AspectRatios.Contains(request.AspectRatio, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    "aspect_ratio must be one of: " +
                    string.Join(", ", capability.AspectRatios) + ".",
                    "aspect_ratio");
            }

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not ReplicateImageOptions)
                throw new ArgumentException(
                    $"Expected {nameof(ReplicateImageOptions)}.", nameof(options));
            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Replicate image options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            if (json.Count != 0)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Replicate image options do not accept provider-specific fields.",
                    Retryable: false,
                    Field: "options"));

            return ProviderOptionsDecodeResult.Ok(new ReplicateImageOptions());
        }
    }
}
