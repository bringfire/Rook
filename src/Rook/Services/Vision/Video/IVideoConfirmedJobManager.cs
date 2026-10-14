using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
namespace Rook.Services.Vision.Video
{
    internal interface IVideoConfirmedJobManager
    {
        Task<VideoRouteQuoteResult> QuoteAsync(VideoRequestIntent intent, CancellationToken ct);
        Task<JobSubmitResult> SubmitConfirmedAsync(VideoRequestIntent intent, VideoSubmitConfirmation confirmation, CancellationToken ct);
    }
    internal sealed class VideoExecutionProjection
    {
        private readonly JsonObject _fields;
        public VideoExecutionProjection(JsonObject fields) { _fields = (JsonObject)fields.DeepClone(); }
        public JsonObject Fields => (JsonObject)_fields.DeepClone();
    }
}
