using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoArtifactMaterializerTests
    {
        [Fact]
        public async Task Inline_under_cap_materializes_without_http()
        {
            var handler = new CapturingHandler(_ =>
                throw new InvalidOperationException("HTTP should not be called."));
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Inline(new byte[] { 1, 2, 3, 4 }, "video/mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, result.Bytes);
            Assert.Equal("video/mp4", result.MimeType);
            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task Inline_over_cap_fails()
        {
            var materializer = new VideoArtifactMaterializer(
                maxGeneratedVideoBytes: 3);

            var result = await materializer.MaterializeAsync(
                Inline(new byte[] { 1, 2, 3, 4 }, "video/mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_content_length_over_cap_fails_before_read()
        {
            var content = new ReadTrackingContent(length: 5);
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK) { Content = content });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.False(content.WasRead);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_missing_content_length_fails_when_stream_crosses_cap()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(new RepeatingStream(length: 5)),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_exactly_cap_is_allowed()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1, 2, 3, 4 }),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, result.Bytes);
            Assert.Equal("video/mp4", result.MimeType);
        }

        [Fact]
        public async Task Remote_empty_body_fails()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(Array.Empty<byte>()),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_does_not_send_authorization_header()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.Null(Assert.Single(handler.Requests).Headers.Authorization);
        }

        [Fact]
        public async Task Remote_transport_error_is_retried_before_success()
        {
            var calls = 0;
            var handler = new CapturingHandler(_ =>
            {
                calls++;
                if (calls == 1)
                    throw new HttpRequestException("connection reset");

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1, 2, 3 }),
                };
            });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(new byte[] { 1, 2, 3 }, result.Bytes);
            Assert.Equal(2, handler.Requests.Count);
        }

        [Fact]
        public async Task Declared_mime_wins_over_response_mime()
        {
            var handler = new CapturingHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType =
                    new MediaTypeHeaderValue("video/webm");
                return response;
            });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out", "video/mp4"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/mp4", result.MimeType);
        }

        [Fact]
        public async Task Response_mime_used_when_declared_absent()
        {
            var handler = new CapturingHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType =
                    new MediaTypeHeaderValue("video/webm");
                return response;
            });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/webm", result.MimeType);
        }

        [Fact]
        public async Task Fallback_mime_is_mp4()
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("video/mp4", result.MimeType);
        }

        [Theory]
        [InlineData(HttpStatusCode.BadRequest, false)]
        [InlineData(HttpStatusCode.ServiceUnavailable, true)]
        public async Task Remote_non_success_http_maps_dependency_unavailable(
            HttpStatusCode statusCode,
            bool retryable)
        {
            var handler = new CapturingHandler(_ =>
                new HttpResponseMessage(statusCode)
                {
                    Content = new StringContent("secret token detail"),
                });
            var materializer = new VideoArtifactMaterializer(
                handler,
                maxGeneratedVideoBytes: 4);

            var result = await materializer.MaterializeAsync(
                Remote("https://cdn.example.test/out.mp4?token=secret"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.Equal(retryable, result.Error.Retryable);
            Assert.DoesNotContain("token", result.Error.Message);
        }

        [Fact]
        public async Task Null_artifact_throws_argument_null_exception()
        {
            var materializer = new VideoArtifactMaterializer();

            await Assert.ThrowsAsync<ArgumentNullException>(
                async () => await materializer.MaterializeAsync(
                    null!,
                    CancellationToken.None));
        }

        private static ResultArtifact Inline(byte[] bytes, string mime) =>
            new ResultArtifact(
                Role: VideoMediaRoles.Video,
                Body: new InlineArtifactBody(bytes),
                DeclaredMimeType: mime,
                ProviderMetadata: EmptyMetadata());

        private static ResultArtifact Remote(
            string url,
            string? declaredMimeType = null) =>
            new ResultArtifact(
                Role: VideoMediaRoles.Video,
                Body: new RemoteArtifactBody(new Uri(url)),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: EmptyMetadata());

        private static IReadOnlyDictionary<string, JsonNode> EmptyMetadata() =>
            new Dictionary<string, JsonNode>();

        private sealed class CapturingHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, HttpResponseMessage> _onSend;

            public CapturingHandler(
                Func<HttpRequestMessage, HttpResponseMessage> onSend)
            {
                _onSend = onSend;
            }

            public List<HttpRequestMessage> Requests { get; } =
                new List<HttpRequestMessage>();

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                Requests.Add(request);
                return Task.FromResult(_onSend(request));
            }
        }

        private sealed class ReadTrackingContent : HttpContent
        {
            private readonly long _length;

            public ReadTrackingContent(long length)
            {
                _length = length;
                Headers.ContentLength = length;
            }

            public bool WasRead { get; private set; }

            protected override Task SerializeToStreamAsync(
                Stream stream,
                TransportContext? context)
            {
                WasRead = true;
                return Task.CompletedTask;
            }

            protected override bool TryComputeLength(out long length)
            {
                length = _length;
                return true;
            }
        }

        private sealed class RepeatingStream : Stream
        {
            private long _remaining;

            public RepeatingStream(long length)
            {
                _remaining = length;
            }

            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();

            public override long Position
            {
                get => throw new NotSupportedException();
                set => throw new NotSupportedException();
            }

            public override void Flush() { }

            public override int Read(byte[] buffer, int offset, int count)
            {
                if (_remaining <= 0)
                    return 0;

                var toRead = (int)Math.Min(count, _remaining);
                for (var i = 0; i < toRead; i++)
                    buffer[offset + i] = 42;
                _remaining -= toRead;
                return toRead;
            }

            public override long Seek(long offset, SeekOrigin origin) =>
                throw new NotSupportedException();

            public override void SetLength(long value) =>
                throw new NotSupportedException();

            public override void Write(byte[] buffer, int offset, int count) =>
                throw new NotSupportedException();
        }
    }
}
