using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal static class VideoJobRecordProviderHandle
    {
        public const string ExtensionKey = "provider_handle";

        public static JsonObject? ToExtensionObject(ProviderJobHandle? handle)
        {
            if (handle is null || !HasExtendedFields(handle))
                return null;

            var obj = new JsonObject
            {
                ["status_url"] = handle.StatusUrl?.ToString(),
                ["response_url"] = handle.ResponseUrl?.ToString(),
                ["cancel_url"] = handle.CancelUrl?.ToString(),
                ["cancel_http_method"] = handle.CancelHttpMethod,
                ["provider_metadata"] = handle.ProviderMetadata is null
                    ? null
                    : CloneMetadata(handle.ProviderMetadata),
            };

            return obj;
        }

        public static bool TryFromRecord(
            VideoJobRecord record,
            out ProviderJobHandle? handle)
        {
            handle = null;
            if (record is null || string.IsNullOrWhiteSpace(record.ProviderJobId))
                return false;

            try
            {
                var extension = record.Extensions?[ExtensionKey] as JsonObject;
                if (!TryUri(extension, "status_url", out var statusUrl)
                    || !TryUri(extension, "response_url", out var responseUrl)
                    || !TryUri(extension, "cancel_url", out var cancelUrl))
                {
                    return false;
                }

                var cancelMethod = TryString(extension, "cancel_http_method");
                var metadata = extension?["provider_metadata"] as JsonObject;

                handle = new ProviderJobHandle(
                    providerJobId: record.ProviderJobId!,
                    statusUrl: statusUrl,
                    responseUrl: responseUrl,
                    cancelUrl: cancelUrl,
                    cancelHttpMethod: cancelMethod,
                    providerResultToken: record.ProviderResultToken,
                    providerMetadata: metadata is null ? null : CloneMetadataObject(metadata));
                return true;
            }
            catch (ArgumentException)
            {
                handle = null;
                return false;
            }
        }

        private static bool HasExtendedFields(ProviderJobHandle handle) =>
            handle.StatusUrl is not null
            || handle.ResponseUrl is not null
            || handle.CancelUrl is not null
            || handle.CancelHttpMethod is not null
            || handle.ProviderMetadata is not null;

        private static JsonObject CloneMetadata(
            IReadOnlyDictionary<string, JsonNode> metadata)
        {
            var clone = new JsonObject();
            foreach (var kvp in metadata)
                clone[kvp.Key] = kvp.Value?.DeepClone();
            return clone;
        }

        private static Dictionary<string, JsonNode> CloneMetadataObject(
            JsonObject metadata)
        {
            var clone = new Dictionary<string, JsonNode>(metadata.Count);
            foreach (var kvp in metadata)
            {
                if (kvp.Value is not null)
                    clone[kvp.Key] = kvp.Value.DeepClone();
            }
            return clone;
        }

        private static bool TryUri(JsonObject? obj, string key, out Uri? uri)
        {
            uri = null;
            var value = TryString(obj, key);
            if (value is null) return true;
            return Uri.TryCreate(value, UriKind.Absolute, out uri);
        }

        private static string? TryString(JsonObject? obj, string key)
        {
            if (obj is null || !obj.TryGetPropertyValue(key, out var node) || node is null)
                return null;
            try { return node.GetValue<string>(); } catch { return null; }
        }
    }
}
