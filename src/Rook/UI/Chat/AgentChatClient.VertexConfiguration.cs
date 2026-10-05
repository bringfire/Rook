using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.UI.Chat
{
    internal sealed record VertexConfigurationStatus(bool Configured, string? Mode, string ProjectId,
        string VideoLocation, string ImageLocation, bool VideoAvailable);
    internal sealed record VertexConfigurationResult(bool Success, VertexConfigurationStatus? Status, string Message);

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
                if (!response.IsSuccessStatusCode || bytes is null) return new(false, null,
                    "Google configuration was not completed. Refresh local status; check the client file, administrator approval and project settings.");
                using var doc = JsonDocument.Parse(bytes);
                var root = doc.RootElement;
                ConfigurationJson.Shape(root, "success data");
                ConfigurationJson.Need(root.GetProperty("success").GetBoolean());
                var data = root.GetProperty("data");
                ConfigurationJson.Shape(data, "configured mode project_id video_location image_location video_available");
                var configured = data.GetProperty("configured").GetBoolean();
                var mode = data.GetProperty("mode").ValueKind == JsonValueKind.Null ? null : ConfigurationJson.Text(data.GetProperty("mode"));
                ConfigurationJson.Need(mode is null or "oauth" or "adc" or "service_account");
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
    }
}
