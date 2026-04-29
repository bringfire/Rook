using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageArtifactMaterializerTests
    {
        [Fact]
        public async Task Inline_artifact_returns_existing_bytes_without_http()
        {
            var bytes = new byte[] { 1, 2, 3 };
            var handler = new ThrowingHttpMessageHandler();
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                InlineArtifact(bytes, "image/jpeg"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Same(bytes, result.Bytes);
            Assert.Equal("image/jpeg", result.MimeType);
            Assert.Null(result.Error);
            Assert.Equal(0, handler.SendCount);
        }

        [Fact]
        public async Task Inline_artifact_rejects_bytes_greater_than_max()
        {
            var bytes = new byte[(int)ImageArtifactMaterializer.MaxGeneratedImageBytes + 1];
            var materializer = new ImageArtifactMaterializer();

            var result = await materializer.MaterializeAsync(
                InlineArtifact(bytes, "image/png"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
            Assert.DoesNotContain("http", result.Error.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Null(result.Bytes);
        }

        [Fact]
        public void Inline_artifact_requires_declared_mime_through_result_artifact_invariant()
        {
            Assert.Throws<ArgumentException>(() =>
                InlineArtifact(new byte[] { 1 }, declaredMimeType: null));
        }

        [Fact]
        public async Task Remote_artifact_fetches_url_and_returns_response_bytes()
        {
            var responseBytes = new byte[] { 5, 6, 7 };
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(responseBytes),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(responseBytes, result.Bytes);
            Assert.Equal("https://cdn.example.com/out.png?token=secret", handler.RequestUri!.ToString());
            Assert.Equal(HttpMethod.Get, handler.Method);
        }

        [Fact]
        public async Task Remote_artifact_uses_provider_declared_mime_when_present()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType = new MediaTypeHeaderValue("image/webp");
                return response;
            });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out", "image/jpeg"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("image/jpeg", result.MimeType);
        }

        [Fact]
        public async Task Remote_artifact_falls_back_to_response_content_type_when_declared_mime_is_absent()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
                response.Content.Headers.ContentType = new MediaTypeHeaderValue("image/webp");
                return response;
            });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("image/webp", result.MimeType);
        }

        [Fact]
        public async Task Remote_artifact_falls_back_to_png_when_no_mime_exists()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out"),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal("image/png", result.MimeType);
        }

        [Theory]
        [InlineData(HttpStatusCode.BadRequest, false)]
        [InlineData(HttpStatusCode.ServiceUnavailable, true)]
        public async Task Remote_artifact_rejects_non_success_http_with_typed_sanitized_error(
            HttpStatusCode status,
            bool retryable)
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(status)
                {
                    Content = new StringContent("provider detail with https://secret.example/path?token=abc"),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.Equal(
                $"Remote image artifact fetch failed with HTTP {(int)status}.",
                result.Error.Message);
            Assert.Equal(retryable, result.Error.Retryable);
            Assert.DoesNotContain("token", result.Error.Message);
            Assert.Null(result.Bytes);
        }

        [Fact]
        public async Task Remote_artifact_rejects_empty_response_bytes()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(Array.Empty<byte>()),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_artifact_rejects_content_length_greater_than_max_before_reading()
        {
            var content = new ReadTrackingContent(
                ImageArtifactMaterializer.MaxGeneratedImageBytes + 1);
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = content,
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(content.WasRead);
        }

        [Fact]
        public async Task Remote_artifact_rejects_read_bytes_greater_than_max_when_content_length_is_missing()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(new NonSeekableRepeatingStream(
                        ImageArtifactMaterializer.MaxGeneratedImageBytes + 1)),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.ExecutionFailed, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Remote_artifact_does_not_add_authorization_headers()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.test/files/abc/output.png"),
                CancellationToken.None);

            Assert.Null(handler.Authorization);
        }

        [Fact]
        public async Task Remote_artifact_handler_seam_does_not_send_authorization_header()
        {
            var handler = new CapturingHttpMessageHandler(req =>
            {
                Assert.Null(req.Headers.Authorization);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new ByteArrayContent(new byte[] { 1 }),
                };
            });
            var materializer = new ImageArtifactMaterializer(handler);

            await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png"),
                CancellationToken.None);

            Assert.Null(handler.Authorization);
        }

        [Fact]
        public void Materializer_does_not_expose_httpclient_injection_constructor()
        {
            var constructors = typeof(ImageArtifactMaterializer).GetConstructors(
                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);

            Assert.DoesNotContain(
                constructors,
                ctor => Array.Exists(
                    ctor.GetParameters(),
                    param => param.ParameterType == typeof(HttpClient)));
        }

        [Fact]
        public async Task Transport_exception_maps_dependency_unavailable_retryable()
        {
            var handler = new ThrowingHttpMessageHandler(
                new HttpRequestException("raw transport failure"));
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.True(result.Error.Retryable);
            Assert.DoesNotContain("raw transport failure", result.Error.Message);
            Assert.DoesNotContain("token", result.Error.Message);
        }

        [Fact]
        public async Task Non_caller_timeout_maps_dependency_unavailable_retryable()
        {
            var handler = new ThrowingHttpMessageHandler(
                new TaskCanceledException("raw timeout detail"));
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.True(result.Error.Retryable);
            Assert.DoesNotContain("raw timeout detail", result.Error.Message);
            Assert.DoesNotContain("token", result.Error.Message);
        }

        [Fact]
        public async Task Stream_read_failure_maps_dependency_unavailable_retryable()
        {
            var handler = new CapturingHttpMessageHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(new ThrowingReadStream(
                        new IOException("raw stream failure with token=secret"))),
                });
            var materializer = new ImageArtifactMaterializer(handler);

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
            Assert.True(result.Error.Retryable);
            Assert.DoesNotContain("raw stream failure", result.Error.Message);
            Assert.DoesNotContain("token", result.Error.Message);
        }

        [Fact]
        public async Task Caller_cancellation_maps_interrupted_non_retryable()
        {
            using var cts = new CancellationTokenSource();
            cts.Cancel();
            var materializer = new ImageArtifactMaterializer(
                new CapturingHttpMessageHandler(_ =>
                    new HttpResponseMessage(HttpStatusCode.OK)));

            var result = await materializer.MaterializeAsync(
                RemoteArtifact("https://cdn.example.com/out.png?token=secret"),
                cts.Token);

            Assert.False(result.Success);
            Assert.Equal(GenerationErrorCode.Interrupted, result.Error!.Code);
            Assert.False(result.Error.Retryable);
        }

        [Fact]
        public async Task Null_artifact_throws_argument_null_exception()
        {
            var materializer = new ImageArtifactMaterializer();

            await Assert.ThrowsAsync<ArgumentNullException>(
                async () => await materializer.MaterializeAsync(null!, CancellationToken.None));
        }

        private static ResultArtifact InlineArtifact(
            byte[] bytes,
            string? declaredMimeType) =>
            new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new InlineArtifactBody(bytes),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: EmptyMetadata());

        private static ResultArtifact RemoteArtifact(
            string url,
            string? declaredMimeType = null) =>
            new ResultArtifact(
                Role: ImageMediaRoles.Image,
                Body: new RemoteArtifactBody(new Uri(url)),
                DeclaredMimeType: declaredMimeType,
                ProviderMetadata: EmptyMetadata());

        private static IReadOnlyDictionary<string, JsonNode> EmptyMetadata() =>
            new Dictionary<string, JsonNode>();

        private sealed class CapturingHttpMessageHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, HttpResponseMessage> _onSend;

            public CapturingHttpMessageHandler(
                Func<HttpRequestMessage, HttpResponseMessage> onSend)
            {
                _onSend = onSend;
            }

            public Uri? RequestUri { get; private set; }
            public HttpMethod? Method { get; private set; }
            public AuthenticationHeaderValue? Authorization { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                if (cancellationToken.IsCancellationRequested)
                    return Task.FromCanceled<HttpResponseMessage>(cancellationToken);

                RequestUri = request.RequestUri;
                Method = request.Method;
                Authorization = request.Headers.Authorization;
                return Task.FromResult(_onSend(request));
            }
        }

        private sealed class ThrowingHttpMessageHandler : HttpMessageHandler
        {
            private readonly Exception? _exception;

            public ThrowingHttpMessageHandler(Exception? exception = null)
            {
                _exception = exception;
            }

            public int SendCount { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                SendCount++;
                if (_exception is not null)
                    throw _exception;

                throw new InvalidOperationException("HTTP should not be called.");
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

        private sealed class NonSeekableRepeatingStream : Stream
        {
            private long _remaining;

            public NonSeekableRepeatingStream(long length)
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

        private sealed class ThrowingReadStream : Stream
        {
            private readonly Exception _exception;

            public ThrowingReadStream(Exception exception)
            {
                _exception = exception;
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

            public override int Read(byte[] buffer, int offset, int count) =>
                throw _exception;

            public override Task<int> ReadAsync(
                byte[] buffer,
                int offset,
                int count,
                CancellationToken cancellationToken) =>
                Task.FromException<int>(_exception);

            public override long Seek(long offset, SeekOrigin origin) =>
                throw new NotSupportedException();

            public override void SetLength(long value) =>
                throw new NotSupportedException();

            public override void Write(byte[] buffer, int offset, int count) =>
                throw new NotSupportedException();
        }
    }
}
