using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Generic per-modality provider seam. Generic over the request and
    /// capability shapes only — NOT options. Options pairing lives on the
    /// resolved-model + codec edge so a video provider is not baked to
    /// any single options subtype (e.g. fal video and Veo are both video
    /// providers but ship different <see cref="ProviderOptions"/>
    /// subtypes; their codecs sit on their respective resolved-model
    /// records).
    ///
    /// <para>The provider casts <c>request.Options</c> to its own concrete
    /// <see cref="ProviderOptions"/> subtype internally and returns
    /// <see cref="FailedSubmitOutcome"/> with
    /// <see cref="GenerationErrorCode.InvalidRequest"/> on type mismatch
    /// — the boundary stays total, no exceptions cross it.</para>
    ///
    /// <para>Statelessness: providers must not cache per-job state across
    /// calls. All state needed across method invocations rides on
    /// <see cref="ProviderJobHandle"/>, which the manager persists into
    /// the ledger. This lets a manager restart resume polling without
    /// provider-side recovery code.</para>
    /// </summary>
    public interface IGenerationProvider<TRequest, TCapability> : IGenerationProvider
        where TRequest : GenerationRequest
        where TCapability : IModelCapability
    {
        /// <summary>
        /// Submit a generation request. The manager pre-resolves any
        /// <see cref="MediaRef"/> in the request into bytes via
        /// <see cref="IMediaResolver"/>; this keeps providers
        /// independent of artifact-storage layout.
        ///
        /// <para>Return value is a sealed-record union:
        /// <list type="bullet">
        ///   <item><see cref="SyncSubmitOutcome"/> — sync providers (e.g.
        ///         Gemini direct) returning the full result inline at
        ///         submit; carries a <see cref="ProviderResultOutcome"/>
        ///         which itself discriminates success vs failure.</item>
        ///   <item><see cref="QueuedSubmitOutcome"/> — async providers
        ///         (Veo, fal queue, Replicate) returning a
        ///         <see cref="ProviderJobHandle"/> for subsequent
        ///         polling/fetching.</item>
        ///   <item><see cref="FailedSubmitOutcome"/> — pre-meter failure
        ///         (auth, validation, network, quota returned
        ///         synchronously). The provider's billing meter never
        ///         ran; manager logs as no-cost failure.</item>
        /// </list></para>
        /// </summary>
        Task<ProviderSubmitOutcome> SubmitAsync(
            TRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct);

        Task<ProviderStatusOutcome> GetStatusAsync(
            ProviderJobHandle handle,
            CancellationToken ct);

        Task<ProviderCancelOutcome> CancelAsync(
            ProviderJobHandle handle,
            CancellationToken ct);

        /// <summary>
        /// Fetch the generated artifact(s) once the provider reports
        /// <see cref="ProviderCompleteStatusOutcome"/>. The manager
        /// passes the most recently observed handle (which the status
        /// outcome may have updated, e.g. with Veo's videoUri stamped
        /// into <see cref="ProviderJobHandle.ProviderResultToken"/>)
        /// so the provider stays stateless across calls.
        /// </summary>
        Task<ProviderResultOutcome> FetchResultAsync(
            ProviderJobHandle handle,
            CancellationToken ct);
    }
}
