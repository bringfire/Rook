using System;
using System.Threading;
using Rook.Artifacts;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Video;

namespace Rook
{
    /// <summary>
    /// Neutral composition root for shared Rook subsystems. Owns the
    /// process-wide singletons that multiple subsystems must agree on:
    /// the on-disk <see cref="ArtifactStore"/>, the DPAPI-wrapped
    /// <see cref="VisionSecretStore"/>, and the <see cref="VideoSubsystemBundle"/>
    /// (manager + registry + estimator).
    ///
    /// Why a separate root (V2): the Vision tab (Pattern A bridge), the
    /// native HTTP routes (vision_dispatch trampoline), and the future
    /// GH NLE all need the same in-memory instances. Without a neutral
    /// surface, the parameterless <c>VisionHandler()</c> ctor and a
    /// registrar-owned <see cref="ArtifactStore"/> would write to the
    /// same on-disk root but hold independent in-memory caches —
    /// invisible until two callers race on the same artifact id.
    ///
    /// This type is deliberately UI-free, registrar-free, and bridge-
    /// free. Consumers depend on it; it depends on nothing in those
    /// layers. Static initialization runs on first access; cheap (the
    /// wrapped stores defer disk I/O until first read/write).
    ///
    /// The video bundle is built lazily so callers that never touch
    /// video (image-only paths, command-only paths) do not pay the
    /// registry-validation + Veo-provider construction cost.
    /// </summary>
    internal sealed class RookSubsystemRoot
    {
        private static readonly RookSubsystemRoot _instance = new();

        public static RookSubsystemRoot Instance => _instance;

        public ArtifactStore SharedArtifactStore { get; }

        public IGenerationSecretStore SharedGenerationSecretStore { get; }

        public VisionSecretStore SharedSecretStore { get; }

        private readonly Lazy<VideoSubsystemBundle> _video;
        private readonly Lazy<ImageJobSubsystemBundle> _imageJobs;

        /// <summary>
        /// Resolves the lazy video subsystem. Throws
        /// <see cref="ObjectDisposedException"/> after
        /// <see cref="DisposeVideoSubsystemIfCreated"/> has been called —
        /// shutdown closes the root, and a late caller building a fresh
        /// manager AFTER the only dispose pass would leave it
        /// undisposed and the JSONL ledger un-flushed (Codex review of
        /// step 2 follow-ups). Loud failure beats the silent torn-down
        /// state.
        /// </summary>
        public VideoSubsystemBundle Video
        {
            get
            {
                if (Volatile.Read(ref _disposed) != 0)
                    throw new ObjectDisposedException(
                        nameof(RookSubsystemRoot),
                        "Video subsystem accessed after shutdown.");
                return _video.Value;
            }
        }

        public ImageJobSubsystemBundle ImageJobs
        {
            get
            {
                if (Volatile.Read(ref _disposed) != 0)
                    throw new ObjectDisposedException(
                        nameof(RookSubsystemRoot),
                        "Image job subsystem accessed after shutdown.");
                return _imageJobs.Value;
            }
        }

        private int _reconcileFired = 0;
        private int _disposed = 0;

        private RookSubsystemRoot()
            : this(artifactStore: null, generationSecretStore: null, ledger: null) { }

        /// <summary>
        /// Test seam — production callers use <see cref="Instance"/>.
        /// Lets tests construct an isolated root with their own stores
        /// and an in-memory <see cref="IVideoJobLedger"/>, so
        /// reconcile/dispose lifecycle tests never touch the user's
        /// real <c>%APPDATA%\Rook\video\job-ledger.jsonl</c>.
        /// </summary>
        internal RookSubsystemRoot(
            ArtifactStore? artifactStore,
            IGenerationSecretStore? generationSecretStore,
            IVideoJobLedger? ledger)
        {
            SharedArtifactStore = artifactStore ?? new ArtifactStore();
            SharedGenerationSecretStore = generationSecretStore
                ?? new DpapiGenerationSecretStore();
            SharedSecretStore = new VisionSecretStore(SharedGenerationSecretStore);
            _video = new Lazy<VideoSubsystemBundle>(
                () => VideoSubsystemFactory.Build(
                    SharedGenerationSecretStore, SharedArtifactStore, ledger),
                LazyThreadSafetyMode.ExecutionAndPublication);
            _imageJobs = new Lazy<ImageJobSubsystemBundle>(
                () =>
                {
                    var registry = new DefaultImageProviderRegistry(
                        VisionProviderRegistrations.CreateImageRegistrations(
                            () => SharedGenerationSecretStore.GetSecret(
                                GenerationSecretKeys.GeminiApiKey),
                            () => SharedGenerationSecretStore.GetSecret(
                                GenerationSecretKeys.FalApiKey),
                            () => SharedGenerationSecretStore.GetSecret(
                                GenerationSecretKeys.ReplicateApiToken)));
                    var manager = new ImageJobManager(
                        registry,
                        SharedArtifactStore);
                    return new ImageJobSubsystemBundle(manager, registry);
                },
                LazyThreadSafetyMode.ExecutionAndPublication);
        }

        /// <summary>
        /// Run <see cref="VideoJobManager.ReconcileInterruptedJobs"/>
        /// exactly once per process per success. Safe to call from
        /// multiple plugin startup paths (Idle event + autoload retry)
        /// — only the first caller to win the
        /// <see cref="Interlocked.CompareExchange"/> fires the reconcile.
        ///
        /// Forces lazy construction of the video subsystem. Reconcile
        /// MUST touch the manager's ledger to write Interrupted snapshots
        /// for non-terminal records left by a prior session, so the
        /// manager must exist. Cost is registry validation + one ledger
        /// read at startup.
        ///
        /// Failure semantics (Codex minor #3): the flag stays in the
        /// "available" state until reconcile completes successfully. If
        /// lazy construction or ledger I/O throws, the flag resets so a
        /// later caller (next plugin Idle tick) can retry. Concurrent
        /// callers that race past the CompareExchange while the first
        /// caller is still running will short-circuit; if the first
        /// caller fails, only callers in subsequent ticks observe the
        /// reset window.
        /// </summary>
        public void ReconcileVideoJobsOnce()
        {
            if (Interlocked.CompareExchange(ref _reconcileFired, 1, 0) != 0)
                return;

            try
            {
                Video.Manager.ReconcileInterruptedJobs();
            }
            catch
            {
                Volatile.Write(ref _reconcileFired, 0);
                throw;
            }
        }

        /// <summary>
        /// Dispose the video subsystem if it was ever built. No-op when
        /// <see cref="Lazy{T}.IsValueCreated"/> is false — sessions that
        /// never touched video do not pay a build cost just to dispose.
        /// Idempotent via the same <see cref="Interlocked.CompareExchange"/>
        /// pattern as reconcile so a double-shutdown chain (Plugin
        /// OnShutdown + AppDomain unload) does not re-enter
        /// <see cref="VideoJobManager.Dispose"/>, which is not itself
        /// idempotent.
        ///
        /// After this returns, <see cref="Video"/> throws
        /// <see cref="ObjectDisposedException"/> on access — even if the
        /// subsystem had never been built. This closes the root: a late
        /// caller cannot build a fresh manager that escapes the
        /// shutdown pass.
        ///
        /// Production lifecycle only — calling this on
        /// <see cref="Instance"/> from a test would poison subsequent
        /// tests in the same process that read <see cref="Video"/>. Use
        /// the internal test ctor instead.
        /// </summary>
        public void DisposeVideoSubsystemIfCreated()
        {
            if (Interlocked.CompareExchange(ref _disposed, 1, 0) != 0)
                return;

            if (_imageJobs.IsValueCreated
                && _imageJobs.Value.Manager is IDisposable imageJobManager)
            {
                imageJobManager.Dispose();
            }

            if (_video.IsValueCreated)
            {
                _video.Value.Manager.Dispose();
            }
        }
    }
}
