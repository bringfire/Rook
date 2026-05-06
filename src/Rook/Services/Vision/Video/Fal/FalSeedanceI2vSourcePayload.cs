using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSeedanceI2vSourcePayload
    {
        public const long MaxRawBytes = 1024 * 1024;

        private FalSeedanceI2vSourcePayload(string imageUrl, string? endImageUrl)
        {
            ImageUrl = imageUrl;
            EndImageUrl = endImageUrl;
        }

        public string ImageUrl { get; }
        public string? EndImageUrl { get; }

        public static (
            FalSeedanceI2vSourcePayload? Payload,
            GenerationError? Error) FromResolvedMedia(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request is null)
                return (null, InvalidSource(
                    "Seedance source payload requires a request.",
                    "request"));

            if (media is null)
                return (null, InvalidSource(
                    "Seedance source payload requires resolved media.",
                    "media"));

            if (request.Mode != VideoMode.I2V && request.Mode != VideoMode.Interp)
                return (null, InvalidSource(
                    "Seedance source payload only supports image-to-video and interpolation modes.",
                    "mode"));

            if (request.ReferenceFrames is { Count: > 0 })
                return (null, InvalidSource(
                    "Seedance source payload does not support reference frames.",
                    "reference_frames"));

            if (request.StartFrame is null)
                return (null, InvalidSource(
                    "Seedance source payload requires a start frame.",
                    "start_frame"));

            if (request.Mode == VideoMode.I2V && request.EndFrame is not null)
                return (null, InvalidSource(
                    "Seedance image-to-video source payload does not accept an end frame.",
                    "end_frame"));

            if (request.Mode == VideoMode.Interp && request.EndFrame is null)
                return (null, InvalidSource(
                    "Seedance interpolation source payload requires an end frame.",
                    "end_frame"));

            var start = ResolveDataUri(media, request.StartFrame, "start_frame");
            if (start.Error is not null)
                return (null, start.Error);

            string? endImageUrl = null;
            if (request.Mode == VideoMode.Interp)
            {
                var end = ResolveDataUri(media, request.EndFrame!, "end_frame");
                if (end.Error is not null)
                    return (null, end.Error);

                endImageUrl = end.DataUri;
            }

            return (new FalSeedanceI2vSourcePayload(start.DataUri!, endImageUrl), null);
        }

        private static (string? DataUri, GenerationError? Error) ResolveDataUri(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            MediaRef mediaRef,
            string field)
        {
            if (!media.TryGetValue(mediaRef, out var resolved) || resolved is null)
                return (null, InvalidSource(
                    "Seedance source frame was not resolved.",
                    field));

            if (resolved.Bytes is null || resolved.Bytes.Length == 0)
                return (null, InvalidSource(
                    "Seedance source frame is empty.",
                    field));

            if (resolved.Bytes.LongLength > MaxRawBytes)
                return (null, InvalidSource(
                    "Seedance source frame is too large for data URI upload; " +
                    "capture a smaller viewport or lower resolution.",
                    field));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsPngJpegOrWebp(detectedMime))
                return (null, InvalidSource(
                    "Seedance source frame must be PNG, JPEG, or WebP.",
                    field));

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(
                    resolved.MimeType,
                    detectedMime,
                    StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Seedance source frame MIME does not match its bytes.",
                    field));
            }

            return (
                $"data:{detectedMime};base64,{Convert.ToBase64String(resolved.Bytes)}",
                null);
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);
    }
}
