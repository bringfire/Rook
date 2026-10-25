using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Text;
using System.Threading.Tasks;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal.Models;

namespace Rook.Vision.Qualification
{
    /// <summary>Enumerated byte manifests. Policy is frozen in the qualifier, never supplied by evidence.</summary>
    public static class RuntimeFreezeManifest
    {
        public static string HashBytes(byte[] value) { using var sha = SHA256.Create(); return BitConverter.ToString(sha.ComputeHash(value)).Replace("-", "").ToLowerInvariant(); }
        public static string HashFile(string path)
        {
            using var sha = SHA256.Create();
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024, FileOptions.SequentialScan);
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        public static JsonArray Inventory(string root, string kind)
        {
            root = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (!Directory.Exists(root)) throw new DirectoryNotFoundException(root);
            var records = new List<JsonObject>();
            var aliases = new List<JsonObject>();
            foreach (string path in Walk(root, root, kind, aliases))
                records.Add(new JsonObject { ["path"] = Relative(root, path), ["sha256"] = HashFile(path), ["bytes"] = new FileInfo(path).Length });
            RejectAliasCycles(aliases);
            records.AddRange(aliases);
            return new JsonArray(records.OrderBy(n => n["path"]!.GetValue<string>(), StringComparer.Ordinal).Select(n => (JsonNode)n).ToArray());
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
                ["catalog_allowlist"] = new JsonArray("src/Rook/Services/Vision/Fal/Models/**/*.json", "net48/vision-models/fal/**/*.json", "net7.0/vision-models/fal/**/*.json", "net8.0/vision-models/fal/**/*.json"),
                ["loaded_runtime_evidence"] = "Required separately; an on-disk inventory is not proof of loaded code." });
            return 0;
        }
        private static IEnumerable<string> Walk(string root, string directory, string kind, List<JsonObject> aliases)
        {
            CheckPath(directory);
            foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
            {
                var relative = Relative(root, entry);
                var attributes = File.GetAttributes(entry);
                bool directoryEntry = (attributes & FileAttributes.Directory) != 0;
                if (Excluded(relative, kind, directoryEntry)) continue;
                if (kind == "installed" && directoryEntry && (attributes & FileAttributes.ReparsePoint) != 0)
                {
                    aliases.Add(ReadContainedAlias(root, entry));
                    continue; // Never traverse the alias: its physical in-root target is visited normally.
                }
                CheckPath(entry);
                if (directoryEntry) { foreach (var file in Walk(root, entry, kind, aliases)) yield return file; }
                else yield return entry;
            }
        }
        private static JsonObject ReadContainedAlias(string root, string path)
        {
            // Fixed metadata-only command; paths never enter command text. Windows PowerShell
            // exposes a junction's raw target without opening any files in that target.
            var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell/v1.0/powershell.exe"),
                "-NoProfile -NonInteractive -Command \"$ErrorActionPreference='Stop'; $x=Get-Item -LiteralPath $env:ROOK_FREEZE_ALIAS_PATH -Force; [pscustomobject]@{link_type=$x.LinkType;targets=@($x.Target)} | ConvertTo-Json -Compress\"")
            { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardOutput = true, RedirectStandardError = true };
            start.EnvironmentVariables["ROOK_FREEZE_ALIAS_PATH"] = path;
            using var process = Process.Start(start)!;
            var output = ReadBounded(process.StandardOutput); var error = ReadBounded(process.StandardError);
            if (!process.WaitForExit(10000)) { process.Kill(); throw new IOException("Junction metadata lookup timed out."); }
            string json = output.GetAwaiter().GetResult(); string diagnostic = error.GetAwaiter().GetResult();
            if (process.ExitCode != 0 || diagnostic.Length != 0) throw new IOException("Junction metadata lookup failed.");
            JsonObject metadata;
            try { metadata = JsonNode.Parse(json)!.AsObject(); } catch (Exception e) { throw new IOException("Invalid junction metadata.", e); }
            if (metadata["link_type"]?.ToString() != "Junction" || metadata["targets"] is not JsonArray targets || targets.Count != 1 ||
                targets[0] is not JsonValue value || !value.TryGetValue<string>(out string? raw) || string.IsNullOrWhiteSpace(raw) || !Path.IsPathRooted(raw))
                throw new IOException("Only a resolved absolute single-target directory Junction can be frozen.");
            string target = Path.GetFullPath(raw).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (!target.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new IOException("Junction target is outside the frozen root.");
            if (path.Equals(target, StringComparison.OrdinalIgnoreCase) || path.StartsWith(target + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new IOException("Junction target is an ancestor or cycle.");
            // Reject chains before directory enumeration; external metadata is rejected above.
            CheckPath(target);
            if (!Directory.Exists(target)) throw new IOException("Junction target is unresolved.");
            string relativeTarget = Relative(root, target);
            // A generated-directory exclusion must never make an alias target invisible.
            string prefix = "";
            foreach (string segment in relativeTarget.Split('/'))
            {
                prefix = prefix.Length == 0 ? segment : prefix + "/" + segment;
                if (Excluded(prefix, "installed", true)) throw new IOException("Junction target is excluded from the physical inventory.");
            }
            byte[] identity = Encoding.UTF8.GetBytes("Junction\n" + relativeTarget);
            return new JsonObject { ["path"] = Relative(root, path), ["kind"] = "directory_alias", ["link_type"] = "Junction", ["target"] = relativeTarget, ["sha256"] = HashBytes(identity), ["bytes"] = identity.Length };
        }
        private static async Task<string> ReadBounded(StreamReader reader)
        {
            var result = new StringBuilder(); var buffer = new char[1024]; int count;
            while ((count = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) != 0)
            {
                if (result.Length + count > 16384) throw new IOException("Junction metadata exceeds the output bound.");
                result.Append(buffer, 0, count);
            }
            return result.ToString();
        }
        private static void RejectAliasCycles(List<JsonObject> aliases)
        {
            var active = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var done = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            void Visit(JsonObject alias)
            {
                string path = alias["path"]!.GetValue<string>();
                if (done.Contains(path)) return;
                if (!active.Add(path)) throw new IOException("Junction containment cycle in frozen root.");
                string target = alias["target"]!.GetValue<string>() + "/";
                foreach (var child in aliases.Where(a => a["path"]!.GetValue<string>().StartsWith(target, StringComparison.OrdinalIgnoreCase))) Visit(child);
                active.Remove(path); done.Add(path);
            }
            foreach (var alias in aliases) Visit(alias);
        }
        private static void CheckPath(string path)
        {
            var current = new DirectoryInfo(Path.GetDirectoryName(path)!);
            while (current != null) { if ((current.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Reparse path in freeze."); current = current.Parent; }
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("Reparse entry in freeze.");
        }
        private static string Relative(string root, string path) => path.Substring(root.Length + 1).Replace('\\', '/');
        private static bool FileLikeData(string name) => new[] { ".log", ".jsonl", ".db", ".sqlite", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".wav", ".tmp" }.Any(ext => name.EndsWith(ext, StringComparison.OrdinalIgnoreCase));
        // Exact writer contracts: native/companion discovery, MCP SQLite registries,
        // ACP conversation storage, metrics/history and the configured DSPy cache.
        // Configuration and unknown data remain frozen; none of these matches directories.
        private static readonly Regex InstalledWriterData = new Regex(@"\A(?:" +
            @"discovery/(?:instance-[0-9]+-native\.json(?:\.tmp)?|companion-[0-9]+\.json(?:\.tmp)?|(?:companion-load|native-discovery)-[0-9]+\.log)|" +
            @"registry/(?:owned_sessions|artifacts|work_units)\.db(?:-(?:wal|shm|journal))?|" +
            @"(?:data|app/chirp/data)/dspy-cache/(?:[0-9]{3}/)?cache\.db(?:-(?:wal|shm|journal))?|" +
            @"data/(?:context_history|metrics|agent_metrics)\.json|" +
            @"data/rookchat/acp/v1/(?:conversations/[0-9a-f]{32}\.json|presentation/[0-9a-f]{32}/[0-9]{8}\.json|claims/[0-9a-f]{64}\.open\.claim)" +
            @")\z", RegexOptions.CultureInvariant);
        private static bool Excluded(string path, string kind, bool directory)
        {
            var parts = path.Split('/'); var name = parts[parts.Length - 1];
            // Generated bytecode is never authoritative executable source. Secret filenames are exact.
            if (directory && (name == "__pycache__" || name == ".pytest_cache" || name == ".git")) return true;
            if (kind == "source")
            {
                if (directory && (name == "bin" || name == "obj" || name == ".venv" || name == "node_modules" || path == "runtime" || path == "artifacts")) return true;
            }
            // A directory named model.json or run.log must not hide executable children.
            if (directory) return false;
            if (name == ".env" || name == "secrets.json" || name.EndsWith(".pyc", StringComparison.OrdinalIgnoreCase)) return true;
            if (kind == "source")
            {
                // The Models directory also contains the compiler. Only catalog JSON may change.
                if (path.StartsWith("Rook/Services/Vision/Fal/Models/", StringComparison.Ordinal) && name.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) return true;
            }
            // Mutable installed directories exclude data only. Executable/source payloads there
            // remain enumerated, so moving code under a log/data directory cannot bypass the gate.
            if (kind == "installed" && parts.Length > 1 && (parts[0] == "logs" || parts[0] == "artifacts" || parts[0] == "data" || parts[0] == "cache") &&
                FileLikeData(name)) return true;
            if (kind == "installed" && InstalledWriterData.IsMatch(path)) return true;
            // Exact runtime catalog locations only; unexpected code in a catalog remains frozen.
            if (name.EndsWith(".json", StringComparison.OrdinalIgnoreCase) && (path.StartsWith("vision-models/fal/", StringComparison.Ordinal) ||
                new[] { "net48/vision-models/fal/", "net7.0/vision-models/fal/", "net8.0/vision-models/fal/" }.Any(prefix => path.StartsWith(prefix, StringComparison.Ordinal)))) return true;
            return false;
        }
    }
}
