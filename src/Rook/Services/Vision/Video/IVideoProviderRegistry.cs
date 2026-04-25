using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Exact-match resolver from model id to
    /// <see cref="ResolvedVideoModel"/>. No prefix routing; an unknown
    /// model id returns false and the caller surfaces a typed
    /// <see cref="VideoErrorCode.InvalidRequest"/>.
    ///
    /// <para><see cref="EnumerateAllModels"/> returns descriptors in
    /// stable order (registration order, then per-registration model
    /// dictionary order) for UI model pickers.</para>
    /// </summary>
    public interface IVideoProviderRegistry
    {
        bool TryResolve(string modelId, out ResolvedVideoModel model);

        IReadOnlyList<VideoModelDescriptor> EnumerateAllModels();
    }
}
