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
                requestFactorySelector: null)
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
            ImageArtifactRequestFactorySelector? requestFactorySelector)
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
            var initial = new ImageJobRecord(
                jobId,
                ImageJobState.Queued,
                model.ModelId,
                model.ProviderName,
                _clock.UtcNow());
            _records[jobId] = initial;

            var jobCts = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
            var running = new RunningJob(initial, jobCts, model, start);
            _runningJobs[jobId] = running;

            _ = Task.Run(() => RunJobAsync(jobId, running), jobCts.Token);

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

            if (!_records.TryGetValue(jobId, out var record))
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
                    if (remote.AlreadyTerminal)
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

            if (!_records.TryGetValue(jobId, out var record))
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
            var jobs = _records.Values
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
                    current = Transition(current, ImageJobState.Submitting);
                    running.LatestRecord = current;

                    var submit = await provider.SubmitAsync(
                            running.Start.Request,
                            running.Start.ResolvedMedia,
                            ct)
                        .ConfigureAwait(false);

                    switch (submit)
                    {
                        case FailedSubmitOutcome failed:
                            current = Transition(
                                current,
                                ImageJobState.Error,
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
                            current = Transition(
                                current,
                                ImageJobState.Polling,
                                providerHandle: queued.Handle);
                            running.LatestRecord = current;
                            break;

                        default:
                            current = Transition(
                                current,
                                ImageJobState.Error,
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
                                current = Transition(
                                    current,
                                    ImageJobState.Materializing,
                                    providerHandle: handle);
                                running.LatestRecord = current;
                                break;

                            case FailedStatusOutcome failed:
                                current = Transition(
                                    current,
                                    ImageJobState.Error,
                                    error: failed.Error);
                                running.LatestRecord = current;
                                return;

                            default:
                                current = Transition(
                                    current,
                                    ImageJobState.Error,
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
                    var cancelled = Transition(
                        current,
                        ImageJobState.Cancelled,
                        error: CancelledError());
                    running.LatestRecord = cancelled;
                }
            }
            catch (Exception ex)
            {
                if (!IsTerminal(current.State))
                {
                    var errored = Transition(
                        current,
                        ImageJobState.Error,
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
                var errored = Transition(
                    current,
                    ImageJobState.Error,
                    error: failed.Error);
                running.LatestRecord = errored;
                return;
            }

            if (result is not SuccessResultOutcome success)
            {
                var errored = Transition(
                    current,
                    ImageJobState.Error,
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
                var errored = Transition(
                    current,
                    ImageJobState.Error,
                    error: new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Provider result envelope did not contain an image artifact.",
                        Retryable: false));
                running.LatestRecord = errored;
                return;
            }

            if (current.State != ImageJobState.Materializing)
            {
                current = Transition(current, ImageJobState.Materializing);
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

                var errored = Transition(
                    current,
                    ImageJobState.Error,
                    error: materialized.Error ?? new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Image artifact could not be materialized.",
                        Retryable: false));
                running.LatestRecord = errored;
                return;
            }

            ct.ThrowIfCancellationRequested();

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

            var complete = Transition(
                current,
                ImageJobState.Complete,
                resultArtifactId: artifact.Id);
            running.LatestRecord = complete;
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

        private ImageJobRecord Transition(
            ImageJobRecord prior,
            ImageJobState state,
            ProviderJobHandle? providerHandle = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null)
        {
            while (true)
            {
                var latest = LatestRecord(prior.JobId, prior);
                if (IsTerminal(latest.State))
                    return latest;

                var next = BuildTransition(
                    latest,
                    state,
                    providerHandle,
                    resultArtifactId,
                    error);

                if (_records.TryUpdate(latest.JobId, next, latest))
                    return next;

                if (!_records.TryGetValue(latest.JobId, out var observed))
                {
                    if (_records.TryAdd(latest.JobId, next))
                        return next;
                    continue;
                }

                if (IsTerminal(observed.State))
                    return observed;

                prior = Freshest(observed, latest);
            }
        }

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
                _clock.UtcNow(),
                providerHandle ?? prior.ProviderHandle,
                resultArtifactId ?? prior.ResultArtifactId,
                error);

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
