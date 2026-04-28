using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Persisted, provider-neutral form of a media reference.
    /// Lives on <see cref="NormalizedRequest"/> inside
    /// <see cref="VideoJobRecord"/>. Identical structure to
    /// <see cref="Rook.Services.Vision.Generation.MediaRef"/> but without
    /// the factory-only construction discipline — this is a serialization shape, not a
    /// runtime invariant carrier.
    /// </summary>
    public sealed record NormalizedMediaRef(
        Rook.Services.Vision.Generation.MediaRefKind Kind,
        Guid? ArtifactId,
        string? Path,
        string Role);
}
