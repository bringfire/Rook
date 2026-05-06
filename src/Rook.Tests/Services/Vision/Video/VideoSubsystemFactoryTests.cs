using System;
using System.Linq;
using System.Threading;
using Rook.Artifacts;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// V2 factory tests. Cover the composition surface (everything
    /// non-null, registry resolves real Veo ids, estimator wired with the
    /// resolved model) without exercising provider HTTP — those paths
    /// live in <see cref="VeoProviderTests"/> / <see cref="VeoClientTests"/>.
    /// </summary>
    public class VideoSubsystemFactoryTests
    {
        private static (IGenerationSecretStore Secrets, ArtifactStore Artifacts) FreshDeps()
        {
            // ArtifactStore.overrideRoot=null is fine here — the factory
            // tests never write or read blobs. The secret store similarly
            // is wired but never queried for its key in these tests.
            return (new DpapiGenerationSecretStore(), new ArtifactStore());
        }

        [Fact]
        public void Build_ReturnsNonNullBundle_WithAllSubsystems()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.NotNull(bundle);
                Assert.NotNull(bundle.Manager);
                Assert.NotNull(bundle.Registry);
                Assert.NotNull(bundle.Estimator);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_RegistryResolvesKnownVeoModel()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.True(bundle.Registry.TryResolve(
                    "veo-3.1-lite-generate-preview", out var resolved));
                Assert.Equal("veo-3.1-lite-generate-preview", resolved.ModelId);
                Assert.Equal("veo", resolved.ProviderName);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_RegistryRejectsUnknownModel()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.False(bundle.Registry.TryResolve(
                    "fictional-model-x", out _));
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_RegistryEnumeratesExactVeoCapabilitiesModelIdSet()
        {
            // Tightened from a count check (Codex review): pin the
            // exact model-id set so a future drift where one model is
            // added and another removed (same count) still trips this
            // test. Compares ordered string sets.
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                var expected = VeoCapabilities.Models.Keys
                    .Concat(new[]
                    {
                        FalVideoCapabilities.WanT2v,
                        FalVideoCapabilities.SeedanceI2v,
                    })
                    .OrderBy(k => k, StringComparer.Ordinal)
                    .ToArray();
                var actual = bundle.Registry.EnumerateAllModels()
                    .Select(m => m.ModelId)
                    .OrderBy(s => s, StringComparer.Ordinal)
                    .ToArray();

                Assert.Equal(expected, actual);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_registers_fal_wan_t2v_model()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                var fal = Assert.Single(
                    bundle.Registry.EnumerateAllModels(),
                    m => m.ModelId == FalVideoCapabilities.WanT2v);
                Assert.Equal(FalVideoCapabilities.ProviderName, fal.ProviderName);
                Assert.Equal(PricingKind.PerSecond, fal.PricingKind);
                Assert.Equal(new[] { VideoMode.T2V }, fal.Capability.Modes);
                Assert.False(fal.Capability.SupportsReferenceImages);
                Assert.Equal(0, fal.Capability.MaxReferenceImages);
                Assert.Empty(fal.Capability.Must8sWith);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_does_not_register_fal_i2v_model()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.DoesNotContain(
                    bundle.Registry.EnumerateAllModels(),
                    m => m.ModelId == "fal-ai/wan/v2.7/image-to-video");
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_EstimatorPricesKnownT2vRequest()
        {
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.True(bundle.Registry.TryResolve(
                    TestVideoFixtures.DefaultModelId, out var model));
                var request = TestVideoFixtures.DefaultT2vRequest();

                var result = bundle.Estimator.Estimate(model, request);

                Assert.True(result.Success);
                Assert.NotNull(result.Estimate);
                Assert.Equal(TestVideoFixtures.DefaultModelId, result.Estimate!.Model);
                Assert.True(result.Estimate.DollarsUsd > 0m);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_EstimatorFailsTypedOnRequestModelMismatch()
        {
            // F2 (V1c review) — the estimator boundary check rejects a
            // resolved model paired with a request whose Model field
            // disagrees. The factory does not bypass this guard; a caller
            // mismatching them sees InvalidRequest with field=Model.
            var (secrets, artifacts) = FreshDeps();

            var bundle = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.True(bundle.Registry.TryResolve(
                    "veo-3.1-lite-generate-preview", out var liteModel));
                var requestForFastModel = TestVideoFixtures.DefaultT2vRequest(
                    model: "veo-3.1-fast-generate-preview");

                var result = bundle.Estimator.Estimate(liteModel, requestForFastModel);

                Assert.False(result.Success);
                Assert.NotNull(result.Error);
                Assert.Equal(GenerationErrorCode.InvalidRequest, result.Error!.Code);
                Assert.Equal("Model", result.Error.Field);
            }
            finally { bundle.Manager.Dispose(); }
        }

        [Fact]
        public void Build_NullSecrets_Throws()
        {
            var artifacts = new ArtifactStore();
            Assert.Throws<ArgumentNullException>(
                () => VideoSubsystemFactory.Build(null!, artifacts));
        }

        [Fact]
        public void Build_NullArtifactStore_Throws()
        {
            var secrets = new DpapiGenerationSecretStore();
            Assert.Throws<ArgumentNullException>(
                () => VideoSubsystemFactory.Build(secrets, null!));
        }

        [Fact]
        public void Build_TwoCalls_ProduceIndependentBundles()
        {
            // Statelessness: factory holds no module-level state. Two
            // builds against the same inputs return distinct bundle
            // instances with distinct managers/registries/estimators.
            var (secrets, artifacts) = FreshDeps();

            var bundleA = VideoSubsystemFactory.Build(secrets, artifacts);
            var bundleB = VideoSubsystemFactory.Build(secrets, artifacts);
            try
            {
                Assert.NotSame(bundleA, bundleB);
                Assert.NotSame(bundleA.Manager, bundleB.Manager);
                Assert.NotSame(bundleA.Registry, bundleB.Registry);
                Assert.NotSame(bundleA.Estimator, bundleB.Estimator);
            }
            finally
            {
                bundleA.Manager.Dispose();
                bundleB.Manager.Dispose();
            }
        }
    }

    /// <summary>
    /// Tests for <see cref="RookSubsystemRoot"/>'s lazy video accessor
    /// and lifecycle methods. Uses the internal test ctor with an
    /// in-memory <see cref="FakeVideoJobLedger"/> so production state
    /// at <c>%APPDATA%\Rook\video\job-ledger.jsonl</c> is never touched
    /// — Codex review of step 2 follow-ups identified that a singleton-
    /// based reconcile test would append Interrupted records to the
    /// developer's real ledger.
    /// </summary>
    public class RookSubsystemRootLifecycleTests
    {
        private static RookSubsystemRoot FreshRoot(
            IVideoJobLedger? ledger = null,
            IImageJobLedger? imageLedger = null) =>
            new(
                artifactStore: new ArtifactStore(),
                generationSecretStore: new DpapiGenerationSecretStore(),
                ledger: ledger ?? new FakeVideoJobLedger(),
                imageLedger: imageLedger ?? new FakeImageJobLedger());

        [Fact]
        public void Ctor_BuildsVisionSecretStoreAsShimOverSharedGenerationSecretStore()
        {
            var generationSecrets = new DpapiGenerationSecretStore();
            var root = new RookSubsystemRoot(
                artifactStore: new ArtifactStore(),
                generationSecretStore: generationSecrets,
                ledger: new FakeVideoJobLedger(),
                imageLedger: new FakeImageJobLedger());

            var shimField = typeof(VisionSecretStore).GetField(
                "_generationSecrets",
                System.Reflection.BindingFlags.Instance |
                System.Reflection.BindingFlags.NonPublic);
            Assert.NotNull(shimField);

            Assert.Same(generationSecrets, root.SharedGenerationSecretStore);
            Assert.Same(generationSecrets, shimField!.GetValue(root.SharedSecretStore));
        }

        [Fact]
        public void Video_ReturnsBundle_OnFirstAccess()
        {
            var root = FreshRoot();
            try
            {
                var bundle = root.Video;

                Assert.NotNull(bundle);
                Assert.NotNull(bundle.Manager);
                Assert.NotNull(bundle.Registry);
                Assert.NotNull(bundle.Estimator);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void Video_ReturnsSameInstance_OnRepeatedAccess()
        {
            // Lazy<T> ExecutionAndPublication thread-safe single-build.
            // Pinned because two consumers (registrar in step 5,
            // VisionWebSurface in step 6) will read this property and
            // must observe the SAME manager — sharing the in-memory
            // running-jobs dict and ledger writer.
            var root = FreshRoot();
            try
            {
                var first = root.Video;
                var second = root.Video;

                Assert.Same(first, second);
                Assert.Same(first.Manager, second.Manager);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void ImageJobs_ReturnsSameInstance_OnRepeatedAccess()
        {
            var root = FreshRoot();
            try
            {
                var first = root.ImageJobs;
                var second = root.ImageJobs;

                Assert.Same(first, second);
                Assert.Same(first.Manager, second.Manager);
                Assert.Same(first.Registry, second.Registry);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void Video_AfterDispose_ThrowsObjectDisposed()
        {
            // Codex important #1: dispose must close the root. A late
            // caller hitting Video after Dispose-without-build would
            // otherwise lazy-build a manager that escapes the only
            // disposal pass.
            var root = FreshRoot();
            root.DisposeVideoSubsystemIfCreated();

            var ex = Assert.Throws<ObjectDisposedException>(() => _ = root.Video);
            Assert.Contains(nameof(RookSubsystemRoot), ex.Message);
        }

        [Fact]
        public void ImageJobs_AfterDispose_ThrowsObjectDisposed()
        {
            var root = FreshRoot();
            root.DisposeVideoSubsystemIfCreated();

            Assert.Throws<ObjectDisposedException>(() => _ = root.ImageJobs);
        }

        [Fact]
        public void Video_AfterBuildThenDispose_ThrowsObjectDisposed()
        {
            // Symmetric coverage: dispose-after-build also closes the
            // root (manager already disposed; subsequent access throws
            // rather than returning a torn-down bundle).
            var root = FreshRoot();
            _ = root.Video;
            root.DisposeVideoSubsystemIfCreated();

            Assert.Throws<ObjectDisposedException>(() => _ = root.Video);
        }

        [Fact]
        public void DisposeVideoSubsystemIfCreated_BeforeBuild_DoesNotForceBuild()
        {
            // No-op path: if Video was never accessed, dispose must not
            // build it just to dispose. Verified by checking that the
            // FakeVideoJobLedger received no Append calls (a built
            // manager performs no appends on construction, but a
            // reconcile-on-build path would; this test pins "no
            // construction" indirectly by the post-dispose throw).
            var fakeLedger = new FakeVideoJobLedger();
            var root = FreshRoot(fakeLedger);

            root.DisposeVideoSubsystemIfCreated();

            Assert.Throws<ObjectDisposedException>(() => _ = root.Video);
            Assert.Empty(fakeLedger.AllRecords);
        }

        [Fact]
        public void DisposeVideoSubsystemIfCreated_RepeatedCalls_AreIdempotent()
        {
            // Codex review: VideoJobManager.Dispose is NOT idempotent —
            // a second call disposes _shutdownCts twice and throws
            // ObjectDisposedException. The root's Interlocked guard is
            // the load-bearing protection; pin it.
            var root = FreshRoot();
            _ = root.Video;

            root.DisposeVideoSubsystemIfCreated();
            root.DisposeVideoSubsystemIfCreated();
            root.DisposeVideoSubsystemIfCreated();
        }

        [Fact]
        public void ReconcileVideoJobsOnce_RepeatedCalls_OnlyFireOnce()
        {
            // Seed the ledger with a non-terminal record so reconcile
            // does observable work (appends an Interrupted snapshot).
            // Repeat the call; the Interlocked guard short-circuits
            // subsequent invocations and no additional Interrupted
            // snapshot is appended.
            var fakeLedger = new FakeVideoJobLedger();
            var pollingRecord = MakePollingRecord();
            fakeLedger.Append(pollingRecord);

            var root = FreshRoot(fakeLedger);
            try
            {
                root.ReconcileVideoJobsOnce();
                root.ReconcileVideoJobsOnce();
                root.ReconcileVideoJobsOnce();

                var interruptedCount = fakeLedger.AllRecords
                    .Count(r => r.State == VideoJobState.Interrupted
                                && r.JobId == pollingRecord.JobId);
                Assert.Equal(1, interruptedCount);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void ReconcileVideoJobsOnce_OnFailure_ResetsFlagForRetry()
        {
            // Codex minor #3: if reconcile throws, a later caller
            // (next plugin Idle tick) must be able to retry. The flag
            // resets on throw; only successful completion latches it.
            var throwingLedger = new ThrowingReadLedger();
            var root = FreshRoot(throwingLedger);
            try
            {
                Assert.Throws<System.IO.IOException>(() => root.ReconcileVideoJobsOnce());
                Assert.Throws<System.IO.IOException>(() => root.ReconcileVideoJobsOnce());

                Assert.Equal(2, throwingLedger.ReadAttempts);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void ReconcileVideoJobsOnce_AfterDispose_ThrowsObjectDisposed()
        {
            // Reconcile reaches Video.Manager; the Video getter throws
            // ObjectDisposedException post-dispose, surfacing the
            // same shutdown signal.
            var root = FreshRoot();
            root.DisposeVideoSubsystemIfCreated();

            Assert.Throws<ObjectDisposedException>(
                () => root.ReconcileVideoJobsOnce());
        }

        [Fact]
        public void ReconcileImageJobsOnce_RepeatedCalls_OnlyFireOnce()
        {
            var fakeImageLedger = new FakeImageJobLedger();
            var jobId = Guid.NewGuid();
            fakeImageLedger.Append(ImageJobLedgerRecordFactory.FromInitial(
                jobId,
                GeminiImageCapabilities.ProviderName,
                GeminiImageCapabilities.DefaultModel,
                ImageJobState.Polling,
                DateTimeOffset.UtcNow));

            var root = FreshRoot(imageLedger: fakeImageLedger);
            try
            {
                root.ReconcileImageJobsOnce();
                root.ReconcileImageJobsOnce();
                root.ReconcileImageJobsOnce();

                var interruptedCount = fakeImageLedger.AllRecords
                    .Count(r => r.State == ImageJobState.Interrupted
                                && r.JobId == jobId);
                Assert.Equal(1, interruptedCount);
            }
            finally { root.DisposeVideoSubsystemIfCreated(); }
        }

        [Fact]
        public void ReconcileImageJobsOnce_AfterDispose_ThrowsObjectDisposed()
        {
            var root = FreshRoot();
            root.DisposeVideoSubsystemIfCreated();

            Assert.Throws<ObjectDisposedException>(
                () => root.ReconcileImageJobsOnce());
        }

        private static VideoJobRecord MakePollingRecord()
        {
            var resolvedModel = TestVideoFixtures.VeoLiteResolved();
            var request = TestVideoFixtures.DefaultT2vRequest(seed: 42);
            var estimate = new VideoCostEstimator()
                .Estimate(resolvedModel, request).Estimate!;
            return VideoJobRecordFactory.From(
                jobId: Guid.NewGuid(),
                request, resolvedModel, estimate,
                VideoJobState.Polling,
                DateTime.UtcNow);
        }

        private sealed class ThrowingReadLedger : IVideoJobLedger
        {
            public int ReadAttempts;

            public void Append(VideoJobRecord record) { }

            public VideoJobLedgerReadResult ReadAll()
            {
                Interlocked.Increment(ref ReadAttempts);
                throw new System.IO.IOException(
                    "simulated ledger read failure");
            }
        }
    }
}
