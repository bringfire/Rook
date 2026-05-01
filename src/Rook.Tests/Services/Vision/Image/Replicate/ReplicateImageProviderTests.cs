using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageProviderTests
    {
        [Fact]
        public async Task SubmitAsync_missing_token_returns_dependency_failure_without_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(" ", handler);

            var outcome = await provider.SubmitAsync(
                Request(),
                EmptyMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("Replicate API token is not configured", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_wrong_options_type_returns_invalid_request_without_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(options: new GeminiImageOptions()),
                EmptyMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("options", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_reference_images_fail_before_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(referenceImages: new[]
                {
                    MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage),
                }),
                EmptyMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("reference_image_paths", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_wrong_model_fails_before_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(model: "replicate/other-model"),
                EmptyMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("model", failed.Error.Field);
            Assert.Contains("Unknown Replicate image model", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_posts_official_model_endpoint_and_exact_body()
        {
            string? requestBody = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    requestBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-1",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-1",
                            "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(aspectRatio: ""),
                EmptyMedia(),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8-test-token", request.Headers.Authorization.Parameter);

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(requestBody!));
            Assert.Equal(new[] { "input" }, root.Select(kvp => kvp.Key).OrderBy(k => k));
            var input = Assert.IsType<JsonObject>(root["input"]);
            Assert.Equal(
                new[] { "aspect_ratio", "num_outputs", "output_format", "prompt" },
                input.Select(kvp => kvp.Key).OrderBy(k => k));
            Assert.Equal("sunlit massing study", input["prompt"]!.GetValue<string>());
            Assert.Equal("1:1", input["aspect_ratio"]!.GetValue<string>());
            Assert.Equal(1, input["num_outputs"]!.GetValue<int>());
            Assert.Equal("png", input["output_format"]!.GetValue<string>());
            Assert.DoesNotContain("resolution", requestBody);
            Assert.DoesNotContain("reference", requestBody);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-1", queued.Handle.ProviderJobId);
            Assert.Equal("POST", queued.Handle.CancelHttpMethod);
            Assert.Null(queued.Handle.ResponseUrl);
        }

        [Theory]
        [InlineData("starting", GenerationLifecycleState.Pending)]
        [InlineData("processing", GenerationLifecycleState.Running)]
        public async Task GetStatusAsync_maps_inflight_states_through_replicate_lifecycle_mapper(
            string status,
            GenerationLifecycleState expected)
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, $$"""
                    { "id": "pred-1", "status": "{{status}}" }
                    """),
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            var inflight = Assert.IsType<InFlightStatusOutcome>(outcome);
            Assert.Equal(expected, inflight.State);
        }

        [Fact]
        public async Task GetStatusAsync_maps_succeeded_through_replicate_lifecycle_mapper()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, """
                    {
                      "id": "pred-1",
                      "status": "succeeded",
                      "output": "https://replicate.delivery/pbxt/out.png"
                    }
                    """),
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal(
                "https://replicate.delivery/pbxt/out.png",
                complete.UpdatedHandle.ProviderResultToken);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/predictions/pred-1",
                request.RequestUri!.ToString());
        }

        [Fact]
        public async Task GetStatusAsync_maps_failed_prediction_to_failed_status()
        {
            var provider = Provider("r8-test-token", StatusHandler("failed", "model execution failed"));

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("failed", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task GetStatusAsync_maps_canceled_prediction_to_cancelled_status()
        {
            var provider = Provider("r8-test-token", StatusHandler("canceled", "user canceled"));

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.Cancelled, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Equal("canceled", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task GetStatusAsync_non_success_maps_http_failure()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json((HttpStatusCode)429, """{ "detail": "rate limited" }"""),
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.QuotaExceeded, failed.Error.Code);
            Assert.Equal("429", failed.Error.ProviderErrorCode);
        }

        [Fact]
        public async Task CancelAsync_posts_replicate_cancel_endpoint()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, """{ "id": "pred-1", "status": "canceled" }"""),
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.CancelAsync(
                new ProviderJobHandle("pred-1"),
                CancellationToken.None);

            Assert.IsType<CanceledOutcome>(outcome);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/predictions/pred-1/cancel",
                request.RequestUri!.ToString());
        }

        private static ReplicateImageProvider Provider(
            string? token,
            TestHttpMessageHandler handler) =>
            new(
                () => token,
                new ReplicateApiClient(new HttpClient(handler)));

        private static TestHttpMessageHandler StatusHandler(string status, string error) =>
            new()
            {
                OnSend = _ => Json(HttpStatusCode.OK, $$"""
                    { "id": "pred-1", "status": "{{status}}", "error": "{{error}}" }
                    """),
            };

        private static ImageGenerationRequest Request(
            string model = ReplicateImageCapabilities.FluxSchnell,
            string aspectRatio = "1:1",
            ProviderOptions? options = null,
            System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: model,
                Prompt: "sunlit massing study",
                Resolution: "1K",
                AspectRatio: aspectRatio,
                NumberOfImages: 1,
                ReferenceImages: referenceImages,
                Options: options ?? new ReplicateImageOptions());

        private static System.Collections.Generic.IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
            new System.Collections.Generic.Dictionary<MediaRef, ResolvedMedia>();

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };
    }
}
