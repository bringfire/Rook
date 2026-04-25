using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Resolves a <see cref="VideoMediaRef"/> into bytes for provider
    /// consumption. The manager calls this once per media ref in a
    /// request, builds the resolved-media dictionary, and passes the
    /// dictionary to <see cref="IVideoProvider.SubmitAsync"/>.
    ///
    /// V1b ships <see cref="ArtifactOnlyVideoMediaResolver"/> which
    /// resolves <see cref="VideoMediaRefKind.Artifact"/> only and
    /// rejects <see cref="VideoMediaRefKind.Path"/> — path validation
    /// is V2's adapter-boundary responsibility, and V1b deliberately
    /// has no place to put it. A future
    /// <c>PathVideoMediaResolver</c> + <c>CompositeVideoMediaResolver</c>
    /// will land alongside V2's public HTTP routes.
    /// </summary>
    public interface IVideoMediaResolver
    {
        Task<ResolvedVideoMedia> ResolveAsync(
            VideoMediaRef mediaRef, CancellationToken ct);
    }
}
