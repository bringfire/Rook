using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal interface IFalSeedanceSourceTransport
    {
        Task<(FalSeedanceSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct);
    }
}
