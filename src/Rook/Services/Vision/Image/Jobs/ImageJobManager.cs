using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    internal delegate ImageArtifactRequestFactory? ImageArtifactRequestFactorySelector(
        ResolvedImageModel model,
        ResultArtifact artifact);

    public sealed class ImageJobManager : IImageJobManager, IDisposable
    {
        public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
        public const int DefaultMaxConcurrentJobs = 2;

        private const int MaxListLimit = 100;

        private readonly IImageProviderRegistry _registry;
        private readonly ArtifactStore _artifactStore;
        private readonly ImageArtifactMaterializer _materializer;
        private readonly IImageJobClock _clock;
        private readonly IImageJobIdGenerator _idGenerator;
        private readonly IImageJobLedger _ledger;
        private readonly ImageArtifactRequestFactorySelector? _requestFactorySelector;
        private readonly TimeSpan _pollInterval;
        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _shutdownCts = new();
        private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();
        private readonly ConcurrentDictionary<Guid, ImageJobRecord> _records = new();

        internal Action<Guid>? BeforeLocalCancelTryUpdateForTests { get; set; }
        internal Action<Guid>? BeforeCompleteTransitionForTests { get; set; }

        public ImageJobManager(
            IImageProviderRegistry registry,
            ArtifactStore artifactStore,
            IImageJobClock? clock = null,
            IImageJobIdGenerator? idGenerator = null,
            TimeSpan? pollInterval = null,
            int maxConcurrentJobs = DefaultMaxConcurrentJobs)
            : this(
                registry,
                artifactStore,
                clock,
                idGenerator,
                pollInterval,
                maxConcurrentJobs,
                materializer: null,
                requestFactorySelector: null,
                ledger: null)
        {
        }

        internal ImageJobManager(
            IImageProviderRegistry registry,
            ArtifactStore artifactStore,
            ImageArtifactRequestFactorySelector? requestFactorySelector)
            : this(
                registry,
                artifactStore,
                clock: null,
                idGenerator: null,
                pollInterval: null,
                maxConcurrentJobs: DefaultMaxConcurrentJobs,
                materializer: null,
                requestFactorySelector: requestFactorySelector,
                ledger: null)
        {
        }

        internal ImageJobManager(
            IImageProviderRegistry registry,
            ArtifactStore artifactStore,
            IImageJobClock? clock,
            IImageJobIdGenerator? idGenerator,
            TimeSpan? pollInterval,
            int maxConcurrentJobs,
            ImageArtifactMaterializer? materializer,
            ImageArtifactRequestFactorySelector? requestFactorySelector,
            IImageJobLedger? ledger = null)
        {
            if (maxConcurrentJobs <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(maxConcurrentJobs),
                    "Max concurrent jobs must be positive.");

            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _materializer = materializer ?? new ImageArtifactMaterializer();
            _clock = clock ?? new SystemImageJobClock();
            _idGenerator = idGenerator ?? new GuidImageJobIdGenerator();
            _ledger = ledger ?? new JsonlImageJobLedger();
            _requestFactorySelector = requestFactorySelector;
            _pollInterval = pollInterval ?? DefaultPollInterval;
            _concurrency = new SemaphoreSlim(maxConcurrentJobs, maxConcurrentJobs);
        }

        public Task<ImageJobSubmitResult> SubmitAsync(
            ImageJobStartRequest start,
            CancellationToken ct)
        {
            if (start is null)
                return Task.FromResult(ImageJobSubmitResult.Fail(InvalidRequest(
                    "Request is null.",
                    nameof(start))));

            var request = start.Request;
            var model = start.ResolvedModel;
            if (model is null && !_registry.TryResolve(request.Model, out model))
                return Task.FromResult(ImageJobSubmitResult.Fail(InvalidRequest(
                    $"Unknown image model: '{request.Model ?? "<null>"}'.",
                    nameof(request.Model))));

            var validation = model.OptionsCodec.Validate(
                request,
                request.Options,
                model.Capability);
            if (!validation.Success)
                return Task.FromResult(ImageJobSubmitResult.Fail(new GenerationError(
                    GenerationErrorCode.InvalidRequest,
                    validation.Message ?? "Image provider request is invalid.",
                    Retryable: false,
                    Field: validation.Field)));

            var jobId = _idGenerator.NewJobId();
            var now = _clock.UtcNow();
            var initial = new ImageJobRecord(
                jobId,
                ImageJobState.Queued,
                model.ModelId,
                model.ProviderName,
                createdAt: now,
                updatedAt: now);
            var durable = ImageJobLedgerRecordFactory.FromInitial(
                jobId,
                model.ProviderName,
                model.ModelId,
                ImageJobState.Queued,
                now);
            if (!TryAppendLedger(durable, out var appendError))
                return Task.FromResult(ImageJobSubmitResult.Fail(appendError!));

            _records[jobId] = initial;

            var jobCts = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
            var running = new RunningJob(initial, jobCts, model, start);
            _runningJobs[jobId] = running;

            _ = Task.Run(() => RunJobAsync(jobId, running));

            return Task.FromResult(ImageJobSubmitResult.Ok(jobId, ImageJobState.Queued));
        }

        public Task<ImageJobStatusResult> GetStatusAsync(
            Guid jobId,
            CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(ImageJobStatusResult.Failed(
                    ImageJobState.Error,
                    InvalidRequest("JobId must be non-empty.", nameof(jobId))));

            var record = FindLatestMergedRecord(jobId);
            if (record is null)
                return Task.FromResult(ImageJobStatusResult.Failed(
                    ImageJobState.Error,
                    UnknownJob(jobId)));

            return Task.FromResult(TranslateToStatus(record));
        }

        public async Task<ImageJobCancelResult> CancelAsync(
            Guid jobId,
            CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return ImageJobCancelResult.Fail(
                    InvalidRequest("JobId must be non-empty.", nameof(jobId)));

            if (_runningJobs.TryGetValue(jobId, out var running))
            {
                var latest = LatestRecord(jobId, running.LatestRecord);
                if (IsTerminal(latest.State))
                    return ImageJobCancelResult.Ok(latest.State);

                if (latest.ProviderHandle is { } handle)
                {
                    var remote = await TryRemoteCancelAsync(
                            running.Model.Provider,
                            handle,
                            ct)
                        .ConfigureAwait(false);
                    if (remote.Error is not null)
                        return ImageJobCancelResult.Fail(remote.Error);

                    latest = LatestRecord(jobId, latest);
                    if (IsTerminal(latest.State))
                        return ImageJobCancelResult.Ok(latest.State);
                    if (remote.AlreadyTerminal
                        && latest.State != ImageJobState.Materializing)
                        return ImageJobCancelResult.Ok(latest.State);
                }

                latest = LatestRecord(jobId, latest);
                if (IsTerminal(latest.State))
                    return ImageJobCancelResult.Ok(latest.State);

                var cancelled = TryTransitionToLocalCancelled(latest, running);
                if (cancelled.State == ImageJobState.Cancelled)
                    try { running.Cts.Cancel(); } catch { }
                return ImageJobCancelResult.Ok(cancelled.State);
            }

            if (!_records.TryGetValue(jobId, out var record))
                return ImageJobCancelResult.Fail(UnknownJob(jobId));

            if (IsTerminal(record.State))
                return ImageJobCancelResult.Ok(record.State);

            if (record.ProviderHandle is { } providerHandle)
            {
                if (!ResolveProviderByName(record.Provider, out var provider))
                    return ImageJobCancelResult.Fail(InvalidRequest(
                        $"Cannot cancel job {jobId:D}: provider '{record.Provider}' is no longer registered.",
                        nameof(record.Provider)));

                var remote = await TryRemoteCancelAsync(provider, providerHandle, ct)
                    .ConfigureAwait(false);
                if (remote.Error is not null)
                    return ImageJobCancelResult.Fail(remote.Error);

                record = LatestRecord(jobId, record);
                if (IsTerminal(record.State))
                    return ImageJobCancelResult.Ok(record.State);
                if (remote.AlreadyTerminal)
                    return ImageJobCancelResult.Ok(record.State);
            }

            record = LatestRecord(jobId, record);
            if (IsTerminal(record.State))
                return ImageJobCancelResult.Ok(record.State);

            var localCancelled = TryTransitionToLocalCancelled(record, running: null);
            return ImageJobCancelResult.Ok(localCancelled.State);
        }

        public Task<ImageJobFetchResult> FetchResultAsync(
            Guid jobId,
            CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(ImageJobFetchResult.Failed(
                    ImageJobState.Error,
                    InvalidRequest("JobId must be non-empty.", nameof(jobId))));

            var record = FindLatestMergedRecord(jobId);
            if (record is null)
                return Task.FromResult(ImageJobFetchResult.Failed(
                    ImageJobState.Error,
                    UnknownJob(jobId)));

            if (record.State != ImageJobState.Complete)
                return Task.FromResult(ImageJobFetchResult.Failed(
                    record.State,
                    record.Error ?? new GenerationError(
                        GenerationErrorCode.InvalidRequest,
                        $"Image job is not complete; current state is {record.State}.",
                        Retryable: false)));

            if (record.ResultArtifactId is not { } artifactId)
                return Task.FromResult(ImageJobFetchResult.Failed(
                    ImageJobState.Error,
                    new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Complete image job is missing a result artifact id.",
                        Retryable: false)));

            try
            {
                _ = _artifactStore.GetBlobAbsolutePath(artifactId, ImageMediaRoles.Image);
            }
            catch (Exception ex) when (
                ex is KeyNotFoundException
                || ex is FileNotFoundException
                || ex is InvalidDataException)
            {
                return Task.FromResult(ImageJobFetchResult.Failed(
                    ImageJobState.Error,
                    new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        $"Image job result artifact is unavailable: {artifactId:D}.",
                        Retryable: false,
                        Field: "result_artifact_id")));
            }

            return Task.FromResult(ImageJobFetchResult.Complete(
                artifactId,
                new[]
                {
                    new ImageJobResultFile(
                        ImageMediaRoles.Image,
                        $"/blob/{artifactId:D}/image"),
                }));
        }

        public Task<ImageJobListResult> ListJobsAsync(int limit, CancellationToken ct)
        {
            var appliedLimit = Math.Min(MaxListLimit, Math.Max(1, limit));
            var merged = new Dictionary<Guid, ImageJobRecord>();

            var read = _ledger.ReadAll();
            foreach (var record in read.Records)
                merged[record.JobId] = FromLedgerRecord(record);

            foreach (var record in _records.Values)
                merged[record.JobId] = FreshestForRead(
                    record,
                    merged.TryGetValue(record.JobId, out var existing) ? existing : null)!;

            foreach (var running in _runningJobs.Values)
            {
                var record = running.LatestRecord;
                merged[record.JobId] = FreshestForRead(
                    record,
                    merged.TryGetValue(record.JobId, out var existing) ? existing : null)!;
            }

            var jobs = merged.Values
                .OrderByDescending(r => r.UpdatedAt)
                .ThenByDescending(r => r.JobId)
                .Take(appliedLimit)
                .ToArray();
            return Task.FromResult(new ImageJobListResult(jobs, appliedLimit));
        }

        public void Dispose()
        {
            try { _shutdownCts.Cancel(); } catch { }
            _shutdownCts.Dispose();
            _concurrency.Dispose();
        }

        private async Task RunJobAsync(Guid jobId, RunningJob running)
        {
            var ct = running.Cts.Token;
            var current = running.LatestRecord;
            var provider = running.Model.Provider;

            try
            {
                await _concurrency.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    if (!TryTransitionWithLedger(
                            current,
                            ImageJobState.Submitting,
                            out current,
                            out var appendError))
                    {
                        running.LatestRecord = appendError is null
                            ? current
                            : MarkAppendFailure(current, appendError);
                        return;
                    }
                    running.LatestRecord = current;

                    var submit = await provider.SubmitAsync(
                            running.Start.Request,
                            running.Start.ResolvedMedia,
                            ct)
                        .ConfigureAwait(false);

                    switch (submit)
                    {
                        case FailedSubmitOutcome failed:
                            _ = TryTransitionWithLedger(
                                current,
                                ImageJobState.Error,
                                out current,
                                out _,
                                error: failed.Error);
                            running.LatestRecord = current;
                            return;

                        case SyncSubmitOutcome sync:
                            await CompleteResultAsync(
                                    running,
                                    current,
                                    sync.Result,
                                    ct)
                                .ConfigureAwait(false);
                            return;

                        case QueuedSubmitOutcome queued:
                            if (!TryTransitionWithLedger(
                                    current,
                                    ImageJobState.Polling,
                                    out current,
                                    out appendError,
                                    providerHandle: queued.Handle))
                            {
                                if (appendError is not null)
                                {
                                    _ = await TryRemoteCancelAsync(
                                            provider,
                                            queued.Handle,
                                            CancellationToken.None)
                                        .ConfigureAwait(false);
                                    current = MarkAppendFailure(current, appendError);
                                }
                                running.LatestRecord = current;
                                return;
                            }
                            running.LatestRecord = current;
                            break;

                        default:
                            _ = TryTransitionWithLedger(
                                current,
                                ImageJobState.Error,
                                out current,
                                out _,
                                error: UnknownOutcomeError(
                                    "submit",
                                    submit.GetType().Name));
                            running.LatestRecord = current;
                            return;
                    }

                    var handle = current.ProviderHandle!;
                    while (true)
                    {
                        ct.ThrowIfCancellationRequested();
                        var status = await provider.GetStatusAsync(handle, ct)
                            .ConfigureAwait(false);

                        switch (status)
                        {
                            case InFlightStatusOutcome:
                                await Task.Delay(_pollInterval, ct)
                                    .ConfigureAwait(false);
                                continue;

                            case ProviderCompleteStatusOutcome complete:
                                handle = complete.UpdatedHandle;
                                if (!TryTransitionWithLedger(
                                        current,
                                        ImageJobState.Materializing,
                                        out current,
                                        out appendError,
                                        providerHandle: handle))
                                {
                                    running.LatestRecord = appendError is null
                                        ? current
                                        : MarkAppendFailure(current, appendError);
                                    return;
                                }
                                running.LatestRecord = current;
                                break;

                            case FailedStatusOutcome failed:
                                _ = TryTransitionWithLedger(
                                    current,
                                    ImageJobState.Error,
                                    out current,
                                    out _,
                                    error: failed.Error);
                                running.LatestRecord = current;
                                return;

                            default:
                                _ = TryTransitionWithLedger(
                                    current,
                                    ImageJobState.Error,
                                    out current,
                                    out _,
                                    error: UnknownOutcomeError(
                                        "status",
                                        status.GetType().Name));
                                running.LatestRecord = current;
                                return;
                        }

                        break;
                    }

                    var fetch = await provider.FetchResultAsync(handle, ct)
                        .ConfigureAwait(false);
                    await CompleteResultAsync(running, current, fetch, ct)
                        .ConfigureAwait(false);
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
                    _ = TryTransitionWithLedger(
                        current,
                        ImageJobState.Cancelled,
                        out var cancelled,
                        out _,
                        error: CancelledError());
                    running.LatestRecord = cancelled;
                }
            }
            catch (Exception ex)
            {
                if (!IsTerminal(current.State))
                {
                    _ = TryTransitionWithLedger(
                        current,
                        ImageJobState.Error,
                        out var errored,
                        out _,
                        error: new GenerationError(
                            GenerationErrorCode.ExecutionFailed,
                            $"Unexpected error during image job: {ex.Message}",
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

        private async Task CompleteResultAsync(
            RunningJob running,
            ImageJobRecord current,
            ProviderResultOutcome result,
            CancellationToken ct)
        {
            if (result is FailedResultOutcome failed)
            {
                _ = TryTransitionWithLedger(
                    current,
                    ImageJobState.Error,
                    out var errored,
                    out _,
                    error: failed.Error);
                running.LatestRecord = errored;
                return;
            }

            if (result is not SuccessResultOutcome success)
            {
                _ = TryTransitionWithLedger(
                    current,
                    ImageJobState.Error,
                    out var errored,
                    out _,
                    error: UnknownOutcomeError(
                        "result",
                        result.GetType().Name));
                running.LatestRecord = errored;
                return;
            }

            var imageArtifact = success.Envelope.Artifacts
                .FirstOrDefault(a => string.Equals(
                    a.Role,
                    ImageMediaRoles.Image,
                    StringComparison.Ordinal));
            if (imageArtifact is null)
            {
                _ = TryTransitionWithLedger(
                    current,
                    ImageJobState.Error,
                    out var errored,
                    out _,
                    error: new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Provider result envelope did not contain an image artifact.",
                        Retryable: false));
                running.LatestRecord = errored;
                return;
            }

            if (current.State != ImageJobState.Materializing)
            {
                if (!TryTransitionWithLedger(
                        current,
                        ImageJobState.Materializing,
                        out current,
                        out var appendError))
                {
                    running.LatestRecord = appendError is null
                        ? current
                        : MarkAppendFailure(current, appendError);
                    return;
                }
                running.LatestRecord = current;
            }

            var requestFactory = ResolveRequestFactory(
                running.Model,
                imageArtifact);
            var materialized = await _materializer.MaterializeAsync(
                    imageArtifact,
                    ct,
                    requestFactory)
                .ConfigureAwait(false);
            if (!materialized.Success || materialized.Bytes is null)
            {
                if (IsCancellationMaterializationFailure(materialized, ct))
                    ct.ThrowIfCancellationRequested();

                _ = TryTransitionWithLedger(
                    current,
                    ImageJobState.Error,
                    out var errored,
                    out _,
                    error: materialized.Error ?? new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Image artifact could not be materialized.",
                        Retryable: false));
                running.LatestRecord = errored;
                return;
            }

            ct.ThrowIfCancellationRequested();

            var latestBeforeCreate = LatestRecord(current.JobId, current);
            if (IsTerminal(latestBeforeCreate.State))
            {
                running.LatestRecord = latestBeforeCreate;
                return;
            }

            var mimeType = materialized.MimeType ?? "image/png";
            var artifact = _artifactStore.Create(
                kind: VisionHandler.ArtifactKindGeneratedImage,
                blobs: new[]
                {
                    new BlobInput(
                        ImageMediaRoles.Image,
                        materialized.Bytes,
                        ExtensionForMime(mimeType)),
                },
                parentIds: running.Start.ParentArtifactIds,
                metadata: new Dictionary<string, JsonNode?>
                {
                    ["prompt"] = running.Start.Request.Prompt,
                    ["model"] = running.Model.ModelId,
                    ["provider"] = running.Model.ProviderName,
                    ["resolution"] = running.Start.Request.Resolution,
                    ["aspect_ratio"] = running.Start.Request.AspectRatio,
                    ["mime_type"] = mimeType,
                });

            BeforeCompleteTransitionForTests?.Invoke(current.JobId);

            var transitionWon = TryTransitionWithLedger(
                current,
                ImageJobState.Complete,
                out var complete,
                out var completeAppendError,
                resultArtifactId: artifact.Id);
            if (!transitionWon && completeAppendError is not null)
                complete = MarkAppendFailure(complete, completeAppendError);

            if (complete.State != ImageJobState.Complete
                || complete.ResultArtifactId != artifact.Id)
            {
                await DeleteArtifactQuietlyAsync(artifact.Id).ConfigureAwait(false);
            }

            running.LatestRecord = complete;
        }

        private async Task DeleteArtifactQuietlyAsync(Guid artifactId)
        {
            for (var attempt = 0; attempt < 5; attempt++)
            {
                try
                {
                    if (_artifactStore.Delete(artifactId))
                        return;
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }

                await Task.Delay(10).ConfigureAwait(false);
            }
        }

        private ImageArtifactRequestFactory? ResolveRequestFactory(
            ResolvedImageModel model,
            ResultArtifact artifact)
        {
            if (!RequiresAuthenticatedFetch(artifact))
                return null;

            var factory = _requestFactorySelector?.Invoke(model, artifact);
            if (factory is not null)
                return factory;

            return _ => ImageArtifactFetchRequest.Failed(new GenerationError(
                GenerationErrorCode.DependencyUnavailable,
                "Authenticated image artifact fetch is not configured.",
                Retryable: false));
        }

        private static bool RequiresAuthenticatedFetch(ResultArtifact artifact)
        {
            if (!artifact.ProviderMetadata.TryGetValue(
                    "requires_authenticated_fetch",
                    out var node)
                || node is null)
            {
                return false;
            }

            try { return node.GetValue<bool>(); }
            catch { return false; }
        }

        private bool TryTransitionWithLedger(
            ImageJobRecord prior,
            ImageJobState state,
            out ImageJobRecord next,
            out GenerationError? appendError,
            ProviderJobHandle? providerHandle = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null)
        {
            appendError = null;
            while (true)
            {
                var latest = LatestRecord(prior.JobId, prior);
                if (IsTerminal(latest.State))
                {
                    next = latest;
                    return false;
                }

                var candidate = BuildTransition(
                    latest,
                    state,
                    providerHandle,
                    resultArtifactId,
                    error);
                var durable = ImageJobLedgerRecordFactory.WithState(
                    ToLedgerRecord(latest),
                    state,
                    candidate.UpdatedAt,
                    providerJobId: providerHandle?.ProviderJobId,
                    resultArtifactId: resultArtifactId,
                    error: error);

                if (_records.TryUpdate(latest.JobId, candidate, latest))
                {
                    if (!TryAppendLedger(durable, out appendError))
                    {
                        next = candidate;
                        return false;
                    }

                    next = candidate;
                    return true;
                }

                if (!_records.TryGetValue(latest.JobId, out var observed))
                {
                    next = latest;
                    return false;
                }

                if (IsTerminal(observed.State))
                {
                    next = observed;
                    return false;
                }

                prior = Freshest(observed, latest);
            }
        }

        private ImageJobRecord MarkAppendFailure(
            ImageJobRecord candidate,
            GenerationError appendError)
        {
            while (true)
            {
                var errored = BuildTransition(
                    candidate,
                    ImageJobState.Error,
                    error: appendError);

                if (_records.TryUpdate(candidate.JobId, errored, candidate))
                {
                    var durable = ImageJobLedgerRecordFactory.WithState(
                        ToLedgerRecord(candidate),
                        ImageJobState.Error,
                        errored.UpdatedAt,
                        error: appendError);
                    _ = TryAppendLedger(durable, out _);
                    return errored;
                }

                if (!_records.TryGetValue(candidate.JobId, out var observed))
                    return candidate;

                if (IsTerminal(observed.State) && observed.State != candidate.State)
                    return observed;

                candidate = observed;
            }
        }

        private ImageJobLedgerRecord ToLedgerRecord(ImageJobRecord record) =>
            new(
                ImageJobLedgerRecordFactory.CurrentSchemaVersion,
                record.JobId,
                record.Provider,
                record.Model,
                record.ProviderHandle?.ProviderJobId,
                record.State,
                record.ResultArtifactId,
                ImageJobLedgerRecordFactory.SanitizeError(record.Error),
                record.CreatedAt,
                record.UpdatedAt);

        private ImageJobRecord TryTransitionToLocalCancelled(
            ImageJobRecord prior,
            RunningJob? running)
        {
            while (true)
            {
                var latest = LatestRecord(prior.JobId, prior);
                if (IsTerminal(latest.State))
                    return latest;

                var cancelled = BuildTransition(
                    latest,
                    ImageJobState.Cancelled,
                    providerHandle: null,
                    resultArtifactId: null,
                    error: CancelledError());

                BeforeLocalCancelTryUpdateForTests?.Invoke(latest.JobId);

                if (_records.TryUpdate(latest.JobId, cancelled, latest))
                {
                    if (running is not null)
                        running.LatestRecord = cancelled;
                    return cancelled;
                }

                if (!_records.TryGetValue(latest.JobId, out var observed))
                    return latest;

                if (IsTerminal(observed.State))
                    return observed;

                prior = Freshest(observed, latest);
            }
        }

        private ImageJobRecord BuildTransition(
            ImageJobRecord prior,
            ImageJobState state,
            ProviderJobHandle? providerHandle = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null) =>
            new(
                prior.JobId,
                state,
                prior.Model,
                prior.Provider,
                prior.CreatedAt,
                _clock.UtcNow(),
                providerHandle ?? prior.ProviderHandle,
                resultArtifactId ?? prior.ResultArtifactId,
                error);

        private bool TryAppendLedger(
            ImageJobLedgerRecord record,
            out GenerationError? error)
        {
            try
            {
                _ledger.Append(record);
                error = null;
                return true;
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            {
                error = new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    $"Image job ledger is unavailable: {ex.Message}",
                    Retryable: true);
                return false;
            }
        }

        private async Task<RemoteCancelResult> TryRemoteCancelAsync(
            IImageProvider provider,
            ProviderJobHandle handle,
            CancellationToken ct)
        {
            ProviderCancelOutcome outcome;
            try
            {
                outcome = await provider.CancelAsync(handle, ct)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException ex) when (!ct.IsCancellationRequested)
            {
                return RemoteCancelResult.Failed(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    $"Provider cancel failed: {ex.Message}",
                    Retryable: true));
            }
            catch (Exception ex) when (!(ex is OperationCanceledException))
            {
                return RemoteCancelResult.Failed(new GenerationError(
                    GenerationErrorCode.DependencyUnavailable,
                    $"Provider cancel failed: {ex.Message}",
                    Retryable: true));
            }

            switch (outcome)
            {
                case FailedCancelOutcome failed:
                    return RemoteCancelResult.Failed(failed.Error);

                case AlreadyTerminalOutcome:
                    return RemoteCancelResult.Terminal();

                case CanceledOutcome:
                    return RemoteCancelResult.Cancelled();

                default:
                    return RemoteCancelResult.Failed(UnknownOutcomeError(
                        "cancel",
                        outcome.GetType().Name));
            }
        }

        private bool ResolveProviderByName(
            string providerName,
            out IImageProvider provider) =>
            _registry.TryResolveProviderByName(providerName, out provider);

        private static ImageJobStatusResult TranslateToStatus(ImageJobRecord record)
        {
            return record.State switch
            {
                ImageJobState.Complete when record.ResultArtifactId is { } id =>
                    ImageJobStatusResult.Complete(id),

                ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted =>
                    ImageJobStatusResult.Failed(
                        record.State,
                        record.Error ?? new GenerationError(
                            GenerationErrorCode.ExecutionFailed,
                            $"Terminal state {record.State} without error record.",
                            Retryable: false)),

                _ => ImageJobStatusResult.InFlight(record.State, progress: null),
            };
        }

        private static bool IsTerminal(ImageJobState state) =>
            state is ImageJobState.Complete
              or ImageJobState.Error
              or ImageJobState.Cancelled
              or ImageJobState.Interrupted;

        private ImageJobRecord? FindLatestMergedRecord(Guid jobId)
        {
            _runningJobs.TryGetValue(jobId, out var running);
            var live = running?.LatestRecord
                ?? (_records.TryGetValue(jobId, out var local) ? local : null);
            var durable = FindDurableRecord(jobId);
            return FreshestForRead(live, durable);
        }

        private ImageJobRecord? FindDurableRecord(Guid jobId)
        {
            var read = _ledger.ReadAll();
            foreach (var record in read.Records)
                if (record.JobId == jobId)
                    return FromLedgerRecord(record);
            return null;
        }

        private static ImageJobRecord? FreshestForRead(
            ImageJobRecord? live,
            ImageJobRecord? durable)
        {
            if (live is null) return durable;
            if (durable is null) return live;
            if (durable.UpdatedAt > live.UpdatedAt) return durable;
            if (live.UpdatedAt > durable.UpdatedAt) return live;
            if (IsTerminal(durable.State)) return durable;
            return live;
        }

        private static ImageJobRecord FromLedgerRecord(ImageJobLedgerRecord record) =>
            new(
                record.JobId,
                record.State,
                record.Model,
                record.Provider,
                createdAt: record.CreatedAt,
                updatedAt: record.UpdatedAt,
                providerHandle: string.IsNullOrWhiteSpace(record.ProviderJobId)
                    ? null
                    : new ProviderJobHandle(record.ProviderJobId),
                resultArtifactId: record.ResultArtifactId,
                error: record.Error);

        private ImageJobRecord LatestRecord(
            Guid jobId,
            ImageJobRecord fallback) =>
            _records.TryGetValue(jobId, out var record)
                ? Freshest(record, fallback)
                : fallback;

        private static ImageJobRecord Freshest(
            ImageJobRecord record,
            ImageJobRecord running) =>
            record.UpdatedAt >= running.UpdatedAt ? record : running;

        private static bool IsCancellationMaterializationFailure(
            ImageArtifactMaterializationResult materialized,
            CancellationToken ct) =>
            ct.IsCancellationRequested
            && materialized.Error is { } error
            && (error.Code == GenerationErrorCode.Cancelled
                || error.Code == GenerationErrorCode.Interrupted);

        private static string ExtensionForMime(string mimeType) =>
            mimeType.ToLowerInvariant() switch
            {
                "image/png" => "png",
                "image/jpeg" => "jpg",
                "image/jpg" => "jpg",
                "image/webp" => "webp",
                "image/gif" => "gif",
                "image/bmp" => "bmp",
                _ => "bin",
            };

        private static GenerationError InvalidRequest(
            string message,
            string? field = null) =>
            new(
                GenerationErrorCode.InvalidRequest,
                message,
                Retryable: false,
                Field: field);

        private static GenerationError UnknownJob(Guid jobId) =>
            InvalidRequest($"Unknown jobId: {jobId:D}.", nameof(jobId));

        private static GenerationError CancelledError() =>
            new(
                GenerationErrorCode.Cancelled,
                "Job cancelled.",
                Retryable: false);

        private static GenerationError UnknownOutcomeError(
            string phase,
            string outcomeType) =>
            new(
                GenerationErrorCode.ExecutionFailed,
                $"Unknown provider {phase} outcome: {outcomeType}.",
                Retryable: false);

        private sealed class RunningJob
        {
            public ImageJobRecord LatestRecord;
            public readonly CancellationTokenSource Cts;
            public readonly ResolvedImageModel Model;
            public readonly ImageJobStartRequest Start;

            public RunningJob(
                ImageJobRecord initial,
                CancellationTokenSource cts,
                ResolvedImageModel model,
                ImageJobStartRequest start)
            {
                LatestRecord = initial;
                Cts = cts;
                Model = model;
                Start = start;
            }
        }

        private sealed class RemoteCancelResult
        {
            private RemoteCancelResult(GenerationError? error, bool alreadyTerminal)
            {
                Error = error;
                AlreadyTerminal = alreadyTerminal;
            }

            public GenerationError? Error { get; }
            public bool AlreadyTerminal { get; }

            public static RemoteCancelResult Cancelled() =>
                new(error: null, alreadyTerminal: false);

            public static RemoteCancelResult Terminal() =>
                new(error: null, alreadyTerminal: true);

            public static RemoteCancelResult Failed(GenerationError error) =>
                new(error, alreadyTerminal: false);
        }
    }
}
