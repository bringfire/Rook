using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal static class VideoProviderOutcomeAdapters
    {
        public static MediaRef ToGenerationMediaRef(VideoMediaRef mediaRef)
        {
            if (mediaRef is null) throw new ArgumentNullException(nameof(mediaRef));

            return mediaRef.Kind switch
            {
                VideoMediaRefKind.Artifact => MediaRef.ForArtifact(
                    mediaRef.ArtifactId ?? Guid.Empty,
                    mediaRef.Role),
                VideoMediaRefKind.Path => MediaRef.ForPath(
                    mediaRef.Path ?? string.Empty,
                    mediaRef.Role),
                _ => throw new ArgumentOutOfRangeException(
                    nameof(mediaRef), mediaRef.Kind, "Unknown video media ref kind."),
            };
        }

        public static VideoMediaRef ToVideoMediaRef(MediaRef mediaRef)
        {
            if (mediaRef is null) throw new ArgumentNullException(nameof(mediaRef));

            return mediaRef.Kind switch
            {
                MediaRefKind.Artifact => VideoMediaRef.ForArtifact(
                    mediaRef.ArtifactId ?? Guid.Empty,
                    mediaRef.Role),
                MediaRefKind.Path => VideoMediaRef.ForPath(
                    mediaRef.Path ?? string.Empty,
                    mediaRef.Role),
                _ => throw new ArgumentOutOfRangeException(
                    nameof(mediaRef), mediaRef.Kind, "Unknown generation media ref kind."),
            };
        }

        public static IReadOnlyDictionary<MediaRef, ResolvedMedia> ToGenerationMedia(
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia>? media)
        {
            if (media is null || media.Count == 0)
                return new Dictionary<MediaRef, ResolvedMedia>();

            var converted = new Dictionary<MediaRef, ResolvedMedia>(media.Count);
            foreach (var kvp in media)
            {
                converted[ToGenerationMediaRef(kvp.Key)] =
                    new ResolvedMedia(kvp.Value.Bytes, kvp.Value.MimeType);
            }

            return converted;
        }

        public static IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> ToVideoMedia(
            IReadOnlyDictionary<MediaRef, ResolvedMedia>? media)
        {
            if (media is null || media.Count == 0)
                return new Dictionary<VideoMediaRef, ResolvedVideoMedia>();

            var converted = new Dictionary<VideoMediaRef, ResolvedVideoMedia>(media.Count);
            foreach (var kvp in media)
            {
                var videoRef = ToVideoMediaRef(kvp.Key);
                converted[videoRef] = new ResolvedVideoMedia(
                    kvp.Value.Bytes,
                    kvp.Value.MimeType,
                    SourceDescription(videoRef));
            }

            return converted;
        }

        public static GenerationError ToGenerationError(VideoJobError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));

            var providerDetail = string.IsNullOrEmpty(error.ProviderMessage)
                ? null
                : new Dictionary<string, JsonNode>
                {
                    [VideoErrorDetailKeys.ProviderMessage] =
                        JsonValue.Create(error.ProviderMessage)!,
                };

            return new GenerationError(
                ToGenerationErrorCode(error.Code),
                error.Message,
                error.Retryable,
                error.Field,
                ProviderErrorCode: null,
                ProviderDetail: providerDetail);
        }

        public static VideoJobError ToVideoJobError(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));

            var providerMessage = TryGetProviderMessage(error.ProviderDetail);
            return new VideoJobError(
                Code: ToVideoErrorCode(error.Code),
                Message: error.Message,
                Retryable: error.Retryable,
                ProviderMessage: providerMessage,
                Field: error.Field);
        }

        private static string SourceDescription(VideoMediaRef mediaRef)
        {
            return mediaRef.Kind switch
            {
                VideoMediaRefKind.Artifact =>
                    $"artifact:{mediaRef.ArtifactId} role:{mediaRef.Role}",
                VideoMediaRefKind.Path =>
                    $"path:{mediaRef.Path} role:{mediaRef.Role}",
                _ => $"unknown:{mediaRef.Role}",
            };
        }

        private static GenerationErrorCode ToGenerationErrorCode(VideoErrorCode code) =>
            code switch
            {
                VideoErrorCode.InvalidRequest => GenerationErrorCode.InvalidRequest,
                VideoErrorCode.UnsupportedMedia => GenerationErrorCode.UnsupportedMedia,
                VideoErrorCode.DependencyUnavailable => GenerationErrorCode.DependencyUnavailable,
                VideoErrorCode.ExecutionFailed => GenerationErrorCode.ExecutionFailed,
                VideoErrorCode.Cancelled => GenerationErrorCode.Cancelled,
                VideoErrorCode.Interrupted => GenerationErrorCode.Interrupted,
                _ => GenerationErrorCode.ExecutionFailed,
            };

        private static VideoErrorCode ToVideoErrorCode(GenerationErrorCode code) =>
            code switch
            {
                GenerationErrorCode.InvalidRequest => VideoErrorCode.InvalidRequest,
                GenerationErrorCode.UnsupportedMedia => VideoErrorCode.UnsupportedMedia,
                GenerationErrorCode.DependencyUnavailable => VideoErrorCode.DependencyUnavailable,
                GenerationErrorCode.ExecutionFailed => VideoErrorCode.ExecutionFailed,
                GenerationErrorCode.Cancelled => VideoErrorCode.Cancelled,
                GenerationErrorCode.Interrupted => VideoErrorCode.Interrupted,
                GenerationErrorCode.QuotaExceeded => VideoErrorCode.DependencyUnavailable,
                GenerationErrorCode.ContentPolicy => VideoErrorCode.ExecutionFailed,
                _ => VideoErrorCode.ExecutionFailed,
            };

        private static string? TryGetProviderMessage(
            IReadOnlyDictionary<string, JsonNode>? detail)
        {
            if (detail is null) return null;
            return detail.TryGetValue(VideoErrorDetailKeys.ProviderMessage, out var node)
                ? node?.GetValue<string>()
                : null;
        }
    }

}
