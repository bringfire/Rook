namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Marker base for every generation provider, regardless of modality.
    /// Per-modality interfaces (<c>IVideoProvider</c>, <c>IImageProvider</c>)
    /// extend the typed sub-interface
    /// <see cref="IGenerationProvider{TRequest, TCapability}"/>; this
    /// non-generic base exists so the registry can hold heterogeneous
    /// providers behind a single reference for cross-modality enumeration
    /// (e.g. picker UI listing all providers regardless of modality).
    ///
    /// Phase 1 ships this seam additively; no consumers in PR-1.
    /// </summary>
    public interface IGenerationProvider
    {
        string ProviderName { get; }
    }
}
