using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;
using Xunit;

namespace Rook.Tests
{
    public class RookSubsystemRootTests
    {
        [Fact]
        public void ImageJobs_factory_wires_replicate_authenticated_output_selector()
        {
            var source = File.ReadAllText(FindSourceFile(
                "src", "Rook", "RookSubsystemRoot.cs"));

            Assert.Contains("ReplicateImageArtifactRequestFactorySelector", source);
            Assert.Contains("GenerationSecretKeys.ReplicateApiToken", source);
            Assert.Contains(".Select", source);
            Assert.Contains("new ImageJobManager", source);
        }

        [Fact]
        public void Reconstruction_subsystem_reconciles_on_create_and_disposes_manager()
        {
            var source = File.ReadAllText(FindSourceFile(
                "src", "Rook", "RookSubsystemRoot.cs"));

            // CreateReconstruction reconciles interrupted jobs after building the manager...
            Assert.Contains("manager.ReconcileInterruptedJobs();", source);
            // ...and the teardown path disposes the reconstruction manager.
            Assert.Contains("_reconstruction.Value.Manager.Dispose();", source);
        }

        [Fact]
        public void VertexTokenSource_AllowsOnlyOnePreImageConfiguration()
        {
            var root = NewRoot();
            var first = new FakeVertexAccessTokenSource();
            var second = new FakeVertexAccessTokenSource();

            root.ConfigureVertexAccessTokenSource(first);
            root.ConfigureVertexAccessTokenSource(first);

            Assert.Throws<InvalidOperationException>(
                () => root.ConfigureVertexAccessTokenSource(second));
        }

        [Fact]
        public void VertexTokenSource_RejectsFirstConfigurationAfterImageRegistryCreation()
        {
            var root = NewRoot();
            _ = root.ImageJobs;

            Assert.Throws<InvalidOperationException>(() =>
                root.ConfigureVertexAccessTokenSource(
                    new FakeVertexAccessTokenSource()));
        }

        [Fact]
        public void VertexTokenSource_ConcurrentFirstConfigurationAdmitsExactlyOneInstance()
        {
            var root = NewRoot();
            var sources = new[]
            {
                new FakeVertexAccessTokenSource(),
                new FakeVertexAccessTokenSource(),
            };
            var successCount = 0;
            var rejectionCount = 0;

            Parallel.ForEach(sources, source =>
            {
                try
                {
                    root.ConfigureVertexAccessTokenSource(source);
                    Interlocked.Increment(ref successCount);
                }
                catch (InvalidOperationException)
                {
                    Interlocked.Increment(ref rejectionCount);
                }
            });

            Assert.Equal(1, successCount);
            Assert.Equal(1, rejectionCount);
        }

        [Fact]
        public async Task ImageJobs_FirstAccessSerializesWithTokenConfigurationGate()
        {
            var root = NewRoot();
            var syncField = typeof(RookSubsystemRoot).GetField(
                "_vertexTokenSourceSync",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(syncField);
            var sync = syncField!.GetValue(root)!;
            using var accessStarted = new ManualResetEventSlim(false);
            Task? imageAccess = null;

            Monitor.Enter(sync);
            try
            {
                imageAccess = Task.Run(() =>
                {
                    accessStarted.Set();
                    _ = root.ImageJobs;
                });
                Assert.True(
                    accessStarted.Wait(TimeSpan.FromSeconds(2)),
                    "ImageJobs access did not start.");
                Assert.False(
                    imageAccess.Wait(TimeSpan.FromMilliseconds(250)),
                    "ImageJobs escaped the token-configuration synchronization gate.");
            }
            finally
            {
                Monitor.Exit(sync);
            }

            await imageAccess!;
            Assert.Throws<InvalidOperationException>(() =>
                root.ConfigureVertexAccessTokenSource(
                    new FakeVertexAccessTokenSource()));
        }

        [Fact]
        public void RootRemainsUiNeutral()
        {
            var source = File.ReadAllText(FindSourceFile(
                "src", "Rook", "RookSubsystemRoot.cs"));

            Assert.Contains("IVertexAccessTokenSource", source);
            Assert.DoesNotContain("Rook.UI.Chat", source);
            Assert.DoesNotContain("ChatService", source);
        }

        private static RookSubsystemRoot NewRoot() =>
            new RookSubsystemRoot(
                artifactStore: null,
                generationSecretStore: null,
                ledger: null,
                imageLedger: null,
                vertexAccessTokenSource: null);

        private sealed class FakeVertexAccessTokenSource : IVertexAccessTokenSource
        {
            public Task<VertexAccessTokenResult> AcquireAsync(
                string qualifiedModelKey,
                CancellationToken cancellationToken) =>
                Task.FromResult(new VertexAccessTokenResult(
                    Lease: null,
                    Failure: new VertexAccessTokenFailure(
                        "test_failure",
                        "test failure",
                        Retryable: false)));
        }

        private static string FindSourceFile(params string[] parts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(new[] { dir.FullName }.Concat(parts).ToArray());
                if (File.Exists(candidate))
                    return candidate;
                dir = dir.Parent;
            }
            throw new FileNotFoundException("Could not locate " + Path.Combine(parts));
        }
    }
}
