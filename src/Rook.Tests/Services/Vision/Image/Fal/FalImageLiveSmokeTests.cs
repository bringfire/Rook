using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public class FalImageLiveSmokeTests
    {
        private const string LiveEnabledEnvVar = "ROOK_FAL_IMAGE_LIVE";
        private const string ApiKeyEnvVar = "ROOK_FAL_API_KEY";
        private const string AcceptSpendEnvVar = "ROOK_ACCEPT_FAL_SPEND";

        [Fact]
        public async Task FluxSchnell_live_smoke_returns_remote_image_artifact_when_explicitly_enabled()
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

            var provider = new FalImageProvider(() => apiKey);

            var outcome = await provider.SubmitAsync(
                new ImageGenerationRequest(
                    Model: FalImageCapabilities.FluxSchnell,
                    Prompt: "small isometric massing model, white clay, simple daylight",
                    Resolution: "1K",
                    AspectRatio: "1:1",
                    NumberOfImages: 1,
                    ReferenceImages: null,
                    Options: new FalImageOptions()),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var success = Assert.IsType<SuccessResultOutcome>(sync.Result);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(ImageMediaRoles.Image, artifact.Role);

            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.True(remote.Url.IsAbsoluteUri);
            Assert.True(
                remote.Url.Scheme == Uri.UriSchemeHttp
                || remote.Url.Scheme == Uri.UriSchemeHttps);
        }
    }
}
