namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Provider-neutral cost estimator. Takes an already-resolved
    /// <see cref="ResolvedVideoModel"/> (manager owns the
    /// <see cref="IVideoProviderRegistry.TryResolve"/> call); validates
    /// request shape via <see cref="CapabilityValidator"/> + the model's
    /// codec, then delegates pricing to
    /// <see cref="ResolvedVideoModel.PricingModel"/>. Pricing is computed
    /// exactly once per <see cref="Estimate"/> call.
    /// </summary>
    public interface IVideoCostEstimator
    {
        VideoCostEstimateResult Estimate(
            ResolvedVideoModel model,
            VideoGenerationRequest request);
    }
}
