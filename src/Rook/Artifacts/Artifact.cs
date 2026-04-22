using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Artifacts
{
    /// <summary>
    /// Immutable artifact record. The on-disk shape is uniformly snake_case
    /// (see <c>ArtifactStore</c>); this in-memory record uses PascalCase.
    /// </summary>
    public sealed record Artifact(
        Guid Id,
        string Kind,
        DateTimeOffset CreatedAt,
        IReadOnlyList<ArtifactFile> Files,
        IReadOnlyList<Guid> ParentIds,
        IReadOnlyDictionary<string, JsonNode?> Metadata,
        IReadOnlyDictionary<string, JsonNode?> Flags);

    /// <summary>
    /// One blob entry on an artifact. <see cref="Path"/> is relative to the
    /// artifact directory and is restricted to a flat filename in v1
    /// (no separators, no <c>..</c>, no leading dot).
    /// </summary>
    public sealed record ArtifactFile(string Role, string Path);

    /// <summary>
    /// Caller input for one blob during <c>ArtifactStore.Create</c>.
    /// The store builds the on-disk filename as <c>{Role}.{FileExtension}</c>.
    /// </summary>
    public sealed record BlobInput(string Role, byte[] Content, string FileExtension);
}
