namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Durable persistence seam for <see cref="VideoJobRecord"/>s. The
    /// production implementation (<c>JsonlVideoJobLedger</c>, commit 3)
    /// uses append-only JSONL; tests use an in-memory fake. Single-writer
    /// — only <see cref="VideoJobManager"/> writes; readers (status
    /// route, MCP tools) read.
    ///
    /// Append semantics: each call writes a full snapshot per state
    /// transition. <see cref="ReadAll"/> compacts by <c>job_id</c>,
    /// returning the latest record per id (file-order resolution).
    /// </summary>
    public interface IVideoJobLedger
    {
        void Append(VideoJobRecord record);

        VideoJobLedgerReadResult ReadAll();
    }
}
