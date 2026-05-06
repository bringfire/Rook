using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
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
    public class FalSeedanceSourceTransportTests
    {
        [Fact]
        public async Task ResolveAndUploadAsync_rejects_source_larger_than_seedance_limit_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = PngBytes((int)FalSeedanceSourceTransport.MaxSourceFrameBytes + 1);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, bytes, "image/png"),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("image/png")]
        [InlineData("image/jpeg")]
        [InlineData("image/webp")]
        public async Task ResolveAndUploadAsync_accepts_supported_mime_at_limit(string mimeType)
        {
            var handler = UploadHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = ImageBytes(mimeType, (int)FalSeedanceSourceTransport.MaxSourceFrameBytes);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, bytes, mimeType),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(error);
            Assert.NotNull(urls);
            Assert.Equal("v3b.fal.media", new Uri(urls!.ImageUrl).Host);
            Assert.Null(urls.EndImageUrl);
            Assert.Equal(2, handler.Requests.Count);
            Assert.All(handler.Requests, req => Assert.DoesNotContain("data:", req.RequestUri!.ToString()));
        }

        [Theory]
        [InlineData("image/png", "png")]
        [InlineData("image/jpeg", "jpg")]
        [InlineData("image/webp", "webp")]
        public async Task ResolveAndUploadAsync_upload_initiate_and_put_are_private_and_mime_derived(
            string mimeType,
            string expectedExtension)
        {
            string? initiateBody = null;
            string? putContentType = null;
            byte[]? putBytes = null;
            var bytes = ImageBytes(mimeType, 16);
            var artifactId = Guid.Parse("9efb938d-9e2c-4bba-b33d-9e1d86d0e3bf");
            var localPathMarker = @"C:\source\secret-source-name.png";
            var start = MediaRef.ForArtifact(artifactId, VideoMediaRoles.StartFrame);
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        initiateBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                        return Json(HttpStatusCode.OK, """
                            {
                              "upload_url": "https://uploads.example.test/source-token",
                              "file_url": "https://v3b.fal.media/files/source-private"
                            }
                            """);
                    }

                    putContentType = req.Content!.Headers.ContentType!.MediaType;
                    putBytes = req.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.NoContent);
                },
            };
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(
                    VideoMode.I2V,
                    startFrame: start,
                    prompt: $"secret prompt {artifactId} {localPathMarker}"),
                Media(start, bytes, mimeType),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(error);
            Assert.Equal("https://v3b.fal.media/files/source-private", urls!.ImageUrl);

            var initiate = handler.Requests[0];
            Assert.Equal(HttpMethod.Post, initiate.Method);
            Assert.Equal(
                "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
                initiate.RequestUri!.ToString());
            Assert.Equal(
                "{\"expiration_duration_seconds\":3600}",
                Assert.Single(initiate.Headers.GetValues("X-Fal-Object-Lifecycle")));

            using var doc = JsonDocument.Parse(initiateBody!);
            var contentType = doc.RootElement.GetProperty("content_type").GetString();
            var fileName = doc.RootElement.GetProperty("file_name").GetString();
            Assert.Equal(mimeType, contentType);
            Assert.Matches(
                $"^rook-seedance-source-[0-9a-f]{{32}}\\.{Regex.Escape(expectedExtension)}$",
                fileName);
            Assert.DoesNotContain("secret prompt", initiateBody);
            Assert.DoesNotContain(artifactId.ToString(), initiateBody);
            Assert.DoesNotContain("secret-source-name.png", initiateBody);
            Assert.DoesNotContain(localPathMarker, initiateBody);
            Assert.DoesNotContain("data:", initiateBody);

            var put = handler.Requests[1];
            Assert.Equal(HttpMethod.Put, put.Method);
            Assert.Equal("https://uploads.example.test/source-token", put.RequestUri!.ToString());
            Assert.Null(put.Headers.Authorization);
            Assert.Equal(mimeType, putContentType);
            Assert.Equal(bytes, putBytes);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_propagates_caller_cancellation_during_upload_initiate()
        {
            using var cts = new CancellationTokenSource();
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ =>
                {
                    cts.Cancel();
                    throw new OperationCanceledException(cts.Token);
                },
            };
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            await Assert.ThrowsAsync<OperationCanceledException>(
                async () => await transport.ResolveAndUploadAsync(
                    Request(VideoMode.I2V, startFrame: start),
                    Media(start, PngBytes(), "image/png"),
                    "test-fal-key",
                    cts.Token));

            Assert.Single(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_upload_failure_returns_retryable_dependency_unavailable()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        return Json(HttpStatusCode.OK, """
                            {
                              "upload_url": "https://uploads.example.test/source-token",
                              "file_url": "https://v3b.fal.media/files/source-private"
                            }
                            """);
                    }

                    return Json(HttpStatusCode.InternalServerError, """
                        {
                          "upload_url": "https://uploads.example.test/source-token",
                          "file_url": "https://v3b.fal.media/files/source-private",
                          "prompt": "secret prompt"
                        }
                        """);
                },
            };
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start, prompt: "secret prompt"),
                Media(start, PngBytes(), "image/png"),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            Assert.NotNull(error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error!.Code);
            Assert.True(error.Retryable);
            Assert.Null(error.Field);
            Assert.Equal("fal Seedance source upload failed.", error.Message);
            Assert.DoesNotContain("upload_url", error.Message);
            Assert.DoesNotContain("file_url", error.Message);
            Assert.DoesNotContain("source-token", error.Message);
            Assert.DoesNotContain("secret prompt", error.Message);
            Assert.Equal(2, handler.Requests.Count);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_declared_mime_mismatch_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, PngBytes(), "image/jpeg"),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_missing_start_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: null),
                EmptyMedia(),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_end_frame_for_i2v_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);
            var end = Artifact(VideoMediaRoles.EndFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start, endFrame: end),
                Media(
                    (start, new ResolvedMedia(PngBytes(), "image/png")),
                    (end, new ResolvedMedia(JpegBytes(), "image/jpeg"))),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "end_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_missing_end_for_interp_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.Interp, startFrame: start, endFrame: null),
                Media(start, PngBytes(), "image/png"),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "end_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_reference_frames_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);
            var reference = Artifact("reference");

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(
                    VideoMode.I2V,
                    startFrame: start,
                    referenceFrames: new[] { reference }),
                Media(
                    (start, new ResolvedMedia(PngBytes(), "image/png")),
                    (reference, new ResolvedMedia(JpegBytes(), "image/jpeg"))),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "reference_frames");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_unsupported_bytes_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, GifBytes(), "image/gif"),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_unresolved_media_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.I2V, startFrame: start),
                EmptyMedia(),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "start_frame");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_rejects_t2v_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.T2V, startFrame: null),
                EmptyMedia(),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(urls);
            AssertInvalid(error, "mode");
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task ResolveAndUploadAsync_interp_uploads_start_and_end_frames()
        {
            var initiateBodies = new List<string>();
            var putContentTypes = new List<string>();
            var putBodies = new List<byte[]>();
            var uploadIndex = 0;
            var start = Artifact(VideoMediaRoles.StartFrame);
            var end = Artifact(VideoMediaRoles.EndFrame);
            var startBytes = PngBytes();
            var endBytes = JpegBytes();
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        uploadIndex++;
                        initiateBodies.Add(req.Content!.ReadAsStringAsync().GetAwaiter().GetResult());
                        var ext = uploadIndex == 1 ? "png" : "jpg";
                        return Json(HttpStatusCode.OK, $$"""
                            {
                              "upload_url": "https://uploads.example.test/source-{{uploadIndex}}",
                              "file_url": "https://v3b.fal.media/files/source-{{uploadIndex}}.{{ext}}"
                            }
                            """);
                    }

                    putContentTypes.Add(req.Content!.Headers.ContentType!.MediaType!);
                    putBodies.Add(req.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult());
                    return new HttpResponseMessage(HttpStatusCode.NoContent);
                },
            };
            var transport = Transport(handler);

            var (urls, error) = await transport.ResolveAndUploadAsync(
                Request(VideoMode.Interp, startFrame: start, endFrame: end),
                Media(
                    (start, new ResolvedMedia(startBytes, "image/png")),
                    (end, new ResolvedMedia(endBytes, "image/jpeg"))),
                "test-fal-key",
                CancellationToken.None);

            Assert.Null(error);
            Assert.NotNull(urls);
            Assert.Equal("https://v3b.fal.media/files/source-1.png", urls!.ImageUrl);
            Assert.Equal("https://v3b.fal.media/files/source-2.jpg", urls.EndImageUrl);
            Assert.Equal(4, handler.Requests.Count);
            Assert.Equal(2, CountRequests(handler, HttpMethod.Post));
            Assert.Equal(2, CountRequests(handler, HttpMethod.Put));

            Assert.Equal(2, initiateBodies.Count);
            Assert.Equal("image/png", InitiateContentType(initiateBodies[0]));
            Assert.Equal("image/jpeg", InitiateContentType(initiateBodies[1]));
            Assert.Matches(
                "^rook-seedance-source-[0-9a-f]{32}\\.png$",
                InitiateFileName(initiateBodies[0]));
            Assert.Matches(
                "^rook-seedance-source-[0-9a-f]{32}\\.jpg$",
                InitiateFileName(initiateBodies[1]));

            Assert.Equal("https://uploads.example.test/source-1", handler.Requests[1].RequestUri!.ToString());
            Assert.Equal("https://uploads.example.test/source-2", handler.Requests[3].RequestUri!.ToString());
            Assert.Equal(new[] { "image/png", "image/jpeg" }, putContentTypes);
            Assert.Equal(startBytes, putBodies[0]);
            Assert.Equal(endBytes, putBodies[1]);
        }

        private static FalSeedanceSourceTransport Transport(TestHttpMessageHandler handler) =>
            new(new FalApiClient(new HttpClient(handler)));

        private static TestHttpMessageHandler UploadHandler()
        {
            var uploadIndex = 0;
            return new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        uploadIndex++;
                        var ext = uploadIndex == 1 ? "png" : "jpg";
                        return Json(HttpStatusCode.OK, $$"""
                            {
                              "upload_url": "https://uploads.example.test/source-{{uploadIndex}}",
                              "file_url": "https://v3b.fal.media/files/source-{{uploadIndex}}.{{ext}}"
                            }
                            """);
                    }

                    return new HttpResponseMessage(HttpStatusCode.NoContent);
                },
            };
        }

        private static int CountRequests(TestHttpMessageHandler handler, HttpMethod method)
        {
            var count = 0;
            foreach (var request in handler.Requests)
            {
                if (request.Method == method)
                    count++;
            }

            return count;
        }

        private static string? InitiateContentType(string body)
        {
            using var doc = JsonDocument.Parse(body);
            return doc.RootElement.GetProperty("content_type").GetString();
        }

        private static string? InitiateFileName(string body)
        {
            using var doc = JsonDocument.Parse(body);
            return doc.RootElement.GetProperty("file_name").GetString();
        }

        private static VideoGenerationRequest Request(
            VideoMode mode,
            MediaRef? startFrame,
            MediaRef? endFrame = null,
            IReadOnlyList<MediaRef>? referenceFrames = null,
            string? prompt = "clip") =>
            new(
                Model: FalVideoCapabilities.SeedanceI2v,
                Mode: mode,
                DurationSeconds: 6,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: referenceFrames,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

        private static MediaRef Artifact(string role) =>
            MediaRef.ForArtifact(Guid.NewGuid(), role);

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
            new Dictionary<MediaRef, ResolvedMedia>();

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> Media(
            MediaRef mediaRef,
            byte[] bytes,
            string mimeType) =>
            new Dictionary<MediaRef, ResolvedMedia>
            {
                [mediaRef] = new ResolvedMedia(bytes, mimeType),
            };

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> Media(
            params (MediaRef Ref, ResolvedMedia Media)[] entries)
        {
            var media = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var entry in entries)
                media[entry.Ref] = entry.Media;

            return media;
        }

        private static void AssertInvalid(GenerationError? error, string field)
        {
            Assert.NotNull(error);
            Assert.Equal(GenerationErrorCode.InvalidRequest, error!.Code);
            Assert.False(error.Retryable);
            Assert.Equal(field, error.Field);
        }

        private static HttpResponseMessage Json(HttpStatusCode status, string body) =>
            new(status)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            };

        private static byte[] ImageBytes(string mimeType, int length) =>
            mimeType switch
            {
                "image/png" => PngBytes(length),
                "image/jpeg" => JpegBytes(length),
                "image/webp" => WebPBytes(length),
                _ => throw new ArgumentOutOfRangeException(nameof(mimeType)),
            };

        private static byte[] PngBytes(int length = 12)
        {
            var bytes = new byte[length];
            bytes[0] = 0x89;
            bytes[1] = 0x50;
            bytes[2] = 0x4E;
            bytes[3] = 0x47;
            bytes[4] = 0x0D;
            bytes[5] = 0x0A;
            bytes[6] = 0x1A;
            bytes[7] = 0x0A;
            return bytes;
        }

        private static byte[] JpegBytes(int length = 6)
        {
            var bytes = new byte[length];
            bytes[0] = 0xFF;
            bytes[1] = 0xD8;
            bytes[2] = 0xFF;
            return bytes;
        }

        private static byte[] WebPBytes(int length = 16)
        {
            var bytes = new byte[length];
            bytes[0] = 0x52;
            bytes[1] = 0x49;
            bytes[2] = 0x46;
            bytes[3] = 0x46;
            bytes[8] = 0x57;
            bytes[9] = 0x45;
            bytes[10] = 0x42;
            bytes[11] = 0x50;
            return bytes;
        }

        private static byte[] GifBytes() =>
            new byte[] { 0x47, 0x49, 0x46, 0x38, 1, 2, 3 };
    }
}
