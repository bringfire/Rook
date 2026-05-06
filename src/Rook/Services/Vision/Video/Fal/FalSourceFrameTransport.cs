using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSourceFrameTransport : IFalSourceFrameTransport
    {
        public const int SourceMediaExpirationSeconds = 3600;

        private readonly FalApiClient _client;

        public FalSourceFrameTransport(FalApiClient client)
        {
            _client = client ?? throw new ArgumentNullException(nameof(client));
        }

        public async Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            FalSourceFramePolicy policy,
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct)
        {
            if (policy is null)
                throw new ArgumentNullException(nameof(policy));

            var validationError = ValidateRequest(policy, request, media);
            if (validationError is not null)
                return (null, validationError);

            var start = ResolveSourceFrame(policy, media, request.StartFrame!, "start_frame");
            if (start.Error is not null)
                return (null, start.Error);

            SourceFrame? end = null;
            if (request.Mode == VideoMode.Interp)
            {
                var resolvedEnd = ResolveSourceFrame(policy, media, request.EndFrame!, "end_frame");
                if (resolvedEnd.Error is not null)
                    return (null, resolvedEnd.Error);

                end = resolvedEnd.Frame;
            }

            var startUpload = await TryUploadAsync(
                apiKey,
                policy,
                start.Frame!,
                "start_frame",
                ct).ConfigureAwait(false);
            if (startUpload.Error is not null)
                return (null, startUpload.Error);

            string? endImageUrl = null;
            if (end is not null)
            {
                var endUpload = await TryUploadAsync(
                    apiKey,
                    policy,
                    end,
                    "end_frame",
                    ct).ConfigureAwait(false);
                if (endUpload.Error is not null)
                    return (null, endUpload.Error);

                endImageUrl = endUpload.Url;
            }

            return (new FalSourceFrameUrls(startUpload.Url!, endImageUrl), null);
        }

        private static GenerationError? ValidateRequest(
            FalSourceFramePolicy policy,
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            if (request is null)
                return InvalidSource(
                    $"{policy.ModelLabel} source transport requires a request.",
                    "request");

            if (media is null)
                return InvalidSource(
                    $"{policy.ModelLabel} source transport requires resolved media.",
                    "media");

            if (!IsAllowedMode(policy, request.Mode))
                return InvalidSource(
                    $"{policy.ModelLabel} source transport does not support this video mode.",
                    "mode");

            if (request.ReferenceFrames is { Count: > 0 })
                return InvalidSource(
                    $"{policy.ModelLabel} source transport does not support reference frames.",
                    "reference_frames");

            if (request.StartFrame is null)
                return InvalidSource(
                    $"{policy.ModelLabel} source transport requires a start frame.",
                    "start_frame");

            if (request.Mode == VideoMode.I2V
                && policy.RejectEndFrameForI2v
                && request.EndFrame is not null)
            {
                return InvalidSource(
                    $"{policy.ModelLabel} image-to-video source transport does not accept an end frame.",
                    "end_frame");
            }

            if (request.Mode == VideoMode.Interp && request.EndFrame is null)
                return InvalidSource(
                    $"{policy.ModelLabel} interpolation source transport requires an end frame.",
                    "end_frame");

            return null;
        }

        private static (SourceFrame? Frame, GenerationError? Error) ResolveSourceFrame(
            FalSourceFramePolicy policy,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            MediaRef mediaRef,
            string field)
        {
            if (!media.TryGetValue(mediaRef, out var resolved) || resolved is null)
                return (null, InvalidSource(
                    $"{policy.ModelLabel} source frame was not resolved.",
                    field));

            if (resolved.Bytes.LongLength > policy.MaxSourceFrameBytes)
                return (null, InvalidSource(
                    $"{policy.ModelLabel} source frame is too large for fal source upload; " +
                    "capture a smaller viewport or lower resolution.",
                    field));

            var detectedMime = ImageMimeDetector.Detect(resolved.Bytes);
            if (!IsAllowedMimeType(policy, detectedMime))
                return (null, InvalidSource(
                    $"{policy.ModelLabel} source frame must be an allowed image MIME type.",
                    field));

            if (!string.IsNullOrWhiteSpace(resolved.MimeType)
                && !string.Equals(resolved.MimeType, detectedMime, StringComparison.Ordinal))
            {
                return (null, InvalidSource(
                    $"{policy.ModelLabel} source frame MIME does not match its bytes.",
                    field));
            }

            return (new SourceFrame(resolved.Bytes, detectedMime), null);
        }

        private async Task<(string? Url, GenerationError? Error)> TryUploadAsync(
            string apiKey,
            FalSourceFramePolicy policy,
            SourceFrame frame,
            string field,
            CancellationToken ct)
        {
            try
            {
                return (await UploadAsync(apiKey, policy, frame, ct).ConfigureAwait(false), null);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (FalApiException)
            {
                return (null, DependencyUnavailable(policy, field));
            }
            catch (TaskCanceledException)
            {
                return (null, DependencyUnavailable(policy, field));
            }
        }

        private async Task<string> UploadAsync(
            string apiKey,
            FalSourceFramePolicy policy,
            SourceFrame frame,
            CancellationToken ct)
        {
            try
            {
                return await UploadOnceAsync(apiKey, policy, frame, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw;
            }
            catch (FalApiException)
            {
                return await UploadOnceAsync(apiKey, policy, frame, ct).ConfigureAwait(false);
            }
            catch (TaskCanceledException)
            {
                return await UploadOnceAsync(apiKey, policy, frame, ct).ConfigureAwait(false);
            }
        }

        private Task<string> UploadOnceAsync(
            string apiKey,
            FalSourceFramePolicy policy,
            SourceFrame frame,
            CancellationToken ct) =>
            _client.UploadFileToCdnAsync(
                apiKey,
                BuildFileName(policy, frame.MimeType),
                frame.Bytes,
                frame.MimeType,
                FalUploadPlatformHeaders.ForSourceUpload(SourceMediaExpirationSeconds),
                ct);

        private static string BuildFileName(FalSourceFramePolicy policy, string mimeType) =>
            $"{policy.FileNamePrefix}-{Guid.NewGuid():N}.{ExtensionForMime(mimeType)}";

        private static string ExtensionForMime(string mimeType) =>
            mimeType switch
            {
                "image/png" => "png",
                "image/jpeg" => "jpg",
                "image/webp" => "webp",
                _ => throw new ArgumentOutOfRangeException(nameof(mimeType)),
            };

        private static bool IsAllowedMode(FalSourceFramePolicy policy, VideoMode mode)
        {
            foreach (var allowedMode in policy.AllowedModes)
            {
                if (allowedMode == mode)
                    return true;
            }

            return false;
        }

        private static bool IsAllowedMimeType(FalSourceFramePolicy policy, string mimeType)
        {
            foreach (var allowedMimeType in policy.AllowedMimeTypes)
            {
                if (string.Equals(allowedMimeType, mimeType, StringComparison.Ordinal))
                    return true;
            }

            return false;
        }

        private static GenerationError InvalidSource(string message, string field) =>
            new(
                Code: GenerationErrorCode.InvalidRequest,
                Message: message,
                Retryable: false,
                Field: field);

        private static GenerationError DependencyUnavailable(
            FalSourceFramePolicy policy,
            string field) =>
            new(
                Code: GenerationErrorCode.DependencyUnavailable,
                Message: $"fal {policy.ModelLabel} source upload failed.",
                Retryable: true,
                Field: field);

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
