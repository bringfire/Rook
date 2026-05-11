using System;
using System.IO;
using System.Linq;
using System.Text;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoSidecarPublisherTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly VideoSidecarPublisher _publisher;

        public VideoSidecarPublisherTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-sidecar-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _publisher = new VideoSidecarPublisher(_store);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private Artifact GeneratedImage()
            => _store.Create(
                "generated_image",
                new[] { new BlobInput("image", Bytes("png"), "png") });

        [Theory]
        [InlineData(VideoMediaRoles.Poster)]
        [InlineData(VideoMediaRoles.StartFrame)]
        [InlineData(VideoMediaRoles.EndFrame)]
        public void Publish_accepts_known_video_sidecar_roles(string role)
        {
            var video = GeneratedVideo();

            var result = _publisher.Publish(video.Id, role, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.Succeeded, result.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.Contains(loaded!.Files, f => f.Role == role && f.Path == $"{role}.jpg");
        }

        [Theory]
        [InlineData(VideoMediaRoles.Video)]
        [InlineData(VideoMediaRoles.Image)]
        [InlineData("reference")]
        [InlineData("bad role")]
        public void Publish_rejects_unsupported_roles_before_storage_append(string role)
        {
            var video = GeneratedVideo();

            var result = _publisher.Publish(video.Id, role, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.RejectedUnsupportedRole, result.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.DoesNotContain(loaded!.Files, f => f.Role == role);
        }

        [Fact]
        public void Publish_rejects_non_generated_video_artifact()
        {
            var image = GeneratedImage();

            var result = _publisher.Publish(image.Id, VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.RejectedWrongArtifactKind, result.Code);
            var loaded = _store.Get(image.Id);
            Assert.NotNull(loaded);
            Assert.DoesNotContain(loaded!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public void Publish_missing_artifact_returns_artifact_not_found()
        {
            var result = _publisher.Publish(Guid.NewGuid(), VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.ArtifactNotFound, result.Code);
        }

        [Fact]
        public void Publish_duplicate_role_maps_to_skipped_already_exists()
        {
            var video = GeneratedVideo();
            var first = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("one"), "jpg");
            Assert.Equal(VideoSidecarPublishResultCode.Succeeded, first.Code);

            var second = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("two"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.SkippedAlreadyExists, second.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.Single(loaded!.Files.Where(f => f.Role == VideoMediaRoles.Poster));
            Assert.Equal("one", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.Poster)));
        }

        [Fact]
        public void Publish_storage_failure_maps_to_storage_failed()
        {
            var video = GeneratedVideo();
            var artifactDir = Directory.EnumerateDirectories(_root)
                .SelectMany(Directory.EnumerateDirectories)
                .Single(d => Path.GetFileName(d) == video.Id.ToString("D"));
            File.WriteAllText(Path.Combine(artifactDir, "poster.jpg"), "orphan");

            var result = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.StorageFailed, result.Code);
            Assert.Equal(AppendBlobResultCode.FinalFileCollision, result.StorageCode);
        }
    }
}
