namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Catalog-enumeration projection of a registered
    /// <see cref="IResolvedModel"/>. Modality-specific descriptors
    /// (PR-2's <c>VideoModelDescriptor</c>, PR-3's
    /// <c>ImageModelDescriptor</c>) inherit and add typed fields where
    /// useful (e.g. video keeps the resolution/duration table; image
    /// keeps the resolution/aspect-ratio table). The base lets a picker
    /// UI list models from heterogeneous modalities in a single pass.
    /// </summary>
    public abstract record ModelDescriptor(
        string ModelId,
        string ProviderName,
        IModelCapability Capability,
        string PricingSource);
}
