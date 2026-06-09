using System;
using System.IO;
using System.Linq;

namespace Rook.Services.Vision.Video.Extraction
{
    internal static class FfmpegBinaryResolver
    {
        private const string BinaryName = "ffmpeg.exe";

        public static FfmpegBinaryResolution Resolve(string configuredPath)
            => Resolve(
                bundledPath: null,
                configuredPath: configuredPath,
                pathEnvironment: null);

        public static FfmpegBinaryResolution Resolve(
            string? bundledPath = null,
            string? configuredPath = null,
            string? pathEnvironment = null)
        {
            if (!string.IsNullOrWhiteSpace(bundledPath))
            {
                var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(bundledPath));
                if (File.Exists(full))
                    return FfmpegBinaryResolution.Found(full, FfmpegBinaryResolutionSource.Bundled);
            }

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
                "ffmpeg.exe was not found. Provide bundled ffmpeg.exe, an explicit path, or add ffmpeg.exe to PATH.");
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

    internal static class FfmpegBundledBinaryLocator
    {
        public static string? GetInstalledFfmpegPath()
            => GetInstalledFfmpegPath(typeof(global::Rook.RookPlugin).Assembly.Location);

        internal static string? GetInstalledFfmpegPath(string? managedAssemblyLocation)
        {
            if (string.IsNullOrWhiteSpace(managedAssemblyLocation))
                return null;

            var pluginDirectory = Path.GetDirectoryName(managedAssemblyLocation);
            if (string.IsNullOrWhiteSpace(pluginDirectory))
                return null;

            var assemblyAdjacent = Path.Combine(pluginDirectory, "ffmpeg", "ffmpeg.exe");
            if (File.Exists(assemblyAdjacent))
                return assemblyAdjacent;

            var parentDirectory = Directory.GetParent(pluginDirectory)?.FullName;
            if (!string.IsNullOrWhiteSpace(parentDirectory))
            {
                var parentAdjacent = Path.Combine(parentDirectory, "ffmpeg", "ffmpeg.exe");
                if (File.Exists(parentAdjacent))
                    return parentAdjacent;
            }

            return assemblyAdjacent;
        }
    }
}
