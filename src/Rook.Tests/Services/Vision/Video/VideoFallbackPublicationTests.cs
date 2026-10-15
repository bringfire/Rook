using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Threading;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;
using static Rook.Tests.Services.Vision.Video.VideoFalFallbackManagerTests;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoFallbackPublicationTests
    {
        private sealed class HeldPoster : IVideoPosterSidecarProducer
        {
            internal readonly TaskCompletionSource<Guid> Entered = Signal<Guid>();
            public Task<VideoPosterSidecarResult> TryPublishPosterAsync(Guid id, CancellationToken ct) { Entered.TrySetResult(id); return Signal<VideoPosterSidecarResult>().Task; }
        }
        [Fact]
        public async Task HeaderOnlyMp4NeverCompletes()
        {
            using var rig = new Rig();
            rig.Google.Fetch = (h, ct) => Task.FromResult<ProviderResultOutcome>(new SuccessResultOutcome(new ProviderResultEnvelope(new[] { new ResultArtifact("video", new InlineArtifactBody(new byte[] { 0,0,0,20,102,116,121,112,105,115,111,109,0,0,0,0,105,115,111,109 }), "video/mp4", new Dictionary<string, JsonNode>()) }, new Dictionary<string, JsonNode>())));
            var submit = await rig.Submit(); await Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Error, rig.Record(submit.JobId!.Value).State); Assert.Empty(rig.Store.List());
        }
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task FinishedJobsReleasePreparedSourceBuffers(bool fail)
        {
            using var rig = new Rig(); var input = MediaRef.ForArtifact(Guid.NewGuid(), "image"); rig.Media.Values[input] = Rook.Tests.Services.Vision.Video.Fal.FalVeoCompatibilityTests.Image(1280, 720);
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", mode: VideoMode.I2V, startFrame: input), new JsonObject());
            if (fail) rig.Google.Poll = (h, ct) => Task.FromResult<ProviderStatusOutcome>(new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Failed test provider.", false)));
            await rig.Submit(intent); await Limit(rig.Done.Task);
            var jobs = (System.Collections.IDictionary)typeof(VideoJobManager).GetField("_routedJobs", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.GetValue(rig.Manager)!;
            foreach (var job in jobs.Values) Assert.Null(job.GetType().GetField("Media", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.GetValue(job));
        }
        [Theory]
        [InlineData("poll", 403)]
        [InlineData("poll", 500)]
        [InlineData("fetch", 500)]
        public async Task LifecycleErrorsDoNotPublishRawProviderText(string phase, int status)
        {
            using var rig = new Rig(); const string sentinel = "RAW_PROVIDER_SENTINEL_signed_url_key";
            var error = VideoProviderOutcomeAdapters.ToGenerationError(VeoErrorMapper.MapPollFailure(status, sentinel));
            if (phase == "poll") rig.Google.Poll = (h, ct) => Task.FromResult<ProviderStatusOutcome>(new FailedStatusOutcome(error));
            else rig.Google.Fetch = (h, ct) => Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(error));
            var submit = await rig.Submit(); await Limit(rig.Done.Task);
            var handler = new Rook.Handlers.VideoOpHandler(rig.Manager, rig.Coordinator.Registry, new VideoCostEstimator());
            var response = handler.DispatchOffUi(new JsonObject { ["op"] = "get_video_job", ["job_id"] = submit.JobId!.Value.ToString("D") }.ToJsonString());
            Assert.DoesNotContain(sentinel, System.Text.Json.JsonSerializer.Serialize(response)); Assert.DoesNotContain(sentinel, File.ReadAllText(Path.Combine(rig.DirectoryPath, "ledger.jsonl"))); Assert.Equal(0, rig.Fal.Submits);
        }
        [Fact]
        public async Task CancelAfterCompletionAdmissionWaitsForDurableCompletion()
        {
            using var rig = new Rig(); var entered = Signal<bool>(); var release = Signal<bool>();
            rig.Ledger.BeforeAppend = r => { if (r.State == VideoJobState.Complete) { entered.TrySetResult(true); release.Task.GetAwaiter().GetResult(); } };
            var submit = await rig.Submit(); await Limit(entered.Task);
            var cancellation = rig.Manager.CancelAsync(submit.JobId!.Value, default);
            Assert.False(cancellation.IsCompleted); release.TrySetResult(true);
            Assert.Equal(VideoJobState.Complete, (await Limit(cancellation)).State); await Limit(rig.Done.Task);
            Assert.NotNull(rig.Store.Get(rig.Record(submit.JobId.Value).ResultArtifactId!.Value));
        }
        [Fact]
        public async Task SidecarWaitCannotExtendWholeJobBudget()
        {
            var poster = new HeldPoster(); using var rig = new Rig(poster: poster);
            var submit = await rig.Submit(); var provisional = await Limit(poster.Entered.Task);
            Assert.False(rig.Manager.IsArtifactVisible(rig.Store.Get(provisional)!));
            rig.Timer.Fire(); await Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Interrupted, rig.Record(submit.JobId!.Value).State);
            Assert.Null(rig.Store.Get(provisional));
        }
        [Fact]
        public async Task ProviderCompleteWithoutValidVideoDoesNotPublishOrSwitch()
        {
            using var rig = new Rig();
            rig.Google.Fetch = (h, ct) => Task.FromResult<ProviderResultOutcome>(new SuccessResultOutcome(new ProviderResultEnvelope(new[] { new ResultArtifact("video", new InlineArtifactBody(new byte[] { 1, 2, 3 }), "video/mp4", new Dictionary<string, JsonNode>()) }, new Dictionary<string, JsonNode>())));
            var submit = await rig.Submit(); await Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Error, rig.Record(submit.JobId!.Value).State);
            Assert.Empty(rig.Store.List()); Assert.Equal(0, rig.Fal.Submits);
        }
        [Fact]
        public async Task MarkerFailureAfterDurableCompleteRetainsSameArtifact()
        {
            using var rig = new Rig(store => new VideoPublicationService(store, new VideoArtifactMaterializer(), (id, flag, value) => throw new IOException("marker write failed")));
            var submit = await rig.Submit(); await Limit(rig.Done.Task);
            var record = rig.Record(submit.JobId!.Value);
            var id = record.ResultArtifactId!.Value;
            Assert.Equal(VideoJobState.Complete, record.State);
            Assert.NotNull(rig.Store.Get(id));
            Assert.True(rig.Manager.IsArtifactVisible(rig.Store.Get(id)!));
            Assert.Null((await rig.Manager.FetchResultAsync(record.JobId, default)).Error);
            var status = await rig.Manager.GetStatusAsync(record.JobId, default);
            Assert.Contains("artifact_marker_pending", status.Execution!.Fields["warnings"]!.AsArray().Select(n => n!.GetValue<string>()));
            Assert.Equal(1, rig.Google.Submits);
        }
        [Fact]
        public void RestartMarkerRepairIsIdempotent()
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-publication-" + Guid.NewGuid());
            try
            {
                var store = new ArtifactStore(root); var record = VideoExecutionSnapshotTests.Record();
                var artifact = store.Create("generated_video", new[] { new BlobInput("video", new byte[] { 1 }, "mp4") }, metadata: new Dictionary<string, JsonNode?> { ["video_job_id"] = JsonValue.Create(record.JobId.ToString("D")) }, flags: new Dictionary<string, JsonNode?> { ["video_publication"] = JsonValue.Create("provisional") });
                record = record with { State = VideoJobState.Complete, ResultArtifactId = artifact.Id };
                var service = new VideoPublicationService(store, new VideoArtifactMaterializer());
                Assert.True(service.IsVisible(artifact, record));
                Assert.Null(service.RepairFromLedger(artifact, record));
                Assert.Null(service.RepairFromLedger(store.Get(artifact.Id)!, record));
                Assert.NotNull(store.Get(artifact.Id));
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
        [Fact]
        public void UnknownLedgerQuarantinesRatherThanDeletes()
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-publication-" + Guid.NewGuid());
            try
            {
                var store = new ArtifactStore(root); var record = VideoExecutionSnapshotTests.Record();
                var artifact = store.Create("generated_video", new[] { new BlobInput("video", new byte[] { 1 }, "mp4") }, metadata: new Dictionary<string, JsonNode?> { ["video_job_id"] = JsonValue.Create(record.JobId.ToString("D")) }, flags: new Dictionary<string, JsonNode?> { ["video_publication"] = JsonValue.Create("provisional") });
                var service = new VideoPublicationService(store, new VideoArtifactMaterializer());
                Assert.False(service.IsVisible(artifact, null)); Assert.NotNull(service.RepairFromLedger(artifact, null)); Assert.NotNull(store.Get(artifact.Id));
                service.RemoveOwnedProvisional(artifact, record with { JobId = Guid.NewGuid(), State = VideoJobState.Interrupted });
                Assert.NotNull(store.Get(artifact.Id));
                service.RemoveOwnedProvisional(artifact, record with { State = VideoJobState.Interrupted }); Assert.Null(store.Get(artifact.Id));
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }
        [Fact]
        public async Task StopOrTerminalAppendFailureRemovesOnlyOwnedProvisional()
        {
            using var rig = new Rig();
            var rolledBack = Signal<Guid>(); rig.Manager.AfterRollbackForTests = id => rolledBack.TrySetResult(id);
            rig.Ledger.BeforeAppend = record => { if (record.State == VideoJobState.Complete) throw new IOException("complete commit failed"); };
            var result = await rig.Submit(); await Limit(rig.Done.Task);
            await Limit(rolledBack.Task);
            Assert.NotEqual(VideoJobState.Complete, rig.Record(result.JobId!.Value).State);
            Assert.Empty(rig.Store.List());
            Assert.DoesNotContain(rig.Store.List(), rig.Manager.IsArtifactVisible);
        }
    }
}
