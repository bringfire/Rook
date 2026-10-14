using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoExecutionSnapshotTests
    {
        internal static VideoJobRecord Record()
        {
            var request = TestVideoFixtures.DefaultT2vRequest();
            var model = TestVideoFixtures.VeoLiteResolved();
            return VideoJobRecordFactory.From(Guid.NewGuid(), request, model, new VideoCostEstimator().Estimate(model, request).Estimate!, VideoJobState.Submitting, DateTimeOffset.UtcNow);
        }
        internal static JsonObject Data() => new() { ["requested_provider"] = "veo", ["requested_model"] = "veo-3.1-lite-generate-preview", ["deadline_utc"] = "2026-10-14T15:20:00+00:00", ["accepted_quote"] = new JsonObject(), ["attempts"] = new JsonArray(new JsonObject { ["provider"] = "veo", ["dispatch_state"] = "intent_recorded", ["generation_dispatch_attempted"] = false }) };
        [Fact]
        public void IntentSnapshotSurvivesReopenWithoutSendFlag()
        {
            var directory = Path.Combine(Path.GetTempPath(), "rook-video-" + Guid.NewGuid());
            try
            {
                var file = Path.Combine(directory, "ledger.jsonl");
                var data = Data();
                var record = VideoExecutionSnapshot.Write(Record(), new VideoExecutionSnapshot(1, data));
                data["attempts"] = new JsonArray();
                new JsonlVideoJobLedger(file).Append(record);
                var restored = VideoExecutionSnapshot.Read(new JsonlVideoJobLedger(file).ReadAll().Records.Single());
                Assert.Null(restored.Error);
                var attempt = restored.Snapshot!.Data["attempts"]![0]!;
                Assert.Equal("intent_recorded", attempt["dispatch_state"]!.GetValue<string>());
                Assert.False(attempt["generation_dispatch_attempted"]!.GetValue<bool>());
            }
            finally { if (Directory.Exists(directory)) Directory.Delete(directory, true); }
        }
        [Fact]
        public void CriticalExtensionVersionFailsClosedButLegacyReads()
        {
            var record = Record();
            Assert.Null(VideoExecutionSnapshot.Read(record).Error);
            Assert.Null(VideoExecutionSnapshot.Read(record).Snapshot);
            var unsupported = record with { Extensions = new JsonObject { ["video_execution"] = new JsonObject { ["version"] = 99 } } };
            Assert.NotNull(VideoExecutionSnapshot.Read(unsupported).Error);
            var corrupt = VideoExecutionSnapshot.Write(record, new VideoExecutionSnapshot(1, Data()));
            corrupt.Extensions!["video_execution"]!["deadline_utc"] = "broken";
            Assert.NotNull(VideoExecutionSnapshot.Read(corrupt).Error);
        }
    }
}
