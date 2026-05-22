using System;
using System.Text.RegularExpressions;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Reference to media input for a generation request. Either points
    /// at an artifact in the ArtifactStore (preferred) or at a validated
    /// path. Never carries inline bytes — same domain-shape rule as V1c
    /// video: there is no base64 field anywhere in the domain.
    /// </summary>
    public sealed class MediaRef : IEquatable<MediaRef>
    {
        // Match ArtifactStore's RolePattern exactly so any role accepted
        // here can be passed through to artifact-store APIs.
        private static readonly Regex RolePattern =
            new(@"^[a-z0-9][a-z0-9_-]*$", RegexOptions.Compiled);

        public MediaRefKind Kind { get; }
        public Guid? ArtifactId { get; }
        public string? Path { get; }
        public string Role { get; }

        private MediaRef(MediaRefKind kind, Guid? artifactId, string? path, string role)
        {
            Kind = kind;
            ArtifactId = artifactId;
            Path = path;
            Role = role;
        }

        public static MediaRef ForArtifact(Guid id, string role)
        {
            if (id == Guid.Empty)
                throw new ArgumentException(
                    "ArtifactId must be a non-empty Guid.", nameof(id));

            return new MediaRef(
                MediaRefKind.Artifact,
                artifactId: id,
                path: null,
                role: ValidateRole(role));
        }

        public static MediaRef ForPath(string path, string role)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException(
                    "Path must be non-empty.", nameof(path));

            return new MediaRef(
                MediaRefKind.Path,
                artifactId: null,
                path: path,
                role: ValidateRole(role));
        }

        private static string ValidateRole(string role)
        {
            if (string.IsNullOrWhiteSpace(role))
                throw new ArgumentException(
                    "Role must be non-empty.", nameof(role));

            if (!RolePattern.IsMatch(role))
                throw new ArgumentException(
                    $"Role '{role}' does not match required pattern " +
                    "(^[a-z0-9][a-z0-9_-]*$).", nameof(role));

            return role;
        }

        public bool Equals(MediaRef? other)
        {
            if (ReferenceEquals(this, other)) return true;
            if (other is null) return false;

            return Kind == other.Kind
                && ArtifactId == other.ArtifactId
                && string.Equals(Path, other.Path, StringComparison.Ordinal)
                && string.Equals(Role, other.Role, StringComparison.Ordinal);
        }

        public override bool Equals(object? obj) => Equals(obj as MediaRef);

        public override int GetHashCode()
        {
            unchecked
            {
                var hash = 17;
                hash = hash * 31 + Kind.GetHashCode();
                hash = hash * 31 + ArtifactId.GetHashCode();
                hash = hash * 31 + (Path?.GetHashCode() ?? 0);
                hash = hash * 31 + Role.GetHashCode();
                return hash;
            }
        }
    }

    public enum MediaRefKind
    {
        Artifact = 0,
        Path = 1,
    }
}
