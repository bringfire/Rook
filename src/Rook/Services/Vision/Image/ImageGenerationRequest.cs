using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed record ImageGenerationRequest(
        string Model,
        string Prompt,
        string Resolution,
        string AspectRatio,
        int NumberOfImages,
        IReadOnlyList<MediaRef>? ReferenceImages,
        ProviderOptions Options)
        : GenerationRequest(Model, Options);
}
