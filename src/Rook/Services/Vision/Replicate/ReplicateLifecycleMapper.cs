using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Replicate
{
    public static class ReplicateLifecycleMapper
    {
        public static ProviderJobHandle ParseSubmitHandle(JsonNode submitBody)
        {
            if (submitBody is not JsonObject root)
                throw new ArgumentException(
                    "Replicate submit body must be a JSON object.",
                    nameof(submitBody));

            var id = RequiredString(root, "id");
            var urls = root["urls"] as JsonObject;

            return new ProviderJobHandle(
                providerJobId: id,
                statusUrl: OptionalUri(urls, "get"),
                responseUrl: null,
                cancelUrl: OptionalUri(urls, "cancel"),
                cancelHttpMethod: "POST",
                providerMetadata: BuildProviderMetadata(root));
        }

        public static ProviderStatusOutcome MapStatus(
            ProviderJobHandle handle,
            JsonNode statusBody)
        {
            if (handle is null) throw new ArgumentNullException(nameof(handle));
            if (statusBody is not JsonObject root)
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status body was not a JSON object.",
                    retryable: false);

            var id = OptionalString(root, "id");
            if (string.IsNullOrWhiteSpace(id))
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate status body missing required 'id'.",
                    retryable: false);
            if (!string.Equals(id, handle.ProviderJobId, StringComparison.Ordinal))
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    $"Replicate status id '{id}' did not match handle id '{handle.ProviderJobId}'.",
                    retryable: false,
                    providerErrorCode: "id_mismatch",
                    providerDetail: BuildProviderMetadata(root));

            if (OptionalBool(root, "data_removed") == true)
                return DataRemoved(root);

            var rawStatus = OptionalString(root, "status");
            if (string.IsNullOrWhiteSpace(rawStatus))
                return UnknownStatus(rawStatus);

            switch (rawStatus)
            {
                case "starting":
                    return new InFlightStatusOutcome(
                        GenerationLifecycleState.Pending,
                        Progress: null);

                case "processing":
                    return new InFlightStatusOutcome(
                        GenerationLifecycleState.Running,
                        Progress: null);

                case "succeeded":
                    return MapSucceeded(handle, root, id!);

                case "failed":
                    return MapFailed(root, rawStatus);

                case "canceled":
                    return MapCanceled(root, rawStatus);

                default:
                    return UnknownStatus(rawStatus);
            }
        }

        private static ProviderStatusOutcome MapSucceeded(
            ProviderJobHandle handle,
            JsonObject root,
            string id)
        {
            if (!root.TryGetPropertyValue("output", out var output) || output is null)
            {
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    "Replicate prediction succeeded without output.",
                    retryable: false,
                    providerErrorCode: "succeeded",
                    providerDetail: BuildProviderMetadata(root));
            }

            var urls = root["urls"] as JsonObject;
            if (!TryOptionalUri(urls, "get", out var statusUrl, out var urlError)
                || !TryOptionalUri(urls, "cancel", out var cancelUrl, out urlError))
            {
                return Failed(
                    GenerationErrorCode.ExecutionFailed,
                    urlError!,
                    retryable: false,
                    providerErrorCode: "malformed_urls",
                    providerDetail: BuildProviderMetadata(root));
            }

            var metadata = BuildProviderMetadata(root);
            var updated = new ProviderJobHandle(
                providerJobId: id,
                statusUrl: statusUrl ?? handle.StatusUrl,
                responseUrl: null,
                cancelUrl: cancelUrl ?? handle.CancelUrl,
                cancelHttpMethod: "POST",
                providerResultToken: TrySelectSingleOutputUrl(output),
                providerMetadata: metadata);

            return new ProviderCompleteStatusOutcome(updated);
        }

        private static ProviderStatusOutcome MapFailed(JsonObject root, string rawStatus)
        {
            var providerMessage = ErrorMessage(root["error"]);
            var message = string.IsNullOrWhiteSpace(providerMessage)
                ? "Replicate prediction failed."
                : $"Replicate prediction failed: {providerMessage}";

            return Failed(
                IsObviousDependencyFailure(providerMessage)
                    ? GenerationErrorCode.DependencyUnavailable
                    : GenerationErrorCode.ExecutionFailed,
                message,
                retryable: false,
                providerErrorCode: rawStatus,
                providerDetail: BuildFailureDetail(root));
        }

        private static ProviderStatusOutcome MapCanceled(JsonObject root, string rawStatus)
        {
            var providerMessage = ErrorMessage(root["error"]);
            var message = string.IsNullOrWhiteSpace(providerMessage)
                ? "Replicate prediction was canceled."
                : $"Replicate prediction was canceled: {providerMessage}";

            return Failed(
                GenerationErrorCode.Cancelled,
                message,
                retryable: false,
                providerErrorCode: rawStatus,
                providerDetail: BuildFailureDetail(root));
        }

        private static ProviderStatusOutcome DataRemoved(JsonObject root) =>
            Failed(
                GenerationErrorCode.DependencyUnavailable,
                "Replicate provider output expired before Rook copied it.",
                retryable: false,
                providerErrorCode: "data_removed",
                providerDetail: BuildProviderMetadata(root));

        private static ProviderStatusOutcome UnknownStatus(string? rawStatus) =>
            Failed(
                GenerationErrorCode.ExecutionFailed,
                $"Unknown Replicate lifecycle state '{rawStatus ?? "<missing>"}'.",
                retryable: false,
                providerErrorCode: rawStatus);

        private static string RequiredString(JsonObject root, string name)
        {
            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException($"Replicate response missing required '{name}'.");
            return value!;
        }

        private static string? OptionalString(JsonObject root, string name)
        {
            var node = root[name];
            return node is JsonValue value && value.TryGetValue<string>(out var stringValue)
                ? stringValue
                : null;
        }

        private static bool? OptionalBool(JsonObject root, string name)
        {
            var node = root[name];
            return node is JsonValue value && value.TryGetValue<bool>(out var boolValue)
                ? boolValue
                : null;
        }

        private static Uri? OptionalUri(JsonObject? root, string name)
        {
            if (root is null) return null;

            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                return null;

            if (!Uri.TryCreate(value, UriKind.Absolute, out var uri))
                throw new ArgumentException(
                    $"Replicate response field '{name}' was not a valid absolute URL.",
                    name);

            return uri;
        }

        private static bool TryOptionalUri(
            JsonObject? root,
            string name,
            out Uri? uri,
            out string? error)
        {
            uri = null;
            error = null;
            if (root is null)
                return true;

            var value = OptionalString(root, name);
            if (string.IsNullOrWhiteSpace(value))
                return true;

            if (Uri.TryCreate(value, UriKind.Absolute, out uri)
                && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps))
            {
                return true;
            }

            uri = null;
            error = $"Replicate response field 'urls.{name}' was not a valid absolute http/https URL.";
            return false;
        }

        private static string? TrySelectSingleOutputUrl(JsonNode output)
        {
            if (TryUrl(output, out var direct))
                return direct;

            if (output is JsonArray array
                && array.Count == 1
                && TryUrl(array[0], out var only))
            {
                return only;
            }

            return null;
        }

        private static bool TryUrl(JsonNode? node, out string? url)
        {
            url = null;
            if (node is not JsonValue value
                || !value.TryGetValue<string>(out var text))
            {
                return false;
            }

            if (!Uri.TryCreate(text, UriKind.Absolute, out var uri))
                return false;
            if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
                return false;

            url = text;
            return true;
        }

        private static IReadOnlyDictionary<string, JsonNode> BuildProviderMetadata(JsonObject root)
        {
            var metadata = new Dictionary<string, JsonNode>();
            Preserve(root, metadata, "output");
            Preserve(root, metadata, "metrics");
            Preserve(root, metadata, "model");
            Preserve(root, metadata, "version");
            Preserve(root, metadata, "data_removed");
            Preserve(root, metadata, "urls");
            return new ReadOnlyDictionary<string, JsonNode>(metadata);
        }

        private static IReadOnlyDictionary<string, JsonNode>? BuildFailureDetail(JsonObject root)
        {
            var detail = new Dictionary<string, JsonNode>();
            Preserve(root, detail, "error");
            Preserve(root, detail, "data_removed");
            Preserve(root, detail, "urls");
            return detail.Count == 0
                ? null
                : new ReadOnlyDictionary<string, JsonNode>(detail);
        }

        private static void Preserve(
            JsonObject root,
            IDictionary<string, JsonNode> target,
            string name)
        {
            if (root.TryGetPropertyValue(name, out var node) && node is not null)
                target[name] = node.DeepClone();
        }

        private static string? ErrorMessage(JsonNode? error)
        {
            if (error is null)
                return null;

            if (error is JsonValue value && value.TryGetValue<string>(out var text))
                return text;

            return error.ToJsonString();
        }

        private static bool IsObviousDependencyFailure(string? providerMessage)
        {
            if (string.IsNullOrWhiteSpace(providerMessage))
                return false;

            var text = providerMessage!;
            return text.IndexOf("dependency", StringComparison.OrdinalIgnoreCase) >= 0
                || text.IndexOf("unavailable", StringComparison.OrdinalIgnoreCase) >= 0
                || text.IndexOf("timeout", StringComparison.OrdinalIgnoreCase) >= 0
                || text.IndexOf("timed out", StringComparison.OrdinalIgnoreCase) >= 0
                || text.IndexOf("network", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static FailedStatusOutcome Failed(
            GenerationErrorCode code,
            string message,
            bool retryable,
            string? providerErrorCode = null,
            IReadOnlyDictionary<string, JsonNode>? providerDetail = null) =>
            new FailedStatusOutcome(new GenerationError(
                Code: code,
                Message: message,
                Retryable: retryable,
                ProviderErrorCode: providerErrorCode,
                ProviderDetail: providerDetail));
    }
}
