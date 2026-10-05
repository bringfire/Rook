using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;
using Rook.Services.Vision.Generation;

namespace Rook.UI.Chat
{
    internal sealed class ChatServiceVertexAccessTokenSource
        : IVertexAccessTokenSource
    {
        internal static readonly TimeSpan RouteTimeout = TimeSpan.FromSeconds(30);

        private const string RoutePath = "/internal/providers/vertex/access-token";

        private static readonly IReadOnlyDictionary<string, FailureDefinition>
            KnownFailures = new Dictionary<string, FailureDefinition>(StringComparer.Ordinal)
            {
                ["vertex_internal_access_denied"] = new(
                    HttpStatusCode.Forbidden,
                    "The internal Vertex token route is unavailable to this caller.",
                    Retryable: false),
                ["vertex_internal_method_not_allowed"] = new(
                    HttpStatusCode.MethodNotAllowed,
                    "The internal Vertex token route accepts POST requests only.",
                    Retryable: false),
                ["vertex_internal_request_invalid"] = new(
                    HttpStatusCode.BadRequest,
                    "The internal Vertex token request is invalid.",
                    Retryable: false),
                ["vertex_image_model_unsupported"] = new(
                    HttpStatusCode.BadRequest,
                    "The selected Vertex image model is unsupported.",
                    Retryable: false),
                ["vertex_model_region_unsupported"] = new(
                    HttpStatusCode.BadRequest,
                    "The selected Vertex media model location is unsupported.",
                    Retryable: false),
                ["vertex_signed_out"] = new(
                    HttpStatusCode.Conflict,
                    "Vertex AI is not configured for this Windows user.",
                    Retryable: false),
                ["vertex_authorization_revoked"] = new(
                    HttpStatusCode.Conflict,
                    "Google authorization must be renewed.",
                    Retryable: false),
                ["vertex_adc_unavailable"] = new(
                    HttpStatusCode.Conflict,
                    "Application Default Credentials are unavailable.",
                    Retryable: false),
                ["vertex_service_account_unavailable"] = new(
                    HttpStatusCode.Conflict,
                    "The selected service account is unavailable.",
                    Retryable: false),
                ["vertex_request_failed"] = new(
                    HttpStatusCode.Conflict,
                    "Vertex authorization is unavailable because its local configuration is invalid.",
                    Retryable: false),
                ["vertex_authorization_changed"] = new(
                    HttpStatusCode.Conflict,
                    "Vertex authorization changed during token issuance.",
                    Retryable: true),
                ["vertex_auth_dependency_missing"] = new(
                    HttpStatusCode.ServiceUnavailable,
                    "The installed Google authorization dependency is unavailable.",
                    Retryable: false),
                ["vertex_token_issuance_timeout"] = new(
                    HttpStatusCode.GatewayTimeout,
                    "Vertex token issuance timed out.",
                    Retryable: true),
                ["vertex_token_issuance_failed"] = new(
                    HttpStatusCode.InternalServerError,
                    "Vertex token issuance failed.",
                    Retryable: true),
            };

        private static readonly Lazy<ChatServiceVertexAccessTokenSource> LazyInstance =
            new(() => new ChatServiceVertexAccessTokenSource(
                ChatServiceManager.Instance.AcquireOwnedConnectionAsync,
                new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }),
                () => DateTimeOffset.UtcNow));

        private readonly Func<CancellationToken, Task<ChatServiceConnectionSnapshot?>>
            _acquireConnection;
        private readonly HttpClient _httpClient;
        private readonly Func<DateTimeOffset> _utcNow;
        private readonly TimeSpan _routeTimeout;

        internal ChatServiceVertexAccessTokenSource(
            Func<CancellationToken, Task<ChatServiceConnectionSnapshot?>> acquireConnection,
            HttpClient httpClient,
            Func<DateTimeOffset> utcNow)
            : this(acquireConnection, httpClient, utcNow, RouteTimeout)
        {
        }

        internal ChatServiceVertexAccessTokenSource(
            Func<CancellationToken, Task<ChatServiceConnectionSnapshot?>> acquireConnection,
            HttpClient httpClient,
            Func<DateTimeOffset> utcNow,
            TimeSpan routeTimeout)
        {
            _acquireConnection = acquireConnection
                ?? throw new ArgumentNullException(nameof(acquireConnection));
            _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
            _utcNow = utcNow ?? throw new ArgumentNullException(nameof(utcNow));
            if (routeTimeout <= TimeSpan.Zero)
                throw new ArgumentOutOfRangeException(nameof(routeTimeout));
            _routeTimeout = routeTimeout;

            // The linked cancellation source below is the sole route ceiling.
            // Disable a shorter injected HttpClient timeout so it cannot preempt it.
            _httpClient.Timeout = Timeout.InfiniteTimeSpan;
        }

        public static ChatServiceVertexAccessTokenSource Instance => LazyInstance.Value;

        public async Task<VertexAccessTokenResult> AcquireAsync(
            string qualifiedModelKey,
            string location,
            VertexAuthorizationBinding? expectedBinding,
            CancellationToken cancellationToken)
        {
            return await SendAsync(qualifiedModelKey, location, expectedBinding, false, cancellationToken).ConfigureAwait(false);
        }

        public async Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding, CancellationToken cancellationToken)
        {
            return (await SendAsync(binding.ModelId, binding.Location, binding, true, cancellationToken).ConfigureAwait(false)).Failure;
        }

        private async Task<VertexAccessTokenResult> SendAsync(string qualifiedModelKey, string location, VertexAuthorizationBinding? expectedBinding, bool validateOnly, CancellationToken cancellationToken)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            deadline.CancelAfter(_routeTimeout);
            cancellationToken.ThrowIfCancellationRequested();

            ChatServiceConnectionSnapshot? snapshot;
            try
            {
                snapshot = await _acquireConnection(deadline.Token)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (OperationCanceledException) when (deadline.IsCancellationRequested) { return IssuanceTimeout(); }
            catch
            {
                return ServiceUnavailable();
            }

            if (snapshot is null
                || !IsAllowedServiceUri(snapshot.BaseUri)
                || string.IsNullOrWhiteSpace(snapshot.SessionNonce))
            {
                return ServiceUnavailable();
            }

            using var request = new HttpRequestMessage(
                HttpMethod.Post,
                new Uri(snapshot.BaseUri, RoutePath));
            request.Headers.TryAddWithoutValidation(
                "X-Rook-Session",
                snapshot.SessionNonce);
            request.Content = new StringContent(
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["operation"] = validateOnly ? "validate" : "acquire",
                    ["model"] = qualifiedModelKey,
                    ["location"] = location,
                    ["expected_binding"] = expectedBinding?.ToWire(),
                }),
                Encoding.UTF8,
                "application/json");


            try
            {
                using var response = await _httpClient.SendAsync(
                    request,
                    HttpCompletionOption.ResponseHeadersRead,
                    deadline.Token).ConfigureAwait(false);
                if (response.Content.Headers.ContentLength > 65536) return InvalidResponse();
                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, 65536, deadline.Token).ConfigureAwait(false);
                if (bytes is null) return InvalidResponse();
                var json = Encoding.UTF8.GetString(bytes);
                if (validateOnly && response.IsSuccessStatusCode)
                {
                    using var doc = JsonDocument.Parse(json);
                    var root = doc.RootElement;
                    if (!HasExactProperties(root, "success", "data") || root.GetProperty("success").ValueKind != JsonValueKind.True || !HasExactProperties(root.GetProperty("data"), "validated") || root.GetProperty("data").GetProperty("validated").ValueKind != JsonValueKind.True) return InvalidResponse();
                    return new(null, null);
                }
                var result = ParseResponse(response.StatusCode, json);
                if (result.Lease is not null && (result.Lease.Binding.ModelId != qualifiedModelKey || result.Lease.Location != location || (expectedBinding is not null && result.Lease.Binding != expectedBinding)))
                    return Failure("vertex_authorization_changed", "Vertex authorization changed during token issuance.", false);
                return result;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (OperationCanceledException) when (deadline.IsCancellationRequested)
            {
                return IssuanceTimeout();
            }
            catch (OperationCanceledException)
            {
                return ServiceUnavailable();
            }
            catch
            {
                return ServiceUnavailable();
            }
        }

        private VertexAccessTokenResult ParseResponse(
            HttpStatusCode statusCode,
            string json)
        {
            try
            {
                using var document = JsonDocument.Parse(json);
                var root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object
                    || !HasExactProperties(
                        root,
                        "success",
                        IsSuccessStatusCode(statusCode) ? "data" : "error")
                    || !root.TryGetProperty("success", out var success)
                    || (success.ValueKind != JsonValueKind.True
                        && success.ValueKind != JsonValueKind.False))
                {
                    return InvalidResponse();
                }

                return success.GetBoolean()
                    ? ParseSuccess(statusCode, root)
                    : ParseFailure(statusCode, root);
            }
            catch (JsonException)
            {
                return InvalidResponse();
            }
        }

        private VertexAccessTokenResult ParseSuccess(
            HttpStatusCode statusCode,
            JsonElement root)
        {
            if (!IsSuccessStatusCode(statusCode)
                || !root.TryGetProperty("data", out var data)
                || data.ValueKind != JsonValueKind.Object
                || !HasExactProperties(
                    data,
                    "access_token",
                    "expires_at_unix_seconds",
                    "project_id",
                    "location",
                    "generation",
                    "binding")
                || !TryGetRequiredString(data, "access_token", out var accessToken)
                || !data.TryGetProperty("expires_at_unix_seconds", out var expiryElement)
                || !expiryElement.TryGetInt64(out var expiry)
                || expiry <= _utcNow().ToUnixTimeSeconds()
                || !TryGetRequiredString(data, "project_id", out var projectId)
                || !TryGetRequiredString(data, "location", out var location)
                || !TryGetRequiredString(data, "generation", out var generation)
                || !IsGeneration(generation))
            {
                return InvalidResponse();
            }

            var bindingMetadata = new Dictionary<string, System.Text.Json.Nodes.JsonNode> { ["vertex_binding"] = System.Text.Json.Nodes.JsonNode.Parse(data.GetProperty("binding").GetRawText())! };
            var binding = VertexAuthorizationBinding.FromMetadata(bindingMetadata);
            if (binding is null || binding.AuthorizationGeneration != generation || binding.ProjectId != projectId || binding.Location != location) return InvalidResponse();

            return new VertexAccessTokenResult(
                new VertexAccessTokenLease(
                    accessToken,
                    expiry,
                    projectId,
                    location,
                    generation, binding),
                Failure: null);
        }

        private static VertexAccessTokenResult ParseFailure(
            HttpStatusCode statusCode,
            JsonElement root)
        {
            if (IsSuccessStatusCode(statusCode)
                || !root.TryGetProperty("error", out var error)
                || error.ValueKind != JsonValueKind.Object
                || !HasExactProperties(error, "code", "message")
                || !TryGetRequiredString(error, "code", out var code)
                || !TryGetRequiredString(error, "message", out _)
                || !KnownFailures.TryGetValue(code, out var definition)
                || definition.StatusCode != statusCode)
            {
                return InvalidResponse();
            }

            return Failure(code, definition.Message, definition.Retryable);
        }

        private static bool HasExactProperties(
            JsonElement element,
            params string[] expected)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
                seen.Add(property.Name);
            return seen.SetEquals(expected);
        }

        private static bool TryGetRequiredString(
            JsonElement element,
            string propertyName,
            out string value)
        {
            value = "";
            if (!element.TryGetProperty(propertyName, out var property)
                || property.ValueKind != JsonValueKind.String)
            {
                return false;
            }
            value = property.GetString() ?? "";
            return value.Length > 0;
        }

        private static bool IsGeneration(string value)
        {
            if (value.Length != 32)
                return false;
            foreach (var c in value)
            {
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
                    return false;
            }
            return true;
        }

        private static bool IsAllowedServiceUri(Uri baseUri) =>
            baseUri is not null
            && baseUri.IsAbsoluteUri
            && string.Equals(
                baseUri.Scheme,
                Uri.UriSchemeHttp,
                StringComparison.OrdinalIgnoreCase)
            && baseUri.IsLoopback;

        private static bool IsSuccessStatusCode(HttpStatusCode statusCode) =>
            (int)statusCode >= 200 && (int)statusCode <= 299;

        private static VertexAccessTokenResult ServiceUnavailable() =>
            Failure(
                "vertex_token_service_unavailable",
                "The internal Vertex token service is unavailable.",
                retryable: true);

        private static VertexAccessTokenResult InvalidResponse() =>
            Failure(
                "vertex_token_response_invalid",
                "The internal Vertex token response is invalid.",
                retryable: true);

        private static VertexAccessTokenResult IssuanceTimeout() =>
            Failure(
                "vertex_token_issuance_timeout",
                "Vertex token issuance timed out.",
                retryable: true);

        private static VertexAccessTokenResult Failure(
            string code,
            string message,
            bool retryable) =>
            new(
                Lease: null,
                Failure: new VertexAccessTokenFailure(code, message, retryable));

        private sealed record FailureDefinition(
            HttpStatusCode StatusCode,
            string Message,
            bool Retryable);
    }
}
