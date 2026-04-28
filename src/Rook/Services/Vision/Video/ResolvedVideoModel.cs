namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// A registered model resolved by
    /// <see cref="IVideoProviderRegistry.TryResolve"/>: the model id, the
    /// provider that owns it, and the per-model pricing + options codec.
    /// Pricing is bound at the resolved-model edge (Veo 3.1 vs Veo 3 Lite
    /// charge differently at the same resolution); the options codec is
    /// per-provider (every Veo model shares <see cref="VeoOptionsCodec"/>).
    /// </summary>
    public sealed record ResolvedVideoModel(
        string ModelId,
        string ProviderName,
        IVideoProvider Provider,
        VideoCapability Capability,
        Rook.Services.Vision.Generation.IPricingModel<VideoGenerationRequest, VideoCapability> PricingModel,
        Rook.Services.Vision.Generation.IProviderOptionsCodec<VideoGenerationRequest, VideoCapability> OptionsCodec);
}
