using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

public interface IReconstructionSourceImagePublisher
{
    Task<Uri> PublishAsync(byte[] bytes, string mimeType, string fileName, CancellationToken ct);
}

public sealed record ReconstructionSubmitResult(
    bool Success,
    ReconstructionJobLedgerRecord? Job,
    ReconstructionFailure? Failure);

public sealed record ReconstructionJobStatusResult(
    bool Success,
    ReconstructionJobLedgerRecord? Job,
    bool ResultAvailable,
    ReconstructionFailure? Failure);

public sealed record ReconstructionCancelResult(
    ReconstructionJobState State,
    ReconstructionFailure? Failure);

public sealed record ReconstructionJobResultEnvelope(
    bool Success,
    Guid JobId,
    Guid? ResultArtifactId,
    bool ResultAvailable,
    IReadOnlyList<ReconstructionWarning> Warnings,
    ReconstructionFailure? Failure);

public sealed class ReconstructionJobManager : IDisposable
{
    public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
    public const int DefaultMaxConcurrentJobs = 2;

    private readonly ArtifactStore _store;
    private readonly ReconstructionModelCatalog _catalog;
    private readonly JsonlReconstructionJobLedger _ledger;
    private readonly IReconstructionProvider _provider;
    private readonly ReconstructionPackageMaterializer _materializer;
    private readonly IReconstructionSourceImagePublisher _sourcePublisher;

    // Per-job single-flight gate, shared by the background loop and on-demand StatusAsync/poll
    // callers: every poller acquires it, re-reads the freshest ledger record, and returns early if
    // the job is already terminal — so exactly one terminal transition + materialization occurs.
    private readonly ConcurrentDictionary<Guid, SemaphoreSlim> _pollLocks = new();

    // Background execution lifecycle (W6). No startup reconcile here (that is a separate task).
    private readonly TimeSpan _pollInterval;
    private readonly CancellationTokenSource _shutdownCts = new();
    private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();
    private readonly SemaphoreSlim _concurrency = new(DefaultMaxConcurrentJobs, DefaultMaxConcurrentJobs);
    private bool _disposed;

    public ReconstructionJobManager(
        ArtifactStore store,
        ReconstructionModelCatalog catalog,
        JsonlReconstructionJobLedger ledger,
        IReconstructionProvider provider,
        ReconstructionPackageMaterializer materializer,
        IReconstructionSourceImagePublisher sourcePublisher,
        TimeSpan? pollInterval = null)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _materializer = materializer ?? throw new ArgumentNullException(nameof(materializer));
        _sourcePublisher = sourcePublisher ?? throw new ArgumentNullException(nameof(sourcePublisher));
        _pollInterval = pollInterval ?? DefaultPollInterval;
    }

    private sealed class RunningJob
    {
        public RunningJob(ReconstructionJobLedgerRecord initial, CancellationTokenSource cts)
        {
            Latest = initial;
            Cts = cts;
        }

        public ReconstructionJobLedgerRecord Latest { get; }
        public CancellationTokenSource Cts { get; }
        public Task Loop { get; set; } = Task.CompletedTask;
    }

    public async Task<ReconstructionSubmitResult> SubmitAsync(
        ReconstructionSubmitRequest request,
        CancellationToken ct)
    {
        var model = _catalog.Find(request.ModelId);
        if (!IsSubmittableV1Model(model))
            return SubmitFail("invalid_request", "Requested reconstruction model is not available.", "model_id");

        if (request.PreprocessingChain.Count != 0)
        {
            return SubmitFail(
                "invalid_request",
                "preprocessing_chain execution is not implemented in v0.",
                "preprocessing_chain");
        }

        var source = _store.Get(request.SourceArtifactId);
        if (source is null)
            return SubmitFail("invalid_request", "source_artifact_id was not found.", "source_artifact_id");

        var sourceValidation = ReconstructionSourceValidator.Validate(_store, source, request.SourceRole);
        if (!sourceValidation.Success)
            return new ReconstructionSubmitResult(false, null, sourceValidation.Failure);

        var jobId = Guid.NewGuid();
        var queued = ReconstructionJobLedgerRecord.Queued(
            jobId,
            request.ModelId,
            request.SourceArtifactId,
            request.SourceRole);
        _ledger.Append(queued);

        var submitting = WithState(
            queued,
            ReconstructionJobState.Running,
            ReconstructionJobStage.Submitting);
        _ledger.Append(submitting);

        ProviderSubmitOutcome submitOutcome;
        try
        {
            // The validator already resolved + length-cap-validated AbsolutePath (it is the resolver).
            // Read bytes here (manager owns the store) and pass only bytes/mime/fileName onward, so the
            // provider/publisher stay storage-agnostic.
            var sourcePath = sourceValidation.AbsolutePath!;
            var sourceBytes = await ReadFileBytesAsync(sourcePath, ct).ConfigureAwait(false);
            var sourceMime = MimeForExtension(sourcePath);
            var sourceFileName = $"rook-reconstruction-{source.Id:D}-{request.SourceRole}{Path.GetExtension(sourcePath)}";
            var sourceUrl = await _sourcePublisher.PublishAsync(
                sourceBytes,
                sourceMime,
                sourceFileName,
                ct).ConfigureAwait(false);
            submitOutcome = await _provider.SubmitAsync(
                new ReconstructionProviderSubmitRequest(request.ModelId, sourceUrl, request.Options),
                ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            // Missing fal key (publisher edge, or provider edge if the key vanished mid-submit). Map to
            // the canonical typed failure rather than the generic submit_failed below. MUST stay before
            // the FalApiException/Exception catches.
            return RecordSubmitFailure(submitting, ReconstructionErrorMapping.MissingCredentialFailure());
        }
        catch (FalApiException ex)
        {
            // The fal CDN source-image upload failed (transport fault or non-2xx). That is a provider
            // dependency failure, not a local source-read/IO fault — surface it with the same
            // provider_unavailable semantics the provider uses for its own transport failures, rather
            // than collapsing it into the generic submit_failed below.
            return RecordSubmitFailure(submitting, Failure(
                "provider_unavailable",
                "Reconstruction source image upload to the provider failed.",
                null,
                retryable: true,
                new Dictionary<string, object?>
                {
                    ["exception_type"] = ex.GetType().Name,
                }));
        }
        catch (Exception ex)
        {
            // Reserved for local source-read/IO faults: the provider itself returns typed Failed*
            // outcomes for HTTP/parse failures (handled below) rather than throwing, and fal upload
            // faults are handled by the FalApiException catch above.
            return RecordSubmitFailure(submitting, Failure(
                "submit_failed",
                "Reconstruction submit failed.",
                null,
                retryable: true,
                new Dictionary<string, object?>
                {
                    ["exception_type"] = ex.GetType().Name,
                }));
        }

        switch (submitOutcome)
        {
            case QueuedSubmitOutcome queuedOutcome:
                var handle = queuedOutcome.Handle;
                var polling = submitting with
                {
                    Stage = ReconstructionJobStage.Polling,
                    ProviderJobId = handle.ProviderJobId,
                    ProviderStatusUrl = handle.StatusUrl?.ToString(),
                    ProviderResponseUrl = handle.ResponseUrl?.ToString(),
                    ProviderCancelUrl = handle.CancelUrl?.ToString(),
                    ProviderCancelHttpMethod = handle.CancelHttpMethod,
                    UpdatedAt = DateTimeOffset.UtcNow,
                };
                _ledger.Append(polling);
                StartBackgroundLoop(polling);
                return new ReconstructionSubmitResult(true, queued, null);

            case FailedSubmitOutcome failedOutcome:
                var submitFailure = ReconstructionErrorMapping.ToFailure(failedOutcome.Error);
                _ledger.Append(submitting with
                {
                    State = ReconstructionJobState.Error,
                    Stage = ReconstructionJobStage.Error,
                    Error = submitFailure,
                    UpdatedAt = DateTimeOffset.UtcNow,
                });
                return new ReconstructionSubmitResult(false, null, submitFailure);

            default:
                // fal reconstruction is always queued; a sync result would be a contract violation.
                var unexpected = Failure(
                    "submit_failed",
                    "Reconstruction provider returned an unexpected synchronous result.",
                    null);
                _ledger.Append(submitting with
                {
                    State = ReconstructionJobState.Error,
                    Stage = ReconstructionJobStage.Error,
                    Error = unexpected,
                    UpdatedAt = DateTimeOffset.UtcNow,
                });
                return new ReconstructionSubmitResult(false, null, unexpected);
        }
    }

    // Records a terminal submit-phase error on the ledger and returns the failed submit result.
    private ReconstructionSubmitResult RecordSubmitFailure(
        ReconstructionJobLedgerRecord submitting,
        ReconstructionFailure failure)
    {
        _ledger.Append(submitting with
        {
            State = ReconstructionJobState.Error,
            Stage = ReconstructionJobStage.Error,
            Error = failure,
            UpdatedAt = DateTimeOffset.UtcNow,
        });
        return new ReconstructionSubmitResult(false, null, failure);
    }

    // net48-safe async file read (File.ReadAllBytesAsync does not exist on net48).
    private static async Task<byte[]> ReadFileBytesAsync(string path, CancellationToken ct)
    {
        using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, bufferSize: 81920, useAsync: true);
        using var ms = new MemoryStream();
        await fs.CopyToAsync(ms, 81920, ct).ConfigureAwait(false);
        return ms.ToArray();
    }

    // Source extension is already validated to {.png,.jpg,.jpeg,.webp} by ReconstructionSourceValidator.
    private static string MimeForExtension(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".jpg" or ".jpeg" => "image/jpeg",
        ".webp" => "image/webp",
        _ => "image/png",
    };

    public ReconstructionJobListResult List(int limit)
        => _ledger.List(limit);

    public ReconstructionJobStatusResult Status(Guid jobId)
    {
        var job = FindJob(jobId);
        if (job is null)
            return new ReconstructionJobStatusResult(
                false,
                null,
                false,
                Failure("not_found", "Reconstruction job was not found.", "job_id"));
        return new ReconstructionJobStatusResult(
            true,
            job,
            ResultAvailable(job),
            null);
    }

    public async Task<ReconstructionJobStatusResult> StatusAsync(Guid jobId, CancellationToken ct)
    {
        var job = FindJob(jobId);
        if (job is null)
            return new ReconstructionJobStatusResult(
                false,
                null,
                false,
                Failure("not_found", "Reconstruction job was not found.", "job_id"));

        if (!IsTerminal(job.State) && !string.IsNullOrWhiteSpace(job.ProviderJobId))
        {
            await PollActiveJobAsync(jobId, ct).ConfigureAwait(false);
            job = FindJob(jobId) ?? job;
        }

        return new ReconstructionJobStatusResult(
            true,
            job,
            ResultAvailable(job),
            null);
    }

    public async Task<ReconstructionCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
    {
        // Acquire the per-job gate so the CancellationRequested append is serialized with any
        // in-flight background/on-demand poll — otherwise a racing poll could clobber it with Running.
        // The remote cancel call is made OUTSIDE the gate (don't hold it across a network round-trip).
        var gate = _pollLocks.GetOrAdd(jobId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(ct).ConfigureAwait(false);
        ReconstructionJobLedgerRecord job;
        try
        {
            var current = FindJob(jobId);
            if (current is null)
                return new ReconstructionCancelResult(
                    ReconstructionJobState.Error,
                    Failure("not_found", "Reconstruction job was not found.", "job_id"));

            if (IsTerminal(current.State))
                return new ReconstructionCancelResult(current.State, null);

            job = current;
            _ledger.Append(current with
            {
                State = ReconstructionJobState.CancellationRequested,
                UpdatedAt = DateTimeOffset.UtcNow,
            });
        }
        finally
        {
            gate.Release();
        }

        if (!string.IsNullOrWhiteSpace(job.ProviderJobId))
            await _provider.CancelAsync(HandleFor(job), ct).ConfigureAwait(false);

        return new ReconstructionCancelResult(ReconstructionJobState.CancellationRequested, null);
    }

    public ReconstructionJobResultEnvelope Result(Guid jobId)
    {
        var job = FindJob(jobId);
        if (job is null)
            return new ReconstructionJobResultEnvelope(
                false,
                jobId,
                null,
                false,
                Array.Empty<ReconstructionWarning>(),
                Failure("not_found", "Reconstruction job was not found.", "job_id"));

        var warnings = new List<ReconstructionWarning>();
        var available = ResultAvailable(job);
        if (job.ResultArtifactId.HasValue && !available)
        {
            warnings.Add(new ReconstructionWarning(
                "result_artifact_missing",
                "The reconstruction package artifact referenced by the job ledger is missing.",
                new Dictionary<string, object?>
                {
                    ["result_artifact_id"] = job.ResultArtifactId.Value.ToString("D"),
                }));
        }

        return new ReconstructionJobResultEnvelope(
            true,
            jobId,
            job.ResultArtifactId,
            available,
            warnings,
            null);
    }

    public async Task PollActiveJobAsync(Guid jobId, CancellationToken ct)
    {
        var gate = _pollLocks.GetOrAdd(jobId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(ct).ConfigureAwait(false);

        try
        {
            var job = FindJob(jobId)
                ?? throw new KeyNotFoundException($"Reconstruction job '{jobId:D}' was not found.");
            if (IsTerminal(job.State) || string.IsNullOrWhiteSpace(job.ProviderJobId))
                return;

            var statusOutcome = await _provider.GetStatusAsync(HandleFor(job), ct).ConfigureAwait(false);
            var latest = FindJob(jobId) ?? job;
            if (IsTerminal(latest.State))
                return;

            switch (statusOutcome)
            {
                case InFlightStatusOutcome:
                    _ledger.Append(latest with
                    {
                        State = latest.State == ReconstructionJobState.CancellationRequested
                            ? ReconstructionJobState.CancellationRequested
                            : ReconstructionJobState.Running,
                        Stage = ReconstructionJobStage.Polling,
                        UpdatedAt = DateTimeOffset.UtcNow,
                    });
                    return;

                case FailedStatusOutcome failedStatus:
                    AppendError(latest, failedStatus.Error);
                    return;

                case ProviderCompleteStatusOutcome complete:
                    var materializing = latest with
                    {
                        State = ReconstructionJobState.Running,
                        Stage = ReconstructionJobStage.Materializing,
                        UpdatedAt = DateTimeOffset.UtcNow,
                    };
                    _ledger.Append(materializing);

                    var fetch = await _provider.FetchResultAsync(complete.UpdatedHandle, ct).ConfigureAwait(false);
                    if (fetch is FailedResultOutcome failedResult)
                    {
                        AppendError(materializing, failedResult.Error);
                        return;
                    }
                    if (fetch is not SuccessResultOutcome success)
                    {
                        AppendError(materializing, new GenerationError(
                            GenerationErrorCode.ExecutionFailed,
                            $"Reconstruction provider returned an unexpected result outcome: {fetch.GetType().Name}.",
                            Retryable: false));
                        return;
                    }

                    var materialized = await _materializer.MaterializeAsync(
                        materializing.JobId,
                        new[] { materializing.SourceArtifactId },
                        materializing.Provider,
                        materializing.ModelId,
                        success.Envelope,
                        ct).ConfigureAwait(false);
                    if (!materialized.Success)
                    {
                        AppendError(materializing, materialized.Error!);
                        return;
                    }

                    _ledger.Append(materializing with
                    {
                        State = ReconstructionJobState.Complete,
                        Stage = ReconstructionJobStage.Complete,
                        ResultArtifactId = materialized.Package!.Id,
                        ResultAvailable = true,
                        UpdatedAt = DateTimeOffset.UtcNow,
                    });
                    return;

                default:
                    AppendError(latest, new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Reconstruction provider returned an unexpected status outcome.",
                        Retryable: false));
                    return;
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            var latest = FindJob(jobId);
            if (latest is null)
                throw;

            _ledger.Append(latest with
            {
                State = ReconstructionJobState.Error,
                Stage = ReconstructionJobStage.Error,
                Error = Failure(
                    "poll_failed",
                    "Reconstruction polling or materialization failed.",
                    null,
                    retryable: true,
                    new Dictionary<string, object?>
                    {
                        ["exception_type"] = ex.GetType().Name,
                        ["exception_message"] = ex.Message,
                    }),
                UpdatedAt = DateTimeOffset.UtcNow,
            });
        }
        finally
        {
            gate.Release();
        }
    }

    private ReconstructionJobLedgerRecord? FindJob(Guid jobId)
        => _ledger.List(int.MaxValue).Jobs.FirstOrDefault(j => j.JobId == jobId);

    private bool ResultAvailable(ReconstructionJobLedgerRecord job)
        => job.ResultArtifactId.HasValue && _store.Get(job.ResultArtifactId.Value) is not null;

    private static ReconstructionJobLedgerRecord WithState(
        ReconstructionJobLedgerRecord job,
        ReconstructionJobState state,
        ReconstructionJobStage stage)
        => job with
        {
            State = state,
            Stage = stage,
            UpdatedAt = DateTimeOffset.UtcNow,
        };

    private static bool IsTerminal(ReconstructionJobState state)
        => state is ReconstructionJobState.Complete
            or ReconstructionJobState.Error
            or ReconstructionJobState.Cancelled
            or ReconstructionJobState.Interrupted;

    private static bool IsSubmittableV1Model(ReconstructionModelEntry? model)
        => model is not null
            && model.Enabled
            && string.Equals(model.Status, "stable", StringComparison.OrdinalIgnoreCase)
            && string.Equals(model.Task, "single_image_to_3d", StringComparison.Ordinal)
            && model.PipelineRoles.Contains("single_image_to_3d", StringComparer.Ordinal);

    private static ReconstructionSubmitResult SubmitFail(
        string code,
        string message,
        string? field)
        => new(false, null, Failure(code, message, field));

    private static ReconstructionFailure Failure(
        string code,
        string message,
        string? field,
        bool retryable = false,
        IReadOnlyDictionary<string, object?>? details = null)
        => new(code, message, retryable, field, details ?? new Dictionary<string, object?>());

    private static Uri? OptionalUri(string? value)
        => Uri.TryCreate(value, UriKind.Absolute, out var uri) ? uri : null;

    private static ProviderJobHandle HandleFor(ReconstructionJobLedgerRecord job)
        => new(
            job.ProviderJobId!,
            OptionalUri(job.ProviderStatusUrl),
            OptionalUri(job.ProviderResponseUrl),
            OptionalUri(job.ProviderCancelUrl),
            string.IsNullOrWhiteSpace(job.ProviderCancelHttpMethod) ? null : job.ProviderCancelHttpMethod);

    // Maps a shared GenerationError onto the public ReconstructionFailure DTO at the manager
    // boundary and records a terminal ledger entry. A cancelled provider state maps to the Cancelled
    // job state/stage; everything else is a job Error.
    private void AppendError(ReconstructionJobLedgerRecord job, GenerationError error)
    {
        var cancelled = error.Code == GenerationErrorCode.Cancelled;
        _ledger.Append(job with
        {
            State = cancelled ? ReconstructionJobState.Cancelled : ReconstructionJobState.Error,
            Stage = cancelled ? ReconstructionJobStage.Cancelled : ReconstructionJobStage.Error,
            Error = ReconstructionErrorMapping.ToFailure(error),
            UpdatedAt = DateTimeOffset.UtcNow,
        });
    }

    /// <summary>
    /// Flips every non-terminal ledger job to <see cref="ReconstructionJobState.Interrupted"/> —
    /// called once on subsystem construction to settle jobs whose background loops were abandoned by a
    /// plugin reload/crash. Terminal records are left untouched. Provider job id + status/response/
    /// cancel URLs are preserved (carried by <c>record with { … }</c>) so an explicit cancel can still
    /// reach the remote job; there is NO automatic remote resume.
    /// </summary>
    public void ReconcileInterruptedJobs()
    {
        foreach (var record in _ledger.List(int.MaxValue).Jobs)
        {
            if (IsTerminal(record.State)) continue;

            _ledger.Append(record with
            {
                State = ReconstructionJobState.Interrupted,
                Stage = ReconstructionJobStage.Error,
                Error = new ReconstructionFailure(
                    "interrupted",
                    "Job interrupted by plugin reload.",
                    Retryable: true,
                    Field: null,
                    Details: new Dictionary<string, object?>()),
                UpdatedAt = DateTimeOffset.UtcNow,
            });
        }
    }

    // Kicks a per-job background poll loop, linked to the shutdown token and tracked for drain on
    // Dispose. The loop reuses PollActiveJobAsync, so it shares the per-job single-flight gate with
    // any on-demand StatusAsync caller — exactly one terminal transition + materialization per job.
    private void StartBackgroundLoop(ReconstructionJobLedgerRecord record)
    {
        if (_disposed || _shutdownCts.IsCancellationRequested)
            return;

        var linked = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
        var running = new RunningJob(record, linked);
        // Assign Loop BEFORE publishing into _runningJobs. Otherwise Dispose could observe a
        // half-initialized entry (Loop == Task.CompletedTask), conclude everything is drained, dispose
        // _shutdownCts/_concurrency, and then the real loop starts and touches disposed primitives.
        // Task.Run queues to the thread pool, so the loop cannot start — let alone finish and
        // self-remove — before the publish line below executes on this thread.
        running.Loop = Task.Run(() => RunJobAsync(record.JobId, running), CancellationToken.None);
        _runningJobs[record.JobId] = running;
    }

    private async Task RunJobAsync(Guid jobId, RunningJob running)
    {
        var ct = running.Cts.Token;
        var acquired = false;
        try
        {
            await _concurrency.WaitAsync(ct).ConfigureAwait(false);
            acquired = true;

            while (true)
            {
                ct.ThrowIfCancellationRequested();
                await PollActiveJobAsync(jobId, ct).ConfigureAwait(false);

                var job = FindJob(jobId);
                if (job is null || IsTerminal(job.State))
                    return;

                await Task.Delay(_pollInterval, ct).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            // Shutdown or job cancellation: leave the ledger record non-terminal. Startup reconcile
            // (a separate task) flips lingering non-terminal jobs to Interrupted on next load.
        }
        catch (Exception ex)
        {
            var latest = FindJob(jobId);
            if (latest is not null && !IsTerminal(latest.State))
                AppendError(latest, new GenerationError(
                    GenerationErrorCode.ExecutionFailed, ex.Message, Retryable: false));
        }
        finally
        {
            _runningJobs.TryRemove(jobId, out _);
            if (acquired) _concurrency.Release();
            running.Cts.Dispose();
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        try { _shutdownCts.Cancel(); }
        catch (ObjectDisposedException) { }

        var loops = _runningJobs.Values.Select(r => r.Loop).ToArray();
        bool drained;
        try
        {
            // Task.WaitAll returns false on timeout. Faulted/cancelled loops surface as an
            // AggregateException — they ARE observed-complete, so treat that as drained.
            drained = loops.Length == 0 || Task.WaitAll(loops, TimeSpan.FromSeconds(5));
        }
        catch (AggregateException)
        {
            drained = true;
        }

        if (drained)
        {
            _shutdownCts.Dispose();
            _concurrency.Dispose();
        }
        // else: a loop did not observe cancellation within the drain budget. Intentionally leave
        // _shutdownCts and _concurrency undisposed — a straggler may still read the token or call
        // _concurrency.Release(), and disposing here would turn it into an ObjectDisposedException
        // fault. Correctness (never dispose an object another thread may touch) outranks reclaiming.
    }
}
