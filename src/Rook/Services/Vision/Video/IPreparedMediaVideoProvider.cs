using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;
namespace Rook.Services.Vision.Video
{
    internal interface IPreparedMediaVideoProvider
    {
        Task<ProviderSubmitOutcome> SubmitPreparedAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot preparedMedia, Action beforeDispatch, CancellationToken ct, VideoPreparationLease? phase = null);
    }
}
