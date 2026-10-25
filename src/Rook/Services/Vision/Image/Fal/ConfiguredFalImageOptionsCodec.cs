using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class ConfiguredFalImageOptionsCodec : IProviderOptionsCodec<ImageGenerationRequest, ImageCapability>
    {
        private readonly ConfiguredGenerationBinding _binding;
        public ConfiguredFalImageOptionsCodec(FalModelDefinition model, FalAdapterRegistry adapters) => _binding = new(model, adapters, "image");
        public FalNormalizationResult Normalize(FalModelInput input) => _binding.Normalize(input);
        public ValidationResult Validate(ImageGenerationRequest request, ProviderOptions options, ImageCapability capability) => _binding.Validate(request, options, capability);
        public ProviderOptionsDecodeResult Deserialize(JsonObject json) => _binding.Deserialize(json);
        public JsonObject Serialize(ProviderOptions options) => _binding.Serialize(options);
    }
}
