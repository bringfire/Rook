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
    public sealed class FfmpegVideoFrameExtractorTests : IDisposable
    {
        private readonly string _root = Path.Combine(
            Path.GetTempPath(),
            "rook-ffmpeg-frame-extractor-" + Guid.NewGuid().ToString("N"));

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void VideoFrameSelector_FirstIsFrameIndexZero()
        {
            var selector = VideoFrameSelector.First;

            Assert.Equal(VideoFrameSelectorKind.First, selector.Kind);
            Assert.Equal(0, selector.FrameIndexValue);
        }

        [Fact]
        public void VideoFrameSelector_FrameIndexUsesZeroBasedDecodedFrameIndex()
        {
            var selector = VideoFrameSelector.FrameIndex(42);

            Assert.Equal(VideoFrameSelectorKind.FrameIndex, selector.Kind);
            Assert.Equal(42, selector.FrameIndexValue);
        }

        [Fact]
        public void VideoFrameSelector_FrameIndexRejectsNegativeIndex()
        {
            var ex = Assert.Throws<ArgumentOutOfRangeException>(
                () => VideoFrameSelector.FrameIndex(-1));

            Assert.Equal("index", ex.ParamName);
        }

        [Fact]
        public void VideoFrameSelector_LastHasNoConcreteIndex()
        {
            var selector = VideoFrameSelector.Last;

            Assert.Equal(VideoFrameSelectorKind.Last, selector.Kind);
            Assert.Null(selector.FrameIndexValue);
        }

        [Fact]
        public async Task ExtractFrameAsync_FirstBuildsFrameIndexZeroCommandAndReadsDimensions()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input file.mp4"));
            var output = Path.Combine(_root, "start frame.jpg");
            var runner = new FakeProcessRunner(startInfo =>
            {
                WriteJpeg(output, width: 64, height: 32);
                return new ProcessRunResult(0, "frame stderr", timedOut: false, TimeSpan.FromMilliseconds(11));
            });
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpegPath: ffmpeg,
                inputPath: input,
                selector: VideoFrameSelector.First,
                outputPath: output,
                timeout: TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(64, result.Width);
            Assert.Equal(32, result.Height);
            Assert.Equal(VideoFrameSelectorKind.First, result.Selector.Kind);
            Assert.Contains("-hide_banner", result.CommandLine);
            Assert.Contains("-map 0:v:0", result.CommandLine);
            Assert.Contains("select=eq(n\\,0)", result.CommandLine);
            Assert.Contains("-frames:v 1", result.CommandLine);
            Assert.Contains("\"" + input + "\"", result.CommandLine);
            Assert.Contains("\"" + output + "\"", result.CommandLine);
            Assert.Single(runner.Starts);
        }

        [Fact]
        public async Task ExtractFrameAsync_FrameIndexBuildsZeroBasedIndexCommand()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "frame-42.jpg");
            var runner = new FakeProcessRunner(startInfo =>
            {
                WriteJpeg(output, width: 10, height: 10);
                return new ProcessRunResult(0, "", timedOut: false, TimeSpan.FromMilliseconds(1));
            });
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.FrameIndex(42),
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Contains("-map 0:v:0", result.CommandLine);
            Assert.Contains("select=eq(n\\,42)", result.CommandLine);
        }

        [Fact]
        public async Task ExtractFrameAsync_LastBuildsLastFrameCommandWithoutChangingSelectorApi()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "end-frame.jpg");
            var runner = new FakeProcessRunner(startInfo =>
            {
                WriteJpeg(output, width: 20, height: 15);
                return new ProcessRunResult(0, "", timedOut: false, TimeSpan.FromMilliseconds(2));
            });
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.Last,
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(VideoFrameSelectorKind.Last, result.Selector.Kind);
            Assert.Contains("-map 0:v:0", result.CommandLine);
            Assert.Contains("reverse", result.CommandLine);
            Assert.Contains("-frames:v 1", result.CommandLine);
        }

        [Fact]
        public async Task ExtractFrameAsync_MissingFfmpegFailsBeforeProcessStart()
        {
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var runner = new FakeProcessRunner(_ => throw new InvalidOperationException("process should not start"));
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                Path.Combine(_root, "missing-ffmpeg.exe"),
                input,
                VideoFrameSelector.First,
                Path.Combine(_root, "frame.jpg"),
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegVideoFrameExtractionError.FfmpegMissing, result.ErrorCode);
            Assert.Empty(runner.Starts);
        }

        [Fact]
        public async Task ExtractFrameAsync_MissingInputFailsBeforeProcessStart()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var runner = new FakeProcessRunner(_ => throw new InvalidOperationException("process should not start"));
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                Path.Combine(_root, "missing.mp4"),
                VideoFrameSelector.First,
                Path.Combine(_root, "frame.jpg"),
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegVideoFrameExtractionError.InputMissing, result.ErrorCode);
            Assert.Empty(runner.Starts);
        }

        [Theory]
        [InlineData(22, "decode failed", FfmpegVideoFrameExtractionError.ProcessFailed)]
        [InlineData(null, "timeout", FfmpegVideoFrameExtractionError.TimedOut)]
        public async Task ExtractFrameAsync_ProcessFailuresReturnTypedResults(
            int? exitCode,
            string stderr,
            object expectedValue)
        {
            var expected = (FfmpegVideoFrameExtractionError)expectedValue;
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "frame.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(
                    exitCode,
                    stderr,
                    expected == FfmpegVideoFrameExtractionError.TimedOut,
                    TimeSpan.FromMilliseconds(3)));
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.First,
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(expected, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractFrameAsync_ZeroExitMissingOutputFailsWithoutBogusFrame()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "undecodable.mp4"));
            var output = Path.Combine(_root, "frame.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(0, "no frames decoded", timedOut: false, TimeSpan.FromMilliseconds(3)));
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.Last,
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegVideoFrameExtractionError.OutputMissing, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractFrameAsync_InvalidImageOutputFails()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "frame.jpg");
            var runner = new FakeProcessRunner(_ =>
            {
                File.WriteAllText(output, "not an image");
                return new ProcessRunResult(0, "", timedOut: false, TimeSpan.FromMilliseconds(3));
            });
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.First,
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.Equal(FfmpegVideoFrameExtractionError.InvalidOutputImage, result.ErrorCode);
        }

        [Fact]
        public async Task ExtractFrameAsync_DiagnosticsAreBounded()
        {
            var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
            var input = Touch(Path.Combine(_root, "input.mp4"));
            var output = Path.Combine(_root, "frame.jpg");
            var runner = new FakeProcessRunner(_ =>
                new ProcessRunResult(1, new string('x', 3000), timedOut: false, TimeSpan.FromMilliseconds(3)));
            var extractor = new FfmpegVideoFrameExtractor(runner);

            var result = await extractor.ExtractFrameAsync(
                ffmpeg,
                input,
                VideoFrameSelector.First,
                output,
                TimeSpan.FromSeconds(5),
                CancellationToken.None);

            Assert.False(result.Success);
            Assert.True(result.Stderr.Length <= 2048);
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
