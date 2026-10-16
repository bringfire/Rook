using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    internal static class VideoEstimateFingerprint
    {
        public static string Compute(JsonObject canonicalSnapshot)
        {
            using var stream = new MemoryStream();
            using (var writer = new Utf8JsonWriter(stream)) Write(writer, canonicalSnapshot);
            using var sha = SHA256.Create();
            return "v1:" + BitConverter.ToString(sha.ComputeHash(stream.ToArray())).Replace("-", "").ToLowerInvariant();
        }
        private static void Write(Utf8JsonWriter writer, JsonNode? node)
        {
            if (node is JsonObject obj)
            {
                writer.WriteStartObject();
                foreach (var pair in obj.OrderBy(p => p.Key, StringComparer.Ordinal)) { writer.WritePropertyName(pair.Key); Write(writer, pair.Value); }
                writer.WriteEndObject();
            }
            else if (node is JsonArray array)
            {
                writer.WriteStartArray(); foreach (var value in array) Write(writer, value); writer.WriteEndArray();
            }
            else if (node is null) writer.WriteNullValue();
            else
            {
                using var document = JsonDocument.Parse(node.ToJsonString());
                var value = document.RootElement;
                if (value.ValueKind == JsonValueKind.Number && value.TryGetDecimal(out var number)) writer.WriteRawValue(number.ToString("G29", CultureInfo.InvariantCulture), skipInputValidation: false);
                else value.WriteTo(writer);
            }
        }
    }
}
