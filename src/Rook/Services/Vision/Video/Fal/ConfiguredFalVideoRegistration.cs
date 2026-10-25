using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class ConfiguredFalVideoRegistration : IVideoProviderRegistration
    {
        public ConfiguredFalVideoRegistration(FalModelDefinition model, FalConfiguredExecutor executor, FalAdapterRegistry adapters,
            IPricingModel<VideoGenerationRequest, VideoCapability> pricingModel)
        {
            if (pricingModel == null) throw new ArgumentNullException(nameof(pricingModel));
            var binding = new ConfiguredGenerationBinding(model, adapters, "video");
            Provider = new ConfiguredFalVideoProvider(model, executor, adapters);
            OptionsCodec = new ConfiguredFalVideoOptionsCodec(model, adapters);
            var durations = model.Operations.SelectMany(o => new FalDescriptorProjector().Describe(o, null).ToJson()["capabilities"]!["durations"]!.AsArray())
                .Select(n => n!.GetValue<int>()).Distinct().ToArray();
            var modes = model.Operations.Select(o => o.OperationId == "text_to_video" ? VideoMode.T2V : o.OperationId == "image_to_video" ? VideoMode.I2V : VideoMode.Interp).Distinct().ToArray();
            var capability = new VideoCapability(model.ModelId, model.DisplayName, model.Status, binding.Choices("resolution"), durations,
                binding.Choices("aspect_ratio"), modes, binding.MaxReferences > 0, binding.MaxReferences, Array.Empty<string>());
            Models = new ReadOnlyDictionary<string, (VideoCapability, IPricingModel<VideoGenerationRequest, VideoCapability>)>(
                new Dictionary<string, (VideoCapability, IPricingModel<VideoGenerationRequest, VideoCapability>)>(StringComparer.Ordinal) { [model.ModelId] = (capability, pricingModel) });
        }
        public string ProviderName => "fal";
        public IVideoProvider Provider { get; }
        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; }
        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } = Array.AsReadOnly(new[] { new ProviderSecretRequirement(GenerationSecretKeys.FalApiKey, "fal API key", isRequired: true) });
    }
}
