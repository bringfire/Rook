using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class ConfiguredFalImageRegistration : IImageProviderRegistration
    {
        public ConfiguredFalImageRegistration(FalModelDefinition model, FalConfiguredExecutor executor, FalAdapterRegistry adapters,
            IPricingModel<ImageGenerationRequest, ImageCapability> pricingModel)
        {
            if (pricingModel == null) throw new ArgumentNullException(nameof(pricingModel));
            var binding = new ConfiguredGenerationBinding(model, adapters, "image");
            Provider = new ConfiguredFalImageProvider(model, executor, adapters);
            OptionsCodec = new ConfiguredFalImageOptionsCodec(model, adapters);
            var capability = new ImageCapability(model.ModelId, model.DisplayName, model.Status,
                binding.Choices("resolution"), binding.Choices("aspect_ratio"), binding.MaxReferences,
                model.Operations.Any(o => o.OperationId == "image_to_image"), model.Operations.Any(o => o.OperationId == "text_to_image"),
                model.Operations.Select(o => o.OperationId).ToArray());
            Models = new ReadOnlyDictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(
                new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal) { [model.ModelId] = (capability, pricingModel) });
        }
        public string ProviderName => "fal";
        public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.AsyncImageJob;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } = Array.AsReadOnly(new[] { new ProviderSecretRequirement(GenerationSecretKeys.FalApiKey, "fal API key", isRequired: true) });
    }
}
