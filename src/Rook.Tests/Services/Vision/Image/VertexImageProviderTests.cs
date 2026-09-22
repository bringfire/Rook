using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public sealed class VertexImageProviderTests
    {
        [Fact]
        public async Task UnavailableTokenSource_ReturnsFixedFailureWithoutThrowing()
        {
            var result = await UnavailableVertexAccessTokenSource.Instance.AcquireAsync(
                "vertex_ai/gemini-3.1-flash-image",
                CancellationToken.None);

            Assert.Null(result.Lease);
            Assert.NotNull(result.Failure);
            Assert.Equal("vertex_token_service_unavailable", result.Failure!.Code);
            Assert.Equal(
                "The internal Vertex token service is unavailable.",
                result.Failure.Message);
            Assert.True(result.Failure.Retryable);
        }

        [Fact]
        public void AccessTokenLease_ToStringRedactsBearerToken()
        {
            var lease = new VertexAccessTokenLease(
                "secret-token-sentinel",
                1_900_000_000,
                "company-project",
                "global",
                "0123456789abcdef0123456789abcdef");

            Assert.Equal("VertexAccessTokenLease(<redacted>)", lease.ToString());
            Assert.DoesNotContain("secret-token-sentinel", lease.ToString());
        }
    }
}
