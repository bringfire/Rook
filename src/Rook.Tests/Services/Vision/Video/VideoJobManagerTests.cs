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
        private readonly IVideoProviderRegistry _registry;
        private readonly VideoCostEstimator _estimator = new();
        private readonly ResolvedVideoModel _resolvedModel;

        public VideoJobManagerTests()
        {
            _artifactRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-mgr-test-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(_artifactRoot);
            _registry = TestVideoFixtures.RegistryWithVeo(_provider);
            _resolvedModel = TestVideoFixtures.VeoLiteResolved(_provider);
        }

        public void Dispose()
        {
            if (Directory.Exists(_artifactRoot))
                Directory.Delete(_artifactRoot, recursive: true);
        }

        private VideoJobManager Manager(TimeSpan? pollInterval = null) =>
            new(
                registry: _registry,
                mediaResolver: _resolver,
                ledger: _ledger,
                estimator: _estimator,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGen,
                pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(5));

        private VideoGenerationRequest T2vRequest() =>
            TestVideoFixtures.DefaultT2vRequest();

        private VideoCostEstimate EstimateFor(VideoGenerationRequest req) =>
            _estimator.Estimate(_resolvedModel, req).Estimate!;

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
                Options = new VeoOptions(PersonGenerationPolicy.AllowAdult),
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

        // ─── Codex round 6: cancel correctness invariants ────────────
        //
        // These pin the cost-leak prevention contract that v3.1 D4 +
        // V1b's `provider_job_id` persistence were designed to enforce:
        // Interrupted jobs must remain remote-cancellable, and the
        // manager must not claim cancellation when the provider rejects
        // the cancel.

        [Fact]
        public async Task Cancel_interrupted_job_calls_provider_cancel_with_persisted_id()
        {
            var jobId = Guid.NewGuid();
            // Pre-populate ledger with an Interrupted record carrying
            // provider_job_id (the post-Reconcile state).
            var prior = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Polling, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Polling, _clock.UtcNow(),
                providerJobId: "op-stale-456");
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                error: new VideoJobError(VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            string? cancelCalledWith = null;
            _provider.OnCancel = id =>
            {
                cancelCalledWith = id;
                return ProviderCancelResult.Ok(VideoJobState.Cancelled);
            };

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal("op-stale-456", cancelCalledWith);
            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);

            // Final ledger record is Cancelled with Cancelled error attached.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, latest.State);
            Assert.NotNull(latest.Error);
            Assert.Equal(VideoErrorCode.Cancelled, latest.Error!.Code);
            Assert.False(latest.Error.Retryable);
        }

        [Fact]
        public async Task Cancel_interrupted_job_when_provider_fails_returns_Fail_no_state_change()
        {
            var jobId = Guid.NewGuid();
            var prior = VideoJobRecordFactory.From(
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Interrupted, _clock.UtcNow());
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "op-stale-789",
                error: new VideoJobError(VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            _provider.OnCancel = _ => ProviderCancelResult.Fail(new VideoJobError(
                Code: VideoErrorCode.DependencyUnavailable,
                Message: "Veo cancel rate-limited",
                Retryable: true));

            var beforeCount = _ledger.AllRecords.Count;
            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            // CancelAsync surfaces the provider's failure to the caller.
            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.DependencyUnavailable, result.Error!.Code);
            // No new record appended — durable state stays Interrupted,
            // provider_job_id intact for the next retry.
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Interrupted, latest.State);
            Assert.Equal("op-stale-789", latest.ProviderJobId);
        }

        [Fact]
        public async Task Cancel_in_flight_when_provider_fails_returns_Fail_local_task_kept_running()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);

            // Provider submits ok, polls forever (so the local task
            // remains in-flight throughout the cancel attempt).
            _provider.OnSubmit = (_, _) => ProviderSubmitResult.Ok("op-keepalive");
            _provider.OnGetStatus = _ => ProviderStatusResult.InFlight(
                VideoJobState.Polling,
                new VideoJobProgress(Pct: 10, Stage: "polling", Message: null));

            // Provider rejects cancel.
            _provider.OnCancel = _ => ProviderCancelResult.Fail(new VideoJobError(
                Code: VideoErrorCode.InvalidRequest,
                Message: "Veo refused cancel",
                Retryable: false));

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

            // Cancel surfaces Fail — not Ok(Cancelled) — because the
            // remote may still be running and billing.
            Assert.NotNull(cancel.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, cancel.Error!.Code);

            // Latest ledger record should NOT be Cancelled — the local
            // task is still running.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.NotEqual(VideoJobState.Cancelled, latest.State);
        }

        [Fact]
        public async Task Cancel_in_flight_when_provider_succeeds_persists_Cancelled_with_error()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) => ProviderSubmitResult.Ok("op-ok");
            _provider.OnGetStatus = _ => ProviderStatusResult.InFlight(
                VideoJobState.Polling,
                new VideoJobProgress(Pct: 10, Stage: "polling", Message: null));
            _provider.OnCancel = _ => ProviderCancelResult.Ok(VideoJobState.Cancelled);

            var mgr = Manager(pollInterval: TimeSpan.FromMilliseconds(20));
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                if (_ledger.AllRecords.Any(r => r.JobId == jobId && r.ProviderJobId is not null))
                    break;
                await Task.Delay(10);
            }

            await mgr.CancelAsync(jobId, CancellationToken.None);

            // Wait for the background task to finalize its Cancelled write
            // after the local CTS fires.
            deadline = DateTime.UtcNow + TimeSpan.FromSeconds(2);
            while (DateTime.UtcNow < deadline)
            {
                var latest = _ledger.AllRecords.LastOrDefault(r => r.JobId == jobId);
                if (latest is not null && latest.State == VideoJobState.Cancelled) break;
                await Task.Delay(10);
            }

            var final = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, final.State);
            // Background task's catch path persists the Cancelled error.
            Assert.NotNull(final.Error);
            Assert.Equal(VideoErrorCode.Cancelled, final.Error!.Code);
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
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
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
                jobId, T2vRequest(), _resolvedModel,
                EstimateFor(T2vRequest()),
                VideoJobState.Complete, _clock.UtcNow());
            _ledger.Append(staleRecord);

            var beforeCount = _ledger.AllRecords.Count;

            var mgr = Manager();
            mgr.ReconcileInterruptedJobs();

            // No new record appended — terminal state stays terminal.
            Assert.Equal(beforeCount, _ledger.AllRecords.Count);
        }

        // ─── Pricing single-pass invariant (M3) ───────────────────────

        [Fact]
        public async Task Pricing_model_Estimate_is_called_exactly_once_across_submit_to_complete()
        {
            // M3: the audit-snapshot invariant says pricing is computed
            // once at estimate time and copied verbatim downstream. A
            // counting pricing model proves it end-to-end — no recompute
            // anywhere between submit and the persisted Complete record.
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();

            var counter = new CountingPricingModel(
                inner: VeoCapabilities.Models["veo-3.1-lite-generate-preview"].PricingModel);
            var resolvedWithCounter = _resolvedModel with { PricingModel = counter };
            var registryWithCounter = new SingleModelRegistry(resolvedWithCounter);
            var mgr = new VideoJobManager(
                registry: registryWithCounter,
                mediaResolver: _resolver,
                ledger: _ledger,
                estimator: _estimator,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGen,
                pollInterval: TimeSpan.FromMilliseconds(5));

            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(1, counter.CallCount);
        }

        // Test pricing model that delegates to a real one but counts calls.
        private sealed class CountingPricingModel : IPricingModel
        {
            private readonly IPricingModel _inner;
            public int CallCount { get; private set; }

            public CountingPricingModel(IPricingModel inner) { _inner = inner; }

            public PricingKind Kind => _inner.Kind;
            public string PricingSource => _inner.PricingSource;

            public PricingResult Estimate(VideoGenerationRequest request, ModelCapability cap)
            {
                CallCount++;
                return _inner.Estimate(request, cap);
            }
        }

        // Trivial registry holding one resolved model. Avoids the
        // VeoProviderRegistration path so the swapped PricingModel sticks.
        private sealed class SingleModelRegistry : IVideoProviderRegistry
        {
            private readonly ResolvedVideoModel _model;

            public SingleModelRegistry(ResolvedVideoModel model) { _model = model; }

            public bool TryResolve(string modelId, out ResolvedVideoModel model)
            {
                if (modelId == _model.ModelId)
                {
                    model = _model;
                    return true;
                }
                model = null!;
                return false;
            }

            public bool TryResolveProviderByName(string providerName, out IVideoProvider provider)
            {
                if (providerName == _model.ProviderName)
                {
                    provider = _model.Provider;
                    return true;
                }
                provider = null!;
                return false;
            }

            public IReadOnlyList<VideoModelDescriptor> EnumerateAllModels() =>
                new[]
                {
                    new VideoModelDescriptor(
                        _model.ModelId, _model.ProviderName, _model.Capability,
                        _model.PricingModel.Kind, _model.PricingModel.PricingSource),
                };
        }

        // ─── Submit short-circuits before media resolver on validation failure (M5) ──

        [Fact]
        public async Task Submit_with_invalid_request_does_not_invoke_media_resolver()
        {
            // M5: media resolution is non-trivial work (artifact lookup,
            // disk IO). Submit must reject validation failures BEFORE
            // touching the resolver, otherwise a bad request burns IO on
            // every retry.
            var resolverCalls = 0;
            _resolver.OnResolve = _ =>
            {
                resolverCalls++;
                return new ResolvedVideoMedia(new byte[] { 1 }, "image/png", "fake");
            };

            var mgr = Manager();
            // Invalid: resolution doesn't match cap.
            var bad = T2vRequest() with { Resolution = "8k" };

            var result = await mgr.SubmitAsync(bad, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(0, resolverCalls);
            Assert.Empty(_ledger.AllRecords);
        }

        // ─── H1 regression: cancel succeeds when model deprecated but provider still registered ──

        [Fact]
        public async Task Cancel_after_model_deprecation_resolves_provider_by_name_and_succeeds()
        {
            // H1: persisted record's model id may no longer be in the
            // registry (Google sunsets a Veo model overnight while a job
            // is mid-flight from yesterday). The cancel path must NOT
            // refuse on model-id miss — it should resolve by provider
            // name (which is still registered) and call CancelAsync.
            var jobId = Guid.NewGuid();

            // Pre-populate ledger with an Interrupted record using a
            // DEPRECATED model id that's not in our registry.
            // Construct via the production VeoProviderRegistration first
            // to get a valid pricing snapshot, then force the model on
            // the record.
            var realModel = TestVideoFixtures.VeoLiteResolved(_provider);
            var validReq = TestVideoFixtures.DefaultT2vRequest();
            var prior = VideoJobRecordFactory.From(
                jobId, validReq, realModel, EstimateFor(validReq),
                VideoJobState.Polling, _clock.UtcNow())
                with { Model = "veo-deprecated-yesterday" };  // forced
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "operations/stranded-by-deprecation",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            // Provider is still registered under the real Veo registration.
            string? cancelCalledWith = null;
            _provider.OnCancel = id =>
            {
                cancelCalledWith = id;
                return ProviderCancelResult.Ok(VideoJobState.Cancelled);
            };

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.Equal("operations/stranded-by-deprecation", cancelCalledWith);
            Assert.Equal(VideoJobState.Cancelled, result.State);
            Assert.Null(result.Error);

            // Final record is Cancelled with the Cancelled error attached.
            var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
            Assert.Equal(VideoJobState.Cancelled, latest.State);
            Assert.NotNull(latest.Error);
            Assert.Equal(VideoErrorCode.Cancelled, latest.Error!.Code);
        }

        [Fact]
        public async Task Cancel_when_provider_not_registered_returns_typed_Fail()
        {
            // The other side of H1: if the provider name itself is no
            // longer registered (the entire provider was unbundled, not
            // just one model deprecated), we cannot cancel remotely. Fail
            // typed, surface the missing-provider name in the message.
            var jobId = Guid.NewGuid();

            var realModel = TestVideoFixtures.VeoLiteResolved(_provider);
            var validReq = TestVideoFixtures.DefaultT2vRequest();
            var prior = VideoJobRecordFactory.From(
                jobId, validReq, realModel, EstimateFor(validReq),
                VideoJobState.Polling, _clock.UtcNow())
                with { Provider = "ghost-provider" };  // forced
            prior = VideoJobRecordFactory.WithState(
                prior, VideoJobState.Interrupted, _clock.UtcNow(),
                providerJobId: "operations/orphan",
                error: new VideoJobError(
                    VideoErrorCode.Interrupted, "x", Retryable: true));
            _ledger.Append(prior);

            var mgr = Manager();
            var result = await mgr.CancelAsync(jobId, CancellationToken.None);

            Assert.NotNull(result.Error);
            Assert.Equal(VideoErrorCode.InvalidRequest, result.Error!.Code);
            Assert.Contains("ghost-provider", result.Error.Message);
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
