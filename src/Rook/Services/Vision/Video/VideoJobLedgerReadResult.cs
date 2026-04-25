using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoJobLedger.ReadAll"/>. Records are always
    /// returned (compacted to the latest entry per <c>job_id</c>) regardless
    /// of <see cref="Success"/>, so a single bad line doesn't hide prior
    /// history.
    ///
    /// <c>Success ⇔ Errors.Count == 0</c>.
    /// </summary>
    public sealed record VideoJobLedgerReadResult(
        IReadOnlyList<VideoJobRecord> Records,
        IReadOnlyList<LedgerReadError> Errors)
    {
        public bool Success => Errors.Count == 0;
    }
}
