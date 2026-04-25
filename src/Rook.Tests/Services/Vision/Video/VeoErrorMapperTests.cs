using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VeoErrorMapperTests
    {
        [Theory]
        [InlineData(401, VideoErrorCode.DependencyUnavailable, false)]
        [InlineData(403, VideoErrorCode.DependencyUnavailable, false)]
        [InlineData(429, VideoErrorCode.DependencyUnavailable, true)]
        [InlineData(400, VideoErrorCode.InvalidRequest, false)]
        [InlineData(404, VideoErrorCode.InvalidRequest, false)]
        [InlineData(500, VideoErrorCode.ExecutionFailed, true)]
        [InlineData(502, VideoErrorCode.ExecutionFailed, true)]
        [InlineData(503, VideoErrorCode.ExecutionFailed, true)]
        [InlineData(504, VideoErrorCode.ExecutionFailed, true)]
        public void MapStartFailure_classifies_status_codes(
            int status, VideoErrorCode expectedCode, bool expectedRetryable)
        {
            var err = VeoErrorMapper.MapStartFailure(status, "{\"error\":\"...\"}");

            Assert.Equal(expectedCode, err.Code);
            Assert.Equal(expectedRetryable, err.Retryable);
        }

        [Fact]
        public void MapStartFailure_includes_truncated_body_excerpt()
        {
            var longBody = new string('x', 500);

            var err = VeoErrorMapper.MapStartFailure(400, longBody);

            Assert.Contains("xxx", err.Message);
            Assert.True(err.Message.Length < 500);
        }

        [Fact]
        public void MapStartFailure_carries_full_body_in_provider_message()
        {
            var body = "the full provider error body";

            var err = VeoErrorMapper.MapStartFailure(400, body);

            Assert.Equal(body, err.ProviderMessage);
        }

        [Fact]
        public void Unknown_status_falls_back_to_ExecutionFailed_retryable()
        {
            var err = VeoErrorMapper.MapStartFailure(599, "weird");

            Assert.Equal(VideoErrorCode.ExecutionFailed, err.Code);
            Assert.True(err.Retryable);
        }

        [Fact]
        public void NetworkError_is_DependencyUnavailable_retryable()
        {
            var err = VeoErrorMapper.NetworkError("submit", "DNS failure");

            Assert.Equal(VideoErrorCode.DependencyUnavailable, err.Code);
            Assert.True(err.Retryable);
            Assert.Contains("submit", err.Message);
            Assert.Contains("DNS failure", err.Message);
        }

        [Fact]
        public void MissingApiKey_is_DependencyUnavailable_not_retryable()
        {
            var err = VeoErrorMapper.MissingApiKey();

            Assert.Equal(VideoErrorCode.DependencyUnavailable, err.Code);
            Assert.False(err.Retryable);
        }

        [Theory]
        [InlineData(401)]
        [InlineData(429)]
        [InlineData(500)]
        public void Op_name_appears_in_message(int status)
        {
            var pollErr = VeoErrorMapper.MapPollFailure(status, "x");
            var cancelErr = VeoErrorMapper.MapCancelFailure(status, "x");
            var downloadErr = VeoErrorMapper.MapDownloadFailure(status, "x");

            Assert.Contains("poll", pollErr.Message);
            Assert.Contains("cancel", cancelErr.Message);
            Assert.Contains("download", downloadErr.Message);
        }
    }
}
