namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-resolved-model pricing strategy. <see cref="Kind"/> +
    /// <see cref="PricingSource"/> must match the same fields on the
    /// <see cref="JobPricing"/> emitted by <see cref="Estimate"/> — they
    /// are exposed separately so <see cref="VideoModelDescriptor"/> can
    /// surface them without invoking pricing for a representative request.
    /// </summary>
    public interface IPricingModel
    {
        PricingKind Kind { get; }
        string PricingSource { get; }

        PricingResult Estimate(VideoGenerationRequest request, ModelCapability cap);
    }
}
