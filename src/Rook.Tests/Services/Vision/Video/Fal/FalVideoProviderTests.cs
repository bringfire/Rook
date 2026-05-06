using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoProviderTests
    {
        [Fact]
        public async Task Submit_posts_expected_body_and_parses_queue_handle()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, @"{
                      ""request_id"": ""wan-123"",
                      ""status_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/status"",
                      ""response_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123"",
                      ""cancel_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"",
                      ""status"": ""IN_QUEUE"",
                      ""queue_position"": 3
                    }");
                },
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                Request(seed: 123),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("wan-123", queued.Handle.ProviderJobId);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/status", queued.Handle.StatusUrl!.ToString());
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123", queued.Handle.ResponseUrl!.ToString());
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel", queued.Handle.CancelUrl!.ToString());
            Assert.Equal("PUT", queued.Handle.CancelHttpMethod);
            Assert.Equal(3, queued.Handle.ProviderMetadata!["queue_position"]!.GetValue<int>());

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/v2.7/text-to-video", request.RequestUri!.ToString());
            Assert.Equal("Key", request.Headers.Authorization!.Scheme);
            Assert.Equal("test-fal-key", request.Headers.Authorization.Parameter);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.Equal("a clay massing animation", json["prompt"]!.GetValue<string>());
            Assert.Equal("16:9", json["aspect_ratio"]!.GetValue<string>());
            Assert.Equal("720p", json["resolution"]!.GetValue<string>());
            Assert.Equal(2, json["duration"]!.GetValue<int>());
            Assert.Equal(123, json["seed"]!.GetValue<int>());
            Assert.True(json["enable_safety_checker"]!.GetValue<bool>());
            Assert.True(json["enable_prompt_expansion"]!.GetValue<bool>());
            Assert.False(json.ContainsKey("negative_prompt"));
            Assert.False(json.ContainsKey("audio_url"));
        }

        [Fact]
        public async Task Submit_omits_seed_when_absent()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, SubmitBody());
                },
            };
            var provider = Provider(handler);

            await provider.SubmitAsync(
                Request(seed: null),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.False(json.ContainsKey("seed"));
        }

        [Fact]
        public async Task Submit_missing_key_returns_dependency_unavailable()
        {
            var provider = new FalVideoProvider(
                () => null,
                new FalApiClient(new HttpClient(new TestHttpMessageHandler())));

            var outcome = await provider.SubmitAsync(
                Request(),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
        }

        [Fact]
        public async Task Submit_requires_fal_video_options()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.SubmitAsync(
                Request(options: new VeoOptions(PersonGenerationPolicy.AllowAll)),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Options), failed.Error.Field);
        }

        [Fact]
        public async Task Submit_missing_prompt_returns_invalid_request()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.SubmitAsync(
                Request(prompt: null),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Prompt), failed.Error.Field);
        }

        [Fact]
        public async Task Submit_rejects_non_wan_model()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.SubmitAsync(
                Request(model: VeoCapabilities.DefaultModelId),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Model), failed.Error.Field);
        }

        [Fact]
        public async Task Submit_rejects_input_media()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.SubmitAsync(
                Request(startFrame: MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.Image)),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
        }

        [Fact]
        public async Task Submit_seedance_i2v_posts_data_uri_body_and_returns_request_id_only_handle()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, @"{
                      ""request_id"": ""seedance-123"",
                      ""status"": ""IN_QUEUE""
                    }");
                },
            };
            var provider = Provider(handler);
            var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
            var startBytes = PngBytes();

            var outcome = await provider.SubmitAsync(
                SeedanceRequest(VideoMode.I2V, startFrame: start),
                new Dictionary<MediaRef, ResolvedMedia>
                {
                    [start] = new ResolvedMedia(startBytes, "image/png"),
                },
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("seedance-123", queued.Handle.ProviderJobId);
            Assert.Null(queued.Handle.StatusUrl);
            Assert.Null(queued.Handle.ResponseUrl);
            Assert.Null(queued.Handle.CancelUrl);
            Assert.Null(queued.Handle.ProviderMetadata);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://queue.fal.run/bytedance/seedance-2.0/image-to-video",
                request.RequestUri!.ToString());

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.Equal("animate this source", json["prompt"]!.GetValue<string>());
            Assert.Equal(
                "data:image/png;base64," + Convert.ToBase64String(startBytes),
                json["image_url"]!.GetValue<string>());
            Assert.Equal("720p", json["resolution"]!.GetValue<string>());
            Assert.Equal("6", json["duration"]!.GetValue<string>());
            Assert.Equal("16:9", json["aspect_ratio"]!.GetValue<string>());
            Assert.False(json["generate_audio"]!.GetValue<bool>());
            Assert.Equal(77, json["seed"]!.GetValue<int>());
            Assert.False(json.ContainsKey("end_image_url"));
            Assert.False(json.ContainsKey("negative_prompt"));
            Assert.False(json.ContainsKey("multi_prompt"));
            Assert.False(json.ContainsKey("elements"));
        }

        [Fact]
        public async Task Submit_seedance_retries_once_after_connect_timeout()
        {
            var attempts = 0;
            var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ =>
                {
                    attempts++;
                    if (attempts == 1)
                    {
                        throw new HttpRequestException(
                            "connect timed out",
                            new SocketException((int)SocketError.TimedOut));
                    }

                    return Json(HttpStatusCode.OK, @"{
                      ""request_id"": ""seedance-retry-123"",
                      ""status"": ""IN_QUEUE""
                    }");
                },
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                SeedanceRequest(VideoMode.I2V, startFrame: start),
                new Dictionary<MediaRef, ResolvedMedia>
                {
                    [start] = new ResolvedMedia(PngBytes(), "image/png"),
                },
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("seedance-retry-123", queued.Handle.ProviderJobId);
            Assert.Equal(2, attempts);
            Assert.Equal(2, handler.Requests.Count);
        }

        [Fact]
        public async Task Submit_seedance_does_not_retry_generic_transport_failure()
        {
            var attempts = 0;
            var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ =>
                {
                    attempts++;
                    throw new HttpRequestException("request may have been sent");
                },
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                SeedanceRequest(VideoMode.I2V, startFrame: start),
                new Dictionary<MediaRef, ResolvedMedia>
                {
                    [start] = new ResolvedMedia(PngBytes(), "image/png"),
                },
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
            Assert.Equal(1, attempts);
            Assert.Single(handler.Requests);
        }

        [Fact]
        public async Task Submit_seedance_interp_includes_end_image_url()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return Json(HttpStatusCode.OK, @"{
                      ""request_id"": ""seedance-123"",
                      ""status"": ""IN_QUEUE""
                    }");
                },
            };
            var provider = Provider(handler);
            var start = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.StartFrame);
            var end = MediaRef.ForArtifact(Guid.NewGuid(), VideoMediaRoles.EndFrame);
            var startBytes = PngBytes();
            var endBytes = JpegBytes();

            var outcome = await provider.SubmitAsync(
                SeedanceRequest(VideoMode.Interp, startFrame: start, endFrame: end),
                new Dictionary<MediaRef, ResolvedMedia>
                {
                    [start] = new ResolvedMedia(startBytes, "image/png"),
                    [end] = new ResolvedMedia(endBytes, "image/jpeg"),
                },
                CancellationToken.None);

            var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
            Assert.Equal("seedance-123", queued.Handle.ProviderJobId);

            var json = JsonNode.Parse(body!)!.AsObject();
            Assert.Equal(
                "data:image/png;base64," + Convert.ToBase64String(startBytes),
                json["image_url"]!.GetValue<string>());
            Assert.Equal(
                "data:image/jpeg;base64," + Convert.ToBase64String(endBytes),
                json["end_image_url"]!.GetValue<string>());
        }

        [Fact]
        public async Task Submit_seedance_rejects_t2v_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                SeedanceRequest(VideoMode.T2V),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.Equal(nameof(VideoGenerationRequest.Mode), failed.Error.Field);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task Submit_timeout_returns_retryable_dependency_unavailable()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => throw new TaskCanceledException("timed out"),
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                Request(),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
        }

        [Fact]
        public async Task Submit_malformed_queue_url_returns_typed_failure()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{
                  ""request_id"": ""wan-123"",
                  ""status_url"": ""not a url"",
                  ""response_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123"",
                  ""cancel_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel""
                }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.SubmitAsync(
                Request(),
                new Dictionary<MediaRef, ResolvedMedia>(),
                CancellationToken.None);

            var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.False(failed.Error.Retryable);
            Assert.Contains("status_url", failed.Error.Message);
        }

        [Fact]
        public async Task Status_completed_returns_provider_complete_without_fetch_success()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{ ""status"": ""COMPLETED"" }"),
            };
            var provider = Provider(handler);
            var handle = Handle();

            var outcome = await provider.GetStatusAsync(handle, CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Same(handle, complete.UpdatedHandle);
        }

        [Fact]
        public async Task Status_seedance_reconstructs_status_url_from_model_and_request_id()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{ ""status"": ""COMPLETED"" }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.GetStatusAsync(
                FalVideoCapabilities.SeedanceI2v,
                new ProviderJobHandle(
                    "seedance-123",
                    providerResultToken: "existing-token"),
                CancellationToken.None);

            var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
            Assert.Equal("seedance-123", complete.UpdatedHandle.ProviderJobId);
            Assert.Equal("existing-token", complete.UpdatedHandle.ProviderResultToken);
            Assert.Null(complete.UpdatedHandle.StatusUrl);
            Assert.Null(complete.UpdatedHandle.ResponseUrl);
            Assert.Null(complete.UpdatedHandle.CancelUrl);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal(
                "https://queue.fal.run/bytedance/seedance-2.0/requests/seedance-123/status",
                request.RequestUri!.ToString());
        }

        [Fact]
        public async Task Status_timeout_returns_retryable_dependency_unavailable()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => throw new TaskCanceledException("timed out"),
            };
            var provider = Provider(handler);

            var outcome = await provider.GetStatusAsync(Handle(), CancellationToken.None);

            var failed = Assert.IsType<FailedStatusOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
        }

        [Fact]
        public async Task Fetch_requires_response_url()
        {
            var provider = Provider(new TestHttpMessageHandler());

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle("wan-123"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
            Assert.DoesNotContain("wan-123", failed.Error.Message);
        }

        [Fact]
        public async Task Fetch_parses_remote_video_artifact()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{
                  ""actual_prompt"": ""expanded prompt"",
                  ""seed"": 42,
                  ""video"": {
                    ""url"": ""https://v3b.fal.media/files/out.mp4"",
                    ""content_type"": ""video/mp4"",
                    ""duration"": 2,
                    ""fps"": 24,
                    ""num_frames"": 48,
                    ""width"": 1280,
                    ""height"": 720
                  }
                }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(VideoMediaRoles.Video, artifact.Role);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://v3b.fal.media/files/out.mp4", remote.Url.ToString());
            Assert.Equal("video/mp4", artifact.DeclaredMimeType);
            Assert.Equal("https://v3b.fal.media/files/out.mp4", artifact.ProviderMetadata["url"]!.GetValue<string>());
            Assert.Equal(1280, artifact.ProviderMetadata["width"]!.GetValue<int>());
            Assert.Equal("expanded prompt", success.Envelope.EnvelopeMetadata["actual_prompt"]!.GetValue<string>());
        }

        [Fact]
        public async Task Fetch_seedance_reconstructs_response_url_and_drops_provider_metadata()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, @"{
                  ""video"": {
                    ""url"": ""https://v3.fal.media/files/seedance.mp4"",
                    ""content_type"": ""video/mp4"",
                    ""duration"": 6
                  },
                  ""seed"": 42
                }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(
                FalVideoCapabilities.SeedanceI2v,
                new ProviderJobHandle("seedance-123"),
                CancellationToken.None);

            var success = Assert.IsType<SuccessResultOutcome>(outcome);
            var artifact = Assert.Single(success.Envelope.Artifacts);
            Assert.Equal(VideoMediaRoles.Video, artifact.Role);
            var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
            Assert.Equal("https://v3.fal.media/files/seedance.mp4", remote.Url.ToString());
            Assert.Equal("video/mp4", artifact.DeclaredMimeType);
            Assert.Empty(artifact.ProviderMetadata);
            Assert.Empty(success.Envelope.EnvelopeMetadata);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal(
                "https://queue.fal.run/bytedance/seedance-2.0/requests/seedance-123",
                request.RequestUri!.ToString());
        }

        [Theory]
        [InlineData(@"{}")]
        [InlineData(@"{ ""video"": {} }")]
        [InlineData(@"{ ""video"": { ""url"": ""https://"" } }")]
        [InlineData(@"{ ""video"": { ""url"": ""data:video/mp4;base64,AAAA"" } }")]
        [InlineData(@"{ ""video"": { ""url"": ""file:///C:/temp/out.mp4"" } }")]
        public async Task Fetch_seedance_rejects_missing_or_invalid_video_url(string responseJson)
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.OK, responseJson),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(
                FalVideoCapabilities.SeedanceI2v,
                new ProviderJobHandle("seedance-123"),
                CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, failed.Error.Code);
        }

        [Fact]
        public async Task Fetch_non_success_maps_provider_error()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json((HttpStatusCode)422, @"{ ""detail"": [{ ""msg"": ""bad"" }] }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.InvalidRequest, failed.Error.Code);
            Assert.NotNull(failed.Error.ProviderDetail);
        }

        [Fact]
        public async Task Fetch_timeout_returns_retryable_dependency_unavailable()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => throw new TaskCanceledException("timed out"),
            };
            var provider = Provider(handler);

            var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

            var failed = Assert.IsType<FailedResultOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
        }

        [Fact]
        public async Task Cancel_uses_put_and_cancel_url()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.Accepted, @"{ ""status"": ""CANCELLATION_REQUESTED"" }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.CancelAsync(Handle(), CancellationToken.None);

            Assert.IsType<CanceledOutcome>(outcome);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Put, request.Method);
            Assert.Equal("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel", request.RequestUri!.ToString());
        }

        [Fact]
        public async Task Cancel_timeout_returns_retryable_dependency_unavailable()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => throw new TaskCanceledException("timed out"),
            };
            var provider = Provider(handler);

            var outcome = await provider.CancelAsync(Handle(), CancellationToken.None);

            var failed = Assert.IsType<FailedCancelOutcome>(outcome);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
            Assert.True(failed.Error.Retryable);
        }

        [Fact]
        public async Task Cancel_not_found_maps_provider_error()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.NotFound, @"{ ""status"": ""NOT_FOUND"" }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.CancelAsync(Handle(), CancellationToken.None);

            Assert.IsType<FailedCancelOutcome>(outcome);
        }

        [Fact]
        public async Task Cancel_uses_persisted_handle_method()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.Accepted, @"{ ""status"": ""CANCELLATION_REQUESTED"" }"),
            };
            var provider = Provider(handler);
            var handle = new ProviderJobHandle(
                providerJobId: "wan-123",
                cancelUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"),
                cancelHttpMethod: "POST");

            await provider.CancelAsync(handle, CancellationToken.None);

            Assert.Equal(HttpMethod.Post, Assert.Single(handler.Requests).Method);
        }

        [Fact]
        public async Task Cancel_seedance_reconstructs_cancel_url_from_model_and_request_id()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => Json(HttpStatusCode.Accepted, @"{ ""status"": ""CANCELLATION_REQUESTED"" }"),
            };
            var provider = Provider(handler);

            var outcome = await provider.CancelAsync(
                FalVideoCapabilities.SeedanceI2v,
                new ProviderJobHandle("seedance-123"),
                CancellationToken.None);

            Assert.IsType<CanceledOutcome>(outcome);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Put, request.Method);
            Assert.Equal(
                "https://queue.fal.run/bytedance/seedance-2.0/requests/seedance-123/cancel",
                request.RequestUri!.ToString());
        }

        [Fact]
        public async Task Model_aware_lifecycle_rejects_unknown_model_without_inferring_from_request_id_only_handle()
        {
            var handler = new TestHttpMessageHandler();
            var provider = Provider(handler);
            var handle = new ProviderJobHandle("seedance-123");

            var status = await provider.GetStatusAsync(
                "unknown-model",
                handle,
                CancellationToken.None);
            var fetch = await provider.FetchResultAsync(
                "unknown-model",
                handle,
                CancellationToken.None);
            var cancel = await provider.CancelAsync(
                "unknown-model",
                handle,
                CancellationToken.None);

            Assert.Equal(
                GenerationErrorCode.InvalidRequest,
                Assert.IsType<FailedStatusOutcome>(status).Error.Code);
            Assert.Equal(
                GenerationErrorCode.InvalidRequest,
                Assert.IsType<FailedResultOutcome>(fetch).Error.Code);
            Assert.Equal(
                GenerationErrorCode.InvalidRequest,
                Assert.IsType<FailedCancelOutcome>(cancel).Error.Code);
            Assert.Empty(handler.Requests);
        }

        private static FalVideoProvider Provider(TestHttpMessageHandler handler) =>
            new(() => "test-fal-key", new FalApiClient(new HttpClient(handler)));

        private static VideoGenerationRequest Request(
            int? seed = null,
            string? prompt = "a clay massing animation",
            ProviderOptions? options = null,
            string? model = null,
            MediaRef? startFrame = null) =>
            new(
                Model: model ?? FalVideoCapabilities.WanT2v,
                Mode: VideoMode.T2V,
                DurationSeconds: 2,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: null,
                ReferenceFrames: null,
                Seed: seed,
                Options: options ?? new FalVideoOptions(),
                NumberOfVideos: 1);

        private static VideoGenerationRequest SeedanceRequest(
            VideoMode mode,
            MediaRef? startFrame = null,
            MediaRef? endFrame = null) =>
            new(
                Model: FalVideoCapabilities.SeedanceI2v,
                Mode: mode,
                DurationSeconds: 6,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "animate this source",
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: null,
                Seed: 77,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

        private static ProviderJobHandle Handle() =>
            new(
                providerJobId: "wan-123",
                statusUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/status"),
                responseUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123"),
                cancelUrl: new Uri("https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"),
                cancelHttpMethod: "PUT");

        private static HttpResponseMessage Json(HttpStatusCode status, string body) =>
            new(status)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            };

        private static string SubmitBody() =>
            @"{
              ""request_id"": ""wan-123"",
              ""status_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/status"",
              ""response_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123"",
              ""cancel_url"": ""https://queue.fal.run/fal-ai/wan/requests/wan-123/cancel"",
              ""status"": ""IN_QUEUE""
            }";

        private static byte[] PngBytes() =>
            new byte[]
            {
                0x89, 0x50, 0x4E, 0x47,
                0x0D, 0x0A, 0x1A, 0x0A,
                1, 2, 3, 4,
            };

        private static byte[] JpegBytes() =>
            new byte[] { 0xFF, 0xD8, 0xFF, 1, 2, 3 };
    }
}
