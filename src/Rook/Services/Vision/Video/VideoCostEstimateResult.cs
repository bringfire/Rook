namespace Rook.Services.Vision.Video
{
    public sealed record VideoCostEstimateResult(
        bool Success,
        VideoCostEstimate? Estimate,
        VideoJobError? Error)
    {
        public static VideoCostEstimateResult Ok(VideoCostEstimate estimate) =>
            new(true, estimate, null);

        public static VideoCostEstimateResult Fail(VideoJobError error) =>
            new(false, null, error);
    }
}
