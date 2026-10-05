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
        [Fact]
        public void OriginalBinding_IsCopiedIntoHandleAndEnvelope()
        {
            var binding = new JsonObject { ["authorization_generation"] = "original" };
            var metadata = new Dictionary<string,JsonNode> { ["vertex_binding"] = binding };
            var handle = new ProviderJobHandle("original-operation",providerMetadata:metadata);
            var envelope = new ProviderResultEnvelope(new[] {new ResultArtifact("video",new InlineArtifactBody(new byte[]{1}),"video/mp4",metadata)},metadata);
            binding["authorization_generation"] = "replacement";
            Assert.Equal("original",handle.ProviderMetadata!["vertex_binding"]["authorization_generation"]!.GetValue<string>());
            Assert.Equal("original",envelope.EnvelopeMetadata["vertex_binding"]["authorization_generation"]!.GetValue<string>());
        }
    }
}
