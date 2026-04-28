using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class ArtifactOnlyVideoMediaResolverTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly ArtifactOnlyVideoMediaResolver _resolver;

        public ArtifactOnlyVideoMediaResolverTests()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                $"rook-resolver-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _resolver = new ArtifactOnlyVideoMediaResolver(_store);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        // ─── Artifact kind happy path ─────────────────────────────────

        [Fact]
        public async Task Resolves_artifact_returns_bytes_and_mime()
        {
            var pngBytes = new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };
            var artifact = _store.Create(
                kind: "captured_viewport",
                blobs: new[] { new BlobInput("image", pngBytes, "png") });

            var media = VideoMediaRef.ForArtifact(artifact.Id, VideoMediaRoles.Image);

            var resolved = await _resolver.ResolveAsync(media, CancellationToken.None);

            Assert.Equal(pngBytes, resolved.Bytes);
            Assert.Equal("image/png", resolved.MimeType);
            Assert.Contains(artifact.Id.ToString("D"), resolved.SourceDescription);
            Assert.Contains("image", resolved.SourceDescription);
        }

        [Fact]
        public async Task Resolves_jpg_artifact_with_jpeg_mime()
        {
            var jpgBytes = new byte[] { 0xFF, 0xD8, 0xFF, 0xE0 };
            var artifact = _store.Create(
                kind: "generated_image",
                blobs: new[] { new BlobInput("image", jpgBytes, "jpg") });

            var media = VideoMediaRef.ForArtifact(artifact.Id);

            var resolved = await _resolver.ResolveAsync(media, CancellationToken.None);

            Assert.Equal("image/jpeg", resolved.MimeType);
        }

        // ─── Path kind explicitly unsupported ─────────────────────────

        [Fact]
        public async Task Path_kind_throws_NotSupportedException()
        {
            var media = VideoMediaRef.ForPath(@"C:\fixtures\frame.png");

            await Assert.ThrowsAsync<NotSupportedException>(
                async () => await _resolver.ResolveAsync(media, CancellationToken.None));
        }

        [Fact]
        public async Task Path_exception_message_explains_v1b_policy()
        {
            var media = VideoMediaRef.ForPath(@"C:\fixtures\frame.png");

            var ex = await Assert.ThrowsAsync<NotSupportedException>(
                async () => await _resolver.ResolveAsync(media, CancellationToken.None));

            Assert.Contains("V1b", ex.Message);
            Assert.Contains("V2", ex.Message);
        }

        // ─── Error paths ──────────────────────────────────────────────

        [Fact]
        public async Task Null_mediaRef_throws_ArgumentNullException()
        {
            await Assert.ThrowsAsync<ArgumentNullException>(
                async () => await _resolver.ResolveAsync(null!, CancellationToken.None));
        }

        [Fact]
        public async Task Cancelled_token_throws_OperationCanceledException()
        {
            var media = VideoMediaRef.ForArtifact(Guid.NewGuid());
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAsync<OperationCanceledException>(
                async () => await _resolver.ResolveAsync(media, cts.Token));
        }

        [Fact]
        public void Constructor_rejects_null_store()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new ArtifactOnlyVideoMediaResolver(null!));
        }

        [Fact]
        public async Task ResolveAllAsync_uses_generic_media_ref_and_resolved_media()
        {
            var pngBytes = new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };
            var artifact = _store.Create(
                kind: "captured_viewport",
                blobs: new[] { new BlobInput("image", pngBytes, "png") });
            IMediaResolver resolver = _resolver;
            var media = MediaRef.ForArtifact(artifact.Id, VideoMediaRoles.Image);

            var result = await resolver.ResolveAllAsync(
                new[] { media },
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(pngBytes, result.Resolved![media].Bytes);
            Assert.Equal("image/png", result.Resolved[media].MimeType);
        }

        [Fact]
        public async Task ResolveAllAsync_path_kind_returns_typed_failure()
        {
            IMediaResolver resolver = _resolver;
            var media = MediaRef.ForPath(@"C:\fixtures\frame.png", VideoMediaRoles.Image);

            var result = await resolver.ResolveAllAsync(
                new[] { media },
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Equal("MediaRef", result.Error.Field);
            Assert.Contains("V1b", result.Error.Message);
        }
    }
}
