using System;
using System.IO;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public class FfmpegBinaryResolverTests : IDisposable
    {
        private readonly string _root;

        public FfmpegBinaryResolverTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-ffmpeg-resolver-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void Resolve_ExplicitExistingPath_WinsOverPathLookup()
        {
            var explicitPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));
            var pathExe = TouchExe(Path.Combine(_root, "path", "ffmpeg.exe"));

            var result = FfmpegBinaryResolver.Resolve(
                configuredPath: explicitPath,
                pathEnvironment: Path.GetDirectoryName(pathExe));

            Assert.True(result.Success);
            Assert.Equal(explicitPath, result.Path);
            Assert.Equal(FfmpegBinaryResolutionSource.ConfiguredPath, result.Source);
            Assert.Null(result.ErrorCode);
        }

        [Fact]
        public void Resolve_ConfiguredPathConvenienceOverload_ResolvesExistingConfiguredPath()
        {
            var configuredPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));

            var result = FfmpegBinaryResolver.Resolve(configuredPath);

            Assert.True(result.Success);
            Assert.Equal(configuredPath, result.Path);
            Assert.Equal(FfmpegBinaryResolutionSource.ConfiguredPath, result.Source);
            Assert.Null(result.ErrorCode);
        }

        [Fact]
        public void Resolve_BundledExistingPath_WinsOverConfiguredAndPathLookup()
        {
            var bundledPath = TouchExe(Path.Combine(_root, "bundled", "ffmpeg.exe"));
            var configuredPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));
            var pathExe = TouchExe(Path.Combine(_root, "path", "ffmpeg.exe"));

            var result = FfmpegBinaryResolver.Resolve(
                bundledPath: bundledPath,
                configuredPath: configuredPath,
                pathEnvironment: Path.GetDirectoryName(pathExe));

            Assert.True(result.Success);
            Assert.Equal(bundledPath, result.Path);
            Assert.Equal(FfmpegBinaryResolutionSource.Bundled, result.Source);
            Assert.Null(result.ErrorCode);
        }

        [Fact]
        public void Resolve_BundledMissingPath_FallsBackToConfiguredForDevConvenience()
        {
            var bundledPath = Path.Combine(_root, "bundled", "missing-ffmpeg.exe");
            var configuredPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));

            var result = FfmpegBinaryResolver.Resolve(
                bundledPath: bundledPath,
                configuredPath: configuredPath,
                pathEnvironment: null);

            Assert.True(result.Success);
            Assert.Equal(configuredPath, result.Path);
            Assert.Equal(FfmpegBinaryResolutionSource.ConfiguredPath, result.Source);
        }

        [Fact]
        public void Resolve_ConfiguredMissingPath_FailsWithoutPathFallback()
        {
            var pathExe = TouchExe(Path.Combine(_root, "path", "ffmpeg.exe"));
            var missing = Path.Combine(_root, "configured", "missing-ffmpeg.exe");

            var result = FfmpegBinaryResolver.Resolve(
                configuredPath: missing,
                pathEnvironment: Path.GetDirectoryName(pathExe));

            Assert.False(result.Success);
            Assert.Null(result.Path);
            Assert.Equal(FfmpegBinaryResolutionError.ConfiguredPathMissing, result.ErrorCode);
            Assert.Contains(missing, result.Message);
        }

        [Fact]
        public void Resolve_PathLookup_FindsFfmpegExe()
        {
            var pathExe = TouchExe(Path.Combine(_root, "path with spaces", "ffmpeg.exe"));

            var result = FfmpegBinaryResolver.Resolve(
                configuredPath: null,
                pathEnvironment: Path.GetDirectoryName(pathExe));

            Assert.True(result.Success);
            Assert.Equal(pathExe, result.Path);
            Assert.Equal(FfmpegBinaryResolutionSource.PathLookup, result.Source);
        }

        [Fact]
        public void Resolve_MissingEverywhere_ReturnsStructuredFailure()
        {
            var result = FfmpegBinaryResolver.Resolve(
                configuredPath: null,
                pathEnvironment: Path.Combine(_root, "empty"));

            Assert.False(result.Success);
            Assert.Null(result.Path);
            Assert.Equal(FfmpegBinaryResolutionError.NotFound, result.ErrorCode);
            Assert.Contains("ffmpeg.exe was not found", result.Message);
            Assert.Contains("bundled ffmpeg.exe", result.Message);
        }

        [Fact]
        public void GetInstalledFfmpegPath_UsesManagedPluginAssemblyDirectory()
        {
            var pluginPath = Path.Combine(_root, "installed", "Rook.rhp");
            Directory.CreateDirectory(Path.GetDirectoryName(pluginPath)!);
            File.WriteAllText(pluginPath, "fake plugin");

            var result = FfmpegBundledBinaryLocator.GetInstalledFfmpegPath(pluginPath);

            Assert.Equal(
                Path.Combine(Path.GetDirectoryName(pluginPath)!, "ffmpeg", "ffmpeg.exe"),
                result);
        }

        [Fact]
        public void GetInstalledFfmpegPath_MissingAssemblyLocation_ReturnsNull()
        {
            Assert.Null(FfmpegBundledBinaryLocator.GetInstalledFfmpegPath(null));
            Assert.Null(FfmpegBundledBinaryLocator.GetInstalledFfmpegPath(string.Empty));
        }

        private static string TouchExe(string path)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "fake exe");
            return Path.GetFullPath(path);
        }
    }
}
