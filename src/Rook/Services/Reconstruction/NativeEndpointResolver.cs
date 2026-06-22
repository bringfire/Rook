using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction
{
    /// <summary>
    /// Resolves the HTTP port of the Rook native plugin server for THIS Rhino process,
    /// so the managed import client can loop a request back to the native importer.
    /// </summary>
    public interface INativeEndpointResolver
    {
        int? ResolveNativePort();
    }

    /// <summary>
    /// Reads the native plugin's discovery file(s) and selects the endpoint for this process.
    /// Native writes its discovery file under <see cref="RookPaths.SharedDiscoveryFolder"/>,
    /// with a legacy fallback under <see cref="RookPaths.DiscoveryFolder"/> (%TEMP%\rook).
    /// </summary>
    public sealed class DiscoveryFileNativeEndpointResolver : INativeEndpointResolver
    {
        private readonly IReadOnlyList<string> _folders;

        public DiscoveryFileNativeEndpointResolver(IReadOnlyList<string>? folders = null)
        {
            _folders = folders ?? new[] { RookPaths.SharedDiscoveryFolder, RookPaths.DiscoveryFolder };
        }

        public int? ResolveNativePort()
        {
            var docs = new List<JsonObject>();
            foreach (var folder in _folders)
            {
                if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder)) continue;
                foreach (var file in Directory.EnumerateFiles(folder, "*.json"))
                {
                    try
                    {
                        if (JsonNode.Parse(File.ReadAllText(file)) is JsonObject obj)
                            docs.Add(obj);
                    }
                    catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
                    {
                        // Skip unreadable/partial discovery files.
                    }
                }
            }

            return NativeEndpointResolver.SelectNativePort(docs, Process.GetCurrentProcess().Id);
        }
    }

    public static class NativeEndpointResolver
    {
        /// <summary>
        /// Pure selection: the native (<c>pluginType=="native"</c>) discovery entry whose
        /// <c>processId</c> matches THIS OS process (native + companion share the process).
        /// Load-bearing multi-Rhino safety gate. Only loopback hosts are accepted (the
        /// "no arbitrary URL" invariant, pinned at discovery). Exactly one native endpoint
        /// per process is expected; 0 matches, or an ambiguous &gt;1 DISTINCT endpoint for
        /// this PID, fails closed (caller maps to <c>native_unavailable</c>) rather than
        /// guessing. The same endpoint mirrored into shared + legacy folders is deduped
        /// (it is not ambiguity).
        /// </summary>
        public static int? SelectNativePort(IEnumerable<JsonObject> docs, int currentProcessId)
        {
            var ports = new List<int>();
            foreach (var doc in docs)
            {
                if (!string.Equals(ReadString(doc, "pluginType"), "native", StringComparison.Ordinal)) continue;
                if (ReadInt(doc, "processId") != currentProcessId) continue;
                if (!IsLoopbackHost(ReadString(doc, "host"))) continue;   // never loop back to a non-local host
                var port = ReadInt(doc, "port");
                if (port is > 0) ports.Add(port.Value);
            }

            // Dedupe identical endpoints (same record mirrored across shared + legacy folders).
            // Ambiguity = two DIFFERENT ports for this PID → fail closed.
            var distinct = ports.Distinct().ToList();
            return distinct.Count == 1 ? distinct[0] : (int?)null;
        }

        private static bool IsLoopbackHost(string? host)
            => string.Equals(host, "127.0.0.1", StringComparison.Ordinal)
               || string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase);

        private static string? ReadString(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

        private static int? ReadInt(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<int>(out var i) ? i : (int?)null;
    }
}
