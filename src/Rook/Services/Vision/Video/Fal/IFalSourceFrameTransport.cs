using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed record FalVeoSourceUrls(string? Start, string? End, IReadOnlyList<string> References);
    internal interface IFalVeoSourceFrameTransport
    {
        Task<(FalVeoSourceUrls? Urls, GenerationError? Error)> ResolveAndUploadVeoAsync(FalVeoBinding binding, VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, string apiKey, CancellationToken ct);
    }

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
