using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Veo's contribution to the
    /// <see cref="IVideoProviderRegistry"/>. Composition root constructs
    /// this with a <see cref="VeoProvider"/> instance; the registration
    /// pairs every Veo model from <see cref="VeoCapabilities.Models"/>
    /// with its per-second pricing + the shared
    /// <see cref="VeoOptionsCodec"/>.
    /// </summary>
    public sealed class VeoProviderRegistration : IVideoProviderRegistration
    {
        public VeoProviderRegistration(IVideoProvider veoProvider)
        {
            Provider = veoProvider ?? throw new ArgumentNullException(nameof(veoProvider));
            OptionsCodec = new VeoOptionsCodec();
            Models = VeoCapabilities.Models;
        }

        public string ProviderName => VeoCapabilities.ProviderName;

        public IVideoProvider Provider { get; }

        public IProviderOptionsCodec OptionsCodec { get; }

        public IReadOnlyDictionary<string, (VideoCapability Capability, IPricingModel PricingModel)> Models { get; }
    }
}
