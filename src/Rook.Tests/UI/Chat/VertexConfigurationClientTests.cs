using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class VertexConfigurationClientTests
    {
        [Theory]
        [InlineData("success")]
        [InlineData("unavailable")]
        [InlineData("malformed")]
        [InlineData("cancelled")]
        public async Task FailedRetirementAfterDisconnectStillReturnsCommittedDeletion(string reconciliation)
        {
            using var cancellation = new CancellationTokenSource();
            var data = new { contract_version = 2, active = (object?)null, active_generation = (string?)null,
                retirement_pending = false, pending = (object?)null, pending_revision = (string?)null,
                authorization_epoch = (string?)null, legacy_mode = (string?)null, state = "unconfigured" };
            var handler = new VertexTestHandler(async (request, _) => {
                var operation = JsonDocument.Parse(await request.Content!.ReadAsStringAsync()).RootElement.GetProperty("operation").GetString();
                if (operation != "disconnect" && reconciliation == "cancelled") {
                    cancellation.Cancel(); throw new OperationCanceledException(cancellation.Token);
                }
                if (operation != "disconnect" && reconciliation != "success")
                    return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) { Content = new StringContent(reconciliation == "malformed" ? "invalid" : "{}") };
                return new HttpResponseMessage(operation == "disconnect" ? HttpStatusCode.Conflict : HttpStatusCode.OK) {
                    Content = new StringContent(operation == "disconnect"
                        ? JsonSerializer.Serialize(new { success = false, error = new { code = "vertex_restart_required", message = "private-sentinel" }, data })
                        : JsonSerializer.Serialize(new { success = true, data })) };
            });
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).DisconnectFirmAccountAsync(cancellation.Token);
            Assert.False(result.Success); Assert.NotNull(result.Status); Assert.Null(result.Status!.Active); Assert.Null(result.Status.Pending);
            Assert.Equal("vertex_restart_required", result.Code); Assert.DoesNotContain("private-sentinel", result.Message);
        }
        internal static object RetirementStatus(bool committed) => new {
            contract_version = 2,
            active = committed ? SyntheticSummary : null, active_generation = committed ? new string('c', 32) : null,
            retirement_pending = committed, pending = committed ? null : SyntheticSummary,
            pending_revision = committed ? null : new string('a', 32), authorization_epoch = committed ? null : new string('b', 32),
            legacy_mode = committed ? null : "adc", state = committed ? "restart_required" : "sign_in_required",
        };
        private static readonly object SyntheticSummary = new { label = "Synthetic firm", project_id = "synthetic-firm-project", video_location = "us-central1", image_location = "global", workforce_pool_user_project = "synthetic-firm-project", quota_project_id = (string?)null };

        [Fact]
        public async Task FailedCommittedActivationRetainsClosedStatusAndNewGeneration()
        {
            var handler = new VertexTestHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Conflict) {
                Content = new StringContent(JsonSerializer.Serialize(new { success = false, error = new { code = "vertex_restart_required", message = "private-sentinel" }, data = RetirementStatus(true) })) }));
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).ConnectFirmAccountAsync(new string('a',32), new string('b',32), CancellationToken.None);
            Assert.False(result.Success); Assert.NotNull(result.Status); Assert.Equal(new string('c',32),result.Status!.ActiveGeneration);
            Assert.Null(result.Status.Pending); Assert.Null(result.Status.LegacyMode); Assert.True(result.Status.RetirementPending);
            Assert.Equal("vertex_restart_required",result.Code); Assert.DoesNotContain("private-sentinel",result.Message);
        }

        [Fact]
        public async Task PendingFirmSettings_AreDistinctFromConnectedAccount()
        {
            var summary = new { label = "Synthetic firm", project_id = "synthetic-firm-project", video_location = "us-central1", image_location = "global", workforce_pool_user_project = "synthetic-firm-project", quota_project_id = (string?)null };
            var handler = new VertexTestHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
                Content = new StringContent(JsonSerializer.Serialize(new { success = true, data = new {
                    contract_version = 2, active = (object?)null, active_generation = (string?)null, retirement_pending = false,
                    pending = summary, pending_revision = new string('a', 32), authorization_epoch = new string('b', 32), legacy_mode = "oauth", state = "sign_in_required",
                }})) }));
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).ReadFirmConfigurationAsync(CancellationToken.None);
            Assert.True(result.Success); Assert.Null(result.Status!.Active); Assert.NotNull(result.Status.Pending);
            Assert.Equal("oauth", result.Status.LegacyMode); Assert.Equal("sign_in_required", result.Status.State);
        }

        [Theory]
        [InlineData("generation_ready", "unverified", "identity_exchange", null)]
        [InlineData("signed_in", "verified", "identity_exchange", null)]
        [InlineData("signed_in", "unverified", "model_readiness", null)]
        [InlineData("signed_in", "unverified", "identity_exchange", "vertex_request_failed")]
        public async Task SignInCheck_RejectsReadyOrVerifiedClaims(string state, string imageAccess, string scope, string? code)
        {
            var handler = new VertexTestHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { success = true, data = new {
                contract_version = 2, check_scope = scope, state, code, generation = new string('a', 32), image_access = imageAccess, video_access = "unverified", billing = "unverified", quota = "unverified",
            }})) }));
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).CheckFirmSignInAsync(new string('a', 32), CancellationToken.None);
            Assert.False(result.Success); Assert.Null(result.Check);
        }

        [Theory]
        [InlineData("signed_in", null)]
        [InlineData("sign_in_required", "vertex_firm_sign_in_required")]
        [InlineData("exchange_denied", "vertex_workforce_exchange_denied")]
        [InlineData("service_unavailable", "vertex_token_issuance_timeout")]
        [InlineData("authorization_changed", "vertex_authorization_changed")]
        [InlineData("restart_required", "vertex_restart_required")]
        public async Task SignInCheck_MapsClosedFailureStates(string state, string? code)
        {
            var handler = new VertexTestHandler(async (request, _) => {
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
                Assert.Equal("check_firm_sign_in", body.RootElement.GetProperty("operation").GetString());
                Assert.Equal(new string('a', 32), body.RootElement.GetProperty("authorization_generation").GetString());
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { success = true, data = new {
                    contract_version = 2, check_scope = "identity_exchange", state, code, generation = new string('a', 32), image_access = "unverified", video_access = "unverified", billing = "unverified", quota = "unverified",
                }})) };
            });
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).CheckFirmSignInAsync(new string('a', 32), CancellationToken.None);
            Assert.True(result.Success); Assert.Equal(state, result.Check!.State);
            Assert.DoesNotContain("Generation ready", result.Message);
        }

        [Fact]
        public async Task FirmConnect_UsesDisplayedRevision()
        {
            var handler = new VertexTestHandler(async (request, _) => {
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync());
                Assert.Equal("connect_firm", body.RootElement.GetProperty("operation").GetString());
                Assert.Equal(new string('a', 32), body.RootElement.GetProperty("pending_revision").GetString());
                Assert.Equal(new string('b', 32), body.RootElement.GetProperty("authorization_epoch").GetString());
                return new HttpResponseMessage(HttpStatusCode.Conflict) { Content = new StringContent("{\"success\":false,\"error\":{\"code\":\"vertex_authorization_changed\",\"message\":\"private-sentinel\"}}") };
            });
            var result = await AgentChatClient.ForTests(handler, new Uri("http://127.0.0.1:1")).ConnectFirmAccountAsync(new string('a', 32), new string('b', 32), CancellationToken.None);
            Assert.False(result.Success); Assert.DoesNotContain("private-sentinel", result.Message);
        }
        [Fact]
        public async Task LocalStatusUsesOwnedVertexRouteAndPreservesUnsupportedRegion()
        {
            var handler=new VertexTestHandler((request,_)=>
            {
                Assert.Equal("/internal/providers/vertex/configuration",request.RequestUri!.AbsolutePath);
                Assert.Equal(HttpMethod.Post,request.Method);
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(
                    "{\"success\":true,\"data\":{\"configured\":true,\"mode\":\"adc\",\"project_id\":\"company-project\",\"video_location\":\"europe-west4\",\"image_location\":\"global\",\"video_available\":false}}",Encoding.UTF8,"application/json")});
            });
            var client=AgentChatClient.ForTests(handler,new Uri("http://127.0.0.1:1"));
            client.SetSessionNonce("owned-nonce");
            var result=await client.ReadVertexConfigurationAsync(CancellationToken.None);
            Assert.True(result.Success); Assert.Equal("europe-west4",result.Status!.VideoLocation); Assert.False(result.Status.VideoAvailable);
            Assert.Equal(1,handler.Calls);
        }
        [Theory]
        [InlineData(302)] [InlineData(500)] [InlineData(200)]
        public async Task UnexpectedResponseNeverLeaksUpstreamText(int status)
        {
            var handler=new VertexTestHandler((_,_)=>Task.FromResult(new HttpResponseMessage((HttpStatusCode)status)
                {Content=new StringContent("{\"secret\":\"secret-sentinel\"}")}));
            var result=await AgentChatClient.ForTests(handler,new Uri("http://127.0.0.1:1")).ReadVertexConfigurationAsync(CancellationToken.None);
            Assert.False(result.Success); Assert.DoesNotContain("secret-sentinel",result.Message);
        }
    }
}
