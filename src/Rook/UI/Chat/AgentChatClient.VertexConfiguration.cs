using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Vertex;

namespace Rook.UI.Chat
{
    internal sealed record VertexConfigurationStatus(bool Configured, string? Mode, string ProjectId,
        string VideoLocation, string ImageLocation, bool VideoAvailable);
    internal sealed record VertexConfigurationResult(bool Success, VertexConfigurationStatus? Status, string Message, string? Code = null);

    internal sealed record FirmSettingsSummary(string Label, string ProjectId, string VideoLocation, string ImageLocation, string WorkforcePoolUserProject, string? QuotaProjectId);
    internal sealed record FirmConfigurationStatus(FirmSettingsSummary? Active, FirmSettingsSummary? Pending, string? ActiveGeneration, string? PendingRevision, string? AuthorizationEpoch, string State, string? LegacyMode, bool RetirementPending);
    internal sealed record FirmConfigurationResult(bool Success, FirmConfigurationStatus? Status, string Message, string? Code = null);
    internal sealed record FirmSignInCheck(string State, string? Code, string? Generation, string ImageAccess, string VideoAccess, string Billing, string Quota);
    internal sealed record FirmSignInResult(bool Success, FirmSignInCheck? Check, string Message);

    public sealed partial class AgentChatClient
    {
        private static readonly HttpClient VertexConfigurationHttp = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = Timeout.InfiniteTimeSpan };
        internal Task<VertexConfigurationResult> ReadVertexConfigurationAsync(CancellationToken ct) => VertexConfigureAsync(new { operation = "status" }, false, ct);
        internal Task<VertexConfigurationResult> ConnectVertexAccountAsync(string clientConfigurationPath, string projectId, string videoLocation, CancellationToken ct)
            => VertexConfigureAsync(new { operation = "connect", client_config_path = clientConfigurationPath, project_id = projectId, video_location = videoLocation }, true, ct);
        internal Task<VertexConfigurationResult> SaveVertexMediaConfigurationAsync(string projectId, string videoLocation, CancellationToken ct)
            => VertexConfigureAsync(new { operation = "save", project_id = projectId, video_location = videoLocation }, true, ct);
        internal Task<VertexConfigurationResult> DisconnectVertexAccountAsync(CancellationToken ct) => VertexConfigureAsync(new { operation = "disconnect" }, true, ct);
        private async Task<VertexConfigurationResult> VertexConfigureAsync(object body, bool mutation, CancellationToken ct)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(TimeSpan.FromSeconds(mutation ? 210 : 30));
            try
            {
                var connection = _fixedBaseUri is not null ? null : await ChatServiceManager.Instance.AcquireOwnedConnectionAsync(deadline.Token).ConfigureAwait(false);
                var baseUri = _fixedBaseUri ?? connection?.BaseUri;
                if (baseUri is null) return new(false, null, "The owned Google configuration service is unavailable.");
                using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/internal/providers/vertex/configuration"))
                { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
                if (connection is not null) request.Headers.Add(SessionHeaderName, connection.SessionNonce);
                var http = _fixedBaseUri is not null ? _client : VertexConfigurationHttp;
                using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
                if (response.Content.Headers.ContentLength > 8192) return new(false, null, "Invalid Google configuration response.");
                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, 8192, deadline.Token).ConfigureAwait(false);
                if (bytes is null) return new(false, null,
                    "Google configuration was not completed. Refresh local status; check the client file, administrator approval and project settings.");
                using var doc = JsonDocument.Parse(bytes);
                var root = doc.RootElement;
                if (!response.IsSuccessStatusCode) {
                    if (root.TryGetProperty("data", out var committed)) {
                        ConfigurationJson.Shape(root, "success error data");
                        ConfigurationJson.Need(root.GetProperty("success").ValueKind == JsonValueKind.False);
                        ConfigurationJson.Shape(root.GetProperty("error"), "code message");
                        ConfigurationJson.Need(ConfigurationJson.Text(root.GetProperty("error").GetProperty("code")) == "vertex_restart_required");
                        var status = ParseFirmStatus(committed);
                        ConfigurationJson.Need(status.State == "unconfigured" && status.LegacyMode is null);
                        return new(false, new(false, null, "", "", "global", false),
                            "Disconnected locally. Restart required: process retirement has not been confirmed.", "vertex_restart_required");
                    }
                    return new(false, null, "Google configuration was not completed. Refresh local status; check the client file, administrator approval and project settings.");
                }
                ConfigurationJson.Shape(root, "success data");
                ConfigurationJson.Need(root.GetProperty("success").GetBoolean());
                var data = root.GetProperty("data");
                ConfigurationJson.Shape(data, "configured mode project_id video_location image_location video_available");
                var configured = data.GetProperty("configured").GetBoolean();
                var mode = data.GetProperty("mode").ValueKind == JsonValueKind.Null ? null : ConfigurationJson.Text(data.GetProperty("mode"));
                ConfigurationJson.Need(mode is null or "oauth" or "adc" or "service_account" or "workforce");
                var project = ConfigurationJson.Text(data.GetProperty("project_id"), empty: true);
                var location = ConfigurationJson.Text(data.GetProperty("video_location"), empty: true);
                var image = ConfigurationJson.Text(data.GetProperty("image_location"));
                var available = data.GetProperty("video_available").GetBoolean();
                ConfigurationJson.Need(image == "global" && available == (configured && location == "us-central1"));
                return new(true, new(configured, mode, project, location, image, available), "Google configuration updated.");
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch { return new(false, null, "Google configuration could not be read. Refresh local status before trying again."); }
        }
        internal Task<FirmConfigurationResult> ReadFirmConfigurationAsync(CancellationToken ct) => FirmConfigureAsync(new { operation = "firm_status" }, false, ct);
        internal Task<FirmConfigurationResult> ImportFirmSettingsAsync(string path, CancellationToken ct) => FirmConfigureAsync(new { operation = "import_firm", settings_path = path }, true, ct);
        internal Task<FirmConfigurationResult> DiscardPendingFirmSettingsAsync(CancellationToken ct) => FirmConfigureAsync(new { operation = "discard_firm" }, true, ct);
        internal Task<FirmConfigurationResult> ConnectFirmAccountAsync(string pendingRevision, string authorizationEpoch, CancellationToken ct) => FirmConfigureAsync(new { operation = "connect_firm", pending_revision = pendingRevision, authorization_epoch = authorizationEpoch }, true, ct);
        internal Task<FirmConfigurationResult> PrepareFirmReconnectAsync(string expectedGeneration, CancellationToken ct) => FirmConfigureAsync(new { operation = "prepare_firm_reconnect", authorization_generation = expectedGeneration }, true, ct);
        internal async Task<FirmConfigurationResult> DisconnectFirmAccountAsync(CancellationToken ct)
        {
            var result = await DisconnectVertexAccountAsync(ct).ConfigureAwait(false);
            if (result.Success) return await ReadFirmConfigurationAsync(ct).ConfigureAwait(false);
            if (result.Code == "vertex_restart_required" && result.Status?.Configured == false) {
                var current = await ReadFirmConfigurationAsync(ct).ConfigureAwait(false);
                return new(false, current.Status, result.Message, result.Code);
            }
            return new(false, null, result.Message, result.Code);
        }

        private static string? NullableText(JsonElement obj, string key) => obj.GetProperty(key).ValueKind == JsonValueKind.Null ? null : ConfigurationJson.Text(obj.GetProperty(key));
        private static bool Opaque(string? value) => value is not null && System.Text.RegularExpressions.Regex.IsMatch(value, "\\A[0-9a-f]{32}\\z");
        private static FirmSettingsSummary? FirmSummary(JsonElement data)
        {
            if (data.ValueKind == JsonValueKind.Null) return null;
            ConfigurationJson.Shape(data, "label project_id video_location image_location workforce_pool_user_project quota_project_id");
            var label = ConfigurationJson.Text(data.GetProperty("label"));
            var project = ConfigurationJson.Text(data.GetProperty("project_id"));
            var region = ConfigurationJson.Text(data.GetProperty("video_location"));
            var image = ConfigurationJson.Text(data.GetProperty("image_location"));
            var user = ConfigurationJson.Text(data.GetProperty("workforce_pool_user_project"));
            var quota = NullableText(data, "quota_project_id");
            ConfigurationJson.Need(label.Length <= 160 && VertexAuthorizationBinding.IsProject(project) && VertexAuthorizationBinding.IsUserProject(user)
                && (quota is null || VertexAuthorizationBinding.IsUserProject(quota)) && image == "global" && region.Length <= 64
                && System.Text.RegularExpressions.Regex.IsMatch(region, "\\A(?:global|[a-z][a-z0-9]*(?:-[a-z0-9]+)+)\\z"));
            return new(label, project, region, image, user, quota);
        }
        private static FirmConfigurationStatus ParseFirmStatus(JsonElement data)
        {
            ConfigurationJson.Shape(data, "contract_version active active_generation retirement_pending pending pending_revision authorization_epoch legacy_mode state");
            ConfigurationJson.Need(data.GetProperty("contract_version").GetInt32() == 2);
            var active = FirmSummary(data.GetProperty("active")); var pending = FirmSummary(data.GetProperty("pending"));
            var generation = NullableText(data, "active_generation"); var revision = NullableText(data, "pending_revision"); var epoch = NullableText(data, "authorization_epoch");
            var legacy = NullableText(data, "legacy_mode"); var state = ConfigurationJson.Text(data.GetProperty("state"));
            var retirement = data.GetProperty("retirement_pending").GetBoolean();
            ConfigurationJson.Need(active is null ? generation is null && !retirement : Opaque(generation));
            ConfigurationJson.Need(pending is null ? revision is null && epoch is null : Opaque(revision) && Opaque(epoch));
            ConfigurationJson.Need(legacy is null or "oauth" or "adc" or "service_account");
            ConfigurationJson.Need(active is null || legacy is null);
            ConfigurationJson.Need(state == (active is not null ? retirement ? "restart_required" : "signed_in" : pending is not null ? "sign_in_required" : "unconfigured"));
            return new(active, pending, generation, revision, epoch, state, legacy, retirement);
        }
        private async Task<JsonElement> SendFirmRequestAsync(object body, bool interaction, CancellationToken ct)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(TimeSpan.FromSeconds(interaction ? 210 : 30));
            var connection = _fixedBaseUri is not null ? null : await ChatServiceManager.Instance.AcquireOwnedConnectionAsync(deadline.Token).ConfigureAwait(false);
            var baseUri = _fixedBaseUri ?? connection?.BaseUri;
            if (baseUri is null || !baseUri.IsAbsoluteUri || !baseUri.IsLoopback || baseUri.Scheme != Uri.UriSchemeHttp) throw new InvalidOperationException();
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/internal/providers/vertex/configuration")) { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
            if (connection is not null) request.Headers.Add(SessionHeaderName, connection.SessionNonce);
            var http = _fixedBaseUri is not null ? _client : VertexConfigurationHttp;
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
            if (response.Content.Headers.ContentLength > 8192) throw new InvalidOperationException();
            using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
            var bytes = await CappedStreamReader.ReadCappedAsync(stream, 8192, deadline.Token).ConfigureAwait(false);
            if (bytes is null) throw new InvalidOperationException();
            using var document = JsonDocument.Parse(bytes);
            var root = document.RootElement;
            var committedFailure = !response.IsSuccessStatusCode && root.TryGetProperty("data", out _);
            ConfigurationJson.Shape(root, response.IsSuccessStatusCode ? "success data" : committedFailure ? "success error data" : "success error");
            if (!response.IsSuccessStatusCode) {
                ConfigurationJson.Need(root.GetProperty("success").ValueKind == JsonValueKind.False);
                ConfigurationJson.Shape(root.GetProperty("error"), "code message");
                var code = ConfigurationJson.Text(root.GetProperty("error").GetProperty("code"));
                FirmConfigurationStatus? committed = null;
                if (committedFailure) {
                    ConfigurationJson.Need(code == "vertex_restart_required");
                    committed = ParseFirmStatus(root.GetProperty("data"));
                    ConfigurationJson.Need(committed.Active is not null && committed.RetirementPending && committed.State == "restart_required");
                }
                throw new FirmOperationException(code, committed);
            }
            ConfigurationJson.Need(root.GetProperty("success").ValueKind == JsonValueKind.True);
            return root.GetProperty("data").Clone();
        }
        private sealed class FirmOperationException : Exception {
            internal string Code { get; }
            internal FirmConfigurationStatus? CommittedStatus { get; }
            internal FirmOperationException(string code, FirmConfigurationStatus? committed = null) {
                Code = code is "vertex_configuration_busy" or "vertex_authorization_changed" or "vertex_restart_required" or "vertex_firm_sign_in_required" or "vertex_workforce_exchange_denied" or "vertex_firm_settings_reimport_required" or "vertex_auth_dependency_missing" or "vertex_token_issuance_timeout" or "vertex_authorization_declined" ? code : "vertex_configuration_failed";
                CommittedStatus = committed;
            }
        }
        private static string FirmFailureMessage(string code) => code switch {
            "vertex_configuration_busy" => "An earlier configuration operation is still settling. Read local settings or disconnect from Rook.",
            "vertex_authorization_changed" => "Authorization or pending settings changed. Read local settings before signing in again.",
            "vertex_restart_required" => "Restart required: a previous managed process could not be retired. Read local settings and check sign-in after restarting.",
            "vertex_firm_sign_in_required" => "Sign in with your firm to renew authorization.",
            "vertex_workforce_exchange_denied" => "Google denied the firm's identity exchange. Ask your administrator to check the workforce provider and permissions.",
            "vertex_firm_settings_reimport_required" => "Reimport firm settings and sign in deliberately to change the active firm connection.",
            "vertex_auth_dependency_missing" => "The installed firm sign-in dependency is unavailable. Update the packaged Rook runtime.",
            "vertex_token_issuance_timeout" => "Sign-in checking timed out. Image/video access, billing and quota remain unverified.",
            "vertex_authorization_declined" => "Firm sign-in was cancelled or declined. Read local settings.",
            _ => "Firm configuration is unavailable. Read local settings and check the administrator-provided settings file.",
        };
        private async Task<FirmConfigurationResult> FirmConfigureAsync(object body, bool interaction, CancellationToken ct)
        {
            try { var data = await SendFirmRequestAsync(body, interaction, ct).ConfigureAwait(false); return new(true, ParseFirmStatus(data), "Local firm settings updated. Image/video access, billing and quota remain unverified."); }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (FirmOperationException error) { return new(false, error.CommittedStatus, FirmFailureMessage(error.Code), error.Code); }
            catch { return new(false, null, "Firm configuration could not be read. Read local settings before retrying."); }
        }
        internal async Task<FirmSignInResult> CheckFirmSignInAsync(string expectedGeneration, CancellationToken ct)
        {
            try {
                ConfigurationJson.Need(Opaque(expectedGeneration));
                var data = await SendFirmRequestAsync(new { operation = "check_firm_sign_in", authorization_generation = expectedGeneration }, false, ct).ConfigureAwait(false);
                ConfigurationJson.Shape(data, "contract_version check_scope state code generation image_access video_access billing quota");
                ConfigurationJson.Need(data.GetProperty("contract_version").GetInt32() == 2 && ConfigurationJson.Text(data.GetProperty("check_scope")) == "identity_exchange");
                foreach (var name in new[] { "image_access", "video_access", "billing", "quota" }) ConfigurationJson.Need(ConfigurationJson.Text(data.GetProperty(name)) == "unverified");
                var state = ConfigurationJson.Text(data.GetProperty("state")); var code = NullableText(data, "code"); var generation = NullableText(data, "generation");
                ConfigurationJson.Need(generation is null || generation == expectedGeneration);
                var valid = state switch {
                    "signed_in" => code is null && generation == expectedGeneration,
                    "sign_in_required" => code == "vertex_firm_sign_in_required",
                    "exchange_denied" => code == "vertex_workforce_exchange_denied",
                    "service_unavailable" => code is "vertex_token_issuance_timeout" or "vertex_request_failed" or "vertex_refresh_stale",
                    "authorization_changed" => code == "vertex_authorization_changed",
                    "restart_required" => code == "vertex_restart_required",
                    _ => false,
                };
                ConfigurationJson.Need(valid);
                return new(true, new(state, code, generation, "unverified", "unverified", "unverified", "unverified"), state == "signed_in"
                    ? "Sign-in and Google exchange passed. Image/video access, billing and quota remain unverified." : FirmFailureMessage(code!));
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (FirmOperationException error) { return new(false, null, FirmFailureMessage(error.Code)); }
            catch { return new(false, null, "Sign-in checking did not complete. Image/video access, billing and quota remain unverified."); }
        }
    }
}
