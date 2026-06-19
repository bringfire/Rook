using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

public interface IReconstructionSourceImagePublisher
{
    Task<Uri> PublishAsync(Artifact artifact, string role, string absolutePath, CancellationToken ct);
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

public sealed class ReconstructionJobManager
{
    private readonly ArtifactStore _store;
    private readonly ReconstructionModelCatalog _catalog;
    private readonly JsonlReconstructionJobLedger _ledger;
    private readonly IReconstructionProvider _provider;
    private readonly ReconstructionPackageMaterializer _materializer;
    private readonly IReconstructionSourceImagePublisher _sourcePublisher;

    public ReconstructionJobManager(
        ArtifactStore store,
        ReconstructionModelCatalog catalog,
        JsonlReconstructionJobLedger ledger,
        IReconstructionProvider provider,
        ReconstructionPackageMaterializer materializer,
        IReconstructionSourceImagePublisher sourcePublisher)
    {
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _materializer = materializer ?? throw new ArgumentNullException(nameof(materializer));
        _sourcePublisher = sourcePublisher ?? throw new ArgumentNullException(nameof(sourcePublisher));
    }

    public async Task<ReconstructionSubmitResult> SubmitAsync(
        ReconstructionSubmitRequest request,
        CancellationToken ct)
    {
        var model = _catalog.Find(request.ModelId);
        if (model is null || !model.Enabled)
            return SubmitFail("invalid_request", "Requested reconstruction model is not available.", "model_id");

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

        var sourceUrl = await _sourcePublisher.PublishAsync(
            source,
            request.SourceRole,
            sourceValidation.AbsolutePath!,
            ct).ConfigureAwait(false);
        var providerSubmit = await _provider.SubmitAsync(
            new ReconstructionProviderSubmitRequest(request.ModelId, sourceUrl, request.Options),
            ct).ConfigureAwait(false);

        _ledger.Append(submitting with
        {
            Stage = ReconstructionJobStage.Polling,
            ProviderJobId = providerSubmit.ProviderJobId,
            UpdatedAt = DateTimeOffset.UtcNow,
        });

        return new ReconstructionSubmitResult(true, queued, null);
    }

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

    public async Task<ReconstructionCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
    {
        var job = FindJob(jobId);
        if (job is null)
            return new ReconstructionCancelResult(
                ReconstructionJobState.Error,
                Failure("not_found", "Reconstruction job was not found.", "job_id"));

        if (IsTerminal(job.State))
            return new ReconstructionCancelResult(job.State, null);

        var cancelled = job with
        {
            State = ReconstructionJobState.CancellationRequested,
            UpdatedAt = DateTimeOffset.UtcNow,
        };
        _ledger.Append(cancelled);

        if (!string.IsNullOrWhiteSpace(job.ProviderJobId))
            await _provider.CancelAsync(job.ModelId, job.ProviderJobId!, ct).ConfigureAwait(false);

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
        var job = FindJob(jobId)
            ?? throw new KeyNotFoundException($"Reconstruction job '{jobId:D}' was not found.");
        if (IsTerminal(job.State) || string.IsNullOrWhiteSpace(job.ProviderJobId))
            return;

        var status = await _provider.GetStatusAsync(
            job.ModelId,
            job.ProviderJobId!,
            ct).ConfigureAwait(false);
        if (!status.IsTerminal)
        {
            _ledger.Append(job with
            {
                State = ReconstructionJobState.Running,
                Stage = ReconstructionJobStage.Polling,
                UpdatedAt = DateTimeOffset.UtcNow,
            });
            return;
        }

        if (!status.IsSuccess)
        {
            _ledger.Append(job with
            {
                State = status.State == ReconstructionProviderLifecycleState.Cancelled
                    ? ReconstructionJobState.Cancelled
                    : ReconstructionJobState.Error,
                Stage = status.State == ReconstructionProviderLifecycleState.Cancelled
                    ? ReconstructionJobStage.Cancelled
                    : ReconstructionJobStage.Error,
                Error = status.Error ?? Failure("provider_error", "Reconstruction provider failed.", null),
                UpdatedAt = DateTimeOffset.UtcNow,
            });
            return;
        }

        var materializing = job with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Materializing,
            UpdatedAt = DateTimeOffset.UtcNow,
        };
        _ledger.Append(materializing);

        var resultJson = await _provider.GetResultAsync(
            job.ModelId,
            job.ProviderJobId!,
            ct).ConfigureAwait(false);
        var artifact = _materializer.Materialize(
            job.JobId,
            new[] { job.SourceArtifactId },
            job.Provider,
            job.ModelId,
            resultJson);
        _ledger.Append(materializing with
        {
            State = ReconstructionJobState.Complete,
            Stage = ReconstructionJobStage.Complete,
            ResultArtifactId = artifact.Id,
            ResultAvailable = true,
            UpdatedAt = DateTimeOffset.UtcNow,
        });
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

    private static ReconstructionSubmitResult SubmitFail(
        string code,
        string message,
        string? field)
        => new(false, null, Failure(code, message, field));

    private static ReconstructionFailure Failure(string code, string message, string? field)
        => new(code, message, false, field, new Dictionary<string, object?>());
}
