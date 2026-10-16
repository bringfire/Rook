using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    public sealed class ArtifactOnlyVideoMediaResolver : IMediaResolver
    {
        private readonly ArtifactStore _store;
        private readonly VideoPreparationResources _resources;
        private readonly Func<Artifact, bool>? _videoArtifactIsVisible;
        private readonly Func<string, Stream> _openSource;
        public ArtifactOnlyVideoMediaResolver(ArtifactStore store) : this(store, VideoPreparationResources.Shared) { }
        internal ArtifactOnlyVideoMediaResolver(ArtifactStore store, VideoPreparationResources resources,
            Func<Artifact, bool>? videoArtifactIsVisible = null, Func<string, Stream>? openSource = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store)); _resources = resources;
            _videoArtifactIsVisible = videoArtifactIsVisible;
            _openSource = openSource ?? (path => new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
                bufferSize: 1, FileOptions.Asynchronous | FileOptions.SequentialScan));
        }

        public Task<MediaResolutionResult> ResolveAllAsync(IReadOnlyList<MediaRef> refs, CancellationToken ct)
            => refs is null ? Task.FromResult(MediaResolutionResult.Fail(Invalid("Media refs are null.", "MediaRef")))
                : ResolveCompatibilityAsync(refs.Where(r => r != null).Select(r => ("MediaRef", r)), ct);

        internal Task<MediaResolutionResult> ResolveMediaAsync(VideoGenerationRequest request, CancellationToken ct)
            => ResolveCompatibilityAsync(VideoPreparedMediaSnapshot.References(request), ct);

        private async Task<MediaResolutionResult> ResolveCompatibilityAsync(IEnumerable<(string Role, MediaRef Ref)> roles, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            using var preflight = CancellationTokenSource.CreateLinkedTokenSource(ct);
            preflight.CancelAfter(TimeSpan.FromSeconds(15));
            VideoPreparationLease? lease = null;
            try
            {
                lease = await _resources.AcquireAsync(preflight.Token).ConfigureAwait(false);
                var result = await ResolveCoreAsync(roles.ToArray(), lease, preflight.Token).ConfigureAwait(false);
                if (result.Error != null) return MediaResolutionResult.Fail(result.Error);
                using var snapshot = result.Snapshot!;
                var copy = snapshot.ToResolvedMedia(lease);
                copy.OwnPhase(lease); lease = null;
                return MediaResolutionResult.OkOwned(copy.Media, copy);
            }
            catch (VideoPreparationBusyException) { return MediaResolutionResult.Fail(VideoSourcePreparationErrors.Busy("media")); }
            finally { lease?.Dispose(); }
        }

        internal Task<VideoSourceSnapshotResult> ResolveSnapshotAsync(VideoGenerationRequest request, VideoPreparationLease lease, CancellationToken ct)
            => ResolveCoreAsync(VideoPreparedMediaSnapshot.References(request).ToArray(), lease, ct);

        private async Task<VideoSourceSnapshotResult> ResolveCoreAsync(IReadOnlyList<(string Role, MediaRef Ref)> roles,
            VideoPreparationLease lease, CancellationToken ct)
        {
            var sources = new Dictionary<MediaRef, VideoResolvedSource>();
            bool transferred = false;
            string field = "media";
            try
            {
                foreach (var slot in roles)
                {
                    field = slot.Role; var reference = slot.Ref;
                    ct.ThrowIfCancellationRequested();
                    if (sources.ContainsKey(reference)) continue;
                    if (reference.Kind != MediaRefKind.Artifact)
                        return new(null, Invalid("Path-kind MediaRef is not supported in V1b. Path validation is V2's adapter-boundary responsibility; use Artifact-kind image references.", field));
                    if (reference.ArtifactId is not { } id || id == Guid.Empty)
                        return new(null, Invalid("An image artifact reference is required.", field));
                    if (reference.Role is not ("image" or "start_frame" or "end_frame"))
                        return new(null, Invalid("Use an image sidecar role: image, start_frame, or end_frame.", field));
                    var artifact = _store.Get(id);
                    if (artifact == null || VideoPublicationService.IsAffectedArtifact(artifact) && _videoArtifactIsVisible?.Invoke(artifact) != true)
                        return new(null, Invalid("Video source is unavailable. Choose an image from a durably completed job.", field));
                    var path = _store.GetBlobAbsolutePath(id, reference.Role);
                    var mime = MimeTypeFromExtension(path);
                    if (!mime.StartsWith("image/", StringComparison.Ordinal))
                        return new(null, Invalid("The source resolved to non-image media. Video source refs must resolve to image blobs.", field));
                    using var file = _openSource(path);
                    long initialLength = file.Length;
                    var read = await BoundedVideoSourceReader.ReadAsync(file, initialLength, field, lease, ct).ConfigureAwait(false);
                    if (read.Error != null) return new(null, read.Error);
                    sources.Add(reference, new(read.Buffer!, mime));
                }
                var snapshot = VideoPreparedMediaSnapshot.FromOwned(roles, sources);
                transferred = true; return new(snapshot, null);
            }
            catch (OperationCanceledException) { throw; }
            catch (VideoPreparationBusyException) { return new(null, VideoSourcePreparationErrors.Busy(field)); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            { return new(null, VideoSourcePreparationErrors.Create("source_changed", field)); }
            catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException or InvalidOperationException or NotSupportedException)
            { return new(null, Invalid("Video source could not be resolved. Choose an existing image artifact.", field)); }
            finally { if (!transferred) foreach (var source in sources.Values) source.Buffer.Dispose(); }
        }
        private static GenerationError Invalid(string message, string field) => new(GenerationErrorCode.InvalidRequest, message, false, field);
        private static string MimeTypeFromExtension(string path) => Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp",
            ".gif" => "image/gif", _ => "application/octet-stream"
        };
    }
}
