using System.Text.Json;
using System.Text.Json.Serialization;

namespace MultiProviderSpike.Models;

public sealed class CaptureEnvelope
{
    [JsonPropertyName("captured_at")]
    public string? CapturedAt { get; set; }

    [JsonPropertyName("context")]
    public JsonElement Context { get; set; }

    [JsonPropertyName("stage")]
    public string? Stage { get; set; }

    [JsonPropertyName("request")]
    public JsonElement Request { get; set; }

    [JsonPropertyName("response")]
    public JsonElement Response { get; set; }
}
