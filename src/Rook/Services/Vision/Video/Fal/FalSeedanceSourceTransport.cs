using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSeedanceSourceTransport : IFalSeedanceSourceTransport
    {
        public const long MaxSourceFrameBytes = 30L * 1024L * 1024L;
        public const int SourceMediaExpirationSeconds = 3600;

        private readonly FalApiClient _client;

        public FalSeedanceSourceTransport(FalApiClient client)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
        }

        public async Task<(FalSeedanceSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct)
        {
            var validationError = ValidateRequest(request, media);
            if (validationError is not null)
                return (null, validationError);

            var start = ResolveSourceFrame(media, request.StartFrame!, "start_frame");
            if (start.Error is not null)
                return (null, start.Error);

            SourceFrame? end = null;
            if (request.Mode == VideoMode.Interp)
            {
                var resolvedEnd = ResolveSourceFrame(media, request.EndFrame!, "end_frame");
                if (resolvedEnd.Error is not null)
                    return (null, resolvedEnd.Error);

                end = resolvedEnd.Frame;
            }

            try
            {
                var imageUrl = await UploadAsync(apiKey, start.Frame!, ct).ConfigureAwait(false);
                string? endImageUrl = null;
                if (end is not null)
                    endImageUrl = await UploadAsync(apiKey, end, ct).ConfigureAwait(false);

                return (new FalSeedanceSourceUrls(imageUrl, endImageUrl), null);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (FalApiException)
            {
                return (null, DependencyUnavailable());
            }
            catch (TaskCanceledException)
            {
                return (null, DependencyUnavailable());
            }
        }

        private static GenerationError? ValidateRequest(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request is null)
                return InvalidSource(
                    "Seedance source transport requires a request.",
                    "request");

            if (media is null)
                return InvalidSource(
                    "Seedance source transport requires resolved media.",
                    "media");

            if (request.Mode != VideoMode.I2V && request.Mode != VideoMode.Interp)
                return InvalidSource(
                    "Seedance source transport only supports image-to-video and interpolation modes.",
                    "mode");

            if (request.ReferenceFrames is { Count: > 0 })
                return InvalidSource(
                    "Seedance source transport does not support reference frames.",
                    "reference_frames");

            if (request.StartFrame is null)
                return InvalidSource(
                    "Seedance source transport requires a start frame.",
                    "start_frame");

            if (request.Mode == VideoMode.I2V && request.EndFrame is not null)
                return InvalidSource(
                    "Seedance image-to-video source transport does not accept an end frame.",
                    "end_frame");

            if (request.Mode == VideoMode.Interp && request.EndFrame is null)
                return InvalidSource(
                    "Seedance interpolation source transport requires an end frame.",
                    "end_frame");

            return null;
        }

        private static (SourceFrame? Frame, GenerationError? Error) ResolveSourceFrame(
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            MediaRef mediaRef,
            string field)
        {
            if (!media.TryGetValue(mediaRef, out var resolved) || resolved is null)
                return (null, InvalidSource(
                    "Seedance source frame was not resolved.",
                    field));

            if (resolved.Bytes.LongLength > MaxSourceFrameBytes)
                return (null, InvalidSource(
                    "Seedance source frame is too large for fal source upload; " +
                    "capture a smaller viewport or lower resolution.",
                    field));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!ImageMimeDetector.IsPngJpegOrWebp(detectedMime))
                return (null, InvalidSource(
                    "Seedance source frame must be PNG, JPEG, or WebP.",
                    field));

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    "Seedance source frame MIME does not match its bytes.",
                    field));
            }

            return (new SourceFrame(resolved.Bytes, detectedMime), null);
        }

        private Task<string> UploadAsync(
            string apiKey,
            SourceFrame frame,
            CancellationToken ct) =>
            _client.UploadFileToCdnAsync(
                apiKey,
                BuildFileName(frame.MimeType),
                frame.Bytes,
                frame.MimeType,
                FalUploadPlatformHeaders.ForSourceUpload(SourceMediaExpirationSeconds),
                ct);

        private static string BuildFileName(string mimeType) =>
            $"rook-seedance-source-{Guid.NewGuid():N}.{ExtensionForMime(mimeType)}";

        private static string ExtensionForMime(string mimeType) =>
            mimeType switch
            {
                "image/png" => "png",
                "image/jpeg" => "jpg",
                "image/webp" => "webp",
                _ => throw new ArgumentOutOfRangeException(nameof(mimeType)),
            };

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);

        private static GenerationError DependencyUnavailable() =>
            new(
                Code: GenerationErrorCode.DependencyUnavailable,
                Message: "fal Seedance source upload failed.",
                Retryable: true);

        private sealed class SourceFrame
        {
            public SourceFrame(byte[] bytes, string mimeType)
            {
                Bytes = bytes;
                MimeType = mimeType;
            }

            public byte[] Bytes { get; }
            public string MimeType { get; }
        }
    }
}
