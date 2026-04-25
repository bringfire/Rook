namespace Rook.Services.Vision.Video
{
    public interface IVideoCostEstimator
    {
        VideoCostEstimateResult Estimate(VideoGenerationRequest request);
    }
}
