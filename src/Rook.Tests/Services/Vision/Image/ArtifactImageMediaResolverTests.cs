using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ArtifactImageMediaResolverTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly ArtifactImageMediaResolver _resolver;

        public ArtifactImageMediaResolverTests()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "rook-image-resolver-test-" + Guid.NewGuid().ToString("N"));
            _store = new ArtifactStore(_root);
            _resolver = new ArtifactImageMediaResolver(_store);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(_root))
                    Directory.Delete(_root, recursive: true);
            }
            catch { }
        }

        [Fact]
        public async Task ResolveAllAsync_resolves_artifact_image_bytes_and_mime()
        {
            var pngBytes = new byte[]
                { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 };
            var artifact = _store.Create(
                kind: "captured_viewport",
                blobs: new[] { new BlobInput("image", pngBytes, "png") });
            var media = MediaRef.ForArtifact(artifact.Id, ImageMediaRoles.Image);

            var result = await _resolver.ResolveAllAsync(
                new[] { media },
                CancellationToken.None);

            Assert.True(result.Success);
            var resolved = result.Resolved![media];
            Assert.Equal(pngBytes, resolved.Bytes);
            Assert.Equal("image/png", resolved.MimeType);
        }

        [Theory]
        [InlineData(ImageMediaRoles.InputImage)]
        [InlineData(ImageMediaRoles.ReferenceImage)]
        public async Task ResolveAllAsync_falls_back_runtime_roles_to_image_blob_role(
            string runtimeRole)
        {
            var jpgBytes = new byte[] { 0xFF, 0xD8, 0xFF, 0xE0 };
            var artifact = _store.Create(
                kind: "imported_image",
                blobs: new[] { new BlobInput(ImageMediaRoles.Image, jpgBytes, "jpg") });
            var media = MediaRef.ForArtifact(artifact.Id, runtimeRole);

            var result = await _resolver.ResolveAllAsync(
                new[] { media },
                CancellationToken.None);

            Assert.True(result.Success);
            var resolved = result.Resolved![media];
            Assert.Equal(jpgBytes, resolved.Bytes);
            Assert.Equal("image/jpeg", resolved.MimeType);
        }

        [Fact]
        public async Task ResolveAllAsync_rejects_artifact_image_over_single_limit()
        {
            var bytes = new byte[] { 0x89, 0x50, 0x4E, 0x47 };
            var artifact = _store.Create(
                kind: "imported_image",
                blobs: new[] { new BlobInput(ImageMediaRoles.Image, bytes, "png") });
            var media = MediaRef.ForArtifact(artifact.Id, ImageMediaRoles.InputImage);
            var resolver = new ArtifactImageMediaResolver(
                _store,
                maxSingleImageBytes: bytes.Length - 1,
                maxAggregateImageBytes: long.MaxValue);

            var result = await resolver.ResolveAllAsync(
                new[] { media },
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error?.Code);
            Assert.Contains("size limit", result.Error?.Message);
        }

        [Fact]
        public async Task ResolveAllAsync_rejects_artifact_images_over_aggregate_limit()
        {
            var first = _store.Create(
                kind: "imported_image",
                blobs: new[] { new BlobInput(ImageMediaRoles.Image, new byte[] { 1, 2, 3 }, "png") });
            var second = _store.Create(
                kind: "imported_image",
                blobs: new[] { new BlobInput(ImageMediaRoles.Image, new byte[] { 4, 5, 6 }, "png") });
            var firstMedia = MediaRef.ForArtifact(first.Id, ImageMediaRoles.InputImage);
            var secondMedia = MediaRef.ForArtifact(second.Id, ImageMediaRoles.ReferenceImage);
            var resolver = new ArtifactImageMediaResolver(
                _store,
                maxSingleImageBytes: 10,
                maxAggregateImageBytes: 5);

            var result = await resolver.ResolveAllAsync(
                new[] { firstMedia, secondMedia },
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error?.Code);
            Assert.Contains("Aggregate image payload", result.Error?.Message);
        }
    }
}
