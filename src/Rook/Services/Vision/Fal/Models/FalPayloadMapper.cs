using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>Finite JSON mapping only. No transport, media resolution, or downloads.</summary>
    public sealed class FalPayloadMapper
    {
        public JsonObject BuildPayload(FalNormalizedRequest request, IReadOnlyList<FalPreparedMedia> media)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            if (media == null) throw new ArgumentNullException(nameof(media));
            if (media.Any(m => m == null) || media.Count != request.Media.Count
                || request.Media.Any(i => media.Count(m => m.Role == i.Role && m.Ordinal == i.Ordinal) != 1))
                throw new ArgumentException("Prepared media must match every normalized role and ordinal exactly once.", nameof(media));
            var payload = new JsonObject();
            var fields = request.EffectiveRequestFields; var options = request.EffectiveOptions;
            foreach (var field in request.Binding.Fields)
            {
                var source = field.Scope == "request" ? fields : options;
                if (!source.TryGetPropertyValue(field.Key, out var value)) continue;
                JsonNode? mapped = value?.DeepClone();
                if (field.Payload.Conversion == "integer_to_string")
                    mapped = JsonValue.Create(decimal.Parse(value!.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture).ToString("0", CultureInfo.InvariantCulture));
                else if (field.Payload.Conversion == "enum_lookup") mapped = field.Payload.Lookup![value!.GetValue<string>()]!.DeepClone();
                Write(payload, field.Payload.Pointer, mapped);
            }
            foreach (var definition in request.Binding.Media)
            {
                var items = media.Where(m => m.Role == definition.Role).OrderBy(m => m.Ordinal).ToArray();
                if (items.Length == 0) continue;
                JsonNode value = definition.Payload.Conversion == "ordered_array"
                    ? new JsonArray(items.Select(m => (JsonNode?)JsonValue.Create(m.TransportValue)).ToArray())
                    : JsonValue.Create(items.Single().TransportValue)!;
                Write(payload, definition.Payload.Pointer, value);
            }
            foreach (var constant in request.Binding.Constants) Write(payload, constant.Pointer, constant.Value);
            return payload;
        }

        public ProviderResultOutcome MapResult(FalOperationBinding binding, JsonObject response)
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (response == null) throw new ArgumentNullException(nameof(response));
            var result = binding.Result;
            if (result.CollectionPointer != null && (!(Read(response, result.CollectionPointer) is JsonArray array) || array.Count != 1))
                return Failed("The declared result collection must contain exactly one output.");
            if (!(Read(response, result.UrlPointer) is JsonValue value) || value.GetValueKind() != JsonValueKind.String
                || !Uri.TryCreate(value.GetValue<string>(), UriKind.Absolute, out var url)
                || (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps) || url.UserInfo.Length != 0)
                return Failed("The result must contain an absolute HTTP(S) artifact URL without credentials.");
            string? mime = null;
            if (result.MimePointer != null && Read(response, result.MimePointer) is JsonNode mimeNode)
            {
                if (!(mimeNode is JsonValue mimeValue) || mimeValue.GetValueKind() != JsonValueKind.String) return Failed("Result MIME must be a string when present.");
                mime = mimeValue.GetValue<string>();
                if (!AllowedMime(result.MimeFamily, mime)) return Failed("Result MIME does not match the declared artifact family.");
            }
            var artifact = new ResultArtifact(result.MimeFamily, new RemoteArtifactBody(url), mime, new Dictionary<string, JsonNode>());
            return new SuccessResultOutcome(new ProviderResultEnvelope(new[] { artifact }, new Dictionary<string, JsonNode>()));
        }

        private static bool AllowedMime(string family, string mime)
        {
            string normalized = mime.Split(';')[0].Trim().ToLowerInvariant();
            return family == "image" ? new[] { "image/png", "image/jpeg", "image/webp", "image/gif", "image/avif" }.Contains(normalized)
                : new[] { "video/mp4", "video/webm", "video/quicktime" }.Contains(normalized);
        }
        private static ProviderResultOutcome Failed(string message)
            => new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, message, false));

        private static string[] Segments(string pointer) => pointer.Substring(1).Split('/').Select(s => s.Replace("~1", "/").Replace("~0", "~")).ToArray();
        private static void Write(JsonObject root, string pointer, JsonNode? value)
        {
            var segments = Segments(pointer); JsonObject current = root;
            foreach (string segment in segments.Take(segments.Length - 1))
            {
                if (current[segment] == null) current.Add(segment, new JsonObject());
                current = current[segment]!.AsObject();
            }
            current.Add(segments.Last(), value);
        }
        private static JsonNode? Read(JsonNode root, string pointer)
        {
            JsonNode? current = root;
            foreach (string segment in Segments(pointer))
            {
                if (current is JsonObject obj) current = obj[segment];
                else if (current is JsonArray array && segment == "0" && array.Count == 1) current = array[0];
                else return null;
            }
            return current;
        }
    }
}
