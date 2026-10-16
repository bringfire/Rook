using System;
using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoSourceRendererTests
    {
        [Theory]
        [InlineData(SourceFramingMode.Fit)]
        [InlineData(SourceFramingMode.Fill)]
        public async Task Renderer_ActualPixelsMatchGeometryAndMatte(SourceFramingMode mode)
        {
            using var phase = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("rgb-1166x912.png")), phase.Buffers);
            var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
            var geometry = VideoFramingGeometry.Create(info, "1080p", "16:9", mode, "start_frame").Layout!;
            var result = await new FfmpegVideoSourceRenderer(bundledPath: () => Binary).RenderAsync(original, info,
                new(mode, info, geometry, VideoFramingRendererProfile.Sha256), phase, CancellationToken.None);
            Assert.Null(result.Error);
            using var rendered = result.Source!;
            using var stream = rendered.Bytes.OpenRead();
            using var image = new Bitmap(stream);
            Assert.Equal((1920, 1080), (image.Width, image.Height));
            Assert.True(rendered.Bytes.Length <= 8_000_000);
            if (mode == SourceFramingMode.Fit)
            {
                Pixel(image, 0, 540, Color.Black); Pixel(image, 960, 10, Color.FromArgb(240, 20, 20));
                Pixel(image, 960, 1070, Color.FromArgb(20, 240, 20)); Pixel(image, 280, 540, Color.FromArgb(20, 20, 240));
                Pixel(image, 1640, 540, Color.FromArgb(240, 220, 20));
            }
            else { Pixel(image, 960, 10, Color.FromArgb(180, 180, 180)); Pixel(image, 960, 540, Color.FromArgb(100, 20, 180)); }
        }
        [Theory]
        [InlineData("alpha.png")]
        [InlineData("alpha.webp")]
        public async Task Renderer_AlphaIsCompositedOntoOpaqueBlack(string fixture)
        {
            using var phase = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture(fixture)), phase.Buffers);
            var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
            var layout = VideoFramingGeometry.Create(info, "1080p", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
            var result = await new FfmpegVideoSourceRenderer(bundledPath: () => Binary).RenderAsync(original, info,
                new(SourceFramingMode.Fit, info, layout, VideoFramingRendererProfile.Sha256), phase, CancellationToken.None);
            Assert.Null(result.Error);
            using var prepared = result.Source!; using var stream = prepared.Bytes.OpenRead(); using var image = new Bitmap(stream);
            Pixel(image, 300, 540, Color.Black); Pixel(image, 1100, 540, Color.FromArgb(120, 20, 10), 2);
        }
        [Fact]
        public async Task Renderer_PngThenJpegFirstWithinBound_WithoutReadingOversizedOutput()
        {
            using var phase = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), phase.Buffers);
            var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
            var layout = VideoFramingGeometry.Create(info, "720p", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
            var runner = new OutputWriter(layout);
            var result = await new FfmpegVideoSourceRenderer(runner, () => Binary).RenderAsync(original, info,
                new(SourceFramingMode.Fit, info, layout, VideoFramingRendererProfile.Sha256), phase, CancellationToken.None);
            Assert.Null(result.Error); using var prepared = result.Source!;
            Assert.Equal(new[] { "png", "mjpeg:2", "mjpeg:3" }, runner.Attempts);
            Assert.Equal(3, prepared.Recipe.Quantizer);
            Assert.True(phase.Buffers.PeakReservedBytes < 1_000_000, "Oversized output must be statted, not read into a payload array.");
            Assert.All(runner.Directories, p => Assert.False(Directory.Exists(p)));
        }
        [Fact]
        public async Task Renderer_ProfileMismatchAndCancellationPublishNothing()
        {
            using var phase = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), phase.Buffers);
            var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
            var layout = VideoFramingGeometry.Create(info, "720p", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
            var recipe = new VideoFramingRecipe(SourceFramingMode.Fit, info, layout, VideoFramingRendererProfile.Sha256);
            var runner = new OutputWriter(layout);
            var result = await new FfmpegVideoSourceRenderer(runner, () => VideoStillImageInspectorTests.Fixture("matching.png")).RenderAsync(original, info, recipe, phase, CancellationToken.None);
            Assert.Null(result.Source); Assert.NotNull(result.Error); Assert.Empty(runner.Attempts);
            using var stop = new CancellationTokenSource(); stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new FfmpegVideoSourceRenderer(runner, () => Binary).RenderAsync(original, info, recipe, phase, stop.Token));
        }
        private static void Pixel(Bitmap image, int x, int y, Color expected, int tolerance = 0)
        { var actual = image.GetPixel(x, y); Assert.InRange(Math.Abs(actual.R - expected.R), 0, tolerance); Assert.InRange(Math.Abs(actual.G - expected.G), 0, tolerance); Assert.InRange(Math.Abs(actual.B - expected.B), 0, tolerance); Assert.Equal(255, actual.A); }
        private sealed class OutputWriter(VideoFramingLayout layout) : IFramingProcessRunner
        {
            public List<string> Attempts { get; } = new();
            public List<string> Directories { get; } = new();
            public Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct)
            {
                var args = request.Arguments.ToList(); string codec = args[args.IndexOf("-c:v") + 1];
                var q = args.IndexOf("-q:v"); Attempts.Add(codec + (q >= 0 ? ":" + args[q + 1] : "")); Directories.Add(request.WorkingDirectory);
                if (Attempts.Count < 3) { using var output = File.Create(request.OutputPath); output.SetLength(8_000_001); }
                else { using var image = new Bitmap(layout.CanvasWidth, layout.CanvasHeight); image.Save(request.OutputPath, ImageFormat.Jpeg); }
                return Task.FromResult(new FramingProcessResult(true, null, 100, true, "", 0, null));
            }
        }
        [Fact]
        public async Task Renderer_EncodingFailureAndDeadlineCleanup()
        {
            using var phase = await new VideoPreparationResources().AcquireAsync(CancellationToken.None);
            using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), phase.Buffers);
            var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
            var layout = VideoFramingGeometry.Create(info, "720p", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
            var recipe = new VideoFramingRecipe(SourceFramingMode.Fit, info, layout, VideoFramingRendererProfile.Sha256);
            string? owned = null;
            var failing = new DelegateRunner((request, _) => {
                owned = request.WorkingDirectory; File.WriteAllText(request.OutputPath, "partial");
                return Task.FromResult(new FramingProcessResult(false, "renderer_failed", 0, true, "Unknown encoder (internal diagnostic)", 1, null));
            });
            var failure = await new FfmpegVideoSourceRenderer(failing, () => Binary).RenderAsync(original, info, recipe, phase, CancellationToken.None);
            Assert.Null(failure.Source); Assert.NotNull(failure.Error); Assert.DoesNotContain("encoder", failure.Error!.Message); Assert.False(Directory.Exists(owned));
            using var stop = new CancellationTokenSource();
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var waiting = new DelegateRunner(async (request, ct) => {
                owned = request.WorkingDirectory; File.WriteAllText(request.OutputPath, "partial"); entered.SetResult(true);
                await Task.Delay(Timeout.Infinite, ct); throw new InvalidOperationException();
            });
            var pending = new FfmpegVideoSourceRenderer(waiting, () => Binary).RenderAsync(original, info, recipe, phase, stop.Token);
            await entered.Task; stop.Cancel(); await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending);
            Assert.False(Directory.Exists(owned)); Assert.Equal(original.Length, phase.Buffers.ReservedBytes);
        }
        private sealed class DelegateRunner(Func<FramingProcessRequest, CancellationToken, Task<FramingProcessResult>> run) : IFramingProcessRunner
        { public Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct) => run(request, ct); }
        internal static string Binary => Path.GetFullPath(Path.Combine(Path.GetDirectoryName(VideoStillImageInspectorTests.Fixture("matching.png"))!, "..", "..", "ffmpeg.exe"));
        [Fact]
        public async Task BundledProfile_DecodesAndEncodesStillPng()
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-framing-profile-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string output = Path.Combine(root, "output.png");
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                var result = await new WindowsFramingProcessRunner().RunAsync(new FramingProcessRequest(Binary,
                    new[] { "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1", "-i", VideoStillImageInspectorTests.Fixture("matching.png"), "-frames:v", "1", "-threads", "1", "-c:v", "png", "-y", output }, root, output), deadline.Token);
                Assert.True(result.Success, result.Diagnostics);
                Assert.True(File.Exists(output));
            }
            finally { Directory.Delete(root, true); }
        }
    }
}
