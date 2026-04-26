using System;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// One row of <see cref="JobListResult.Jobs"/>: a queue-panel-shaped
    /// projection of a <see cref="VideoJobRecord"/>. Carries the freshest
    /// state observed across the ledger and any in-memory running snapshot
    /// at the moment <see cref="IVideoJobManager.ListJobsAsync"/> ran (see
    /// the manager's freshness-merge rule).
    ///
    /// <see cref="UpdatedAt"/> is <see cref="DateTimeOffset"/> so the
    /// explicit-offset invariant of the persisted ledger contract is
    /// preserved end-to-end (V1b ledger format pins ISO 8601 with offset).
    /// </summary>
    public sealed record JobListEntry(
        Guid JobId,
        VideoJobState State,
        DateTimeOffset UpdatedAt,
        JobRequestSummary Summary,
        Guid? ResultArtifactId,
        VideoJobError? Error);
}
