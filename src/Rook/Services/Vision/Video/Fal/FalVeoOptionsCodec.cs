using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Validation = Rook.Services.Vision.Generation.ValidationResult;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalVeoOptionsCodec : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>
    {
        public Validation Validate(VideoGenerationRequest request, ProviderOptions options, VideoCapability cap) => options is FalVeoOptions ? Validation.Ok() : Validation.Fail("fal Veo requires its fixed provider-default profile.", "options");
        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not FalVeoOptions) throw new ArgumentException("Invalid fal Veo options.", nameof(options));
            return new JsonObject { ["generate_audio"] = true, ["auto_fix"] = false, ["safety_tolerance"] = "4" };
        }
        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            foreach (var item in json)
            {
                var allowed = item.Key switch {
                    "generate_audio" => item.Value is JsonValue a && a.TryGetValue<bool>(out var audio) && audio,
                    "auto_fix" => item.Value is JsonValue f && f.TryGetValue<bool>(out var fix) && !fix,
                    "safety_tolerance" => item.Value is JsonValue s && s.TryGetValue<string>(out var safety) && safety == "4",
                    _ => false
                };
                if (!allowed) return ProviderOptionsDecodeResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, "Option is incompatible with the fal Veo fixed profile.", false, "options." + item.Key));
            }
            return ProviderOptionsDecodeResult.Ok(new FalVeoOptions());
        }
    }
}
