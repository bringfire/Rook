using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class FakeVideoProviderTests
    {
        private static VideoGenerationRequest SampleRequest() => new(
            Model: "veo-3.1-lite-generate-preview",
            Mode: VideoMode.T2V,
            DurationSeconds: 8,
            Resolution: "720p",
            AspectRatio: "16:9",
            Prompt: "a clip",
            StartFrame: null,
            EndFrame: null,
            ReferenceFrames: null,
            Seed: null,
            PersonGeneration: PersonGenerationPolicy.AllowAll,
            NumberOfVideos: 1);

        // ─── Hooks fire when set ──────────────────────────────────────

        [Fact]
        public async Task Submit_invokes_OnSubmit_when_set()
        {
            var fake = new FakeVideoProvider
            {
                OnSubmit = req => JobSubmitResult.Ok("custom-id-42", VideoJobState.Queued),
            };

            var result = await fake.SubmitAsync(SampleRequest(), CancellationToken.None);

            Assert.Equal("custom-id-42", result.ProviderJobId);
            Assert.Equal(VideoJobState.Queued, result.State);
        }

        [Fact]
        public async Task Cancel_invokes_OnCancel_when_set()
        {
            var fake = new FakeVideoProvider
            {
                OnCancel = id => JobCancelResult.Ok(VideoJobState.Cancelled),
            };

            var result = await fake.CancelAsync("any", CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, result.State);
        }

        // ─── Recorded calls preserve order ────────────────────────────

        [Fact]
        public async Task RecordedCalls_captures_methods_in_order()
        {
            var fake = new FakeVideoProvider();

            await fake.SubmitAsync(SampleRequest(), CancellationToken.None);
            await fake.GetStatusAsync("fake-job-1", CancellationToken.None);
            await fake.GetStatusAsync("fake-job-1", CancellationToken.None);
            await fake.CancelAsync("fake-job-1", CancellationToken.None);

            Assert.Collection(fake.RecordedCalls,
                c => Assert.Equal("Submit", c.Method),
                c => Assert.Equal("GetStatus", c.Method),
                c => Assert.Equal("GetStatus", c.Method),
                c => Assert.Equal("Cancel", c.Method));
        }

        // ─── Default behaviour is sensible ────────────────────────────

        [Fact]
        public async Task Default_Submit_returns_submitting_with_provider_id()
        {
            var fake = new FakeVideoProvider();

            var result = await fake.SubmitAsync(SampleRequest(), CancellationToken.None);

            Assert.Equal(VideoJobState.Submitting, result.State);
            Assert.NotNull(result.ProviderJobId);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task Default_FetchResult_when_premature_surfaces_error_not_fake_guid()
        {
            // Pinning the JobFetchResult invariant: when Error != null,
            // ResultArtifactId must be null. The fake's default behaviour
            // models the "premature fetch" failure mode honestly.
            var fake = new FakeVideoProvider();

            var result = await fake.FetchResultAsync("any", CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Null(result.ResultArtifactId);
            Assert.Null(result.Files);
        }

        [Fact]
        public async Task Custom_FetchResult_complete_state_carries_artifact_id_and_files()
        {
            var artifactId = Guid.NewGuid();
            var fake = new FakeVideoProvider
            {
                OnFetchResult = id => JobFetchResult.Complete(
                    artifactId,
                    new[]
                    {
                        new JobResultFile(VideoMediaRoles.Video, "primary.mp4"),
                        new JobResultFile(VideoMediaRoles.Poster, "poster.jpg"),
                    }),
            };

            var result = await fake.FetchResultAsync("any", CancellationToken.None);

            Assert.Equal(VideoJobState.Complete, result.State);
            Assert.Equal(artifactId, result.ResultArtifactId);
            Assert.NotNull(result.Files);
            Assert.Equal(2, result.Files!.Count);
            Assert.Null(result.Error);
        }
    }
}
