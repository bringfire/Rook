using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class ConfiguredFalVideoOptionsCodec : IProviderOptionsCodec<VideoGenerationRequest, VideoCapability>
    {
        private readonly ConfiguredGenerationBinding _binding;
        public ConfiguredFalVideoOptionsCodec(FalModelDefinition model, FalAdapterRegistry adapters) => _binding = new(model, adapters, "video");
        public FalNormalizationResult Normalize(FalModelInput input) => _binding.Normalize(input);
        public Rook.Services.Vision.Generation.ValidationResult Validate(VideoGenerationRequest request, ProviderOptions options, VideoCapability capability) => _binding.Validate(request, options, capability);
        public ProviderOptionsDecodeResult Deserialize(JsonObject json) => _binding.Deserialize(json);
        public JsonObject Serialize(ProviderOptions options) => _binding.Serialize(options);
    }
}
