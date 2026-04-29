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
            var handler = new TestHttpMessageHandler
            {
                OnSend = req => new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json"),
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
            Assert.Equal("application/json", request.Content!.Headers.ContentType!.MediaType);
            Assert.Equal("{\"prompt\":\"red cube\"}", await request.Content.ReadAsStringAsync());
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

        [Fact]
        public async Task SendAsync_rejects_non_fal_https_urls_before_adding_auth()
        {
            var handler = new TestHttpMessageHandler();
            var client = new FalApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(
                async () => await client.GetAsync(
                    "test-key",
                    new Uri("https://example.com/status/abc"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }
    }
}
