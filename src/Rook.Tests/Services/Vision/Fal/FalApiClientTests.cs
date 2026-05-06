using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalApiClientTests
    {
        [Fact]
        public async Task PostJsonAsync_sends_key_auth_and_json_body()
        {
            string? requestBody = null;
            string? requestMediaType = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    requestMediaType = req.Content!.Headers.ContentType!.MediaType;
                    requestBody = req.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json"),
                    };
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var response = await client.PostJsonAsync(
                "test-key",
                new Uri("https://fal.run/fal-ai/flux/schnell"),
                "{\"prompt\":\"red cube\"}",
                CancellationToken.None);

            Assert.Equal(200, response.StatusCode);
            Assert.Equal("{\"ok\":true}", response.Body);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("Key", request.Headers.Authorization!.Scheme);
            Assert.Equal("test-key", request.Headers.Authorization.Parameter);
            Assert.Equal("application/json", requestMediaType);
            Assert.Equal("{\"prompt\":\"red cube\"}", requestBody);
        }

        [Fact]
        public async Task PostJsonAsync_can_send_seedance_queue_platform_headers()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            await client.PostJsonAsync(
                "test-key",
                new Uri("https://queue.fal.run/fal-ai/seedance/submit"),
                "{}",
                FalJsonPlatformHeaders.ForSeedanceSubmit(
                    objectLifecyclePreferenceSeconds: 3600,
                    disableStoreIo: true,
                    disableFalRetry: true),
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(
                "{\"expiration_duration_seconds\":3600}",
                Assert.Single(request.Headers.GetValues("X-Fal-Object-Lifecycle-Preference")));
            Assert.Equal("0", Assert.Single(request.Headers.GetValues("X-Fal-Store-IO")));
            Assert.Equal("1", Assert.Single(request.Headers.GetValues("X-Fal-No-Retry")));
        }

        [Fact]
        public async Task PostJsonAsync_does_not_send_platform_headers_when_absent()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            await client.PostJsonAsync(
                "test-key",
                new Uri("https://queue.fal.run/fal-ai/seedance/submit"),
                "{}",
                CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.False(request.Headers.Contains("X-Fal-Object-Lifecycle-Preference"));
            Assert.False(request.Headers.Contains("X-Fal-Store-IO"));
            Assert.False(request.Headers.Contains("X-Fal-No-Retry"));
        }

        [Fact]
        public async Task UploadFileToCdnAsync_initiates_upload_then_puts_raw_bytes()
        {
            string? initiateBody = null;
            string? uploadBody = null;
            string? uploadContentType = null;
            var bytes = new byte[] { 1, 2, 3, 4 };
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        initiateBody = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                        return new HttpResponseMessage(HttpStatusCode.OK)
                        {
                            Content = new StringContent(
                                """
                                {
                                  "upload_url": "https://uploads.example.test/source-token",
                                  "file_url": "https://v3b.fal.media/files/source.png"
                                }
                                """,
                                Encoding.UTF8,
                                "application/json"),
                        };
                    }

                    uploadContentType = req.Content!.Headers.ContentType!.MediaType;
                    uploadBody = Convert.ToBase64String(
                        req.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult());
                    return new HttpResponseMessage(HttpStatusCode.NoContent);
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var fileUrl = await client.UploadFileToCdnAsync(
                "test-key",
                "source.png",
                bytes,
                "image/png",
                FalUploadPlatformHeaders.ForSourceUpload(3600),
                CancellationToken.None);

            Assert.Equal("https://v3b.fal.media/files/source.png", fileUrl);
            Assert.Equal(2, handler.Requests.Count);

            var initiate = handler.Requests[0];
            Assert.Equal(HttpMethod.Post, initiate.Method);
            Assert.Equal(
                "https://rest.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3",
                initiate.RequestUri!.ToString());
            Assert.Equal("Key", initiate.Headers.Authorization!.Scheme);
            Assert.Equal("test-key", initiate.Headers.Authorization.Parameter);
            Assert.Equal("application/json", initiate.Content!.Headers.ContentType!.MediaType);
            Assert.Equal(
                "{\"expiration_duration_seconds\":3600}",
                Assert.Single(initiate.Headers.GetValues("X-Fal-Object-Lifecycle")));
            Assert.Contains("\"content_type\":\"image/png\"", initiateBody);
            Assert.Contains("\"file_name\":\"source.png\"", initiateBody);

            var upload = handler.Requests[1];
            Assert.Equal(HttpMethod.Put, upload.Method);
            Assert.Equal("https://uploads.example.test/source-token", upload.RequestUri!.ToString());
            Assert.Null(upload.Headers.Authorization);
            Assert.Equal("image/png", uploadContentType);
            Assert.Equal(Convert.ToBase64String(bytes), uploadBody);
        }

        [Theory]
        [InlineData("../secret.png")]
        [InlineData("/absolute.png")]
        [InlineData("rook\\secret.png")]
        [InlineData("https://rest.fal.ai/file.png")]
        public async Task UploadFileToCdnAsync_rejects_unsafe_file_names(string fileName)
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    fileName,
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public async Task UploadFileToCdnAsync_rejects_empty_api_key_before_http(string apiKey)
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.UploadFileToCdnAsync(
                    apiKey,
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_rejects_null_bytes_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentNullException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    null!,
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_rejects_empty_bytes_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    Array.Empty<byte>(),
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public async Task UploadFileToCdnAsync_rejects_empty_content_type_before_http(
            string contentType)
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    contentType,
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_rejects_invalid_content_type_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "not a valid media type",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_rejects_default_upload_platform_headers_before_http()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentNullException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    default,
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("")]
        [InlineData("{}")]
        [InlineData("{\"upload_url\":\"https://uploads.example.test/source-token\"}")]
        [InlineData("{\"file_url\":\"https://v3b.fal.media/files/source.png\"}")]
        [InlineData("{\"upload_url\":\"http://uploads.example.test/source-token\",\"file_url\":\"https://v3b.fal.media/files/source.png\"}")]
        [InlineData("{\"upload_url\":\"https://uploads.example.test/source-token\",\"file_url\":\"https://example.com/files/source.png\"}")]
        public async Task UploadFileToCdnAsync_rejects_invalid_initiate_response(string responseBody)
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(responseBody, Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var ex = await Assert.ThrowsAsync<FalApiException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            if (responseBody.Length > 0)
                Assert.DoesNotContain(responseBody, ex.Message);
            Assert.Single(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_sanitizes_initiate_non_success_failures()
        {
            const string forbiddenBody = """
                {
                  "upload_url": "https://uploads.example.test/source-token",
                  "file_url": "https://v3b.fal.media/files/source.png",
                  "header": "X-Fal-Object-Lifecycle",
                  "request": { "content_type": "image/png", "file_name": "source.png" }
                }
                """;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.InternalServerError)
                {
                    Content = new StringContent(forbiddenBody, Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var ex = await Assert.ThrowsAsync<FalApiException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            AssertUploadExceptionIsSanitized(ex);
            Assert.Single(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_sanitizes_initiate_transport_failures()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => throw new HttpRequestException(ForbiddenTransportMessage),
            };
            var client = new FalApiClient(new HttpClient(handler));

            var ex = await Assert.ThrowsAsync<FalApiException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            AssertTransportExceptionIsSanitized(ex);
            Assert.Single(handler.Requests);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_sanitizes_put_non_success_failures()
        {
            const string forbiddenPutBody = """
                {
                  "upload_url": "https://uploads.example.test/source-token",
                  "file_url": "https://v3b.fal.media/files/source.png",
                  "header": "X-Fal-Object-Lifecycle",
                  "request": { "content_type": "image/png", "file_name": "source.png" }
                }
                """;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        return new HttpResponseMessage(HttpStatusCode.OK)
                        {
                            Content = new StringContent(
                                """
                                {
                                  "upload_url": "https://uploads.example.test/source-token",
                                  "file_url": "https://v3b.fal.media/files/source.png"
                                }
                                """,
                                Encoding.UTF8,
                                "application/json"),
                        };
                    }

                    return new HttpResponseMessage(HttpStatusCode.InternalServerError)
                    {
                        Content = new StringContent(forbiddenPutBody, Encoding.UTF8, "application/json"),
                    };
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var ex = await Assert.ThrowsAsync<FalApiException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            AssertUploadExceptionIsSanitized(ex);
            Assert.Equal(2, handler.Requests.Count);
            Assert.Equal(HttpMethod.Put, handler.Requests[1].Method);
            Assert.Null(handler.Requests[1].Headers.Authorization);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_sanitizes_put_transport_failures()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    if (req.RequestUri!.Host == "rest.fal.ai")
                    {
                        return new HttpResponseMessage(HttpStatusCode.OK)
                        {
                            Content = new StringContent(
                                """
                                {
                                  "upload_url": "https://v3b.fal.media/upload/presigned-token",
                                  "file_url": "https://v3b.fal.media/files/source.png"
                                }
                                """,
                                Encoding.UTF8,
                                "application/json"),
                        };
                    }

                    throw new HttpRequestException(ForbiddenTransportMessage);
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var ex = await Assert.ThrowsAsync<FalApiException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    CancellationToken.None));

            AssertTransportExceptionIsSanitized(ex);
            Assert.Equal(2, handler.Requests.Count);
            Assert.Equal(HttpMethod.Put, handler.Requests[1].Method);
            Assert.Null(handler.Requests[1].Headers.Authorization);
        }

        [Fact]
        public async Task UploadFileToCdnAsync_preserves_caller_cancellation()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAsync<TaskCanceledException>(
                async () => await client.UploadFileToCdnAsync(
                    "test-key",
                    "source.png",
                    new byte[] { 1 },
                    "image/png",
                    FalUploadPlatformHeaders.ForSourceUpload(3600),
                    cts.Token));

            Assert.Single(handler.Requests);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(-1)]
        public void Platform_headers_reject_non_positive_lifecycle_seconds(int seconds)
        {
            Assert.Throws<ArgumentOutOfRangeException>(
                () => FalJsonPlatformHeaders.ForSeedanceSubmit(seconds, true, true));
            Assert.Throws<ArgumentOutOfRangeException>(
                () => FalUploadPlatformHeaders.ForSourceUpload(seconds));
        }

        [Fact]
        public async Task GetAsync_preserves_headers_case_insensitively()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    var response = new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"status\":\"COMPLETED\"}", Encoding.UTF8, "application/json"),
                    };
                    response.Headers.TryAddWithoutValidation("X-Fal-Billable-Units", "2.0");
                    return response;
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            var response = await client.GetAsync(
                "test-key",
                new Uri("https://queue.fal.run/status/abc"),
                CancellationToken.None);

            Assert.True(response.Headers.ContainsKey("x-fal-billable-units"));
            Assert.Equal("2.0", response.Headers["x-fal-billable-units"][0]);
        }

        [Theory]
        [InlineData("POST")]
        [InlineData("PUT")]
        [InlineData("DELETE")]
        public async Task SendAsync_supports_cancel_methods(string method)
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                },
            };
            var client = new FalApiClient(new HttpClient(handler));

            await client.SendAsync(
                "test-key",
                new HttpMethod(method),
                new Uri("https://queue.fal.run/cancel/abc"),
                bodyJson: null,
                CancellationToken.None);

            Assert.Equal(method, handler.Requests.Last().Method.Method);
        }

        [Fact]
        public async Task SendAsync_rejects_non_http_urls_before_adding_auth()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.GetAsync(
                    "test-key",
                    new Uri("file:///C:/temp/secret.json"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public async Task SendAsync_rejects_http_fal_urls_before_adding_auth()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.GetAsync(
                    "test-key",
                    new Uri("http://queue.fal.run/status/abc"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("https://example.com/status/abc")]
        [InlineData("https://evilfal.run/status/abc")]
        [InlineData("https://fal.run.evil.com/status/abc")]
        public async Task SendAsync_rejects_non_fal_https_urls_before_adding_auth(string url)
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.GetAsync(
                    "test-key",
                    new Uri(url),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        private static void AssertUploadExceptionIsSanitized(FalApiException ex)
        {
            Assert.DoesNotContain("upload_url", ex.Message);
            Assert.DoesNotContain("file_url", ex.Message);
            Assert.DoesNotContain("https://uploads.example.test/source-token", ex.Message);
            Assert.DoesNotContain("https://v3b.fal.media/files/source.png", ex.Message);
            Assert.DoesNotContain("X-Fal-Object-Lifecycle", ex.Message);
            Assert.DoesNotContain("content_type", ex.Message);
            Assert.DoesNotContain("file_name", ex.Message);
            Assert.DoesNotContain("source.png", ex.Message);
            Assert.DoesNotContain("image/png", ex.Message);
        }

        private static void AssertTransportExceptionIsSanitized(FalApiException ex)
        {
            Assert.DoesNotContain("https://v3b.fal.media/upload/presigned-token", ex.Message);
            Assert.DoesNotContain("https://v3b.fal.media/files/source.png", ex.Message);
            Assert.DoesNotContain("X-Fal-Object-Lifecycle", ex.Message);
            Assert.DoesNotContain("{\"content_type\":\"image/png\"}", ex.Message);
            Assert.DoesNotContain("content_type", ex.Message);
            Assert.DoesNotContain("image/png", ex.Message);
        }

        private const string ForbiddenTransportMessage =
            "Transport failed for https://v3b.fal.media/upload/presigned-token " +
            "and https://v3b.fal.media/files/source.png with X-Fal-Object-Lifecycle " +
            "and {\"content_type\":\"image/png\"}.";
    }
}
