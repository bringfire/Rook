using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal.Models;

namespace Rook.Vision.Qualification
{
    /// <summary>Enumerated byte manifests. Policy is frozen in the qualifier, never supplied by evidence.</summary>
    public static class RuntimeFreezeManifest
    {
        public static string HashBytes(byte[] value) { using var sha = SHA256.Create(); return BitConverter.ToString(sha.ComputeHash(value)).Replace("-", "").ToLowerInvariant(); }
        public static string HashFile(string path) { using var sha = SHA256.Create(); using var stream = File.OpenRead(path); return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
        public static JsonArray Inventory(string root, string kind)
        {
            root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (!Directory.Exists(root)) throw new DirectoryNotFoundException(root);
            var files = new JsonArray();
            foreach (string path in Walk(root, root, kind).OrderBy(p => p, StringComparer.Ordinal))
                files.Add(new JsonObject { ["path"] = Relative(root, path), ["sha256"] = HashFile(path), ["bytes"] = new FileInfo(path).Length });
            return files;
        }
        public static bool Matches(JsonArray frozen, JsonArray current) => ConfiguredEndpointQualification.Equal(frozen, current);
        public static int Capture(string repo, string pluginRoot, string mcpRoot, string output)
        {
            repo = Path.GetFullPath(repo); pluginRoot = Path.GetFullPath(pluginRoot); mcpRoot = Path.GetFullPath(mcpRoot);
            var roots = new JsonArray();
            void Add(string name, string path, string kind)
            {
                var files = Inventory(path, kind);
                if (files.Count == 0) throw new InvalidOperationException("Required frozen root is empty: " + name);
                roots.Add(new JsonObject { ["name"] = name, ["path"] = Path.GetFullPath(path), ["kind"] = kind, ["files"] = files });
            }
            foreach (var name in new[] { "src", "scripts", "mcp_server", "installer" }) Add("source/" + name, Path.Combine(repo, name), "source");
            foreach (var target in new[] { "net48", "net7.0", "net8.0" })
            {
                Add("built/managed/" + target, Path.Combine(repo, "src/Rook/bin/Release", target), "payload");
                Add("built/qualifier/" + target, Path.Combine(repo, "src/Rook.Vision.Qualification/bin/Release", target), "payload");
            }
            Add("built/native", Path.Combine(repo, "src/RookNative/bin/Release/x64"), "payload");
            Add("installed/plugin", pluginRoot, "installed"); Add("installed/mcp", mcpRoot, "installed");
            string exe = Path.Combine(repo, "src/Rook.Vision.Qualification/bin/Release/net48/Rook.Vision.Qualification.exe");
            var psi = new ProcessStartInfo("git", "rev-parse HEAD") { WorkingDirectory = repo, UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true };
            using var p = Process.Start(psi)!; string commit = p.StandardOutput.ReadToEnd().Trim(); p.WaitForExit();
            if (p.ExitCode != 0 || commit.Length != 40) throw new InvalidOperationException("Cannot establish Git commit.");
            var catalog = new FalCatalogCompiler().Compile(Path.Combine(repo, "src/Rook/Services/Vision/Fal/Models"), VisionProviderRegistrations.GetLegacyModelIds());
            if (catalog.Catalog == null) throw new InvalidOperationException("Cannot freeze an invalid source catalog.");
            ConfiguredEndpointQualification.Write(output, new JsonObject { ["schema_version"] = 1, ["policy"] = "fal-runtime-freeze-v1", ["commit"] = commit,
                ["created_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["catalog_models"] = new JsonArray(catalog.Catalog.Definitions.Select(d => (JsonNode?)JsonValue.Create(d.ModelId)).ToArray()),
                ["catalog_endpoints"] = new JsonArray(catalog.Catalog.Definitions.SelectMany(d => d.Operations).Select(o => (JsonNode?)JsonValue.Create(o.EndpointId)).ToArray()), ["repo"] = repo, ["plugin_root"] = pluginRoot, ["mcp_root"] = mcpRoot,
                ["qualifier"] = exe, ["qualifier_sha256"] = HashFile(exe), ["roots"] = roots,
                ["catalog_allowlist"] = new JsonArray("src/Rook/Services/Vision/Fal/Models/**/*.json", "managed/net48/vision-models/fal/**/*.json", "managed/net7.0/vision-models/fal/**/*.json", "managed/net8.0/vision-models/fal/**/*.json"),
                ["loaded_runtime_evidence"] = "Required separately; an on-disk inventory is not proof of loaded code." });
            return 0;
        }
        private static IEnumerable<string> Walk(string root, string directory, string kind)
        {
            CheckPath(directory);
            foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
            {
                var relative = Relative(root, entry);
                if (Excluded(relative, kind)) continue;
                CheckPath(entry);
                if ((File.GetAttributes(entry) & FileAttributes.Directory) != 0) { foreach (var file in Walk(root, entry, kind)) yield return file; }
                else yield return entry;
            }
        }
        private static void CheckPath(string path)
        {
            var current = new DirectoryInfo(Path.GetDirectoryName(path)!);
            while (current != null) { if ((current.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Reparse path in freeze."); current = current.Parent; }
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("Reparse entry in freeze.");
        }
        private static string Relative(string root, string path) => path.Substring(root.Length + 1).Replace('\\', '/');
        private static bool FileLikeData(string name) => new[] { ".log", ".jsonl", ".db", ".sqlite", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".wav", ".tmp" }.Any(ext => name.EndsWith(ext, StringComparison.OrdinalIgnoreCase));
        private static bool Excluded(string path, string kind)
        {
            var parts = path.Split('/'); var name = parts[parts.Length - 1];
            // Generated bytecode is never authoritative executable source. Secret filenames are exact.
            if (parts.Any(p => p == "__pycache__" || p == ".pytest_cache" || p == ".git") || name == ".env" || name == "secrets.json" || name.EndsWith(".pyc", StringComparison.OrdinalIgnoreCase)) return true;
            if (kind == "source")
            {
                if (parts.Any(p => p == "bin" || p == "obj" || p == ".venv" || p == "node_modules") || parts[0] == "runtime" || parts[0] == "artifacts") return true;
                // The Models directory also contains the compiler. Only catalog JSON may change.
                if (path.StartsWith("Rook/Services/Vision/Fal/Models/", StringComparison.Ordinal) && name.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) return true;
            }
            // Mutable installed directories exclude data only. Executable/source payloads there
            // remain enumerated, so moving code under a log/data directory cannot bypass the gate.
            if (kind == "installed" && parts.Length > 1 && (parts[0] == "logs" || parts[0] == "artifacts" || parts[0] == "data" || parts[0] == "cache") &&
                FileLikeData(name)) return true;
            // Exact runtime catalog locations only; unexpected code in a catalog remains frozen.
            if (name.EndsWith(".json", StringComparison.OrdinalIgnoreCase) && (path.StartsWith("vision-models/fal/", StringComparison.Ordinal) ||
                new[] { "managed/net48/vision-models/fal/", "managed/net7.0/vision-models/fal/", "managed/net8.0/vision-models/fal/" }.Any(prefix => path.StartsWith(prefix, StringComparison.Ordinal)))) return true;
            return false;
        }
    }
}
