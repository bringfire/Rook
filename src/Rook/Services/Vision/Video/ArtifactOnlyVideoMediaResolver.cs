using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Resolves <see cref="VideoMediaRefKind.Artifact"/> media refs by
    /// reading bytes from the <see cref="ArtifactStore"/>. Throws
    /// <see cref="NotSupportedException"/> for
    /// <see cref="VideoMediaRefKind.Path"/> — the name encodes the policy:
    /// path refs are intentionally unsupported until V2 owns the path
    /// validation seam, NOT "not yet implemented." The manager translates
    /// this exception into a typed <see cref="VideoErrorCode.InvalidRequest"/>
    /// before it reaches the provider or job state.
    /// </summary>
    public sealed class ArtifactOnlyVideoMediaResolver : IVideoMediaResolver
    {
        private readonly ArtifactStore _store;

        public ArtifactOnlyVideoMediaResolver(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public Task<ResolvedVideoMedia> ResolveAsync(
            VideoMediaRef mediaRef, CancellationToken ct)
        {
            if (mediaRef is null)
                throw new ArgumentNullException(nameof(mediaRef));

            ct.ThrowIfCancellationRequested();

            return mediaRef.Kind switch
            {
                VideoMediaRefKind.Artifact => Task.FromResult(ResolveArtifact(mediaRef)),
                VideoMediaRefKind.Path => throw new NotSupportedException(
                    "Path-kind VideoMediaRef is not supported in V1b. " +
                    "Path validation is V2's adapter-boundary responsibility; " +
                    "use Artifact-kind refs (created via ArtifactStore) until V2 ships."),
                _ => throw new NotSupportedException(
                    $"Unknown VideoMediaRefKind value: {(int)mediaRef.Kind}."),
            };
        }

        private ResolvedVideoMedia ResolveArtifact(VideoMediaRef mediaRef)
        {
            // VideoMediaRef.ForArtifact validated the Guid is non-empty;
            // assert here to surface the contract if someone bypassed it.
            if (mediaRef.ArtifactId is not { } id || id == Guid.Empty)
                throw new InvalidOperationException(
                    "Artifact-kind VideoMediaRef has null or empty ArtifactId.");

            var blobPath = _store.GetBlobAbsolutePath(id, mediaRef.Role);
            var bytes = File.ReadAllBytes(blobPath);
            var mimeType = MimeTypeFromExtension(blobPath);
            var description = $"artifact:{id:D} role:{mediaRef.Role}";

            return new ResolvedVideoMedia(bytes, mimeType, description);
        }

        // Map common image extensions to MIME types Veo (and other
        // providers) accept. ArtifactStore enforces a small lowercase
        // extension regex, so the set of values here is bounded and
        // known. Unknown extensions fall through to "application/octet-stream"
        // — the provider will reject the request, which is the right
        // failure mode for an unrecognized format.
        private static string MimeTypeFromExtension(string path)
        {
            var ext = Path.GetExtension(path)?.TrimStart('.').ToLowerInvariant() ?? string.Empty;
            return ext switch
            {
                "png" => "image/png",
                "jpg" or "jpeg" => "image/jpeg",
                "webp" => "image/webp",
                "gif" => "image/gif",
                "mp4" => "video/mp4",
                "webm" => "video/webm",
                _ => "application/octet-stream",
            };
        }
    }
}
