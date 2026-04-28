using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal static class VideoProviderOutcomeAdapters
    {
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
