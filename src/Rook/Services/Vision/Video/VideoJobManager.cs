using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Orchestrates video-job lifecycle. Singleton on the companion
    /// plugin (per-Rhino-process); survives tab open/close and is
    /// disposed on plugin unload. The per-job <see cref="CancellationTokenSource"/>
    /// chains to a manager-wide shutdown CTS so unloading Rhino mid-job
    /// triggers clean cancellation.
    ///
    /// V1c: provider resolution moved from a constructor-bound
    /// <see cref="IVideoProvider"/> + <c>providerName</c> string into
    /// <see cref="IVideoProviderRegistry.TryResolve"/>, called per-submit
    /// against <see cref="VideoGenerationRequest.Model"/>. The resolved
    /// <see cref="ResolvedVideoModel"/> rides on each
    /// <see cref="RunningJob"/> so cancel/poll/fetch in the background
    /// loop never re-resolve.
    ///
    /// Translation responsibilities (from the V1b contract repair):
    ///   - <see cref="ProviderSubmitResult"/> → ledger record + JobSubmitResult
    ///   - <see cref="ProviderStatusResult"/> → ledger record + JobStatusResult
    ///   - <see cref="ProviderFetchResult"/> bytes → ArtifactStore write → artifact id
    ///   - reads of latest ledger record → JobStatusResult / JobFetchResult
    ///
    /// Restart semantics (v3.1 D4): no auto-resume in V1b. On startup,
    /// <see cref="ReconcileInterruptedJobs"/> appends an Interrupted
    /// snapshot for any non-terminal jobs found in the ledger. The
    /// persisted <c>provider_job_id</c> remains so explicit cancel can
    /// clean up remote provider jobs.
    /// </summary>
    public sealed class VideoJobManager : IVideoJobManager, IDisposable
    {
        public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
        public const int DefaultMaxConcurrentJobs = 2;

        private readonly IVideoProviderRegistry _registry;
        private readonly IVideoMediaResolver _mediaResolver;
        private readonly IVideoJobLedger _ledger;
        private readonly IVideoCostEstimator _estimator;
        private readonly ArtifactStore _artifactStore;
        private readonly IVideoJobClock _clock;
        private readonly IVideoJobIdGenerator _idGenerator;
        private readonly TimeSpan _pollInterval;

        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _shutdownCts = new();
        private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();

        public VideoJobManager(
            IVideoProviderRegistry registry,
            IVideoMediaResolver mediaResolver,
            IVideoJobLedger ledger,
            IVideoCostEstimator estimator,
            ArtifactStore artifactStore,
            IVideoJobClock? clock = null,
            IVideoJobIdGenerator? idGenerator = null,
            TimeSpan? pollInterval = null,
            int maxConcurrentJobs = DefaultMaxConcurrentJobs)
        {
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _mediaResolver = mediaResolver ?? throw new ArgumentNullException(nameof(mediaResolver));
            _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
            _estimator = estimator ?? throw new ArgumentNullException(nameof(estimator));
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _clock = clock ?? new SystemVideoJobClock();
            _idGenerator = idGenerator ?? new GuidVideoJobIdGenerator();
            _pollInterval = pollInterval ?? DefaultPollInterval;
            _concurrency = new SemaphoreSlim(maxConcurrentJobs, maxConcurrentJobs);
        }

        // ─── Submit ───────────────────────────────────────────────────

        public async Task<JobSubmitResult> SubmitAsync(
            VideoGenerationRequest request, CancellationToken ct)
        {
            if (request is null)
                return JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "Request is null.",
                    Retryable: false,
                    Field: nameof(request)));

            if (!_registry.TryResolve(request.Model, out var model))
                return JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Unknown model: '{request.Model ?? "<null>"}'.",
                    Retryable: false,
                    Field: nameof(request.Model)));

            var estimate = _estimator.Estimate(model, request);
            if (!estimate.Success)
                return JobSubmitResult.Fail(estimate.Error!);

            // Resolve media refs to bytes. Failures translate to typed
            // JobSubmitResult.Fail before any background work starts.
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> resolved;
            try
            {
                resolved = await ResolveAllMediaAsync(request, ct).ConfigureAwait(false);
            }
            catch (NotSupportedException ex)
            {
                return JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: ex.Message,
                    Retryable: false,
                    Field: "MediaRef"));
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                return JobSubmitResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Media resolution failed: {ex.Message}",
                    Retryable: false,
                    Field: "MediaRef"));
            }

            var jobId = _idGenerator.NewJobId();
            var now = _clock.UtcNow();
            var initial = VideoJobRecordFactory.From(
                jobId, request, model, estimate.Estimate!,
                VideoJobState.Queued, now);

            _ledger.Append(initial);

            // Kick off background task. Caller returns immediately with
            // Queued state; the task drives the state machine.
            var jobCts = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
            var running = new RunningJob(initial, jobCts, model);
            _runningJobs[jobId] = running;

            _ = Task.Run(() => RunJobAsync(jobId, request, resolved, running), jobCts.Token);

            return JobSubmitResult.Ok(jobId, VideoJobState.Queued);
        }

        // ─── Status ───────────────────────────────────────────────────

        public Task<JobStatusResult> GetStatusAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(JobStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: "JobId must be non-empty.",
                        Retryable: false,
                        Field: nameof(jobId))));

            var record = FindLatestRecord(jobId);
            if (record is null)
                return Task.FromResult(JobStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: $"Unknown jobId: {jobId:D}.",
                        Retryable: false,
                        Field: nameof(jobId))));

            return Task.FromResult(TranslateToStatus(record));
        }

        // ─── Cancel ───────────────────────────────────────────────────
        //
        // Cancel is cost-correctness-critical: this is the path that
        // prevents Veo (or any provider) from continuing to bill for jobs
        // the user asked to stop. Two non-obvious invariants (Codex round 6):
        //
        //   1. Interrupted records with a persisted provider_job_id MUST
        //      still be cancellable — that's the entire reason the
        //      ProviderJobId was persisted across restart per v3.1 D4.
        //      Otherwise the cancel-after-restart path leaks money.
        //
        //   2. CancelAsync MUST NOT report Ok when the provider rejects
        //      cancel. The remote may keep running. Surface Fail to the
        //      caller and don't kill the local CTS, so the local task
        //      can still observe the eventual provider-side terminal.
        //
        // The Cancelled error is always persisted alongside the state
        // transition (invariant #4) so JobStatusResult.Failed translation
        // never has to synthesize a fallback error.

        public async Task<JobCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "JobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(jobId)));

            // In-flight: provider comes from the running-job's resolved
            // model (set at SubmitAsync). Try remote cancel first; only
            // kill local CTS on confirmed remote success so a Fail from
            // the provider doesn't leave the user thinking the job is
            // cancelled when the remote is still running.
            if (_runningJobs.TryGetValue(jobId, out var running))
            {
                if (!string.IsNullOrEmpty(running.LatestRecord.ProviderJobId))
                {
                    var remote = await TryRemoteCancelAsync(
                        running.Model.Provider,
                        running.LatestRecord.ProviderJobId!, ct).ConfigureAwait(false);
                    if (remote.Error is not null)
                        return remote;  // Fail; local task untouched

                    try { running.Cts.Cancel(); } catch { /* already cancelled */ }
                    // Background task will write its own Cancelled record
                    // with the Cancelled error on its catch path; we just
                    // surface the provider-reported state.
                    return remote;
                }

                // No provider_job_id yet (job never reached SubmitAsync).
                // Killing the local CTS is sufficient; nothing remote to
                // cancel. The background task's catch path persists
                // Cancelled with the Cancelled error.
                try { running.Cts.Cancel(); } catch { /* already cancelled */ }
                return JobCancelResult.Ok(VideoJobState.Cancelled);
            }

            // Not running locally — look up in the ledger.
            var record = FindLatestRecord(jobId);
            if (record is null)
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Unknown jobId: {jobId:D}.",
                    Retryable: false,
                    Field: nameof(jobId)));

            // Interrupted records with a persisted provider_job_id are
            // still cancellable — that's the cost-cleanup contract from
            // v3.1 D4 + v5 amendments. Non-terminal records with
            // provider_job_id but no in-flight task are the same shape
            // (orphaned by a manager that didn't get to Reconcile).
            var hasRemote = !string.IsNullOrEmpty(record.ProviderJobId);
            var canRemoteCancel = hasRemote
                && (record.State == VideoJobState.Interrupted
                    || !IsTerminal(record.State));

            if (canRemoteCancel)
            {
                // Re-resolve the provider via registry from the persisted
                // record's model id. If the model is no longer registered
                // (e.g., deprecated between runs), we cannot cancel
                // remotely — surface a typed Fail rather than silently
                // leak the remote job.
                if (!_registry.TryResolve(record.Model, out var model))
                    return JobCancelResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: $"Cannot cancel job {jobId:D}: model '{record.Model}' " +
                                 "is no longer registered with this manager.",
                        Retryable: false,
                        Field: nameof(record.Model)));

                var remote = await TryRemoteCancelAsync(
                    model.Provider, record.ProviderJobId!, ct).ConfigureAwait(false);
                if (remote.Error is not null)
                    return remote;  // Fail; ledger state unchanged

                // Provider confirmed cancel; persist Cancelled with
                // the explicit Cancelled error so durable terminal
                // state matches the result-factory invariant.
                var cancelled = VideoJobRecordFactory.WithState(
                    record, VideoJobState.Cancelled, _clock.UtcNow(),
                    error: CancelledError());
                _ledger.Append(cancelled);
                return remote;
            }

            // Already terminal (Complete / Error / Cancelled, or
            // Interrupted without a remote handle) — nothing to do.
            if (IsTerminal(record.State))
                return JobCancelResult.Ok(record.State);

            // Non-terminal, no provider_job_id, no in-flight task —
            // degenerate edge case. Persist a Cancelled snapshot with
            // the Cancelled error.
            var localCancelled = VideoJobRecordFactory.WithState(
                record, VideoJobState.Cancelled, _clock.UtcNow(),
                error: CancelledError());
            _ledger.Append(localCancelled);
            return JobCancelResult.Ok(VideoJobState.Cancelled);
        }

        private static async Task<JobCancelResult> TryRemoteCancelAsync(
            IVideoProvider provider, string providerJobId, CancellationToken ct)
        {
            try
            {
                var result = await provider.CancelAsync(providerJobId, ct)
                    .ConfigureAwait(false);

                if (result.Error is not null)
                    return JobCancelResult.Fail(result.Error);

                return JobCancelResult.Ok(result.State);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: $"Provider cancel failed: {ex.Message}",
                    Retryable: true));
            }
        }

        private static VideoJobError CancelledError() => new(
            Code: VideoErrorCode.Cancelled,
            Message: "Job cancelled.",
            Retryable: false);

        // ─── Fetch result ─────────────────────────────────────────────

        public Task<JobFetchResult> FetchResultAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(JobFetchResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: "JobId must be non-empty.",
                        Retryable: false,
                        Field: nameof(jobId))));

            var record = FindLatestRecord(jobId);
            if (record is null)
                return Task.FromResult(JobFetchResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: $"Unknown jobId: {jobId:D}.",
                        Retryable: false,
                        Field: nameof(jobId))));

            if (record.State != VideoJobState.Complete || record.ResultArtifactId is null)
                return Task.FromResult(JobFetchResult.Failed(
                    record.State,
                    record.Error ?? new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: $"Job not complete (state={record.State}).",
                        Retryable: false)));

            var artifact = _artifactStore.Get(record.ResultArtifactId.Value);
            if (artifact is null)
                return Task.FromResult(JobFetchResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: $"Result artifact {record.ResultArtifactId:D} not found.",
                        Retryable: false)));

            var files = new List<JobResultFile>(artifact.Files.Count);
            foreach (var f in artifact.Files)
                files.Add(new JobResultFile(f.Role, f.Path));

            return Task.FromResult(JobFetchResult.Complete(
                record.ResultArtifactId.Value, files));
        }

        // ─── Reconcile ────────────────────────────────────────────────

        public void ReconcileInterruptedJobs()
        {
            var read = _ledger.ReadAll();
            var now = _clock.UtcNow();

            foreach (var record in read.Records)
            {
                if (IsTerminal(record.State)) continue;

                // Mid-flight at last shutdown. Per v3.1 D4: append
                // Interrupted; don't auto-resume. provider_job_id stays
                // in the record so explicit cancel can still clean up.
                var interrupted = VideoJobRecordFactory.WithState(
                    record,
                    VideoJobState.Interrupted,
                    now,
                    error: new VideoJobError(
                        Code: VideoErrorCode.Interrupted,
                        Message: "Job interrupted by plugin reload.",
                        Retryable: true));
                _ledger.Append(interrupted);
            }
        }

        // ─── Disposal ─────────────────────────────────────────────────

        public void Dispose()
        {
            try { _shutdownCts.Cancel(); } catch { /* already cancelled */ }
            _shutdownCts.Dispose();
            _concurrency.Dispose();
        }

        // ─── Background task ──────────────────────────────────────────

        private async Task RunJobAsync(
            Guid jobId,
            VideoGenerationRequest request,
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> resolvedMedia,
            RunningJob running)
        {
            var ct = running.Cts.Token;
            var current = running.LatestRecord;
            var provider = running.Model.Provider;

            try
            {
                await _concurrency.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    current = AppendTransition(current, VideoJobState.Submitting);
                    running.LatestRecord = current;

                    var submit = await provider.SubmitAsync(
                        request, resolvedMedia, ct).ConfigureAwait(false);

                    if (submit.Error is not null)
                    {
                        current = AppendTransition(current, VideoJobState.Error, error: submit.Error);
                        running.LatestRecord = current;
                        return;
                    }

                    current = AppendTransition(
                        current, VideoJobState.Polling,
                        providerJobId: submit.ProviderJobId);
                    running.LatestRecord = current;

                    // Polling loop
                    string? providerResultToken = null;
                    while (true)
                    {
                        ct.ThrowIfCancellationRequested();
                        var status = await provider.GetStatusAsync(
                            submit.ProviderJobId!, ct).ConfigureAwait(false);

                        if (status.Error is not null)
                        {
                            current = AppendTransition(current, status.State, error: status.Error);
                            running.LatestRecord = current;
                            return;
                        }

                        if (status.State == VideoJobState.Complete
                            && !string.IsNullOrEmpty(status.ProviderResultToken))
                        {
                            providerResultToken = status.ProviderResultToken;
                            current = AppendTransition(
                                current, VideoJobState.Downloading,
                                providerResultToken: providerResultToken);
                            running.LatestRecord = current;
                            break;
                        }

                        await Task.Delay(_pollInterval, ct).ConfigureAwait(false);
                    }

                    // Download
                    var fetch = await provider.FetchResultAsync(
                        submit.ProviderJobId!, providerResultToken, ct).ConfigureAwait(false);

                    if (fetch.Error is not null)
                    {
                        current = AppendTransition(current, VideoJobState.Error, error: fetch.Error);
                        running.LatestRecord = current;
                        return;
                    }

                    // Saving
                    current = AppendTransition(current, VideoJobState.Saving);
                    running.LatestRecord = current;

                    var ext = ExtensionFromMime(fetch.MimeType!);
                    var artifact = _artifactStore.Create(
                        kind: "generated_video",
                        blobs: new[] { new BlobInput("video", fetch.Bytes!, ext) },
                        parentIds: CollectMediaParents(request));

                    // Complete (artifact-first per v3.1 D4 ordering;
                    // result(jobId) never returns a missing artifact_id).
                    current = AppendTransition(
                        current, VideoJobState.Complete,
                        resultArtifactId: artifact.Id);
                    running.LatestRecord = current;
                }
                finally
                {
                    _concurrency.Release();
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                if (!IsTerminal(current.State))
                {
                    var cancelled = AppendTransition(
                        current, VideoJobState.Cancelled,
                        error: new VideoJobError(
                            Code: VideoErrorCode.Cancelled,
                            Message: "Job cancelled.",
                            Retryable: false));
                    running.LatestRecord = cancelled;
                }
            }
            catch (Exception ex)
            {
                if (!IsTerminal(current.State))
                {
                    var errored = AppendTransition(
                        current, VideoJobState.Error,
                        error: new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: $"Unexpected error during job: {ex.Message}",
                            Retryable: false));
                    running.LatestRecord = errored;
                }
            }
            finally
            {
                _runningJobs.TryRemove(jobId, out _);
                running.Cts.Dispose();
            }
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private VideoJobRecord AppendTransition(
            VideoJobRecord prior,
            VideoJobState newState,
            string? providerJobId = null,
            string? providerResultToken = null,
            Guid? resultArtifactId = null,
            VideoJobError? error = null)
        {
            var next = VideoJobRecordFactory.WithState(
                prior, newState, _clock.UtcNow(),
                providerJobId: providerJobId,
                providerResultToken: providerResultToken,
                resultArtifactId: resultArtifactId,
                error: error);
            _ledger.Append(next);
            return next;
        }

        private async Task<IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia>> ResolveAllMediaAsync(
            VideoGenerationRequest request, CancellationToken ct)
        {
            var dict = new Dictionary<VideoMediaRef, ResolvedVideoMedia>();
            await ResolveOneAsync(request.StartFrame, dict, ct).ConfigureAwait(false);
            await ResolveOneAsync(request.EndFrame, dict, ct).ConfigureAwait(false);
            if (request.ReferenceFrames is { Count: > 0 } refs)
            {
                foreach (var r in refs)
                    await ResolveOneAsync(r, dict, ct).ConfigureAwait(false);
            }
            return dict;
        }

        private async Task ResolveOneAsync(
            VideoMediaRef? mediaRef,
            Dictionary<VideoMediaRef, ResolvedVideoMedia> into,
            CancellationToken ct)
        {
            if (mediaRef is null || into.ContainsKey(mediaRef)) return;
            var resolved = await _mediaResolver.ResolveAsync(mediaRef, ct).ConfigureAwait(false);
            into[mediaRef] = resolved;
        }

        private VideoJobRecord? FindLatestRecord(Guid jobId)
        {
            // In-memory state is the freshest (commits happen there).
            if (_runningJobs.TryGetValue(jobId, out var running))
                return running.LatestRecord;

            // Otherwise read the ledger.
            var read = _ledger.ReadAll();
            foreach (var r in read.Records)
                if (r.JobId == jobId) return r;
            return null;
        }

        private static JobStatusResult TranslateToStatus(VideoJobRecord record)
        {
            return record.State switch
            {
                VideoJobState.Complete when record.ResultArtifactId is { } id =>
                    JobStatusResult.Complete(id),

                VideoJobState.Error or VideoJobState.Cancelled or VideoJobState.Interrupted =>
                    JobStatusResult.Failed(
                        record.State,
                        record.Error ?? new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: $"Terminal state {record.State} without error record.",
                            Retryable: false)),

                _ => JobStatusResult.InFlight(
                    record.State,
                    progress: null),
            };
        }

        private static IReadOnlyList<Guid> CollectMediaParents(VideoGenerationRequest request)
        {
            var parents = new List<Guid>();
            if (request.StartFrame?.ArtifactId is { } sId) parents.Add(sId);
            if (request.EndFrame?.ArtifactId is { } eId) parents.Add(eId);
            if (request.ReferenceFrames is { Count: > 0 } refs)
                foreach (var r in refs)
                    if (r.ArtifactId is { } rId) parents.Add(rId);
            return parents;
        }

        private static bool IsTerminal(VideoJobState s) =>
            s is VideoJobState.Complete
              or VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;

        private static string ExtensionFromMime(string mimeType) => mimeType.ToLowerInvariant() switch
        {
            "video/mp4" => "mp4",
            "video/webm" => "webm",
            _ => "bin",
        };

        // Per-job runtime state. Mutable LatestRecord lets the manager's
        // public methods see freshest state without a ledger round-trip;
        // ledger remains the durable source of truth. Model snapshot is
        // captured at submit time so cancel/poll/fetch in this job's
        // lifecycle never re-resolve through the registry.
        private sealed class RunningJob
        {
            public VideoJobRecord LatestRecord;
            public readonly CancellationTokenSource Cts;
            public readonly ResolvedVideoModel Model;

            public RunningJob(VideoJobRecord initial, CancellationTokenSource cts, ResolvedVideoModel model)
            {
                LatestRecord = initial;
                Cts = cts;
                Model = model;
            }
        }
    }
}
