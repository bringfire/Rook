using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateFileTransportTests
    {
        [Fact]
        public async Task UploadAsync_http_failure_returns_dependency_failure()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    Assert.Equal(HttpMethod.Post, req.Method);
                    Assert.Equal("https://api.replicate.com/v1/files", req.RequestUri!.ToString());
                    return new HttpResponseMessage(HttpStatusCode.InternalServerError)
                    {
                        Content = new StringContent(
                            "{\"error\":\"unavailable\"}",
                            Encoding.UTF8,
                            "application/json"),
                    };
                },
            };
            var transport = Transport(handler);

            var result = await transport.UploadAsync(
                "r8_token",
                "source.png",
                new byte[] { 1, 2, 3 },
                "image/png",
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Null(result.Url);
            AssertTransportUnavailable(result.Error);
            Assert.Contains("HTTP 500", result.Error!.Message);
            Assert.Contains("unavailable", result.Error.Message);
        }

        [Fact]
        public async Task UploadAsync_malformed_response_returns_dependency_failure()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        "{\"id\":\"file-1\",\"urls\":{\"get\":123}}",
                        Encoding.UTF8,
                        "application/json"),
                },
            };
            var transport = Transport(handler);

            var result = await transport.UploadAsync(
                "r8_token",
                "source.png",
                new byte[] { 1, 2, 3 },
                "image/png",
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Null(result.Url);
            AssertTransportUnavailable(result.Error);
        }

        [Fact]
        public async Task UploadAsync_caller_cancellation_is_rethrown()
        {
            var handler = new TestHttpMessageHandler();
            var transport = Transport(handler);
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
                transport.UploadAsync(
                    "r8_token",
                    "source.png",
                    new byte[] { 1, 2, 3 },
                    "image/png",
                    cts.Token));
        }

        private static ReplicateFileTransport Transport(TestHttpMessageHandler handler) =>
            new(new ReplicateApiClient(new HttpClient(handler)));

        private static void AssertTransportUnavailable(GenerationError? error)
        {
            Assert.NotNull(error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, error!.Code);
            Assert.True(error.Retryable);
            Assert.Equal("input_image_path", error.Field);
            Assert.Contains("Replicate file upload transport is unavailable", error.Message);
        }
    }
}
