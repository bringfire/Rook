using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal interface IFalSourceFrameTransport
    {
        Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(
            FalSourceFramePolicy policy,
            VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media,
            string apiKey,
            CancellationToken ct);
    }
}
