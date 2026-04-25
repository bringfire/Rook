using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    public sealed record CostBreakdownComponent(
        string Label,
        decimal DollarsUsd);

    public sealed record VideoCostEstimate(
        decimal DollarsUsd,
        string Model,
        string Resolution,
        int DurationSeconds,
        int NumberOfVideos,
        IReadOnlyList<CostBreakdownComponent> Breakdown);
}
