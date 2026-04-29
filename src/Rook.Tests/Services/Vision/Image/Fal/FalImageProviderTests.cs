using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Gemini;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public class FalImageProviderTests
    {
        [Fact]
        public async Task SubmitAsync_missing_api_key_returns_dependency_failure_without_http_call()
        {
            var (provider, handler) = MakeProvider(
                _ => JsonResponse(HttpStatusCode.OK, "{}"),
                apiKey: " ");

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("fal API key is not configured", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_null_request_returns_invalid_request_field_request()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                null!,
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("request", failed.Error.Field);
            Assert.False(failed.Error.Retryable);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_wrong_options_type_returns_invalid_request_field_options()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request() with { Options = new GeminiImageOptions() },
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("options", failed.Error.Field);
            Assert.False(failed.Error.Retryable);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_success_posts_flux_schnell_request_without_image_bytes()
        {
            string? capturedBody = null;
            string? authScheme = null;
            string? authParameter = null;
            var (provider, handler) = MakeProvider(req =>
            {
                capturedBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                authScheme = req.Headers.Authorization!.Scheme;
                authParameter = req.Headers.Authorization.Parameter;
                return JsonResponse(HttpStatusCode.OK, """
                    {
                      "images": [
                        {
                          "url": "https://fal.media/files/result.jpg",
                          "content_type": "image/jpeg",
                          "width": 1536,
                          "height": 864
                        }
                      ],
                      "seed": 12345,
                      "prompt": "sunlit massing study",
                      "timings": { "inference": 0.42 },
                      "has_nsfw_concepts": [false]
                    }
                    """);
            });

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://fal.run/fal-ai/flux/schnell", request.RequestUri!.ToString());
            Assert.Equal("Key", authScheme);
            Assert.Equal("test-key", authParameter);

            Assert.NotNull(capturedBody);
            var body = JsonNode.Parse(capturedBody!)!.AsObject();
            Assert.Equal("sunlit massing study", body["prompt"]!.GetValue<string>());
            Assert.Equal("landscape_16_9", body["image_size"]!.GetValue<string>());
            Assert.Equal(1, body["num_images"]!.GetValue<int>());
            Assert.True(body["enable_safety_checker"]!.GetValue<bool>());
            Assert.Equal("jpeg", body["output_format"]!.GetValue<string>());
            Assert.False(body["sync_mode"]!.GetValue<bool>());
            Assert.DoesNotContain("CQgH", capturedBody);
            Assert.DoesNotContain("BgUE", capturedBody);
            Assert.DoesNotContain("image/png", capturedBody);
            Assert.DoesNotContain("reference", capturedBody);

            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            var success = Assert.IsType<SuccessResultOutcome>(sync.Result);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(ImageMediaRoles.Image, artifact.Role);
            Assert.Equal("image/jpeg", artifact.DeclaredMimeType);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://fal.media/files/result.jpg", remote.Url.ToString());
            Assert.Equal("https://fal.media/files/result.jpg", artifact.ProviderMetadata["url"]!.GetValue<string>());
            Assert.Equal(1536, artifact.ProviderMetadata["width"]!.GetValue<int>());
            Assert.Equal(864, artifact.ProviderMetadata["height"]!.GetValue<int>());
            Assert.Equal(12345, success.Envelope.EnvelopeMetadata["seed"]!.GetValue<int>());
            Assert.Equal("sunlit massing study", success.Envelope.EnvelopeMetadata["prompt"]!.GetValue<string>());
            Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("timings"));
            Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("has_nsfw_concepts"));
        }

        [Fact]
        public async Task SubmitAsync_non_success_maps_through_fal_error_mapper()
        {
            var (provider, _) = MakeProvider(_ =>
            {
                var response = JsonResponse((HttpStatusCode)429, "{\"detail\":\"slow down\"}");
                response.Headers.TryAddWithoutValidation("x-fal-needs-retry", "true");
                return response;
            });

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.QuotaExceeded, failed.Error.Code);
            Assert.Equal("429", failed.Error.ProviderErrorCode);
            Assert.True(failed.Error.Retryable);
            Assert.Equal("fal request failed with HTTP 429.", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_invalid_aspect_ratio_returns_typed_invalid_request()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request() with { AspectRatio = "2:1" },
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("aspect_ratio", failed.Error.Field);
            Assert.False(failed.Error.Retryable);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_transport_http_request_exception_returns_retryable_dependency_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                throw new HttpRequestException("connect failed; key=test-key body={secret}"));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
            Assert.DoesNotContain("test-key", failed.Error.Message);
            Assert.DoesNotContain("{secret}", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_timeout_returns_retryable_dependency_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                throw new TaskCanceledException("request timed out"));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
            Assert.Contains("timed out", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_caller_cancellation_returns_interrupted_failure()
        {
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                cts.Token);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.Interrupted, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("cancelled", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_malformed_json_returns_sync_result_failure_without_raw_body()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"images\":["));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = AssertFailedResult(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.DoesNotContain("{\"images\":[", failed.Error.Message);
        }

        [Theory]
        [InlineData("{}")]
        [InlineData("{\"images\":42}")]
        public async Task SubmitAsync_missing_images_returns_sync_result_failure(string responseJson)
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, responseJson));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = AssertFailedResult(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("images", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_empty_images_returns_sync_result_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, "{\"images\":[]}"));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = AssertFailedResult(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("images", failed.Error.Message);
        }

        [Theory]
        [InlineData("{\"images\":[{}]}")]
        [InlineData("{\"images\":[{\"url\":42}]}")]
        [InlineData("{\"images\":[{\"url\":\"not-a-url\"}]}")]
        public async Task SubmitAsync_missing_or_invalid_image_url_returns_sync_result_failure(string responseJson)
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, responseJson));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = AssertFailedResult(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("url", failed.Error.Message);
        }

        [Fact]
        public async Task SubmitAsync_non_http_image_url_returns_sync_result_failure()
        {
            var (provider, _) = MakeProvider(_ =>
                JsonResponse(HttpStatusCode.OK, """
                    {
                      "images": [
                        { "url": "file:///C:/temp/result.jpg" }
                      ]
                    }
                    """));

            var outcome = await provider.SubmitAsync(
                Request(),
                ResolvedImages(),
                CancellationToken.None);

            var failed = AssertFailedResult(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Contains("http", failed.Error.Message);
        }

        [Fact]
        public async Task Sync_only_methods_throw_invalid_operation()
        {
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            var handle = new ProviderJobHandle("job-1");

            await Assert.ThrowsAsync<InvalidOperationException>(
                async () => await provider.GetStatusAsync(handle, CancellationToken.None));
            await Assert.ThrowsAsync<InvalidOperationException>(
                async () => await provider.CancelAsync(handle, CancellationToken.None));
            await Assert.ThrowsAsync<InvalidOperationException>(
                async () => await provider.FetchResultAsync(handle, CancellationToken.None));
        }

        private static FailedResultOutcome AssertFailedResult(ProviderSubmitOutcome outcome)
        {
            var sync = Assert.IsType<SyncSubmitOutcome>(outcome);
            return Assert.IsType<FailedResultOutcome>(sync.Result);
        }

        private static ImageGenerationRequest Request() =>
            new(
                Model: FalImageCapabilities.FluxSchnell,
                Prompt: "sunlit massing study",
                Resolution: "1K",
                AspectRatio: "16:9",
                NumberOfImages: 1,
                ReferenceImages: new[]
                {
                    MediaRef.ForPath("C:/tmp/reference.png", ImageMediaRoles.ReferenceImage),
                },
                Options: new FalImageOptions());

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedImages()
        {
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var reference = MediaRef.ForPath("C:/tmp/reference.png", ImageMediaRoles.ReferenceImage);
            return new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = new ResolvedMedia(new byte[] { 9, 8, 7 }, "image/png"),
                [reference] = new ResolvedMedia(new byte[] { 6, 5, 4 }, "image/png"),
            };
        }

        private static (FalImageProvider provider, TestHttpMessageHandler handler) MakeProvider(
            Func<HttpRequestMessage, HttpResponseMessage> onSend,
            string? apiKey = "test-key")
        {
            var handler = new TestHttpMessageHandler { OnSend = onSend };
            var client = new FalApiClient(new HttpClient(handler));
            return (new FalImageProvider(() => apiKey, client), handler);
        }

        private static HttpResponseMessage JsonResponse(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };
    }
}
