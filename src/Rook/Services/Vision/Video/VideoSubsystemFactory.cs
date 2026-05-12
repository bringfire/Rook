using System;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Bundle of the long-lived video subsystem instances. The
    /// <see cref="Manager"/> is the typed concrete (not the interface) so
    /// the composition root can <see cref="IDisposable.Dispose"/> it on
    /// plugin shutdown without a runtime cast.
    /// </summary>
    internal sealed record VideoSubsystemBundle(
        VideoJobManager Manager,
        IVideoProviderRegistry Registry,
        IVideoCostEstimator Estimator,
        IVideoSidecarBackfillService SidecarBackfill);

    /// <summary>
    /// Pure composition for the video subsystem. Stateless; the same
    /// inputs always produce a fresh independent bundle. Held by
    /// <see cref="RookSubsystemRoot"/> behind a <see cref="Lazy{T}"/> so
    /// callers that never touch video (image-only paths) don't pay the
    /// build cost.
    ///
    /// V1c-shipped invariants the build relies on:
    ///   - <see cref="VeoCapabilities.Models"/> is a non-empty static map.
    ///   - <see cref="DefaultVideoProviderRegistry"/> validates registrations
    ///     at construction; a malformed VeoCapabilities throws here, not later.
    ///   - <see cref="ArtifactOnlyVideoMediaResolver"/> rejects path-kind
    ///     refs by design (V2 HTTP adapter is the other rejection point;
    ///     defense-in-depth).
    /// </summary>
    internal static class VideoSubsystemFactory
    {
        /// <param name="ledger">
        /// Optional ledger override. Production callers pass null and get
        /// the default <see cref="JsonlVideoJobLedger"/> at
        /// <c>%APPDATA%\Rook\video\job-ledger.jsonl</c>. Test callers
        /// inject an in-memory or temp-path ledger to keep production
        /// state untouched (see Codex review of step 2 follow-ups —
        /// reconcile MUST NOT append to the shared user file from tests).
        /// </param>
        public static VideoSubsystemBundle Build(
            IGenerationSecretStore generationSecrets,
            ArtifactStore artifactStore,
            IVideoJobLedger? ledger = null,
            IVideoSidecarBackfillService? sidecarBackfill = null)
        {
            if (generationSecrets is null)
                throw new ArgumentNullException(nameof(generationSecrets));
            if (artifactStore is null) throw new ArgumentNullException(nameof(artifactStore));

            var registry = new DefaultVideoProviderRegistry(
                VisionProviderRegistrations.CreateVideoRegistrations(
                    () => generationSecrets.GetSecret(GenerationSecretKeys.GeminiApiKey),
                    () => generationSecrets.GetSecret(GenerationSecretKeys.FalApiKey)));

            var mediaResolver = new ArtifactOnlyVideoMediaResolver(artifactStore);
            var actualLedger = ledger ?? new JsonlVideoJobLedger();
            var estimator = new VideoCostEstimator();

            var manager = new VideoJobManager(
                registry: registry,
                mediaResolver: mediaResolver,
                ledger: actualLedger,
                estimator: estimator,
                artifactStore: artifactStore);

            var actualSidecarBackfill = sidecarBackfill
                ?? new VideoSidecarBackfillService(
                    artifactStore,
                    new VideoPosterSidecarProducer(artifactStore),
                    new VideoFrameSidecarProducer(artifactStore));

            return new VideoSubsystemBundle(
                manager,
                registry,
                estimator,
                actualSidecarBackfill);
        }
    }
}
