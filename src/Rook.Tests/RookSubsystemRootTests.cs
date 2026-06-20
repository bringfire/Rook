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
    }
}
