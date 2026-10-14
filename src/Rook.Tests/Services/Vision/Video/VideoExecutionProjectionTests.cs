using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoExecutionProjectionTests
    {
        [Fact]
        public void CredentialFailureWithoutRouteIsProjected()
        {
            var data = VideoExecutionSnapshotTests.Data();
            data["credential_failure"] = new JsonObject { ["provider"] = "fal", ["kind"] = "rejected" };
            var record = VideoExecutionSnapshot.Write(VideoExecutionSnapshotTests.Record(), new VideoExecutionSnapshot(1, data));
            var projection = VideoExecutionSnapshot.Project(record, null, VideoStopPersistence.None).Fields;
            Assert.Null(projection["video_route"]);
            Assert.Equal("fal", projection["credential_failure"]!["provider"]!.GetValue<string>());
            Assert.True(projection["submission_unknown"]!.GetValue<bool>());
        }
        [Theory]
        [InlineData(1, "pending")]
        [InlineData(3, "failed")]
        public void PendingStopDoesNotClaimDurableCancelled(int persistence, string expected)
        {
            var record = VideoExecutionSnapshot.Write(VideoExecutionSnapshotTests.Record() with { State = VideoJobState.Polling }, new VideoExecutionSnapshot(1, VideoExecutionSnapshotTests.Data()));
            var result = JobStatusResult.InFlight(record.State, null) with { Execution = VideoExecutionSnapshot.Project(record, VideoStopReason.Deadline, (VideoStopPersistence)persistence) };
            Assert.Equal(VideoJobState.Polling, result.State);
            Assert.True(result.Execution.Fields["execution_stopped"]!.GetValue<bool>());
            Assert.Equal(expected, result.Execution.Fields["stop_persistence"]!.GetValue<string>());
            Assert.Equal("deadline", result.Execution.Fields["first_stop_reason"]!.GetValue<string>());
        }
        [Fact]
        public void FailedStopPreservesOriginalReason()
        {
            var data = VideoExecutionSnapshotTests.Data(); data["first_stop_reason"] = "shutdown";
            var record = VideoExecutionSnapshot.Write(VideoExecutionSnapshotTests.Record() with { State = VideoJobState.Interrupted }, new VideoExecutionSnapshot(1, data));
            Assert.Equal("shutdown", VideoExecutionSnapshot.Project(record, null, VideoStopPersistence.Durable).Fields["first_stop_reason"]!.GetValue<string>());
        }
        [Fact]
        public void LegacyResultsRemainUnchanged()
        {
            Assert.Null(JobStatusResult.Complete(Guid.NewGuid()).Execution);
            Assert.Empty(VideoExecutionSnapshot.Project(VideoExecutionSnapshotTests.Record(), null, VideoStopPersistence.None).Fields);
        }
        [Fact]
        public void SafeDetailCodesSurviveConversion()
        {
            var source = new GenerationError(GenerationErrorCode.InvalidRequest, "Fresh estimate required.", false, "estimate_fingerprint", "estimate_stale");
            var job = VideoProviderOutcomeAdapters.ToVideoJobError(source);
            Assert.Equal("estimate_stale", ((GenerationError)job).ProviderErrorCode);
            Assert.Equal("estimate_stale", VideoProviderOutcomeAdapters.ToGenerationError(job).ProviderErrorCode);
        }
    }
}
