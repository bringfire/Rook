using System;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace Rook.Services.Vision.CanvasDirector
{
    internal static class CanvasDirectorCanonicalJson
    {
        private static readonly JsonSerializerOptions StringOptions = new()
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };

        public static string Sha256Hex(JsonElement element)
        {
            var canonical = Serialize(element);
            using var sha256 = SHA256.Create();
            var hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(canonical));
            var builder = new StringBuilder(hash.Length * 2);
            foreach (var b in hash)
            {
                builder.Append(b.ToString("x2"));
            }

            return builder.ToString();
        }

        public static string Serialize(JsonElement element)
        {
            var builder = new StringBuilder();
            WriteElement(builder, element);
            return builder.ToString();
        }

        private static void WriteElement(StringBuilder builder, JsonElement element)
        {
            switch (element.ValueKind)
            {
                case JsonValueKind.Object:
                    builder.Append('{');
                    var firstProperty = true;
                    var properties = element.EnumerateObject().ToArray();
                    foreach (var property in properties)
                    {
                        ValidateAsciiObjectKey(property.Name);
                    }

                    foreach (var property in properties.OrderBy(p => p.Name, StringComparer.Ordinal))
                    {
                        if (!firstProperty)
                        {
                            builder.Append(',');
                        }

                        firstProperty = false;
                        WriteString(builder, property.Name);
                        builder.Append(':');
                        WriteElement(builder, property.Value);
                    }
                    builder.Append('}');
                    break;

                case JsonValueKind.Array:
                    builder.Append('[');
                    var firstElement = true;
                    foreach (var item in element.EnumerateArray())
                    {
                        if (!firstElement)
                        {
                            builder.Append(',');
                        }

                        firstElement = false;
                        WriteElement(builder, item);
                    }
                    builder.Append(']');
                    break;

                case JsonValueKind.String:
                    WriteString(builder, element.GetString());
                    break;

                case JsonValueKind.Number:
                    if (!element.TryGetInt64(out var value))
                    {
                        throw new CanvasDirectorException(
                            "invalid_input",
                            "CanvasExportState numeric values must be integers in slice one; non-integer exported values must be encoded as strings.",
                            400);
                    }

                    builder.Append(value.ToString(System.Globalization.CultureInfo.InvariantCulture));
                    break;

                case JsonValueKind.True:
                    builder.Append("true");
                    break;

                case JsonValueKind.False:
                    builder.Append("false");
                    break;

                case JsonValueKind.Null:
                    builder.Append("null");
                    break;

                default:
                    throw new CanvasDirectorException(
                        "invalid_input",
                        "CanvasExportState contains unsupported JSON values.",
                        400);
            }
        }

        private static void ValidateAsciiObjectKey(string key)
        {
            foreach (var ch in key)
            {
                if (ch > 0x7f)
                {
                    throw new CanvasDirectorException(
                        "invalid_input",
                        "CanvasExportState object keys must be ASCII in slice one.",
                        400);
                }
            }
        }

        private static void WriteString(StringBuilder builder, string? value)
        {
            builder.Append(JsonSerializer.Serialize(value, StringOptions));
        }
    }
}
