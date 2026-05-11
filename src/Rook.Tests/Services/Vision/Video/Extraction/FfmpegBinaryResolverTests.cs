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
        }

        private static string TouchExe(string path)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "fake exe");
            return Path.GetFullPath(path);
        }
    }
}
