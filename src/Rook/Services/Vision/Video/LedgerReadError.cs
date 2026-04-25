namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Line-scoped failure during ledger read. Pinned to a specific line
    /// so one bad future/corrupt entry doesn't hide all valid prior
    /// records. Codex round 4 finding: <see cref="RawLineExcerpt"/> is
    /// populated only for <see cref="LedgerReadErrorReason.MalformedJson"/>
    /// (where raw bytes are needed for diagnostics); semantic errors
    /// surface only <see cref="FieldPath"/> + <see cref="OffendingValue"/>
    /// to avoid leaking prompts or provider-options content.
    ///
    /// <see cref="RawLineExcerpt"/> is documented as diagnostic-only and
    /// must NOT be surfaced through V2 public routes without redaction.
    /// </summary>
    public sealed record LedgerReadError(
        int LineNumber,
        LedgerReadErrorReason Reason,
        string Message,
        string? FieldPath,
        string? OffendingValue,
        string? RawLineExcerpt);
}
