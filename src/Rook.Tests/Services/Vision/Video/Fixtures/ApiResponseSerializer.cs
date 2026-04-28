using System.Collections;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Serializes an <see cref="ApiResponse"/> into a deterministic JSON
    /// shape for golden capture. Mirrors the wire envelope the native
    /// HTTP bridge emits ({success, data, http_status}) without going
    /// through any production serializer.
    ///
    /// <para>The handler's <c>Data</c> values are
    /// <c>Dictionary&lt;string, object?&gt;</c> trees built by the
    /// per-op projection helpers. We walk them directly into a
    /// <see cref="JsonObject"/> tree so the golden bytes do not depend
    /// on a particular <see cref="JsonSerializer"/> setting (which would
    /// shift if a project-wide serializer config changed).</para>
    /// </summary>
    internal static class ApiResponseSerializer
    {
        public static string ToJson(ApiResponse response)
        {
            var obj = new JsonObject
            {
                ["success"] = response.Success,
                ["data"] = ToNode(response.Data),
                ["http_status"] = response.HttpStatus,
            };
            return obj.ToJsonString(new JsonSerializerOptions
            {
                WriteIndented = false,
            });
        }

        private static JsonNode? ToNode(object? value)
        {
            switch (value)
            {
                case null:
                    return null;
                case JsonNode node:
                    return node.DeepClone();
                case string s:
                    return JsonValue.Create(s);
                case bool b:
                    return JsonValue.Create(b);
                case int i:
                    return JsonValue.Create(i);
                case long l:
                    return JsonValue.Create(l);
                case double d:
                    return JsonValue.Create(d);
                case decimal dec:
                    return JsonValue.Create(dec);
                case System.Guid g:
                    return JsonValue.Create(g.ToString("D"));
                case System.DateTimeOffset dto:
                    return JsonValue.Create(
                        dto.ToString("o", System.Globalization.CultureInfo.InvariantCulture));
                case IDictionary<string, object?> dict:
                {
                    var o = new JsonObject();
                    foreach (var kvp in dict) o[kvp.Key] = ToNode(kvp.Value);
                    return o;
                }
                case IEnumerable enumerable:
                {
                    var arr = new JsonArray();
                    foreach (var item in enumerable) arr.Add(ToNode(item));
                    return arr;
                }
                default:
                    // Last-ditch: serialize via System.Text.Json and parse
                    // back. Catches enum / record / pure-data types not
                    // already covered. The capture tests should not rely
                    // on this branch; if a golden flake traces back here
                    // the right fix is to add an explicit case above.
                    var fallbackJson = JsonSerializer.Serialize(value);
                    return JsonNode.Parse(fallbackJson);
            }
        }
    }
}
