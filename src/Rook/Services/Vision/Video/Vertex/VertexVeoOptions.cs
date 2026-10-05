using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Validation = Rook.Services.Vision.Generation.ValidationResult;

namespace Rook.Services.Vision.Video.Vertex
{
    internal sealed class VertexVeoOptions : ProviderOptions
    {
        internal VertexVeoOptions(PersonGenerationPolicy personGeneration) => PersonGeneration = personGeneration;
        internal PersonGenerationPolicy PersonGeneration { get; }
    }

    internal sealed class VertexVeoOptionsCodec : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>
    {
        internal static string? WireValue(PersonGenerationPolicy policy) => policy switch
        {
            PersonGenerationPolicy.AllowAdult => "allow_adult",
            PersonGenerationPolicy.DontAllow => "disallow",
            _ => null,
        };
        public Validation Validate(VideoGenerationRequest request, ProviderOptions options, VideoCapability cap) =>
            options is VertexVeoOptions veo && WireValue(veo.PersonGeneration) is not null
                ? Validation.Ok() : Validation.Fail("Vertex Veo requires allow_adult or disallow person generation.", "person_generation");
        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not VertexVeoOptions veo || WireValue(veo.PersonGeneration) is not string value)
                throw new InvalidOperationException("Invalid Vertex Veo options.");
            return new JsonObject { ["person_generation"] = value };
        }
        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            try
            {
                if (json.Count == 1 && json["person_generation"]?.GetValue<string>() is string value)
                {
                    if (value == "allow_adult") return ProviderOptionsDecodeResult.Ok(new VertexVeoOptions(PersonGenerationPolicy.AllowAdult));
                    if (value == "disallow") return ProviderOptionsDecodeResult.Ok(new VertexVeoOptions(PersonGenerationPolicy.DontAllow));
                }
            }
            catch { }
            return ProviderOptionsDecodeResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest,
                "Invalid Vertex Veo options.", false, Field: "person_generation"));
        }
    }
}
