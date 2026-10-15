using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Tests.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoCredentialRoutingTests
    {
        [Fact]
        public async Task SafeLifecycleMethodsNormalizeProviderLocalTimeouts()
        {
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => throw new TaskCanceledException("sensitive timeout sentinel") };
            var provider = new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http)));
            var handle = new ProviderJobHandle("operations/test", providerResultToken: "https://generativelanguage.googleapis.com/v1beta/files/test:download");
            var status = Assert.IsType<FailedStatusOutcome>(await provider.GetStatusSafeAsync(handle, default));
            var fetch = Assert.IsType<FailedResultOutcome>(await provider.FetchResultSafeAsync(handle, default));
            Assert.DoesNotContain("sentinel", status.Error.Message); Assert.DoesNotContain("sentinel", fetch.Error.Message);
        }
        [Theory]
        [InlineData(403)]
        [InlineData(500)]
        public async Task SafeGooglePollingDropsRawBodiesAndNetworkExceptionText(int status)
        {
            const string sentinel = "RAW_PROVIDER_SENTINEL_signed_url_key";
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => Task.FromResult(FalVeoQueueAdapterTests.Http.Json(status, sentinel)) };
            var provider = new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http)));
            var failure = Assert.IsType<FailedStatusOutcome>(await provider.GetStatusSafeAsync(new ProviderJobHandle("operations/test"), default));
            Assert.DoesNotContain(sentinel, failure.Error.Message); Assert.Null(failure.Error.ProviderDetail);
            http.Send = _ => throw new HttpRequestException(sentinel);
            failure = Assert.IsType<FailedStatusOutcome>(await provider.GetStatusSafeAsync(new ProviderJobHandle("operations/test"), default));
            Assert.DoesNotContain(sentinel, failure.Error.Message); Assert.Null(failure.Error.ProviderDetail);
        }
        [Fact]
        public void Mp4ValidatorRequiresCompleteVideoTrackAndMedia()
        {
            var bytes = VideoFalFallbackManagerTests.ValidVideoBytes();
            Assert.True(Mp4VideoValidation.IsValid(bytes));
            Assert.False(Mp4VideoValidation.IsValid(bytes.Take(bytes.Length - 1).ToArray()));
            var hugeBox = bytes.ToArray(); hugeBox[0] = 127;
            Assert.False(Mp4VideoValidation.IsValid(hugeBox));
            Assert.False(Mp4VideoValidation.IsValid(bytes.Concat(new byte[] { 1, 2 }).ToArray()));
        }
        [Theory]
        [InlineData(401, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}", true)]
        [InlineData(403, "{\"error\":{\"details\":[{\"@type\":\"type.googleapis.com/google.rpc.ErrorInfo\",\"reason\":\"API_KEY_INVALID\",\"domain\":\"googleapis.com\"}]}}", true)]
        [InlineData(403, "{\"error\":{\"message\":\"API key invalid\"}}", false)]
        [InlineData(429, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}", false)]
        [InlineData(500, "{\"error\":{\"code\":\"rook.veo.key_rejected\"}}", false)]
        [InlineData(401, "not json", false)]
        public async Task GoogleClosedRejectionMatrix(int status, string body, bool expected)
        {
            var http = new FalVeoQueueAdapterTests.Http { Send = _ => Task.FromResult(FalVeoQueueAdapterTests.Http.Json(status, body)) };
            var provider = new VeoProvider(() => "key", new VeoClient(new HttpClient(http)));
            var request = TestVideoFixtures.DefaultT2vRequest();
            var result = Assert.IsType<FailedSubmitOutcome>(await ((IPreparedMediaVideoProvider)provider).SubmitPreparedAsync(request, VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>()), () => { }, default));
            Assert.Equal(expected, VideoCredentialErrors.FromError("veo", result.Error)?.Kind == "rejected");
            Assert.Null(result.Error.ProviderDetail);
        }

        [Fact]
        public async Task UploadsAndGoogleInlinePayloadUseFrozenSnapshot()
        {
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var bytes = new byte[] { 97, 98, 99 };
            var request = TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: reference);
            var frozen = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(bytes, "image/png") });
            bytes[0] = 0;
            var http = new FalVeoQueueAdapterTests.Http { Send = async message => {
                var json = JsonNode.Parse(await message.Content!.ReadAsStringAsync())!;
                Assert.Equal("YWJj", json["instances"]![0]!["image"]!["bytesBase64Encoded"]!.GetValue<string>());
                return FalVeoQueueAdapterTests.Http.Json(200, "{\"name\":\"models/veo-3.1-lite-generate-preview/operations/op1\"}");
            } };
            var provider = new VeoProvider(() => "key", new VeoClient(new HttpClient(http)));
            Assert.IsType<QueuedSubmitOutcome>(await ((IPreparedMediaVideoProvider)provider).SubmitPreparedAsync(request, frozen, () => { }, default));
        }
    }
}
