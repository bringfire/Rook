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
    ReconstructionFailure? Failure,
    // Typed result discriminator owned by the manager (derived from the job's persisted task), so the
    // handler is a pure serializer and never re-infers the kind from the artifact/catalog. For a
    // non-3D result, AssetRoles carries the derived artifact's file roles (e.g. image, mask).
    string ResultKind = "",
    IReadOnlyList<string>? AssetRoles = null);

public sealed class ReconstructionJobManager : IDisposable
{
    public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
    public const int DefaultMaxConcurrentJobs = 2;

    private readonly ArtifactStore _store;
    private readonly ReconstructionModelCatalog _catalog;
    private readonly JsonlReconstructionJobLedger _ledger;
    private readonly IReconstructionProvider _provider;
    private readonly ReconstructionPackageMaterializer _materializer;
    private readonly ReconstructionPreprocessMaterializer _preprocessMaterializer;
    private readonly IReconstructionSourceImagePublisher _sourcePublisher;

    // Per-job single-flight gate, shared by the background loop and on-demand StatusAsync/poll
    // callers: every poller acquires it, re-reads the freshest ledger record, and returns early if
    // the job is already terminal — so exactly one terminal transition + materialization occurs.
    private readonly ConcurrentDictionary<Guid, SemaphoreSlim> _pollLocks = new();

    // Background execution lifecycle (W6). No startup reconcile here (that is a separate task).
    private readonly TimeSpan _pollInterval;
    private readonly CancellationTokenSource _shutdownCts = new();
    private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();

    // Job-keyed multi-view provenance: front + filled-slot source ids in resolved order. Read at the
    // 3D materialize site (PollActiveJobAsync), which is shared by the background loop and on-demand
    // StatusAsync, so it must be lookup-by-jobId. In-memory only — the ledger keeps the single front id.
    private readonly ConcurrentDictionary<Guid, IReadOnlyList<Guid>> _jobSourceArtifactIds = new();

    private readonly SemaphoreSlim _concurrency = new(DefaultMaxConcurrentJobs, DefaultMaxConcurrentJobs);
    private bool _disposed;

    public ReconstructionJobManager(
        ArtifactStore store,
        ReconstructionModelCatalog catalog,
        JsonlReconstructionJobLedger ledger,
        IReconstructionProvider provider,
        ReconstructionPackageMaterializer materializer,
        ReconstructionPreprocessMaterializer preprocessMaterializer,
        IReconstructionSourceImagePublisher sourcePublisher,
        TimeSpan? pollInterval = null)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _materializer = materializer ?? throw new ArgumentNullException(nameof(materializer));
        _preprocessMaterializer = preprocessMaterializer ?? throw new ArgumentNullException(nameof(preprocessMaterializer));
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
        if (!IsSubmittableImageModel(model, request.AllowExperimentalModel))
            return SubmitFail("invalid_request", "Requested reconstruction model is not available.", "model_id");

        if (request.PreprocessingChain.Count != 0)
        {
            return SubmitFail(
                "invalid_request",
                "preprocessing_chain execution is not implemented in v0.",
                "preprocessing_chain");
        }

        if (model!.Options is not null)
        {
            // Catalog-described model: validate + default-fill + omit-ignored via the shared validator.
            // The legacy enable_pbr/enable_geometry guards are subsumed (and would reject the structured
            // options as unknown keys), so they only run for verbatim-options models below.
            var optionsResult = ReconstructionOptionsValidator.Validate(request.Options, model);
            if (!optionsResult.Success)
                return new ReconstructionSubmitResult(false, null, optionsResult.Failure);
            request = request with { Options = optionsResult.Options };
        }
        else
        {
            // Legacy verbatim-options models (e.g. Rapid): keep the existing pbr/geometry guards.
            if (IsJsonTrue(request.Options, "enable_pbr") && IsJsonTrue(request.Options, "enable_geometry"))
            {
                return SubmitFail(
                    "invalid_request",
                    "enable_geometry=true requests geometry-only output and cannot be combined with "
                    + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
                    + "enable_pbr to request geometry-only output.",
                    "options");
            }

            if (IsJsonTrue(request.Options, "enable_pbr") && !model.SupportsPbr)
            {
                return SubmitFail(
                    "invalid_request",
                    $"Model '{model.ModelId}' does not support reliable PBR output. Submit without "
                    + "enable_pbr for the model's default output, or choose a PBR-capable model.",
                    "options");
            }
        }

        return await SubmitCoreAsync(request, model, "single_image_to_3d", ct).ConfigureAwait(false);
    }

    /// <summary>
    /// Dedicated entry for the explicit background-removal op. Resolves a remove_background catalog
    /// model: when an explicit model_id is supplied it must itself be a remove_background entry —
    /// an explicit non-remove_background model_id is REJECTED (null), never silently substituted; the
    /// catalog default (first enabled remove_background entry) applies only when model_id is omitted.
    /// Then drives the shared submit body with task=remove_background. No pbr/geometry guard — those
    /// options are irrelevant to background removal.
    /// </summary>
    public async Task<ReconstructionSubmitResult> SubmitRemoveBackgroundAsync(
        ReconstructionSubmitRequest request,
        CancellationToken ct)
    {
        var model = ResolveRemoveBackgroundModel(request.ModelId);
        if (model is null)
            return SubmitFail("invalid_request", "No background-removal model is available.", "model_id");

        return await SubmitCoreAsync(request with { ModelId = model.ModelId }, model, "remove_background", ct)
            .ConfigureAwait(false);
    }

    // Shared submit body for every reconstruction task: source validate → read bytes → publish to fal
    // CDN → provider submit → ledger append of the queued/submitting/polling records. The persisted
    // task discriminates downstream behavior (materialization, result envelope) in later tasks. Caller
    // is responsible for resolving + gating the model.
    private async Task<ReconstructionSubmitResult> SubmitCoreAsync(
        ReconstructionSubmitRequest request,
        ReconstructionModelEntry model,
        string task,
        CancellationToken ct)
    {
        // ── Pass A: resolve the effective slot→artifact map and validate every slot (pre-ledger) so a
        // rejected submit creates no phantom ledger job and typed failures aren't swallowed by the
        // publish try below. The front slot preserves the original single-source error semantics. ──
        var resolution = ResolveViews(request, model);
        if (!resolution.Success)
            return new ReconstructionSubmitResult(false, null, resolution.Failure);

        var validatedViews = new List<(ResolvedView View, string AbsolutePath)>();
        foreach (var rv in resolution.Views)
        {
            var isFront = string.Equals(rv.Slot, "front", StringComparison.Ordinal);
            var artifact = _store.Get(rv.ArtifactId);
            if (artifact is null)
                return isFront
                    ? SubmitFail("invalid_request", "source_artifact_id was not found.", "source_artifact_id")
                    : SubmitFail("invalid_request", $"artifact for slot '{rv.Slot}' was not found.", "views");

            var validation = ReconstructionSourceValidator.Validate(_store, artifact, rv.Role);
            if (!validation.Success)
            {
                if (isFront)
                    return new ReconstructionSubmitResult(false, null, validation.Failure);
                var f = validation.Failure!;
                var details = f.Details.ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.Ordinal);
                details["slot"] = rv.Slot;
                return new ReconstructionSubmitResult(false, null, new ReconstructionFailure(
                    f.Code, f.Message, f.Retryable, f.Field ?? "views", details));
            }
            validatedViews.Add((rv, validation.AbsolutePath!));
        }

        var jobId = Guid.NewGuid();
        var queued = ReconstructionJobLedgerRecord.Queued(
            jobId,
            request.ModelId,
            request.SourceArtifactId,
            request.SourceRole,
            DeriveTextureExpected(request.Options, model),
            task);
        _ledger.Append(queued);

        var submitting = WithState(
            queued,
            ReconstructionJobState.Running,
            ReconstructionJobStage.Submitting);
        _ledger.Append(submitting);

        // sourceArtifactIds (front + filled slots, resolved order) is read in the post-try switch by
        // Task 1.10's carrier population, so declare it above the try. providerViews stays inside.
        var sourceArtifactIds = new List<Guid>();
        ProviderSubmitOutcome submitOutcome;
        try
        {
            // The validator already resolved + length-cap-validated each AbsolutePath. Read bytes here
            // (manager owns the store) and publish each slot's image; pass only bytes/mime/fileName so
            // the provider/publisher stay storage-agnostic. Order is front-first (ResolveViews order).
            var providerViews = new List<ReconstructionProviderViewUrl>();
            foreach (var (rv, absolutePath) in validatedViews)
            {
                var bytes = await ReadFileBytesAsync(absolutePath, ct).ConfigureAwait(false);
                var mime = MimeForExtension(absolutePath);
                var fileName = $"rook-reconstruction-{rv.ArtifactId:D}-{rv.Slot}{Path.GetExtension(absolutePath)}";
                var url = await _sourcePublisher.PublishAsync(bytes, mime, fileName, ct).ConfigureAwait(false);
                providerViews.Add(new ReconstructionProviderViewUrl(rv.Field, url));
                sourceArtifactIds.Add(rv.ArtifactId);
            }

            submitOutcome = await _provider.SubmitAsync(
                new ReconstructionProviderSubmitRequest(request.ModelId, providerViews, request.Options),
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
                // Stash full multi-view provenance for the materialize step (queued only — failed
                // submits never start a loop, so this avoids a stale entry). Read in PollActiveJobAsync.
                _jobSourceArtifactIds[jobId] = sourceArtifactIds.ToArray();
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
        {
            try
            {
                await _provider.CancelAsync(HandleFor(job), ct).ConfigureAwait(false);
            }
            catch (ReconstructionCredentialMissingException)
            {
                // Best-effort remote cancel hit a missing fal key. CancellationRequested was already
                // recorded above; surface a typed failure instead of an unhandled throw. Ledger
                // semantics unchanged.
                return new ReconstructionCancelResult(
                    ReconstructionJobState.CancellationRequested,
                    ReconstructionErrorMapping.MissingCredentialFailure());
            }
        }

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
        var assetRoles = Array.Empty<string>();
        if (job.ResultArtifactId.HasValue && !available)
        {
            warnings.Add(new ReconstructionWarning(
                "result_artifact_missing",
                "The result artifact referenced by the job ledger is missing.",
                new Dictionary<string, object?>
                {
                    ["result_artifact_id"] = job.ResultArtifactId.Value.ToString("D"),
                }));
        }
        else if (available)
        {
            var package = _store.Get(job.ResultArtifactId!.Value)!;
            assetRoles = package.Files
                .Select(f => f.Role)
                .ToArray();
            // Texture-degradation warnings are a 3D-package concern; skip them for non-3D results.
            if (string.Equals(job.Task, "remove_background", StringComparison.Ordinal) == false)
            {
                warnings.AddRange(BuildTextureWarnings(
                    job.TextureExpected,
                    _catalog.Find(job.ModelId),
                    assetRoles));
                var mm = BuildMaterialMapsMissingWarning(package);
                if (mm is not null) warnings.Add(mm);
            }
        }

        return new ReconstructionJobResultEnvelope(
            true,
            jobId,
            job.ResultArtifactId,
            available,
            warnings,
            null,
            ResultKindForTask(job.Task),
            assetRoles);
    }

    // The manager owns the result-kind discriminator: it maps the job's persisted task to the typed
    // result kind (which equals the produced artifact's kind). The handler serializes this verbatim.
    private static string ResultKindForTask(string task)
        => string.Equals(task, "remove_background", StringComparison.Ordinal)
            ? ReconstructionArtifactKinds.PreprocessedImage
            : ReconstructionArtifactKinds.Package;

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

                    // Branch materialization on the persisted task: a remove_background job produces a
                    // derived preprocessed_image linked to its source; everything else (3D) writes a
                    // reconstruction_package. Both put their artifact in the result's Package field, so
                    // the completed record's ResultArtifactId is set uniformly below.
                    var materialized = string.Equals(
                        materializing.Task, "remove_background", StringComparison.Ordinal)
                        ? await _preprocessMaterializer.MaterializeAsync(
                            materializing.JobId,
                            new[] { materializing.SourceArtifactId },
                            materializing.Provider,
                            materializing.ModelId,
                            success.Envelope,
                            ct).ConfigureAwait(false)
                        : await _materializer.MaterializeAsync(
                            materializing.JobId,
                            _jobSourceArtifactIds.TryGetValue(materializing.JobId, out var allSourceIds)
                                ? allSourceIds
                                : new[] { materializing.SourceArtifactId },
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
        catch (ReconstructionCredentialMissingException)
        {
            // Missing fal key during status/result polling → typed missing_credential, not the opaque
            // poll_failed below. MUST stay before the generic Exception catch.
            var latest = FindJob(jobId);
            if (latest is null)
                throw;

            _ledger.Append(latest with
            {
                State = ReconstructionJobState.Error,
                Stage = ReconstructionJobStage.Error,
                Error = ReconstructionErrorMapping.MissingCredentialFailure(),
                UpdatedAt = DateTimeOffset.UtcNow,
            });
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

    // Capability-based 3D submit gate: enabled + (stable OR explicit experimental override) + has an
    // importable 3D output role (model_glb/model_obj) + accepts input (a source_field, or view_slots).
    // allowExperimental is a submit-time dev/test override; it relaxes ONLY the stable clause and is
    // honored only for an explicitly named model_id (see SubmitAsync). It never affects model resolution.
    internal static bool IsSubmittable3DModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => model is not null
            && model.Enabled
            && (allowExperimental || string.Equals(model.Status, "stable", StringComparison.OrdinalIgnoreCase))
            && (model.OutputRoles.Contains("model_glb", StringComparer.Ordinal)
                || model.OutputRoles.Contains("model_obj", StringComparer.Ordinal))
            && (!string.IsNullOrWhiteSpace(model.Input?.SourceField)
                || (model.Input?.ViewSlots is { Length: > 0 }));

    // Image submit must reject mesh models (which also output model_glb); requires an image input.
    internal static bool IsSubmittableImageModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => IsSubmittable3DModel(model, allowExperimental)
            && model!.InputTypes.Contains("image_url", StringComparer.Ordinal);

    // Mesh submit must reject image models; requires a mesh input (model_url or single_model mode).
    internal static bool IsSubmittableMeshModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => IsSubmittable3DModel(model, allowExperimental)
            && (model!.InputTypes.Contains("model_url", StringComparer.Ordinal)
                || string.Equals(model.Input?.Mode, "single_model", StringComparison.Ordinal));

    private sealed record ResolvedView(string Slot, Guid ArtifactId, string Role, string Field);
    private sealed record ViewResolution(bool Success, IReadOnlyList<ResolvedView> Views, ReconstructionFailure? Failure);

    // Resolves the effective slot→artifact map for a submit. The canonical front (source_artifact_id +
    // source_role) is immutable: a views[] "front" entry is accepted only as a redundant restatement
    // (same artifact AND role), never an override. Non-front views must map to a declared model slot
    // and be unique. Output is ordered front-first, then declared view_slots order.
    private static ViewResolution ResolveViews(ReconstructionSubmitRequest request, ReconstructionModelEntry model)
    {
        var slots = model.Input?.ViewSlots ?? Array.Empty<ReconstructionViewSlot>();
        var byRole = slots.ToDictionary(s => s.Role, StringComparer.Ordinal);

        var frontField = byRole.TryGetValue("front", out var frontSlot)
            ? frontSlot.Field
            : (model.Input?.SourceField ?? "input_image_url");

        var ordered = new Dictionary<string, ResolvedView>(StringComparer.Ordinal)
        {
            ["front"] = new ResolvedView("front", request.SourceArtifactId, request.SourceRole, frontField),
        };

        foreach (var v in request.Views)
        {
            if (string.Equals(v.Slot, "front", StringComparison.Ordinal))
            {
                // Canonical-front restatement only: must match artifact AND role.
                if (v.ArtifactId != request.SourceArtifactId
                    || !string.Equals(v.Role, request.SourceRole, StringComparison.Ordinal))
                {
                    return Conflict("views", "views.front must match source_artifact_id and source_role.", "conflicting_front");
                }
                continue;   // redundant restatement; canonical front already seeded
            }

            if (!byRole.ContainsKey(v.Slot))
                return Conflict("views", $"slot '{v.Slot}' is not supported by this model.", "unsupported_slot");

            if (ordered.ContainsKey(v.Slot))
                return Conflict("views", $"slot '{v.Slot}' appears more than once.", "duplicate_slot");

            ordered[v.Slot] = new ResolvedView(v.Slot, v.ArtifactId, v.Role, byRole[v.Slot].Field);
        }

        var result = new List<ResolvedView> { ordered["front"] };
        foreach (var slot in slots)
        {
            if (string.Equals(slot.Role, "front", StringComparison.Ordinal)) continue;
            if (ordered.TryGetValue(slot.Role, out var rv)) result.Add(rv);
        }

        return new ViewResolution(true, result, null);
    }

    private static ViewResolution Conflict(string field, string message, string reason)
        => new(false, Array.Empty<ResolvedView>(),
            new ReconstructionFailure("invalid_request", message, false, field,
                new Dictionary<string, object?> { ["reason"] = reason }));

    // A model is submittable for background removal when it is enabled and its catalog task is
    // remove_background. Unlike the 3D gate this does NOT require status=="stable" — bg-removal models
    // ship experimental in v1 (and bg-removal is never surfaced by the 3D-only `models` op anyway).
    private static bool IsSubmittableRemoveBackgroundModel(ReconstructionModelEntry? model)
        => model is not null
            && model.Enabled
            && string.Equals(model.Task, "remove_background", StringComparison.Ordinal);

    // Resolves the model that will service a background-removal submit. When an explicit model_id is
    // supplied it must itself be a remove_background entry: a non-remove_background model_id is
    // rejected (returns null) — we never silently substitute the bg-removal default for an explicitly
    // requested model. The catalog default (first enabled remove_background entry) is used ONLY when
    // model_id is omitted. Returns null when no usable background-removal model is available.
    private ReconstructionModelEntry? ResolveRemoveBackgroundModel(string? requestedModelId)
    {
        if (!string.IsNullOrWhiteSpace(requestedModelId))
        {
            var requested = _catalog.Find(requestedModelId!);
            return IsSubmittableRemoveBackgroundModel(requested) ? requested : null;
        }

        return _catalog
            .List(includeExperimental: true, includeHidden: true)
            .FirstOrDefault(IsSubmittableRemoveBackgroundModel);
    }

    private static bool? ReadStrictBool(JsonObject options, string key)
    {
        if (options is null) return null;
        if (!options.TryGetPropertyValue(key, out var node)) return null;
        if (node is not JsonValue value) return null;
        return value.TryGetValue<bool>(out var parsed) ? parsed : (bool?)null;
    }

    private static string? ReadString(JsonObject options, string key)
        => options is not null
            && options.TryGetPropertyValue(key, out var node)
            && node is JsonValue value
            && value.TryGetValue<string>(out var text)
                ? text
                : null;

    internal static bool DeriveTextureExpected(JsonObject options, ReconstructionModelEntry model)
    {
        // Catalog-described (Pro) path: generate_type drives texture expectation. Normal expects a
        // texture even when enable_pbr=false; Geometry never does.
        if (ReadString(options, "generate_type") is { } generateType)
        {
            if (string.Equals(generateType, "Geometry", StringComparison.Ordinal)) return false;
            if (string.Equals(generateType, "Normal", StringComparison.Ordinal)) return true;
        }

        // Meshy family: once the model declares should_texture, that option OWNS texture expectation
        // and the legacy enable_pbr/enable_geometry rules do NOT apply (enable_pbr only selects which
        // maps, not whether texturing happens).
        if (ModelDeclaresOption(model, "should_texture"))
        {
            var shouldTexture = ReadStrictBool(options, "should_texture");
            if (shouldTexture == true) return true;
            if (shouldTexture == false) return false;
            return model.DefaultTextureExpected;
        }

        if (ReadStrictBool(options, "enable_geometry") == true) return false;   // legacy rule 1
        var pbr = ReadStrictBool(options, "enable_pbr");
        if (pbr == true) return true;                                          // legacy rule 2
        if (pbr == false) return false;                                        // legacy rule 3
        return model.DefaultTextureExpected;                                   // legacy rule 4
    }

    private static bool ModelDeclaresOption(ReconstructionModelEntry model, string key)
        => model.Options is { } opts
            && Array.Exists(opts, o => string.Equals(o.Key, key, StringComparison.Ordinal));

    // Pure: classifies a delivered reconstruction result against the request's texture expectation and
    // the model's catalog capability. No store/state access — callers pass the delivered role names.
    // At most one warning; output_roles is deliberately NOT consulted (advertised vocabulary, not a
    // guarantee). material_mtl alone counts as not-degraded.
    internal static IReadOnlyList<ReconstructionWarning> BuildTextureWarnings(
        bool textureExpected,
        ReconstructionModelEntry? model,
        IReadOnlyCollection<string> deliveredRoles)
    {
        if (!textureExpected || model is null)
            return Array.Empty<ReconstructionWarning>();

        var hasMaterial = deliveredRoles.Any(r =>
            string.Equals(r, ReconstructionFileRoles.MaterialMtl, StringComparison.Ordinal));
        var hasTexture = deliveredRoles.Any(r => r.StartsWith("texture", StringComparison.Ordinal));
        if (hasMaterial || hasTexture)
            return Array.Empty<ReconstructionWarning>();

        return new[]
        {
            new ReconstructionWarning(
                "result_missing_texture",
                "Texture output was expected, but the delivered package contains no material or texture assets.",
                new Dictionary<string, object?>
                {
                    ["model_id"] = model.ModelId,
                    ["delivered_roles"] = deliveredRoles.ToArray(),
                }),
        };
    }

    // Compares the texture filenames referenced by the package's MTL blob against the delivered
    // texture filenames resolved from provider_result_json. Returns a material_maps_missing warning
    // when at least one referenced filename is absent from the delivered set, or null otherwise.
    // Only runs when the package has both model_obj and material_mtl; guarded try/catch on all I/O
    // and JSON so a bad blob never blocks the result envelope.
    private ReconstructionWarning? BuildMaterialMapsMissingWarning(Artifact package)
    {
        bool Has(string role) => package.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal));
        if (!Has(ReconstructionFileRoles.ModelObj) || !Has(ReconstructionFileRoles.MaterialMtl)) return null;

        string mtl;
        JsonObject? providerJson;
        try
        {
            mtl = File.ReadAllText(_store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.MaterialMtl));
            providerJson = JsonNode.Parse(File.ReadAllText(
                _store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ProviderResultJson))) as JsonObject;
        }
        catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException or InvalidOperationException or KeyNotFoundException)
        {
            return null;
        }
        if (providerJson is null) return null;

        // Texture integrity: compare against delivered TEXTURE filenames only (role starts with "texture"),
        // not model/material/thumbnail names.
        var resolved = ReconstructionProviderFileNames.ProviderFileNamesByRole(providerJson, package);
        var delivered = new HashSet<string>(
            resolved.Where(kv => kv.Key.StartsWith("texture", StringComparison.Ordinal)).Select(kv => kv.Value),
            StringComparer.OrdinalIgnoreCase);
        var referenced = ObjMaterialReferences.ReferencedMapFileNames(mtl);
        var missing = referenced.Where(r => !delivered.Contains(r)).ToList();
        if (missing.Count == 0) return null;

        // map_Kd is the base-color map; its absence causes the white/untextured appearance.
        var baseColorRef = ObjMaterialReferences.MapFileName(mtl, "map_Kd");
        var missingBaseColor = baseColorRef is not null && missing.Contains(baseColorRef);

        return new ReconstructionWarning(
            "material_maps_missing",
            "The OBJ material references texture maps not present in the package; the model will import "
            + (missingBaseColor
                ? "without its base-color texture (it will appear untextured)."
                : "with some maps missing."),
            new Dictionary<string, object?>
            {
                ["missing_maps"]      = missing,
                ["missing_base_color"] = missingBaseColor,
                ["material_role"]     = ReconstructionFileRoles.MaterialMtl,
                ["asset_role"]        = ReconstructionFileRoles.ModelObj,
            });
    }

    private static bool IsJsonTrue(JsonObject options, string key)
    {
        if (options is null) return false;
        if (!options.TryGetPropertyValue(key, out var node)) return false;
        if (node is not JsonValue value) return false;
        return value.TryGetValue<bool>(out var parsed) && parsed;
    }

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
            _jobSourceArtifactIds.TryRemove(jobId, out _);   // best-effort housekeeping; fallback covers absence
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
