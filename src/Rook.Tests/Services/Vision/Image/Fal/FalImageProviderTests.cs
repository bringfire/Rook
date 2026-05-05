using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
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

        [Theory]
        [InlineData("openai/gpt-image-2")]
        [InlineData("fal-ai/flux/schnel")]
        public async Task SubmitAsync_unknown_model_fails_before_http_call(string model)
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request(model: model),
                ResolvedImages(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("model", failed.Error.Field);
            Assert.Contains(model, failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_gpt_image_2_prompt_only_fails_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                EmptyMedia(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains(
                "GPT Image 2 Edit requires exactly one source image",
                failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_gpt_image_2_rejects_reference_image_roles_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var reference = MediaRef.ForPath(
                "C:/tmp/ref.png",
                ImageMediaRoles.ReferenceImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMedia(),
                [reference] = PngMedia(),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: new[] { reference }),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal("reference_image_paths", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_gpt_image_2_rejects_oversized_source_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            var bytes = PngBytes();
            Array.Resize(ref bytes, 1024 * 1024 + 1);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    new(bytes, "image/png"),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("GPT Image 2 Edit data URI upload", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("image/gif", new byte[] { 0x47, 0x49, 0x46, 0x38 })]
        [InlineData("application/octet-stream", new byte[] { 0x01, 0x02, 0x03 })]
        public async Task SubmitAsync_gpt_image_2_rejects_unsupported_mime_before_http_call(
            string declaredMime,
            byte[] bytes)
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    new(bytes, declaredMime),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("PNG, JPEG, or WebP", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_gpt_image_2_rejects_declared_mime_mismatch_before_http_call()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, "{}"));
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    new(PngBytes(), "image/jpeg"),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("MIME does not match", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_gpt_image_2_posts_queue_request_with_data_uri_and_request_id_only_handle()
        {
            string? capturedBody = null;
            var (provider, handler) = MakeProvider(req =>
            {
                capturedBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                return JsonResponse(HttpStatusCode.Created, """
                    {
                      "request_id": "fal-gpt-1",
                      "status_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/status",
                      "response_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/response",
                      "cancel_url": "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/cancel",
                      "queue_position": 0
                    }
                    """);
            });
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    PngMedia(),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                media,
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://queue.fal.run/openai/gpt-image-2/edit",
                request.RequestUri!.ToString());

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(capturedBody!));
            Assert.Equal("sunlit massing study", root["prompt"]!.GetValue<string>());
            Assert.Equal("auto", root["image_size"]!.GetValue<string>());
            Assert.Equal("high", root["quality"]!.GetValue<string>());
            Assert.Equal(1, root["num_images"]!.GetValue<int>());
            Assert.Equal("png", root["output_format"]!.GetValue<string>());
            Assert.False(root.ContainsKey("sync_mode"));
            Assert.False(root.ContainsKey("mask_url"));

            var urls = Assert.IsType<JsonArray>(root["image_urls"]);
            var dataUri = Assert.Single(urls)!.GetValue<string>();
            Assert.StartsWith(
                "data:image/png;base64,",
                dataUri,
                StringComparison.Ordinal);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("fal-gpt-1", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.StatusUrl);
            Assert.Null(queued.Handle.ResponseUrl);
            Assert.Null(queued.Handle.CancelUrl);
            Assert.Null(queued.Handle.ProviderMetadata);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Theory]
        [InlineData("https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1")]
        [InlineData("data:image/png;base64,AAAA")]
        [InlineData("{\"request_id\":\"fal-gpt-1\"}")]
        [InlineData("fal-gpt-1/response")]
        public async Task SubmitAsync_gpt_image_2_rejects_unsafe_request_id_before_handle_persistence(
            string requestId)
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.Created, $$"""
                { "request_id": {{JsonValue.Create(requestId)!.ToJsonString()}} }
                """));
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage)] =
                    PngMedia(),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: FalImageCapabilities.GptImage2Edit,
                    resolution: "auto",
                    aspectRatio: "match_input_image",
                    referenceImages: Array.Empty<MediaRef>()),
                media,
                CancellationToken.None);

            Assert.Single(handler.Requests);
            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.Equal("provider_job_id", failed.Error.Field);
            Assert.DoesNotContain(requestId, failed.Error.Message);
        }

        [Theory]
        [InlineData("IN_QUEUE", typeof(InFlightStatusOutcome))]
        [InlineData("IN_PROGRESS", typeof(InFlightStatusOutcome))]
        [InlineData("COMPLETED", typeof(ProviderCompleteStatusOutcome))]
        public async Task GetStatusAsync_gpt_image_2_reconstructs_status_url_and_maps_state(
            string state,
            Type expectedType)
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, $$"""
                { "status": "{{state}}", "request_id": "fal-gpt-1", "queue_position": 1 }
                """));

            var outcome = await ((IModelAwareImageProvider)provider).GetStatusAsync(
                FalImageCapabilities.GptImage2Edit,
                new ProviderJobHandle("fal-gpt-1"),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(
                "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/status",
                request.RequestUri!.ToString());
            Assert.IsType(expectedType, outcome);
        }

        [Fact]
        public async Task FetchResultAsync_gpt_image_2_parses_exactly_one_image_url_without_provider_metadata()
        {
            var (provider, handler) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, """
                {
                  "images": [
                    {
                      "url": "https://v3.fal.media/files/result.png",
                      "content_type": "image/png",
                      "width": 1024,
                      "height": 1024
                    }
                  ],
                  "prompt": "do not persist this",
                  "seed": 42
                }
                """));

            var outcome = await ((IModelAwareImageProvider)provider).FetchResultAsync(
                FalImageCapabilities.GptImage2Edit,
                new ProviderJobHandle("fal-gpt-1"),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(
                "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/response",
                request.RequestUri!.ToString());

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(ImageMediaRoles.Image, artifact.Role);
            Assert.Equal("image/png", artifact.DeclaredMimeType);
            Assert.Empty(artifact.ProviderMetadata);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://v3.fal.media/files/result.png", remote.Url.ToString());
            Assert.Empty(success.Envelope.EnvelopeMetadata);

            var serializedMetadata = JsonSerializer.Serialize(new
            {
                artifact.ProviderMetadata,
                success.Envelope.EnvelopeMetadata,
            });
            Assert.DoesNotContain("fal.media", serializedMetadata);
            Assert.DoesNotContain("image_urls", serializedMetadata);
            Assert.DoesNotContain("request_id", serializedMetadata);
            Assert.DoesNotContain("prompt", serializedMetadata);
        }

        [Fact]
        public async Task CancelAsync_gpt_image_2_reconstructs_cancel_url_and_maps_accepted()
        {
            var (provider, handler) = MakeProvider(_ =>
                JsonResponse(
                    HttpStatusCode.Accepted,
                    "{ \"status\": \"CANCELLATION_REQUESTED\" }"));

            var outcome = await ((IModelAwareImageProvider)provider).CancelAsync(
                FalImageCapabilities.GptImage2Edit,
                new ProviderJobHandle("fal-gpt-1"),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Put, request.Method);
            Assert.Equal(
                "https://queue.fal.run/openai/gpt-image-2/requests/fal-gpt-1/cancel",
                request.RequestUri!.ToString());
            Assert.IsType<CanceledOutcome>(outcome);
        }

        [Theory]
        [InlineData("{ \"images\": [] }")]
        [InlineData("{ \"images\": [ { \"url\": \"https://v3.fal.media/a.png\" }, { \"url\": \"https://v3.fal.media/b.png\" } ] }")]
        [InlineData("{ \"images\": [ { } ] }")]
        [InlineData("{ \"images\": [ { \"url\": \"file:///C:/tmp/result.png\" } ] }")]
        public async Task FetchResultAsync_gpt_image_2_rejects_invalid_result_shape(
            string body)
        {
            var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, body));

            var outcome = await ((IModelAwareImageProvider)provider).FetchResultAsync(
                FalImageCapabilities.GptImage2Edit,
                new ProviderJobHandle("fal-gpt-1"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
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

        private static ImageGenerationRequest Request(
            string? model = null,
            string? resolution = null,
            string? aspectRatio = null,
            IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: model ?? FalImageCapabilities.FluxSchnell,
                Prompt: "sunlit massing study",
                Resolution: resolution ?? "1K",
                AspectRatio: aspectRatio ?? "16:9",
                NumberOfImages: 1,
                ReferenceImages: referenceImages ?? new[]
                {
                    MediaRef.ForPath("C:/tmp/reference.png", ImageMediaRoles.ReferenceImage),
                },
                Options: new FalImageOptions());

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
            new Dictionary<MediaRef, ResolvedMedia>();

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

        private static ResolvedMedia PngMedia() => new(PngBytes(), "image/png");

        private static byte[] PngBytes() =>
            new byte[]
            {
                0x89, 0x50, 0x4E, 0x47,
                0x0D, 0x0A, 0x1A, 0x0A,
                1, 2, 3, 4,
            };

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
