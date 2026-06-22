using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Reconstruction
{
    /// <summary>
    /// Managed adapter over the native reconstruction import route. The native
    /// importer stays authoritative; this only loops a request back to it so the
    /// in-process WebView tab (Pattern A, no network) can trigger an import.
    /// </summary>
    public interface IReconstructionImportClient
    {
        Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken);
    }

    /// <summary>
    /// Either the unwrapped native <c>data</c> object (success) or a structured failure.
    /// The native route returns its own <c>{success,data}</c> envelope; the client unwraps
    /// it once so callers see <c>asset_role</c>/<c>imported_ids</c> at the top level.
    /// </summary>
    public sealed record NativeImportOutcome(JsonObject? Data, ReconstructionFailure? Failure)
    {
        public bool Success => Failure is null;

        public static NativeImportOutcome Ok(JsonObject data) => new(data, null);
        public static NativeImportOutcome Fail(ReconstructionFailure failure) => new(null, failure);
    }

    /// <summary>
    /// Loopback adapter to the native <c>/reconstruction/2d-to-3d/import</c> route. Discovers
    /// this Rhino's native endpoint (loopback-only, see <see cref="NativeEndpointResolver"/>),
    /// POSTs only <c>{package_id}</c> to the fixed route, and unwraps the native
    /// <c>{success,data}</c> envelope ONCE. The native importer stays authoritative.
    /// </summary>
    public sealed class NativeReconstructionImportClient : IReconstructionImportClient
    {
        private const string ImportPath = "/reconstruction/2d-to-3d/import";

        private readonly HttpClient _http;
        private readonly INativeEndpointResolver _resolver;

        public NativeReconstructionImportClient(HttpClient http, INativeEndpointResolver resolver)
        {
            _http = http ?? throw new ArgumentNullException(nameof(http));
            _resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
        }

        public async Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken)
        {
            var port = _resolver.ResolveNativePort();
            if (port is not > 0)
                return NativeImportOutcome.Fail(Failure("native_unavailable",
                    "The Rook native plugin endpoint could not be found for this Rhino instance."));

            // Always the fixed loopback route; the resolver guarantees a local endpoint, so the
            // host is hardcoded 127.0.0.1 and only the discovered port varies. No arbitrary URL.
            var url = $"http://127.0.0.1:{port}{ImportPath}";
            var requestBody = new JsonObject { ["package_id"] = packageId.ToString("D") }.ToJsonString();

            HttpResponseMessage response;
            try
            {
                using var content = new StringContent(requestBody, System.Text.Encoding.UTF8, "application/json");
                response = await _http.PostAsync(url, content, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex) when ((ex is HttpRequestException or TaskCanceledException) && !cancellationToken.IsCancellationRequested)
            {
                return NativeImportOutcome.Fail(Failure("native_unavailable",
                    "The Rook native plugin import endpoint did not respond."));
            }

            string payload;
            using (response)
                payload = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            JsonObject? envelope;
            try { envelope = JsonNode.Parse(payload) as JsonObject; }
            catch (JsonException) { envelope = null; }
            if (envelope is null)
                return NativeImportOutcome.Fail(Failure("import_failed", "Native import returned an unreadable response."));

            var success = envelope.TryGetPropertyValue("success", out var s)
                && s is JsonValue sv && sv.TryGetValue<bool>(out var b) && b;
            var data = envelope.TryGetPropertyValue("data", out var d) ? d as JsonObject : null;

            // One unwrap: return the inner data so callers see asset_role/imported_ids at the top.
            if (success && data is not null)
                return NativeImportOutcome.Ok((JsonObject)data.DeepClone());

            var code = ReadString(data, "code") ?? "import_failed";
            var message = ReadString(data, "message") ?? "Native reconstruction import failed.";
            return NativeImportOutcome.Fail(Failure(code, message));
        }

        private static string? ReadString(JsonObject? obj, string key)
            => obj is not null && obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var str)
                ? str
                : null;

        private static ReconstructionFailure Failure(string code, string message)
            => new(code, message, Retryable: code == "native_unavailable", Field: null,
                   new Dictionary<string, object?>());
    }
}
