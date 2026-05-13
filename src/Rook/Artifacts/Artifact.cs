using System;
using System.Collections.Generic;
using System.IO;
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

    /// <summary>
    /// Caller input for one file-backed blob during artifact creation.
    /// <see cref="SourcePath"/> is copied into the staged artifact directory;
    /// the original file is never moved or deleted.
    /// </summary>
    public sealed record BlobFileInput(
        string Role,
        string SourcePath,
        string FileExtension);

    public sealed class ArtifactBlobCopyException : IOException
    {
        public ArtifactBlobCopyException(string role, string sourcePath, string destinationPath, Exception innerException)
            : base($"Artifact blob '{role}' could not be copied.", innerException)
        {
            Role = role;
            SourcePath = sourcePath;
            DestinationPath = destinationPath;
        }

        public string Role { get; }
        public string SourcePath { get; }
        public string DestinationPath { get; }
    }

    public enum AppendBlobResultCode
    {
        Succeeded,
        ArtifactNotFound,
        ManifestReadFailed,
        InvalidRole,
        InvalidExtension,
        DuplicateRole,
        FinalFileCollision,
        StagedWriteFailed,
        FinalizeBlobFailed,
        ManifestReplaceFailed,
    }

    public sealed record AppendBlobResult(
        AppendBlobResultCode Code,
        Artifact? Artifact = null,
        string? Message = null)
    {
        public bool Success => Code == AppendBlobResultCode.Succeeded;

        public static AppendBlobResult Succeeded(Artifact artifact) =>
            new(AppendBlobResultCode.Succeeded, artifact);

        public static AppendBlobResult Fail(
            AppendBlobResultCode code,
            string message) =>
            new(code, null, message);
    }
}
