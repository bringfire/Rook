namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Catalog-enumeration projection of a registered
    /// <see cref="ResolvedVideoModel"/>. Returned by
    /// <see cref="IVideoProviderRegistry.EnumerateAllModels"/> for UI
    /// model pickers and cost-overview surfaces; carries enough to
    /// render a per-model row (provider tag, pricing kind, source) without
    /// exposing the live <see cref="IVideoProvider"/> /
    /// <see cref="IPricingModel"/> instances.
    /// </summary>
    public sealed record VideoModelDescriptor(
        string ModelId,
        string ProviderName,
        ModelCapability Capability,
        PricingKind PricingKind,
        string PricingSource);
}
