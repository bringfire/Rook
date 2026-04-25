namespace Rook.Services.Vision.Video
{
    public static class VideoErrorCodeExtensions
    {
        public static bool IsRetryable(this VideoErrorCode code) => code switch
        {
            VideoErrorCode.DependencyUnavailable => true,
            VideoErrorCode.ExecutionFailed => true,
            VideoErrorCode.Interrupted => true,
            _ => false,
        };
    }
}
