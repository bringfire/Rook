using System;
using System.Collections.Generic;
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
        public async Task SubmitAsync_flux2_prompt_only_posts_prediction_without_input_images_or_match_input_defaults()
        {
            string? requestBody = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    requestBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-flux2-prompt",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-flux2-prompt",
                            "cancel": "https://api.replicate.com/v1/predictions/pred-flux2-prompt/cancel"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "", aspectRatio: "match_input_image"),
                EmptyMedia(),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
                request.RequestUri!.ToString());

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(requestBody!));
            var inputJson = Assert.IsType<JsonObject>(root["input"]);
            Assert.Equal(
                new[] { "aspect_ratio", "output_format", "prompt", "resolution" },
                inputJson.Select(kvp => kvp.Key).OrderBy(k => k));
            Assert.Equal("1:1", inputJson["aspect_ratio"]!.GetValue<string>());
            Assert.Equal("1 MP", inputJson["resolution"]!.GetValue<string>());
            Assert.DoesNotContain("input_images", requestBody);
            Assert.DoesNotContain("data:image/", requestBody);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2-prompt", queued.Handle.ProviderJobId);
        }

        [Theory]
        [InlineData("2 MP", "2 MP")]
        [InlineData("4 MP", "4 MP")]
        [InlineData("1MP", "1 MP")]
        public async Task SubmitAsync_flux2_prompt_only_serializes_provider_resolution_values(
            string requestedResolution,
            string expectedProviderResolution)
        {
            string? requestBody = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    requestBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-flux2-resolution",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-flux2-resolution",
                            "cancel": "https://api.replicate.com/v1/predictions/pred-flux2-resolution/cancel"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: requestedResolution,
                    aspectRatio: "1:1"),
                EmptyMedia(),
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2-resolution", queued.Handle.ProviderJobId);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
                request.RequestUri!.ToString());

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(requestBody!));
            var inputJson = Assert.IsType<JsonObject>(root["input"]);
            Assert.Equal(expectedProviderResolution, inputJson["resolution"]!.GetValue<string>());
            Assert.Equal("1:1", inputJson["aspect_ratio"]!.GetValue<string>());
            Assert.DoesNotContain("input_images", requestBody);
        }

        [Fact]
        public async Task SubmitAsync_flux2_rejects_reference_image_roles_before_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);

            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMedia(),
                [MediaRef.ForPath("C:/tmp/ref.png", ImageMediaRoles.ReferenceImage)] = PngMedia(),
            };

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("reference_image_paths", failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_rejects_unsupported_mime_before_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = new ResolvedMedia(
                    new byte[] { 0x00, 0x01, 0x02, 0x03 },
                    "application/octet-stream"),
            };

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("PNG, JPEG, GIF, or WebP", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_rejects_source_over_pixel_policy_before_http_call()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensions(3001, 3000),
            };

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("9 megapixels or less", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_rejects_source_over_upload_byte_policy_before_upload()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var maxBytes = ReplicateImageCapabilities.Flux2ProMediaPolicy.Transport.MaxSingleUploadBytes;
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensionsAndLength(512, 512, checked((int)maxBytes + 1)),
            };

            var outcome = await provider.SubmitAsync(
                Request(model: ReplicateImageCapabilities.Flux2Pro, resolution: "1MP", aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal("input_image_path", failed.Error.Field);
            Assert.Contains("upload", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_uploads_source_and_posts_https_input_image_url()
        {
            string? predictionBody = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.AbsolutePath == "/v1/files")
                    {
                        return Json(HttpStatusCode.Created, """
                            {
                              "id": "file-flux2-source",
                              "urls": {
                                "get": "https://api.replicate.com/v1/files/file-flux2-source"
                              }
                            }
                            """);
                    }

                    predictionBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-flux2",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-flux2",
                            "cancel": "https://api.replicate.com/v1/predictions/pred-flux2/cancel"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensions(512, 512),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            Assert.Equal(2, handler.Requests.Count);
            Assert.Equal(HttpMethod.Post, handler.Requests[0].Method);
            Assert.Equal("https://api.replicate.com/v1/files", handler.Requests[0].RequestUri!.ToString());

            var request = handler.Requests[1];
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-2-pro/predictions",
                request.RequestUri!.ToString());

            var root = Assert.IsType<JsonObject>(JsonNode.Parse(predictionBody!));
            Assert.Equal(new[] { "input" }, root.Select(kvp => kvp.Key).OrderBy(k => k));
            var inputJson = Assert.IsType<JsonObject>(root["input"]);
            Assert.Equal(
                new[] { "aspect_ratio", "input_images", "output_format", "prompt", "resolution" },
                inputJson.Select(kvp => kvp.Key).OrderBy(k => k));
            Assert.Equal("sunlit massing study", inputJson["prompt"]!.GetValue<string>());
            Assert.Equal("match_input_image", inputJson["aspect_ratio"]!.GetValue<string>());
            Assert.Equal("match_input_image", inputJson["resolution"]!.GetValue<string>());
            Assert.Equal("png", inputJson["output_format"]!.GetValue<string>());

            var images = Assert.IsType<JsonArray>(inputJson["input_images"]);
            var image = Assert.Single(images);
            Assert.Equal("https://api.replicate.com/v1/files/file-flux2-source", image!.GetValue<string>());
            Assert.DoesNotContain("data:image/", predictionBody);
            Assert.DoesNotContain("num_outputs", predictionBody);
            Assert.DoesNotContain("reference", predictionBody);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
            Assert.NotNull(queued.Handle.ProviderMetadata);
            var urlsJson = queued.Handle.ProviderMetadata!["urls"]!.ToJsonString();
            Assert.Contains("predictions/pred-flux2", urlsJson);
            Assert.DoesNotContain("/v1/files/file-flux2-source", urlsJson);
            Assert.DoesNotContain("data:image/", urlsJson);
            Assert.Null(queued.Handle.ProviderResultToken);
        }

        [Fact]
        public async Task SubmitAsync_flux2_does_not_store_upload_url_in_handle()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.AbsolutePath == "/v1/files")
                    {
                        return Json(HttpStatusCode.Created, """
                            {
                              "id": "file-secret",
                              "urls": { "get": "https://api.replicate.com/v1/files/file-secret" }
                            }
                            """);
                    }

                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-flux2",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-flux2",
                            "cancel": "https://api.replicate.com/v1/predictions/pred-flux2/cancel"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensions(512, 512),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "4 MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2", queued.Handle.ProviderJobId);
            Assert.NotNull(queued.Handle.ProviderMetadata);
            var urlsJson = queued.Handle.ProviderMetadata!["urls"]!.ToJsonString();
            Assert.Contains("predictions/pred-flux2", urlsJson);
            Assert.DoesNotContain("/v1/files/file-secret", urlsJson);
            Assert.DoesNotContain("data:image/", urlsJson);
            Assert.Null(queued.Handle.ProviderResultToken);
            Assert.DoesNotContain("file-secret", queued.Handle.ProviderJobId);
        }

        [Fact]
        public async Task SubmitAsync_flux2_upload_http_exception_returns_retryable_dependency_failure()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(
                "r8-test-token",
                handler,
                ThrowingFileTransport.HttpRequest());
            var media = SinglePngInputMedia();

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
            Assert.Contains("transport", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_small_upload_failure_fails_closed_without_prediction_post()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(
                "r8-test-token",
                handler,
                FailingFileTransport.DependencyUnavailable());
            var media = SinglePngInputMedia();

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.Contains("HTTP 500", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_large_upload_failure_fails_with_transport_detail()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(
                "r8-test-token",
                handler,
                FailingFileTransport.DependencyUnavailable());
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensionsAndLength(512, 512, 262_145),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.Contains("HTTP 500", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_upload_task_canceled_exception_returns_retryable_timeout_failure()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(
                "r8-test-token",
                handler,
                ThrowingFileTransport.TaskCanceled());
            var media = SinglePngInputMedia();

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
            Assert.Contains("timed out", failed.Error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_upload_argument_exception_returns_failed_outcome()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(
                "r8-test-token",
                handler,
                ThrowingFileTransport.Argument());
            var media = SinglePngInputMedia();

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("before it could be sent", failed.Error.Message);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SubmitAsync_flux2_accepts_gif_source_image()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.AbsolutePath == "/v1/files")
                    {
                        return Json(HttpStatusCode.Created, """
                            {
                              "id": "file-flux2-gif",
                              "urls": {
                                "get": "https://api.replicate.com/v1/files/file-flux2-gif"
                              }
                            }
                            """);
                    }

                    return Json(HttpStatusCode.Created, """
                        {
                          "id": "pred-flux2-gif",
                          "status": "starting",
                          "urls": {
                            "get": "https://api.replicate.com/v1/predictions/pred-flux2-gif"
                          }
                        }
                        """);
                },
            };
            var provider = Provider("r8-test-token", handler);
            var input = MediaRef.ForPath("C:/tmp/input.gif", ImageMediaRoles.InputImage);
            var media = new Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = GifMediaWithDimensions(320, 240),
            };

            var outcome = await provider.SubmitAsync(
                Request(
                    model: ReplicateImageCapabilities.Flux2Pro,
                    resolution: "1MP",
                    aspectRatio: "match_input_image"),
                media,
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("pred-flux2-gif", queued.Handle.ProviderJobId);
            Assert.Equal(2, handler.Requests.Count);
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

        [Theory]
        [InlineData("""
            {
              "id": "pred-1",
              "status": "succeeded",
              "output": "https://replicate.delivery/pbxt/out.png",
              "metrics": { "predict_time": 0.507 },
              "model": "black-forest-labs/flux-schnell",
              "version": "abc123",
              "urls": {
                "get": "https://api.replicate.com/v1/predictions/pred-1",
                "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
              }
            }
            """)]
        [InlineData("""
            {
              "id": "pred-1",
              "status": "succeeded",
              "output": [ "https://replicate.delivery/pbxt/out.png" ],
              "metrics": { "predict_time": 0.507 },
              "model": "black-forest-labs/flux-schnell",
              "version": "abc123",
              "urls": {
                "get": "https://api.replicate.com/v1/predictions/pred-1",
                "cancel": "https://api.replicate.com/v1/predictions/pred-1/cancel"
              }
            }
            """)]
        public async Task FetchResultAsync_accepts_single_url_output_shapes(string statusJson)
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = CompleteHandle(statusJson);

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(ImageMediaRoles.Image, artifact.Role);
            var body = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://replicate.delivery/pbxt/out.png", body.Url.ToString());
            Assert.Null(artifact.DeclaredMimeType);
            Assert.Equal("https://replicate.delivery/pbxt/out.png", artifact.ProviderMetadata["url"]!.GetValue<string>());
            Assert.True(artifact.ProviderMetadata["requires_authenticated_fetch"]!.GetValue<bool>());

            Assert.True(success.Envelope.EnvelopeMetadata.ContainsKey("output"));
            Assert.Equal(0.507, success.Envelope.EnvelopeMetadata["metrics"]!["predict_time"]!.GetValue<double>());
            Assert.Equal("black-forest-labs/flux-schnell", success.Envelope.EnvelopeMetadata["model"]!.GetValue<string>());
            Assert.Equal("abc123", success.Envelope.EnvelopeMetadata["version"]!.GetValue<string>());
            Assert.Equal(
                "https://api.replicate.com/v1/predictions/pred-1",
                success.Envelope.EnvelopeMetadata["urls"]!["get"]!.GetValue<string>());

            ((JsonObject)handle.ProviderMetadata!["metrics"]!)["predict_time"] = 9.9;
            Assert.Equal(0.507, success.Envelope.EnvelopeMetadata["metrics"]!["predict_time"]!.GetValue<double>());
        }

        [Theory]
        [InlineData("""{ "output": [] }""")]
        [InlineData("""{ "output": [ "https://replicate.delivery/pbxt/a.png", "https://replicate.delivery/pbxt/b.png" ] }""")]
        [InlineData("""{ "output": { "url": "https://replicate.delivery/pbxt/out.png" } }""")]
        [InlineData("""{ "output": null }""")]
        [InlineData("""{ "output": 42 }""")]
        [InlineData("""{ "output": "not-a-url" }""")]
        public async Task FetchResultAsync_rejects_unsupported_output_shapes(string metadataJson)
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = new ProviderJobHandle(
                "pred-1",
                providerResultToken: "https://replicate.delivery/pbxt/out.png",
                providerMetadata: Metadata(metadataJson));

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("exactly one image URL", failed.Error.Message);
        }

        [Fact]
        public async Task FetchResultAsync_output_metadata_url_must_match_result_token()
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = new ProviderJobHandle(
                "pred-1",
                providerResultToken: "https://replicate.delivery/pbxt/token.png",
                providerMetadata: Metadata("""{ "output": "https://replicate.delivery/pbxt/output.png" }"""));

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("exactly one image URL", failed.Error.Message);
        }

        [Fact]
        public async Task FetchResultAsync_accepts_replicate_delivery_subdomain_output_url()
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = new ProviderJobHandle(
                "pred-1",
                providerResultToken: "https://v3b.replicate.delivery/pbxt/out.png",
                providerMetadata: Metadata("""{ "output": "https://v3b.replicate.delivery/pbxt/out.png" }"""));

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            var body = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://v3b.replicate.delivery/pbxt/out.png", body.Url.ToString());
        }

        [Theory]
        [InlineData("http://replicate.delivery/pbxt/out.png")]
        [InlineData("https://replicate.delivery.evil.test/out.png")]
        [InlineData("https://example.test/out.png")]
        public async Task FetchResultAsync_rejects_output_urls_outside_authenticated_replicate_delivery(
            string outputUrl)
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = new ProviderJobHandle(
                "pred-1",
                providerResultToken: outputUrl,
                providerMetadata: Metadata($$"""{ "output": "{{outputUrl}}" }"""));

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("exactly one image URL", failed.Error.Message);
        }

        [Fact]
        public async Task FetchResultAsync_missing_output_metadata_returns_execution_failed()
        {
            var provider = Provider("r8-test-token", new TestHttpMessageHandler());
            var handle = new ProviderJobHandle(
                "pred-1",
                providerResultToken: "https://replicate.delivery/pbxt/out.png",
                providerMetadata: Metadata("""{ "metrics": { "predict_time": 0.507 } }"""));

            var outcome = await provider.FetchResultAsync(handle, CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("exactly one image URL", failed.Error.Message);
        }

        private static ReplicateImageProvider Provider(
            string? token,
            TestHttpMessageHandler handler,
            IReplicateFileTransport? fileTransport = null) =>
            new(
                () => token,
                new ReplicateApiClient(new HttpClient(handler)),
                fileTransport);

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
            string resolution = "1K",
            ProviderOptions? options = null,
            System.Collections.Generic.IReadOnlyList<MediaRef>? referenceImages = null) =>
            new(
                Model: model,
                Prompt: "sunlit massing study",
                Resolution: resolution,
                AspectRatio: aspectRatio,
                NumberOfImages: 1,
                ReferenceImages: referenceImages,
                Options: options ?? new ReplicateImageOptions());

        private static System.Collections.Generic.IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
            new System.Collections.Generic.Dictionary<MediaRef, ResolvedMedia>();

        private static System.Collections.Generic.IReadOnlyDictionary<MediaRef, ResolvedMedia> SinglePngInputMedia()
        {
            var input = MediaRef.ForPath("C:/tmp/input.png", ImageMediaRoles.InputImage);
            return new System.Collections.Generic.Dictionary<MediaRef, ResolvedMedia>
            {
                [input] = PngMediaWithDimensions(512, 512),
            };
        }

        private static ResolvedMedia PngMedia() =>
            new(
                new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 },
                "image/png");

        private static ResolvedMedia PngMediaWithDimensions(int width, int height)
        {
            return PngMediaWithDimensionsAndLength(width, height, 33);
        }

        private static ResolvedMedia PngMediaWithDimensionsAndLength(
            int width,
            int height,
            int totalBytes)
        {
            var bytes = new byte[33];
            if (totalBytes < bytes.Length)
                throw new ArgumentOutOfRangeException(nameof(totalBytes));

            if (totalBytes != bytes.Length)
                bytes = new byte[totalBytes];

            bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
            bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
            WriteBigEndian(bytes, 8, 13);
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return new ResolvedMedia(bytes, "image/png");
        }

        private static ResolvedMedia GifMediaWithDimensions(int width, int height) =>
            new(
                new byte[]
                {
                    0x47, 0x49, 0x46, 0x38, 0x39, 0x61,
                    (byte)(width & 0xFF), (byte)((width >> 8) & 0xFF),
                    (byte)(height & 0xFF), (byte)((height >> 8) & 0xFF),
                    0x00, 0x00, 0x00,
                },
                "image/gif");

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string json) =>
            new(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };

        private static ProviderJobHandle CompleteHandle(string statusJson)
        {
            var outcome = ReplicateLifecycleMapper.MapStatus(
                new ProviderJobHandle("pred-1"),
                JsonNode.Parse(statusJson)!);
            return Assert.IsType<ProviderCompleteStatusOutcome>(outcome).UpdatedHandle;
        }

        private static System.Collections.Generic.IReadOnlyDictionary<string, JsonNode> Metadata(string json)
        {
            var root = Assert.IsType<JsonObject>(JsonNode.Parse(json));
            var metadata = new System.Collections.Generic.Dictionary<string, JsonNode>();
            foreach (var kvp in root)
            {
                metadata[kvp.Key] = kvp.Value?.DeepClone()!;
            }

            return metadata;
        }

        private sealed class ThrowingFileTransport : IReplicateFileTransport
        {
            private readonly Exception _exception;

            private ThrowingFileTransport(Exception exception)
            {
                _exception = exception;
            }

            public static ThrowingFileTransport HttpRequest() =>
                new(new HttpRequestException("network unavailable"));

            public static ThrowingFileTransport TaskCanceled() =>
                new(new TaskCanceledException("upload timed out"));

            public static ThrowingFileTransport Argument() =>
                new(new ArgumentException("bad upload"));

            public Task<ReplicateFileUploadResult> UploadAsync(
                string apiToken,
                string fileName,
                byte[] bytes,
                string mimeType,
                CancellationToken ct)
            {
                throw _exception;
            }
        }

        private sealed class FailingFileTransport : IReplicateFileTransport
        {
            public static FailingFileTransport DependencyUnavailable() => new();

            public Task<ReplicateFileUploadResult> UploadAsync(
                string apiToken,
                string fileName,
                byte[] bytes,
                string mimeType,
                CancellationToken ct)
            {
                return Task.FromResult(ReplicateFileUploadResult.Failed(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    "Replicate file upload transport is unavailable. Upload failure detail: HttpRequestException: Replicate file upload failed with HTTP 500 Internal Server Error: {\"detail\":\"Internal server error\"}",
                    Retryable: true,
                    Field: "input_image_path")));
            }
        }
    }
}
