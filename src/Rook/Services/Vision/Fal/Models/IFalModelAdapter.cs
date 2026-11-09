using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
namespace Rook.Services.Vision.Fal.Models
{
    public interface IFalModelAdapter
    {
        JsonObject BuildPayload(FalNormalizedRequest request, IReadOnlyList<FalPreparedMedia> media);
        ProviderResultOutcome MapResult(FalOperationBinding binding, JsonObject response);
    }
}
