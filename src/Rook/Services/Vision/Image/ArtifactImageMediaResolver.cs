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
        private readonly long _maxSingleImageBytes;
        private readonly long _maxAggregateImageBytes;

        public ArtifactImageMediaResolver(ArtifactStore store)
            : this(store, long.MaxValue, long.MaxValue)
        {
        }

        public ArtifactImageMediaResolver(
            ArtifactStore store,
            long maxSingleImageBytes,
            long maxAggregateImageBytes)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _maxSingleImageBytes = maxSingleImageBytes > 0
                ? maxSingleImageBytes
                : throw new ArgumentOutOfRangeException(
                    nameof(maxSingleImageBytes),
                    "Single image byte limit must be positive.");
            _maxAggregateImageBytes = maxAggregateImageBytes > 0
                ? maxAggregateImageBytes
                : throw new ArgumentOutOfRangeException(
                    nameof(maxAggregateImageBytes),
                    "Aggregate image byte limit must be positive.");
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
            var byteSizes = new Dictionary<MediaRef, long>();
            long aggregateBytes = 0;
            foreach (var mediaRef in refs)
            {
                if (mediaRef is null)
                    continue;

                try
                {
                    ct.ThrowIfCancellationRequested();
                    if (byteSizes.TryGetValue(mediaRef, out var existingByteSize))
                    {
                        ValidateImageSize(existingByteSize, aggregateBytes);
                        aggregateBytes += existingByteSize;
                        continue;
                    }

                    var item = await ResolveOneAsync(mediaRef, ct, aggregateBytes)
                        .ConfigureAwait(false);
                    aggregateBytes += item.ByteSize;
                    resolved[mediaRef] = item.Media;
                    byteSizes[mediaRef] = item.ByteSize;
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    return MediaResolutionResult.Fail(ToError(mediaRef, ex));
                }
            }

            return MediaResolutionResult.Ok(resolved);
        }

        private Task<(ResolvedMedia Media, long ByteSize)> ResolveOneAsync(
            MediaRef mediaRef,
            CancellationToken ct,
            long currentAggregateBytes)
        {
            ct.ThrowIfCancellationRequested();

            return mediaRef.Kind switch
            {
                MediaRefKind.Artifact => ResolveOneArtifactAsync(
                    mediaRef,
                    ct,
                    currentAggregateBytes),
                MediaRefKind.Path => Task.FromResult(ResolvePath(
                    mediaRef,
                    currentAggregateBytes)),
                _ => throw new NotSupportedException(
                    $"Unknown MediaRefKind value: {(int)mediaRef.Kind}."),
            };
        }

        private Task<(ResolvedMedia Media, long ByteSize)> ResolveOneArtifactAsync(
            MediaRef mediaRef,
            CancellationToken ct,
            long currentAggregateBytes)
        {
            ct.ThrowIfCancellationRequested();

            if (mediaRef.ArtifactId is not { } id || id == Guid.Empty)
            {
                throw new InvalidOperationException(
                    "Artifact-kind MediaRef has null or empty ArtifactId.");
            }

            var role = ArtifactBlobRoleFor(mediaRef.Role);
            var blobPath = _store.GetBlobAbsolutePath(id, role);
            var byteSize = GetFileLength(blobPath);
            ValidateImageSize(byteSize, currentAggregateBytes);
            var bytes = File.ReadAllBytes(blobPath);
            return Task.FromResult((
                new ResolvedMedia(
                    bytes,
                    ImageMimeDetector.Detect(bytes, blobPath)),
                byteSize));
        }

        private (ResolvedMedia Media, long ByteSize) ResolvePath(
            MediaRef mediaRef,
            long currentAggregateBytes)
        {
            if (string.IsNullOrWhiteSpace(mediaRef.Path))
                throw new InvalidOperationException("Path-kind MediaRef has no path.");

            var path = mediaRef.Path!;
            var byteSize = GetFileLength(path);
            ValidateImageSize(byteSize, currentAggregateBytes);
            var bytes = File.ReadAllBytes(path);
            return (
                new ResolvedMedia(
                    bytes,
                    ImageMimeDetector.Detect(bytes, path)),
                byteSize);
        }

        private static long GetFileLength(string path)
            => new FileInfo(path).Length;

        private void ValidateImageSize(
            long byteSize,
            long currentAggregateBytes)
        {
            if (byteSize > _maxSingleImageBytes)
            {
                throw new ImageMediaSizeException(
                    "Image media exceeds size limit of " +
                    $"{_maxSingleImageBytes} bytes ({byteSize} bytes).");
            }

            if (currentAggregateBytes > _maxAggregateImageBytes - byteSize)
            {
                var aggregateBytes = currentAggregateBytes + byteSize;
                throw new ImageMediaSizeException(
                    "Aggregate image payload exceeds " +
                    $"{_maxAggregateImageBytes} bytes ({aggregateBytes} bytes).");
            }
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
                var message = ex is ImageMediaSizeException
                    ? $"Artifact image media resolution failed: {ex.Message}"
                    : "Artifact image media resolution failed.";

                return new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    message,
                    Retryable: false,
                    Field: "MediaRef");
            }

            return new GenerationError(
                GenerationErrorCode.InvalidRequest,
                $"Image media resolution failed: {ex.Message}",
                Retryable: false,
                Field: "MediaRef");
        }

        private sealed class ImageMediaSizeException : InvalidOperationException
        {
            public ImageMediaSizeException(string message)
                : base(message)
            {
            }
        }
    }
}
