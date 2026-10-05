using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public sealed class GenerationPublicationGuardContractTests
    {
        private sealed class Guard : IGenerationPublicationGuard
        {
            public Task<GenerationError?> ValidatePublicationAsync(IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken cancellationToken)
            { cancellationToken.ThrowIfCancellationRequested(); return Task.FromResult<GenerationError?>(null); }
        }
        [Fact]
        public async Task PublicationGuard_HasMetadataAndCancellationContract()
        {
            IGenerationPublicationGuard guard = new Guard();
            Assert.Null(await guard.ValidatePublicationAsync(new Dictionary<string, JsonNode>(), CancellationToken.None));
            await Assert.ThrowsAnyAsync<System.OperationCanceledException>(() => guard.ValidatePublicationAsync(new Dictionary<string, JsonNode>(), new CancellationToken(true)));
        }
    }
}
