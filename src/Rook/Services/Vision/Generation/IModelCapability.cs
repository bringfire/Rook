using System.Collections.Generic;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral capability description. Modality-specific
    /// subclasses (<c>VideoCapability</c>, <c>ImageCapability</c>)
    /// implement this interface and add their own typed fields
    /// (resolutions, durations, aspect ratios, reference image counts,
    /// etc.).
    ///
    /// <para><see cref="Modality"/> is a free-form <c>string</c> rather
    /// than an enum so a future modality can be added without
    /// recompiling the core. Phase 1 enforces a closed set
    /// (<c>"image"</c>, <c>"video"</c>) via the symbol-scan acceptance
    /// test; Phase 4 will widen this when 3D ships.</para>
    /// </summary>
    public interface IModelCapability
    {
        string Id { get; }
        string Name { get; }
        string Status { get; }                          // "stable" | "preview"
        string Modality { get; }                        // "image" | "video"
        IReadOnlyList<string> SubCapabilities { get; }  // e.g. ["text_to_image", "image_to_image"]
    }
}
