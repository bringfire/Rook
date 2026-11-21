using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Vision.Qualification;
using Xunit;
namespace Rook.Tests.Services.Vision.Fal
{
    public class FalQualificationHarnessTests
    {
        [Theory]
        [InlineData("added")] [InlineData("modified")] [InlineData("removed")]
        public void Freeze_tracks_standalone_sourceless_python_bytecode(string mutation)
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-freeze-bytecode-" + Guid.NewGuid().ToString("N"));
            string package = Path.Combine(root, "venv/Lib/site-packages/package"); Directory.CreateDirectory(package);
            try
            {
                string module = Path.Combine(package, "module.pyc");
                if (mutation != "added") File.WriteAllBytes(module, new byte[] { 1, 2, 3 });
                var frozen = RuntimeFreezeManifest.Inventory(root, "installed");
                if (mutation == "removed") File.Delete(module); else File.WriteAllBytes(module, new byte[] { 4, 5, 6 });
                Assert.False(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
                var beforeCache = RuntimeFreezeManifest.Inventory(root, "installed");
                string cache = Path.Combine(package, "__pycache__"); Directory.CreateDirectory(cache); File.WriteAllBytes(Path.Combine(cache, "generated.cpython-311.pyc"), new byte[] { 7 });
                Assert.True(RuntimeFreezeManifest.Matches(beforeCache, RuntimeFreezeManifest.Inventory(root, "installed")));
            }
            finally { Directory.Delete(root, true); }
        }
        [Fact]
        public void File_hash_matches_known_bytes_across_multiple_buffers_and_tail()
        {
            string path = Path.Combine(Path.GetTempPath(), "rook-freeze-hash-" + Guid.NewGuid().ToString("N"));
            byte[] data = new byte[2 * 1024 * 1024 + 137];
            for (int i = 0; i < data.Length; i++) data[i] = (byte)(i * 31 + i / 251);
            try { File.WriteAllBytes(path, data); Assert.Equal(RuntimeFreezeManifest.HashBytes(data), RuntimeFreezeManifest.HashFile(path)); }
            finally { File.Delete(path); }
        }
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
                var catalog = Path.Combine(root, runtime + "/vision-models/fal"); Directory.CreateDirectory(catalog); File.WriteAllText(Path.Combine(catalog, "model.json"), "{}");
                Directory.CreateDirectory(Path.Combine(root, "logs")); File.WriteAllText(Path.Combine(root, "logs/run.log"), "mutable");
                Assert.True(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
                File.WriteAllText(Path.Combine(catalog, "adapter.dll"), "injected");
                Assert.False(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
            }
            finally { Directory.Delete(root, true); }
        }
        [Theory]
        [InlineData("discovery/instance-123-native.json")]
        [InlineData("discovery/instance-123-native.json.tmp")]
        [InlineData("discovery/companion-123.json")]
        [InlineData("discovery/companion-load-123.log")]
        [InlineData("discovery/native-discovery-123.log")]
        [InlineData("registry/owned_sessions.db-wal")]
        [InlineData("registry/artifacts.db")]
        [InlineData("registry/work_units.db-shm")]
        [InlineData("data/rookchat/acp/v1/conversations/0123456789abcdef0123456789abcdef.json")]
        [InlineData("data/rookchat/acp/v1/presentation/0123456789abcdef0123456789abcdef/00000001.json")]
        [InlineData("data/rookchat/acp/v1/claims/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.open.claim")]
        [InlineData("data/dspy-cache/001/cache.db-wal")]
        [InlineData("app/chirp/data/dspy-cache/001/cache.db-shm")]
        [InlineData("data/context_history.json")]
        [InlineData("data/metrics.json")]
        [InlineData("data/agent_metrics.json")]
        public void Freeze_excludes_only_known_installed_writer_data(string path)
            => AssertInstalledAddition(path, excluded: true);

        [Theory]
        [InlineData("discovery/adapter.py")]
        [InlineData("discovery/unknown.json")]
        [InlineData("registry/adapter.dll")]
        [InlineData("registry/unknown.db")]
        [InlineData("chat/adapter.cs")]
        [InlineData("chat/prime/unknown.json")]
        [InlineData("data/rookchat/acp/v1/conversations/adapter.py")]
        [InlineData("data/rookchat/acp/v1/prime-uv/runtime.py")]
        [InlineData("data/model_profiles.json")]
        [InlineData("data/run.log/adapter.py")]
        [InlineData("net8.0/vision-models/fal/model.json/adapter.dll")]
        public void Freeze_keeps_code_and_unknown_files_in_mutable_locations(string path)
            => AssertInstalledAddition(path, excluded: false);

        private static void AssertInstalledAddition(string path, bool excluded)
        {
            string root = Path.Combine(Path.GetTempPath(), "rook-freeze-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
            try
            {
                File.WriteAllText(Path.Combine(root, "runtime.dll"), "runtime");
                var frozen = RuntimeFreezeManifest.Inventory(root, "installed");
                string file = Path.Combine(root, path); Directory.CreateDirectory(Path.GetDirectoryName(file)!); File.WriteAllText(file, "data or code");
                Assert.Equal(excluded, RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(root, "installed")));
            }
            finally { Directory.Delete(root, true); }
        }
        [Theory]
        [InlineData("target_changed")] [InlineData("target_added")] [InlineData("target_removed")]
        [InlineData("alias_added")] [InlineData("alias_removed")] [InlineData("alias_retargeted")]
        public void Freeze_tracks_real_contained_junction_identity_and_target_bytes(string mutation)
        {
            using var fixture = new JunctionFixture();
            string target = fixture.Directory("data/prime/python/version-one");
            string other = fixture.Directory("data/prime/python/version-two");
            string code = Path.Combine(target, "python.exe"); File.WriteAllText(code, "runtime bytes");
            File.WriteAllText(Path.Combine(other, "python.exe"), "other runtime");
            string alias = fixture.Link("data/prime/python/current", target);
            var frozen = RuntimeFreezeManifest.Inventory(fixture.Root, "installed");
            var record = frozen.Single(n => n!["path"]!.GetValue<string>() == "data/prime/python/current")!;
            Assert.Equal("directory_alias", record["kind"]!.GetValue<string>());
            Assert.Equal("Junction", record["link_type"]!.GetValue<string>());
            Assert.Equal("data/prime/python/version-one", record["target"]!.GetValue<string>());
            Assert.Contains(frozen, n => n!["path"]!.GetValue<string>() == "data/prime/python/version-one/python.exe" && n["sha256"]!.GetValue<string>() == RuntimeFreezeManifest.HashFile(code));
            if (mutation == "target_changed") File.WriteAllText(code, "changed runtime");
            if (mutation == "target_added") File.WriteAllText(Path.Combine(target, "adapter.py"), "new code");
            if (mutation == "target_removed") File.Delete(code);
            if (mutation == "alias_added") fixture.Link("data/prime/python/second", target);
            if (mutation == "alias_removed") Directory.Delete(alias);
            if (mutation == "alias_retargeted") { Directory.Delete(alias); fixture.Link("data/prime/python/current", other); }
            Assert.False(RuntimeFreezeManifest.Matches(frozen, RuntimeFreezeManifest.Inventory(fixture.Root, "installed")));
        }

        [Theory]
        [InlineData("external")] [InlineData("ancestor")] [InlineData("cycle")]
        [InlineData("unresolved")] [InlineData("chained")] [InlineData("source")] [InlineData("payload")] [InlineData("root")]
        public void Freeze_rejects_unsafe_real_junctions(string mode)
        {
            using var fixture = new JunctionFixture();
            using var outside = new JunctionFixture();
            string target = fixture.Directory("target");
            string other = fixture.Directory("other");
            string sentinel = Path.Combine(outside.Root, "unreadable.exe"); File.WriteAllText(sentinel, "external bytes must not be read");
            using var locked = new FileStream(sentinel, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
            string alias = fixture.Link("alias", mode == "external" ? outside.Root : target);
            if (mode == "ancestor") { Directory.Delete(alias); alias = fixture.Link("target/alias", target); }
            if (mode == "cycle") { Directory.Delete(alias); fixture.Link("target/to-other", other); fixture.Link("other/to-target", target); }
            if (mode == "unresolved") Directory.Delete(target);
            if (mode == "chained") fixture.Link("second", alias);
            string kind = mode == "source" || mode == "payload" ? mode : "installed";
            var error = Assert.ThrowsAny<IOException>(() => RuntimeFreezeManifest.Inventory(mode == "root" ? alias : fixture.Root, kind));
            if (mode == "external") Assert.Contains("outside", error.Message);
        }

        private sealed class JunctionFixture : IDisposable
        {
            public string Root { get; } = Path.Combine(Path.GetTempPath(), "rook-freeze-junction-" + Guid.NewGuid().ToString("N"));
            private readonly List<string> links = new List<string>();
            public JunctionFixture() { System.IO.Directory.CreateDirectory(Root); }
            public string Directory(string relative) { string path = Path.Combine(Root, relative); System.IO.Directory.CreateDirectory(path); return path; }
            public string Link(string relative, string target)
            {
                string path = Path.Combine(Root, relative); System.IO.Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                var start = new ProcessStartInfo("cmd.exe", "/c mklink /J \"" + path + "\" \"" + target + "\"") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
                using var process = Process.Start(start)!; Assert.True(process.WaitForExit(10000)); Assert.Equal(0, process.ExitCode);
                links.Add(path); return path;
            }
            public void Dispose()
            {
                foreach (string path in links.Distinct())
                {
                    try { if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) System.IO.Directory.Delete(path); }
                    catch (FileNotFoundException) { }
                    catch (DirectoryNotFoundException) { }
                }
                System.IO.Directory.Delete(Root, true);
            }
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
