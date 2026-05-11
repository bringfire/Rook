# Local MP4 Extraction Tooling Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove whether Rook can extract a poster candidate frame from a local MP4 through a replaceable external `ffmpeg.exe`, record the evidence, and recommend the production extraction path.

**Architecture:** Add an unwired managed extraction spike seam under `Rook.Services.Vision.Video.Extraction`: binary resolution, ffmpeg process invocation, and result modeling. Add unit tests with fake process runners for discovery and command behavior, plus an opt-in manual spike test driven by a PowerShell runner. The runner writes a committed findings document; no `ArtifactStore`, `VideoJobManager`, provider, installer, or binary fixture work is included.

**Tech Stack:** C# net48/net7.0 managed companion code, xUnit, `System.Diagnostics.Process`, `System.Drawing` for output dimension validation, PowerShell runner, Markdown findings.

---

## Fixture Policy

Do not commit an MP4 fixture in this slice.

The executable spike must use, in order:

1. `-InputMp4` passed to `scripts/run_video_extraction_spike.ps1`;
2. `ROOK_VIDEO_SPIKE_MP4` if set;
3. the newest local `%APPDATA%\Rook\artifacts\**\video.mp4` if present.

If none is available, the runner must stop with a clear message and make no findings commit. This keeps binary media out of the repository while still allowing the spike to test a real local generated-video artifact.

## File Structure

- Create `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`
  - Resolves explicit configured ffmpeg path or `PATH` lookup.
  - Does not know about Rook settings, installer paths, or dev-machine paths.

- Create `src/Rook/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractor.cs`
  - Builds and runs the ffmpeg poster extraction command.
  - Uses an injectable process runner for tests.
  - Validates output existence and image dimensions.

- Create `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`
  - Result records/enums shared by resolver, extractor, tests, and manual spike test.

- Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`
  - Pins explicit path, `PATH` lookup, and missing-binary behavior.

- Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractorTests.cs`
  - Pins command shape, quoting, timeout/nonzero/missing-output/invalid-dimensions behavior with fake process runner.

- Create `src/Rook.Tests/Services/Vision/Video/Extraction/VideoExtractionSpikeManualTests.cs`
  - Opt-in manual test that executes the real extractor when `ROOK_RUN_VIDEO_EXTRACTION_SPIKE=1`.
  - Writes `docs/rook_docs/video-extraction-spike-findings.md` when `ROOK_VIDEO_SPIKE_FINDINGS_PATH` is provided.

- Create `scripts/run_video_extraction_spike.ps1`
  - Discovers input MP4 and optional ffmpeg path.
  - Sets environment variables.
  - Runs the focused manual xUnit test.

- Create `docs/rook_docs/video-extraction-spike-findings.md`
  - Generated/updated by the manual spike run and committed with the spike.

---

### Task 1: Add Failing ffmpeg Discovery Tests

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`
- Create later: `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`
- Create later: `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`

- [ ] **Step 1: Create the failing resolver tests**

Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`:

```csharp
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
```

- [ ] **Step 2: Run the failing resolver tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~FfmpegBinaryResolverTests
```

Expected: FAIL because `Rook.Services.Vision.Video.Extraction` types do not exist.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegBinaryResolverTests.cs
git commit -m "test: pin ffmpeg binary discovery"
```

---

### Task 2: Implement ffmpeg Binary Resolution

**Files:**
- Create: `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`
- Create: `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`

- [ ] **Step 1: Add shared spike result models**

Create `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Video.Extraction
{
    internal enum FfmpegBinaryResolutionSource
    {
        ConfiguredPath,
        PathLookup,
    }

    internal enum FfmpegBinaryResolutionError
    {
        ConfiguredPathMissing,
        NotFound,
    }

    internal sealed class FfmpegBinaryResolution
    {
        private FfmpegBinaryResolution(
            bool success,
            string? path,
            FfmpegBinaryResolutionSource? source,
            FfmpegBinaryResolutionError? errorCode,
            string message)
        {
            Success = success;
            Path = path;
            Source = source;
            ErrorCode = errorCode;
            Message = message;
        }

        public bool Success { get; }
        public string? Path { get; }
        public FfmpegBinaryResolutionSource? Source { get; }
        public FfmpegBinaryResolutionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegBinaryResolution Found(
            string path,
            FfmpegBinaryResolutionSource source) =>
            new(
                success: true,
                path: path,
                source: source,
                errorCode: null,
                message: $"Resolved ffmpeg.exe from {source}.");

        public static FfmpegBinaryResolution Failed(
            FfmpegBinaryResolutionError errorCode,
            string message) =>
            new(
                success: false,
                path: null,
                source: null,
                errorCode: errorCode,
                message: message);
    }

    internal enum FfmpegPosterExtractionError
    {
        InputMissing,
        BinaryMissing,
        ProcessFailed,
        TimedOut,
        OutputMissing,
        InvalidOutputImage,
    }

    internal sealed class FfmpegPosterExtractionResult
    {
        private FfmpegPosterExtractionResult(
            bool success,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            int? width,
            int? height,
            TimeSpan elapsed,
            FfmpegPosterExtractionError? errorCode,
            string message)
        {
            Success = success;
            CommandLine = commandLine;
            ExitCode = exitCode;
            Stderr = stderr;
            OutputPath = outputPath;
            Width = width;
            Height = height;
            Elapsed = elapsed;
            ErrorCode = errorCode;
            Message = message;
        }

        public bool Success { get; }
        public string CommandLine { get; }
        public int? ExitCode { get; }
        public string Stderr { get; }
        public string OutputPath { get; }
        public int? Width { get; }
        public int? Height { get; }
        public TimeSpan Elapsed { get; }
        public FfmpegPosterExtractionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegPosterExtractionResult Completed(
            string commandLine,
            int exitCode,
            string stderr,
            string outputPath,
            int width,
            int height,
            TimeSpan elapsed) =>
            new(true, commandLine, exitCode, stderr, outputPath, width, height, elapsed, null, "Extracted poster candidate frame.");

        public static FfmpegPosterExtractionResult Failed(
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            TimeSpan elapsed,
            FfmpegPosterExtractionError errorCode,
            string message) =>
            new(false, commandLine, exitCode, stderr, outputPath, null, null, elapsed, errorCode, message);
    }

    internal sealed class ProcessRunResult
    {
        public ProcessRunResult(int? exitCode, string standardError, bool timedOut, TimeSpan elapsed)
        {
            ExitCode = exitCode;
            StandardError = standardError ?? string.Empty;
            TimedOut = timedOut;
            Elapsed = elapsed;
        }

        public int? ExitCode { get; }
        public string StandardError { get; }
        public bool TimedOut { get; }
        public TimeSpan Elapsed { get; }
    }
}
```

- [ ] **Step 2: Add the resolver implementation**

Create `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`:

```csharp
using System;
using System.IO;
using System.Linq;

namespace Rook.Services.Vision.Video.Extraction
{
    internal static class FfmpegBinaryResolver
    {
        private const string BinaryName = "ffmpeg.exe";

        public static FfmpegBinaryResolution Resolve(
            string? configuredPath = null,
            string? pathEnvironment = null)
        {
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
                "ffmpeg.exe was not found. Provide an explicit path or add ffmpeg.exe to PATH.");
        }

        private static string[] SplitPath(string? pathEnvironment) =>
            string.IsNullOrWhiteSpace(pathEnvironment)
                ? Array.Empty<string>()
                : pathEnvironment
                    .Split(new[] { Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries)
                    .Select(p => p.Trim().Trim('"'))
                    .Where(p => p.Length > 0)
                    .ToArray();
    }
}
```

- [ ] **Step 3: Run resolver tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~FfmpegBinaryResolverTests
```

Expected: PASS.

- [ ] **Step 4: Commit resolver implementation**

Run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\VideoExtractionSpikeModels.cs `
        src\Rook\Services\Vision\Video\Extraction\FfmpegBinaryResolver.cs
git commit -m "feat: add ffmpeg binary resolver spike"
```

---

### Task 3: Add Failing Poster Extraction Tests

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractorTests.cs`
- Create later: `src/Rook/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractor.cs`

- [ ] **Step 1: Create extraction tests with a fake runner**

Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractorTests.cs`:

```csharp
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

            public List<ProcessStartInfo> Starts { get; } = new();

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
```

- [ ] **Step 2: Run the failing extraction tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~FfmpegPosterFrameExtractorTests
```

Expected: FAIL because `FfmpegPosterFrameExtractor` and `IProcessRunner` do not exist.

- [ ] **Step 3: Commit the failing extraction tests**

Run:

```powershell
git add src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegPosterFrameExtractorTests.cs
git commit -m "test: pin ffmpeg poster extraction command"
```

---

### Task 4: Implement ffmpeg Poster Extraction

**Files:**
- Create: `src/Rook/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractor.cs`
- Modify: `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractorTests.cs`

- [ ] **Step 1: Add the process runner and extractor implementation**

Create `src/Rook/Services/Vision/Video/Extraction/FfmpegPosterFrameExtractor.cs`:

```csharp
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

                process.Start();
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

            var run = await _runner.RunAsync(startInfo, timeout, cancellationToken)
                .ConfigureAwait(false);

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
                using var image = Image.FromFile(outputPath);
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
            catch (Exception ex) when (ex is ArgumentException || ex is OutOfMemoryException || ex is IOException)
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
```

- [ ] **Step 2: Run extraction tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests|FullyQualifiedName~FfmpegPosterFrameExtractorTests"
```

Expected: PASS.

- [ ] **Step 3: Commit extractor implementation**

Run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\FfmpegPosterFrameExtractor.cs `
        src\Rook\Services\Vision\Video\Extraction\VideoExtractionSpikeModels.cs
git commit -m "feat: add ffmpeg poster extraction spike"
```

---

### Task 5: Add Manual Spike Runner And Findings Writer

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/Extraction/VideoExtractionSpikeManualTests.cs`
- Create: `scripts/run_video_extraction_spike.ps1`
- Create during execution: `docs/rook_docs/video-extraction-spike-findings.md`

- [ ] **Step 1: Add the opt-in manual spike test**

Create `src/Rook.Tests/Services/Vision/Video/Extraction/VideoExtractionSpikeManualTests.cs`:

```csharp
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public class VideoExtractionSpikeManualTests
    {
        [Fact]
        public async Task Ffmpeg_extracts_poster_from_local_mp4_when_enabled()
        {
            if (!string.Equals(Environment.GetEnvironmentVariable("ROOK_RUN_VIDEO_EXTRACTION_SPIKE"), "1", StringComparison.Ordinal))
                return;

            var input = RequiredEnv("ROOK_VIDEO_SPIKE_MP4");
            var findingsPath = RequiredEnv("ROOK_VIDEO_SPIKE_FINDINGS_PATH");
            var configuredFfmpeg = Environment.GetEnvironmentVariable("ROOK_VIDEO_SPIKE_FFMPEG");
            var outputRoot = Environment.GetEnvironmentVariable("ROOK_VIDEO_SPIKE_OUTPUT_DIR");
            if (string.IsNullOrWhiteSpace(outputRoot))
                outputRoot = Path.Combine(Path.GetTempPath(), "rook-video-extraction-spike");

            Directory.CreateDirectory(outputRoot);
            var output = Path.Combine(outputRoot, "poster-candidate.jpg");

            var resolution = FfmpegBinaryResolver.Resolve(configuredFfmpeg);
            var result = resolution.Success
                ? await new FfmpegPosterFrameExtractor().ExtractPosterAsync(
                    resolution.Path!,
                    input,
                    output,
                    TimeSpan.FromSeconds(30),
                    CancellationToken.None)
                : FfmpegPosterExtractionResult.Failed(
                    "ffmpeg discovery",
                    null,
                    resolution.Message,
                    output,
                    TimeSpan.Zero,
                    FfmpegPosterExtractionError.BinaryMissing,
                    resolution.Message);

            WriteFindings(findingsPath, input, resolution, result);

            Assert.True(resolution.Success, resolution.Message);
            Assert.True(result.Success, result.Message + Environment.NewLine + result.Stderr);
        }

        private static string RequiredEnv(string name)
        {
            var value = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidOperationException($"{name} must be set when ROOK_RUN_VIDEO_EXTRACTION_SPIKE=1.");
            return value;
        }

        private static void WriteFindings(
            string findingsPath,
            string input,
            FfmpegBinaryResolution resolution,
            FfmpegPosterExtractionResult result)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(findingsPath)!);
            var now = DateTimeOffset.Now;
            var sb = new StringBuilder();
            sb.AppendLine("# Local MP4 Extraction Spike Findings");
            sb.AppendLine();
            sb.AppendLine($"Date: {now:yyyy-MM-dd}");
            sb.AppendLine();
            sb.AppendLine("## Fixture Policy");
            sb.AppendLine();
            sb.AppendLine("No MP4 fixture or ffmpeg binary is committed. The spike used a local MP4 path supplied by the runner or discovered from the local Rook artifact store.");
            sb.AppendLine();
            sb.AppendLine("## Environment");
            sb.AppendLine();
            sb.AppendLine($"- OS: {Environment.OSVersion}");
            sb.AppendLine($"- Machine: {Environment.MachineName}");
            sb.AppendLine($"- .NET runtime: {Environment.Version}");
            sb.AppendLine();
            sb.AppendLine("## Input");
            sb.AppendLine();
            sb.AppendLine($"- Input path shape: `{Sanitize(input)}`");
            sb.AppendLine($"- Input exists: `{File.Exists(input)}`");
            if (File.Exists(input))
                sb.AppendLine($"- Input bytes: `{new FileInfo(input).Length}`");
            sb.AppendLine();
            sb.AppendLine("## ffmpeg Discovery");
            sb.AppendLine();
            sb.AppendLine($"- Success: `{resolution.Success}`");
            sb.AppendLine($"- Source: `{resolution.Source}`");
            sb.AppendLine($"- Error code: `{resolution.ErrorCode}`");
            sb.AppendLine($"- Resolved path shape: `{Sanitize(resolution.Path)}`");
            sb.AppendLine($"- Message: {EscapeMarkdown(resolution.Message)}");
            sb.AppendLine();
            sb.AppendLine("## Extraction Result");
            sb.AppendLine();
            sb.AppendLine($"- Success: `{result.Success}`");
            sb.AppendLine($"- Command/API shape: `{SanitizeCommand(result.CommandLine)}`");
            sb.AppendLine($"- Exit code: `{result.ExitCode}`");
            sb.AppendLine($"- Error code: `{result.ErrorCode}`");
            sb.AppendLine($"- Output path shape: `{Sanitize(result.OutputPath)}`");
            sb.AppendLine($"- Output exists: `{File.Exists(result.OutputPath)}`");
            sb.AppendLine($"- Output dimensions: `{result.Width}x{result.Height}`");
            sb.AppendLine($"- Elapsed ms: `{result.Elapsed.TotalMilliseconds:0}`");
            sb.AppendLine($"- Diagnostic summary: {EscapeMarkdown(Trim(result.Stderr, 600))}");
            sb.AppendLine();
            sb.AppendLine("## WMF Feasibility");
            sb.AppendLine();
            sb.AppendLine("WMF was not implemented as code in this spike. The feasibility review remains documentation-level: using WMF from the managed companion would require new interop or package work and careful COM/threading design, while the ffmpeg external-process path keeps decoding out of the Rhino UI process and is directly testable from managed code.");
            sb.AppendLine();
            sb.AppendLine("## Failure Observations");
            sb.AppendLine();
            sb.AppendLine("- Missing ffmpeg is represented as a structured binary-discovery failure.");
            sb.AppendLine("- Missing input fails before process start.");
            sb.AppendLine("- Nonzero exit, timeout, missing output, and invalid image output are covered by unit tests.");
            sb.AppendLine();
            sb.AppendLine("## Recommendation");
            sb.AppendLine();
            sb.AppendLine(result.Success
                ? "Use ffmpeg as the production extraction path candidate, invoked as a replaceable external process. Keep packaging, LGPL-build selection, notices, and source-compliance work in a later slice."
                : "Do not proceed to production extraction until the local ffmpeg failure above is resolved and rerun.");
            File.WriteAllText(findingsPath, sb.ToString(), Encoding.UTF8);
        }

        private static string Sanitize(string? path)
        {
            if (string.IsNullOrWhiteSpace(path))
                return "";

            var file = Path.GetFileName(path);
            var parent = Path.GetFileName(Path.GetDirectoryName(path) ?? "");
            return string.IsNullOrWhiteSpace(parent)
                ? file
                : Path.Combine("...", parent, file);
        }

        private static string SanitizeCommand(string command)
        {
            var sanitized = command;
            var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrWhiteSpace(userProfile))
                sanitized = sanitized.Replace(userProfile, "<USERPROFILE>");

            var userName = Environment.UserName;
            if (!string.IsNullOrWhiteSpace(userName))
                sanitized = sanitized.Replace(userName, "<USER>");

            return sanitized;
        }

        private static string Trim(string value, int max) =>
            string.IsNullOrEmpty(value) || value.Length <= max
                ? value
                : value.Substring(0, max) + "...";

        private static string EscapeMarkdown(string value) =>
            string.IsNullOrEmpty(value)
                ? ""
                : value.Replace("|", "\\|").Replace("\r", " ").Replace("\n", " ");
    }
}
```

- [ ] **Step 2: Add the PowerShell runner**

Create `scripts/run_video_extraction_spike.ps1`:

```powershell
param(
    [string]$InputMp4,
    [string]$FfmpegPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$findingsPath = Join-Path $repoRoot "docs\rook_docs\video-extraction-spike-findings.md"
$outputDir = Join-Path $repoRoot ".scratch\video-extraction-spike"

function Find-LatestRookVideo {
    $artifactRoot = Join-Path $env:APPDATA "Rook\artifacts"
    if (-not (Test-Path $artifactRoot)) {
        return $null
    }

    Get-ChildItem -Path $artifactRoot -Recurse -Filter "video.mp4" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 |
        ForEach-Object { $_.FullName }
}

$resolvedInput = $InputMp4
if ([string]::IsNullOrWhiteSpace($resolvedInput)) {
    $resolvedInput = $env:ROOK_VIDEO_SPIKE_MP4
}
if ([string]::IsNullOrWhiteSpace($resolvedInput)) {
    $resolvedInput = Find-LatestRookVideo
}

if ([string]::IsNullOrWhiteSpace($resolvedInput) -or -not (Test-Path $resolvedInput)) {
    throw "No local MP4 found. Pass -InputMp4, set ROOK_VIDEO_SPIKE_MP4, or generate a RookVision video artifact first."
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$env:ROOK_RUN_VIDEO_EXTRACTION_SPIKE = "1"
$env:ROOK_VIDEO_SPIKE_MP4 = (Resolve-Path $resolvedInput).Path
$env:ROOK_VIDEO_SPIKE_FINDINGS_PATH = $findingsPath
$env:ROOK_VIDEO_SPIKE_OUTPUT_DIR = $outputDir
if (-not [string]::IsNullOrWhiteSpace($FfmpegPath)) {
    $env:ROOK_VIDEO_SPIKE_FFMPEG = (Resolve-Path $FfmpegPath).Path
} else {
    Remove-Item Env:\ROOK_VIDEO_SPIKE_FFMPEG -ErrorAction SilentlyContinue
}

Write-Host "Input MP4: $($env:ROOK_VIDEO_SPIKE_MP4)"
Write-Host "Findings:  $findingsPath"
Write-Host "Output:    $outputDir"

dotnet test "$repoRoot\src\Rook.Tests\Rook.Tests.csproj" --no-restore --filter "FullyQualifiedName~VideoExtractionSpikeManualTests"
if ($LASTEXITCODE -ne 0) {
    throw "Video extraction spike failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $findingsPath)) {
    throw "Expected findings document was not written: $findingsPath"
}

Write-Host "Spike findings written to $findingsPath"
```

- [ ] **Step 3: Run manual test without opt-in and verify it is inert**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VideoExtractionSpikeManualTests
```

Expected: PASS without requiring ffmpeg or an MP4 because `ROOK_RUN_VIDEO_EXTRACTION_SPIKE` is unset.

- [ ] **Step 4: Commit manual runner**

Run:

```powershell
git add src\Rook.Tests\Services\Vision\Video\Extraction\VideoExtractionSpikeManualTests.cs `
        scripts\run_video_extraction_spike.ps1
git commit -m "test: add local video extraction spike runner"
```

---

### Task 6: Execute Spike And Commit Findings

**Files:**
- Create/update: `docs/rook_docs/video-extraction-spike-findings.md`
- Read: `.scratch/video-extraction-spike/poster-candidate.jpg` (untracked scratch output)

- [ ] **Step 1: Locate ffmpeg and local MP4**

Run:

```powershell
Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object Source, Version
Get-ChildItem "$env:APPDATA\Rook\artifacts" -Recurse -Filter video.mp4 -File -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 FullName, Length, LastWriteTime
```

Expected:

- `ffmpeg` should be found on `PATH`, or you must pass `-FfmpegPath`.
- At least one local `video.mp4` should exist, or you must pass `-InputMp4`.
- Do not commit the MP4.

- [ ] **Step 2: Run the executable spike**

If a local artifact exists and ffmpeg is on `PATH`, run:

```powershell
.\scripts\run_video_extraction_spike.ps1
```

If using explicit paths, run:

```powershell
.\scripts\run_video_extraction_spike.ps1 -InputMp4 "C:\path\to\input.mp4" -FfmpegPath "C:\path\to\ffmpeg.exe"
```

Expected:

- Focused manual test passes.
- `.scratch\video-extraction-spike\poster-candidate.jpg` exists.
- `docs\rook_docs\video-extraction-spike-findings.md` is written.

- [ ] **Step 3: Inspect findings**

Run:

```powershell
Get-Content docs\rook_docs\video-extraction-spike-findings.md
```

Expected:

- Contains fixture policy.
- Contains environment.
- Contains sanitized input path shape, not full private path.
- Contains command/API shape.
- Contains exit code, dimensions, elapsed time, failure observations, and recommendation.
- Does not contain API keys, provider URLs, full `%USERPROFILE%` paths, or raw video bytes.

- [ ] **Step 4: Commit findings**

Run:

```powershell
git add docs\rook_docs\video-extraction-spike-findings.md
git commit -m "docs: record local video extraction spike findings"
```

---

### Task 7: Final Verification And Reviewer Handoff

**Files:**
- Read: all files changed by Tasks 1-6

- [ ] **Step 1: Run focused extraction tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests|FullyQualifiedName~FfmpegPosterFrameExtractorTests|FullyQualifiedName~VideoExtractionSpikeManualTests"
```

Expected: PASS. The manual test must remain inert unless `ROOK_RUN_VIDEO_EXTRACTION_SPIKE=1`.

- [ ] **Step 2: Run video smoke slice**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VideoArtifactMaterializerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoOpHandlerTests"
```

Expected: PASS.

- [ ] **Step 3: Verify scope boundaries**

Run:

```powershell
git diff origin/main --check
git show --check --format=short HEAD
git diff --name-only origin/main...HEAD
rg -n "ArtifactStore|VideoJobManager|BlobInput|RookSetup|installer" src\Rook\Services\Vision\Video\Extraction src\Rook.Tests\Services\Vision\Video\Extraction scripts\run_video_extraction_spike.ps1 docs\rook_docs\video-extraction-spike-findings.md
git diff --name-only origin/main...HEAD | rg "\.mp4$|\.exe$|installer|RookSetup\.iss"
```

Expected:

- Whitespace checks pass.
- Changed files are limited to extraction spike code/tests, runner script, plan/spec/findings docs.
- `ArtifactStore`, `VideoJobManager`, `BlobInput`, installer, and `RookSetup` scan returns no production integration hits. Mentions in findings/spec/plan are acceptable only as out-of-scope statements.
- No `.mp4` or `.exe` files are tracked.

- [ ] **Step 4: Produce reviewer prompt**

Use this reviewer prompt:

```text
Please review the Local MP4 Extraction Tooling Spike against docs/superpowers/specs/2026-05-11-local-mp4-extraction-tooling-spike-design.md.

Focus areas:
- Local MP4 extraction must remain the default sidecar producer.
- ffmpeg must be invoked only as a replaceable external process.
- Binary discovery must cover configured path, PATH lookup, and missing-binary failure without hardcoded dev-machine paths.
- The spike must not commit ffmpeg binaries or MP4 fixtures.
- The spike must not modify installer packaging.
- The spike must not integrate with ArtifactStore, VideoJobManager, provider calls, Gallery, or GH NLE.
- The committed findings document must preserve the evidence needed to choose ffmpeg vs WMF: input used, environment, final command/API shape, measurements, failure observations, and recommendation.
- The manual spike test should be inert in normal test runs unless explicitly enabled.

Please report critical, important, and minor issues, and give a readiness verdict for moving to the sidecar publication semantics slice.
```

- [ ] **Step 5: Confirm clean worktree**

Run:

```powershell
git status --short --branch
```

Expected: clean except branch ahead of `origin/main` by the spike commits.

---

## Self-Review

Spec coverage:

- Local MP4-only input is covered by the fixture policy and runner behavior.
- ffmpeg external-process discovery is covered by Tasks 1-2.
- Extraction command and measurement behavior are covered by Tasks 3-4.
- A committed findings document is required by Task 6.
- WMF feasibility is recorded in the findings document as a documented feasibility result, not a full implementation.
- Out-of-scope boundaries are verified in Task 7.

Placeholder scan:

- This plan does not require committing a binary fixture or ffmpeg binary.
- The only environment-dependent step is Task 6, which has explicit failure behavior if no local MP4 or ffmpeg exists.
- The findings document is generated from the real spike run, not hand-waved terminal output.

Type consistency:

- `FfmpegBinaryResolver`, `FfmpegPosterFrameExtractor`, `FfmpegBinaryResolution`, `FfmpegPosterExtractionResult`, and `ProcessRunResult` are introduced before use in later tasks.
- `IProcessRunner` is internal and testable through `InternalsVisibleTo("Rook.Tests")`.
- The manual test uses the same extractor path as the unit-tested implementation.
