using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Generation
{
    public interface IGenerationPublicationGuard
    {
        Task<GenerationError?> ValidatePublicationAsync(IReadOnlyDictionary<string, JsonNode> metadata, CancellationToken cancellationToken);
    }
}
