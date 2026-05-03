using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalImageProviderRegistration : IImageProviderRegistration
    {
        public FalImageProviderRegistration(IImageProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
        }

        public string ProviderName => FalImageCapabilities.ProviderName;
        public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
            = new FalImageOptionsCodec();

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.FalApiKey,
                    "fal API key",
                    isRequired: true),
            });

        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
            => _models;

        private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
            new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
            {
                [FalImageCapabilities.FluxSchnell] = (
                    FalImageCapabilities.Models[FalImageCapabilities.FluxSchnell],
                    new FalFluxSchnellPricingModel()),
            };
    }
}
