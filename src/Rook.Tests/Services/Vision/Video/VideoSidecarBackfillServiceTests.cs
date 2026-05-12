using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoSidecarBackfillServiceTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly FakePosterProducer _poster = new();
        private readonly FakeFrameProducer _frames = new();
        private readonly FakeBackfillClock _clock;

        public VideoSidecarBackfillServiceTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-backfill-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _clock = new FakeBackfillClock(DateTimeOffset.UtcNow);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsNonGeneratedVideoWithoutConsumingCap()
        {
            _store.Create("generated_image", new[] { new BlobInput("image", Bytes("png"), "png") });
            var video = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(1, TimeSpan.FromMinutes(1)),
                CancellationToken.None);

            Assert.Equal(2, result.ScannedArtifacts);
            Assert.Equal(1, result.EligibleArtifacts);
            Assert.Equal(1, result.ArtifactsAttempted);
            Assert.Equal(video.Id, Assert.Single(_poster.ArtifactIds));
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsGeneratedVideoWithoutVideoRole()
        {
            var artifact = _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg") });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedNoVideoRole, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsGeneratedVideoWithUnreadableVideoBlob()
        {
            var artifact = GeneratedVideo();
            File.Delete(_store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video));
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedVideoBlobUnavailable, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsArtifactWithAllRolesPresent()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                    new BlobInput(VideoMediaRoles.EndFrame, Bytes("end"), "jpg"),
                });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedNoMissingRoles, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_PosterOnlyMissingRunsOnlyPoster()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                    new BlobInput(VideoMediaRoles.EndFrame, Bytes("end"), "jpg"),
                });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
            Assert.Equal(1, result.RoleAttempts);
            Assert.Equal(1, result.RolesPublished);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_EndOnlyMissingRunsOnlyEndFrame()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                });
            var service = CreateService();

            await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var request = Assert.Single(_frames.Requests);
            Assert.Equal(artifact.Id, request.ArtifactId);
            Assert.Equal(new[] { VideoMediaRoles.EndFrame }, request.Roles);
            Assert.Empty(_poster.ArtifactIds);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_MissingAllRolesAttemptsDeterministicOrderOneFrameRolePerCall()
        {
            var artifact = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(
                new[] { VideoMediaRoles.Poster, VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                artifactResult.RoleResults.Select(r => r.Role));
            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Equal(2, _frames.Requests.Count);
            Assert.Equal(new[] { VideoMediaRoles.StartFrame }, _frames.Requests[0].Roles);
            Assert.Equal(new[] { VideoMediaRoles.EndFrame }, _frames.Requests[1].Roles);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_MaxArtifactsCountsEligibleArtifactsOnly()
        {
            _store.Create("generated_image", new[] { new BlobInput("image", Bytes("png"), "png") });
            var first = GeneratedVideo();
            var second = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(1, TimeSpan.FromMinutes(1)),
                CancellationToken.None);

            Assert.True(result.StoppedByCap);
            Assert.Equal(1, result.EligibleArtifacts);
            Assert.Single(_poster.ArtifactIds);
            Assert.Contains(_poster.ArtifactIds[0], new[] { first.Id, second.Id });
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_BudgetStopsBeforeStartingNextRole()
        {
            var artifact = GeneratedVideo();
            _poster.OnPublish = () => _clock.Advance(TimeSpan.FromMinutes(5));
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(10, TimeSpan.FromSeconds(1)),
                CancellationToken.None);

            Assert.True(result.BudgetExhausted);
            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
            Assert.Equal(1, result.RoleAttempts);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(
                new[] { VideoMediaRoles.Poster, VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                artifactResult.RoleResults.Select(r => r.Role));
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Published, artifactResult.RoleResults[0].Code);
            Assert.Equal(
                VideoSidecarBackfillRoleResultCode.NotStartedBudgetExhausted,
                artifactResult.RoleResults[1].Code);
            Assert.Equal(
                VideoSidecarBackfillRoleResultCode.NotStartedBudgetExhausted,
                artifactResult.RoleResults[2].Code);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_BudgetStopsBeforePlanningNextArtifactRoles()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                    new BlobInput(VideoMediaRoles.EndFrame, Bytes("end"), "jpg"),
                });
            _clock.AdvanceAfterRead = TimeSpan.FromMinutes(5);
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(10, TimeSpan.FromSeconds(1)),
                CancellationToken.None);

            Assert.True(result.BudgetExhausted);
            Assert.Equal(1, result.EligibleArtifacts);
            Assert.Equal(0, result.ArtifactsAttempted);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.StoppedByBudget, artifactResult.Code);
            Assert.Empty(artifactResult.MissingRoles);
            Assert.Empty(artifactResult.RoleResults);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_RoleFailureDoesNotBlockLaterRole()
        {
            var artifact = GeneratedVideo();
            _poster.ResultCode = VideoPosterSidecarResultCode.ExtractionFailed;
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(3, artifactResult.RoleResults.Count);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Failed, artifactResult.RoleResults[0].Code);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Published, artifactResult.RoleResults[1].Code);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Published, artifactResult.RoleResults[2].Code);
        }

        private VideoSidecarBackfillService CreateService()
            => new VideoSidecarBackfillService(_store, _poster, _frames, _clock);

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private sealed class FakePosterProducer : IVideoPosterSidecarProducer
        {
            public List<Guid> ArtifactIds { get; } = new();
            public VideoPosterSidecarResultCode ResultCode { get; set; } =
                VideoPosterSidecarResultCode.Published;
            public Action? OnPublish { get; set; }

            public Task<VideoPosterSidecarResult> TryPublishPosterAsync(
                Guid artifactId,
                CancellationToken cancellationToken)
            {
                ArtifactIds.Add(artifactId);
                OnPublish?.Invoke();
                return Task.FromResult(VideoPosterSidecarResult.From(ResultCode, artifactId));
            }
        }

        private sealed class FakeFrameProducer : IVideoFrameSidecarProducer
        {
            public List<FrameRequest> Requests { get; } = new();

            public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
                Guid artifactId,
                CancellationToken cancellationToken)
                => TryPublishFrameSidecarsAsync(
                    artifactId,
                    new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                    cancellationToken);

            public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
                Guid artifactId,
                IReadOnlyList<string> roles,
                CancellationToken cancellationToken)
            {
                Requests.Add(new FrameRequest(artifactId, roles.ToArray()));
                return Task.FromResult(new VideoFrameSidecarResult(
                    artifactId,
                    roles.Select(role => VideoFrameSidecarRoleResult.From(
                            role,
                            role == VideoMediaRoles.EndFrame
                                ? VideoFrameSelector.Last
                                : VideoFrameSelector.First,
                            VideoFrameSidecarRoleResultCode.Published))
                        .ToList()));
            }
        }

        private sealed record FrameRequest(Guid ArtifactId, IReadOnlyList<string> Roles);

        private sealed class FakeBackfillClock : IVideoSidecarBackfillClock
        {
            public FakeBackfillClock(DateTimeOffset now)
            {
                UtcNow = now;
            }

            private DateTimeOffset _utcNow;

            public DateTimeOffset UtcNow
            {
                get
                {
                    var value = _utcNow;
                    _utcNow = _utcNow.Add(AdvanceAfterRead);
                    return value;
                }
                private set => _utcNow = value;
            }

            public TimeSpan AdvanceAfterRead { get; set; }

            public void Advance(TimeSpan duration)
            {
                _utcNow = _utcNow.Add(duration);
            }
        }
    }
}
