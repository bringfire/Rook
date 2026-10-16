using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;
using Rook.Tests.Services.Vision.Video.Fal;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingDispatchTests
    {
        [Fact]
        public async Task Dispatch_ResourceSaturationBeforeIntentIsRetryableLocalFailure()
        {
            var provider = new VideoFalFallbackManagerTests.Provider();
            using var rig = new VideoFramingQuoteTests.Rig(google: provider);
            var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            var ledger = new VideoFalFallbackManagerTests.Ledger(Path.Combine(rig.Root, "saturated.jsonl"));
            using var queuedStop = new CancellationTokenSource();
            VideoPreparationLease? first = null, second = null;
            Task<VideoPreparationLease>? third = null, fourth = null;
            ledger.BeforeAppend = record => {
                if (record.Extensions?["video_execution"]?["phase"]?.GetValue<string>() != "preparation" || first != null) return;
                first = rig.Resources.AcquireAsync(default).GetAwaiter().GetResult();
                second = rig.Resources.AcquireAsync(default).GetAwaiter().GetResult();
                third = rig.Resources.AcquireAsync(queuedStop.Token); fourth = rig.Resources.AcquireAsync(queuedStop.Token);
            };
            using var manager = Manager(rig, ledger); var done = Signal(); manager.AfterRunForTests = _ => done.TrySetResult(true);
            try
            {
                var submitted = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(rig.Intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd), default);
                Assert.NotNull(submitted.JobId); await Limit(done.Task);
                var record = ledger.ReadAll().Records.Single();
                Assert.Equal(VideoJobState.Error, record.State);
                Assert.Equal("source_preparation_failed", record.Error!.ProviderErrorCode); Assert.True(record.Error.Retryable);
                Assert.Empty(record.Extensions!["video_execution"]!["attempts"]!.AsArray());
                Assert.Equal(0, provider.Submits); Assert.Equal(0, provider.Polls);
                var status = await manager.GetStatusAsync(submitted.JobId!.Value, default);
                Assert.Equal("preparation_busy", status.Execution!.Fields["source_preparation_error"]!["preparation_detail"]!.GetValue<string>());
                Assert.NotEqual(true, status.Execution.Fields["submission_outcome_unknown"]?.GetValue<bool>());
            }
            finally
            {
                queuedStop.Cancel();
                foreach (var queued in new[] { third, fourth }) if (queued != null)
                    try { using var unexpected = await queued; } catch (OperationCanceledException) { }
                first?.Dispose(); second?.Dispose();
            }
            Assert.Equal(0, rig.Resources.ActiveBundles);
        }
        [Fact]
        public async Task Dispatch_SeparateJobsKeepModesRoutesPricesAndStops()
        {
            var googleEntered = Signal(); var falEntered = Signal(); var releaseGoogle = Signal(); var releaseFal = Signal();
            byte[]? googleBytes = null, falBytes = null;
            var http = new Http(async (message, ct) => {
                if (message.RequestUri!.Host == "rest.fal.ai") return FalVeoQueueAdapterTests.Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload\",\"file_url\":\"https://v3.fal.media/files/source.png\"}");
                if (message.RequestUri.Host == "v3.fal.media") { falBytes = await message.Content!.ReadAsByteArrayAsync(); return FalVeoQueueAdapterTests.Http.Json(200, "{}"); }
                if (message.Method == HttpMethod.Post && message.RequestUri.AbsolutePath.Contains("predictLongRunning"))
                { var body = JsonNode.Parse(await message.Content!.ReadAsStringAsync())!; googleBytes = Convert.FromBase64String(body["instances"]![0]!["image"]!["bytesBase64Encoded"]!.GetValue<string>()); googleEntered.SetResult(true); await releaseGoogle.Task; return FalVeoQueueAdapterTests.Http.Json(200, "{\"name\":\"operations/google-only\"}"); }
                if (message.Method == HttpMethod.Post && message.RequestUri.Host == "queue.fal.run") { falEntered.SetResult(true); await releaseFal.Task; return FalVeoQueueAdapterTests.Http.Json(200, FalVeoQueueAdapterTests.Accepted); }
                return FalVeoQueueAdapterTests.Http.Json(500, "{}");
            });
            var client = new HttpClient(http); var catalog = FalVeoCompatibilityTests.ActiveCatalog();
            using var rig = new VideoFramingQuoteTests.Rig(new VeoProvider(() => "test-only", new VeoClient(client)), new FalVideoProvider(() => "test-only", new FalApiClient(client), null, catalog));
            var other = VideoRequestIntent.Normalize(rig.Intent.Request.With(model: "fal-ai/veo3.1/fast", options: new FalVeoOptions(), sourceFraming: SourceFramingMode.Fill), new JsonObject());
            var firstQuote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!; var secondQuote = (await rig.Quotes.QuoteAsync(other, default)).Quote!;
            var ledger = new FakeVideoJobLedger(); using var manager = Manager(rig, ledger); var done = Signal(); int completed = 0;
            manager.AfterRunForTests = _ => { if (Interlocked.Increment(ref completed) == 2) done.TrySetResult(true); };
            try
            {
                var first = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(rig.Intent, new(firstQuote.EstimateFingerprint, firstQuote.MaximumEstimatedCostUsd), default);
                var second = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(other, new(secondQuote.EstimateFingerprint, secondQuote.MaximumEstimatedCostUsd), default);
                await Limit(Task.WhenAll(googleEntered.Task, falEntered.Task));
                Assert.Equal(2, rig.Resources.ActiveBundles); Assert.NotEqual(first.JobId, second.JobId);
                await manager.CancelAsync(first.JobId!.Value, default);
                var otherStatus = await manager.GetStatusAsync(second.JobId!.Value, default); Assert.Null(otherStatus.Execution!.Fields["first_stop_reason"]);
                using var googleImage = VideoFrozenBuffer.CopyOf(googleBytes!, new VideoBufferBudget()); using var falImage = VideoFrozenBuffer.CopyOf(falBytes!, new VideoBufferBudget());
                Assert.Equal(firstQuote.SourcePreparation!["slots"]![0]!["prepared_sha256"]!.GetValue<string>(), googleImage.Sha256);
                Assert.Equal(secondQuote.SourcePreparation!["slots"]![0]!["prepared_sha256"]!.GetValue<string>(), falImage.Sha256); Assert.NotEqual(googleImage.Sha256, falImage.Sha256);
                releaseGoogle.SetResult(true); releaseFal.SetResult(true); await Limit(done.Task);
                var records = ledger.ReadAll().Records;
                Assert.Equal(3.20m, records.Single(r => r.JobId == first.JobId).Pricing.TotalUsd);
                var falRecord = records.Single(r => r.JobId == second.JobId); Assert.Equal(1.20m, falRecord.Pricing.TotalUsd); Assert.Equal("fal-ai/veo3.1/fast", falRecord.Model);
                Assert.Equal("request1", falRecord.ProviderHandle!.ProviderJobId); Assert.Null(falRecord.Extensions!["video_execution"]!["first_stop_reason"]);
            }
            finally { releaseGoogle.TrySetResult(true); releaseFal.TrySetResult(true); }
            await Limit(Task.Run(async () => { while (rig.Resources.ActiveBundles != 0) await Task.Delay(1); }));
        }
        [Fact]
        public async Task PreparationFailure_PersistsOnlyClosedEvidence_ThroughHandlerAndRestart()
        {
            var local = VideoSourcePreparationErrors.Create("source_preparation_failed", "start_frame", "fill", "render_limits_exceeded");
            var details = local.ProviderDetail!.ToDictionary(kv => kv.Key, kv => kv.Value);
            details["stderr"] = JsonValue.Create("RAW_PATH_SECRET_SENTINEL")!;
            local = local with { ProviderDetail = details };
            var provider = new VideoFalFallbackManagerTests.Provider { Submit = (_, _) => Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(local)) };
            using var rig = new VideoFramingQuoteTests.Rig(provider);
            var ledger = new FakeVideoJobLedger(); using var manager = Manager(rig, ledger);
            var done = Signal(); manager.AfterRunForTests = _ => done.TrySetResult(true);
            var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            var submit = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(rig.Intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd), default);
            await Limit(done.Task);
            var record = ledger.ReadAll().Records.Single(); Assert.Null(record.Error!.ProviderDetail);
            Assert.Equal("choose_fit", record.Extensions!["video_execution"]!["source_preparation_error"]!["action"]!.GetValue<string>());
            Assert.DoesNotContain("RAW_PATH", record.Extensions.ToJsonString());
            var handler = new VideoOpHandler(manager, rig.Coordinator.Registry, new VideoCostEstimator());
            foreach (string op in new[] { "get_video_job", "get_video_job_result", "list_video_jobs" })
            {
                var response = handler.DispatchOffUi(new JsonObject { ["op"] = op, ["job_id"] = submit.JobId!.Value.ToString("D") }.ToJsonString());
                string json = System.Text.Json.JsonSerializer.Serialize(response);
                Assert.Contains("render_limits_exceeded", json); Assert.Contains("choose_fit", json); Assert.DoesNotContain("RAW_PATH", json);
            }
            var cancelled = await handler.DispatchAsync(new JsonObject { ["op"] = "cancel_video_job", ["job_id"] = submit.JobId!.Value.ToString("D") }.ToJsonString());
            Assert.Contains("choose_fit", System.Text.Json.JsonSerializer.Serialize(cancelled));
            using var restored = Manager(rig, ledger); restored.ReconcileInterruptedJobs();
            var status = await restored.GetStatusAsync(submit.JobId!.Value, default);
            Assert.Equal("fill", status.Execution!.Fields["source_preparation_error"]!["framing_mode"]!.GetValue<string>());
        }
        private sealed class Http(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
        { protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) => send(request, ct); }
        private static VideoJobManager Manager(VideoFramingQuoteTests.Rig rig, IVideoJobLedger ledger) => new(rig.Coordinator.Registry,
            new ArtifactOnlyVideoMediaResolver(rig.Store, rig.Resources), ledger, new VideoCostEstimator(), rig.Store, new FakeVideoJobClock(), null,
            TimeSpan.FromMilliseconds(1), 2, null, coordinator: rig.Coordinator, routeQuotes: rig.Quotes);
        private static async Task Limit(Task task) { Assert.Same(task, await Task.WhenAny(task, Task.Delay(8000))); await task; }
        private static TaskCompletionSource<bool> Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task Dispatch_PreviewEqualsActualGoogleInlineAndFalUploadBytes(bool fal)
        {
            byte[]? sent = null; int generations = 0;
            var http = new Http(async (message, ct) => {
                if (message.RequestUri!.Host == "rest.fal.ai") return FalVeoQueueAdapterTests.Http.Json(200, "{\"upload_url\":\"https://v3.fal.media/upload\",\"file_url\":\"https://v3.fal.media/files/source.png\"}");
                if (message.RequestUri.Host == "v3.fal.media") { sent = await message.Content!.ReadAsByteArrayAsync(); return FalVeoQueueAdapterTests.Http.Json(200, "{}"); }
                if (message.Method == HttpMethod.Post && message.RequestUri.AbsolutePath.Contains("predictLongRunning"))
                { var body = JsonNode.Parse(await message.Content!.ReadAsStringAsync())!; sent = Convert.FromBase64String(body["instances"]![0]!["image"]!["bytesBase64Encoded"]!.GetValue<string>()); generations++; return FalVeoQueueAdapterTests.Http.Json(200, "{\"name\":\"operations/framed\"}"); }
                if (message.Method == HttpMethod.Post && message.RequestUri.Host == "queue.fal.run") { generations++; return FalVeoQueueAdapterTests.Http.Json(200, FalVeoQueueAdapterTests.Accepted); }
                return FalVeoQueueAdapterTests.Http.Json(500, "{}");
            });
            var catalog = FalVeoCompatibilityTests.ActiveCatalog(); var client = new HttpClient(http);
            var google = new VeoProvider(() => "test-only", new VeoClient(client));
            var falProvider = new FalVideoProvider(() => "test-only", new FalApiClient(client), null, catalog);
            using var rig = new VideoFramingQuoteTests.Rig(google, falProvider, new VideoRouteQuoteTests.Secrets { Google = fal ? null : "test-only" });
            var preview = await rig.Preparation.PreviewAsync(new(rig.Intent.Request.Model, VideoMode.I2V, new[] { new VideoFramingSourceSlot("start_frame", rig.Source) }, "1080p", "16:9"), default);
            var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            var ledger = new JsonlVideoJobLedger(Path.Combine(rig.Root, "ledger.jsonl")); using var manager = Manager(rig, ledger);
            var done = Signal(); manager.AfterRunForTests = _ => done.TrySetResult(true);
            var submitted = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(rig.Intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd), default);
            Assert.Null(submitted.GenerationError); Assert.NotNull(submitted.JobId); await Limit(done.Task);
            Assert.True(sent != null, ledger.ReadAll().Records.Single().Error?.Message ?? "No payload captured");
            using var actual = VideoFrozenBuffer.CopyOf(sent!, new VideoBufferBudget());
            Assert.Equal(preview.Fit!.Slots[0].Sha256, actual.Sha256); Assert.Equal(1, generations);
            var record = ledger.ReadAll().Records.Single(); Assert.Null(VideoExecutionSnapshot.Read(record).Error);
            Assert.Equal(actual.Sha256, record.Extensions!["video_execution"]!["prepared_media"]![0]!["sha256"]!.GetValue<string>());
            Assert.Equal(0, rig.Resources.ActiveBundles);
        }
        [Fact]
        public async Task Dispatch_DurableIntentRestoresUnknown_AndCancellationKeepsLateConsumerPinned()
        {
            var entered = Signal(); var release = Signal(); int sends = 0;
            var http = new Http(async (message, ct) => {
                if (message.Method == HttpMethod.Post && message.RequestUri!.AbsolutePath.Contains("predictLongRunning"))
                { await message.Content!.ReadAsStringAsync(); Interlocked.Increment(ref sends); entered.SetResult(true); await release.Task; return FalVeoQueueAdapterTests.Http.Json(200, "{\"name\":\"operations/late-framed\"}"); }
                return FalVeoQueueAdapterTests.Http.Json(500, "{}");
            });
            using var rig = new VideoFramingQuoteTests.Rig(new VeoProvider(() => "test-only", new VeoClient(new HttpClient(http))));
            var quote = (await rig.Quotes.QuoteAsync(rig.Intent, default)).Quote!;
            var ledger = new FakeVideoJobLedger(); using var manager = Manager(rig, ledger);
            var done = Signal(); manager.AfterRunForTests = _ => done.TrySetResult(true);
            try
            {
                var submit = await ((IVideoConfirmedJobManager)manager).SubmitConfirmedAsync(rig.Intent, new(quote.EstimateFingerprint, quote.MaximumEstimatedCostUsd), default);
                await Limit(entered.Task);
                var captured = ledger.ReadAll().Records.Single(); var data = VideoExecutionSnapshot.Read(captured).Snapshot!.Data;
                Assert.Equal("intent_recorded", data["attempts"]![0]!["dispatch_state"]!.GetValue<string>()); Assert.False(data["attempts"]![0]!["generation_dispatch_attempted"]!.GetValue<bool>());
                var restoredLedger = new JsonlVideoJobLedger(Path.Combine(rig.Root, "restored.jsonl")); restoredLedger.Append(captured);
                using (var restored = Manager(rig, restoredLedger)) { restored.ReconcileInterruptedJobs(); Assert.Equal(VideoJobState.Interrupted, restoredLedger.ReadAll().Records.Single().State); Assert.Equal(1, sends); }
                var corrupt = (JsonObject)data.DeepClone(); corrupt["source_preparation"]!["slots"]![0]!["recipe"]!["offset_x"] = 999;
                Assert.NotNull(VideoExecutionSnapshot.Read(VideoExecutionSnapshot.Write(captured, new(1, corrupt))).Error);
                var cancel = await manager.CancelAsync(submit.JobId!.Value, default); await Limit(done.Task);
                Assert.Equal(VideoJobState.Interrupted, cancel.State); Assert.Equal("user", cancel.Execution!.Fields["first_stop_reason"]!.GetValue<string>()); Assert.Equal(1, rig.Resources.ActiveBundles);
                rig.Cache.Dispose(); Assert.True(rig.Cache.RetainedBytes > 0);
            }
            finally { release.TrySetResult(true); }
            await Limit(Task.Run(async () => { while (rig.Resources.ActiveBundles != 0 || rig.Cache.RetainedBytes != 0) await Task.Delay(1); }));
            Assert.Equal(1, sends);
        }
    }
}
