using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalErrorMapper
    {
        public static GenerationError MapHttpFailure(FalHttpResponse response)
        {
            if (response is null) throw new ArgumentNullException(nameof(response));

            var statusCode = response.StatusCode;
            return new GenerationError(
                MapErrorCode(statusCode),
                string.Format(
                    CultureInfo.InvariantCulture,
                    "fal request failed with HTTP {0}.",
                    statusCode),
                IsRetryable(statusCode, response.Headers),
                ProviderErrorCode: statusCode.ToString(CultureInfo.InvariantCulture),
                ProviderDetail: TryParseProviderDetail(response.Body));
        }

        private static GenerationErrorCode MapErrorCode(int statusCode)
        {
            switch (statusCode)
            {
                case 400:
                case 422:
                    return GenerationErrorCode.InvalidRequest;
                case 401:
                case 403:
                    return GenerationErrorCode.DependencyUnavailable;
                case 429:
                    return GenerationErrorCode.QuotaExceeded;
                default:
                    return statusCode >= 500
                        ? GenerationErrorCode.DependencyUnavailable
                        : GenerationErrorCode.ExecutionFailed;
            }
        }

        private static bool IsRetryable(
            int statusCode,
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers)
        {
            switch (statusCode)
            {
                case 400:
                case 401:
                case 403:
                case 422:
                    return false;
            }

            return FalNeedsRetry(headers)
                || statusCode == 408
                || statusCode >= 500;
        }

        private static bool FalNeedsRetry(
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers)
        {
            if (!headers.TryGetValue("x-fal-needs-retry", out var values)
                || values.Count == 0)
            {
                return false;
            }

            return bool.TryParse(values[0], out var needsRetry) && needsRetry;
        }

        private static IReadOnlyDictionary<string, JsonNode>? TryParseProviderDetail(
            string body)
        {
            if (string.IsNullOrWhiteSpace(body))
                return null;

            try
            {
                if (JsonNode.Parse(body) is not JsonObject root)
                    return null;

                var detail = new Dictionary<string, JsonNode>();
                foreach (var kvp in root)
                {
                    detail[kvp.Key] = kvp.Value?.DeepClone()!;
                }

                return new ReadOnlyDictionary<string, JsonNode>(detail);
            }
            catch (JsonException)
            {
                return null;
            }
        }
    }
}
