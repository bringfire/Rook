namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral view of a registered model. Modality-specific
    /// resolved-model records (PR-2: <c>ResolvedVideoModel</c>; PR-3:
    /// <c>ResolvedImageModel</c>) implement this with their typed
    /// <c>Provider</c>, <c>Capability</c>, <c>PricingModel</c>, and
    /// <c>OptionsCodec</c> references; this interface is used by the
    /// catalog enumeration / picker UI surfaces that need a
    /// modality-agnostic projection.
    /// </summary>
    public interface IResolvedModel
    {
        string ModelId { get; }
        string ProviderName { get; }
        IModelCapability Capability { get; }
        string PricingSource { get; }
    }
}
