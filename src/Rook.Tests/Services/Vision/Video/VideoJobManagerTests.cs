using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoJobManagerTests : IDisposable
    {
        private readonly string _artifactRoot;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeVideoJobLedger _ledger = new();
        private readonly FakeVideoJobClock _clock = new();
        private readonly FakeVideoJobIdGenerator _idGen = new();
        private readonly FakeVideoProvider _provider = new();
        private readonly FakeVideoMediaResolver _resolver = new();
        private readonly VideoCapabilities _catalog = VideoCapabilities.Default;
        private readonly VeoCostEstimator _estimator;

        public VideoJobManagerTests()
        {
            _artifactRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-mgr-test-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(_artifactRoot);
            _estimator = new VeoCostEstimator(_catalog);
        }

        public void Dispose()
        {
            if (Directory.Exists(_artifactRoot))
                Directory.Delete(_artifactRoot, recursive: true);
        }

        private VideoJobManager Manager(TimeSpan? pollInterval = null) =>
            new(
                provider: _provider,
                mediaResolver: _resolver,
                ledger: _ledger,
                catalog: _catalog,
                estimator: _estimator,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGen,
                pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(5));

        private static VideoGenerationRequest T2vRequest() => new(
            Model: "veo-3.1-lite-generate-preview",
            Mode: VideoMode.T2V,
            DurationSeconds: 8,
            Resolution: "720p",
            AspectRatio: "16:9",
            Prompt: "a clip",
            StartFrame: null,
            EndFrame: null,
            ReferenceFrames: null,
            Seed: null,
            PersonGeneration: PersonGenerationPolicy.AllowAll,
            NumberOfVideos: 1);

        private static byte[] FakeMp4 => new byte[] { 0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70 };

        // Helper: poll the manager until the job reaches a terminal state
        // or the deadline passes. Returns the final status.
        private async Task<JobStatusResult> WaitForTerminalAsync(
            VideoJobManager mgr, Guid jobId,
            TimeSpan? deadline = null)
        {
            var stop = DateTime.UtcNow + (deadline ?? TimeSpan.FromSeconds(5));
            JobStatusResult? last = null;
            while (DateTime.UtcNow < stop)
            {
                last = await mgr.GetStatusAsync(jobId, CancellationToken.None);
                if (IsTerminal(last.State)) return last;
                await Task.Delay(10);
            }
            return last ?? throw new TimeoutException("Never observed any status.");
        }

        private static bool IsTerminal(VideoJobState s) =>
            s is VideoJobState.Complete
              or VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;

        // ─── Submit happy path ────────────────────────────────────────

        [Fact]
        public async Task Submit_returns_jobId_immediately_with_Queued_state()
        {
            var preMintedJobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(preMintedJobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            var submit = await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            Assert.Equal(preMintedJobId, submit.JobId);
            Assert.Equal(VideoJobState.Queued, submit.State);
            Assert.Null(submit.Error);
        }

        [Fact]
        public async Task Initial_ledger_record_has_null_provider_job_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Block provider.SubmitAsync so we can observe initial state
            // before the background task transitions it.
            var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            _provider.OnSubmit = (_, _) =>
            {
                gate.Task.GetAwaiter().GetResult();
                return ProviderSubmitResult.Ok("op-123");
            };
            _provider.OnGetStatus = _ => ProviderStatusResult.Complete("https://veo/result/x");
            _provider.OnFetchResult = (_, _) => ProviderFetchResult.Ok(FakeMp4, "video/mp4");

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            // The first record (Queued) is appended synchronously
            // during SubmitAsync and is observable before we release
            // the gate.
            var initial = _ledger.AllRecords.First(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Queued, initial.State);
            Assert.Null(initial.ProviderJobId);
            Assert.Null(initial.ProviderResultToken);
            Assert.Null(initial.ResultArtifactId);

            gate.SetResult(true);
            await WaitForTerminalAsync(mgr, jobId);
        }

        [Fact]
        public async Task ProviderJobId_appears_after_provider_submit_returns()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            // At least one record after the initial Queued must have
            // ProviderJobId set — that's the post-submit transition.
            var withProvId = _ledger.AllRecords
                .Where(r => r.JobId == jobId && r.ProviderJobId is not null)
                .ToList();

            Assert.NotEmpty(withProvId);
            Assert.All(withProvId, r => Assert.Equal("op-123", r.ProviderJobId));
        }

        [Fact]
        public async Task ProviderResultToken_appears_after_provider_complete()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var withToken = _ledger.AllRecords
                .Where(r => r.JobId == jobId && r.ProviderResultToken is not null)
                .ToList();

            Assert.NotEmpty(withToken);
            Assert.All(withToken, r => Assert.Equal("https://veo/result/x", r.ProviderResultToken));
        }

        [Fact]
        public async Task Happy_path_reaches_Complete_with_artifact_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);

            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Equal("generated_video", artifact!.Kind);
            Assert.Single(artifact.Files);
            Assert.Equal("video", artifact.Files[0].Role);
        }

        // ─── Validation / estimator / resolver failures ──────────────

        [Fact]
        public async Task Submit_with_invalid_model_returns_Fail_no_ledger_write()
        {
            var mgr = Manager();
            var bad = T2vRequest() with { Model = "veo-9000" };

            var result = await mgr.SubmitAsync(bad, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Null(result.JobId);
            Assert.Empty(_ledger.AllRecords);
        }

        [Fact]
        public async Task Submit_with_path_media_ref_returns_InvalidRequest()
        {
            // Resolver throws NotSupportedException for Path-kind refs;
            // manager translates to InvalidRequest before any ledger write.
            _resolver.OnResolve = mediaRef =>
                mediaRef.Kind == VideoMediaRefKind.Path
                    ? throw new NotSupportedException("Path unsupported in V1b")
                    : new ResolvedVideoMedia(new byte[] { 1 }, "image/png", "fake");

            var mgr = Manager();
            var req = T2vRequest() with
            {
                Mode = VideoMode.I2V,
                Prompt = null,
                StartFrame = VideoMediaRef.ForPath(@"C:\nope.png"),
                PersonGeneration = PersonGenerationPolicy.AllowAdult,
                Model = "veo-3.1-generate-preview",
            };

            var result = await mgr.SubmitAsync(req, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Empty(_ledger.AllRecords);
        }

        // ─── Provider-side errors ────────────────────────────────────

        [Fact]
        public async Task Provider_submit_failure_transitions_to_Error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => ProviderSubmitResult.Fail(new VideoJobError(
                Code: VideoErrorCode.DependencyUnavailable,
                Message: "auth bad",
                Retryable: false));

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Error, final.State);
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, final.Error!.Code);
        }

        // ─── Cancel ──────────────────────────────────────────────────

        [Fact]
        public async Task Cancel_unknown_jobId_returns_Fail()
        {
            var mgr = Manager();

            var result = await mgr.CancelAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        [Fact]
        public async Task Cancel_in_flight_calls_provider_cancel_with_persisted_provider_job_id()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Provider submits ok, polls forever (so we can cancel)
            _provider.OnSubmit = (_, _) => ProviderSubmitResult.Ok("op-cancel-test");
            _provider.OnGetStatus = _ => ProviderStatusResult.InFlight(
                VideoJobState.Polling,
                new VideoJobProgress(Pct: 10, Stage: "polling", Message: null));

            string? cancelCalledWith = null;
            _provider.OnCancel = id =>
            {
                cancelCalledWith = id;
                return ProviderCancelResult.Ok(VideoJobState.Cancelled);
            };

            var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            // Wait until provider_job_id is persisted (post-submit).
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    break;
                await Task.Delay(10);
            }

            var cancel = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Cancelled, cancel.State);
            Assert.Equal("op-cancel-test", cancelCalledWith);
        }

        // ─── Reconcile (no auto-resume) ──────────────────────────────

        [Fact]
        public void Reconcile_marks_non_terminal_jobs_as_Interrupted()
        {
            // Pre-populate the ledger as if a prior session left a
            // job mid-flight. ReconcileInterruptedJobs should append
            // an Interrupted record without touching the provider.
            var jobId = Guid.NewGuid();
            var staleRecord = VideoJobRecordFactory.From(
                jobId, T2vRequest(), "veo",
                _estimator.Estimate(T2vRequest()).Estimate!,
                VideoJobState.Polling, _clock.UtcNow());
            staleRecord = VideoJobRecordFactory.WithState(
                staleRecord, VideoJobState.Polling, _clock.UtcNow(),
                providerJobId: "op-stale-123");
            _ledger.Append(staleRecord);

            // Track provider calls — should be NONE during reconcile.
            var providerCalls = 0;
            _provider.OnSubmit = (_, _) => { providerCalls++; return ProviderSubmitResult.Ok("x"); };
            _provider.OnGetStatus = _ => { providerCalls++; return ProviderStatusResult.InFlight(VideoJobState.Polling, null); };
            _provider.OnCancel = _ => { providerCalls++; return ProviderCancelResult.Ok(VideoJobState.Cancelled); };
            _provider.OnFetchResult = (_, _) => { providerCalls++; return ProviderFetchResult.Fail(new VideoJobError(VideoErrorCode.ExecutionFailed, "x", Retryable: false)); };

            var mgr = Manager();
            mgr.ReconcileInterruptedJobs();

            Assert.Equal(0, providerCalls);  // no auto-resume per v3.1 D4

            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Interrupted, latest.State);
            Assert.Equal("op-stale-123", latest.ProviderJobId);  // persisted for explicit cancel
            Assert.NotNull(latest.Error);
            Assert.Equal(VideoErrorCode.Interrupted, latest.Error!.Code);
        }

        [Fact]
        public void Reconcile_does_not_touch_terminal_jobs()
        {
            var jobId = Guid.NewGuid();
            var staleRecord = VideoJobRecordFactory.From(
                jobId, T2vRequest(), "veo",
                _estimator.Estimate(T2vRequest()).Estimate!,
                VideoJobState.Complete, _clock.UtcNow());
            _ledger.Append(staleRecord);

            var beforeCount = _ledger.AllRecords.Count;

            var mgr = Manager();
            mgr.ReconcileInterruptedJobs();

            // No new record appended — terminal state stays terminal.
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
        }

        // ─── FetchResult ──────────────────────────────────────────────

        [Fact]
        public async Task FetchResult_complete_job_returns_artifact_files()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var mgr = Manager();
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            var fetch = await mgr.FetchResultAsync(jobId, CancellationToken.None);

            Assert.Equal(VideoJobState.Complete, fetch.State);
            Assert.NotNull(fetch.ResultArtifactId);
            Assert.NotNull(fetch.Files);
            Assert.Single(fetch.Files!);
            Assert.Equal("video", fetch.Files![0].Role);
        }

        [Fact]
        public async Task FetchResult_unknown_job_returns_Fail()
        {
            var mgr = Manager();

            var result = await mgr.FetchResultAsync(Guid.NewGuid(), CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private void ConfigureProviderHappyPath()
        {
            _provider.OnSubmit = (_, _) => ProviderSubmitResult.Ok("op-123");
            _provider.OnGetStatus = _ => ProviderStatusResult.Complete("https://veo/result/x");
            _provider.OnFetchResult = (_, _) => ProviderFetchResult.Ok(FakeMp4, "video/mp4");
            _provider.OnCancel = _ => ProviderCancelResult.Ok(VideoJobState.Cancelled);
        }
    }

    // Tiny media resolver for tests: synchronous, configurable.
    internal sealed class FakeVideoMediaResolver : IVideoMediaResolver
    {
        public Func<VideoMediaRef, ResolvedVideoMedia>? OnResolve { get; set; }

        public Task<ResolvedVideoMedia> ResolveAsync(
            VideoMediaRef mediaRef, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var resolved = OnResolve?.Invoke(mediaRef)
                ?? new ResolvedVideoMedia(
                    bytes: new byte[] { 0x89, 0x50, 0x4E, 0x47 },
                    mimeType: "image/png",
                    sourceDescription: "fake");
            return Task.FromResult(resolved);
        }
    }
}
