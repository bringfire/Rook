using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    public sealed class FalVideoProviderRegistration : IVideoProviderRegistration
    {
        public FalVideoProviderRegistration(IVideoProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
            OptionsCodec = new FalVideoOptionsCodec();
            Models = FalVideoCapabilities.Models;
        }

        public string ProviderName => FalVideoCapabilities.ProviderName;

        public IVideoProvider Provider { get; }

        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; }

        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.FalApiKey,
                    "fal.ai API key",
                    isRequired: true),
            });
    }
}
