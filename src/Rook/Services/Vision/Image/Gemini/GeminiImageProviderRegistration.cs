using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Gemini
{
    public sealed class GeminiImageProviderRegistration : IImageProviderRegistration
    {
        public GeminiImageProviderRegistration(IImageProvider provider)
        {
            Provider = provider;
        }

        public string ProviderName => GeminiImageCapabilities.ProviderName;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
            = new GeminiImageOptionsCodec();

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.GeminiApiKey,
                    "Gemini API key",
                    isRequired: true),
            });

        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
            => _models;

        private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
            new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>
            {
                [GeminiImageCapabilities.NanoBanana2] = (
                    GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBanana2],
                    new GeminiImagePricingModel()),
                [GeminiImageCapabilities.NanoBananaPro] = (
                    GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBananaPro],
                    new GeminiImagePricingModel()),
            };
    }
}
