using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageSourcePayload
    {
        public const long MaxRawBytes = 1024 * 1024;

        private ReplicateImageSourcePayload(string mimeType, string dataUri)
        {
            MimeType = mimeType;
            DataUri = dataUri;
        }

        public string MimeType { get; }
        public string DataUri { get; }

        public static (ReplicateImageSourcePayload? Payload, GenerationError? Error) FromResolvedMedia(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (media is null)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro requires exactly one source image.",
                    "input_image_path"));
            }

            if (media.Keys.Any(r => string.Equals(
                    r.Role,
                    ImageMediaRoles.ReferenceImage,
                    StringComparison.Ordinal)))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro does not support reference_image_paths in this release.",
                    "reference_image_paths"));
            }

            var inputs = media
                .Where(kvp => string.Equals(
                    kvp.Key.Role,
                    ImageMediaRoles.InputImage,
                    StringComparison.Ordinal))
                .ToArray();

            if (inputs.Length != 1)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro requires exactly one source image.",
                    "input_image_path"));
            }

            var resolved = inputs[0].Value;
            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image is empty.",
                    "input_image_path"));
            }

            if (resolved.Bytes.LongLength > MaxRawBytes)
            {
                return (null, InvalidSource(
                    "Source image is too large for Flux 2 Pro data URI upload; capture a smaller viewport or lower resolution.",
                    "input_image_path"));
            }

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsFlux2SupportedMime(detectedMime))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image must be PNG, JPEG, or WebP.",
                    "input_image_path"));
            }

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Flux 2 Pro source image MIME does not match its bytes.",
                    "input_image_path"));
            }

            var dataUri = $"data:{detectedMime};base64,{Convert.ToBase64String(resolved.Bytes)}";
            return (new ReplicateImageSourcePayload(detectedMime, dataUri), null);
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);
    }
}
