using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video.Extraction
{
    internal interface IProcessRunner
    {
        Task<ProcessRunResult> RunAsync(
            ProcessStartInfo startInfo,
            TimeSpan timeout,
            CancellationToken cancellationToken);
    }

    internal sealed class DefaultProcessRunner : IProcessRunner
    {
        public Task<ProcessRunResult> RunAsync(
            ProcessStartInfo startInfo,
            TimeSpan timeout,
            CancellationToken cancellationToken)
        {
            return Task.Run(() =>
            {
                var stopwatch = Stopwatch.StartNew();
                using var process = new Process { StartInfo = startInfo };
                var stderr = new StringBuilder();
                process.ErrorDataReceived += (_, e) =>
                {
                    if (e.Data != null)
                        stderr.AppendLine(e.Data);
                };

                if (!process.Start())
                    throw new InvalidOperationException("ffmpeg process did not start.");

                process.BeginErrorReadLine();

                var timeoutMs = timeout <= TimeSpan.Zero
                    ? 30000
                    : (int)Math.Min(timeout.TotalMilliseconds, int.MaxValue);

                while (!process.WaitForExit(100))
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    if (stopwatch.ElapsedMilliseconds > timeoutMs)
                    {
                        TryKill(process);
                        stopwatch.Stop();
                        return new ProcessRunResult(null, stderr.ToString().TrimEnd(), timedOut: true, stopwatch.Elapsed);
                    }
                }

                process.WaitForExit();
                stopwatch.Stop();
                return new ProcessRunResult(process.ExitCode, stderr.ToString().TrimEnd(), timedOut: false, stopwatch.Elapsed);
            }, cancellationToken);
        }

        private static void TryKill(Process process)
        {
            try
            {
                if (!process.HasExited)
                    process.Kill();
            }
            catch
            {
                // Best effort cleanup in a spike runner; result still reports timeout.
            }
        }
    }

    internal sealed class FfmpegPosterFrameExtractor
    {
        private const string SeekTime = "00:00:00.100";
        private readonly IProcessRunner _runner;

        public FfmpegPosterFrameExtractor()
            : this(new DefaultProcessRunner())
        {
        }

        internal FfmpegPosterFrameExtractor(IProcessRunner runner)
        {
            _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        }

        public async Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
            string ffmpegPath,
            string inputPath,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken)
        {
            var commandLine = BuildCommandLine(ffmpegPath, inputPath, outputPath);

            if (!File.Exists(inputPath))
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    exitCode: null,
                    stderr: string.Empty,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegPosterExtractionError.InputMissing,
                    $"Input MP4 does not exist: {inputPath}");
            }

            if (!File.Exists(ffmpegPath))
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    exitCode: null,
                    stderr: string.Empty,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegPosterExtractionError.BinaryMissing,
                    $"ffmpeg.exe does not exist: {ffmpegPath}");
            }

            Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
            if (File.Exists(outputPath))
                File.Delete(outputPath);

            var startInfo = new ProcessStartInfo
            {
                FileName = ffmpegPath,
                Arguments = BuildArguments(inputPath, outputPath),
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
                throw;
            }
            catch (Exception ex)
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    exitCode: null,
                    stderr: ex.Message,
                    outputPath: outputPath,
                    elapsed: TimeSpan.Zero,
                    FfmpegPosterExtractionError.ProcessStartFailed,
                    "ffmpeg process could not be started.");
            }

            if (run.TimedOut)
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegPosterExtractionError.TimedOut,
                    "ffmpeg extraction timed out.");
            }

            if (run.ExitCode != 0)
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegPosterExtractionError.ProcessFailed,
                    $"ffmpeg exited with code {run.ExitCode}.");
            }

            if (!File.Exists(outputPath))
            {
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegPosterExtractionError.OutputMissing,
                    "ffmpeg exited successfully but did not create the poster image.");
            }

            try
            {
                using var image = System.Drawing.Image.FromFile(outputPath);
                if (image.Width <= 0 || image.Height <= 0)
                {
                    return FfmpegPosterExtractionResult.Failed(
                        commandLine,
                        run.ExitCode,
                        run.StandardError,
                        outputPath,
                        run.Elapsed,
                        FfmpegPosterExtractionError.InvalidOutputImage,
                        "Poster image dimensions were invalid.");
                }

                return FfmpegPosterExtractionResult.Completed(
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
                return FfmpegPosterExtractionResult.Failed(
                    commandLine,
                    run.ExitCode,
                    run.StandardError,
                    outputPath,
                    run.Elapsed,
                    FfmpegPosterExtractionError.InvalidOutputImage,
                    $"Poster image could not be read: {ex.Message}");
            }
        }

        internal static string BuildCommandLine(string ffmpegPath, string inputPath, string outputPath) =>
            $"{Quote(ffmpegPath)} {BuildArguments(inputPath, outputPath)}";

        private static string BuildArguments(string inputPath, string outputPath) =>
            $"-hide_banner -y -ss {SeekTime} -i {Quote(inputPath)} -frames:v 1 -q:v 2 {Quote(outputPath)}";

        private static string Quote(string value) =>
            "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
