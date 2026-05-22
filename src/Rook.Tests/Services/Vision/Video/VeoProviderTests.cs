using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoProviderTests
    {
        private static VideoGenerationRequest T2vRequest() =>
            TestVideoFixtures.DefaultT2vRequest();

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> NoMedia
            = new Dictionary<MediaRef, ResolvedMedia>();

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

            var outcome = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("operations/abc-123", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Fact]
        public async Task SubmitAsync_generic_happy_path_returns_Queued_never_Sync()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/abc-123\"}"));

            var outcome = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("operations/abc-123", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Fact]
        public async Task SubmitAsync_4xx_maps_to_typed_error()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.BadRequest, "{\"error\":\"bad request\"}"));

            var outcome = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        [Fact]
        public async Task SubmitAsync_missing_api_key_returns_DependencyUnavailable()
        {
            var (provider, _) = MakeProvider(
                _ => JsonResponse(HttpStatusCode.OK, "{}"),
                apiKey: null);

            var outcome = await provider.SubmitAsync(
                T2vRequest(), NoMedia, CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
        }

        // ─── GetStatus ────────────────────────────────────────────────

        [Fact]
        public async Task GetStatusAsync_in_progress_returns_InFlight_Polling()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"done\":false}"));

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            var inFlight = Assert.IsType<InFlightStatusOutcome>(outcome);
            Assert.Equal(GenerationLifecycleState.Running, inFlight.State);
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

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal(
                "https://veo/result/xyz",
                complete.UpdatedHandle.ProviderResultToken);
        }

        [Fact]
        public async Task GetStatusAsync_done_with_sidecar_like_fields_keeps_only_video_uri_token()
        {
            var json = """
                {
                  "done": true,
                  "response": {
                    "generateVideoResponse": {
                      "generatedSamples": [
                        {
                          "video": { "uri": "https://veo/result/xyz" },
                          "posterUrl": "https://provider.invalid/poster.jpg",
                          "thumbnail": { "uri": "https://provider.invalid/thumb.jpg" },
                          "firstFrame": { "uri": "https://provider.invalid/first.jpg" },
                          "lastFrame": { "uri": "https://provider.invalid/last.jpg" }
                        }
                      ]
                    }
                  }
                }
                """;
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, json));

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal(
                "https://veo/result/xyz",
                complete.UpdatedHandle.ProviderResultToken);
            Assert.Null(complete.UpdatedHandle.ProviderMetadata);
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

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            Assert.IsType<FailedStatusOutcome>(outcome);
        }

        [Fact]
        public void ProviderJobHandle_empty_provider_job_id_throws()
        {
            Assert.Throws<ArgumentException>(() => new ProviderJobHandle(""));
        }

        // ─── Cancel ───────────────────────────────────────────────────

        [Fact]
        public async Task CancelAsync_2xx_returns_Cancelled()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.CancelAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            Assert.IsType<CanceledOutcome>(outcome);
        }

        [Fact]
        public async Task CancelAsync_404_returns_typed_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.NotFound, "{\"error\":\"not found\"}"));

            var outcome = await provider.CancelAsync(
                new ProviderJobHandle("operations/abc"), CancellationToken.None);

            var failed = Assert.IsType<FailedCancelOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
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

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle(
                    "operations/abc",
                    providerResultToken: "https://veo/r/x.mp4"),
                CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            var body = Assert.IsType<InlineArtifactBody>(artifact.Body);
            Assert.Equal(payload, body.Bytes);
            Assert.Equal("video/mp4", artifact.DeclaredMimeType);
        }

        [Fact]
        public async Task FetchResultAsync_without_token_returns_InvalidRequest()
        {
            // Veo requires the token (videoUri); manager must persist
            // and pass it back. Null token surfaces as a typed error
            // rather than a network call attempt.
            var (provider, handler) = MakeProvider(_ =>
                new HttpResponseMessage(HttpStatusCode.OK));

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle("operations/abc"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("providerResultToken", failed.Error.Field);
            Assert.Empty(handler.Requests);  // never called the network
        }

        [Fact]
        public async Task FetchResultAsync_4xx_maps_to_typed_error()
        {
            var (provider, _) = MakeProvider(_ =>
                new HttpResponseMessage(HttpStatusCode.Forbidden));

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle(
                    "operations/abc",
                    providerResultToken: "https://veo/r/x.mp4"),
                CancellationToken.None);

            // EnsureSuccessStatusCode throws HttpRequestException → caught →
            // mapped to NetworkError, which is DependencyUnavailable.
            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
        }

        // ─── Options mismatch (V1c provider boundary totality) ───────

        [Fact]
        public async Task SubmitAsync_with_non_VeoOptions_returns_typed_InvalidRequest()
        {
            // Per V1c review Finding 2: provider boundary stays total.
            // A request reaching VeoProvider with non-VeoOptions is a
            // programming error (registry bypass), but surfaces as a
            // typed envelope rather than throwing.
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"name\":\"operations/abc\"}"));
            var bad = T2vRequest().With(options: new ForeignProviderOptions());

            var outcome = await provider.SubmitAsync(
                bad, NoMedia, CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("Options", failed.Error.Field);
            Assert.Contains(nameof(VeoOptions), failed.Error.Message);
        }

        // Test-only ProviderOptions subtype to exercise the cast guard.
        private sealed class ForeignProviderOptions : ProviderOptions
        {
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
