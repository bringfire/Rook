using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Domain request shape for video generation. D2.1-clean: NO base64
    /// fields exist anywhere in the domain. Inputs are referenced by
    /// <see cref="VideoMediaRef"/> (artifact_id + role, or validated path).
    /// The adapter (PR-V2) is the rejection boundary for any
    /// legacy/base64-shaped wire payloads; the type system enforces the
    /// invariant from V1a on.
    ///
    /// V1c: provider-specific fields (e.g. PersonGeneration for Veo)
    /// migrated off this generic shape into per-provider
    /// <see cref="ProviderOptions"/> subtypes (e.g. <see cref="VeoOptions"/>).
    /// <see cref="Options"/> is non-nullable; manager + estimator fail
    /// typed <see cref="VideoErrorCode.InvalidRequest"/> at the boundary
    /// if a caller hands them a request with null options.
    /// </summary>
    public sealed record VideoGenerationRequest(
        string Model,
        VideoMode Mode,
        int DurationSeconds,
        string Resolution,
        string AspectRatio,
        string? Prompt,
        VideoMediaRef? StartFrame,
        VideoMediaRef? EndFrame,
        IReadOnlyList<VideoMediaRef>? ReferenceFrames,
        int? Seed,
        ProviderOptions Options,
        int NumberOfVideos);
}
