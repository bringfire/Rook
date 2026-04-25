using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Persisted, provider-neutral form of a <see cref="VideoMediaRef"/>.
    /// Lives on <see cref="NormalizedRequest"/> inside
    /// <see cref="VideoJobRecord"/>. Identical structure to
    /// <see cref="VideoMediaRef"/> but without the factory-only
    /// construction discipline — this is a serialization shape, not a
    /// runtime invariant carrier.
    /// </summary>
    public sealed record NormalizedMediaRef(
        VideoMediaRefKind Kind,
        Guid? ArtifactId,
        string? Path,
        string Role);
}
