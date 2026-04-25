using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
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
        public const string DefaultProviderName = "veo";
        public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
        public const int DefaultMaxConcurrentJobs = 2;

        private readonly IVideoProvider _provider;
        private readonly IVideoMediaResolver _mediaResolver;
        private readonly IVideoJobLedger _ledger;
        private readonly IVideoCapabilityCatalog _catalog;
        private readonly IVideoCostEstimator _estimator;
        private readonly ArtifactStore _artifactStore;
        private readonly IVideoJobClock _clock;
        private readonly IVideoJobIdGenerator _idGenerator;
        private readonly string _providerName;
        private readonly TimeSpan _pollInterval;

        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _shutdownCts = new();
        private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();

        public VideoJobManager(
            IVideoProvider provider,
            IVideoMediaResolver mediaResolver,
            IVideoJobLedger ledger,
            IVideoCapabilityCatalog catalog,
            IVideoCostEstimator estimator,
            ArtifactStore artifactStore,
            IVideoJobClock? clock = null,
            IVideoJobIdGenerator? idGenerator = null,
            string providerName = DefaultProviderName,
            TimeSpan? pollInterval = null,
            int maxConcurrentJobs = DefaultMaxConcurrentJobs)
        {
            _provider = provider ?? throw new ArgumentNullException(nameof(provider));
            _mediaResolver = mediaResolver ?? throw new ArgumentNullException(nameof(mediaResolver));
            _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _estimator = estimator ?? throw new ArgumentNullException(nameof(estimator));
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _clock = clock ?? new SystemVideoJobClock();
            _idGenerator = idGenerator ?? new GuidVideoJobIdGenerator();
            _providerName = providerName;
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

            var validation = _catalog.Validate(request);
            if (!validation.Success)
                return JobSubmitResult.Fail(new VideoJobError(
                    Code: ClassifyValidationFailure(validation.Field),
                    Message: validation.Message ?? "Validation failed.",
                    Retryable: false,
                    Field: validation.Field));

            var estimate = _estimator.Estimate(request);
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
                jobId, request, _providerName, estimate.Estimate!,
                VideoJobState.Queued, now);

            _ledger.Append(initial);

            // Kick off background task. Caller returns immediately with
            // Queued state; the task drives the state machine.
            var jobCts = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
            var running = new RunningJob(initial, jobCts);
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

        public async Task<JobCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "JobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(jobId)));

            // In-flight: signal local CTS and best-effort remote cancel.
            if (_runningJobs.TryGetValue(jobId, out var running))
            {
                try { running.Cts.Cancel(); } catch { /* already cancelled */ }

                if (!string.IsNullOrEmpty(running.LatestRecord.ProviderJobId))
                {
                    try
                    {
                        await _provider.CancelAsync(
                            running.LatestRecord.ProviderJobId!, ct).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException) { throw; }
                    catch
                    {
                        // Best-effort. The local CTS already triggered cleanup;
                        // remote cancel failure is logged via the eventual
                        // background-task ledger entry.
                    }
                }

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

            if (IsTerminal(record.State))
                return JobCancelResult.Ok(record.State);

            // Non-terminal but not in-flight — orphaned (Interrupted by
            // restart, or somehow lost). Best-effort remote cancel using
            // persisted provider_job_id, then persist Cancelled.
            if (!string.IsNullOrEmpty(record.ProviderJobId))
            {
                try
                {
                    await _provider.CancelAsync(
                        record.ProviderJobId!, ct).ConfigureAwait(false);
                }
                catch (OperationCanceledException) { throw; }
                catch { /* best-effort */ }
            }

            var cancelled = VideoJobRecordFactory.WithState(
                record, VideoJobState.Cancelled, _clock.UtcNow());
            _ledger.Append(cancelled);

            return JobCancelResult.Ok(VideoJobState.Cancelled);
        }

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

            try
            {
                await _concurrency.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    current = AppendTransition(current, VideoJobState.Submitting);
                    running.LatestRecord = current;

                    var submit = await _provider.SubmitAsync(
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
                        var status = await _provider.GetStatusAsync(
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
                    var fetch = await _provider.FetchResultAsync(
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

        private static VideoErrorCode ClassifyValidationFailure(string? field) => field switch
        {
            "Resolution" or "DurationSeconds" or "AspectRatio"
                or "Mode" or "ReferenceFrames" or "NumberOfVideos"
                or "PersonGeneration" => VideoErrorCode.UnsupportedMedia,
            _ => VideoErrorCode.InvalidRequest,
        };

        private static string ExtensionFromMime(string mimeType) => mimeType.ToLowerInvariant() switch
        {
            "video/mp4" => "mp4",
            "video/webm" => "webm",
            _ => "bin",
        };

        // Per-job runtime state. Mutable LatestRecord lets the manager's
        // public methods see freshest state without a ledger round-trip;
        // ledger remains the durable source of truth.
        private sealed class RunningJob
        {
            public VideoJobRecord LatestRecord;
            public readonly CancellationTokenSource Cts;

            public RunningJob(VideoJobRecord initial, CancellationTokenSource cts)
            {
                LatestRecord = initial;
                Cts = cts;
            }
        }
    }
}
