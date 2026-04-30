using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

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
    ///   - <see cref="ProviderSubmitOutcome"/> → ledger record + JobSubmitResult
    ///   - <see cref="ProviderStatusOutcome"/> → ledger record + JobStatusResult
    ///   - <see cref="ProviderResultOutcome"/> bytes → ArtifactStore write → artifact id
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
        private readonly IMediaResolver _mediaResolver;
        private readonly IVideoJobLedger _ledger;
        private readonly IVideoCostEstimator _estimator;
        private readonly ArtifactStore _artifactStore;
        private readonly VideoArtifactMaterializer _materializer;
        private readonly IVideoJobClock _clock;
        private readonly IVideoJobIdGenerator _idGenerator;
        private readonly TimeSpan _pollInterval;

        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _shutdownCts = new();
        private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();

        public VideoJobManager(
            IVideoProviderRegistry registry,
            IMediaResolver mediaResolver,
            IVideoJobLedger ledger,
            IVideoCostEstimator estimator,
            ArtifactStore artifactStore,
            IVideoJobClock? clock = null,
            IVideoJobIdGenerator? idGenerator = null,
            TimeSpan? pollInterval = null,
            int maxConcurrentJobs = DefaultMaxConcurrentJobs)
            : this(
                registry,
                mediaResolver,
                ledger,
                estimator,
                artifactStore,
                clock,
                idGenerator,
                pollInterval,
                maxConcurrentJobs,
                materializer: null)
        {
        }

        internal VideoJobManager(
            IVideoProviderRegistry registry,
            IMediaResolver mediaResolver,
            IVideoJobLedger ledger,
            IVideoCostEstimator estimator,
            ArtifactStore artifactStore,
            IVideoJobClock? clock,
            IVideoJobIdGenerator? idGenerator,
            TimeSpan? pollInterval,
            int maxConcurrentJobs,
            VideoArtifactMaterializer? materializer)
        {
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _mediaResolver = mediaResolver ?? throw new ArgumentNullException(nameof(mediaResolver));
            _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
            _estimator = estimator ?? throw new ArgumentNullException(nameof(estimator));
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _materializer = materializer ?? new VideoArtifactMaterializer();
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
            var mediaResult = await ResolveAllMediaAsync(request, ct).ConfigureAwait(false);
            if (!mediaResult.Success)
                return JobSubmitResult.Fail(
                    VideoProviderOutcomeAdapters.ToVideoJobError(mediaResult.Error!));
            var resolved = mediaResult.Resolved!;

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
        // the user asked to stop. Invariants:
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
        //   3. The Cancelled error is always persisted alongside the
        //      state transition so JobStatusResult.Failed translation
        //      never has to synthesize a fallback error.
        //
        //   4. ProviderJobId for the remote-cancel call is read from the
        //      ledger, not from the in-memory RunningJob.LatestRecord.
        //      The background task writes ledger.Append BEFORE assigning
        //      LatestRecord, so a forced ledger read is the same-or-newer
        //      view of state with a memory barrier (the ledger's lock).
        //      Reading from LatestRecord risks seeing a stale snapshot
        //      under .NET's relaxed memory model and missing a remote
        //      handle that the background task just persisted (M6).
        //
        //   5. For the not-running case, the cancel-target provider is
        //      resolved by record.Provider NAME (not record.Model). The
        //      model id may have been deprecated between runs — e.g.
        //      Google sunsets veo-3.0-fast-generate-001 while a job is
        //      still mid-flight from yesterday. Per H1, refusing to
        //      cancel because the model is unknown strands a remote job
        //      and leaks billing. Provider-name resolution requires only
        //      that the same provider implementation is still registered,
        //      which is the realistic case.
        //
        //   6. CancelAsync's _runningJobs probe runs BEFORE any ledger
        //      read used for the cancel decision. Reading the ledger
        //      first races against the background task's terminal-state
        //      sequence (BG appends Complete to ledger, THEN removes
        //      from _runningJobs). A pre-ledger read could capture a
        //      stale Polling snapshot, then the post-runningJobs probe
        //      sees "absent", and the not-running branch would persist
        //      Cancelled — overwriting the BG's Complete record. By
        //      probing _runningJobs first, an "absent" result implies
        //      BG has already finished its ledger.Append, so the
        //      subsequent ledger read sees the terminal state and the
        //      terminal short-circuit fires (no overwrite).
        //
        //   7. The in-flight branch (probe present) ALSO checks for
        //      terminal ledger state before using ProviderJobId. The BG
        //      task's terminal write may land after the _runningJobs
        //      probe but before the in-flight branch's ledger read,
        //      leaving the branch with a "live" probe and a "terminal"
        //      ledger view. Calling provider.CancelAsync in that window
        //      would return Cancelled to the user even though the
        //      durable state is Complete — the wrong outcome plus a
        //      paid extra provider request. Short-circuit on terminal
        //      symmetrically with invariant 6.

        public async Task<JobCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: "JobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(jobId)));

            // ── In-flight branch (probe _runningJobs FIRST per invariant 6) ──
            if (_runningJobs.TryGetValue(jobId, out var running))
            {
                // Now read ledger for ProviderJobId per M6 (in-memory
                // LatestRecord is racy under relaxed memory).
                var inFlightRecord = FindLedgerRecord(jobId);

                // F1b: even with _runningJobs probed first, a second race
                // exists inside the in-flight branch — the BG task may
                // have appended a terminal record to the ledger between
                // the _runningJobs probe and this ledger read, but not
                // yet executed its finally-block TryRemove. In that
                // window the in-flight branch sees BOTH a live
                // _runningJobs entry AND a terminal ledger view. Calling
                // provider.CancelAsync now would return Cancelled (or
                // Fail) to the user even though the durable state is
                // already Complete/Error — the wrong outcome plus a paid
                // unneeded cancel request. Short-circuit on terminal,
                // mirroring the not-running branch's protection.
                if (inFlightRecord is not null && IsTerminal(inFlightRecord.State))
                    return JobCancelResult.Ok(inFlightRecord.State);

                var inFlightProviderHandle = inFlightRecord?.ProviderHandle;
                var inFlightProviderJobId = inFlightProviderHandle?.ProviderJobId
                    ?? inFlightRecord?.ProviderJobId;

                if (!string.IsNullOrEmpty(inFlightProviderJobId))
                {
                    var remote = await TryRemoteCancelAsync(
                        running.Model.Provider,
                        inFlightProviderHandle ?? new ProviderJobHandle(inFlightProviderJobId!),
                        ct)
                        .ConfigureAwait(false);
                    if (remote.Error is not null)
                        return remote;  // Fail; local task untouched

                    try { running.Cts.Cancel(); } catch { /* already cancelled */ }
                    // Background task will write its own Cancelled record
                    // with the Cancelled error on its catch path; we just
                    // surface the provider-reported state.
                    return remote;
                }

                // No provider_job_id yet (job never reached provider
                // SubmitAsync). Killing the local CTS is sufficient;
                // nothing remote to cancel. The background task's catch
                // path persists Cancelled with the Cancelled error.
                try { running.Cts.Cancel(); } catch { /* already cancelled */ }
                return JobCancelResult.Ok(VideoJobState.Cancelled);
            }

            // ── Not-in-flight branch ──
            //
            // _runningJobs absence at this point implies BG either never
            // started for this id, or finished and removed itself. In the
            // latter case, BG's ledger.Append (terminal) precedes its
            // _runningJobs.TryRemove (per RunJobAsync's finally block),
            // so reading the ledger NOW sees the terminal state.
            var record = FindLedgerRecord(jobId);
            if (record is null)
                return JobCancelResult.Fail(new VideoJobError(
                    Code: VideoErrorCode.InvalidRequest,
                    Message: $"Unknown jobId: {jobId:D}.",
                    Retryable: false,
                    Field: nameof(jobId)));

            // Already terminal (Complete / Error / Cancelled, or
            // Interrupted without a remote handle) — nothing to do.
            // This branch is the load-bearing protection against the
            // race in invariant 6: if BG just finished and removed
            // itself, this short-circuit fires before any provider call
            // or ledger overwrite.
            if (IsTerminal(record.State) && record.State != VideoJobState.Interrupted)
                return JobCancelResult.Ok(record.State);

            // Interrupted records with a persisted provider_job_id are
            // still cancellable — that's the cost-cleanup contract from
            // v3.1 D4 + v5 amendments. Non-terminal records with
            // provider_job_id but no in-flight task are the same shape
            // (orphaned by a manager that didn't get to Reconcile).
            var providerHandle = record.ProviderHandle;
            var providerJobId = providerHandle?.ProviderJobId ?? record.ProviderJobId;
            var hasRemote = !string.IsNullOrEmpty(providerJobId);
            var canRemoteCancel = hasRemote
                && (record.State == VideoJobState.Interrupted
                    || !IsTerminal(record.State));

            if (canRemoteCancel)
            {
                // H1: resolve by provider NAME, not model id. A
                // deprecated model whose provider is still registered
                // must still be cancellable.
                if (!_registry.TryResolveProviderByName(record.Provider, out var provider))
                    return JobCancelResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.InvalidRequest,
                        Message: $"Cannot cancel job {jobId:D}: provider '{record.Provider}' " +
                                 "is no longer registered with this manager.",
                        Retryable: false,
                        Field: nameof(record.Provider)));

                var remote = await TryRemoteCancelAsync(
                    provider,
                    providerHandle ?? new ProviderJobHandle(providerJobId!),
                    ct).ConfigureAwait(false);
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

            // Interrupted without a remote handle — nothing to clean up
            // on the provider side. Surface its persisted terminal state.
            if (record.State == VideoJobState.Interrupted)
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
            IVideoProvider provider, ProviderJobHandle handle, CancellationToken ct)
        {
            try
            {
                var outcome = await provider.CancelAsync(handle, ct)
                    .ConfigureAwait(false);

                return outcome switch
                {
                    CanceledOutcome =>
                        JobCancelResult.Ok(VideoJobState.Cancelled),
                    AlreadyTerminalOutcome terminal =>
                        JobCancelResult.Ok(ToVideoTerminalState(terminal.TerminalState)),
                    FailedCancelOutcome failed =>
                        JobCancelResult.Fail(
                            VideoProviderOutcomeAdapters.ToVideoJobError(failed.Error)),
                    _ => JobCancelResult.Fail(new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: $"Unknown provider cancel outcome: {outcome.GetType().Name}.",
                        Retryable: false)),
                };
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

        private static VideoJobState ToVideoTerminalState(GenerationLifecycleState state) =>
            state switch
            {
                GenerationLifecycleState.Completed => VideoJobState.Complete,
                GenerationLifecycleState.Canceled => VideoJobState.Cancelled,
                GenerationLifecycleState.Failed => VideoJobState.Error,
                _ => VideoJobState.Error,
            };

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
                    ToVideoJobError(
                        record.Error,
                        new VideoJobError(
                            Code: VideoErrorCode.ExecutionFailed,
                            Message: $"Job not complete (state={record.State}).",
                            Retryable: false))));

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

        // ─── List jobs (PR-V3) ────────────────────────────────────────

        /// <summary>
        /// Hard ceiling for <see cref="ListJobsAsync"/>'s
        /// <c>limit</c> argument. Any caller-supplied value above this
        /// is clamped and surfaced via
        /// <see cref="JobListResult.AppliedLimit"/>. The ceiling exists
        /// so a malformed request (or future MCP client) cannot demand
        /// an unbounded ledger scan + JSON projection.
        /// </summary>
        public const int MaxListLimit = 200;

        public Task<JobListResult> ListJobsAsync(int limit, CancellationToken ct)
        {
            if (limit < 1)
                throw new ArgumentOutOfRangeException(
                    nameof(limit), limit,
                    "limit must be a positive integer; reject before calling.");

            var applied = limit > MaxListLimit ? MaxListLimit : limit;

            var read = _ledger.ReadAll();
            var warnings = ProjectWarnings(read.Errors);

            // Snapshot the in-memory running records. ConcurrentDictionary
            // enumeration is safe; we capture the LatestRecord field (a
            // reference read) per running job into a plain list so the
            // merge step is over an immutable snapshot.
            var runningSnapshots = new List<VideoJobRecord>(_runningJobs.Count);
            foreach (var kvp in _runningJobs)
            {
                var live = kvp.Value.LatestRecord;
                if (live is not null) runningSnapshots.Add(live);
            }

            var merged = MergeByFreshness(read.Records, runningSnapshots);

            // Sort newest first; tie-break on JobId descending so the
            // order is deterministic across reads.
            var ordered = new List<VideoJobRecord>(merged.Values);
            ordered.Sort((a, b) =>
            {
                int byTime = b.UpdatedAt.CompareTo(a.UpdatedAt);
                if (byTime != 0) return byTime;
                return b.JobId.CompareTo(a.JobId);
            });

            // Apply limit AFTER sorting — caller asked for the N newest.
            if (ordered.Count > applied)
                ordered.RemoveRange(applied, ordered.Count - applied);

            var entries = new List<JobListEntry>(ordered.Count);
            foreach (var r in ordered)
                entries.Add(ProjectEntry(r));

            return Task.FromResult(new JobListResult(entries, warnings, applied));
        }

        /// <summary>
        /// Pure freshness-merge over (ledger snapshot, in-memory running
        /// snapshots). Codex sign-off correction (v3 implementation
        /// review): the tie rule is stricter than the original "terminal
        /// wins on tie" — when timestamps are equal, ledger only wins if
        /// ledger is terminal; otherwise running wins. The asymmetry
        /// protects against a future ordering inversion in
        /// <c>RunJobAsync</c> (assigning <c>LatestRecord</c> before
        /// <c>ledger.Append</c>) that would otherwise let a stale
        /// non-terminal ledger pin the in-memory record.
        ///
        /// Rule per job_id:
        /// <list type="bullet">
        ///   <item>only ledger → use ledger</item>
        ///   <item>only running → use running (defensive — current submit
        ///         path appends initial ledger record before adding to
        ///         <c>_runningJobs</c>, so this shouldn't happen)</item>
        ///   <item>both, running newer → running wins</item>
        ///   <item>both, ledger newer → ledger wins</item>
        ///   <item>both, tied + ledger terminal → ledger wins</item>
        ///   <item>both, tied + ledger non-terminal → running wins</item>
        /// </list>
        ///
        /// Note that the tied-non-terminal-ledger case includes the
        /// "running is also non-terminal" path: if both records are at
        /// the same instant and neither is terminal, prefer the in-memory
        /// view because that's the side that races ahead in the future-
        /// ordering scenario.
        ///
        /// Internal so it's unit-testable in isolation (the integration
        /// path goes through a real background task, which is harder to
        /// pose specific freshness scenarios on).
        /// </summary>
        internal static IReadOnlyDictionary<Guid, VideoJobRecord> MergeByFreshness(
            IReadOnlyList<VideoJobRecord> ledgerRecords,
            IReadOnlyList<VideoJobRecord> runningSnapshots)
        {
            var merged = new Dictionary<Guid, VideoJobRecord>(ledgerRecords.Count);
            foreach (var r in ledgerRecords)
                merged[r.JobId] = r;

            foreach (var live in runningSnapshots)
            {
                if (!merged.TryGetValue(live.JobId, out var ledger))
                {
                    merged[live.JobId] = live;
                    continue;
                }

                if (live.UpdatedAt > ledger.UpdatedAt)
                {
                    merged[live.JobId] = live;
                }
                else if (live.UpdatedAt < ledger.UpdatedAt)
                {
                    // ledger wins (already in dict).
                }
                else
                {
                    // Tied. Ledger keeps the slot ONLY if it is itself
                    // terminal — otherwise running wins (Codex tie rule).
                    if (!IsTerminal(ledger.State))
                        merged[live.JobId] = live;
                }
            }

            return merged;
        }

        private static JobListEntry ProjectEntry(VideoJobRecord record)
        {
            // Model id comes from the top-level VideoJobRecord.Model, not
            // NormalizedRequest (which by contract does not carry the
            // model id — see NormalizedRequest docstring).
            var summary = new JobRequestSummary(
                Model: record.Model,
                Mode: record.NormalizedRequest.Mode,
                DurationSeconds: record.NormalizedRequest.DurationSeconds,
                Resolution: record.NormalizedRequest.Resolution,
                AspectRatio: record.NormalizedRequest.AspectRatio);

            return new JobListEntry(
                JobId: record.JobId,
                State: record.State,
                UpdatedAt: record.UpdatedAt,
                Summary: summary,
                ResultArtifactId: record.ResultArtifactId,
                Error: record.Error is null
                    ? null
                    : VideoProviderOutcomeAdapters.ToVideoJobError(record.Error));
        }

        private static IReadOnlyList<LedgerWarning> ProjectWarnings(
            IReadOnlyList<LedgerReadError> errors)
        {
            if (errors.Count == 0) return System.Array.Empty<LedgerWarning>();
            var list = new List<LedgerWarning>(errors.Count);
            foreach (var e in errors)
            {
                // PR-V3 sanitization (Codex review of v3 implementation):
                // Drop RawLineExcerpt and OffendingValue (handled by not
                // copying them) AND synthesize a per-reason message
                // rather than forwarding e.Message. The original
                // LedgerReadError.Message can interpolate user-supplied
                // content (e.g. JsonlVideoJobLedger emits
                //   "Unknown pricing.kind: '{kindStr}'."
                // — which round-trips a raw provider-options value into
                // any consumer that surfaces the warning). The
                // synthesized message is reason-only; the line number +
                // field path are sufficient operator triage signal.
                list.Add(new LedgerWarning(
                    LineNumber: e.LineNumber,
                    Reason: e.Reason,
                    Message: SanitizedWarningMessage(e.Reason),
                    FieldPath: e.FieldPath));
            }
            return list;
        }

        private static string SanitizedWarningMessage(LedgerReadErrorReason reason) => reason switch
        {
            LedgerReadErrorReason.MalformedJson =>
                "Ledger line could not be parsed as JSON.",
            LedgerReadErrorReason.UnsupportedSchemaVersion =>
                "Ledger line uses an unsupported schema version.",
            LedgerReadErrorReason.UnknownPricingKind =>
                "Ledger line carries an unknown pricing kind.",
            LedgerReadErrorReason.MissingRequiredField =>
                "Ledger line is missing a required field.",
            _ => "Ledger line could not be loaded.",
        };

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
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
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

                    var submitOutcome = await provider.SubmitAsync(
                        request,
                        resolvedMedia,
                        ct).ConfigureAwait(false);

                    ProviderJobHandle handle;
                    switch (submitOutcome)
                    {
                        case QueuedSubmitOutcome queued:
                            handle = queued.Handle;
                            break;

                        case FailedSubmitOutcome failed:
                            current = AppendTransition(
                            current,
                            VideoJobState.Error,
                            error: failed.Error);
                            running.LatestRecord = current;
                            return;

                        case SyncSubmitOutcome sync:
                            await CompleteSyncSubmitAsync(
                                current, running, request, sync.Result, ct)
                                .ConfigureAwait(false);
                            return;

                        default:
                            current = AppendTransition(
                                current,
                                VideoJobState.Error,
                                error: new VideoJobError(
                                    VideoErrorCode.ExecutionFailed,
                                    $"Unknown provider submit outcome: {submitOutcome.GetType().Name}.",
                                    Retryable: false));
                            running.LatestRecord = current;
                            return;
                    }

                    current = AppendTransition(
                        current, VideoJobState.Polling,
                        providerHandle: handle);
                    running.LatestRecord = current;

                    // Polling loop
                    while (true)
                    {
                        ct.ThrowIfCancellationRequested();
                        var statusOutcome = await provider.GetStatusAsync(
                            handle, ct).ConfigureAwait(false);

                        switch (statusOutcome)
                        {
                            case InFlightStatusOutcome:
                                await Task.Delay(_pollInterval, ct).ConfigureAwait(false);
                                continue;

                            case ProviderCompleteStatusOutcome complete:
                                handle = complete.UpdatedHandle;
                                current = AppendTransition(
                                    current,
                                    VideoJobState.Downloading,
                                    providerHandle: handle);
                                running.LatestRecord = current;
                                break;

                            case FailedStatusOutcome failed:
                                current = AppendTransition(
                                    current,
                                    VideoJobState.Error,
                                    error: failed.Error);
                                running.LatestRecord = current;
                                return;

                            default:
                                current = AppendTransition(
                                    current,
                                    VideoJobState.Error,
                                    error: new VideoJobError(
                                        VideoErrorCode.ExecutionFailed,
                                        $"Unknown provider status outcome: {statusOutcome.GetType().Name}.",
                                        Retryable: false));
                                running.LatestRecord = current;
                                return;
                        }

                        break;
                    }

                    // Download
                    var fetch = await provider.FetchResultAsync(handle, ct)
                        .ConfigureAwait(false);

                    if (fetch is FailedResultOutcome failedFetch)
                    {
                        current = AppendTransition(
                            current,
                            VideoJobState.Error,
                            error: failedFetch.Error);
                        running.LatestRecord = current;
                        return;
                    }

                    if (fetch is not SuccessResultOutcome successFetch)
                    {
                        current = AppendTransition(
                            current,
                            VideoJobState.Error,
                            error: new VideoJobError(
                                VideoErrorCode.ExecutionFailed,
                                $"Unknown provider result outcome: {fetch.GetType().Name}.",
                                Retryable: false));
                        running.LatestRecord = current;
                        return;
                    }

                    if (!TryFindVideoArtifact(successFetch.Envelope, out var videoArtifact))
                    {
                        current = AppendTransition(
                            current,
                            VideoJobState.Error,
                            error: MissingInlineVideoArtifactError());
                        running.LatestRecord = current;
                        return;
                    }

                    // Saving
                    current = AppendTransition(current, VideoJobState.Saving);
                    running.LatestRecord = current;

                    var materialized = await _materializer.MaterializeAsync(
                        videoArtifact,
                        ct).ConfigureAwait(false);
                    if (!materialized.Success)
                    {
                        if (IsCancellationMaterializationFailure(materialized, ct))
                            ct.ThrowIfCancellationRequested();

                        current = AppendTransition(
                            current,
                            VideoJobState.Error,
                            error: materialized.Error);
                        running.LatestRecord = current;
                        return;
                    }

                    var ext = ExtensionFromMime(materialized.MimeType!);
                    var artifact = _artifactStore.Create(
                        kind: "generated_video",
                        blobs: new[] { new BlobInput("video", materialized.Bytes!, ext) },
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
            GenerationError? error = null,
            ProviderJobHandle? providerHandle = null)
        {
            var next = VideoJobRecordFactory.WithState(
                prior, newState, _clock.UtcNow(),
                providerJobId: providerJobId,
                providerResultToken: providerResultToken,
                resultArtifactId: resultArtifactId,
                error: error,
                providerHandle: providerHandle);
            _ledger.Append(next);
            return next;
        }

        private async Task CompleteSyncSubmitAsync(
            VideoJobRecord current,
            RunningJob running,
            VideoGenerationRequest request,
            ProviderResultOutcome result,
            CancellationToken ct)
        {
            if (result is FailedResultOutcome failed)
            {
                var errored = AppendTransition(
                    current,
                    VideoJobState.Error,
                    error: failed.Error);
                running.LatestRecord = errored;
                return;
            }

            if (result is not SuccessResultOutcome success)
            {
                var errored = AppendTransition(
                    current,
                    VideoJobState.Error,
                    error: new VideoJobError(
                        VideoErrorCode.ExecutionFailed,
                        $"Unknown provider result outcome: {result.GetType().Name}.",
                        Retryable: false));
                running.LatestRecord = errored;
                return;
            }

            if (!TryFindVideoArtifact(success.Envelope, out var videoArtifact))
            {
                var errored = AppendTransition(
                    current,
                    VideoJobState.Error,
                    error: MissingInlineVideoArtifactError());
                running.LatestRecord = errored;
                return;
            }

            current = AppendTransition(current, VideoJobState.Saving);
            running.LatestRecord = current;

            ct.ThrowIfCancellationRequested();
            var materialized = await _materializer.MaterializeAsync(
                videoArtifact,
                ct).ConfigureAwait(false);
            if (!materialized.Success)
            {
                if (IsCancellationMaterializationFailure(materialized, ct))
                    ct.ThrowIfCancellationRequested();

                var errored = AppendTransition(
                    current,
                    VideoJobState.Error,
                    error: materialized.Error);
                running.LatestRecord = errored;
                return;
            }

            var ext = ExtensionFromMime(materialized.MimeType!);
            var artifact = _artifactStore.Create(
                kind: "generated_video",
                blobs: new[] { new BlobInput("video", materialized.Bytes!, ext) },
                parentIds: CollectMediaParents(request));

            current = AppendTransition(
                current,
                VideoJobState.Complete,
                resultArtifactId: artifact.Id);
            running.LatestRecord = current;
        }

        private static bool IsCancellationMaterializationFailure(
            VideoArtifactMaterializationResult materialized,
            CancellationToken ct)
        {
            if (!ct.IsCancellationRequested || materialized.Error is null)
                return false;

            return materialized.Error.Code == GenerationErrorCode.Cancelled
                || materialized.Error.Code == GenerationErrorCode.Interrupted;
        }

        private static bool TryFindVideoArtifact(
            ProviderResultEnvelope envelope,
            out ResultArtifact videoArtifact)
        {
            foreach (var artifact in envelope.Artifacts)
            {
                if (artifact.Role == VideoMediaRoles.Video)
                {
                    videoArtifact = artifact;
                    return true;
                }
            }

            videoArtifact = null!;
            return false;
        }

        private static VideoJobError MissingInlineVideoArtifactError() =>
            new(
                VideoErrorCode.ExecutionFailed,
                "Provider result envelope did not contain an inline video artifact.",
                Retryable: false);

        private Task<MediaResolutionResult> ResolveAllMediaAsync(
            VideoGenerationRequest request, CancellationToken ct)
        {
            var mediaRefs = new List<MediaRef>();
            AddMediaRef(request.StartFrame, mediaRefs);
            AddMediaRef(request.EndFrame, mediaRefs);
            if (request.ReferenceFrames is { Count: > 0 } referenceFrames)
            {
                foreach (var r in referenceFrames)
                    AddMediaRef(r, mediaRefs);
            }

            return _mediaResolver.ResolveAllAsync(mediaRefs, ct);
        }

        private static void AddMediaRef(MediaRef? mediaRef, List<MediaRef> refs)
        {
            if (mediaRef is null) return;
            if (!refs.Contains(mediaRef))
                refs.Add(mediaRef);
        }

        private VideoJobRecord? FindLatestRecord(Guid jobId)
        {
            // Used by GetStatusAsync / FetchResultAsync where stale-by-one-
            // transition is acceptable (status is informational; fetch
            // checks state == Complete which is terminal so the in-memory
            // cache cannot be NEWER than the ledger for that path).
            if (_runningJobs.TryGetValue(jobId, out var running))
                return running.LatestRecord;

            return FindLedgerRecord(jobId);
        }

        private VideoJobRecord? FindLedgerRecord(Guid jobId)
        {
            // Forces a ledger read, bypassing the in-memory cache. Used by
            // CancelAsync for cost-correctness (M6): the background task
            // writes ledger.Append BEFORE assigning RunningJob.LatestRecord,
            // so the ledger view is the same-or-newer state with a memory
            // barrier. Reading from LatestRecord risks missing a remote
            // handle the background task just persisted.
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
                        ToVideoJobError(
                            record.Error,
                            new VideoJobError(
                                Code: VideoErrorCode.ExecutionFailed,
                                Message: $"Terminal state {record.State} without error record.",
                                Retryable: false))),

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

        private static VideoJobError ToVideoJobError(
            GenerationError? error,
            VideoJobError fallback) =>
            error is null
                ? fallback
                : VideoProviderOutcomeAdapters.ToVideoJobError(error);

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
