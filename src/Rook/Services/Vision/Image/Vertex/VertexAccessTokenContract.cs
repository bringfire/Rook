using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Image.Vertex
{
    internal sealed record VertexAuthorizationBinding(int BindingVersion, string AuthorizationGeneration, string ProjectId, string Location, string ModelId,
        string? PrincipalId = null, string? ConnectionFingerprint = null, string? WorkforcePoolUserProject = null, string? QuotaProjectId = null)
    {
        private static bool Hex(string? value, int count) => value is not null && value.Length == count && Regex.IsMatch(value, "\\A[0-9a-f]+\\z", RegexOptions.CultureInvariant);
        internal static bool IsProject(string? value) => value is not null && Regex.IsMatch(value, "\\A[a-z][a-z0-9-]{4,28}[a-z0-9]\\z", RegexOptions.CultureInvariant);
        internal static bool IsUserProject(string? value) => IsProject(value) || value is not null && Regex.IsMatch(value, "\\A[1-9][0-9]{5,31}\\z", RegexOptions.CultureInvariant);
        internal bool IsValid() => Hex(AuthorizationGeneration, 32) && IsProject(ProjectId)
            && !string.IsNullOrEmpty(Location) && Location.Length <= 64 && Regex.IsMatch(Location, "\\A[a-z0-9-]+\\z", RegexOptions.CultureInvariant)
            && !string.IsNullOrEmpty(ModelId) && ModelId.Length <= 256
            && (BindingVersion == 1 && PrincipalId is null && ConnectionFingerprint is null && WorkforcePoolUserProject is null && QuotaProjectId is null
                || BindingVersion == 2 && Hex(PrincipalId, 32) && Hex(ConnectionFingerprint, 64) && IsUserProject(WorkforcePoolUserProject) && (QuotaProjectId is null || IsUserProject(QuotaProjectId)));

        internal Dictionary<string, object?> ToWire()
        {
            if (!IsValid()) throw new ArgumentException("Invalid Vertex binding.");
            var value = new Dictionary<string, object?> {
                ["binding_version"] = BindingVersion, ["authorization_generation"] = AuthorizationGeneration,
                ["project_id"] = ProjectId, ["location"] = Location, ["model_id"] = ModelId,
            };
            if (BindingVersion == 2) {
                value["principal_id"] = PrincipalId; value["connection_fingerprint"] = ConnectionFingerprint;
                value["workforce_pool_user_project"] = WorkforcePoolUserProject; value["quota_project_id"] = QuotaProjectId;
            }
            return value;
        }
        internal IReadOnlyDictionary<string, JsonNode> ToMetadata() => new Dictionary<string, JsonNode>
        { ["vertex_binding"] = JsonNode.Parse(JsonSerializer.Serialize(ToWire()))! };
        internal static VertexAuthorizationBinding? FromMetadata(IReadOnlyDictionary<string, JsonNode> metadata)
        {
            try {
                if (!metadata.TryGetValue("vertex_binding", out var node) || node is not JsonObject obj) return null;
                var version = obj["binding_version"]!.GetValue<int>();
                var keys = new HashSet<string>(StringComparer.Ordinal) { "binding_version", "authorization_generation", "project_id", "location", "model_id" };
                if (version == 2) keys.UnionWith(new[] { "principal_id", "connection_fingerprint", "workforce_pool_user_project", "quota_project_id" });
                if (obj.Count != keys.Count) return null;
                foreach (var property in obj) if (!keys.Remove(property.Key)) return null;
                var binding = new VertexAuthorizationBinding(version, obj["authorization_generation"]!.GetValue<string>(), obj["project_id"]!.GetValue<string>(), obj["location"]!.GetValue<string>(), obj["model_id"]!.GetValue<string>(),
                    version == 2 ? obj["principal_id"]!.GetValue<string>() : null,
                    version == 2 ? obj["connection_fingerprint"]!.GetValue<string>() : null,
                    version == 2 ? obj["workforce_pool_user_project"]!.GetValue<string>() : null,
                    version == 2 ? obj["quota_project_id"]?.GetValue<string>() : null);
                return binding.IsValid() ? binding : null;
            }
            catch { return null; }
        }
    }

    internal sealed record VertexAccessTokenLease(
        string AccessToken,
        long ExpiresAtUnixSeconds,
        string ProjectId,
        string Location,
        string Generation,
        VertexAuthorizationBinding Binding,
        int ContractVersion = 1,
        string? QuotaProjectId = null)
    {
        public override string ToString() => "VertexAccessTokenLease(<redacted>)";
    }

    internal sealed record VertexAccessTokenFailure(
        string Code,
        string Message,
        bool Retryable);

    internal sealed record VertexAccessTokenResult(
        VertexAccessTokenLease? Lease,
        VertexAccessTokenFailure? Failure);

    internal interface IVertexAccessTokenSource
    {
        Task<VertexAccessTokenResult> AcquireAsync(
            string qualifiedModelKey,
            string location,
            VertexAuthorizationBinding? expectedBinding,
            CancellationToken cancellationToken);
        Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding, CancellationToken cancellationToken);
    }

    internal sealed class UnavailableVertexAccessTokenSource
        : IVertexAccessTokenSource
    {
        public static UnavailableVertexAccessTokenSource Instance { get; } = new();

        public Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding, CancellationToken cancellationToken)
        { cancellationToken.ThrowIfCancellationRequested(); return Task.FromResult<VertexAccessTokenFailure?>(new("vertex_token_service_unavailable", "The internal Vertex token service is unavailable.", true)); }

        private UnavailableVertexAccessTokenSource()
        {
        }

        public Task<VertexAccessTokenResult> AcquireAsync(
            string qualifiedModelKey,
            string location,
            VertexAuthorizationBinding? expectedBinding,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(new VertexAccessTokenResult(
                Lease: null,
                Failure: new VertexAccessTokenFailure(
                    "vertex_token_service_unavailable",
                    "The internal Vertex token service is unavailable.",
                    Retryable: true)));
        }
    }
}
