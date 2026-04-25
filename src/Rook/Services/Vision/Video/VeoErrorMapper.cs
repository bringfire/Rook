namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Maps Veo HTTP responses (status code + body excerpt) to typed
    /// <see cref="VideoJobError"/> values for surfacing to consumers.
    /// Centralizes the policy so V1c's optional registry work can lift
    /// it into a per-provider <c>IVideoErrorMapper</c> without touching
    /// the provider implementation.
    /// </summary>
    public static class VeoErrorMapper
    {
        public static VideoJobError MapStartFailure(int? statusCode, string? errorBody) =>
            MapByStatus(statusCode, errorBody, opName: "submit");

        public static VideoJobError MapPollFailure(int? statusCode, string? errorBody) =>
            MapByStatus(statusCode, errorBody, opName: "poll");

        public static VideoJobError MapCancelFailure(int? statusCode, string? errorBody) =>
            MapByStatus(statusCode, errorBody, opName: "cancel");

        public static VideoJobError MapDownloadFailure(int? statusCode, string? errorBody) =>
            MapByStatus(statusCode, errorBody, opName: "download");

        public static VideoJobError NetworkError(string opName, string message) => new(
            Code: VideoErrorCode.DependencyUnavailable,
            Message: $"Veo network error during {opName}: {message}",
            Retryable: true);

        public static VideoJobError MissingApiKey() => new(
            Code: VideoErrorCode.DependencyUnavailable,
            Message: "Veo API key not configured. Set it via the Vision tab Settings panel.",
            Retryable: false);

        private static VideoJobError MapByStatus(int? statusCode, string? errorBody, string opName)
        {
            // Codes per https://cloud.google.com/apis/design/errors and Veo docs.
            // 401/403 → auth; retryable=false because the same key won't fix itself.
            // 429 → rate limit; retryable=true (caller backs off).
            // 400 → caller error; retryable=false.
            // 404 → operation not found / model not found; retryable=false.
            // 5xx → backend; retryable=true.
            // Unknown → conservative: retryable=true so callers don't pin.

            var code = statusCode ?? 0;
            var bodyExcerpt = TruncateForMessage(errorBody);

            return code switch
            {
                401 or 403 => new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: $"Veo {opName} rejected: authentication failed ({code}). {bodyExcerpt}",
                    Retryable: false,
                    ProviderMessage: errorBody),

                429 => new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: $"Veo {opName} rate-limited ({code}). {bodyExcerpt}",
                    Retryable: true,
                    ProviderMessage: errorBody),

                400 => new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Veo {opName} rejected as invalid ({code}). {bodyExcerpt}",
                    Retryable: false,
                    ProviderMessage: errorBody),

                404 => new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Veo {opName} not found ({code}). {bodyExcerpt}",
                    Retryable: false,
                    ProviderMessage: errorBody),

                >= 500 and < 600 => new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: $"Veo {opName} backend error ({code}). {bodyExcerpt}",
                    Retryable: true,
                    ProviderMessage: errorBody),

                _ => new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: $"Veo {opName} failed (status {code}). {bodyExcerpt}",
                    Retryable: true,
                    ProviderMessage: errorBody),
            };
        }

        private static string TruncateForMessage(string? body)
        {
            if (string.IsNullOrEmpty(body)) return string.Empty;
            const int maxLen = 200;
            return body!.Length <= maxLen ? body : body.Substring(0, maxLen) + "...";
        }
    }
}
