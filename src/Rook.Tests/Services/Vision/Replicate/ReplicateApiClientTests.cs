using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Replicate;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicateApiClientTests
    {
        [Fact]
        public async Task CreatePredictionAsync_sends_bearer_auth_and_json_body_to_default_api_host()
        {
            string? body = null;
            var handler = new TestHttpMessageHandler
            {
                OnSend = req =>
                {
                    body = req.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
                    return new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"id\":\"pred-1\"}", Encoding.UTF8, "application/json"),
                    };
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            var response = await client.CreatePredictionAsync(
                "r8_token",
                "v1/models/black-forest-labs/flux-schnell/predictions",
                "{\"input\":{\"prompt\":\"red cube\"}}",
                CancellationToken.None);

            Assert.Equal(200, response.StatusCode);
            Assert.Equal("{\"id\":\"pred-1\"}", response.Body);
            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
            Assert.Equal("application/json", request.Content!.Headers.ContentType!.MediaType);
            Assert.Equal("{\"input\":{\"prompt\":\"red cube\"}}", body);
        }

        [Fact]
        public async Task GetPredictionAsync_sends_bearer_auth_to_default_api_host()
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await client.GetPredictionAsync("r8_token", "pred-1", CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1", request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
        }

        [Fact]
        public async Task CancelPredictionAsync_sends_bearer_auth_to_default_api_host()
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await client.CancelPredictionAsync("r8_token", "pred-1", CancellationToken.None);

            var request = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://api.replicate.com/v1/predictions/pred-1/cancel", request.RequestUri!.ToString());
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
        }

        [Fact]
        public async Task SendApiAsync_rejects_non_api_replicate_hosts()
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(() =>
                client.GetJsonAsync(
                    "r8_token",
                    new Uri("https://replicate.delivery/prediction-output.png"),
                    CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Theory]
        [InlineData("https://api.replicate.com.evil.test/v1/predictions/pred-1")]
        [InlineData("https://evil-api.replicate.com/v1/predictions/pred-1")]
        [InlineData("http://api.replicate.com/v1/predictions/pred-1")]
        public async Task SendApiAsync_rejects_api_host_lookalikes_and_http(string url)
        {
            var handler = new TestHttpMessageHandler();
            var client = new ReplicateApiClient(new HttpClient(handler));

            await Assert.ThrowsAsync<ArgumentException>(() =>
                client.GetJsonAsync("r8_token", new Uri(url), CancellationToken.None));

            Assert.Empty(handler.Requests);
        }

        [Fact]
        public void BuildAuthenticatedOutputRequest_allows_replicate_delivery_with_bearer_auth()
        {
            using var request = ReplicateApiClient.BuildAuthenticatedOutputRequest(
                "r8_token",
                new Uri("https://replicate.delivery/pbxt/output.png"));

            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", request.Headers.Authorization.Parameter);
            Assert.Equal("https://replicate.delivery/pbxt/output.png", request.RequestUri!.ToString());
        }

        [Fact]
        public void BuildAuthenticatedOutputRequest_allows_replicate_delivery_subdomains()
        {
            using var request = ReplicateApiClient.BuildAuthenticatedOutputRequest(
                "r8_token",
                new Uri("https://v3b.replicate.delivery/pbxt/output.png"));

            Assert.Equal("v3b.replicate.delivery", request.RequestUri!.Host);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
        }

        [Theory]
        [InlineData("https://replicate.delivery.evil.test/pbxt/output.png")]
        [InlineData("https://evilreplicate.delivery/pbxt/output.png")]
        [InlineData("http://replicate.delivery/pbxt/output.png")]
        public void BuildAuthenticatedOutputRequest_rejects_output_host_lookalikes_and_http(string url)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicateApiClient.BuildAuthenticatedOutputRequest(
                    "r8_token",
                    new Uri(url)));
        }

        [Fact]
        public async Task GetJsonAsync_preserves_headers_case_insensitively()
        {
            var handler = new TestHttpMessageHandler
            {
                OnSend = _ =>
                {
                    var response = new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("{\"status\":\"processing\"}", Encoding.UTF8, "application/json"),
                    };
                    response.Headers.TryAddWithoutValidation("X-Replicate-Request-Id", "req-1");
                    return response;
                },
            };
            var client = new ReplicateApiClient(new HttpClient(handler));

            var response = await client.GetJsonAsync(
                "r8_token",
                new Uri("https://api.replicate.com/v1/predictions/pred-1"),
                CancellationToken.None);

            Assert.True(response.Headers.ContainsKey("x-replicate-request-id"));
            Assert.Equal("req-1", response.Headers["x-replicate-request-id"].Single());
        }
    }
}
