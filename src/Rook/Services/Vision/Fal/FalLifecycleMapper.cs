using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalLifecycleMapper
    {
        public static ProviderJobHandle ParseSubmitHandle(
            JsonNode submitBody,
            string cancelHttpMethod)
        {
            if (submitBody is not JsonObject root)
                throw new ArgumentException("fal submit body must be a JSON object.", nameof(submitBody));

            var requestId = RequiredString(root, "request_id");
            var metadata = new Dictionary<string, JsonNode>();
            if (root["queue_position"] is JsonNode queuePosition)
                metadata["queue_position"] = queuePosition.DeepClone();
            if (root["status"] is JsonNode status)
                metadata["status"] = status.DeepClone();

            return new ProviderJobHandle(
                providerJobId: requestId,
                statusUrl: OptionalUri(root, "status_url"),
                responseUrl: OptionalUri(root, "response_url"),
                cancelUrl: OptionalUri(root, "cancel_url"),
                cancelHttpMethod: cancelHttpMethod,
                providerMetadata: metadata);
        }

        public static ProviderStatusOutcome MapStatus(
            ProviderJobHandle handle,
            JsonNode statusBody)
        {
            if (handle is null) throw new ArgumentNullException(nameof(handle));
            if (statusBody is not JsonObject root)
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    "fal status body was not a JSON object.",
                    Retryable: false));
            }

            var rawStatus = OptionalString(root, "status");
            if (rawStatus is null
                || !GenerationLifecycleStateNormalizer.TryNormalize(rawStatus, out var state))
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    $"Unknown fal lifecycle state '{rawStatus ?? "<missing>"}'.",
                    Retryable: false,
                    ProviderErrorCode: rawStatus));
            }

            if (state == GenerationLifecycleState.Pending
                || state == GenerationLifecycleState.Running)
            {
                var queuePosition = OptionalInt(root, "queue_position");
                return new InFlightStatusOutcome(
                    state,
                    queuePosition is null
                        ? null
                        : new GenerationProgress(QueuePosition: queuePosition));
            }

            if (state == GenerationLifecycleState.Completed)
                return new ProviderCompleteStatusOutcome(handle);

            if (state == GenerationLifecycleState.Canceled)
            {
                return new FailedStatusOutcome(new GenerationError(
                    GenerationErrorCode.Cancelled,
                    "fal job was cancelled.",
                    Retryable: false,
                    ProviderErrorCode: rawStatus));
            }

            return new FailedStatusOutcome(new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                $"fal job failed with state '{rawStatus}'.",
                Retryable: false,
                ProviderErrorCode: rawStatus));
        }

        private static string RequiredString(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException($"fal response missing required '{name}'.");
            return value!;
        }

        private static string? OptionalString(JsonObject root, string name)
        {
            var node = root[name];
            return node is null ? null : node.GetValue<string>();
        }

        private static int? OptionalInt(JsonObject root, string name)
        {
            var node = root[name];
            return node is null ? null : node.GetValue<int>();
        }

        private static Uri? OptionalUri(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            return string.IsNullOrWhiteSpace(value) ? null : new Uri(value!);
        }
    }
}
