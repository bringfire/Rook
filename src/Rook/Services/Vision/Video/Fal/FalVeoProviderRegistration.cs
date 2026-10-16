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
            Models = catalog.All.GroupBy(b => b.ModelId).ToDictionary(g => g.Key, g => (AdmittedCapability(g), (IPricingModel<VideoGenerationRequest, VideoCapability>)new FalVeoPricingModel(catalog)));
        }
        private static VideoCapability AdmittedCapability(IGrouping<string, FalVeoBinding> bindings)
        {
            var capability = bindings.First().Capability;
            bool references = bindings.Any(b => b.SubmitEndpoint.EndsWith("/reference-to-video", StringComparison.Ordinal)
                && b.SubmissionVerified && b.ReferenceFramingVerified);
            return new VideoCapability(capability.Id, capability.Name, capability.Status, capability.Resolutions,
                capability.Durations, capability.AspectRatios, capability.Modes,
                capability.SupportsReferenceImages && references, references ? capability.MaxReferenceImages : 0, capability.Must8sWith);
        }
        public string ProviderName => "fal";
        public IVideoProvider Provider { get; }
        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; } = new FalVeoOptionsCodec();
        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } = Array.AsReadOnly(new[] { new ProviderSecretRequirement(GenerationSecretKeys.FalApiKey, "fal.ai API key", true) });
    }
}
