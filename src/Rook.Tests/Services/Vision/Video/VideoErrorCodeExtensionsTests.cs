using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoErrorCodeExtensionsTests
    {
        [Theory]
        [InlineData(VideoErrorCode.InvalidRequest, false)]
        [InlineData(VideoErrorCode.UnsupportedMedia, false)]
        [InlineData(VideoErrorCode.DependencyUnavailable, true)]
        [InlineData(VideoErrorCode.ExecutionFailed, true)]
        [InlineData(VideoErrorCode.Cancelled, false)]
        [InlineData(VideoErrorCode.Interrupted, true)]
        public void IsRetryable_matches_v3_1_contract(
            VideoErrorCode code, bool expected)
        {
            Assert.Equal(expected, code.IsRetryable());
        }
    }
}
