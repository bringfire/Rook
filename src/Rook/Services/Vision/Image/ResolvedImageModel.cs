using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed record ResolvedImageModel(
        string ModelId,
        string ProviderName,
        IImageProvider Provider,
        ImageCapability Capability,
        IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel,
        IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec)
        : IResolvedModel
    {
        IModelCapability IResolvedModel.Capability => Capability;
        public string PricingSource => PricingModel.PricingSource;
    }
}
