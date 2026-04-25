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

        /// <summary>
        /// Resolves a provider by its registered name. Used by
        /// <see cref="VideoJobManager.CancelAsync"/> to clean up remote
        /// jobs whose persisted model id may have been deprecated between
        /// runs (the persisted <c>provider</c> name is still valid even
        /// after a model retirement). When duplicate provider names are
        /// registered, the first-registered provider wins; this assumes
        /// implementations sharing a name are interchangeable for
        /// out-of-band ops like cancel.
        /// </summary>
        bool TryResolveProviderByName(string providerName, out IVideoProvider provider);
    }
}
