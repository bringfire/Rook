using System;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction
{
    public class NativeEndpointSelectionTests
    {
        private static JsonObject Doc(string pluginType, int processId, int port, string host = "127.0.0.1") => new()
        {
            ["pluginType"] = pluginType,
            ["processId"] = processId,
            ["port"] = port,
            ["host"] = host,
        };

        [Fact]
        public void Selects_Native_Entry_For_Current_Process()
        {
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Equal(51000, NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_When_No_Native_Entry_For_This_Process()
        {
            var docs = new[] { Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_For_Empty()
        {
            Assert.Null(NativeEndpointResolver.SelectNativePort(new JsonObject[0], currentProcessId: 4242));
        }

        [Fact]
        public void Ambiguous_Same_Process_Native_Entries_Return_Null()
        {
            // Two DIFFERENT native endpoints for THIS pid (stale/conflict) — fail closed, don't guess.
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 4242, 52000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Rejects_NonLoopback_Host()
        {
            // "no arbitrary URL" pinned at discovery: a native+current-pid record with a
            // non-loopback host must NOT be selected.
            var docs = new[] { Doc("native", 4242, 51000, host: "evil.example.com") };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Duplicate_Identical_Entries_Resolve_Not_Ambiguous()
        {
            // Same endpoint mirrored into shared + legacy discovery folders — dedupe, resolve.
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 4242, 51000) };
            Assert.Equal(51000, NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }
    }

    public class NativeReconstructionImportClientTests
    {
        private sealed class StubResolver : INativeEndpointResolver
        {
            private readonly int? _port;
            public StubResolver(int? port) { _port = port; }
            public int? ResolveNativePort() => _port;
        }

        private sealed class CapturingHandler : HttpMessageHandler
        {
            private readonly HttpStatusCode _status;
            private readonly string _body;
            public string? RequestUri;
            public string? RequestBody;
            public string? RequestContentType;
            public string? ClientHeader;
            public CapturingHandler(HttpStatusCode status, string body) { _status = status; _body = body; }
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                RequestUri = request.RequestUri!.AbsoluteUri;
                RequestContentType = request.Content?.Headers?.ContentType?.MediaType;
                ClientHeader = request.Headers.TryGetValues(NativeReconstructionImportClient.NativeClientHeader, out var values) ? string.Join(",", values) : null;
                RequestBody = request.Content is null ? null : await request.Content.ReadAsStringAsync().ConfigureAwait(false);
                return new HttpResponseMessage(_status) { Content = new StringContent(_body) };
            }
        }

        private sealed class ThrowingHandler : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
                => throw new HttpRequestException("connection refused");
        }

        [Fact]
        public async Task Posts_PackageId_To_Fixed_Loopback_Url_And_Unwraps_Data()
        {
            var cap = new CapturingHandler(HttpStatusCode.OK,
                "{\"success\":true,\"data\":{\"asset_role\":\"model_obj\",\"imported_ids\":[\"a\",\"b\"]}}");
            var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(51000));
            var pkg = Guid.NewGuid();

            var outcome = await client.ImportAsync(pkg, CancellationToken.None);

            Assert.True(outcome.Success);
            // Always the fixed loopback URL with the discovered port — no arbitrary host.
            Assert.Equal("http://127.0.0.1:51000/reconstruction/2d-to-3d/import", cap.RequestUri);
            Assert.Equal("application/json", cap.RequestContentType);
            // The native server admits only requests carrying the Rook client header.
            Assert.Equal(NativeReconstructionImportClient.NativeClientHeaderValue, cap.ClientHeader);
            Assert.Contains(pkg.ToString("D"), cap.RequestBody);
            Assert.Equal("model_obj", (string?)outcome.Data!["asset_role"]);
            Assert.Equal(2, outcome.Data!["imported_ids"]!.AsArray().Count);
            // Exactly one unwrap — the native envelope keys must NOT leak into the UI data.
            Assert.False(outcome.Data!.ContainsKey("success"), "'success' leaked into UI data (double-wrap)");
            Assert.False(outcome.Data!.ContainsKey("data"), "'data' leaked into UI data (double-wrap)");
        }

        [Fact]
        public async Task Maps_AssociationFailed_To_Structured_Failure()
        {
            var cap = new CapturingHandler(HttpStatusCode.InternalServerError,
                "{\"success\":false,\"data\":{\"code\":\"association_failed\",\"message\":\"user-string association failed\"}}");
            var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(51000));

            var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.False(outcome.Success);
            Assert.Equal("association_failed", outcome.Failure!.Code);
        }

        [Fact]
        public async Task AssociationFailed_Preserves_Native_Failure_Details()
        {
            // Partial-success failure: objects imported, association/history failed. The native
            // details (imported_ids/asset_role/association_error) must survive to the UI.
            var cap = new CapturingHandler(HttpStatusCode.InternalServerError,
                "{\"success\":false,\"data\":{\"code\":\"association_failed\",\"message\":\"Import completed, but object association failed.\",\"retryable\":true,\"field\":null,\"details\":{\"imported_ids\":[\"a\",\"b\"],\"asset_role\":\"model_obj\",\"association_error\":\"boom\"}}}");
            var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(51000));

            var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.False(outcome.Success);
            Assert.Equal("association_failed", outcome.Failure!.Code);
            Assert.True(outcome.Failure.Retryable);
            Assert.Contains("imported_ids", outcome.Failure.Details.Keys);
            Assert.Contains("asset_role", outcome.Failure.Details.Keys);
            Assert.Contains("association_error", outcome.Failure.Details.Keys);
        }

        [Fact]
        public async Task No_Endpoint_Returns_NativeUnavailable_Without_Posting()
        {
            var cap = new CapturingHandler(HttpStatusCode.OK, "{}");
            var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(null));

            var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.False(outcome.Success);
            Assert.Equal("native_unavailable", outcome.Failure!.Code);
            Assert.Null(cap.RequestUri);   // never posted
        }

        [Fact]
        public async Task Transport_Fault_Maps_To_NativeUnavailable()
        {
            var client = new NativeReconstructionImportClient(new HttpClient(new ThrowingHandler()), new StubResolver(51000));

            var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.False(outcome.Success);
            Assert.Equal("native_unavailable", outcome.Failure!.Code);
        }
    }
}
