using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Replicate
{
    public sealed class ReplicateImageProviderRegistration : IImageProviderRegistration
    {
        public ReplicateImageProviderRegistration(IImageProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
        }

        public string ProviderName => ReplicateImageCapabilities.ProviderName;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
            = new ReplicateImageOptionsCodec();

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.ReplicateApiToken,
                    "Replicate API token",
                    isRequired: true),
            });

        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
            => _models;

        private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
            new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
            {
                [ReplicateImageCapabilities.FluxSchnell] = (
                    ReplicateImageCapabilities.Models[ReplicateImageCapabilities.FluxSchnell],
                    new ReplicateImagePricingModel()),
            };
    }
}
