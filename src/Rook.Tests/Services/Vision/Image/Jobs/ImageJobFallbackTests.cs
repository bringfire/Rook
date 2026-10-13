using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobFallbackTests
    {
        private static ImageJobManager Manager(ImageFallbackFixture f, IImageJobLedger? ledger = null,
            Func<TimeSpan, CancellationTokenSource>? timer = null, int slots = 2) =>
            new(f.Registry, f.Store, null, null, null, slots, new ImageArtifactMaterializer(f.DownloadHttp),
                null, ledger ?? new JsonlImageJobLedger(Path.Combine(f.Root, "ledger.jsonl")), f.Executor, timer);
        internal static async Task<ImageJobStatusResult> Terminal(ImageJobManager manager, Guid id)
        {
            for (var i = 0; i < 500; i++)
            {
                var result = await manager.GetStatusAsync(id, CancellationToken.None);
                if (result.State is ImageJobState.Complete or ImageJobState.Cancelled or ImageJobState.Interrupted or ImageJobState.Error)
                    return result;
                await Task.Delay(10);
            }
            throw new TimeoutException("Image job did not settle.");
        }
        internal static async Task Settled(ImageJobManager manager)
        {
            var field = typeof(ImageJobManager).GetField("_runningJobs", BindingFlags.Instance | BindingFlags.NonPublic)!;
            for (var i = 0; i < 500; i++)
            {
                var value = field.GetValue(manager)!;
                if ((int)value.GetType().GetProperty("Count")!.GetValue(value)! == 0) return;
                await Task.Delay(10);
            }
            throw new TimeoutException("Worker did not settle.");
        }
        private static TaskCompletionSource<bool> Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
        private static async Task Bounded(Task task)
        { Assert.Same(task, await Task.WhenAny(task, Task.Delay(5000))); await task; }

        [Theory]
        [InlineData(GeminiImageCapabilities.NanoBanana2, "fal-ai/nano-banana-2")]
        [InlineData(GeminiImageCapabilities.NanoBananaPro, "fal-ai/nano-banana-pro")]
        [InlineData("fal-ai/nano-banana-2", "fal-ai/nano-banana-2")]
        public async Task EffectiveRouteSurvivesRestartAndArtifactKeepsParents(string requested, string effective)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var manager = Manager(f);
            var start = f.Start(requested);
            var submit = await manager.SubmitAsync(start, CancellationToken.None);
            var status = await Terminal(manager, submit.JobId!.Value);
            await Settled(manager);
            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Equal("fal", status.Provider); Assert.Equal(effective, status.Model);
            using var fresh = Manager(f);
            var restored = await fresh.GetStatusAsync(submit.JobId.Value, CancellationToken.None);
            Assert.Equal(status.Routing, restored.Routing);
            Assert.Equal(ImageFalDispatchState.Attempted, restored.FalDispatchState);
            var artifact = f.Store.Get(restored.ResultArtifactId!.Value)!;
            Assert.Equal(start.ParentArtifactIds, artifact.ParentIds);
            Assert.Equal(effective, artifact.Metadata["model"]!.GetValue<string>());
            Assert.Equal("fal", artifact.Metadata["provider"]!.GetValue<string>());
            Assert.Equal(requested.StartsWith("gemini"), status.Routing?.Route != null);
        }

        [Theory]
        [InlineData(GeminiImageCapabilities.NanoBanana2)]
        [InlineData("fal-ai/nano-banana-2")]
        public async Task HeldFalResponsePhysicalLedgerRestoresUnknownSubmission(string requested)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var restoredFixture = new ImageFallbackFixture();
            var entered = Signal(); var release = Signal();
            f.FalHttp.OnSendAsync = async (_, _) =>
            { entered.TrySetResult(true); await release.Task; return ImageFallbackFixture.Json(200,
                "{\"images\":[{\"url\":\"https://fal.media/result.png\"}]}"); };
            var ledger = new JsonlImageJobLedger(Path.Combine(f.Root, "ledger.jsonl"));
            using var manager = Manager(f, ledger);
            var submit = await manager.SubmitAsync(f.Start(requested), CancellationToken.None);
            try
            {
                await Bounded(entered.Task);
                var snapshotPath = Path.Combine(restoredFixture.Root, "crash.jsonl");
                File.Copy(ledger.FilePath, snapshotPath);
                var copied = new JsonlImageJobLedger(snapshotPath);
                var record = Assert.Single(copied.ReadAll().Records);
                Assert.Equal(ImageFalDispatchState.IntentRecorded, record.FalDispatchState);
                Assert.False(record.ImageRoute?.GenerationDispatchAttempted ?? false);
                Assert.Equal(requested.StartsWith("gemini"), record.ImageRoute != null);
                using var fresh = Manager(restoredFixture, copied);
                fresh.ReconcileInterruptedJobs();
                var restored = await fresh.GetStatusAsync(submit.JobId!.Value, CancellationToken.None);
                Assert.Equal(ImageJobState.Interrupted, restored.State);
                Assert.Equal("fal", restored.Provider);
                Assert.Equal(ImageFalDispatchState.IntentRecorded, restored.FalDispatchState);
                Assert.Contains("submission outcome is unknown", restored.Error!.Message);
                Assert.False(restored.Error.Retryable);
                Assert.Empty(restoredFixture.FalHttp.Requests);
            }
            finally { release.TrySetResult(true); }
            await Terminal(manager, submit.JobId!.Value); await Settled(manager);
        }

        [Theory]
        [InlineData("google")]
        [InlineData("fal")]
        [InlineData("download")]
        public async Task OneDeadlineInterruptsHeldHttpWithoutPublishing(string stage)
        {
            using var f = new ImageFallbackFixture(geminiKey: stage == "google" ? "key" : null);
            var entered = Signal(); var release = Signal();
            var timer = new CancellationTokenSource(); var durations = new List<TimeSpan>();
            var handler = stage == "google" ? f.GoogleHttp : stage == "fal" ? f.FalHttp : f.DownloadHttp;
            var original = handler.OnSendAsync!;
            handler.OnSendAsync = async (r, ct) => { entered.TrySetResult(true); await release.Task; return await original(r, ct); };
            using var manager = Manager(f, timer: duration => { durations.Add(duration); return timer; });
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            await Bounded(entered.Task);
            timer.Cancel();
            var status = await Terminal(manager, submit.JobId!.Value);
            release.TrySetResult(true); await Settled(manager);
            Assert.Equal(ImageJobState.Interrupted, status.State);
            Assert.Equal("Image generation execution deadline exceeded (180s).", status.Error!.Message);
            Assert.False(status.Error.Retryable);
            Assert.Equal(new[] { TimeSpan.FromSeconds(180) }, durations);
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
            if (stage == "google") Assert.Empty(f.FalHttp.Requests);
            else Assert.Equal(ImageFalDispatchState.Attempted, status.FalDispatchState);
        }

        [Fact]
        public async Task QueueWaitDoesNotStartTimerAndSubmitTokenIsIndependent()
        {
            using var f = new ImageFallbackFixture();
            var entered = Signal(); var release = Signal();
            var original = f.GoogleHttp.OnSendAsync!; var sends = 0;
            f.GoogleHttp.OnSendAsync = async (r, ct) =>
            { if (Interlocked.Increment(ref sends) == 1) { entered.TrySetResult(true); await release.Task; } return await original(r, ct); };
            var timers = 0;
            using var manager = Manager(f, timer: _ => { Interlocked.Increment(ref timers); return new CancellationTokenSource(); }, slots: 1);
            var first = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            await Bounded(entered.Task);
            using var acceptedToken = new CancellationTokenSource();
            var second = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), acceptedToken.Token);
            acceptedToken.Cancel();
            Assert.Equal(1, timers);
            Assert.Equal(ImageJobState.Queued, (await manager.GetStatusAsync(second.JobId!.Value, CancellationToken.None)).State);
            release.TrySetResult(true);
            Assert.Equal(ImageJobState.Complete, (await Terminal(manager, first.JobId!.Value)).State);
            Assert.Equal(ImageJobState.Complete, (await Terminal(manager, second.JobId!.Value)).State);
            await Settled(manager); Assert.Equal(2, timers);
        }

        [Fact]
        public async Task FailedIntentPersistenceSendsNoFalRequest()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var ledger = new FakeImageJobLedger { BeforeAppend = r =>
            { if (r.FalDispatchState == ImageFalDispatchState.IntentRecorded) throw new IOException("intent blocked"); } };
            using var manager = Manager(f, ledger);
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            var status = await Terminal(manager, submit.JobId!.Value); await Settled(manager);
            Assert.Equal(ImageJobState.Error, status.State);
            Assert.Equal("fal", status.Provider);
            Assert.Empty(f.FalHttp.Requests);
            Assert.NotEqual(ImageFalDispatchState.IntentRecorded, Assert.Single(ledger.ReadAll().Records).FalDispatchState);
        }

        [Fact]
        public async Task CancelWhileIntentAppendHeldRetainsIntentAndNeverSends()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var entered = new ManualResetEventSlim(); using var release = new ManualResetEventSlim();
            var ledger = new FakeImageJobLedger { BeforeAppend = r =>
            { if (r.FalDispatchState == ImageFalDispatchState.IntentRecorded && r.State == ImageJobState.Submitting)
                { entered.Set(); Assert.True(release.Wait(5000)); } } };
            using var manager = Manager(f, ledger);
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            Assert.True(entered.Wait(5000));
            var cancel = Task.Run(() => manager.CancelAsync(submit.JobId!.Value, CancellationToken.None));
            Assert.NotSame(cancel, await Task.WhenAny(cancel, Task.Delay(50)));
            release.Set();
            Assert.Equal(ImageJobState.Cancelled, (await cancel).State);
            await Settled(manager);
            var durable = Assert.Single(ledger.ReadAll().Records);
            Assert.Equal(ImageJobState.Cancelled, durable.State);
            Assert.Equal(ImageFalDispatchState.IntentRecorded, durable.FalDispatchState);
            Assert.False(durable.ImageRoute!.GenerationDispatchAttempted);
            Assert.Empty(f.FalHttp.Requests);
        }

        [Fact]
        public async Task ExpiryDuringRoutePreparationDoesNotResetBudgetOrSend()
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var timer = new CancellationTokenSource(); var starts = 0;
            var ledger = new FakeImageJobLedger { BeforeAppend = r =>
            { if (r.ImageRoute != null && r.State == ImageJobState.Submitting) timer.Cancel(); } };
            using var manager = Manager(f, ledger, _ => { starts++; return timer; });
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            var status = await Terminal(manager, submit.JobId!.Value); await Settled(manager);
            Assert.Equal(1, starts);
            Assert.Equal(ImageJobState.Interrupted, status.State);
            Assert.False(status.Routing!.Route!.GenerationDispatchAttempted);
            Assert.Equal(ImageFalDispatchState.NotStarted, status.FalDispatchState);
            Assert.Empty(f.FalHttp.Requests);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task DeadlineOnEitherSideOfCompletionAdmissionRespectsWinner(bool admitted)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var timer = new CancellationTokenSource();
            var ledger = new FakeImageJobLedger();
            using var manager = Manager(f, ledger, _ => timer);
            if (admitted) ledger.BeforeAppend = r => { if (r.State == ImageJobState.Complete) timer.Cancel(); };
            else manager.BeforeCompleteTransitionForTests = _ => timer.Cancel();
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            var status = await Terminal(manager, submit.JobId!.Value); await Settled(manager);
            Assert.Equal(admitted ? ImageJobState.Complete : ImageJobState.Interrupted, status.State);
            Assert.Equal(admitted ? 1 : 0, f.Store.List().Count(a => a.Kind == "generated_image"));
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task UserAndShutdownStopsHaveDistinctProvenance(bool shutdown)
        {
            using var f = new ImageFallbackFixture();
            var entered = Signal(); var release = Signal(); var original = f.FalHttp.OnSendAsync!;
            f.FalHttp.OnSendAsync = async (r, ct) => { entered.TrySetResult(true); await release.Task; return await original(r, ct); };
            using var manager = Manager(f);
            var submit = await manager.SubmitAsync(f.Start("fal-ai/nano-banana-2"), CancellationToken.None);
            await Bounded(entered.Task);
            if (shutdown) manager.Dispose(); else await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);
            var status = await Terminal(manager, submit.JobId!.Value);
            release.TrySetResult(true); await Settled(manager);
            Assert.True(status.State == (shutdown ? ImageJobState.Interrupted : ImageJobState.Cancelled),
                status.State + ": " + status.Error?.Message);
            Assert.Null(status.Routing?.Route);
            Assert.Equal(ImageFalDispatchState.Attempted, status.FalDispatchState);
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
        }

        [Theory]
        [InlineData(GeminiImageCapabilities.NanoBanana2, true)]
        [InlineData(GeminiImageCapabilities.NanoBananaPro, true)]
        [InlineData("fal-ai/nano-banana-2", true)]
        [InlineData("fal-ai/nano-banana-pro", true)]
        [InlineData(GeminiImageCapabilities.NanoBanana2, false)]
        [InlineData(GeminiImageCapabilities.NanoBananaPro, false)]
        [InlineData("fal-ai/nano-banana-2", false)]
        [InlineData("fal-ai/nano-banana-pro", false)]
        public async Task QueuedStopsKeepFirstReasonAcrossCancelAndShutdown(string requested, bool shutdownFirst)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            var ledger = new JsonlImageJobLedger(Path.Combine(f.Root, "ledger.jsonl"));
            var timers = 0;
            using var manager = Manager(f, ledger, _ =>
            { Interlocked.Increment(ref timers); return new CancellationTokenSource(); }, slots: 1);
            // Occupy the slot without dispatching another job, so this job remains entirely queued.
            var slots = (SemaphoreSlim)typeof(ImageJobManager)
                .GetField("_concurrency", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(manager)!;
            await slots.WaitAsync();
            var submit = await manager.SubmitAsync(f.Start(requested), CancellationToken.None);
            var id = submit.JobId!.Value;
            Assert.Equal(ImageJobState.Queued, (await manager.GetStatusAsync(id, CancellationToken.None)).State);
            using var releaseWorker = new ManualResetEventSlim();
            var workerEntered = Signal();
            var transitions = 0;
            if (shutdownFirst) manager.BeforeTransitionGateForTests = _ =>
            {
                if (Interlocked.Increment(ref transitions) != 1) return;
                workerEntered.TrySetResult(true);
                Assert.True(releaseWorker.Wait(5000), "Queued worker terminal commit was not released.");
            };
            Task shutdown = Task.CompletedTask;
            var expectedState = shutdownFirst ? ImageJobState.Interrupted : ImageJobState.Cancelled;
            var expectedCode = shutdownFirst ? GenerationErrorCode.Interrupted : GenerationErrorCode.Cancelled;
            var expectedMessage = shutdownFirst ? "Image job interrupted by plugin shutdown." : "Job cancelled.";
            try
            {
                if (shutdownFirst)
                {
                    // Cancellation callbacks may run the worker inline; signal from a separate task.
                    shutdown = Task.Run(() => manager.Dispose());
                    await Bounded(workerEntered.Task);
                    Assert.Equal(ImageJobState.Queued, (await manager.GetStatusAsync(id, CancellationToken.None)).State);
                    Assert.Equal(expectedState, (await manager.CancelAsync(id, CancellationToken.None)).State);
                }
                else
                {
                    Assert.Equal(expectedState, (await manager.CancelAsync(id, CancellationToken.None)).State);
                    shutdown = Task.Run(() => manager.Dispose());
                }
            }
            finally
            {
                releaseWorker.Set();
                await Bounded(shutdown);
                await Settled(manager);
            }
            var status = await manager.GetStatusAsync(id, CancellationToken.None);
            using var fresh = Manager(f, new JsonlImageJobLedger(ledger.FilePath));
            var restored = await fresh.GetStatusAsync(id, CancellationToken.None);
            foreach (var result in new[] { status, restored })
            {
                Assert.Equal(expectedState, result.State);
                Assert.Equal(expectedCode, result.Error!.Code);
                Assert.Equal(expectedMessage, result.Error.Message);
                Assert.False(result.Error.Retryable);
                Assert.Equal(requested, result.Model);
                Assert.Null(result.Routing);
                Assert.Equal(ImageFalDispatchState.NotStarted, result.FalDispatchState);
                Assert.Null(result.ResultArtifactId);
            }
            var durable = Assert.Single(ledger.ReadAll().Records);
            Assert.Equal(expectedState, durable.State); Assert.Equal(expectedMessage, durable.Error!.Message);
            Assert.Equal(0, timers);
            Assert.Empty(f.GoogleHttp.Requests); Assert.Empty(f.FalHttp.Requests); Assert.Empty(f.DownloadHttp.Requests);
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
        }

        [Theory]
        [InlineData(false, false)]
        [InlineData(false, true)]
        [InlineData(true, false)]
        [InlineData(true, true)]
        public async Task LateCancelPreservesObservedStopWhileWorkerAwaitsTerminalCommit(bool shutdown, bool fallback)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var fal = f.HoldNextResponse(f.FalHttp);
            using var releaseCommit = new ManualResetEventSlim();
            var commitEntered = Signal();
            var timer = new CancellationTokenSource();
            var ledger = new JsonlImageJobLedger(Path.Combine(f.Root, "ledger.jsonl"));
            using var manager = Manager(f, ledger, _ => timer);
            var requested = fallback ? GeminiImageCapabilities.NanoBanana2 : "fal-ai/nano-banana-2";
            var submit = await manager.SubmitAsync(f.Start(requested), CancellationToken.None);
            await Bounded(fal.Entered);
            var commits = 0;
            manager.BeforeTransitionGateForTests = _ =>
            {
                if (Interlocked.Increment(ref commits) != 1) return;
                commitEntered.TrySetResult(true);
                Assert.True(releaseCommit.Wait(5000), "Worker terminal commit was not released.");
            };
            var expectedMessage = shutdown ? "Image job interrupted by plugin shutdown."
                : "Image generation execution deadline exceeded (180s).";
            try
            {
                if (shutdown) manager.Dispose(); else timer.Cancel();
                await Bounded(commitEntered.Task);
                Assert.Equal(ImageJobState.Submitting,
                    (await manager.GetStatusAsync(submit.JobId!.Value, CancellationToken.None)).State);
                // Cancel must preserve the stop already observed by the worker, even when it wins the commit.
                var cancel = await manager.CancelAsync(submit.JobId!.Value, CancellationToken.None);
                Assert.Equal(ImageJobState.Interrupted, cancel.State);
            }
            finally { releaseCommit.Set(); fal.Release(); }
            await Settled(manager);
            var status = await Terminal(manager, submit.JobId!.Value);
            var durable = Assert.Single(ledger.ReadAll().Records);
            using var fresh = Manager(f, new JsonlImageJobLedger(ledger.FilePath));
            var restored = await fresh.GetStatusAsync(submit.JobId.Value, CancellationToken.None);
            foreach (var result in new[] { status, restored })
            {
                Assert.Equal(ImageJobState.Interrupted, result.State);
                Assert.Equal(GenerationErrorCode.Interrupted, result.Error!.Code);
                Assert.Equal(expectedMessage, result.Error.Message);
                Assert.False(result.Error.Retryable);
                Assert.Equal("fal", result.Provider);
                Assert.Equal(ImageFalDispatchState.Attempted, result.FalDispatchState);
                Assert.Equal(fallback, result.Routing?.Route != null);
                if (fallback) Assert.True(result.Routing!.Route!.GenerationDispatchAttempted);
                Assert.Null(result.ResultArtifactId);
            }
            Assert.Equal(ImageJobState.Interrupted, durable.State);
            Assert.Equal(expectedMessage, durable.Error!.Message);
            Assert.Single(f.FalHttp.Requests);
            Assert.DoesNotContain(f.Store.List(), a => a.Kind == "generated_image");
        }

        [Fact]
        public async Task ConcurrentJobsKeepIndependentExecutionContext()
        {
            using var f = new ImageFallbackFixture();
            var original = f.GoogleHttp.OnSendAsync!;
            f.GoogleHttp.OnSendAsync = (r, ct) => r.Content!.ReadAsStringAsync().Result.Contains("fallback job")
                ? Task.FromResult(ImageFallbackFixture.Json(401, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}"))
                : original(r, ct);
            using var manager = Manager(f);
            var ordinary = f.Start(GeminiImageCapabilities.NanoBanana2);
            var fallback = new ImageJobStartRequest(ordinary.Request.With(prompt: "fallback job"),
                ordinary.ResolvedMedia, ordinary.ParentArtifactIds);
            var a = await manager.SubmitAsync(ordinary, CancellationToken.None);
            var b = await manager.SubmitAsync(fallback, CancellationToken.None);
            var direct = await Terminal(manager, a.JobId!.Value);
            var switched = await Terminal(manager, b.JobId!.Value); await Settled(manager);
            Assert.Null(direct.Routing); Assert.Equal("gemini", direct.Provider);
            Assert.Equal("fal", switched.Routing!.Route!.EffectiveProvider);
            Assert.Single(f.FalHttp.Requests);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task ConcurrentHeldRoutesStopOnlyTheirOwnJob(bool deadline)
        {
            using var f = new ImageFallbackFixture();
            var original = f.GoogleHttp.OnSendAsync!;
            f.GoogleHttp.OnSendAsync = (r, ct) => r.Content!.ReadAsStringAsync().Result.Contains("fallback job")
                ? Task.FromResult(ImageFallbackFixture.Json(401, "{\"error\":{\"status\":\"UNAUTHENTICATED\"}}"))
                : original(r, ct);
            using var google = f.HoldNextResponse(f.GoogleHttp);
            using var fal = f.HoldNextResponse(f.FalHttp);
            var timers = new System.Collections.Concurrent.ConcurrentQueue<CancellationTokenSource>();
            using var manager = Manager(f, timer: _ => { var timer = new CancellationTokenSource(); timers.Enqueue(timer); return timer; });
            var direct = f.Start(GeminiImageCapabilities.NanoBanana2);
            var switched = new ImageJobStartRequest(direct.Request.With(prompt: "fallback job"), direct.ResolvedMedia, direct.ParentArtifactIds);
            var a = await manager.SubmitAsync(direct, CancellationToken.None);
            await Bounded(google.Entered);
            var b = await manager.SubmitAsync(switched, CancellationToken.None);
            await Bounded(fal.Entered);
            var sources = timers.ToArray(); Assert.Equal(2, sources.Length);
            try
            {
                if (deadline) sources[1].Cancel();
                else await manager.CancelAsync(b.JobId!.Value, CancellationToken.None);
                var stopped = await Terminal(manager, b.JobId!.Value);
                Assert.Equal(deadline ? ImageJobState.Interrupted : ImageJobState.Cancelled, stopped.State);
                Assert.Equal("fal", stopped.Provider); Assert.True(stopped.Routing!.Route!.GenerationDispatchAttempted);
                Assert.Equal(ImageJobState.Submitting, (await manager.GetStatusAsync(a.JobId!.Value, CancellationToken.None)).State);
                Assert.False(sources[0].IsCancellationRequested);
                google.Release();
                var completed = await Terminal(manager, a.JobId.Value);
                Assert.Equal(ImageJobState.Complete, completed.State);
                Assert.Equal("gemini", completed.Provider); Assert.Null(completed.Routing);
            }
            finally { google.Release(); fal.Release(); }
            await Settled(manager);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public async Task CancellationOnEitherSideOfRouteCommitPreventsFal(bool appendStarted)
        {
            using var f = new ImageFallbackFixture(geminiKey: null);
            using var entered = new ManualResetEventSlim(); using var release = new ManualResetEventSlim();
            var ledger = new FakeImageJobLedger();
            using var manager = Manager(f, ledger);
            if (appendStarted) ledger.BeforeAppend = r =>
            { if (r.ImageRoute != null && r.State == ImageJobState.Submitting) { entered.Set(); Assert.True(release.Wait(5000)); } };
            else
            {
                var hits = 0;
                manager.BeforeTransitionGateForTests = _ =>
                { if (Interlocked.Increment(ref hits) == 2) { entered.Set(); Assert.True(release.Wait(5000)); } };
            }
            var submit = await manager.SubmitAsync(f.Start(GeminiImageCapabilities.NanoBanana2), CancellationToken.None);
            Assert.True(entered.Wait(5000));
            var cancel = Task.Run(() => manager.CancelAsync(submit.JobId!.Value, CancellationToken.None));
            if (appendStarted) Assert.NotSame(cancel, await Task.WhenAny(cancel, Task.Delay(50)));
            else await Bounded(cancel);
            release.Set(); await cancel; await Settled(manager);
            Assert.Equal(ImageJobState.Cancelled, Assert.Single(ledger.ReadAll().Records).State);
            Assert.Empty(f.FalHttp.Requests);
        }
    }
}
