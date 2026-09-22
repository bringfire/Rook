using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Image.Vertex
{
    internal sealed record VertexAccessTokenLease(
        string AccessToken,
        long ExpiresAtUnixSeconds,
        string ProjectId,
        string Location,
        string Generation)
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
            CancellationToken cancellationToken);
    }

    internal sealed class UnavailableVertexAccessTokenSource
        : IVertexAccessTokenSource
    {
        public static UnavailableVertexAccessTokenSource Instance { get; } = new();

        private UnavailableVertexAccessTokenSource()
        {
        }

        public Task<VertexAccessTokenResult> AcquireAsync(
            string qualifiedModelKey,
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
