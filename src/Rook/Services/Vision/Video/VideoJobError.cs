using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    public sealed record VideoJobError(
        VideoErrorCode Code,
        string Message,
        bool Retryable,
        string? ProviderMessage = null,
        string? Field = null)
    {
        public static implicit operator GenerationError(VideoJobError error)
        {
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
    }
}
