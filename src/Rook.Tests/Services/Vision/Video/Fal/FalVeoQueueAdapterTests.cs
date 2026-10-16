using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVeoQueueAdapterTests
    {
        internal sealed class Http : HttpMessageHandler
        {
            internal Func<HttpRequestMessage, Task<HttpResponseMessage>> Send = _ => Task.FromResult(Json(200, "{}"));
            internal static HttpResponseMessage Json(int status, string body) => new((HttpStatusCode)status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) => Send(request);
        }
        internal sealed class Uploads : IFalVeoSourceFrameTransport
        {
            internal List<byte[]> Bytes = new();
            public Task<(FalVeoSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadVeoAsync(FalVeoBinding binding, VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, string apiKey, CancellationToken ct, VideoPreparationLease? phase = null)
            {
                foreach (var slot in preparedMedia.Slots) Bytes.Add(slot.CopyBytes());
                return Task.FromResult<(FalVeoSourceUrls?, GenerationError?)>((new("https://v3.fal.media/a.png", request.EndFrame != null ? "https://v3.fal.media/b.png" : null, Array.AsReadOnly(preparedMedia.Slots.Where(s => s.Role.StartsWith("reference_frames")).Select(s => "https://v3.fal.media/" + s.Ref.ArtifactId + ".png").ToArray())), null));
            }
        }
        internal static ProviderJobHandle Handle(string root = "fal-ai/veo3.1", string id = "request1") => new(id,
            new Uri("https://queue.fal.run/" + root + "/requests/" + id + "/status"), new Uri("https://queue.fal.run/" + root + "/requests/" + id), new Uri("https://queue.fal.run/" + root + "/requests/" + id + "/cancel"), "PUT",
            providerMetadata: new Dictionary<string, JsonNode> { ["veo_lifecycle_root"] = JsonValue.Create("fal-ai/veo3.1")!, ["veo_endpoint"] = JsonValue.Create("fal-ai/veo3.1/image-to-video")! });
        internal const string Accepted = "{\"request_id\":\"request1\",\"status_url\":\"https://queue.fal.run/fal-ai/veo3.1/requests/request1/status\",\"response_url\":\"https://queue.fal.run/fal-ai/veo3.1/requests/request1\",\"cancel_url\":\"https://queue.fal.run/fal-ai/veo3.1/requests/request1/cancel\"}";

        [Fact]
        public async Task SignedCdnUpload401DoesNotInvalidateApiCredential()
        {
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", mode: VideoMode.I2V, startFrame: input).With(options: new FalVeoOptions());
            var client = new FalApiClient(new HttpClient(new Http { Send = message => Task.FromResult(message.RequestUri!.Host == "rest.fal.ai" ? Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload/source\",\"file_url\":\"https://v3.fal.media/files/source.png\"}") : Http.Json(401, "signed URL rejected")) }));
            var adapter = new FalVeoQueueAdapter(() => "test-only", client, FalVeoCompatibilityTests.ActiveCatalog(), new FalSourceFrameTransport(client));
            var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [input] = FalVeoCompatibilityTests.Image(1280, 720) });
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            var failure = Assert.IsType<FailedSubmitOutcome>(await adapter.SubmitPreparedAsync(request, snapshot, () => throw new Exception("Generation must not dispatch"), default, phase));
            Assert.Null(VideoCredentialErrors.FromError("fal", failure.Error));
        }
        [Fact]
        public async Task ActualSourceUpload401RetainsFalCredentialEvidenceBeforeDispatch()
        {
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", mode: VideoMode.I2V, startFrame: input).With(options: new FalVeoOptions());
            var client = new FalApiClient(new HttpClient(new Http { Send = _ => Task.FromResult(Http.Json(401, "sensitive provider body")) }));
            var adapter = new FalVeoQueueAdapter(() => "test-only", client, FalVeoCompatibilityTests.ActiveCatalog(), new FalSourceFrameTransport(client));
            var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [input] = FalVeoCompatibilityTests.Image(1280, 720) });
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            var failure = Assert.IsType<FailedSubmitOutcome>(await adapter.SubmitPreparedAsync(request, snapshot, () => throw new Exception("Generation must not dispatch"), default, phase));
            Assert.Equal("rook.fal.key_rejected", failure.Error.ProviderErrorCode); Assert.DoesNotContain("sensitive", failure.Error.Message);
        }
        [Fact]
        public async Task ActualUploadUsesFrozenBytesAndReexpandsRepeatedReferences()
        {
            var input = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", referenceFrames: new[] { input, input }).With(options: new FalVeoOptions());
            var source = FalVeoCompatibilityTests.Image(1280, 720); var expected = source.Bytes.ToArray();
            var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [input] = source });
            source.Bytes[0] = 0; int uploads = 0, sends = 0; bool admitted = false;
            var http = new Http { Send = async message => {
                if (message.RequestUri!.Host == "rest.fal.ai") return Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload/source\",\"file_url\":\"https://v3.fal.media/files/source.png\"}");
                if (message.Method == HttpMethod.Put) { uploads++; Assert.Equal(expected, await message.Content!.ReadAsByteArrayAsync()); Assert.False(admitted); return Http.Json(200, "{}"); }
                sends++; Assert.True(admitted); var payload = JsonNode.Parse(await message.Content!.ReadAsStringAsync())!;
                Assert.Equal(new[] { "https://v3.fal.media/files/source.png", "https://v3.fal.media/files/source.png" }, payload["image_urls"]!.AsArray().Select(n => n!.GetValue<string>()));
                return Http.Json(200, Accepted);
            } };
            var client = new FalApiClient(new HttpClient(http));
            var adapter = new FalVeoQueueAdapter(() => "test-only", client, FalVeoCompatibilityTests.ActiveCatalog(), new FalSourceFrameTransport(client));
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            var outcome = await adapter.SubmitPreparedAsync(request, snapshot, () => admitted = true, default, phase);
            Assert.True(outcome is QueuedSubmitOutcome, (outcome as FailedSubmitOutcome)?.Error.Message);
            Assert.Equal(1, uploads); Assert.Equal(1, sends);
        }
        [Fact]
        public async Task QueuePayloadMatchesTierModeAndFixedProfile()
        {
            var events = new List<string>();
            var http = new Http { Send = async request => {
                events.Add("send");
                Assert.Equal("1", request.Headers.GetValues("X-Fal-No-Retry").Single());
                Assert.Equal("https://queue.fal.run/fal-ai/veo3.1/fast", request.RequestUri!.AbsoluteUri);
                var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
                Assert.Equal("8s", body["duration"]!.GetValue<string>());
                Assert.True(body["generate_audio"]!.GetValue<bool>());
                Assert.False(body["auto_fix"]!.GetValue<bool>());
                Assert.Equal("4", body["safety_tolerance"]!.GetValue<string>());
                return Http.Json(200, Accepted);
            } };
            var adapter = new FalVeoQueueAdapter(() => "key", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new Uploads());
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1/fast").With(options: new FalVeoOptions());
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            var result = await adapter.SubmitPreparedAsync(request, snapshot, () => events.Add("intent"), default, phase);
            Assert.IsType<QueuedSubmitOutcome>(result);
            Assert.Equal(new[] { "intent", "send" }, events);
        }

        [Fact]
        public async Task IntentCallbackPrecedesOnlyGenerationSend()
        {
            var sent = 0;
            var http = new Http { Send = _ => { sent++; return Task.FromResult(Http.Json(200, Accepted)); } };
            var adapter = new FalVeoQueueAdapter(() => "key", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new Uploads());
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1").With(options: new FalVeoOptions());
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            await Assert.ThrowsAsync<InvalidOperationException>(() => adapter.SubmitPreparedAsync(request, snapshot, () => throw new InvalidOperationException("ledger blocked"), default, phase));
            Assert.Equal(0, sent);
        }

        [Fact]
        public async Task QueueUrlsMustMatchRequestAndApplication()
        {
            var requests = 0;
            var http = new Http { Send = _ => { requests++; return Task.FromResult(Http.Json(200, "{}")); } };
            var adapter = new FalVeoQueueAdapter(() => "key", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new Uploads());
            Assert.IsType<FailedStatusOutcome>(await adapter.GetStatusAsync(Handle("fal-ai/other"), default));
            Assert.IsType<FailedCancelOutcome>(await adapter.CancelAsync(Handle("fal-ai/other"), default));
            Assert.IsType<FailedResultOutcome>(await adapter.FetchResultAsync(Handle("fal-ai/other"), default));
            Assert.Equal(0, requests);
        }

        [Theory]
        [InlineData(202, "{\"status\":\"CANCELLATION_REQUESTED\"}", "accepted")]
        [InlineData(400, "{\"status\":\"ALREADY_COMPLETED\"}", "already_completed")]
        [InlineData(404, "{\"status\":\"NOT_FOUND\"}", "not_found")]
        [InlineData(400, "{\"status\":\"different\"}", "failed")]
        [InlineData(202, "{}", "unknown")]
        public async Task CancellationBodyDeterminesCleanupOutcome(int status, string body, string expected)
        {
            var http = new Http { Send = _ => Task.FromResult(Http.Json(status, body)) };
            var adapter = new FalVeoQueueAdapter(() => "key", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new Uploads());
            Assert.Equal(expected, FalVeoQueueAdapter.CleanupOutcome(await adapter.CancelAsync(Handle(), default)));
        }

        [Theory]
        [InlineData(401, true)]
        [InlineData(403, false)]
        public async Task FalCredentialEvidenceDoesNotRequireFallback(int status, bool rejected)
        {
            var http = new Http { Send = _ => Task.FromResult(Http.Json(status, "{\"detail\":\"raw forbidden key text\"}")) };
            var adapter = new FalVeoQueueAdapter(() => "key", new FalApiClient(new HttpClient(http)), FalVeoCompatibilityTests.ActiveCatalog(), new Uploads());
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1").With(options: new FalVeoOptions());
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>());
            var result = Assert.IsType<FailedSubmitOutcome>(await adapter.SubmitPreparedAsync(request, snapshot, () => { }, default, phase));
            Assert.Equal(rejected, VideoCredentialErrors.FromError("fal", result.Error) != null);
            Assert.DoesNotContain("raw forbidden", result.Error.Message);
        }
    }
}
