using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Gemini
{
    public sealed class GeminiImageOptionsCodec
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
            if (options is not GeminiImageOptions)
                return ValidationResult.Fail(
                    $"Gemini image provider requires {nameof(GeminiImageOptions)}; got " +
                    $"{options?.GetType().Name ?? "null"}.",
                    "options");
            if (request.NumberOfImages != 1)
                return ValidationResult.Fail(
                    "number_of_images must be 1 for Gemini image generation.",
                    "number_of_images");

            var resolution = string.IsNullOrWhiteSpace(request.Resolution)
                ? "1K"
                : request.Resolution.ToUpperInvariant();
            if (!capability.Resolutions.Contains(resolution, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    $"resolution must be one of: {string.Join(", ", capability.Resolutions)} " +
                    $"for model '{GeminiImageCapabilities.ShortNameForMessage(capability.Id)}'.",
                    "resolution");
            }

            if (!string.IsNullOrWhiteSpace(request.AspectRatio)
                && !capability.AspectRatios.Contains(request.AspectRatio, StringComparer.Ordinal))
            {
                return ValidationResult.Fail(
                    "aspect_ratio must be one of: " +
                    string.Join(", ", capability.AspectRatios) + ".",
                    "aspect_ratio");
            }

            var refCount = request.ReferenceImages?.Count ?? 0;
            if (refCount > capability.MaxReferenceImages)
            {
                return ValidationResult.Fail(
                    $"reference_image_paths exceeds the limit of {capability.MaxReferenceImages}.",
                    "reference_image_paths");
            }

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not GeminiImageOptions)
                throw new ArgumentException(
                    $"Expected {nameof(GeminiImageOptions)}.", nameof(options));
            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Gemini image options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            if (json.Count != 0)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Gemini image options do not accept provider-specific fields.",
                    Retryable: false,
                    Field: "options"));

            return ProviderOptionsDecodeResult.Ok(new GeminiImageOptions());
        }
    }
}
