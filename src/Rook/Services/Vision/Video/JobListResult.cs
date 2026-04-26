using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoJobManager.ListJobsAsync"/>:
    /// <list type="bullet">
    ///   <item><see cref="Jobs"/> — newest-first list of compacted job
    ///         entries, capped at the caller-supplied limit (see manager
    ///         contract for sort + limit semantics).</item>
    ///   <item><see cref="Warnings"/> — sanitized
    ///         <see cref="LedgerReadError"/> projections for any
    ///         malformed / unsupported lines encountered while reading.
    ///         Always non-null; empty when the read was clean. Bad lines
    ///         do not block valid records from appearing in
    ///         <see cref="Jobs"/>.</item>
    ///   <item><see cref="AppliedLimit"/> — the limit actually used after
    ///         clamping to the manager's hard ceiling, so callers can
    ///         distinguish "I asked for 500, got 200" from "fewer records
    ///         exist." Mirrors <c>list_artifacts.applied_limit</c>.</item>
    /// </list>
    /// </summary>
    public sealed record JobListResult(
        IReadOnlyList<JobListEntry> Jobs,
        IReadOnlyList<LedgerWarning> Warnings,
        int AppliedLimit);
}
