using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed record VerifiedFramingRendererResult(VerifiedFramingRenderer? Renderer, string? FailureDetail);
    internal sealed class VerifiedFramingRenderer : IDisposable
    {
        private readonly FileStream _executionLock;
        public string Path { get; }
        private VerifiedFramingRenderer(string path, FileStream held) { Path = path; _executionLock = held; }
        public static VerifiedFramingRendererResult Resolve(string? bundledPath)
        {
            FileStream? held = null;
            try
            {
                if (string.IsNullOrWhiteSpace(bundledPath)) return new(null, "renderer_unavailable");
                var fullPath = System.IO.Path.GetFullPath(bundledPath!);
                held = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read);
                using var sha = SHA256.Create();
                string hash = BitConverter.ToString(sha.ComputeHash(held)).Replace("-", "");
                string provenance = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(fullPath)!, "ffmpeg-provenance.json");
                using var evidence = new FileStream(provenance, FileMode.Open, FileAccess.Read, FileShare.Read);
                if (evidence.Length > 65_536) return new(null, "renderer_profile_mismatch");
                using var reader = new StreamReader(evidence);
                var json = JsonNode.Parse(reader.ReadToEnd()) as JsonObject;
                if (!string.Equals(hash, VideoFramingRendererProfile.Sha256, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(json?["binary_sha256"]?.GetValue<string>(), hash, StringComparison.OrdinalIgnoreCase))
                    return new(null, "renderer_profile_mismatch");
                var result = new VerifiedFramingRenderer(fullPath, held); held = null; return new(result, null);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or System.Text.Json.JsonException or InvalidOperationException)
            { return new(null, "renderer_unavailable"); }
            finally { held?.Dispose(); }
        }
        public void Dispose() => _executionLock.Dispose();
    }
}
