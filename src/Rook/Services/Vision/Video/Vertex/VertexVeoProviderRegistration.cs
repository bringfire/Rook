using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Generation.Vertex;

namespace Rook.Services.Vision.Video.Vertex
{
    internal sealed class VertexVeoProviderRegistration : IVideoProviderRegistration
    {
        internal static readonly VideoCapability Capability = new(VertexVeoProvider.ModelKey,
            "Google Enterprise — Veo 3.1 Fast", "stable", new[] { "720p", "1080p" }, new[] { 4, 6, 8 },
            new[] { "16:9", "9:16" }, new[] { VideoMode.T2V, VideoMode.I2V, VideoMode.Interp }, true, 3,
            new[] { "1080p", "referenceImages" });
        internal VertexVeoProviderRegistration(IVideoProvider provider)
        {
            Provider = provider;
            Models = new Dictionary<string, (VideoCapability, IPricingModel<VideoGenerationRequest, VideoCapability>)>
            { [VertexVeoProvider.ModelKey] = (Capability, new VertexUnpricedModel<VideoGenerationRequest, VideoCapability>()) };
        }
        public string ProviderName => "vertex_ai";
        public IVideoProvider Provider { get; }
        public IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; } = new VertexVeoOptionsCodec();
        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => Array.Empty<ProviderSecretRequirement>();
    }
}
