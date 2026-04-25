using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoProviderTests
    {
        private static VideoGenerationRequest T2vRequest() => new(
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

        private static IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> NoMedia
            = new Dictionary<VideoMediaRef, ResolvedVideoMedia>();

        private static (VeoProvider provider, TestHttpMessageHandler handler) MakeProvider(
            Func<HttpRequestMessage, HttpResponseMessage> onSend,
            string? apiKey = "test-key")
        {
            var handler = new TestHttpMessageHandler { OnSend = onSend };
            var http = new HttpClient(handler);
            var client = new VeoClient(http);
            return (new VeoProvider(() => apiKey, client), handler);
        }

        private static HttpResponseMessage JsonResponse(HttpStatusCode status, string json) =>
            new(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

        // ─── Submit ───────────────────────────────────────────────────

        [Fact]
        public async Task SubmitAsync_happy_path_returns_Ok_with_provider_job_id()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/abc-123\"}"));

            var result = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            Assert.NotNull(result.ProviderJobId);
            Assert.Equal("operations/abc-123", result.ProviderJobId);
            Assert.Equal(VideoJobState.Submitting, result.State);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task SubmitAsync_4xx_maps_to_typed_error()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.BadRequest, "{\"error\":\"bad request\"}"));

            var result = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            Assert.Null(result.ProviderJobId);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task SubmitAsync_missing_api_key_returns_DependencyUnavailable()
        {
            var (provider, _) = MakeProvider(
                _ => JsonResponse(HttpStatusCode.OK, "{}"),
                apiKey: null);

            var result = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            Assert.Equal(VideoErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        // ─── GetStatus ────────────────────────────────────────────────

        [Fact]
        public async Task GetStatusAsync_in_progress_returns_InFlight_Polling()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"done\":false}"));

            var result = await provider.GetStatusAsync(
                "operations/abc", CancellationToken.None);

            Assert.Equal(VideoJobState.Polling, result.State);
            Assert.Null(result.ProviderResultToken);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task GetStatusAsync_done_with_uri_returns_Complete_with_token()
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
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, json));

            var result = await provider.GetStatusAsync(
                "operations/abc", CancellationToken.None);

            Assert.Equal(VideoJobState.Complete, result.State);
            Assert.Equal("https://veo/result/xyz", result.ProviderResultToken);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task GetStatusAsync_operation_error_returns_terminal_failure()
        {
            var json = """
                {
                  "done": true,
                  "error": { "code": 13, "message": "Internal" }
                }
                """;
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, json));

            var result = await provider.GetStatusAsync(
                "operations/abc", CancellationToken.None);

            Assert.Equal(VideoJobState.Error, result.State);
            Assert.NotNull(result.Error);
        }

        [Fact]
        public async Task GetStatusAsync_empty_provider_job_id_returns_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"done\":false}"));

            var result = await provider.GetStatusAsync(
                "", CancellationToken.None);

            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── Cancel ───────────────────────────────────────────────────

        [Fact]
        public async Task CancelAsync_2xx_returns_Cancelled()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{}"));

            var result = await provider.CancelAsync(
                "operations/abc", CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task CancelAsync_404_returns_typed_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.NotFound, "{\"error\":\"not found\"}"));

            var result = await provider.CancelAsync(
                "operations/abc", CancellationToken.None);

            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── FetchResult ──────────────────────────────────────────────

        [Fact]
        public async Task FetchResultAsync_with_token_downloads_bytes()
        {
            var payload = new byte[] { 0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70 };
            var (provider, _) = MakeProvider(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(payload),
                });

            var result = await provider.FetchResultAsync(
                "operations/abc",
                providerResultToken: "https://veo/r/x.mp4",
                CancellationToken.None);

            Assert.Equal(payload, result.Bytes);
            Assert.Equal("video/mp4", result.MimeType);
            Assert.Null(result.Error);
        }

        [Fact]
        public async Task FetchResultAsync_without_token_returns_InvalidRequest()
        {
            // Veo requires the token (videoUri); manager must persist
            // and pass it back. Null token surfaces as a typed error
            // rather than a network call attempt.
            var (provider, handler) = MakeProvider(_ =>
                new HttpResponseMessage(HttpStatusCode.OK));

            var result = await provider.FetchResultAsync(
                "operations/abc",
                providerResultToken: null,
                CancellationToken.None);

            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Null(result.Bytes);
            Assert.Empty(handler.Requests);  // never called the network
        }

        [Fact]
        public async Task FetchResultAsync_4xx_maps_to_typed_error()
        {
            var (provider, _) = MakeProvider(_ =>
                new HttpResponseMessage(HttpStatusCode.Forbidden));

            var result = await provider.FetchResultAsync(
                "operations/abc",
                providerResultToken: "https://veo/r/x.mp4",
                CancellationToken.None);

            // EnsureSuccessStatusCode throws HttpRequestException → caught →
            // mapped to NetworkError, which is DependencyUnavailable.
            Assert.Equal(VideoErrorCode.DependencyUnavailable, result.Error!.Code);
        }

        // ─── Constructor ──────────────────────────────────────────────

        [Fact]
        public void Constructor_rejects_null_apiKeyProvider()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new VeoProvider(null!));
        }
    }
}
