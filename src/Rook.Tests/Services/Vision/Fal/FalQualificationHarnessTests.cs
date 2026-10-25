using System;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Vision.Qualification;
using Xunit;
namespace Rook.Tests.Services.Vision.Fal
{
    public class FalQualificationHarnessTests
    {
        [Theory]
        [InlineData("added")] [InlineData("modified")] [InlineData("removed")]
        public void Freeze_detects_added_modified_or_removed_code_including_Models_compiler(string mutation)
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-freeze-" + Guid.NewGuid().ToString("N"));
            var dir = Path.Combine(root, "Rook/Services/Vision/Fal/Models"); Directory.CreateDirectory(dir);
            try
            {
                string compiler = Path.Combine(dir, "FalCatalogCompiler.cs"); File.WriteAllText(compiler, "compiler");
                var frozen = RuntimeFreezeManifest.Inventory(root, "source"); Assert.Single(frozen);
                if (mutation == "added") File.WriteAllText(Path.Combine(dir, "new.cs"), "new code");
                if (mutation == "modified") File.WriteAllText(compiler, "changed");
                if (mutation == "removed") File.Delete(compiler);
                Assert.False(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "source")));
            }
            finally { Directory.Delete(root, true); }
        }
        [Theory]
        [InlineData("net48")] [InlineData("net7.0")] [InlineData("net8.0")]
        public void Freeze_allows_only_catalog_JSON_and_declared_root_mutable_data(string runtime)
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-freeze-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
            try
            {
                File.WriteAllText(Path.Combine(root, "runtime.dll"), "runtime");
                var frozen = RuntimeFreezeManifest.Inventory(root, "installed");
                var catalog = Path.Combine(root, "managed/" + runtime + "/vision-models/fal"); Directory.CreateDirectory(catalog); File.WriteAllText(Path.Combine(catalog, "model.json"), "{}");
                Directory.CreateDirectory(Path.Combine(root, "logs")); File.WriteAllText(Path.Combine(root, "logs/run.log"), "mutable");
                Assert.True(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
                File.WriteAllText(Path.Combine(catalog, "adapter.dll"), "injected");
                Assert.False(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
            }
            finally { Directory.Delete(root, true); }
        }
        [Fact]
        public void Evidence_redacts_urls_raw_media_and_credentials_but_preserves_exact_scalars()
        {
            var safe = ConfiguredEndpointQualification.Sanitize(JsonNode.Parse("""{"seed":9007199254740991,"strength":0.123456,"audio":false,"api_key":"secret","media":["data:image/png;base64,AA","https://v3.fal.media/private"]}"""))!;
            Assert.False(safe.AsObject().ContainsKey("api_key")); Assert.Equal(9007199254740991L, safe["seed"]!.GetValue<long>());
            Assert.Equal(.123456m, safe["strength"]!.GetValue<decimal>()); Assert.False(safe["audio"]!.GetValue<bool>());
            Assert.DoesNotContain("base64", safe.ToJsonString()); Assert.DoesNotContain("private", safe.ToJsonString());
        }
    }
}
