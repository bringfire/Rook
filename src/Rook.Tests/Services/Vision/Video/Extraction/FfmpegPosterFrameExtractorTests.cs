using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public class FfmpegPosterFrameExtractorTests : IDisposable
    {
        private readonly string _root;

        public FfmpegPosterFrameExtractorTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-ffmpeg-extractor-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task ExtractPosterAsync_BuildsExpectedCommandAndReadsDimensions()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input file.mp4"));
            var output = Path.Combine(_root, "poster file.jpg");
            var runner = new FakeProcessRunner(startInfo =>
            {
                WriteJpeg(output, width: 64, height: 32);
                return new ProcessRunResult(0, "ffmpeg stderr", timedOut: false, TimeSpan.FromMilliseconds(123));
            });
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(64, result.Width);
            Assert.Equal(32, result.Height);
            Assert.Contains("-hide_banner", result.CommandLine);
            Assert.Contains("-ss 00:00:00.100", result.CommandLine);
            Assert.Contains("-frames:v 1", result.CommandLine);
            Assert.Contains("-q:v 2", result.CommandLine);
            Assert.Contains("\"" + input + "\"", result.CommandLine);
            Assert.Contains("\"" + output + "\"", result.CommandLine);
            Assert.Equal("ffmpeg stderr", result.Stderr);
            Assert.Equal(0, result.ExitCode);
            Assert.Single(runner.Starts);
        }

        [Fact]
        public async Task ExtractPosterAsync_MissingInputFailsBeforeProcessStart()
        {
            var runner = new FakeProcessRunner(_ => throw new InvalidOperationException("process should not start"));
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: Path.Combine(_root, "ffmpeg.exe"),
                inputPath: Path.Combine(_root, "missing.mp4"),
                outputPath: Path.Combine(_root, "poster.jpg"),
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegPosterExtractionError.InputMissing, result.ErrorCode);
            Assert.Empty(runner.Starts);
        }

        [Fact]
        public async Task ExtractPosterAsync_ProcessStartExceptionFailsStructurally()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "poster.jpg");
            var runner = new FakeProcessRunner(_ =>
                throw new InvalidOperationException("not a valid executable"));
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Null(result.ExitCode);
            Assert.Equal(FfmpegPosterExtractionError.ProcessStartFailed, result.ErrorCode);
            Assert.Contains("not a valid executable", result.Stderr);
            Assert.Single(runner.Starts);
        }

        [Fact]
        public async Task ExtractPosterAsync_NonzeroExitFailsWithStderr()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "poster.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(22, "decode failed", timedOut: false, TimeSpan.FromMilliseconds(7)));
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(22, result.ExitCode);
            Assert.Equal("decode failed", result.Stderr);
            Assert.Equal(FfmpegPosterExtractionError.ProcessFailed, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractPosterAsync_TimeoutFails()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "poster.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(null, "timeout", timedOut: true, TimeSpan.FromSeconds(5)));
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Null(result.ExitCode);
            Assert.Equal(FfmpegPosterExtractionError.TimedOut, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractPosterAsync_ZeroExitMissingOutputFails()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "poster.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(0, "", timedOut: false, TimeSpan.FromMilliseconds(3)));
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegPosterExtractionError.OutputMissing, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractPosterAsync_InvalidImageOutputFails()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "poster.jpg");
            var runner = new FakeProcessRunner(_ =>
            {
                File.WriteAllText(output, "not an image");
                return new ProcessRunResult(0, "", timedOut: false, TimeSpan.FromMilliseconds(3));
            });
            var extractor = new FfmpegPosterFrameExtractor(runner);

            var result = await extractor.ExtractPosterAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegPosterExtractionError.InvalidOutputImage, result.ErrorCode);
        }

        private static string Touch(string path)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, new byte[] { 0, 1, 2, 3 });
            return path;
        }

        private static void WriteJpeg(string path, int width, int height)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            using var bitmap = new Bitmap(width, height);
            bitmap.Save(path, ImageFormat.Jpeg);
        }

        private sealed class FakeProcessRunner : IProcessRunner
        {
            private readonly Func<ProcessStartInfo, ProcessRunResult> _handler;

            public FakeProcessRunner(Func<ProcessStartInfo, ProcessRunResult> handler)
            {
                _handler = handler;
            }

            public List<ProcessStartInfo> Starts { get; } = new List<ProcessStartInfo>();

            public Task<ProcessRunResult> RunAsync(
                ProcessStartInfo startInfo,
                TimeSpan timeout,
                CancellationToken cancellationToken)
            {
                Starts.Add(startInfo);
                return Task.FromResult(_handler(startInfo));
            }
        }
    }
}
