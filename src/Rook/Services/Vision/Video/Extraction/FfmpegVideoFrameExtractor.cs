using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video.Extraction
{
    internal sealed class FfmpegVideoFrameExtractor
    {
        private readonly IProcessRunner _runner;

        public FfmpegVideoFrameExtractor()
            : this(new DefaultProcessRunner())
        {
        }

        internal FfmpegVideoFrameExtractor(IProcessRunner runner)
        {
            _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        }

        public async Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken)
        {
            var commandLine = BuildCommandLine(ffmpegPath, inputPath, selector, outputPath);

            if (!File.Exists(inputPath))
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    exitCode: null,
                    stderr: string.Empty,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegVideoFrameExtractionError.InputMissing,
                    $"Input MP4 does not exist: {inputPath}");
            }

            if (!File.Exists(ffmpegPath))
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    exitCode: null,
                    stderr: string.Empty,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegVideoFrameExtractionError.FfmpegMissing,
                    $"ffmpeg.exe does not exist: {ffmpegPath}");
            }

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            if (File.Exists(outputPath))
                File.Delete(outputPath);

            var startInfo = new ProcessStartInfo
            {
                FileName = ffmpegPath,
                Arguments = BuildArguments(inputPath, selector, outputPath),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = false,
            };

            ProcessRunResult run;
            try
            {
                run = await _runner.RunAsync(startInfo, timeout, cancellationToken)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    exitCode: null,
                    stderr: string.Empty,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegVideoFrameExtractionError.Cancelled,
                    "Frame extraction was cancelled.");
            }
            catch (Exception ex)
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    exitCode: null,
                    stderr: ex.Message,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegVideoFrameExtractionError.ProcessStartFailed,
                    "ffmpeg process could not be started.");
            }

            if (run.TimedOut)
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegVideoFrameExtractionError.TimedOut,
                    "ffmpeg frame extraction timed out.");
            }

            if (run.ExitCode != 0)
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegVideoFrameExtractionError.ProcessFailed,
                    $"ffmpeg exited with code {run.ExitCode}.");
            }

            if (!File.Exists(outputPath))
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegVideoFrameExtractionError.OutputMissing,
                    "ffmpeg exited successfully but did not create a frame image.");
            }

            try
            {
                using var image = System.Drawing.Image.FromFile(outputPath);
                if (image.Width <= 0 || image.Height <= 0)
                {
                    return FfmpegVideoFrameExtractionResult.Failed(
                        selector,
                        commandLine,
                        run.ExitCode,
                        run.StandardError,
                        outputPath,
                        run.Elapsed,
                        FfmpegVideoFrameExtractionError.InvalidOutputImage,
                        "Frame image dimensions were invalid.");
                }

                return FfmpegVideoFrameExtractionResult.Completed(
                    selector,
                    commandLine,
                    run.ExitCode.GetValueOrDefault(),
                    run.StandardError,
                    outputPath,
                    image.Width,
                    image.Height,
                    run.Elapsed);
            }
            catch (Exception ex)
            {
                return FfmpegVideoFrameExtractionResult.Failed(
                    selector,
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegVideoFrameExtractionError.InvalidOutputImage,
                    $"Frame image could not be read: {ex.Message}");
            }
        }

        internal static string BuildCommandLine(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath) =>
            $"{Quote(ffmpegPath)} {BuildArguments(inputPath, selector, outputPath)}";

        private static string BuildArguments(
            string inputPath,
            VideoFrameSelector selector,
            string outputPath)
        {
            var filter = BuildFilter(selector);
            return $"-hide_banner -y -i {Quote(inputPath)} -map 0:v:0 -an -vf \"{filter}\" -vsync 0 -frames:v 1 -q:v 2 {Quote(outputPath)}";
        }

        private static string BuildFilter(VideoFrameSelector selector)
        {
            var normalized = selector.NormalizeFirst();
            if (normalized.Kind == VideoFrameSelectorKind.Last)
                return "reverse,select=eq(n\\,0)";

            if (normalized.FrameIndexValue is long index)
                return $"select=eq(n\\,{index})";

            throw new InvalidOperationException($"Unsupported video frame selector: {selector.Kind}.");
        }

        private static string Quote(string value) =>
            "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
