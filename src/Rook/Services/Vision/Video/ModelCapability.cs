using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    public sealed record ModelCapability(
        string Id,
        string Name,
        string Status,                                 // "stable" | "preview"
        IReadOnlyList<string> Resolutions,
        IReadOnlyList<int> Durations,
        IReadOnlyList<string> AspectRatios,
        IReadOnlyList<VideoMode> Modes,                // T2V supported by all; I2V/Interp gated
        bool SupportsReferenceImages,
        int MaxReferenceImages,
        IReadOnlyList<string> Must8sWith,              // tokens forcing duration=8 ("1080p", "4k", "referenceImages")
        IReadOnlyDictionary<string, decimal> PricePerSecondUsd);
}
