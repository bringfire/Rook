using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Test-only types that satisfy the generic seam constraints so PR-1
    /// fixtures can exercise <see cref="IGenerationProvider{TRequest, TCapability}"/>
    /// without depending on PR-2 (<c>VideoGenerationRequest</c> /
    /// <c>VideoCapability</c>) or PR-3 (<c>ImageGenerationRequest</c> /
    /// <c>ImageCapability</c>) modality-specific types.
    ///
    /// These are intentionally minimal: they are NOT modeling a real
    /// modality. The symbol-scan acceptance test rejects 3D-shaped
    /// values for <see cref="TestCapability.Modality"/>; <c>"test"</c>
    /// is the chosen value so the scan guards production code only.
    /// </summary>
    internal sealed class TestGenerationRequest : GenerationRequest
    {
        public TestGenerationRequest(string Model, ProviderOptions Options)
            : base(Model, Options)
        {
        }
    }

    internal sealed class TestProviderOptions : ProviderOptions
    {
    }

    internal sealed record TestCapability(
        string Id,
        string Name,
        string Status,
        IReadOnlyList<string> SubCapabilities) : IModelCapability
    {
        public string Modality => "test";
    }
}
