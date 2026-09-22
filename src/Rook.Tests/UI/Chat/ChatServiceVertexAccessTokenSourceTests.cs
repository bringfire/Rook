using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class ChatServiceVertexAccessTokenSourceTests
    {
        private static readonly DateTimeOffset Now =
            DateTimeOffset.FromUnixTimeSeconds(1_800_000_000);

        [Fact]
        public async Task AcquireAsync_UsesOneAtomicConnectionSnapshotAndExactRequest()
        {
            var acquireCalls = 0;
            HttpRequestMessage? capturedRequest = null;
            string? capturedBody = null;
            var handler = new DelegateHandler(async (request, _) =>
            {
                capturedRequest = request;
                capturedBody = await request.Content!.ReadAsStringAsync();
                return JsonResponse(
                    HttpStatusCode.OK,
                    SuccessJson(
                        token: "short-lived-token",
                        expiry: Now.ToUnixTimeSeconds() + 600));
            });
            var httpClient = new HttpClient(handler)
            {
                Timeout = TimeSpan.FromMilliseconds(1),
            };
            var source = new ChatServiceVertexAccessTokenSource(
                _ =>
                {
                    acquireCalls++;
                    return Task.FromResult<ChatServiceConnectionSnapshot?>(
                        new ChatServiceConnectionSnapshot(
                            new Uri("http://127.0.0.1:43123"),
                            "one-snapshot-nonce"));
                },
                httpClient,
                () => Now);

            var result = await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            Assert.Equal(1, acquireCalls);
            Assert.NotNull(result.Lease);
            Assert.Null(result.Failure);
            Assert.Equal("short-lived-token", result.Lease!.AccessToken);
            Assert.Equal("company-project", result.Lease.ProjectId);
            Assert.Equal("global", result.Lease.Location);
            Assert.Equal("0123456789abcdef0123456789abcdef", result.Lease.Generation);
            Assert.Equal(
                new Uri("http://127.0.0.1:43123/internal/providers/vertex/access-token"),
                capturedRequest!.RequestUri);
            Assert.Equal(HttpMethod.Post, capturedRequest.Method);
            Assert.False(capturedRequest.Headers.Contains("Origin"));
            Assert.Equal(
                "one-snapshot-nonce",
                Assert.Single(capturedRequest.Headers.GetValues("X-Rook-Session")));
            Assert.Equal(
                "{\"model\":\"vertex_ai/gemini-3.1-flash-image\"}",
                capturedBody);
            Assert.Equal(TimeSpan.FromSeconds(35), ChatServiceVertexAccessTokenSource.RouteTimeout);
            Assert.Equal(Timeout.InfiniteTimeSpan, httpClient.Timeout);
        }

        [Fact]
        public async Task AcquireAsync_UnavailableConnectionFailsBeforeTransport()
        {
            var acquireCalls = 0;
            var handler = new DelegateHandler((_, _) =>
                throw new InvalidOperationException("transport must not run"));
            var source = new ChatServiceVertexAccessTokenSource(
                _ =>
                {
                    acquireCalls++;
                    return Task.FromResult<ChatServiceConnectionSnapshot?>(null);
                },
                new HttpClient(handler),
                () => Now);

            var result = await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            Assert.Equal(1, acquireCalls);
            Assert.Null(result.Lease);
            AssertFailure(
                result,
                "vertex_token_service_unavailable",
                "The internal Vertex token service is unavailable.",
                retryable: true);
            Assert.Equal(0, handler.CallCount);
        }

        [Fact]
        public async Task AcquireAsync_NonLoopbackSnapshotFailsBeforeNonceEgress()
        {
            var handler = new DelegateHandler((_, _) =>
                throw new InvalidOperationException("transport must not run"));
            var source = new ChatServiceVertexAccessTokenSource(
                _ => Task.FromResult<ChatServiceConnectionSnapshot?>(
                    new ChatServiceConnectionSnapshot(
                        new Uri("http://example.com:43123"),
                        "must-not-leave-machine")),
                new HttpClient(handler),
                () => Now);

            var result = await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            AssertFailure(
                result,
                "vertex_token_service_unavailable",
                "The internal Vertex token service is unavailable.",
                retryable: true);
            Assert.Equal(0, handler.CallCount);
        }

        [Theory]
        [InlineData("not-json")]
        [InlineData("{\"success\":true,\"data\":{\"access_token\":\"token\"}}")]
        [InlineData("{\"success\":false,\"error\":{\"code\":\"unknown\",\"message\":\"hostile detail\"}}")]
        public async Task AcquireAsync_MalformedOrUnknownEnvelopeReturnsFixedInvalidResponse(
            string responseJson)
        {
            var result = await AcquireFromResponseAsync(HttpStatusCode.OK, responseJson);

            AssertFailure(
                result,
                "vertex_token_response_invalid",
                "The internal Vertex token response is invalid.",
                retryable: true);
            Assert.DoesNotContain("hostile", result.Failure!.Message, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public async Task AcquireAsync_ExpiredLeaseNeverFallsBack()
        {
            var result = await AcquireFromResponseAsync(
                HttpStatusCode.OK,
                SuccessJson("expired-token", Now.ToUnixTimeSeconds()));

            AssertFailure(
                result,
                "vertex_token_response_invalid",
                "The internal Vertex token response is invalid.",
                retryable: true);
        }

        [Fact]
        public async Task AcquireAsync_NonGlobalLeaseReturnsFixedRegionFailure()
        {
            var json = SuccessJson(
                "regional-token",
                Now.ToUnixTimeSeconds() + 600,
                location: "us-central1");

            var result = await AcquireFromResponseAsync(HttpStatusCode.OK, json);

            AssertFailure(
                result,
                "vertex_model_region_unsupported",
                "Vertex AI Nano Banana 2 requires the global location.",
                retryable: false);
        }

        [Fact]
        public async Task AcquireAsync_InvalidGenerationReturnsFixedInvalidResponse()
        {
            var result = await AcquireFromResponseAsync(
                HttpStatusCode.OK,
                SuccessJson(
                    "generation-token",
                    Now.ToUnixTimeSeconds() + 600,
                    generation: "not-a-generation"));

            AssertFailure(
                result,
                "vertex_token_response_invalid",
                "The internal Vertex token response is invalid.",
                retryable: true);
        }

        [Fact]
        public async Task AcquireAsync_KnownFailureIgnoresProviderMessage()
        {
            var result = await AcquireFromResponseAsync(
                HttpStatusCode.Conflict,
                "{\"success\":false,\"error\":{\"code\":\"vertex_signed_out\",\"message\":\"private credential detail\"}}");

            AssertFailure(
                result,
                "vertex_signed_out",
                "Vertex AI is not configured for this Windows user.",
                retryable: false);
            Assert.DoesNotContain("private credential detail", result.Failure!.Message);
        }

        [Fact]
        public async Task AcquireAsync_PythonIssuanceTimeoutRetainsFixedTaxonomy()
        {
            var result = await AcquireFromResponseAsync(
                HttpStatusCode.GatewayTimeout,
                "{\"success\":false,\"error\":{\"code\":\"vertex_token_issuance_timeout\",\"message\":\"Vertex token issuance timed out.\"}}");

            AssertFailure(
                result,
                "vertex_token_issuance_timeout",
                "Vertex token issuance timed out.",
                retryable: true);
        }

        [Fact]
        public async Task AcquireAsync_AdapterDeadlineReturnsIssuanceTimeoutPromptly()
        {
            var handler = new DelegateHandler(async (_, ct) =>
            {
                await Task.Delay(Timeout.Infinite, ct);
                throw new InvalidOperationException("unreachable");
            });
            var source = new ChatServiceVertexAccessTokenSource(
                _ => Task.FromResult<ChatServiceConnectionSnapshot?>(
                    new ChatServiceConnectionSnapshot(
                        new Uri("http://127.0.0.1:43123"),
                        "one-snapshot-nonce")),
                new HttpClient(handler),
                () => Now,
                routeTimeout: TimeSpan.FromMilliseconds(25));
            var stopwatch = Stopwatch.StartNew();

            var result = await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            stopwatch.Stop();
            AssertFailure(
                result,
                "vertex_token_issuance_timeout",
                "Vertex token issuance timed out.",
                retryable: true);
            Assert.True(
                stopwatch.Elapsed < TimeSpan.FromSeconds(2),
                $"Injected adapter deadline took {stopwatch.Elapsed}.");
        }

        [Fact]
        public async Task AcquireAsync_PreservesCallerCancellation()
        {
            var handler = new DelegateHandler(async (_, ct) =>
            {
                await Task.Delay(Timeout.Infinite, ct);
                throw new InvalidOperationException("unreachable");
            });
            var source = CreateSource(new HttpClient(handler));
            using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(25));

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
                source.AcquireAsync(
                    "vertex_ai/gemini-3.1-flash-image",
                    cts.Token));
        }

        [Fact]
        public async Task AcquireAsync_UnrelatedTransportCancellationReturnsUnavailable()
        {
            using var transportCts = new CancellationTokenSource();
            transportCts.Cancel();
            var handler = new DelegateHandler((_, _) =>
                Task.FromCanceled<HttpResponseMessage>(transportCts.Token));
            var source = CreateSource(new HttpClient(handler));

            var result = await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            AssertFailure(
                result,
                "vertex_token_service_unavailable",
                "The internal Vertex token service is unavailable.",
                retryable: true);
        }

        [Fact]
        public void LeaseToString_RedactsAccessToken()
        {
            var lease = new VertexAccessTokenLease(
                "secret-token-sentinel",
                Now.ToUnixTimeSeconds() + 600,
                "company-project",
                "global",
                "0123456789abcdef0123456789abcdef");

            Assert.Equal("VertexAccessTokenLease(<redacted>)", lease.ToString());
            Assert.DoesNotContain("secret-token-sentinel", lease.ToString());
        }

        [Fact]
        public void AdapterSource_DoesNotReadDiscoveryOrMutableManagerNonce()
        {
            var source = ReadSourceFile(
                "src", "Rook", "UI", "Chat", "ChatServiceVertexAccessTokenSource.cs");

            Assert.DoesNotContain("Discovery", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("ChatServiceManager.Instance.SessionNonce", source);
            Assert.Contains("ChatServiceConnectionSnapshot", source);
            Assert.Contains("CancellationTokenSource.CreateLinkedTokenSource", source);
            Assert.Contains("deadline.CancelAfter(_routeTimeout);", source);
            Assert.DoesNotContain("RhinoApp.WriteLine", source);
            Assert.DoesNotContain("Console.", source);
        }

        private static ChatServiceVertexAccessTokenSource CreateSource(HttpClient client) =>
            new ChatServiceVertexAccessTokenSource(
                _ => Task.FromResult<ChatServiceConnectionSnapshot?>(
                    new ChatServiceConnectionSnapshot(
                        new Uri("http://127.0.0.1:43123"),
                        "one-snapshot-nonce")),
                client,
                () => Now);

        private static async Task<VertexAccessTokenResult> AcquireFromResponseAsync(
            HttpStatusCode status,
            string json)
        {
            var handler = new DelegateHandler((_, _) =>
                Task.FromResult(JsonResponse(status, json)));
            var source = CreateSource(new HttpClient(handler));
            return await source.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);
        }

        private static HttpResponseMessage JsonResponse(HttpStatusCode status, string json) =>
            new HttpResponseMessage(status)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };

        private static string SuccessJson(
            string token,
            long expiry,
            string project = "company-project",
            string location = "global",
            string generation = "0123456789abcdef0123456789abcdef") =>
            "{\"success\":true,\"data\":{" +
            $"\"access_token\":\"{token}\"," +
            $"\"expires_at_unix_seconds\":{expiry}," +
            $"\"project_id\":\"{project}\"," +
            $"\"location\":\"{location}\"," +
            $"\"generation\":\"{generation}\"}}}}";

        private static void AssertFailure(
            VertexAccessTokenResult result,
            string code,
            string message,
            bool retryable)
        {
            Assert.Null(result.Lease);
            Assert.NotNull(result.Failure);
            Assert.Equal(code, result.Failure!.Code);
            Assert.Equal(message, result.Failure.Message);
            Assert.Equal(retryable, result.Failure.Retryable);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }
            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private sealed class DelegateHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _send;

            public DelegateHandler(
                Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send)
            {
                _send = send;
            }

            public int CallCount { get; private set; }

            protected override Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                CallCount++;
                return _send(request, cancellationToken);
            }
        }
    }
}
