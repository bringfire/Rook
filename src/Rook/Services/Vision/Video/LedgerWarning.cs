namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Sanitized projection of <see cref="LedgerReadError"/> intended for
    /// public surfaces (<c>list_video_jobs</c> response, future MCP tools).
    /// Drops <c>RawLineExcerpt</c> and <c>OffendingValue</c> — both can
    /// carry user-supplied content (prompt text, provider-options blobs)
    /// that must not leak through unauthenticated routes. Keeps line,
    /// reason, optional field path, and the system-generated message —
    /// enough for an operator to find the offending record.
    ///
    /// See <c>LedgerReadError</c>'s docstring: <c>RawLineExcerpt</c> is
    /// "documented as diagnostic-only and must NOT be surfaced through V2
    /// public routes without redaction." This record is the redaction.
    /// </summary>
    public sealed record LedgerWarning(
        int LineNumber,
        LedgerReadErrorReason Reason,
        string Message,
        string? FieldPath);
}
