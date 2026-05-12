# Video Frame Sidecar Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce frame-exact `start_frame` and `end_frame` sidecars for every newly completed generated-video artifact while preserving the durable-video success boundary.

**Architecture:** Add a reusable local-MP4-to-JPEG frame extractor shaped around `VideoFrameSelector.First`, `Last`, and `FrameIndex(long index)`. Add a narrow artifact-aware `VideoFrameSidecarProducer` that resolves `ffmpeg.exe` once, extracts `First` then `Last`, and publishes each role independently through `VideoSidecarPublisher`; wire it into `VideoJobManager` after durable video artifact creation and before terminal `Complete`.

**Tech Stack:** C# managed Rook video subsystem (`src/Rook`, multi-target `net7.0;net48`), xUnit tests in `src/Rook.Tests` (`net48`), `ArtifactStore`, `VideoSidecarPublisher`, existing ffmpeg process runner and resolver seams.

---

## File Structure

- Create `src/Rook/Services/Vision/Video/Extraction/VideoFrameExtractionModels.cs`
  - Owns `VideoFrameSelector`, `VideoFrameSelectorKind`, `FfmpegVideoFrameExtractionError`, and `FfmpegVideoFrameExtractionResult`.
- Create `src/Rook/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractor.cs`
  - Owns local MP4 frame extraction for `First`, `Last`, and `FrameIndex`.
  - Reuses existing `IProcessRunner`, `DefaultProcessRunner`, and `ProcessRunResult` from the extraction namespace.
- Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractorTests.cs`
  - Pins selector validation, command intent, result mapping, image validation, and bounded diagnostics.
- Create `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`
  - Owns `IVideoFrameSidecarProducer`, producer result types, resolver/extractor/temp/byte-reader/publisher seams, and default producer implementation.
- Create `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`
  - Pins per-role publication, partial success, missing ffmpeg short-circuit, duplicate behavior, cleanup diagnostics, and one-frame distinct-role behavior without invoking real ffmpeg.
- Modify `src/Rook/Services/Vision/Video/VideoJobManager.cs`
  - Adds injectable `IVideoFrameSidecarProducer`.
  - Calls it after poster derivative work and before terminal `Complete`.
  - Keeps derivative exceptions/cancellation contained after artifact creation.
- Modify `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
  - Adds a fake frame sidecar producer.
  - Updates the test helper to inject the fake by default, so the manager suite does not run ffmpeg in unrelated tests.
  - Adds focused manager tests for frame sidecar ordering and non-fatal failure behavior.
- Modify after implementation verification:
  - `docs/rook_docs/video-thumbnail-roadmap.md`
  - `docs/rook_docs/work-queue.md`

---

### Task 1: Add Frame Selector And Extraction Result Models

**Files:**
- Create: `src/Rook/Services/Vision/Video/Extraction/VideoFrameExtractionModels.cs`
- Create: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractorTests.cs`

- [ ] **Step 1: Write failing selector model tests**

Create `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractorTests.cs` with this initial content:

```csharp
using System;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public sealed class FfmpegVideoFrameExtractorTests
    {
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
    }
}
```

- [ ] **Step 2: Run the selector tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests" --no-restore
```

Expected: build fails because `VideoFrameSelector` and `VideoFrameSelectorKind` do not exist.

- [ ] **Step 3: Add minimal selector and extraction result models**

Create `src/Rook/Services/Vision/Video/Extraction/VideoFrameExtractionModels.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Video.Extraction
{
    internal enum VideoFrameSelectorKind
    {
        First,
        Last,
        FrameIndex,
    }

    internal readonly struct VideoFrameSelector
    {
        private VideoFrameSelector(VideoFrameSelectorKind kind, long? frameIndexValue)
        {
            Kind = kind;
            FrameIndexValue = frameIndexValue;
        }

        public VideoFrameSelectorKind Kind { get; }
        public long? FrameIndexValue { get; }

        public static VideoFrameSelector First => new(VideoFrameSelectorKind.First, 0);
        public static VideoFrameSelector Last => new(VideoFrameSelectorKind.Last, null);

        public static VideoFrameSelector FrameIndex(long index)
        {
            if (index < 0)
                throw new ArgumentOutOfRangeException(nameof(index), "Frame index must be zero or greater.");

            return new VideoFrameSelector(VideoFrameSelectorKind.FrameIndex, index);
        }

        internal VideoFrameSelector NormalizeFirst()
            => Kind == VideoFrameSelectorKind.First ? FrameIndex(0) : this;
    }

    internal enum FfmpegVideoFrameExtractionError
    {
        InputMissing,
        FfmpegMissing,
        ProcessStartFailed,
        ProcessFailed,
        TimedOut,
        OutputMissing,
        InvalidOutputImage,
        Cancelled,
    }

    internal sealed class FfmpegVideoFrameExtractionResult
    {
        private const int MaxDiagnosticLength = 2048;

        private FfmpegVideoFrameExtractionResult(
            bool success,
            VideoFrameSelector selector,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            int? width,
            int? height,
            TimeSpan elapsed,
            FfmpegVideoFrameExtractionError? errorCode,
            string message)
        {
            Success = success;
            Selector = selector;
            CommandLine = commandLine ?? string.Empty;
            ExitCode = exitCode;
            Stderr = Truncate(stderr ?? string.Empty);
            OutputPath = outputPath ?? string.Empty;
            Width = width;
            Height = height;
            Elapsed = elapsed;
            ErrorCode = errorCode;
            Message = message ?? string.Empty;
        }

        public bool Success { get; }
        public VideoFrameSelector Selector { get; }
        public string CommandLine { get; }
        public int? ExitCode { get; }
        public string Stderr { get; }
        public string OutputPath { get; }
        public int? Width { get; }
        public int? Height { get; }
        public TimeSpan Elapsed { get; }
        public FfmpegVideoFrameExtractionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegVideoFrameExtractionResult Completed(
            VideoFrameSelector selector,
            string commandLine,
            int exitCode,
            string stderr,
            string outputPath,
            int width,
            int height,
            TimeSpan elapsed) =>
            new(
                true,
                selector,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                width,
                height,
                elapsed,
                null,
                "Extracted video frame.");

        public static FfmpegVideoFrameExtractionResult Failed(
            VideoFrameSelector selector,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            TimeSpan elapsed,
            FfmpegVideoFrameExtractionError errorCode,
            string message) =>
            new(
                false,
                selector,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                null,
                null,
                elapsed,
                errorCode,
                message);

        private static string Truncate(string value)
            => value.Length <= MaxDiagnosticLength
                ? value
                : value.Substring(0, MaxDiagnosticLength);
    }
}
```

- [ ] **Step 4: Run selector tests and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests" --no-restore
```

Expected: selector tests pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\VideoFrameExtractionModels.cs src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegVideoFrameExtractorTests.cs
git commit -m "test: add video frame selector contract"
```

---

### Task 2: Add Frame-Exact ffmpeg Extractor

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractorTests.cs`
- Create: `src/Rook/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractor.cs`

- [ ] **Step 1: Add failing extractor tests**

Add these using directives at the top of `FfmpegVideoFrameExtractorTests.cs`:

```csharp
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
```

Change the class declaration to `public sealed class FfmpegVideoFrameExtractorTests : IDisposable`, then add this temp-root fixture inside the class:

```csharp
private readonly string _root = Path.Combine(
    Path.GetTempPath(),
    "rook-ffmpeg-frame-extractor-" + Guid.NewGuid().ToString("N"));

public void Dispose()
{
    if (Directory.Exists(_root))
        Directory.Delete(_root, recursive: true);
}
```

Add these tests:

```csharp
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
    FfmpegVideoFrameExtractionError expected)
{
    var ffmpeg = Touch(Path.Combine(_root, "ffmpeg.exe"));
    var input = Touch(Path.Combine(_root, "input.mp4"));
    var output = Path.Combine(_root, "frame.jpg");
    var runner = new FakeProcessRunner(_ =>
        new ProcessRunResult(exitCode, stderr, expected == FfmpegVideoFrameExtractionError.TimedOut, TimeSpan.FromMilliseconds(3)));
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
```

Add these helpers inside the test class:

```csharp
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
```

- [ ] **Step 2: Run extractor tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests" --no-restore
```

Expected: build fails because `FfmpegVideoFrameExtractor` does not exist.

- [ ] **Step 3: Add minimal frame extractor implementation**

Create `src/Rook/Services/Vision/Video/Extraction/FfmpegVideoFrameExtractor.cs`:

```csharp
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
                using var image = Image.FromFile(outputPath);
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
```

- [ ] **Step 4: Run extractor tests and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests" --no-restore
```

Expected: all `FfmpegVideoFrameExtractorTests` pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\FfmpegVideoFrameExtractor.cs src\Rook\Services\Vision\Video\Extraction\VideoFrameExtractionModels.cs src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegVideoFrameExtractorTests.cs
git commit -m "feat: add frame-exact video extractor"
```

---

### Task 3: Add Frame Sidecar Producer Happy Path And Missing-ffmpeg Behavior

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`
- Create: `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`

- [ ] **Step 1: Write failing producer tests for both-role success and missing ffmpeg**

Create `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFrameSidecarProducerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;

        public VideoFrameSidecarProducerTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-frame-sidecar-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_PublishesStartThenEnd()
        {
            var video = GeneratedVideo();
            var ffmpeg = Path.Combine(_root, "tools", "ffmpeg.exe");
            var tempFiles = new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            var extractor = new FakeFrameExtractor();
            var byteReader = new FakeFrameByteReader(new Dictionary<string, byte[]>
            {
                [tempFiles.StartPath] = Bytes("start jpg"),
                [tempFiles.EndPath] = Bytes("end jpg"),
            });
            var producer = CreateProducer(
                resolver: FakeFrameFfmpegResolver.Found(ffmpeg),
                extractor: extractor,
                tempFiles: tempFiles,
                byteReader: byteReader);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(video.Id, result.ArtifactId);
            Assert.Equal(
                new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                result.RoleResults.Select(r => r.Role).ToArray());
            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.Published, r.Code));
            Assert.Equal(
                new[] { VideoFrameSelectorKind.First, VideoFrameSelectorKind.Last },
                extractor.Selectors.Select(s => s.Kind).ToArray());
            Assert.Equal(new[] { ffmpeg, ffmpeg }, extractor.FfmpegPaths);
            Assert.Equal(new[] { tempFiles.StartPath, tempFiles.EndPath }, extractor.OutputPaths);
            Assert.Equal(new[] { tempFiles.StartPath, tempFiles.EndPath }, tempFiles.DeletedPaths);
            Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
            Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
        }

        [Fact]
        public async Task TryPublishFrameSidecarsAsync_MissingFfmpegReportsBothRolesWithoutExtraction()
        {
            var video = GeneratedVideo();
            var extractor = new FakeFrameExtractor();
            var producer = CreateProducer(
                resolver: FakeFrameFfmpegResolver.Missing("ffmpeg.exe was not found"),
                extractor: extractor);

            var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

            Assert.Equal(
                new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                result.RoleResults.Select(r => r.Role).ToArray());
            Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.FfmpegMissing, r.Code));
            Assert.Empty(extractor.Selectors);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
            Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
        }

        private VideoFrameSidecarProducer CreateProducer(
            FakeFrameFfmpegResolver? resolver = null,
            FakeFrameExtractor? extractor = null,
            FakeFrameTempFiles? tempFiles = null,
            FakeFrameByteReader? byteReader = null,
            IVideoFrameSidecarPublisher? publisher = null)
        {
            tempFiles ??= new FakeFrameTempFiles(
                Path.Combine(_root, "tmp", "start.jpg"),
                Path.Combine(_root, "tmp", "end.jpg"));
            return new VideoFrameSidecarProducer(
                _store,
                resolver ?? FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe")),
                extractor ?? new FakeFrameExtractor(),
                tempFiles,
                byteReader ?? new FakeFrameByteReader(new Dictionary<string, byte[]>
                {
                    [tempFiles.StartPath] = Bytes("start jpg"),
                    [tempFiles.EndPath] = Bytes("end jpg"),
                }),
                publisher);
        }

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);
    }
}
```

- [ ] **Step 2: Run producer tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoFrameSidecarProducerTests" --no-restore
```

Expected: build fails because `VideoFrameSidecarProducer`, `IVideoFrameSidecarPublisher`, result types, and fake seam interfaces do not exist.

- [ ] **Step 3: Add minimal frame sidecar producer implementation and test fakes**

Create `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs` with these contracts and implementation:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video
{
    internal enum VideoFrameSidecarRoleResultCode
    {
        Published,
        SkippedAlreadyExists,
        FfmpegMissing,
        ExtractionTimedOut,
        ExtractionFailed,
        InvalidOutput,
        VideoBlobUnavailable,
        TempPathUnavailable,
        FrameReadFailed,
        PublishFailed,
        CancelledAfterArtifactCreated,
        FinalizerFailed,
    }

    internal sealed record VideoFrameSidecarRoleResult(
        string Role,
        VideoFrameSelector Selector,
        VideoFrameSidecarRoleResultCode Code,
        string? Message = null,
        string? Diagnostic = null)
    {
        public bool Success =>
            Code == VideoFrameSidecarRoleResultCode.Published
            || Code == VideoFrameSidecarRoleResultCode.SkippedAlreadyExists;
    }

    internal sealed record VideoFrameSidecarResult(
        Guid ArtifactId,
        IReadOnlyList<VideoFrameSidecarRoleResult> RoleResults);

    internal interface IVideoFrameSidecarProducer
    {
        Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            CancellationToken cancellationToken);
    }

    internal interface IVideoFrameFfmpegResolver
    {
        FfmpegBinaryResolution Resolve();
    }

    internal interface IVideoFrameExtractor
    {
        Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken);
    }

    internal interface IVideoFrameTempFiles
    {
        string CreateFrameTempPath(Guid artifactId, string role);
        void TryDelete(string path);
    }

    internal interface IVideoFrameByteReader
    {
        byte[] ReadAllBytes(string path);
    }

    internal interface IVideoFrameSidecarPublisher
    {
        VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension);
    }

    internal sealed class VideoFrameSidecarProducer : IVideoFrameSidecarProducer
    {
        private static readonly TimeSpan DefaultExtractionTimeout = TimeSpan.FromSeconds(30);

        private readonly ArtifactStore _store;
        private readonly IVideoFrameFfmpegResolver _resolver;
        private readonly IVideoFrameExtractor _extractor;
        private readonly IVideoFrameTempFiles _tempFiles;
        private readonly IVideoFrameByteReader _byteReader;
        private readonly IVideoFrameSidecarPublisher _publisher;

        public VideoFrameSidecarProducer(ArtifactStore store)
            : this(
                store,
                new DefaultVideoFrameFfmpegResolver(),
                new DefaultVideoFrameExtractor(),
                new DefaultVideoFrameTempFiles(),
                new DefaultVideoFrameByteReader())
        {
        }

        internal VideoFrameSidecarProducer(
            ArtifactStore store,
            IVideoFrameFfmpegResolver resolver,
            IVideoFrameExtractor extractor,
            IVideoFrameTempFiles tempFiles,
            IVideoFrameByteReader byteReader,
            IVideoFrameSidecarPublisher? publisher = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
            _extractor = extractor ?? throw new ArgumentNullException(nameof(extractor));
            _tempFiles = tempFiles ?? throw new ArgumentNullException(nameof(tempFiles));
            _byteReader = byteReader ?? throw new ArgumentNullException(nameof(byteReader));
            _publisher = publisher ?? new DefaultVideoFrameSidecarPublisher(_store);
        }

        public async Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
            Guid artifactId,
            CancellationToken cancellationToken)
        {
            var roles = new[]
            {
                new RolePlan(VideoMediaRoles.StartFrame, VideoFrameSelector.First),
                new RolePlan(VideoMediaRoles.EndFrame, VideoFrameSelector.Last),
            };

            string videoPath;
            try
            {
                videoPath = _store.GetBlobAbsolutePath(artifactId, VideoMediaRoles.Video);
            }
            catch (Exception ex)
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    Array.ConvertAll(
                        roles,
                        r => Failure(r, VideoFrameSidecarRoleResultCode.VideoBlobUnavailable, ex.Message, ex.ToString())));
            }

            FfmpegBinaryResolution ffmpeg;
            try
            {
                ffmpeg = _resolver.Resolve();
            }
            catch (Exception ex)
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    Array.ConvertAll(
                        roles,
                        r => Failure(r, VideoFrameSidecarRoleResultCode.FinalizerFailed, ex.Message, ex.ToString())));
            }

            if (!ffmpeg.Success || string.IsNullOrWhiteSpace(ffmpeg.Path))
            {
                return new VideoFrameSidecarResult(
                    artifactId,
                    Array.ConvertAll(
                        roles,
                        r => Failure(r, VideoFrameSidecarRoleResultCode.FfmpegMissing, ffmpeg.Message, ffmpeg.ErrorCode?.ToString())));
            }

            var results = new List<VideoFrameSidecarRoleResult>(roles.Length);
            foreach (var role in roles)
            {
                results.Add(await TryPublishOneAsync(
                    artifactId,
                    videoPath,
                    ffmpeg.Path!,
                    role,
                    cancellationToken).ConfigureAwait(false));
            }

            return new VideoFrameSidecarResult(artifactId, results);
        }

        private async Task<VideoFrameSidecarRoleResult> TryPublishOneAsync(
            Guid artifactId,
            string videoPath,
            string ffmpegPath,
            RolePlan role,
            CancellationToken cancellationToken)
        {
            string? tempPath = null;
            try
            {
                tempPath = _tempFiles.CreateFrameTempPath(artifactId, role.Role);
                var extraction = await _extractor.ExtractFrameAsync(
                        ffmpegPath,
                        videoPath,
                        role.Selector,
                        tempPath,
                        DefaultExtractionTimeout,
                        cancellationToken)
                    .ConfigureAwait(false);

                if (!extraction.Success)
                    return CleanupAndReturn(tempPath, MapExtractionFailure(role, extraction));

                byte[] bytes;
                try
                {
                    bytes = _byteReader.ReadAllBytes(tempPath);
                }
                catch (Exception ex) when (!(ex is OperationCanceledException))
                {
                    return CleanupAndReturn(
                        tempPath,
                        Failure(role, VideoFrameSidecarRoleResultCode.FrameReadFailed, ex.Message, ex.ToString()));
                }

                var published = _publisher.Publish(artifactId, role.Role, bytes, "jpg");
                var result = published.Code switch
                {
                    VideoSidecarPublishResultCode.Succeeded =>
                        Failure(role, VideoFrameSidecarRoleResultCode.Published, published.Message, null),
                    VideoSidecarPublishResultCode.SkippedAlreadyExists =>
                        Failure(role, VideoFrameSidecarRoleResultCode.SkippedAlreadyExists, published.Message, null),
                    _ =>
                        Failure(role, VideoFrameSidecarRoleResultCode.PublishFailed, published.Message, published.Code.ToString()),
                };
                return CleanupAndReturn(tempPath, result);
            }
            catch (OperationCanceledException ex)
            {
                return CleanupAndReturn(
                    tempPath,
                    Failure(role, VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated, ex.Message, ex.ToString()));
            }
            catch (Exception ex) when (tempPath is null)
            {
                return Failure(role, VideoFrameSidecarRoleResultCode.TempPathUnavailable, ex.Message, ex.ToString());
            }
            catch (Exception ex)
            {
                return CleanupAndReturn(
                    tempPath,
                    Failure(role, VideoFrameSidecarRoleResultCode.FinalizerFailed, ex.Message, ex.ToString()));
            }
        }

        private VideoFrameSidecarRoleResult CleanupAndReturn(
            string? tempPath,
            VideoFrameSidecarRoleResult result)
        {
            if (string.IsNullOrWhiteSpace(tempPath))
                return result;

            try
            {
                _tempFiles.TryDelete(tempPath);
                return result;
            }
            catch (Exception ex)
            {
                return result with
                {
                    Diagnostic = AppendDiagnostic(result.Diagnostic, "Cleanup failed: " + ex),
                };
            }
        }

        private static VideoFrameSidecarRoleResult MapExtractionFailure(
            RolePlan role,
            FfmpegVideoFrameExtractionResult extraction)
        {
            var code = extraction.ErrorCode switch
            {
                FfmpegVideoFrameExtractionError.FfmpegMissing => VideoFrameSidecarRoleResultCode.FfmpegMissing,
                FfmpegVideoFrameExtractionError.TimedOut => VideoFrameSidecarRoleResultCode.ExtractionTimedOut,
                FfmpegVideoFrameExtractionError.InvalidOutputImage => VideoFrameSidecarRoleResultCode.InvalidOutput,
                FfmpegVideoFrameExtractionError.Cancelled => VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated,
                _ => VideoFrameSidecarRoleResultCode.ExtractionFailed,
            };
            return Failure(role, code, extraction.Message, extraction.Stderr);
        }

        private static VideoFrameSidecarRoleResult Failure(
            RolePlan role,
            VideoFrameSidecarRoleResultCode code,
            string? message,
            string? diagnostic) =>
            new(role.Role, role.Selector, code, message, diagnostic);

        private static string AppendDiagnostic(string? current, string addition)
            => string.IsNullOrWhiteSpace(current)
                ? addition
                : current + Environment.NewLine + addition;

        private readonly struct RolePlan
        {
            public RolePlan(string role, VideoFrameSelector selector)
            {
                Role = role;
                Selector = selector;
            }

            public string Role { get; }
            public VideoFrameSelector Selector { get; }
        }
    }

    internal sealed class DefaultVideoFrameFfmpegResolver : IVideoFrameFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve() => FfmpegBinaryResolver.Resolve();
    }

    internal sealed class DefaultVideoFrameExtractor : IVideoFrameExtractor
    {
        private readonly FfmpegVideoFrameExtractor _extractor = new();

        public Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
            string ffmpegPath,
            string inputPath,
            VideoFrameSelector selector,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken) =>
            _extractor.ExtractFrameAsync(ffmpegPath, inputPath, selector, outputPath, timeout, cancellationToken);
    }

    internal sealed class DefaultVideoFrameTempFiles : IVideoFrameTempFiles
    {
        public string CreateFrameTempPath(Guid artifactId, string role)
        {
            var directory = Path.Combine(Path.GetTempPath(), "rook-video-frames");
            Directory.CreateDirectory(directory);
            return Path.Combine(directory, $"{artifactId:N}-{role}-{Guid.NewGuid():N}.jpg");
        }

        public void TryDelete(string path)
        {
            if (!string.IsNullOrWhiteSpace(path) && File.Exists(path))
                File.Delete(path);
        }
    }

    internal sealed class DefaultVideoFrameByteReader : IVideoFrameByteReader
    {
        public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);
    }

    internal sealed class DefaultVideoFrameSidecarPublisher : IVideoFrameSidecarPublisher
    {
        private readonly VideoSidecarPublisher _publisher;

        public DefaultVideoFrameSidecarPublisher(ArtifactStore store)
        {
            _publisher = new VideoSidecarPublisher(store);
        }

        public VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension) =>
            _publisher.Publish(artifactId, role, content, fileExtension);
    }
}
```

Append fake classes to `VideoFrameSidecarProducerTests`:

```csharp
private sealed class FakeFrameFfmpegResolver : IVideoFrameFfmpegResolver
{
    private readonly FfmpegBinaryResolution _resolution;

    private FakeFrameFfmpegResolver(FfmpegBinaryResolution resolution)
    {
        _resolution = resolution;
    }

    public static FakeFrameFfmpegResolver Found(string path)
        => new(FfmpegBinaryResolution.Found(path, FfmpegBinaryResolutionSource.ConfiguredPath));

    public static FakeFrameFfmpegResolver Missing(string message)
        => new(FfmpegBinaryResolution.Failed(FfmpegBinaryResolutionError.NotFound, message));

    public Exception? ThrowOnResolve { get; set; }

    public FfmpegBinaryResolution Resolve()
    {
        if (ThrowOnResolve is not null)
            throw ThrowOnResolve;
        return _resolution;
    }
}

private sealed class FakeFrameExtractor : IVideoFrameExtractor
{
    public List<string> FfmpegPaths { get; } = new();
    public List<string> InputPaths { get; } = new();
    public List<VideoFrameSelector> Selectors { get; } = new();
    public List<string> OutputPaths { get; } = new();
    public Dictionary<VideoFrameSelectorKind, FfmpegVideoFrameExtractionResult> ResultsByKind { get; } = new();
    public Exception? ThrowOnExtract { get; set; }

    public Task<FfmpegVideoFrameExtractionResult> ExtractFrameAsync(
        string ffmpegPath,
        string inputPath,
        VideoFrameSelector selector,
        string outputPath,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        FfmpegPaths.Add(ffmpegPath);
        InputPaths.Add(inputPath);
        Selectors.Add(selector);
        OutputPaths.Add(outputPath);
        if (ThrowOnExtract is not null)
            throw ThrowOnExtract;

        if (ResultsByKind.TryGetValue(selector.Kind, out var result))
            return Task.FromResult(result);

        return Task.FromResult(FfmpegVideoFrameExtractionResult.Completed(
            selector,
            "ffmpeg command",
            0,
            string.Empty,
            outputPath,
            80,
            40,
            TimeSpan.FromMilliseconds(1)));
    }
}

private sealed class FakeFrameTempFiles : IVideoFrameTempFiles
{
    public FakeFrameTempFiles(string startPath, string endPath)
    {
        StartPath = startPath;
        EndPath = endPath;
    }

    public string StartPath { get; }
    public string EndPath { get; }
    public List<string> DeletedPaths { get; } = new();
    public Exception? ThrowOnCreateStart { get; set; }
    public Exception? ThrowOnCreateEnd { get; set; }
    public Exception? ThrowOnDelete { get; set; }

    public string CreateFrameTempPath(Guid artifactId, string role)
    {
        if (role == VideoMediaRoles.StartFrame && ThrowOnCreateStart is not null)
            throw ThrowOnCreateStart;
        if (role == VideoMediaRoles.EndFrame && ThrowOnCreateEnd is not null)
            throw ThrowOnCreateEnd;
        return role == VideoMediaRoles.StartFrame ? StartPath : EndPath;
    }

    public void TryDelete(string path)
    {
        DeletedPaths.Add(path);
        if (ThrowOnDelete is not null)
            throw ThrowOnDelete;
        if (File.Exists(path))
            File.Delete(path);
    }
}

private sealed class FakeFrameByteReader : IVideoFrameByteReader
{
    private readonly Dictionary<string, byte[]> _bytesByPath;

    public FakeFrameByteReader(Dictionary<string, byte[]> bytesByPath)
    {
        _bytesByPath = bytesByPath;
    }

    public Exception? ThrowOnStartRead { get; set; }
    public Exception? ThrowOnEndRead { get; set; }

    public byte[] ReadAllBytes(string path)
    {
        if (path.Contains("start") && ThrowOnStartRead is not null)
            throw ThrowOnStartRead;
        if (path.Contains("end") && ThrowOnEndRead is not null)
            throw ThrowOnEndRead;
        return _bytesByPath[path];
    }
}

private sealed class FakeFrameSidecarPublisher : IVideoFrameSidecarPublisher
{
    public Dictionary<string, VideoSidecarPublishResult> ResultsByRole { get; } = new();
    public List<string> Roles { get; } = new();
    public Exception? ThrowOnStartPublish { get; set; }
    public Exception? ThrowOnEndPublish { get; set; }

    public VideoSidecarPublishResult Publish(
        Guid artifactId,
        string role,
        byte[] content,
        string fileExtension)
    {
        Roles.Add(role);
        if (role == VideoMediaRoles.StartFrame && ThrowOnStartPublish is not null)
            throw ThrowOnStartPublish;
        if (role == VideoMediaRoles.EndFrame && ThrowOnEndPublish is not null)
            throw ThrowOnEndPublish;
        if (ResultsByRole.TryGetValue(role, out var result))
            return result;
        return new VideoSidecarPublishResult(
            VideoSidecarPublishResultCode.Succeeded,
            artifactId,
            role);
    }
}
```

- [ ] **Step 4: Run producer tests and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoFrameSidecarProducerTests" --no-restore
```

Expected: both producer tests pass.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoFrameSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\VideoFrameSidecarProducerTests.cs
git commit -m "feat: add video frame sidecar producer"
```

---

### Task 4: Add Producer Edge-Case Coverage

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`

- [ ] **Step 1: Add failing edge-case tests**

Add tests to `VideoFrameSidecarProducerTests` for partial success, duplicates, temp/read/publish failures, cancellation, cleanup diagnostics, and one-frame distinct roles:

```csharp
[Fact]
public async Task TryPublishFrameSidecarsAsync_StartSuccessEndExtractionFailurePublishesOnlyStart()
{
    var video = GeneratedVideo();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"));
    var extractor = new FakeFrameExtractor();
    extractor.ResultsByKind[VideoFrameSelectorKind.Last] =
        FfmpegVideoFrameExtractionResult.Failed(
            VideoFrameSelector.Last,
            "ffmpeg command",
            1,
            "decode failed",
            tempFiles.EndPath,
            TimeSpan.FromMilliseconds(1),
            FfmpegVideoFrameExtractionError.ProcessFailed,
            "decode failed");
    var producer = CreateProducer(extractor: extractor, tempFiles: tempFiles);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.ExtractionFailed, result.RoleResults[1].Code);
    Assert.Contains(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
    Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_StartFailureEndSuccessPublishesOnlyEnd()
{
    var video = GeneratedVideo();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"));
    var extractor = new FakeFrameExtractor();
    extractor.ResultsByKind[VideoFrameSelectorKind.First] =
        FfmpegVideoFrameExtractionResult.Failed(
            VideoFrameSelector.First,
            "ffmpeg command",
            null,
            "timeout",
            tempFiles.StartPath,
            TimeSpan.FromSeconds(30),
            FfmpegVideoFrameExtractionError.TimedOut,
            "timed out");
    var producer = CreateProducer(extractor: extractor, tempFiles: tempFiles);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.ExtractionTimedOut, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
    Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
    Assert.Contains(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_DuplicateStartDoesNotPreventEnd()
{
    var video = GeneratedVideo();
    new VideoSidecarPublisher(_store).Publish(video.Id, VideoMediaRoles.StartFrame, Bytes("existing"), "jpg");
    var producer = CreateProducer();

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.SkippedAlreadyExists, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
    Assert.Single(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
    Assert.Single(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_TempPathFailureForStartDoesNotPreventEnd()
{
    var video = GeneratedVideo();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"))
    {
        ThrowOnCreateStart = new IOException("start temp failed"),
    };
    var producer = CreateProducer(tempFiles: tempFiles);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.TempPathUnavailable, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_ReadFailureForEndDoesNotChangeStart()
{
    var video = GeneratedVideo();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"));
    var byteReader = new FakeFrameByteReader(new Dictionary<string, byte[]>
    {
        [tempFiles.StartPath] = Bytes("start jpg"),
        [tempFiles.EndPath] = Bytes("end jpg"),
    })
    {
        ThrowOnEndRead = new IOException("end read failed"),
    };
    var producer = CreateProducer(tempFiles: tempFiles, byteReader: byteReader);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.FrameReadFailed, result.RoleResults[1].Code);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_StartPublishFailureDoesNotPreventEnd()
{
    var video = GeneratedVideo();
    var publisher = new FakeFrameSidecarPublisher();
    publisher.ResultsByRole[VideoMediaRoles.StartFrame] = new VideoSidecarPublishResult(
        VideoSidecarPublishResultCode.StorageFailed,
        video.Id,
        VideoMediaRoles.StartFrame,
        Message: "start publish failed");
    var producer = CreateProducer(publisher: publisher);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.PublishFailed, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
    Assert.Equal(
        new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
        publisher.Roles);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_GenericExceptionDuringOneRoleBecomesFinalizerFailedAndOtherRoleIsAttempted()
{
    var video = GeneratedVideo();
    var publisher = new FakeFrameSidecarPublisher
    {
        ThrowOnStartPublish = new InvalidOperationException("start publish exploded"),
    };
    var producer = CreateProducer(publisher: publisher);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.FinalizerFailed, result.RoleResults[0].Code);
    Assert.Contains("start publish exploded", result.RoleResults[0].Message);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
    Assert.Equal(
        new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
        publisher.Roles);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_CancellationDuringOneRoleIsPerRoleFailure()
{
    var video = GeneratedVideo();
    var extractor = new FakeFrameExtractor
    {
        ThrowOnExtract = new OperationCanceledException("cancel derivative"),
    };
    var producer = CreateProducer(extractor: extractor);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.CancelledAfterArtifactCreated, result.RoleResults[1].Code);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_CleanupFailureIsDiagnosticOnly()
{
    var video = GeneratedVideo();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"))
    {
        ThrowOnDelete = new IOException("cleanup failed"),
    };
    var producer = CreateProducer(tempFiles: tempFiles);

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[0].Code);
    Assert.Contains("cleanup failed", result.RoleResults[0].Diagnostic);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_OneFrameVideoStillPublishesDistinctRolesWhenBothExtractionsSucceed()
{
    var video = GeneratedVideo();
    var producer = CreateProducer();

    var result = await producer.TryPublishFrameSidecarsAsync(video.Id, CancellationToken.None);

    Assert.All(result.RoleResults, r => Assert.Equal(VideoFrameSidecarRoleResultCode.Published, r.Code));
    Assert.Contains(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
    Assert.Contains(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
    Assert.NotEqual(
        _store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame),
        _store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame));
}
```

- [ ] **Step 2: Run edge-case tests and verify RED where implementation is incomplete**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoFrameSidecarProducerTests" --no-restore
```

Expected before fixes: one or more edge-case tests fail if the initial implementation does not yet preserve per-role attempts or diagnostics correctly.

- [ ] **Step 3: Update implementation until all edge-case tests pass**

Make only the minimal changes needed in `VideoFrameSidecarProducer.cs`:

- catch exceptions inside `TryPublishOneAsync` per role;
- keep the `foreach` over both roles even after a role fails;
- map extraction timeout to `ExtractionTimedOut`;
- map invalid image output to `InvalidOutput`;
- map extraction cancellation to `CancelledAfterArtifactCreated`;
- keep cleanup diagnostics on the role result without changing `Published` or `SkippedAlreadyExists`.

- [ ] **Step 4: Run producer tests and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoFrameSidecarProducerTests" --no-restore
```

Expected: all frame sidecar producer tests pass.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoFrameSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\VideoFrameSidecarProducerTests.cs
git commit -m "test: cover frame sidecar partial failures"
```

---

### Task 5: Wire Frame Sidecars Into VideoJobManager

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoJobManager.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`

- [ ] **Step 1: Write failing manager wiring tests**

In `VideoJobManagerTests`, update the `Manager(...)` helper signature:

```csharp
private VideoJobManager Manager(
    TimeSpan? pollInterval = null,
    IVideoCostEstimator? estimator = null,
    VideoArtifactMaterializer? materializer = null,
    IVideoPosterSidecarProducer? posterProducer = null,
    IVideoFrameSidecarProducer? frameProducer = null,
    IVideoProviderRegistry? registry = null,
    IVideoJobLedger? ledger = null) =>
```

Pass `frameProducer: frameProducer ?? new FakeFrameProducer()` into the internal `VideoJobManager` constructor after adding that constructor parameter in the next implementation step.

Add tests near the existing poster finalization tests:

```csharp
[Fact]
public async Task Complete_video_publishes_frame_sidecars_before_Complete()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    ConfigureProviderHappyPath();
    var frameStarted = new TaskCompletionSource<Guid>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    var releaseFrames = new TaskCompletionSource<bool>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    var frameProducer = new FakeFrameProducer
    {
        OnPublishAsync = async (artifactId, _) =>
        {
            frameStarted.TrySetResult(artifactId);
            await releaseFrames.Task.ConfigureAwait(false);
            return FakeFrameProducer.PublishedBoth(artifactId);
        },
    };

    var mgr = Manager(frameProducer: frameProducer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);

    await WaitForSignalAsync(
        frameStarted.Task,
        "Frame sidecar producer did not start before job completion.");
    var status = await mgr.GetStatusAsync(jobId, CancellationToken.None);
    Assert.NotEqual(VideoJobState.Complete, status.State);
    Assert.DoesNotContain(
        _ledger.AllRecords.Where(r => r.JobId == jobId),
        r => r.State == VideoJobState.Complete);

    releaseFrames.SetResult(true);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Complete, final.State);
    Assert.Equal(final.ResultArtifactId!.Value, await frameStarted.Task);
}

[Fact]
public async Task Complete_video_still_completes_when_frame_sidecars_partially_fail()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    ConfigureProviderHappyPath();
    var frameProducer = new FakeFrameProducer
    {
        OnPublishAsync = (artifactId, _) => Task.FromResult(new VideoFrameSidecarResult(
            artifactId,
            new[]
            {
                new VideoFrameSidecarRoleResult(
                    VideoMediaRoles.StartFrame,
                    VideoFrameSelector.First,
                    VideoFrameSidecarRoleResultCode.Published),
                new VideoFrameSidecarRoleResult(
                    VideoMediaRoles.EndFrame,
                    VideoFrameSelector.Last,
                    VideoFrameSidecarRoleResultCode.ExtractionFailed),
            })),
    };

    var mgr = Manager(frameProducer: frameProducer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Complete, final.State);
    Assert.Single(frameProducer.ArtifactIds);
    Assert.DoesNotContain(
        _ledger.AllRecords.Where(r => r.JobId == jobId),
        r => r.State == VideoJobState.Error || r.State == VideoJobState.Cancelled);
}

[Fact]
public async Task Complete_video_still_completes_when_frame_stage_observes_cancellation()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    ConfigureProviderHappyPath();
    var frameProducer = new FakeFrameProducer
    {
        OnPublishAsync = (_, _) => throw new OperationCanceledException("frame derivative cancel"),
    };

    var mgr = Manager(frameProducer: frameProducer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Complete, final.State);
    Assert.DoesNotContain(
        _ledger.AllRecords.Where(r => r.JobId == jobId),
        r => r.State == VideoJobState.Cancelled);
}

[Fact]
public async Task Sync_submit_completion_uses_same_frame_sidecar_finalization()
{
    var jobId = Guid.NewGuid();
    _idGen.Sequence.Enqueue(jobId);
    _provider.OnSubmit = (_, _) =>
        new GenSyncSubmitOutcome(
            new GenSuccessResultOutcome(VideoSuccessEnvelope(FakeMp4, "video/mp4")));
    var frameProducer = new FakeFrameProducer();

    var mgr = Manager(frameProducer: frameProducer);
    await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
    var final = await WaitForTerminalAsync(mgr, jobId);

    Assert.Equal(VideoJobState.Complete, final.State);
    Assert.Single(frameProducer.ArtifactIds);
    Assert.Equal(final.ResultArtifactId.Value, frameProducer.ArtifactIds[0]);
}
```

Add fake near `FakePosterProducer`:

```csharp
internal sealed class FakeFrameProducer : IVideoFrameSidecarProducer
{
    public List<Guid> ArtifactIds { get; } = new();

    public Func<Guid, CancellationToken, Task<VideoFrameSidecarResult>>
        OnPublishAsync { get; set; } =
            (artifactId, _) => Task.FromResult(PublishedBoth(artifactId));

    public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
        Guid artifactId,
        CancellationToken cancellationToken)
    {
        ArtifactIds.Add(artifactId);
        return OnPublishAsync(artifactId, cancellationToken);
    }

    public static VideoFrameSidecarResult PublishedBoth(Guid artifactId) =>
        new(
            artifactId,
            new[]
            {
                new VideoFrameSidecarRoleResult(
                    VideoMediaRoles.StartFrame,
                    VideoFrameSelector.First,
                    VideoFrameSidecarRoleResultCode.Published),
                new VideoFrameSidecarRoleResult(
                    VideoMediaRoles.EndFrame,
                    VideoFrameSelector.Last,
                    VideoFrameSidecarRoleResultCode.Published),
            });
}
```

Change the direct public-constructor pricing test to use `Manager(registry: registryWithCounter)` instead of `new VideoJobManager(...)` so unrelated tests do not run the real frame extractor.

- [ ] **Step 2: Run manager tests and verify RED**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoJobManagerTests" --no-restore
```

Expected: build fails because the internal `VideoJobManager` constructor does not yet accept `frameProducer`, or focused tests fail because frame producer is not called.

- [ ] **Step 3: Add `VideoJobManager` frame producer injection and call site**

Modify `src/Rook/Services/Vision/Video/VideoJobManager.cs`:

Add field:

```csharp
private readonly IVideoFrameSidecarProducer _frameProducer;
```

Update the public constructor's internal delegation:

```csharp
frameProducer: null)
```

Update the internal constructor signature:

```csharp
IVideoPosterSidecarProducer? posterProducer = null,
IVideoFrameSidecarProducer? frameProducer = null)
```

Assign:

```csharp
_frameProducer = frameProducer ?? new VideoFrameSidecarProducer(_artifactStore);
```

In `SaveGeneratedVideoAndCompleteAsync`, after the existing poster try/catch and before `AppendTransition(... Complete ...)`, add:

```csharp
try
{
    await _frameProducer.TryPublishFrameSidecarsAsync(
        artifact.Id,
        CancellationToken.None).ConfigureAwait(false);
}
catch (OperationCanceledException)
{
}
catch (Exception)
{
}
```

Keep `CancellationToken.None` for derivative work after durable artifact creation to match Slice 3's non-fatal finalization boundary.

- [ ] **Step 4: Run manager tests and verify GREEN**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~VideoJobManagerTests" --no-restore
```

Expected: all manager tests pass.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoJobManager.cs src\Rook.Tests\Services\Vision\Video\VideoJobManagerTests.cs
git commit -m "feat: publish frame sidecars on video completion"
```

---

### Task 6: Focused Contract And Full Managed Verification

**Files:**
- Read: `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
- Read: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Run focused Slice 4 suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests|FullyQualifiedName~VideoFrameSidecarProducerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VisionVideoSidecarContractSourceTests" --no-restore
```

Expected: focused suite passes. Existing UI source tests still pin generated-video picker eligibility to `start_frame` / `end_frame` and keep `poster` display-only.

- [ ] **Step 2: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore
```

Expected: full managed `net48` test suite passes.

- [ ] **Step 3: Build managed plugin target**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore
```

Expected: `net7.0` managed plugin build succeeds.

- [ ] **Step 4: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

---

### Task 7: Update Roadmap And Work Queue

**Files:**
- Modify: `docs/rook_docs/video-thumbnail-roadmap.md`
- Modify: `docs/rook_docs/work-queue.md`

- [ ] **Step 1: Update roadmap state**

In `docs/rook_docs/video-thumbnail-roadmap.md`, update `Last updated` to `2026-05-12` if it is not already set.

Change current state text so Slice 4 is done and Slice 5 is current next:

```markdown
Current next slice:

- Reconcile/backfill existing generated-video artifacts that are missing local-MP4-derived sidecars.
```

Update the Slice Tracker rows:

```markdown
| 4. Frame-exact sidecar producer | Done | Produce `start_frame` and `end_frame` from the local MP4 for completed generated videos. | Newly completed generated videos attempt both frame-exact boundary sidecars; `start_frame` uses decoded frame index `0`; `end_frame` uses the final decodable frame; partial sidecar failure remains non-fatal; extracted frames are not confused with posters. |
| 5. Existing-video reconcile/backfill | Next | Populate missing sidecars for older video artifacts from local MP4 files when possible. | Reconcile is idempotent, bounded, observable, and does not rerun provider jobs. |
```

- [ ] **Step 2: Prepend work-queue triage entry**

At the top of `docs/rook_docs/work-queue.md`, prepend:

```markdown
**Last triaged:** 2026-05-12 (**RookVision video thumbnail Slice 4 complete.** Newly completed generated-video artifacts now attempt frame-exact `start_frame` and `end_frame` sidecar production from the saved local MP4 after durable `video` artifact creation and before terminal `Complete`. `start_frame` is decoded frame index `0`; `end_frame` is the final decodable frame of the primary video stream. Frame sidecar production is local-MP4 based, publishes only through `VideoSidecarPublisher`, allows per-role partial success, preserves `poster` as display-only, and keeps derivative failure/cancellation from changing a saved video job into `Error` or `Cancelled`. **Promoted to Now:** Slice 5 existing-video reconcile/backfill. **Do not skip ahead** to provider-payload frame/poster mappings, installer ffmpeg packaging/license work, or GH NLE token/component behavior until Slice 5 gates and the ffmpeg packaging decision have their own reviewed slices.)
```

- [ ] **Step 3: Verify docs diff**

Run:

```powershell
git diff --check -- docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
```

Expected: no whitespace errors.

- [ ] **Step 4: Commit docs**

Run:

```powershell
git add docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
git commit -m "docs: advance video thumbnail roadmap to backfill"
```

---

### Task 8: Final Verification And Review Prep

**Files:**
- Read: all changed files from `git diff --name-only main...HEAD` if working on a branch, or from recent commits if working on `main`.

- [ ] **Step 1: Run final focused suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --filter "FullyQualifiedName~FfmpegVideoFrameExtractorTests|FullyQualifiedName~VideoFrameSidecarProducerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VisionVideoSidecarContractSourceTests" --no-restore
```

Expected: focused suite passes.

- [ ] **Step 2: Run final full managed suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore
```

Expected: full managed suite passes.

- [ ] **Step 3: Run final managed build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore
```

Expected: build succeeds.

- [ ] **Step 4: Run final diff check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 5: Summarize implementation for review**

Prepare review notes with:

- frame selector contract and zero-based decoded-frame semantics;
- ffmpeg ownership boundary: producer resolves once, extractor accepts resolved path and validates defensively;
- `First`/`Last` sidecar mapping;
- partial success behavior;
- durable-video success boundary;
- tests run and pass/fail counts;
- explicit note that no live Rhino or real-ffmpeg smoke was required unless a reviewer asks for it.
