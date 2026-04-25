using System;
using System.Text.RegularExpressions;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// A reference to media input for a video generation request. Either
    /// points at an artifact in the ArtifactStore (preferred) or at a
    /// validated path (V1b adapter resolves; V1a stores as-is). Never
    /// carries inline bytes — D2.1 of the v3.1 contract is enforced by
    /// the type system: there is no base64 field anywhere in the domain.
    /// </summary>
    public sealed record VideoMediaRef
    {
        // Match ArtifactStore's RolePattern exactly so any role accepted
        // here can be passed through to ArtifactStore.GetBlobAbsolutePath.
        private static readonly Regex RolePattern =
            new(@"^[a-z0-9][a-z0-9_-]*$", RegexOptions.Compiled);

        public VideoMediaRefKind Kind { get; }
        public Guid? ArtifactId { get; }
        public string? Path { get; }
        public string Role { get; }

        private VideoMediaRef(
            VideoMediaRefKind kind,
            Guid? artifactId,
            string? path,
            string role)
        {
            Kind = kind;
            ArtifactId = artifactId;
            Path = path;
            Role = role;
        }

        public static VideoMediaRef ForArtifact(Guid id, string? role = null)
        {
            if (id == Guid.Empty)
                throw new ArgumentException(
                    "ArtifactId must be a non-empty Guid.", nameof(id));

            var resolvedRole = ResolveRole(role);
            return new VideoMediaRef(
                VideoMediaRefKind.Artifact,
                artifactId: id,
                path: null,
                role: resolvedRole);
        }

        public static VideoMediaRef ForPath(string path, string? role = null)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException(
                    "Path must be non-empty.", nameof(path));

            var resolvedRole = ResolveRole(role);
            return new VideoMediaRef(
                VideoMediaRefKind.Path,
                artifactId: null,
                path: path,
                role: resolvedRole);
        }

        private static string ResolveRole(string? role)
        {
            if (role is null) return VideoMediaRoles.Image;

            if (string.IsNullOrWhiteSpace(role))
                throw new ArgumentException(
                    "Role must be non-empty when provided.", nameof(role));

            if (!RolePattern.IsMatch(role))
                throw new ArgumentException(
                    $"Role '{role}' does not match required pattern " +
                    "(^[a-z0-9][a-z0-9_-]*$).", nameof(role));

            return role;
        }
    }
}
