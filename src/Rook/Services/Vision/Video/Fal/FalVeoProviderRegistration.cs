using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalVeoProviderRegistration : IVideoProviderRegistration
    {
        public FalVeoProviderRegistration(FalVideoProvider provider, FalVeoBindingCatalog catalog)
        {
            Provider = provider;
            Models = catalog.All.GroupBy(b => b.ModelId).ToDictionary(g => g.Key, g => (g.First().Capability, (IPricingModel<VideoGenerationRequest, VideoCapability>)new PerSecondVideoPricingModel(g.First().RatesUsdPerSecond, g.First().PricingSource)));
        }
        public string ProviderName => "fal";
        public IVideoProvider Provider { get; }
        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; } = new FalVeoOptionsCodec();
        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } = Array.AsReadOnly(new[] { new ProviderSecretRequirement(GenerationSecretKeys.FalApiKey, "fal.ai API key", true) });
    }
}
