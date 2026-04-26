namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Compact projection of a <see cref="VideoJobRecord"/>'s submission
    /// fields, suitable for queue-panel rendering. The model id is taken
    /// from <see cref="VideoJobRecord.Model"/> (top-level on the record);
    /// <see cref="NormalizedRequest"/> does not carry the model. Mode,
    /// duration, resolution, and aspect ratio come from the normalized
    /// request inside the same record.
    ///
    /// PR-V3 callers (UI list panel, future MCP <c>rhino_video_jobs</c>)
    /// see only this projection — they never get the raw
    /// <see cref="VideoJobRecord"/>, so persisted-only fields like
    /// <c>provider_options</c> and <c>extensions</c> stay private to the
    /// ledger contract.
    /// </summary>
    public sealed record JobRequestSummary(
        string Model,
        VideoMode Mode,
        int DurationSeconds,
        string Resolution,
        string AspectRatio);
}
