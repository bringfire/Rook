using System;
using System.IO;
using System.Linq;

namespace Rook.Services.Vision.Video.Extraction
{
    internal static class FfmpegBinaryResolver
    {
        private const string BinaryName = "ffmpeg.exe";

        public static FfmpegBinaryResolution Resolve(
            string? configuredPath = null,
            string? pathEnvironment = null)
        {
            if (!string.IsNullOrWhiteSpace(configuredPath))
            {
                var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(configuredPath));
                return File.Exists(full)
                    ? FfmpegBinaryResolution.Found(full, FfmpegBinaryResolutionSource.ConfiguredPath)
                    : FfmpegBinaryResolution.Failed(
                        FfmpegBinaryResolutionError.ConfiguredPathMissing,
                        $"Configured ffmpeg path does not exist: {full}");
            }

            foreach (var dir in SplitPath(pathEnvironment ?? Environment.GetEnvironmentVariable("PATH")))
            {
                var candidate = Path.Combine(dir, BinaryName);
                if (File.Exists(candidate))
                    return FfmpegBinaryResolution.Found(
                        Path.GetFullPath(candidate),
                        FfmpegBinaryResolutionSource.PathLookup);
            }

            return FfmpegBinaryResolution.Failed(
                FfmpegBinaryResolutionError.NotFound,
                "ffmpeg.exe was not found. Provide an explicit path or add ffmpeg.exe to PATH.");
        }

        private static string[] SplitPath(string? pathEnvironment)
        {
            if (string.IsNullOrWhiteSpace(pathEnvironment))
                return Array.Empty<string>();

            return pathEnvironment!
                .Split(new[] { Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries)
                .Select(p => p.Trim().Trim('"'))
                .Where(p => p.Length > 0)
                .ToArray();
        }
    }
}
