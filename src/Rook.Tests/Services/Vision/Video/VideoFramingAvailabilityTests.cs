using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Generation;
using System;
using System.Linq;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingAvailabilityTests
    {
        private static FalVeoBindingCatalog DisabledCatalog() => new(new FalVeoBindingCatalog().All.Select(b => b with { SubmissionVerified = false }));
        [Fact]
        public async Task Availability_SecretFailureIsNotMissingKey()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig(catalog: new FalVeoBindingCatalog());
            var coordinator = new VideoSubmissionCoordinator(rig.Coordinator.Registry, new FalVeoBindingCatalog(), new InaccessibleSecrets());
            var quotes = new VideoRouteQuoteService(coordinator, rig.Media, new FakeVideoJobClock());
            var result = await quotes.QuoteAsync(VideoRouteQuoteTests.Intent(), default);
            Assert.Equal("secret_access_failed", result.Error!.ProviderErrorCode);
            Assert.DoesNotContain("secret raw", result.Error.Message);
        }
        private sealed class InaccessibleSecrets : IGenerationSecretStore
        {
            public string? GetSecret(string key) => throw new Exception("secret raw");
            public bool HasSecret(string key) => throw new Exception("secret raw");
            public string? GetPreview(string key) => null;
            public void SetSecret(string key, string value) => throw new NotSupportedException();
            public void RemoveSecret(string key) => throw new NotSupportedException();
        }
        [Fact]
        public async Task Availability_GatePrecedesIrrelevantMediaError()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig(catalog: DisabledCatalog()); rig.Secrets.Google = null;
            var metadata = rig.Manager.ModelAvailability("veo-3.1-generate-preview");
            Assert.False(metadata["can_generate"]!.GetValue<bool>());
            var quote = await rig.Quotes.QuoteAsync(VideoRouteQuoteTests.Intent(), default);
            Assert.Equal("video_route_unavailable", quote.Error!.ProviderErrorCode);
            Assert.Equal("Video generation needs a Google API key. Fal Veo fallback is currently disabled.", quote.Error.Message);
            Assert.Equal(0, rig.Secrets.FalReads);
        }
        [Fact]
        public async Task Availability_GoogleWorksWithFalDisabled()
        {
            using var rig = new VideoFalFallbackManagerTests.Rig(catalog: DisabledCatalog()); rig.Secrets.ThrowFal = true;
            Assert.True(rig.Manager.ModelAvailability("veo-3.1-generate-preview")["can_generate"]!.GetValue<bool>());
            var quote = await rig.Quotes.QuoteAsync(VideoRouteQuoteTests.Intent(), default);
            Assert.NotNull(quote.Quote); Assert.Equal(0, rig.Secrets.FalReads);
            Assert.All(DisabledCatalog().All, b => Assert.False(b.SubmissionVerified));
        }
    }
}
