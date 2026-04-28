using System.Collections.Generic;

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

        IProviderOptionsCodec OptionsCodec { get; }

        IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel PricingModel)> Models { get; }
    }
}
