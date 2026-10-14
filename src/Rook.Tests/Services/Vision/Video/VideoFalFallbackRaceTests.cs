using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;
using static Rook.Tests.Services.Vision.Video.VideoFalFallbackManagerTests;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoFalFallbackRaceTests
    {
        [Fact]
        public async Task HeldResponseSnapshotRestoresUncertainty()
        {
            using var rig = new Rig(); var entered = Signal<bool>(); var response = Signal<ProviderSubmitOutcome>();
            rig.Google.Submit = (r, ct) => { entered.TrySetResult(true); return response.Task; };
            var result = await rig.Submit(); await Limit(entered.Task);
            var frozen = new JsonlVideoJobLedger(rig.Ledger.Inner.FilePath).ReadAll().Records.Single();
            Assert.Equal("intent_recorded", VideoExecutionSnapshot.Read(frozen).Snapshot!.Data["attempts"]![0]!["dispatch_state"]!.GetValue<string>());
            var copyPath = Path.Combine(rig.DirectoryPath, "restored.jsonl");
            File.Copy(rig.Ledger.Inner.FilePath, copyPath);
            using (var restored = new VideoJobManager(rig.Coordinator.Registry, rig.Media, new JsonlVideoJobLedger(copyPath), new VideoCostEstimator(), rig.Store, rig.Clock, null, TimeSpan.Zero, 2, null, coordinator: rig.Coordinator, routeQuotes: rig.Quotes, deadlineTimer: new VideoExecutionBudgetTests.Timer()))
            {
                restored.ReconcileInterruptedJobs();
                var status = await restored.GetStatusAsync(result.JobId!.Value, default);
                Assert.Equal(VideoJobState.Interrupted, status.State);
                Assert.True(status.Execution!.Fields["submission_unknown"]!.GetValue<bool>());
                Assert.Equal(1, rig.Google.Submits); Assert.Equal(0, rig.Fal.Submits);
            }
            rig.Timer.Fire(); await Limit(rig.Done.Task);
            response.TrySetResult(new QueuedSubmitOutcome(new ProviderJobHandle("late-google")));
            Assert.Equal(VideoJobState.Interrupted, (await rig.Manager.GetStatusAsync(result.JobId!.Value, default)).State);
        }
        [Fact]
        public async Task StoppedIntentAppendPreventsSend()
        {
            using var rig = new Rig(); var entered = Signal<bool>(); using var release = new ManualResetEventSlim();
            rig.Ledger.BeforeAppend = record => { var data = VideoExecutionSnapshot.Read(record).Snapshot?.Data; if (data?["attempts"]?.AsArray().LastOrDefault()?["dispatch_state"]?.GetValue<string>() == "intent_recorded") { entered.TrySetResult(true); release.Wait(); } };
            var result = await rig.Submit(); await Limit(entered.Task);
            rig.Timer.Fire(); release.Set(); await Limit(rig.Done.Task);
            Assert.Equal(0, rig.Google.Submits); Assert.Equal(0, rig.Fal.Submits);
            Assert.Equal(VideoJobState.Interrupted, rig.Record(result.JobId!.Value).State);
        }
        [Fact]
        public async Task FirstStopSurvivesBlockedAndFailedAppend()
        {
            using var rig = new Rig(); var polling = Signal<bool>(); var stopped = Signal<bool>(); var appendEntered = Signal<bool>(); using var release = new ManualResetEventSlim();
            rig.Google.Poll = (h, ct) => { ct.Register(() => stopped.TrySetResult(true)); polling.TrySetResult(true); return Signal<ProviderStatusOutcome>().Task; };
            var result = await rig.Submit(); await Limit(polling.Task);
            rig.Ledger.BeforeAppend = record => { if (record.State is VideoJobState.Interrupted or VideoJobState.Cancelled) { appendEntered.TrySetResult(true); release.Wait(); } };
            rig.Timer.Fire(); await Limit(stopped.Task); await Limit(appendEntered.Task);
            var cancel = rig.Manager.CancelAsync(result.JobId!.Value, default);
            var pending = await rig.Manager.GetStatusAsync(result.JobId.Value, default);
            Assert.Equal("deadline", pending.Execution!.Fields["first_stop_reason"]!.GetValue<string>());
            Assert.Equal("pending", pending.Execution.Fields["stop_persistence"]!.GetValue<string>());
            Assert.False(cancel.IsCompleted);
            release.Set(); await Limit(cancel); await Limit(rig.Done.Task);
            Assert.Equal(VideoJobState.Interrupted, rig.Record(result.JobId.Value).State);
            Assert.Equal("deadline", VideoExecutionSnapshot.Read(rig.Record(result.JobId.Value)).Snapshot!.Data["first_stop_reason"]!.GetValue<string>());
        }
        [Fact]
        public async Task AcceptedHandleAppendFailureStopsAndCleansUp()
        {
            using var rig = new Rig();
            rig.Ledger.BeforeAppend = record => { if (record.ProviderHandle != null) throw new IOException("blocked device"); };
            var result = await rig.Submit(); await Limit(rig.Done.Task);
            var status = await rig.Manager.GetStatusAsync(result.JobId!.Value, default);
            Assert.Equal("failed", status.Execution!.Fields["stop_persistence"]!.GetValue<string>());
            Assert.True(status.Execution.Fields["execution_stopped"]!.GetValue<bool>());
            Assert.Equal(0, rig.Google.Polls);
            Assert.True(rig.Google.Cancels > 0);
        }

        [Fact]
        public async Task FailedStopAppendCannotReenableExecutionAndRetriesOriginalReason()
        {
            using var rig = new Rig(); var polling = Signal<bool>();
            rig.Google.Poll = (h, ct) => { polling.TrySetResult(true); return Signal<ProviderStatusOutcome>().Task; };
            var submit = await rig.Submit(); await Limit(polling.Task);
            rig.Ledger.BeforeAppend = record => { if (record.State is VideoJobState.Interrupted or VideoJobState.Cancelled) throw new IOException("unresponsive device"); };
            rig.Timer.Fire(); await Limit(rig.Done.Task);
            var failed = await rig.Manager.GetStatusAsync(submit.JobId!.Value, default);
            Assert.Equal("failed", failed.Execution!.Fields["stop_persistence"]!.GetValue<string>());
            Assert.True(failed.Execution.Fields["execution_stopped"]!.GetValue<bool>());
            rig.Ledger.BeforeAppend = null;
            await rig.Manager.CancelAsync(submit.JobId.Value, default);
            var saved = rig.Record(submit.JobId.Value);
            Assert.Equal(VideoJobState.Interrupted, saved.State);
            Assert.Equal("deadline", VideoExecutionSnapshot.Read(saved).Snapshot!.Data["first_stop_reason"]!.GetValue<string>());
            Assert.Equal(1, rig.Google.Polls);
        }

        [Fact]
        public async Task PreparedMediaABACannotAuthorizeDifferentSentBytes()
        {
            using var rig = new Rig(); var prepared = Signal<bool>(); var release = Signal<bool>();
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var a = Fal.FalVeoCompatibilityTests.Image(1280, 720); var original = (byte[])a.Bytes.Clone();
            rig.Media.Values[reference] = a;
            byte[]? sent = null; string? digest = null;
            rig.Google.Prepare = async media => { prepared.TrySetResult(true); await release.Task; sent = media.Slots[0].CopyBytes(); digest = media.Slots[0].Sha256; };
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: reference), new JsonObject());
            var quote = (await rig.Quotes.QuoteAsync(intent, default)).Quote!;
            var submit = await rig.Submit(intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd));
            await Limit(prepared.Task);
            a.Bytes[0] = 0;
            rig.Media.Values[reference] = new ResolvedMedia((byte[])original.Clone(), "image/png");
            release.TrySetResult(true); await Limit(rig.Done.Task);
            Assert.Equal(original, sent);
            Assert.Equal(digest, VideoExecutionSnapshot.Read(rig.Record(submit.JobId!.Value)).Snapshot!.Data["prepared_media"]![0]!["sha256"]!.GetValue<string>());
            Assert.Equal(1, rig.Google.Submits);
        }

        [Fact]
        public async Task ConcurrentJobsKeepDifferentRoutes()
        {
            using var rig = new Rig(); var aReply = Signal<ProviderSubmitOutcome>(); var bReply = Signal<ProviderSubmitOutcome>(); var submitted = Signal<bool>(); var falPolling = Signal<bool>(); var allDone = Signal<bool>();
            var count = 0; var done = 0;
            rig.Manager.AfterRunForTests = _ => { if (Interlocked.Increment(ref done) == 2) allDone.TrySetResult(true); };
            rig.Google.Submit = (request, ct) => { if (Interlocked.Increment(ref count) == 2) submitted.TrySetResult(true); return request.Prompt == "A" ? aReply.Task : bReply.Task; };
            rig.Fal.Poll = (h, ct) => { falPolling.TrySetResult(true); return Signal<ProviderStatusOutcome>().Task; };
            var aIntent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-fast-generate-preview", prompt: "A"), new JsonObject());
            var bIntent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-fast-generate-preview", prompt: "B"), new JsonObject());
            var a = await rig.Submit(aIntent); var b = await rig.Submit(bIntent); await Limit(submitted.Task);
            bReply.TrySetResult(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "rejected", false, null, "rook.veo.key_rejected")));
            await Limit(falPolling.Task);
            rig.Timer.Fire();
            aReply.TrySetResult(new QueuedSubmitOutcome(new ProviderJobHandle("google-A")));
            await Limit(allDone.Task);
            var aRecord = rig.Record(a.JobId!.Value); var bRecord = rig.Record(b.JobId!.Value);
            Assert.Equal(VideoJobState.Complete, aRecord.State); Assert.Equal("veo", aRecord.Provider); Assert.Equal(.80m, aRecord.Pricing.TotalUsd);
            Assert.Equal(VideoJobState.Interrupted, bRecord.State); Assert.Equal("fal", bRecord.Provider); Assert.Equal(1.20m, bRecord.Pricing.TotalUsd);
            Assert.Equal("google-A", aRecord.ProviderJobId); Assert.Equal("B", bRecord.ProviderJobId);
            Assert.Equal(2, rig.Timer.Schedules); Assert.Equal(2, rig.Google.Submits); Assert.Equal(1, rig.Fal.Submits);
        }
    }
}
