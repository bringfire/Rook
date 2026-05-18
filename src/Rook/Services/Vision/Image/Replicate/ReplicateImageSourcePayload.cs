using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageSourcePayload
    {
        private ReplicateImageSourcePayload(IReadOnlyList<ResolvedFlux2InputImage> inputImages)
        {
            InputImages = inputImages;
        }

        public IReadOnlyList<ResolvedFlux2InputImage> InputImages { get; }

        public static (ReplicateImageSourcePayload? Payload, GenerationError? Error) FromResolvedMedia(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            var mediaItems = media ?? new Dictionary<MediaRef, ResolvedMedia>();
            var hasPrompt = !string.IsNullOrWhiteSpace(request?.Prompt);

            if (mediaItems.Keys.Any(r => string.Equals(
                    r.Role,
                    ImageMediaRoles.ReferenceImage,
                    StringComparison.Ordinal)))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro does not support reference_image_paths in this release.",
                    "reference_image_paths"));
            }

            var inputs = mediaItems
                .Where(kvp => string.Equals(
                    kvp.Key.Role,
                    ImageMediaRoles.InputImage,
                    StringComparison.Ordinal))
                .ToArray();

            if (inputs.Length == 0)
            {
                var promptOnlyValidation = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                    mediaCount: 0,
                    aggregatePixels: 0,
                    hasPrompt: hasPrompt);
                if (!promptOnlyValidation.Success)
                    return (null, InvalidSource(
                        promptOnlyValidation.Message ?? "Flux 2 Pro request is invalid.",
                        promptOnlyValidation.Field ?? "input_images"));

                return (new ReplicateImageSourcePayload(
                    new ReadOnlyCollection<ResolvedFlux2InputImage>(
                        Array.Empty<ResolvedFlux2InputImage>())), null);
            }

            if (inputs.Length > 1)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro supports only one primary source image in this release.",
                    "input_image_path"));
            }

            var resolved = inputs[0].Value;
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image is empty.",
                    "input_image_path"));
            }

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ReplicateImageCapabilities.Flux2ProMediaPolicy.Model.AllowedMimeTypes.Contains(
                    detectedMime,
                    StringComparer.Ordinal))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image must be PNG, JPEG, GIF, or WebP.",
                    "input_image_path"));
            }

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image MIME does not match its bytes.",
                    "input_image_path"));
            }

            if (!ImageDimensions.TryRead(resolved.Bytes, detectedMime, out var dimensions))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image dimensions could not be read safely.",
                    "input_image_path"));
            }

            var validation = ReplicateImageCapabilities.Flux2ProMediaPolicy.ValidateInputSet(
                mediaCount: inputs.Length,
                aggregatePixels: dimensions.PixelCount,
                hasPrompt: hasPrompt);
            if (!validation.Success)
            {
                return (null, InvalidSource(
                    validation.Message ?? "Flux 2 Pro source image is invalid.",
                    validation.Field == "input_images"
                        ? "input_image_path"
                        : validation.Field ?? "input_image_path"));
            }

            return (new ReplicateImageSourcePayload(
                new ReadOnlyCollection<ResolvedFlux2InputImage>(
                    new[]
                    {
                        new ResolvedFlux2InputImage(
                            resolved.Bytes,
                            detectedMime,
                            dimensions),
                    })), null);
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);
    }

    internal sealed class ResolvedFlux2InputImage
    {
        public ResolvedFlux2InputImage(
            byte[] bytes,
            string mimeType,
            ImageDimensions dimensions)
        {
            Bytes = bytes ?? throw new ArgumentNullException(nameof(bytes));
            if (string.IsNullOrWhiteSpace(mimeType))
                throw new ArgumentException("MIME type must be non-empty.", nameof(mimeType));

            MimeType = mimeType;
            Dimensions = dimensions;
        }

        public byte[] Bytes { get; }

        public string MimeType { get; }

        public ImageDimensions Dimensions { get; }
    }
}
