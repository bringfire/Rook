using System;
using System.IO;
using System.Diagnostics;
using Rook.Services.Vision.Fal.Models;
using Xunit;
namespace Rook.Tests.Services.Vision.Fal
{
    [CollectionDefinition("Catalog cwd", DisableParallelization = true)]
    public class CatalogCwdCollection { }
    [Collection("Catalog cwd")]
    public class FalCatalogLoaderTests
    {
        [Fact]
        public void Loader_uses_assembly_directory_and_copies_state()
        {
            using var files = new CatalogFiles();
            string assembly = Path.Combine(files.Root, "runtime");
            string installed = Path.Combine(assembly, "vision-models", "fal");
            Directory.CreateDirectory(installed);
            File.Copy(Path.Combine(files.Root, "catalog.json"), Path.Combine(installed, "catalog.json"));
            File.Copy(Path.Combine(files.Root, "image.json"), Path.Combine(installed, "image.json"));
            var cwd = Environment.CurrentDirectory;
            try
            {
                Environment.CurrentDirectory = Path.GetTempPath();
                var result = new FalCatalogLoader().Load(assembly, Array.Empty<string>());
                Assert.Empty(result.Diagnostics);
                var binding = result.Catalog!.GetOperation("synthetic/image", "text_to_image");
                var originalHash = binding.DefinitionHash;
                var copy = binding.ToJson(); copy["endpoint_id"] = "modified";
                File.WriteAllText(Path.Combine(installed, "image.json"), "{}");
                Assert.Equal(originalHash, binding.DefinitionHash);
                Assert.Equal("fal-ai/synthetic/render", binding.EndpointId);
                Assert.Equal("fal-ai/synthetic/render", binding.ToJson()["endpoint_id"]!.GetValue<string>());
                var fieldCopy = binding.Fields[5].ToJson(); fieldCopy["default"] = "large";
                Assert.Equal("small", binding.Fields[5].Default!.GetValue<string>());
                var lookupCopy = binding.Fields[5].Payload.Lookup!; lookupCopy["small"] = "changed";
                Assert.Equal("S", binding.Fields[5].Payload.Lookup!["small"]!.GetValue<string>());
                var rateCopy = binding.Pricing!.Rates[0].Selectors; rateCopy["new"] = true;
                Assert.Empty(binding.Pricing.Rates[0].Selectors);
                var definitionCopy = result.Catalog.Definitions[0].ToJson(); definitionCopy["model_id"] = "changed";
                Assert.Equal("synthetic/image", result.Catalog.Definitions[0].ModelId);
            }
            finally { Environment.CurrentDirectory = cwd; }
        }
        [Fact]
        public void Empty_manifest_succeeds_and_missing_manifest_has_diagnostics()
        {
            using var files = new CatalogFiles(); files.Manifest();
            Assert.Empty(files.Compile().Catalog!.Definitions);
            File.Delete(Path.Combine(files.Root, "catalog.json"));
            FalCatalogCompilerTests.AssertInvalid(files.Compile());
            FalCatalogCompilerTests.AssertInvalid(new FalCatalogLoader().Load(files.Root, Array.Empty<string>()));
        }
        [Fact]
        public void Junction_references_are_rejected_instead_of_followed()
        {
            using var files = new CatalogFiles();
            using var outside = new CatalogFiles();
            var junction = Path.Combine(files.Root, "linked");
            var start = new ProcessStartInfo("cmd.exe", "/c mklink /J \"" + junction + "\" \"" + outside.Root + "\"") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using (var process = Process.Start(start)!) { process.WaitForExit(); Assert.Equal(0, process.ExitCode); }
            try { files.Manifest("linked/image.json"); FalCatalogCompilerTests.AssertInvalid(files.Compile()); }
            finally { Directory.Delete(junction); }
        }
    }
}
