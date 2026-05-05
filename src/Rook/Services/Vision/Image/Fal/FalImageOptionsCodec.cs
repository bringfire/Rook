using System;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalImageOptionsCodec
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
            if (options is not FalImageOptions)
                return ValidationResult.Fail(
                    $"fal image provider requires {nameof(FalImageOptions)}; got " +
                    $"{options?.GetType().Name ?? "null"}.",
                    "options");
            if (request.NumberOfImages != 1)
                return ValidationResult.Fail(
                    "number_of_images must be 1 for fal image generation.",
                    "number_of_images");

            if (string.Equals(
                    capability.Id,
                    FalImageCapabilities.GptImage2Edit,
                    StringComparison.Ordinal))
            {
                return ValidateGptImage2Edit(request);
            }

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
                    "reference_image_paths are not supported for fal Flux Schnell.",
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

        private static ValidationResult ValidateGptImage2Edit(
            ImageGenerationRequest request)
        {
            var resolution = string.IsNullOrWhiteSpace(request.Resolution)
                ? "auto"
                : request.Resolution.Trim();
            if (!string.Equals(
                    resolution,
                    "auto",
                    StringComparison.OrdinalIgnoreCase))
            {
                return ValidationResult.Fail(
                    "resolution must be auto for GPT Image 2 Edit.",
                    "resolution");
            }

            if (!string.IsNullOrWhiteSpace(request.AspectRatio)
                && !string.Equals(
                    request.AspectRatio,
                    "match_input_image",
                    StringComparison.Ordinal))
            {
                return ValidationResult.Fail(
                    "aspect_ratio must be match_input_image for GPT Image 2 Edit.",
                    "aspect_ratio");
            }

            if ((request.ReferenceImages?.Count ?? 0) > 0)
            {
                return ValidationResult.Fail(
                    "reference_image_paths are not supported for GPT Image 2 Edit.",
                    "reference_image_paths");
            }

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not FalImageOptions)
                throw new ArgumentException(
                    $"Expected {nameof(FalImageOptions)}.", nameof(options));
            return new JsonObject();
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "fal image options JSON is null.",
                    Retryable: false,
                    Field: "options"));

            if (json.Count != 0)
                return ProviderOptionsDecodeResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "fal image options do not accept provider-specific fields.",
                    Retryable: false,
                    Field: "options"));

            return ProviderOptionsDecodeResult.Ok(new FalImageOptions());
        }

        internal static string ToFalImageSize(string? aspectRatio)
        {
            if (string.IsNullOrWhiteSpace(aspectRatio))
                return "landscape_4_3";

            return aspectRatio switch
            {
                "1:1" => "square_hd",
                "4:3" => "landscape_4_3",
                "3:4" => "portrait_4_3",
                "16:9" => "landscape_16_9",
                "9:16" => "portrait_16_9",
                _ => throw new ArgumentException(
                    $"Unsupported fal image aspect ratio '{aspectRatio}'.",
                    nameof(aspectRatio)),
            };
        }
    }
}
