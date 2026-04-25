using System;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Durable, provider-neutral snapshot of a video job's state at a
    /// single point in time. Persisted as a JSONL line in the
    /// <see cref="JsonlVideoJobLedger"/>; the ledger compacts by
    /// <see cref="JobId"/> on read, returning the latest record per id.
    ///
    /// <c>created_at</c> is set once at job birth and remains stable
    /// across snapshots; <c>updated_at</c> changes per append.
    ///
    /// <see cref="ProviderJobId"/> is null before <c>SubmitAsync</c>
    /// returns successfully; set once and persisted thereafter, so
    /// explicit cancel can clean up remote provider jobs even after
    /// plugin restart (V1b doesn't auto-resume mid-flight; per v3.1
    /// D4, restart-mid-job marks Interrupted).
    ///
    /// <see cref="ProviderResultToken"/> is null until the provider
    /// reports provider-Complete with a result handle (videoUri for
    /// Veo); set once and persisted, so the manager can call
    /// <c>FetchResultAsync</c> after restart with a stateless provider.
    /// </summary>
    public sealed record VideoJobRecord(
        int SchemaVersion,
        Guid JobId,
        string Provider,
        string Model,
        string? ProviderJobId,
        string? ProviderResultToken,
        VideoJobState State,
        NormalizedRequest NormalizedRequest,
        JsonObject ProviderOptions,
        JobPricing Pricing,
        Guid? ResultArtifactId,
        VideoJobError? Error,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt,
        JsonObject? Extensions);
}
