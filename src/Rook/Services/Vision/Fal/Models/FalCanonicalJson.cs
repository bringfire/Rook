using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Rook.Services.Vision.Fal.Models
{
    public static class FalCanonicalJson
    {
        public static string Hash(JsonNode value)
        {
            if (value == null) throw new ArgumentNullException(nameof(value));
            using var stream = new MemoryStream();
            using (var writer = new Utf8JsonWriter(stream))
            using (var document = JsonDocument.Parse(value.ToJsonString())) Write(writer, document.RootElement);
            using var sha = SHA256.Create();
            return string.Concat(sha.ComputeHash(stream.ToArray()).Select(b => b.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private static void Write(Utf8JsonWriter writer, JsonElement value)
        {
            switch (value.ValueKind)
            {
                case JsonValueKind.Object:
                    writer.WriteStartObject();
                    foreach (var member in value.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal))
                    { writer.WritePropertyName(member.Name); Write(writer, member.Value); }
                    writer.WriteEndObject(); break;
                case JsonValueKind.Array:
                    writer.WriteStartArray(); foreach (var item in value.EnumerateArray()) Write(writer, item); writer.WriteEndArray(); break;
                case JsonValueKind.Number: writer.WriteRawValue(NormalizeNumber(value.GetRawText())); break;
                default: value.WriteTo(writer); break;
            }
        }

        // Normalize the lexeme itself, before decimal conversion can round excess precision.
        internal static string NormalizeNumber(string raw)
        {
            bool negative = raw.StartsWith("-", StringComparison.Ordinal);
            string text = negative ? raw.Substring(1) : raw;
            int e = text.IndexOfAny(new[] { 'e', 'E' });
            long exponent = 0;
            if (e >= 0)
            {
                if (!long.TryParse(text.Substring(e + 1), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out exponent))
                    throw new FormatException("Numeric exponent is outside supported bounds.");
                text = text.Substring(0, e);
            }
            int dot = text.IndexOf('.');
            if (dot >= 0) { exponent = checked(exponent - (text.Length - dot - 1)); text = text.Remove(dot, 1); }
            text = text.TrimStart('0');
            if (text.Length == 0) return "0";
            int length = text.Length;
            text = text.TrimEnd('0');
            exponent = checked(exponent + length - text.Length);
            return (negative ? "-" : "") + text + (exponent == 0 ? "" : "e" + exponent.ToString(CultureInfo.InvariantCulture));
        }

        internal static bool TryExactDecimal(JsonNode? node, out decimal value)
        {
            value = 0;
            if (!(node is JsonValue scalar) || scalar.GetValueKind() != JsonValueKind.Number) return false;
            string raw = scalar.ToJsonString();
            try
            {
                return decimal.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                    && NormalizeNumber(raw) == NormalizeNumber(value.ToString("G29", CultureInfo.InvariantCulture));
            }
            catch (Exception ex) when (ex is FormatException || ex is OverflowException) { return false; }
        }
    }
}
