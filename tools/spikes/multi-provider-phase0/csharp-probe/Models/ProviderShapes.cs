using System.Text.Json;
using System.Text.Json.Serialization;

namespace MultiProviderSpike.Models;

public sealed class CaptureHttpResponse
{
    [JsonPropertyName("status_code")]
    public int? StatusCode { get; set; }

    [JsonPropertyName("headers")]
    public Dictionary<string, string>? Headers { get; set; }

    [JsonPropertyName("body")]
    public JsonElement Body { get; set; }
}

public sealed class ProviderBodyShape
{
    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("state")]
    public string? State { get; set; }

    [JsonPropertyName("output")]
    public JsonElement Output { get; set; }

    [JsonPropertyName("result_url")]
    public string? ResultUrl { get; set; }

    [JsonPropertyName("output_url")]
    public string? OutputUrl { get; set; }

    [JsonPropertyName("urls")]
    public Dictionary<string, JsonElement>? Urls { get; set; }

    // JsonExtensionData kept for forward compatibility (lets unknown fields round-trip),
    // but unknown fields do NOT count as a lifecycle/result signal — otherwise arbitrary
    // payloads and error bodies would silently pass the shape check.
    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; set; }

    public bool HasLifecycleOrResultSignal()
        => !string.IsNullOrWhiteSpace(Status)
           || !string.IsNullOrWhiteSpace(State)
           || Output.ValueKind != JsonValueKind.Undefined
           || !string.IsNullOrWhiteSpace(ResultUrl)
           || !string.IsNullOrWhiteSpace(OutputUrl)
           || (Urls is not null && Urls.Count > 0);
}
