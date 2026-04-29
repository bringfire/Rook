using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// One provider's contribution to the
    /// <see cref="IVideoProviderRegistry"/>. Bundles the provider's
    /// <see cref="IVideoProvider"/> instance, its
    /// <see cref="IProviderOptionsCodec"/>, and the (capability, pricing
    /// model) pair for each model it ships. The registry flattens
    /// registrations into <see cref="ResolvedVideoModel"/> entries keyed
    /// by model id; duplicate model ids across registrations throw at
    /// construction.
    /// </summary>
    public interface IVideoProviderRegistration
    {
        string ProviderName { get; }

        IVideoProvider Provider { get; }

        Rook.Services.Vision.Generation.IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec { get; }

        IReadOnlyDictionary<string, (VideoCapability Capability, Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel)> Models { get; }

        IReadOnlyList<Rook.Services.Vision.Generation.ProviderSecretRequirement> SecretRequirements { get; }
    }
}
