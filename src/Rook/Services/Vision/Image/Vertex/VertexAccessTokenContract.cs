using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Image.Vertex
{
    internal sealed record VertexAuthorizationBinding(int BindingVersion, string AuthorizationGeneration, string ProjectId, string Location, string ModelId)
    {
        internal Dictionary<string, object> ToWire() => new()
        {
            ["binding_version"] = BindingVersion, ["authorization_generation"] = AuthorizationGeneration,
            ["project_id"] = ProjectId, ["location"] = Location, ["model_id"] = ModelId,
        };
        internal IReadOnlyDictionary<string, JsonNode> ToMetadata() => new Dictionary<string, JsonNode>
        { ["vertex_binding"] = JsonNode.Parse(JsonSerializer.Serialize(ToWire()))! };
        internal static VertexAuthorizationBinding? FromMetadata(IReadOnlyDictionary<string, JsonNode> metadata)
        {
            try
            {
                if (!metadata.TryGetValue("vertex_binding", out var node) || node is not JsonObject obj || obj.Count != 5) return null;
                var binding = new VertexAuthorizationBinding(obj["binding_version"]!.GetValue<int>(), obj["authorization_generation"]!.GetValue<string>(), obj["project_id"]!.GetValue<string>(), obj["location"]!.GetValue<string>(), obj["model_id"]!.GetValue<string>());
                return binding.BindingVersion == 1 && !string.IsNullOrEmpty(binding.AuthorizationGeneration) && !string.IsNullOrEmpty(binding.ProjectId) ? binding : null;
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
        VertexAuthorizationBinding Binding)
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
