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

    // fal.ai submit-envelope fields. fal returns
    // { "request_id": "...", "status_url": "...", "response_url": "...", "cancel_url": "..." }
    // on submit; without these as recognized signals the C# shape probe would reject
    // valid fal-hosted P2/P4 lifecycle captures.
    [JsonPropertyName("request_id")]
    public string? RequestId { get; set; }

    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [JsonPropertyName("status_url")]
    public string? StatusUrl { get; set; }

    [JsonPropertyName("response_url")]
    public string? ResponseUrl { get; set; }

    [JsonPropertyName("cancel_url")]
    public string? CancelUrl { get; set; }

    // Modality-specific result envelopes observed in actual captures.
    // - Images: fal sync image result -> {"images": [{url, content_type, ...}]}
    // - Video:  fal queue video result -> {"video": {url, duration, fps, ...}}
    // - ModelGlb / ModelUrls: fal queue 3D result -> {"model_glb": {...}, "model_urls": {glb, obj, fbx, ...}}
    // - Candidates: Gemini result -> {"candidates": [{content: {parts: [...]}}, ...]}
    // - Detail: FastAPI-style error envelope (fal queue 3D 422 rejection) ->
    //   {"detail": [{loc, msg, type, url}, ...]}
    [JsonPropertyName("images")]
    public JsonElement Images { get; set; }

    [JsonPropertyName("video")]
    public JsonElement Video { get; set; }

    [JsonPropertyName("audio")]
    public JsonElement Audio { get; set; }

    [JsonPropertyName("model_glb")]
    public JsonElement ModelGlb { get; set; }

    [JsonPropertyName("model_urls")]
    public JsonElement ModelUrls { get; set; }

    [JsonPropertyName("candidates")]
    public JsonElement Candidates { get; set; }

    [JsonPropertyName("detail")]
    public JsonElement Detail { get; set; }

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
           || !string.IsNullOrWhiteSpace(StatusUrl)
           || !string.IsNullOrWhiteSpace(ResponseUrl)
           || !string.IsNullOrWhiteSpace(CancelUrl)
           || !string.IsNullOrWhiteSpace(RequestId)
           || !string.IsNullOrWhiteSpace(Id)
           || (Urls is not null && Urls.Count > 0)
           // Modality-specific result envelopes (fal video/3D, Gemini, error bodies)
           || Images.ValueKind != JsonValueKind.Undefined
           || Video.ValueKind != JsonValueKind.Undefined
           || Audio.ValueKind != JsonValueKind.Undefined
           || ModelGlb.ValueKind != JsonValueKind.Undefined
           || ModelUrls.ValueKind != JsonValueKind.Undefined
           || Candidates.ValueKind != JsonValueKind.Undefined
           || Detail.ValueKind != JsonValueKind.Undefined;
}
