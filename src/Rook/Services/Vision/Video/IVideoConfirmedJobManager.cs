using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
namespace Rook.Services.Vision.Video
{
    internal interface IConfiguredVideoJobManager
    {
        Task<JobSubmitResult> SubmitConfiguredAsync(VideoGenerationRequest request, Rook.Services.Vision.Fal.Models.FalNormalizedRequest normalized,
            Rook.Services.Vision.Fal.FalMediaSnapshot media, Rook.Services.Vision.Fal.Models.FalPricingSnapshot? pricing,
            CancellationToken ct, Rook.Services.Vision.Fal.Models.FalSubmitConfirmation? confirmation = null);
    }
    internal interface IVideoConfirmedJobManager
    {
        bool ConfirmedRoutingAvailable { get; }
        JsonObject ModelAvailability(string model);
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
