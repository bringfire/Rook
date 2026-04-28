using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoClientTests
    {
        private const string ApiKey = "test-key";

        private static VideoGenerationRequest T2vRequest() =>
            TestVideoFixtures.DefaultT2vRequest();

        private static VeoOptions T2vOptions() =>
            new(PersonGenerationPolicy.AllowAll);

        private static VideoGenerationRequest I2vRequest(MediaRef start) =>
            TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                resolution: "1080p",
                prompt: "camera pushes forward",
                startFrame: start,
                personGeneration: PersonGenerationPolicy.AllowAdult);

        private static VeoOptions I2vOptions() =>
            new(PersonGenerationPolicy.AllowAdult);

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> NoMedia
            = new Dictionary<MediaRef, ResolvedMedia>();

        private static (VeoClient client, TestHttpMessageHandler handler) MakeClient(
            Func<HttpRequestMessage, HttpResponseMessage> onSend)
        {
            var handler = new TestHttpMessageHandler { OnSend = onSend };
            var http = new HttpClient(handler);
            return (new VeoClient(http), handler);
        }

        private static HttpResponseMessage JsonResponse(HttpStatusCode status, string json) =>
            new(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

        // ─── Start: happy path ────────────────────────────────────────

        [Fact]
        public async Task StartGenerationAsync_2xx_returns_operation_name()
        {
            var (client, handler) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/abc-123\"}"));

            var resp = await client.StartGenerationAsync(
                ApiKey, T2vRequest(), T2vOptions(), NoMedia, CancellationToken.None);

            Assert.True(resp.Success);
            Assert.Equal("operations/abc-123", resp.OperationName);
            var req = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, req.Method);
            Assert.Contains(":predictLongRunning", req.RequestUri!.ToString());
            Assert.True(req.Headers.Contains("x-goog-api-key"));
        }

        [Fact]
        public async Task StartGenerationAsync_400_returns_failure_with_body()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.BadRequest, "{\"error\":\"bad request body\"}"));

            var resp = await client.StartGenerationAsync(
                ApiKey, T2vRequest(), T2vOptions(), NoMedia, CancellationToken.None);

            Assert.False(resp.Success);
            Assert.Equal(400, resp.StatusCode);
            Assert.Contains("bad request body", resp.ErrorBody);
        }

        [Fact]
        public async Task StartGenerationAsync_2xx_without_name_field_returns_failure()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"unexpected\":true}"));

            var resp = await client.StartGenerationAsync(
                ApiKey, T2vRequest(), T2vOptions(), NoMedia, CancellationToken.None);

            Assert.False(resp.Success);
            Assert.Contains("missing 'name'", resp.ErrorBody);
        }

        [Fact]
        public async Task StartGenerationAsync_includes_resolved_media_for_i2v()
        {
            string? capturedBody = null;
            var (client, _) = MakeClient(req =>
            {
                capturedBody = req.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/abc\"}");
            });

            var startRef = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.Image);
            var resolved = new Dictionary<MediaRef, ResolvedMedia>
            {
                [startRef] = new ResolvedMedia(
                    Bytes: new byte[] { 0x89, 0x50, 0x4E, 0x47 },
                    MimeType: "image/png"),
            };

            await client.StartGenerationAsync(
                ApiKey, I2vRequest(startRef), I2vOptions(), resolved, CancellationToken.None);

            Assert.NotNull(capturedBody);
            Assert.Contains("bytesBase64Encoded", capturedBody);
            Assert.Contains("image/png", capturedBody);
            Assert.Contains("\"image\":", capturedBody);  // i2v top-level "image" key
        }

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAll, "allow_all")]
        [InlineData(PersonGenerationPolicy.AllowAdult, "allow_adult")]
        [InlineData(PersonGenerationPolicy.DontAllow, "dont_allow")]
        public async Task StartGenerationAsync_personGeneration_string_matches_codec_serialization(
            PersonGenerationPolicy policy, string expected)
        {
            // L3: VeoClient.MapPersonGeneration (Veo HTTP body shape) and
            // VeoOptionsCodec.Serialize (persisted ledger shape) happen to
            // emit the same enum strings, but they're independent contracts.
            // Drift between them would corrupt either the wire payload or
            // the audit record. This test pins both layers' agreement.
            string? capturedBody = null;
            var (client, _) = MakeClient(req =>
            {
                capturedBody = req.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/x\"}");
            });

            // Choose a request shape valid for the requested policy on
            // some Veo model — Veo 2 T2V accepts any policy.
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-2.0-generate-001",
                resolution: "720p",
                personGeneration: policy);
            var options = new VeoOptions(policy);

            await client.StartGenerationAsync(ApiKey, req, options, NoMedia, CancellationToken.None);

            Assert.NotNull(capturedBody);
            // Wire body uses the same string the codec would serialize.
            Assert.Contains($"\"personGeneration\":\"{expected}\"", capturedBody);

            // Cross-check: codec produces the same string for the
            // persisted shape (different JSON key, same value).
            var codecJson = new VeoOptionsCodec().Serialize(options);
            Assert.Equal(expected, codecJson["person_generation"]?.GetValue<string>());
        }

        [Fact]
        public async Task StartGenerationAsync_omits_resolution_for_veo2()
        {
            string? capturedBody = null;
            var (client, _) = MakeClient(req =>
            {
                capturedBody = req.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/x\"}");
            });

            var veo2 = T2vRequest() with { Model = "veo-2.0-generate-001" };

            await client.StartGenerationAsync(ApiKey, veo2, T2vOptions(), NoMedia, CancellationToken.None);

            Assert.NotNull(capturedBody);
            Assert.DoesNotContain("\"resolution\"", capturedBody);
        }

        // ─── Poll ─────────────────────────────────────────────────────

        [Fact]
        public async Task PollOperationAsync_done_false_returns_in_progress()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"done\":false}"));

            var resp = await client.PollOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.True(resp.Success);
            Assert.False(resp.Done);
            Assert.Null(resp.VideoUri);
        }

        [Fact]
        public async Task PollOperationAsync_done_true_with_uri_in_generatedVideos_returns_uri()
        {
            var json = """
                {
                  "done": true,
                  "response": {
                    "generatedVideos": [
                      { "video": { "uri": "https://veo/result/xyz" } }
                    ]
                  }
                }
                """;
            var (client, _) = MakeClient(_ => JsonResponse(HttpStatusCode.OK, json));

            var resp = await client.PollOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.True(resp.Success);
            Assert.True(resp.Done);
            Assert.Equal("https://veo/result/xyz", resp.VideoUri);
        }

        [Fact]
        public async Task PollOperationAsync_done_true_with_uri_in_generateVideoResponse_returns_uri()
        {
            // Alternate documented response shape (curl docs).
            var json = """
                {
                  "done": true,
                  "response": {
                    "generateVideoResponse": {
                      "generatedSamples": [
                        { "video": { "uri": "https://veo/alt/abc" } }
                      ]
                    }
                  }
                }
                """;
            var (client, _) = MakeClient(_ => JsonResponse(HttpStatusCode.OK, json));

            var resp = await client.PollOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.True(resp.Success);
            Assert.Equal("https://veo/alt/abc", resp.VideoUri);
        }

        [Fact]
        public async Task PollOperationAsync_operation_error_returns_failure()
        {
            var json = """
                {
                  "done": true,
                  "error": { "code": 13, "message": "Internal error" }
                }
                """;
            var (client, _) = MakeClient(_ => JsonResponse(HttpStatusCode.OK, json));

            var resp = await client.PollOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.False(resp.Success);
            Assert.True(resp.Done);
            Assert.Contains("Internal error", resp.ErrorBody);
        }

        [Fact]
        public async Task PollOperationAsync_http_error_returns_failure()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.Unauthorized, "{\"error\":\"bad key\"}"));

            var resp = await client.PollOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.False(resp.Success);
            Assert.Equal(401, resp.StatusCode);
        }

        // ─── Cancel ───────────────────────────────────────────────────

        [Fact]
        public async Task CancelOperationAsync_2xx_returns_success()
        {
            var (client, handler) = MakeClient(_ => new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
            });

            var resp = await client.CancelOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.True(resp.Success);
            var req = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, req.Method);
            Assert.Contains(":cancel", req.RequestUri!.ToString());
        }

        [Fact]
        public async Task CancelOperationAsync_4xx_returns_failure()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.NotFound, "{\"error\":\"no such op\"}"));

            var resp = await client.CancelOperationAsync(
                ApiKey, "operations/abc", CancellationToken.None);

            Assert.False(resp.Success);
            Assert.Equal(404, resp.StatusCode);
        }

        // ─── Download ─────────────────────────────────────────────────

        [Fact]
        public async Task DownloadVideoAsync_returns_bytes()
        {
            var payload = new byte[] { 0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70 };
            var (client, _) = MakeClient(_ => new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(payload),
            });

            var bytes = await client.DownloadVideoAsync(
                ApiKey, "https://veo/r/x.mp4", CancellationToken.None);

            Assert.Equal(payload, bytes);
        }

        [Fact]
        public async Task DownloadVideoAsync_4xx_throws()
        {
            var (client, _) = MakeClient(_ =>
                new HttpResponseMessage(HttpStatusCode.Forbidden));

            await Assert.ThrowsAsync<HttpRequestException>(
                async () => await client.DownloadVideoAsync(
                    ApiKey, "https://veo/r/x.mp4", CancellationToken.None));
        }

        // ─── Cancellation propagation ─────────────────────────────────

        [Fact]
        public async Task PollOperationAsync_honors_cancellation()
        {
            var (client, _) = MakeClient(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"done\":false}"));

            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(
                async () => await client.PollOperationAsync(
                    ApiKey, "operations/abc", cts.Token));
        }
    }
}
