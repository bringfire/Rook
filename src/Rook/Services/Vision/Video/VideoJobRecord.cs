using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Fal;

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
        GenerationError? Error,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt,
        JsonObject? Extensions)
    {
        private JsonObject? _extensions = Extensions == null ? null : (JsonObject)Extensions.DeepClone();
        private JsonObject _providerOptions = (JsonObject)ProviderOptions.DeepClone();
        public JsonObject? Extensions { get => _extensions == null ? null : (JsonObject)_extensions.DeepClone(); init => _extensions = value == null ? null : (JsonObject)value.DeepClone(); }
        public JsonObject ProviderOptions { get => (JsonObject)_providerOptions.DeepClone(); init => _providerOptions = (JsonObject)value.DeepClone(); }
        public FalExecutionSnapshotReadResult? ConfiguredFalExecution => _extensions?.ContainsKey(FalExecutionSnapshot.ExtensionKey) == true
            ? FalExecutionSnapshotCodec.Deserialize(_extensions[FalExecutionSnapshot.ExtensionKey] as JsonObject ?? new JsonObject()) : null;

        public ProviderJobHandle? ProviderHandle =>
            VideoJobRecordProviderHandle.TryFromRecord(this, out var handle)
                ? handle
                : null;
    }
}
