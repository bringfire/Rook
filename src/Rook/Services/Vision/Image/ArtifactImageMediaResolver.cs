using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed class ArtifactImageMediaResolver : IMediaResolver
    {
        private readonly ArtifactStore _store;

        public ArtifactImageMediaResolver(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public async Task<MediaResolutionResult> ResolveAllAsync(
            IReadOnlyList<MediaRef> refs,
            CancellationToken ct)
        {
            if (refs is null)
            {
                return MediaResolutionResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Media refs are null.",
                    Retryable: false,
                    Field: "MediaRef"));
            }

            var resolved = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var mediaRef in refs)
            {
                if (mediaRef is null || resolved.ContainsKey(mediaRef))
                    continue;

                try
                {
                    ct.ThrowIfCancellationRequested();
                    resolved[mediaRef] = await ResolveOneAsync(mediaRef, ct)
                        .ConfigureAwait(false);
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    return MediaResolutionResult.Fail(ToError(mediaRef, ex));
                }
            }

            return MediaResolutionResult.Ok(resolved);
        }

        private Task<ResolvedMedia> ResolveOneAsync(
            MediaRef mediaRef,
            CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            return mediaRef.Kind switch
            {
                MediaRefKind.Artifact => ResolveOneArtifactAsync(mediaRef, ct),
                MediaRefKind.Path => Task.FromResult(ResolvePath(mediaRef)),
                _ => throw new NotSupportedException(
                    $"Unknown MediaRefKind value: {(int)mediaRef.Kind}."),
            };
        }

        private Task<ResolvedMedia> ResolveOneArtifactAsync(
            MediaRef mediaRef,
            CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            if (mediaRef.ArtifactId is not { } id || id == Guid.Empty)
            {
                throw new InvalidOperationException(
                    "Artifact-kind MediaRef has null or empty ArtifactId.");
            }

            var role = ArtifactBlobRoleFor(mediaRef.Role);
            var blobPath = _store.GetBlobAbsolutePath(id, role);
            var bytes = File.ReadAllBytes(blobPath);
            return Task.FromResult(new ResolvedMedia(
                bytes,
                ImageMimeDetector.Detect(bytes, blobPath)));
        }

        private static ResolvedMedia ResolvePath(MediaRef mediaRef)
        {
            if (string.IsNullOrWhiteSpace(mediaRef.Path))
                throw new InvalidOperationException("Path-kind MediaRef has no path.");

            var bytes = File.ReadAllBytes(mediaRef.Path);
            return new ResolvedMedia(
                bytes,
                ImageMimeDetector.Detect(bytes, mediaRef.Path));
        }

        private static string ArtifactBlobRoleFor(string runtimeRole) =>
            runtimeRole == ImageMediaRoles.InputImage
                || runtimeRole == ImageMediaRoles.ReferenceImage
                ? ImageMediaRoles.Image
                : runtimeRole;

        private static GenerationError ToError(MediaRef mediaRef, Exception ex)
        {
            if (mediaRef.Kind == MediaRefKind.Artifact)
            {
                return new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    "Artifact image media resolution failed.",
                    Retryable: false,
                    Field: "MediaRef");
            }

            return new GenerationError(
                GenerationErrorCode.InvalidRequest,
                $"Image media resolution failed: {ex.Message}",
                Retryable: false,
                Field: "MediaRef");
        }
    }
}
