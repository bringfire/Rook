using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.MediaImport;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public sealed class VideoMediaImporterTests : IDisposable
    {
        private readonly string _root;
        private readonly string _artifactRoot;
        private readonly ArtifactStore _store;

        public VideoMediaImporterTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-video-import-tests", Guid.NewGuid().ToString("N"));
            _artifactRoot = Path.Combine(_root, "artifacts");
            Directory.CreateDirectory(_root);
            _store = new ArtifactStore(_artifactRoot);
        }

        [Fact]
        public async Task ImportMov_PublishesVideoPosterStartAndEnd()
        {
            var source = Path.Combine(_root, "clip.mov");
            File.WriteAllText(source, "video bytes");
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(VideoImportProbeResult.Success(2.5, 1920, 1080, 30)),
                new FakeSidecarExtractor(_root));

            var result = await importer.Import(source, CancellationToken.None);

            Assert.True(result.IsSuccess, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal(MediaImportConstants.ImportedVideoKind, artifact.Kind);
            Assert.Contains(artifact.Files, file => file.Role == VideoMediaRoles.Video && file.Path == "video.mov");
            Assert.Contains(artifact.Files, file => file.Role == VideoMediaRoles.Poster && file.Path == "poster.jpg");
            Assert.Contains(artifact.Files, file => file.Role == VideoMediaRoles.StartFrame && file.Path == "start_frame.jpg");
            Assert.Contains(artifact.Files, file => file.Role == VideoMediaRoles.EndFrame && file.Path == "end_frame.jpg");
            Assert.Equal("clip.mov", ReadString(artifact.Metadata, "original_filename"));
            Assert.Equal(2.5, ReadDouble(artifact.Metadata, "duration_seconds"));
            Assert.Equal(1920, ReadInt(artifact.Metadata, "width"));
            Assert.Equal(1080, ReadInt(artifact.Metadata, "height"));
            var sidecars = artifact.Metadata["sidecars"]!.AsObject();
            Assert.Equal("ok", sidecars["poster"]!.GetValue<string>());
            Assert.Equal("ok", sidecars["start_frame"]!.GetValue<string>());
            Assert.Equal("ok", sidecars["end_frame"]!.GetValue<string>());
        }

        [Fact]
        public async Task ImportMp4_WhenEndFrameFails_PublishesNothing()
        {
            var source = Path.Combine(_root, "clip.mp4");
            File.WriteAllText(source, "video bytes");
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(VideoImportProbeResult.Success(2.5, 1920, 1080, 30)),
                new FakeSidecarExtractor(_root, failEndFrame: true));

            var result = await importer.Import(source, CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.SidecarExtractionFailed, result.FailureCode);
            Assert.Empty(_store.List());
        }

        [Fact]
        public async Task ImportAvi_ReturnsUnsupportedMediaType()
        {
            var source = Path.Combine(_root, "clip.avi");
            File.WriteAllText(source, "video bytes");
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(VideoImportProbeResult.Success(2.5, 1920, 1080, 30)),
                new FakeSidecarExtractor(_root));

            var result = await importer.Import(source, CancellationToken.None);

            Assert.False(result.IsSuccess);
            Assert.Equal(MediaImportFailureCode.UnsupportedMediaType, result.FailureCode);
        }

        [Fact]
        public async Task DefaultSidecarExtractor_WhenStartFrameReturnsCancelled_ThrowsOperationCanceled()
        {
            var source = Path.Combine(_root, "clip.mp4");
            File.WriteAllText(source, "video bytes");
            var ffmpeg = Path.Combine(_root, "ffmpeg.exe");
            File.WriteAllText(ffmpeg, "fake");
            var sidecarRoot = Path.Combine(_root, "sidecar-root");
            var extractor = new DefaultVideoImportSidecarExtractor(
                () => ffmpeg,
                (_, _, outputPath, _, _) => Task.FromResult(
                    FfmpegPosterExtractionResult.Completed(
                        "ffmpeg poster",
                        0,
                        string.Empty,
                        outputPath,
                        1,
                        1,
                        TimeSpan.Zero)),
                (_, _, selector, outputPath, _, _) => Task.FromResult(
                    FfmpegVideoFrameExtractionResult.Failed(
                        selector,
                        "ffmpeg frame",
                        null,
                        string.Empty,
                        outputPath,
                        TimeSpan.Zero,
                        FfmpegVideoFrameExtractionError.Cancelled,
                        "Frame extraction was cancelled.")),
                sidecarRoot);

            await Assert.ThrowsAsync<OperationCanceledException>(
                () => extractor.ExtractAsync(
                    source,
                    VideoImportProbeResult.Success(2.5, 1920, 1080, 30),
                    CancellationToken.None));
            Assert.False(Directory.Exists(sidecarRoot) && Directory.GetDirectories(sidecarRoot).Length > 0);
        }

        [Fact]
        public async Task ProbeProcessRunner_WhenCancelled_KillsStartedProcess()
        {
            var started = new TaskCompletionSource<int>();
            var runner = new KillOnCancelProcessRunner(processStartedForTests: process => started.SetResult(process.Id));
            using var cts = new CancellationTokenSource();
            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -Command \"Start-Sleep -Seconds 30\"",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = false,
            };

            var run = runner.RunAsync(startInfo, TimeSpan.FromSeconds(30), cts.Token);
            var processId = await started.Task;
            cts.Cancel();

            await Assert.ThrowsAsync<OperationCanceledException>(() => run);
            AssertProcessExited(processId);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(_root))
                    Directory.Delete(_root, recursive: true);
            }
            catch
            {
            }
        }

        private static string ReadString(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<string>();

        private static int ReadInt(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<int>();

        private static double ReadDouble(
            System.Collections.Generic.IReadOnlyDictionary<string, JsonNode?> metadata,
            string key) => metadata[key]!.GetValue<double>();

        private static void AssertProcessExited(int processId)
        {
            try
            {
                using var process = Process.GetProcessById(processId);
                Assert.True(process.HasExited, $"Process {processId} was still running.");
            }
            catch (ArgumentException)
            {
            }
        }
    }

    internal sealed class FakeVideoProbe : IVideoImportProbe
    {
        private readonly VideoImportProbeResult _result;

        public FakeVideoProbe(VideoImportProbeResult result)
        {
            _result = result;
        }

        public Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct)
            => Task.FromResult(_result);
    }

    internal sealed class FakeSidecarExtractor : IVideoImportSidecarExtractor
    {
        private readonly string _root;
        private readonly bool _failEndFrame;

        public FakeSidecarExtractor(string root, bool failEndFrame = false)
        {
            _root = root;
            _failEndFrame = failEndFrame;
        }

        public Task<VideoImportSidecarResult> ExtractAsync(
            string path,
            VideoImportProbeResult probe,
            CancellationToken ct)
        {
            var tempDir = Path.Combine(_root, "sidecars", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);

            var poster = Path.Combine(tempDir, "poster.jpg");
            var start = Path.Combine(tempDir, "start_frame.jpg");
            var end = Path.Combine(tempDir, "end_frame.jpg");

            File.WriteAllText(poster, "poster");
            File.WriteAllText(start, "start");

            if (_failEndFrame)
            {
                Directory.Delete(tempDir, recursive: true);
                return Task.FromResult(VideoImportSidecarResult.Failed("End frame extraction failed."));
            }

            File.WriteAllText(end, "end");
            return Task.FromResult(VideoImportSidecarResult.Success(poster, start, end, tempDir));
        }
    }
}
