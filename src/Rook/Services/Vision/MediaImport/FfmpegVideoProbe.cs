using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.MediaImport
{
    internal interface IVideoImportProbe
    {
        Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct);
    }

    internal sealed record VideoImportProbeResult(
        bool IsSuccess,
        double DurationSeconds,
        int Width,
        int Height,
        double? FrameRate,
        string? Message)
    {
        public static VideoImportProbeResult Success(
            double durationSeconds,
            int width,
            int height,
            double? frameRate) =>
            new(true, durationSeconds, width, height, frameRate, null);

        public static VideoImportProbeResult Failed(string message) =>
            new(false, 0, 0, 0, null, message);
    }

    internal sealed class FfmpegVideoProbe : IVideoImportProbe
    {
        private static readonly Regex DurationPattern = new(
            @"Duration:\s*(?<hours>\d+):(?<minutes>\d+):(?<seconds>\d+(?:\.\d+)?)",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        private static readonly Regex DimensionsPattern = new(
            @"(?<![0-9])(?<width>[1-9]\d{1,4})x(?<height>[1-9]\d{1,4})(?![0-9])",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        private static readonly Regex FrameRatePattern = new(
            @"(?<fps>\d+(?:\.\d+)?)\s*fps",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        private readonly IProcessRunner _runner;
        private readonly TimeSpan _timeout;
        private readonly Func<string?> _ffmpegPathProvider;

        public FfmpegVideoProbe()
            : this(new KillOnCancelProcessRunner(), TimeSpan.FromSeconds(15))
        {
        }

        internal FfmpegVideoProbe(IProcessRunner runner, TimeSpan timeout)
            : this(runner, timeout, FfmpegBundledBinaryLocator.GetInstalledFfmpegPath)
        {
        }

        internal FfmpegVideoProbe(
            IProcessRunner runner,
            TimeSpan timeout,
            Func<string?> ffmpegPathProvider)
        {
            _runner = runner ?? throw new ArgumentNullException(nameof(runner));
            _timeout = timeout;
            _ffmpegPathProvider = ffmpegPathProvider ?? throw new ArgumentNullException(nameof(ffmpegPathProvider));
        }

        public async Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct)
        {
            var resolution = FfmpegBinaryResolver.Resolve(bundledPath: _ffmpegPathProvider());
            var ffmpegPath = resolution.Path;
            if (!resolution.Success || string.IsNullOrWhiteSpace(ffmpegPath))
                return VideoImportProbeResult.Failed("ffmpeg.exe was not available for video probing.");
            var resolvedFfmpegPath = ffmpegPath!;

            var startInfo = new ProcessStartInfo
            {
                FileName = resolvedFfmpegPath,
                Arguments = $"-hide_banner -i {Quote(path)}",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = false,
            };

            ProcessRunResult run;
            try
            {
                run = await _runner.RunAsync(startInfo, _timeout, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch
            {
                return VideoImportProbeResult.Failed("ffmpeg video probe could not be started.");
            }

            if (run.TimedOut)
                return VideoImportProbeResult.Failed("ffmpeg video probe timed out.");

            if (!TryParseDuration(run.StandardError, out var durationSeconds) ||
                !TryParseDimensions(run.StandardError, out var width, out var height))
            {
                return VideoImportProbeResult.Failed("ffmpeg could not read video duration or dimensions.");
            }

            var frameRate = TryParseFrameRate(run.StandardError, out var fps)
                ? fps
                : (double?)null;

            return VideoImportProbeResult.Success(durationSeconds, width, height, frameRate);
        }

        private static bool TryParseDuration(string stderr, out double durationSeconds)
        {
            durationSeconds = 0;
            var match = DurationPattern.Match(stderr ?? string.Empty);
            if (!match.Success)
                return false;

            if (!int.TryParse(match.Groups["hours"].Value, NumberStyles.None, CultureInfo.InvariantCulture, out var hours) ||
                !int.TryParse(match.Groups["minutes"].Value, NumberStyles.None, CultureInfo.InvariantCulture, out var minutes) ||
                !double.TryParse(match.Groups["seconds"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds))
            {
                return false;
            }

            durationSeconds = TimeSpan.FromHours(hours).TotalSeconds +
                              TimeSpan.FromMinutes(minutes).TotalSeconds +
                              seconds;
            return durationSeconds > 0;
        }

        private static bool TryParseDimensions(string stderr, out int width, out int height)
        {
            width = 0;
            height = 0;
            var match = DimensionsPattern.Match(stderr ?? string.Empty);
            if (!match.Success)
                return false;

            return int.TryParse(match.Groups["width"].Value, NumberStyles.None, CultureInfo.InvariantCulture, out width) &&
                   int.TryParse(match.Groups["height"].Value, NumberStyles.None, CultureInfo.InvariantCulture, out height) &&
                   width > 0 &&
                   height > 0;
        }

        private static bool TryParseFrameRate(string stderr, out double fps)
        {
            fps = 0;
            var match = FrameRatePattern.Match(stderr ?? string.Empty);
            return match.Success &&
                   double.TryParse(match.Groups["fps"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out fps) &&
                   fps > 0;
        }

        private static string Quote(string value) =>
            "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    internal sealed class KillOnCancelProcessRunner : IProcessRunner
    {
        private readonly Action<Process>? _processStartedForTests;

        internal KillOnCancelProcessRunner(Action<Process>? processStartedForTests = null)
        {
            _processStartedForTests = processStartedForTests;
        }

        public Task<ProcessRunResult> RunAsync(
            ProcessStartInfo startInfo,
            TimeSpan timeout,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();

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

                _processStartedForTests?.Invoke(process);

                using var cancelRegistration = cancellationToken.Register(() => TryKill(process));

                if (startInfo.RedirectStandardError)
                    process.BeginErrorReadLine();

                var timeoutMs = timeout <= TimeSpan.Zero
                    ? 30000
                    : (int)Math.Min(timeout.TotalMilliseconds, int.MaxValue);

                while (!process.WaitForExit(100))
                {
                    if (cancellationToken.IsCancellationRequested)
                    {
                        TryKill(process);
                        cancellationToken.ThrowIfCancellationRequested();
                    }

                    if (stopwatch.ElapsedMilliseconds > timeoutMs)
                    {
                        TryKill(process);
                        stopwatch.Stop();
                        return new ProcessRunResult(null, stderr.ToString().TrimEnd(), timedOut: true, stopwatch.Elapsed);
                    }
                }

                process.WaitForExit();
                stopwatch.Stop();
                cancellationToken.ThrowIfCancellationRequested();
                return new ProcessRunResult(process.ExitCode, stderr.ToString().TrimEnd(), timedOut: false, stopwatch.Elapsed);
            });
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
            }
        }
    }
}
