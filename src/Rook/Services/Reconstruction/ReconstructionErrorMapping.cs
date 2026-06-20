using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

/// <summary>
/// Boundary mapping from the shared, modality-neutral <see cref="GenerationError"/> to the
/// reconstruction subsystem's public <see cref="ReconstructionFailure"/> HTTP DTO. The internal
/// provider/materializer plumbing speaks <see cref="GenerationError"/> (so it can reuse the shared
/// fal mappers); only the manager/handler boundary translates to <see cref="ReconstructionFailure"/>.
/// </summary>
public static class ReconstructionErrorMapping
{
    public static ReconstructionFailure ToFailure(GenerationError error)
        => new(
            MapCode(error.Code),
            error.Message,
            error.Retryable,
            error.Field,
            new Dictionary<string, object?>
            {
                ["provider_error_code"] = error.ProviderErrorCode,
            });

    private static string MapCode(GenerationErrorCode code) => code switch
    {
        GenerationErrorCode.InvalidRequest => "invalid_request",
        GenerationErrorCode.UnsupportedMedia => "invalid_source_file",
        GenerationErrorCode.DependencyUnavailable => "provider_unavailable",
        GenerationErrorCode.QuotaExceeded => "quota_exceeded",
        GenerationErrorCode.Cancelled => "cancelled",
        GenerationErrorCode.Interrupted => "interrupted",
        GenerationErrorCode.ContentPolicy => "content_policy",
        _ => "provider_failed",
    };
}
