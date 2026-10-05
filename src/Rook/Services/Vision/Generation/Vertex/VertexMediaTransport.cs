using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;

namespace Rook.Services.Vision.Generation.Vertex
{
    internal sealed record VertexHttpResult(byte[]? Body, GenerationError? Error, bool RetryableRead = false);

    /// <summary>Bounded transport shared by explicit Vertex media providers. Submission is always one attempt.</summary>
    internal sealed class VertexMediaTransport
    {
        internal static readonly TimeSpan OperationTimeout = TimeSpan.FromSeconds(120);
        internal const int SmallResponseLimit = 1024 * 1024;
        private readonly HttpClient _http;
        internal VertexMediaTransport(HttpClient? http = null)
        {
            _http = http ?? new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });
            _http.Timeout = Timeout.InfiniteTimeSpan;
        }

        internal static bool ValidBinding(VertexAuthorizationBinding binding) =>
            binding.BindingVersion == 1
            && Regex.IsMatch(binding.AuthorizationGeneration ?? "", "^[a-f0-9]{32}$")
            && Regex.IsMatch(binding.ProjectId ?? "", "^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
            && ((binding.ModelId == "vertex_ai/gemini-3.1-flash-image" && binding.Location == "global")
                || (binding.ModelId == "vertex_ai/veo-3.1-fast-generate-001" && binding.Location == "us-central1"));

        internal static string ModelPath(VertexAuthorizationBinding binding) =>
            $"projects/{binding.ProjectId}/locations/{binding.Location}/publishers/google/models/{binding.ModelId.Substring(10)}";

        internal static string Endpoint(VertexAuthorizationBinding binding, string action) =>
            $"https://{(binding.Location == "global" ? "aiplatform.googleapis.com" : binding.Location + "-aiplatform.googleapis.com")}/v1/{ModelPath(binding)}:{action}";

        internal async Task<VertexHttpResult> PostAsync(VertexAuthorizationBinding binding, string accessToken,
            string action, string body, long responseLimit, bool submission, CancellationToken ct)
        {
            if (!ValidBinding(binding)) return new(null, Interrupted());
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(OperationTimeout);
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, Endpoint(binding, action))
                { Content = new StringContent(body, Encoding.UTF8, "application/json") };
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
                using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token).ConfigureAwait(false);
                var status = (int)response.StatusCode;
                var limit = response.IsSuccessStatusCode ? responseLimit : SmallResponseLimit;
                if (response.Content.Headers.ContentLength > limit)
                    return new(null, submission ? UnknownSubmission() : InvalidOutput());
                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, limit, deadline.Token).ConfigureAwait(false);
                if (bytes is null) return new(null, submission ? UnknownSubmission() : InvalidOutput());
                if (response.IsSuccessStatusCode) return new(bytes, null);
                if (submission && (status >= 500 || status >= 300 && status < 400)) return new(null, UnknownSubmission());
                var code = status == 429 ? GenerationErrorCode.QuotaExceeded : status == 400 ? GenerationErrorCode.InvalidRequest : GenerationErrorCode.DependencyUnavailable;
                return new(null, new GenerationError(code, status == 429 ? "Google media quota is unavailable." : "Google media request was refused.", false,
                    ProviderErrorCode: status == 401 || status == 403 ? "vertex_authorization_required" : status == 429 ? "vertex_quota_unavailable" : "vertex_request_refused"), status == 429 || status >= 500);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch
            {
                return new(null, submission ? UnknownSubmission() : new GenerationError(GenerationErrorCode.DependencyUnavailable, "Google media operation could not be read.", true), !submission);
            }
        }

        internal static GenerationError UnknownSubmission() => new(GenerationErrorCode.ExecutionFailed,
            "Google submission outcome is unknown. Do not retry automatically; a new request may create another billed generation.", false, ProviderErrorCode: "vertex_submission_unknown");
        internal static GenerationError InvalidOutput() => new(GenerationErrorCode.ExecutionFailed, "Google media output is invalid or exceeds the allowed size.", false, ProviderErrorCode: "vertex_output_invalid");
        internal static GenerationError Interrupted() => new(GenerationErrorCode.Interrupted, "The original Google authorization or project is no longer available. This job will not resume.", false, ProviderErrorCode: "vertex_authorization_changed");
        internal static GenerationError TokenFailure(VertexAccessTokenFailure? failure, bool bound) =>
            bound || failure?.Code == "vertex_authorization_changed" ? Interrupted() : new(GenerationErrorCode.DependencyUnavailable, "Google media authorization is unavailable. Check the Google account configuration.", false, ProviderErrorCode: "vertex_authorization_required");

        internal static bool ValidLease(VertexAccessTokenLease lease, string model, string location, VertexAuthorizationBinding? expected = null) =>
            ValidBinding(lease.Binding) && lease.Binding.ModelId == model && lease.Binding.Location == location
            && lease.Binding.AuthorizationGeneration == lease.Generation && lease.Binding.ProjectId == lease.ProjectId
            && lease.Binding.Location == lease.Location && lease.ExpiresAtUnixSeconds > DateTimeOffset.UtcNow.ToUnixTimeSeconds()
            && !string.IsNullOrEmpty(lease.AccessToken) && (expected is null || expected == lease.Binding);

        internal static async Task<GenerationError?> ValidatePublicationAsync(IVertexAccessTokenSource source, IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken ct)
        {
            var binding = VertexAuthorizationBinding.FromMetadata(metadata);
            if (binding is null || !ValidBinding(binding)) return Interrupted();
            var failure = await source.ValidateBindingAsync(binding, ct).ConfigureAwait(false);
            return failure is null ? null : Interrupted();
        }

        // Validate raw encoded length/padding before allocation. Keep Base64 out of UTF-16 strings.
        internal static bool ValidateEncodedFields(byte[] json, string propertyName, int decodedLimit)
        {
            var reader = new Utf8JsonReader(json);
            while (reader.Read())
            {
                if (reader.TokenType != JsonTokenType.PropertyName || !reader.ValueTextEquals(propertyName)) continue;
                if (!reader.Read() || reader.TokenType != JsonTokenType.String || reader.ValueIsEscaped) return false;
                var value = reader.ValueSpan;
                if (value.Length == 0 || value.Length % 4 != 0 || value.Length > 4L * ((decodedLimit + 2L) / 3)) return false;
                var padding = value[value.Length - 1] == '=' ? value[value.Length - 2] == '=' ? 2 : 1 : 0;
                if (value.Length / 4L * 3 - padding > decodedLimit) return false;
                for (var i = 0; i < value.Length - padding; i++)
                {
                    var c = value[i];
                    if (!(c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '+' || c == '/')) return false;
                }
            }
            return true;
        }
    }
}
