using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoLiveSmokeTests
    {
        private const string LiveEnabledEnvVar = "ROOK_FAL_VIDEO_LIVE";
        private const string ApiKeyEnvVar = "ROOK_FAL_API_KEY";
        private const string AcceptSpendEnvVar = "ROOK_ACCEPT_FAL_SPEND";

        [Fact]
        public async Task Wan_t2v_live_smoke_returns_remote_video_artifact_when_explicitly_enabled()
        {
            if (!string.Equals(
                    Environment.GetEnvironmentVariable(LiveEnabledEnvVar),
                    "1",
                    StringComparison.Ordinal))
            {
                return;
            }

            var apiKey = Environment.GetEnvironmentVariable(ApiKeyEnvVar);
            Assert.False(
                string.IsNullOrWhiteSpace(apiKey),
                $"{ApiKeyEnvVar} must be set when {LiveEnabledEnvVar}=1.");

            Assert.True(
                string.Equals(
                    Environment.GetEnvironmentVariable(AcceptSpendEnvVar),
                    "1",
                    StringComparison.Ordinal),
                $"{AcceptSpendEnvVar}=1 must be set when {LiveEnabledEnvVar}=1.");

            var provider = new FalVideoProvider(() => apiKey);
            var request = new VideoGenerationRequest(
                Model: FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "short architectural clay massing orbit, simple daylight",
                StartFrame: null,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

            var submit = await provider.SubmitAsync(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);
            var queued = Assert.IsType<QueuedSubmitOutcome>(submit);

            ProviderJobHandle handle = queued.Handle;
            for (var i = 0; i < 90; i++)
            {
                var status = await provider.GetStatusAsync(handle, CancellationToken.None);
                if (status is ProviderCompleteStatusOutcome complete)
                {
                    handle = complete.UpdatedHandle;
                    break;
                }

                if (status is FailedStatusOutcome failed)
                    throw new Xunit.Sdk.XunitException(failed.Error.Message);

                await Task.Delay(TimeSpan.FromSeconds(5));
            }

            var fetch = await provider.FetchResultAsync(handle, CancellationToken.None);
            var success = Assert.IsType<SuccessResultOutcome>(fetch);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(VideoMediaRoles.Video, artifact.Role);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.True(remote.Url.IsAbsoluteUri);
            Assert.True(remote.Url.Scheme == Uri.UriSchemeHttp || remote.Url.Scheme == Uri.UriSchemeHttps);

            var materialized = await new VideoArtifactMaterializer()
                .MaterializeAsync(artifact, CancellationToken.None);
            Assert.True(
                materialized.Success,
                materialized.Error?.Message ?? "Live video materialization failed.");
            Assert.NotEmpty(materialized.Bytes!);
            Assert.Equal("video/mp4", materialized.MimeType);
        }
    }
}
