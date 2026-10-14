using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed record VideoSubmitConfirmation(string? EstimateFingerprint, decimal? MaxEstimatedCostUsd);
    internal sealed class VideoRouteQuote
    {
        private readonly JsonObject _canonical;
        public VideoRouteQuote(JsonObject canonicalSnapshot, IReadOnlyList<VideoRouteCandidate> candidates, VideoCostEstimate primaryEstimate, decimal maximumEstimatedCostUsd, string estimateFingerprint)
        { _canonical = (JsonObject)canonicalSnapshot.DeepClone(); Candidates = candidates; PrimaryEstimate = primaryEstimate; MaximumEstimatedCostUsd = maximumEstimatedCostUsd; EstimateFingerprint = estimateFingerprint; }
        public JsonObject CanonicalSnapshot => (JsonObject)_canonical.DeepClone();
        public IReadOnlyList<VideoRouteCandidate> Candidates { get; }
        public VideoCostEstimate PrimaryEstimate { get; }
        public decimal MaximumEstimatedCostUsd { get; }
        public string EstimateFingerprint { get; }
    }
    internal sealed record VideoRouteQuoteResult(VideoRouteQuote? Quote, GenerationError? Error);
}
