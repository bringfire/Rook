using System;
using System.Text.RegularExpressions;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public static class ImageJobLedgerRecordFactory
    {
        public const int CurrentSchemaVersion = 1;
        private const int MaxMessageLength = 300;
        private const int MaxProviderErrorCodeLength = 64;
        private const string RedactedMessage =
            "Image job failed; provider details were redacted.";

        private static readonly Regex ControlChars =
            new("[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F]", RegexOptions.Compiled);

        private static readonly string[] BannedSubstrings =
        {
            "http://",
            "https://",
            "replicate.delivery",
            "api.replicate.com",
            "urls.get",
            "urls.cancel",
            "status_url",
            "cancel_url",
            "response_url",
            "provider_result_token",
            "data:image/",
            "Bearer ",
            "api_token",
            "r8_",
        };

        public static ImageJobLedgerRecord FromInitial(
            Guid jobId,
            string provider,
            string model,
            ImageJobState initialState,
            DateTimeOffset now)
        {
            if (jobId == Guid.Empty)
                throw new ArgumentException(
                    "JobId must be non-empty.", nameof(jobId));
            if (string.IsNullOrWhiteSpace(provider))
                throw new ArgumentException(
                    "Provider must be non-empty.", nameof(provider));
            if (string.IsNullOrWhiteSpace(model))
                throw new ArgumentException(
                    "Model must be non-empty.", nameof(model));

            return new ImageJobLedgerRecord(
                CurrentSchemaVersion,
                jobId,
                provider,
                model,
                ProviderJobId: null,
                initialState,
                ResultArtifactId: null,
                Error: null,
                CreatedAt: now,
                UpdatedAt: now);
        }

        public static ImageJobLedgerRecord WithState(
            ImageJobLedgerRecord prior,
            ImageJobState state,
            DateTimeOffset now,
            string? providerJobId = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null)
        {
            if (prior is null) throw new ArgumentNullException(nameof(prior));

            return prior with
            {
                State = state,
                ProviderJobId = string.IsNullOrWhiteSpace(providerJobId)
                    ? prior.ProviderJobId
                    : providerJobId,
                ResultArtifactId = resultArtifactId ?? prior.ResultArtifactId,
                Error = SanitizeError(error) ?? prior.Error,
                UpdatedAt = now,
            };
        }

        internal static GenerationError? SanitizeError(GenerationError? error)
        {
            if (error is null) return null;
            var message = SanitizeMessage(error.Message);
            var providerCode = SanitizeProviderErrorCode(error.ProviderErrorCode);
            return new GenerationError(
                error.Code,
                message,
                error.Retryable,
                error.Field,
                providerCode,
                ProviderDetail: null);
        }

        internal static string SanitizeMessage(string? message)
        {
            if (string.IsNullOrWhiteSpace(message))
                return RedactedMessage;

            var normalized = ControlChars.Replace(message, " ").Trim();
            foreach (var banned in BannedSubstrings)
            {
                if (normalized.IndexOf(banned, StringComparison.OrdinalIgnoreCase) >= 0)
                    return RedactedMessage;
            }

            return normalized.Length <= MaxMessageLength
                ? normalized
                : normalized.Substring(0, MaxMessageLength);
        }

        private static string? SanitizeProviderErrorCode(
            string? providerErrorCode)
        {
            if (string.IsNullOrWhiteSpace(providerErrorCode)) return null;
            var trimmed = providerErrorCode.Trim();
            if (trimmed.Length > MaxProviderErrorCodeLength) return null;
            foreach (var ch in trimmed)
            {
                if (!(char.IsLetterOrDigit(ch)
                    || ch == '_'
                    || ch == '-'
                    || ch == '.'))
                {
                    return null;
                }
            }

            return trimmed;
        }
    }
}
