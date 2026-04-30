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
    }
}
