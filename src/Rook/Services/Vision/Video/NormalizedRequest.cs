using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Persisted, provider-neutral form of the request that produced a
    /// job. Captured in <see cref="VideoJobRecord.NormalizedRequest"/> so
    /// audit / replay can reconstruct what was submitted without depending
    /// on provider-specific options (which live in
    /// <see cref="VideoJobRecord.ProviderOptions"/>).
    ///
    /// Field set is the universal subset across video providers: prompt,
    /// duration, resolution, aspect, mode, media refs, seed, count.
    /// PersonGeneration is provider-specific (Veo) and lives in
    /// ProviderOptions, not here.
    /// </summary>
    public sealed record NormalizedRequest(
        VideoMode Mode,
        int DurationSeconds,
        string Resolution,
        string AspectRatio,
        string? Prompt,
        NormalizedMediaRef? StartFrame,
        NormalizedMediaRef? EndFrame,
        IReadOnlyList<NormalizedMediaRef>? ReferenceFrames,
        int? Seed,
        int NumberOfVideos);
}
