using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public interface IImageProviderRegistration
    {
        string ProviderName { get; }
        IImageProvider Provider { get; }
        IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
        IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models { get; }
        IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; }
    }
}
