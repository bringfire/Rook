using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
namespace Rook.Services.Vision.Video
{
    internal interface IPreparedMediaVideoProvider
    {
        Task<ProviderSubmitOutcome> SubmitPreparedAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, Action beforeDispatch, CancellationToken ct);
    }
}
