using System;
using System.Collections.Generic;
using System.Net;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public sealed class VertexBindingV2Tests
    {
        internal static VertexAuthorizationBinding FirmBinding() => new(2, new string('a', 32), "synthetic-firm-project", "global", "vertex_ai/gemini-3.1-flash-image", new string('b', 32), new string('c', 64), "synthetic-user-project", "synthetic-quota-project");

        [Fact]
        public void V1Binding_RoundTripsWithoutExtraFields()
        {
            var binding = new VertexAuthorizationBinding(1, new string('a', 32), "synthetic-firm-project", "global", "vertex_ai/gemini-3.1-flash-image");
            Assert.Equal(5, binding.ToWire().Count);
            Assert.Equal(binding, VertexAuthorizationBinding.FromMetadata(binding.ToMetadata()));
        }

        [Fact]
        public void V2Metadata_UsesExactlyNineFieldsAndRejectsExtras()
        {
            var binding = FirmBinding();
            Assert.Equal(9, binding.ToWire().Count);
            Assert.Equal(binding, VertexAuthorizationBinding.FromMetadata(binding.ToMetadata()));
            var node = (JsonObject)binding.ToMetadata()["vertex_binding"];
            node["access_token"] = "never-ledger-this";
            Assert.Null(VertexAuthorizationBinding.FromMetadata(new Dictionary<string, JsonNode> { ["vertex_binding"] = node }));
        }

        [Theory]
        [InlineData("quota")]
        [InlineData("principal")]
        public async Task V2Lease_RejectsQuotaAndPrincipalMismatch(string mismatch)
        {
            var expected = FirmBinding();
            var returned = mismatch == "principal" ? expected with { PrincipalId = new string('d', 32) } : expected;
            var json = JsonSerializer.Serialize(new { success = true, data = new {
                access_token = "synthetic-token", expires_at_unix_seconds = 1800000600L,
                project_id = returned.ProjectId, location = returned.Location,
                generation = returned.AuthorizationGeneration, binding = returned.ToWire(),
                contract_version = 2, quota_project_id = mismatch == "quota" ? "wrong-quota-project" : returned.QuotaProjectId,
            }});
            var source = Source((request, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(json) }));
            var result = await source.AcquireAsync(expected.ModelId, expected.Location, expected, CancellationToken.None);
            Assert.Null(result.Lease);
            Assert.NotNull(result.Failure);
        }

        [Fact]
        public async Task ValidationV2_UsesClosedShape()
        {
            string? body = null;
            var source = Source(async (request, _) => {
                body = await request.Content!.ReadAsStringAsync();
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"success\":true,\"data\":{\"contract_version\":2,\"validated\":true}}") };
            });
            Assert.Null(await source.ValidateBindingAsync(FirmBinding(), CancellationToken.None));
            using var document = JsonDocument.Parse(body!);
            Assert.Equal(2, document.RootElement.GetProperty("contract_version").GetInt32());
            Assert.Equal(9, document.RootElement.GetProperty("expected_binding").EnumerateObject().Count());
        }

        private static ChatServiceVertexAccessTokenSource Source(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) => new(
            _ => Task.FromResult<ChatServiceConnectionSnapshot?>(new(new Uri("http://127.0.0.1:43123"), "synthetic-nonce")),
            new HttpClient(new Handler(send)), () => DateTimeOffset.FromUnixTimeSeconds(1800000000));
        private sealed class Handler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> _send;
            internal Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) { _send = send; }
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) => _send(request, ct);
        }
    }
}

