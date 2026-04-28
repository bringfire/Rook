using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Resolves <see cref="MediaRef"/> values into
    /// <see cref="ResolvedMedia"/> (bytes + MIME) before they reach a
    /// provider. The resolver enforces policy that providers must not
    /// know about — e.g. V1c's
    /// <c>ArtifactOnlyVideoMediaResolver</c> rejects
    /// <see cref="MediaRefKind.Path"/> refs to keep production calls
    /// from reading arbitrary paths off disk.
    ///
    /// <para>Returning <see cref="MediaResolutionResult.Fail"/> short-
    /// circuits the manager's submit before any provider call,
    /// surfacing as a typed <see cref="GenerationError"/>
    /// (<see cref="GenerationErrorCode.UnsupportedMedia"/> typically).</para>
    /// </summary>
    public interface IMediaResolver
    {
        Task<MediaResolutionResult> ResolveAllAsync(
            IReadOnlyList<MediaRef> refs,
            CancellationToken ct);
    }
}
