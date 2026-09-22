using System;
using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Reconstruction;
using Rook.Services.Reconstruction.Fal;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Image.Replicate;
using Rook.Services.Vision.Image.Vertex;
using Rook.Services.Vision.MediaImport;
using Rook.Services.Vision.Video;

namespace Rook
{
    internal sealed record VideoSidecarBackfillStartupOptions(
        bool Enabled,
        VideoSidecarBackfillOptions ServiceOptions,
        Action<VideoSidecarBackfillResult>? OnCompleted,
        Action<Exception>? OnFailed)
    {
        public static VideoSidecarBackfillStartupOptions Default { get; } =
            new VideoSidecarBackfillStartupOptions(
                Enabled: true,
                ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
                OnCompleted: null,
                OnFailed: null);

        public static VideoSidecarBackfillStartupOptions Disabled { get; } =
            new VideoSidecarBackfillStartupOptions(
                Enabled: false,
                ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
                OnCompleted: null,
                OnFailed: null);
    }

    internal interface IVideoSidecarBackfillTaskScheduler
    {
        void Schedule(Func<Task> work);
    }

    internal sealed class ThreadPoolVideoSidecarBackfillTaskScheduler
        : IVideoSidecarBackfillTaskScheduler
    {
        public void Schedule(Func<Task> work)
        {
            _ = Task.Run(work);
        }
    }

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
        private readonly Lazy<MediaImportJobManager> _mediaImports;
        private readonly Lazy<ReconstructionOpHandler> _reconstruction;
        private readonly IVideoSidecarBackfillTaskScheduler _backfillScheduler;
        private readonly object _vertexTokenSourceSync = new();
        private IVertexAccessTokenSource _vertexAccessTokenSource;
        private bool _vertexTokenSourceConfigured;

        /// <summary>
        /// Resolves the lazy video subsystem. Throws
        /// <see cref="ObjectDisposedException"/> after
        /// <see cref="DisposeCreatedSubsystems"/> has been called —
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

                if (_imageJobs.IsValueCreated)
                    return _imageJobs.Value;

                lock (_vertexTokenSourceSync)
                {
                    if (Volatile.Read(ref _disposed) != 0)
                        throw new ObjectDisposedException(
                            nameof(RookSubsystemRoot),
                            "Image job subsystem accessed after shutdown.");
                    return _imageJobs.Value;
                }
            }
        }

        public MediaImportJobManager MediaImports
        {
            get
            {
                if (Volatile.Read(ref _disposed) != 0)
                    throw new ObjectDisposedException(
                        nameof(RookSubsystemRoot),
                        "Media import subsystem accessed after shutdown.");
                return _mediaImports.Value;
            }
        }

        public ReconstructionOpHandler Reconstruction
        {
            get
            {
                if (Volatile.Read(ref _disposed) != 0)
                    throw new ObjectDisposedException(
                        nameof(RookSubsystemRoot),
                        "Reconstruction subsystem accessed after shutdown.");
                return _reconstruction.Value;
            }
        }

        private int _reconcileFired = 0;
        private int _videoSidecarBackfillFired = 0;
        private int _imageReconcileFired = 0;
        private int _disposed = 0;

        private RookSubsystemRoot()
            : this(
                artifactStore: null,
                generationSecretStore: null,
                ledger: null,
                imageLedger: null,
                vertexAccessTokenSource: null) { }

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
            IVideoJobLedger? ledger,
            IImageJobLedger? imageLedger,
            IVideoSidecarBackfillService? sidecarBackfill = null,
            IVideoSidecarBackfillTaskScheduler? backfillScheduler = null,
            IVertexAccessTokenSource? vertexAccessTokenSource = null)
        {
            SharedArtifactStore = artifactStore ?? new ArtifactStore();
            SharedGenerationSecretStore = generationSecretStore
                ?? new DpapiGenerationSecretStore();
            SharedSecretStore = new VisionSecretStore(SharedGenerationSecretStore);
            _vertexAccessTokenSource = vertexAccessTokenSource
                ?? UnavailableVertexAccessTokenSource.Instance;
            _vertexTokenSourceConfigured = vertexAccessTokenSource is not null;
            _video = new Lazy<VideoSubsystemBundle>(
                () => VideoSubsystemFactory.Build(
                    SharedGenerationSecretStore,
                    SharedArtifactStore,
                    ledger,
                    sidecarBackfill),
                LazyThreadSafetyMode.ExecutionAndPublication);
            _backfillScheduler = backfillScheduler
                ?? new ThreadPoolVideoSidecarBackfillTaskScheduler();
            _mediaImports = new Lazy<MediaImportJobManager>(
                () => MediaImportSubsystemFactory.Build(SharedArtifactStore),
                LazyThreadSafetyMode.ExecutionAndPublication);
            _reconstruction = new Lazy<ReconstructionOpHandler>(
                CreateReconstruction,
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
                    var selector = new ReplicateImageArtifactRequestFactorySelector(
                        () => SharedGenerationSecretStore.GetSecret(
                            GenerationSecretKeys.ReplicateApiToken));
                    var manager = new ImageJobManager(
                        registry,
                        SharedArtifactStore,
                        clock: null,
                        idGenerator: null,
                        pollInterval: null,
                        maxConcurrentJobs: ImageJobManager.DefaultMaxConcurrentJobs,
                        materializer: null,
                        requestFactorySelector: selector.Select,
                        ledger: imageLedger ?? new JsonlImageJobLedger());
                    return new ImageJobSubsystemBundle(manager, registry);
                },
                LazyThreadSafetyMode.ExecutionAndPublication);
        }

        internal void ConfigureVertexAccessTokenSource(
            IVertexAccessTokenSource vertexAccessTokenSource)
        {
            if (vertexAccessTokenSource is null)
                throw new ArgumentNullException(nameof(vertexAccessTokenSource));

            lock (_vertexTokenSourceSync)
            {
                if (_vertexTokenSourceConfigured)
                {
                    if (ReferenceEquals(
                        _vertexAccessTokenSource,
                        vertexAccessTokenSource))
                    {
                        return;
                    }

                    throw new InvalidOperationException(
                        "The Vertex access-token source is already configured.");
                }

                if (_imageJobs.IsValueCreated)
                {
                    throw new InvalidOperationException(
                        "The Vertex access-token source must be configured before the image registry is created.");
                }

                _vertexAccessTokenSource = vertexAccessTokenSource;
                _vertexTokenSourceConfigured = true;
            }
        }

        private ReconstructionOpHandler CreateReconstruction()
        {
            var catalog = LoadReconstructionCatalog();
            var falClient = new FalApiClient();
            Func<string?> falApiKey = () => SharedGenerationSecretStore.GetSecret(
                GenerationSecretKeys.FalApiKey);
            var provider = new FalReconstructionProvider(
                new FalApiTransport(falClient, falApiKey));
            var downloader = new ReconstructionRemoteAssetDownloader(
                new HttpClient(),
                role => role.StartsWith("model_", StringComparison.Ordinal)
                    ? 100_000_000L
                    : 25_000_000L);
            var materializer = new ReconstructionPackageMaterializer(
                SharedArtifactStore,
                downloader);
            var preprocessMaterializer = new ReconstructionPreprocessMaterializer(
                SharedArtifactStore,
                downloader);
            var manager = new ReconstructionJobManager(
                SharedArtifactStore,
                catalog,
                new JsonlReconstructionJobLedger(
                    JsonlReconstructionJobLedger.DefaultPath()),
                provider,
                materializer,
                preprocessMaterializer,
                new FalReconstructionSourceImagePublisher(
                    falClient,
                    SharedGenerationSecretStore));

            // Settle any jobs whose background loops were abandoned by a prior plugin reload/crash:
            // non-terminal ledger records become Interrupted (provider ids preserved; no auto-resume).
            manager.ReconcileInterruptedJobs();

            return new ReconstructionOpHandler(
                catalog,
                manager,
                SharedArtifactStore,
                new ReconstructionViewSetAssembler(SharedArtifactStore),
                new NativeReconstructionImportClient(new HttpClient(), new DiscoveryFileNativeEndpointResolver()));
        }

        private static ReconstructionModelCatalog LoadReconstructionCatalog()
        {
            var assembly = Assembly.GetExecutingAssembly();
            const string resourceName =
                "Rook.Services.Reconstruction.Fal.fal-model-catalog.json";
            using var stream = assembly.GetManifestResourceStream(resourceName)
                ?? throw new InvalidOperationException(
                    "Embedded reconstruction model catalog was not found.");
            using var reader = new StreamReader(stream);
            return ReconstructionModelCatalog.FromJson(reader.ReadToEnd());
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

        public void ReconcileImageJobsOnce()
        {
            if (Interlocked.CompareExchange(ref _imageReconcileFired, 1, 0) != 0)
                return;

            try
            {
                ImageJobs.Manager.ReconcileInterruptedJobs();
            }
            catch
            {
                Volatile.Write(ref _imageReconcileFired, 0);
                throw;
            }
        }

        public void BackfillVideoSidecarsOnce(
            VideoSidecarBackfillStartupOptions? startupOptions = null)
        {
            var options = startupOptions ?? VideoSidecarBackfillStartupOptions.Default;
            if (!options.Enabled)
                return;

            if (Interlocked.CompareExchange(ref _videoSidecarBackfillFired, 1, 0) != 0)
                return;

            try
            {
                var bundle = Video;
                _backfillScheduler.Schedule(async () =>
                {
                    try
                    {
                        var result = await bundle.SidecarBackfill
                            .BackfillMissingSidecarsAsync(
                                options.ServiceOptions,
                                CancellationToken.None)
                            .ConfigureAwait(false);
                        TryInvokeCompleted(options.OnCompleted, result);
                    }
                    catch (Exception ex)
                    {
                        TryInvokeFailed(options.OnFailed, ex);
                    }
                });
            }
            catch
            {
                Volatile.Write(ref _videoSidecarBackfillFired, 0);
                throw;
            }
        }

        private static void TryInvokeCompleted(
            Action<VideoSidecarBackfillResult>? callback,
            VideoSidecarBackfillResult result)
        {
            if (callback is null)
                return;

            try { callback(result); }
            catch { }
        }

        private static void TryInvokeFailed(
            Action<Exception>? callback,
            Exception exception)
        {
            if (callback is null)
                return;

            try { callback(exception); }
            catch { }
        }

        /// <summary>
        /// Atomically marks the root disposed and disposes any lazy
        /// subsystem bundles that were created. Per bundle this is a
        /// no-op when <see cref="Lazy{T}.IsValueCreated"/> is false — a
        /// session that never touched a subsystem does not pay a build
        /// cost just to dispose it.
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
        public void DisposeCreatedSubsystems()
        {
            if (Interlocked.CompareExchange(ref _disposed, 1, 0) != 0)
                return;

            if (_imageJobs.IsValueCreated
                && _imageJobs.Value.Manager is IDisposable imageJobManager)
            {
                imageJobManager.Dispose();
            }

            if (_mediaImports.IsValueCreated)
            {
                _mediaImports.Value.Dispose();
            }

            if (_video.IsValueCreated)
            {
                _video.Value.Manager.Dispose();
            }

            if (_reconstruction.IsValueCreated)
            {
                _reconstruction.Value.Manager.Dispose();
            }
        }
    }
}
