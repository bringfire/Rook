using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral typed error. Mirrors the V1c
    /// <c>VideoJobError</c> for the existing four fields (Code, Message,
    /// Retryable, Field) and adds two new fields for Phase 1's
    /// multi-provider needs:
    /// <list type="bullet">
    ///   <item><see cref="ProviderErrorCode"/> — the raw provider code
    ///         string (e.g. fal <c>"validation_error"</c>, Replicate
    ///         <c>"NSFW"</c>) for support-escalation diagnostics.</item>
    ///   <item><see cref="ProviderDetail"/> — the provider's structured
    ///         error envelope (e.g. FastAPI-style
    ///         <c>detail: [{loc, msg, type, url}]</c>) preserved as a
    ///         JsonNode bag so audit + replay can reconstruct what the
    ///         provider returned.</item>
    /// </list>
    /// </summary>
    public sealed record GenerationError(
        GenerationErrorCode Code,
        string Message,
        bool Retryable,
        string? Field = null,
        string? ProviderErrorCode = null,
        IReadOnlyDictionary<string, JsonNode>? ProviderDetail = null);
}
