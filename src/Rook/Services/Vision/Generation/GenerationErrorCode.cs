namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral error classification. PR-2 maps the legacy
    /// per-modality <c>VideoErrorCode</c> onto these values 1:1 by name
    /// for the first six entries so wire-shape JSON for video error
    /// responses is byte-identical pre/post.
    /// </summary>
    public enum GenerationErrorCode
    {
        InvalidRequest = 0,         // caller-shaped: bad inputs, missing fields, type mismatch
        UnsupportedMedia = 1,       // capability mismatch (resolution unsupported, etc.)
        DependencyUnavailable = 2,  // network / 5xx / auth-failure / missing api key
        ExecutionFailed = 3,        // provider-side execution error (NSFW filter, OOM, etc.)
        Cancelled = 4,
        Interrupted = 5,
        QuotaExceeded = 6,          // new in Phase 1 — fal/Replicate surface this distinctly from auth
        ContentPolicy = 7,          // new in Phase 1 — separated from ExecutionFailed for UX
    }
}
