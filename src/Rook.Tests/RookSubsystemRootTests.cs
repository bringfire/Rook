using System;
using System.IO;
using System.Linq;
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

        [Fact]
        public void VertexSourceConfigurationMustPrecedeEitherRegistryAndRootRemainsNeutral()
        {
            var root = new RookSubsystemRoot(null,null,new Rook.Tests.Services.Vision.Video.FakeVideoJobLedger(),new Rook.Tests.Services.Vision.Image.Jobs.FakeImageJobLedger());
            var source = new Rook.Tests.Services.Vision.Generation.VertexTestTokenSource();
            root.ConfigureVertexAccessTokenSource(source);
            root.ConfigureVertexAccessTokenSource(source);
            Assert.Throws<InvalidOperationException>(() => root.ConfigureVertexAccessTokenSource(new Rook.Tests.Services.Vision.Generation.VertexTestTokenSource()));
            Assert.True(root.ImageJobs.Registry.TryResolve("vertex_ai/gemini-3.1-flash-image",out var image));
            Assert.Equal("vertex_ai",image.ProviderName);
            root.DisposeCreatedSubsystems();
            var late = new RookSubsystemRoot(null,null,new Rook.Tests.Services.Vision.Video.FakeVideoJobLedger(),new Rook.Tests.Services.Vision.Image.Jobs.FakeImageJobLedger());
            _ = late.Video;
            Assert.Throws<InvalidOperationException>(() => late.ConfigureVertexAccessTokenSource(source));
            late.DisposeCreatedSubsystems();
            var code = File.ReadAllText(FindSourceFile("src","Rook","RookSubsystemRoot.cs"));
            Assert.DoesNotContain("Rook.UI.Chat",code);
        }
    }
}
