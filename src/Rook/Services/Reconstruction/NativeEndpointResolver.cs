using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
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
        /// Load-bearing multi-Rhino safety gate. Exactly one native endpoint per process is
        /// expected; 0 matches, or an ambiguous &gt;1 (stale/duplicate files for this PID),
        /// fails closed (caller maps to <c>native_unavailable</c>) rather than guessing.
        /// </summary>
        public static int? SelectNativePort(IEnumerable<JsonObject> docs, int currentProcessId)
        {
            var ports = new List<int>();
            foreach (var doc in docs)
            {
                if (!string.Equals(ReadString(doc, "pluginType"), "native", StringComparison.Ordinal)) continue;
                if (ReadInt(doc, "processId") != currentProcessId) continue;
                var port = ReadInt(doc, "port");
                if (port is > 0) ports.Add(port.Value);
            }

            return ports.Count == 1 ? ports[0] : (int?)null;
        }

        private static string? ReadString(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

        private static int? ReadInt(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<int>(out var i) ? i : (int?)null;
    }
}
