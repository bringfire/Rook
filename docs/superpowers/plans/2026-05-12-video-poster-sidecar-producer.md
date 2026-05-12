# Video Poster Sidecar Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce display-only `poster` sidecars for newly completed generated-video artifacts before the video job reaches `Complete`, while keeping poster work strictly best-effort after the MP4 artifact is saved.

**Architecture:** Add a managed `VideoPosterSidecarProducer` with seams for ffmpeg resolution, extraction, temp files, poster byte reads, and sidecar publication. Refactor `VideoJobManager` so both polled and sync completion paths use one generated-video finalization helper: save `video`, attempt poster, append `Complete`.

**Tech Stack:** C# net7.0, xUnit, `ArtifactStore`, `VideoSidecarPublisher`, `FfmpegBinaryResolver`, `FfmpegPosterFrameExtractor`, managed Rook video subsystem.

---

## File Structure

- Create `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`
  - Owns `IVideoPosterSidecarProducer`, `VideoPosterSidecarResultCode`, `VideoPosterSidecarResult`, and the default producer implementation.
  - Provides test seams for ffmpeg resolution, extraction, temp-file handling, poster byte reads, and sidecar publication.
- Create `src/Rook.Tests/Services/Vision/Video/VideoPosterSidecarProducerTests.cs`
  - Unit-tests poster producer outcomes without invoking real ffmpeg.
- Modify `src/Rook/Services/Vision/Video/VideoJobManager.cs`
  - Adds injectable `IVideoPosterSidecarProducer`.
  - Extracts shared generated-video finalization helper.
  - Uses `VideoMediaRoles.Video` instead of literal `"video"` in changed save code.
- Modify `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
  - Injects a fake poster producer for deterministic manager tests.
  - Pins success, failure, duplicate/no-op, and cancellation-after-artifact-created behavior.
- Read only `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
  - Existing source-level UI tests already pin Gallery poster display and picker exclusion.
- Modify after implementation completion:
  - `docs/rook_docs/video-thumbnail-roadmap.md`
  - `docs/rook_docs/work-queue.md`

---

### Task 1: Add Producer Result Contracts And Happy/Missing-ffmpeg Tests

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/VideoPosterSidecarProducerTests.cs`
- Create: `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`

- [ ] **Step 1: Write failing producer tests for publish success and missing ffmpeg**

Create `src/Rook.Tests/Services/Vision/Video/VideoPosterSidecarProducerTests.cs` with this initial content:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoPosterSidecarProducerTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly FakeFfmpegResolver _resolver = new();
        private readonly FakePosterExtractor _extractor = new();
        private readonly FakeTempFiles _tempFiles;
        private readonly FakePosterBytes _posterBytes = new();

        public VideoPosterSidecarProducerTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-poster-producer-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _tempFiles = new FakeTempFiles(Path.Combine(_root, "tmp"));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task TryPublishPosterAsync_ExtractsAndPublishesPoster()
        {
            var artifact = GeneratedVideo();
            var outputPath = Path.Combine(_root, "tmp", "poster.jpg");
            _resolver.Result = FfmpegBinaryResolution.Found("C:\\tools\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);
            _tempFiles.NextPath = outputPath;
            _extractor.Result = FfmpegPosterExtractionResult.Completed(
                "ffmpeg command",
                0,
                "stderr",
                outputPath,
                640,
                360,
                TimeSpan.FromMilliseconds(25));
            _posterBytes.BytesByPath[outputPath] = new byte[] { 1, 2, 3, 4 };

            var producer = Producer();
            var result = await producer.TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.Published, result.Code);
            var loaded = _store.Get(artifact.Id);
            Assert.NotNull(loaded);
            Assert.Contains(loaded!.Files, f => f.Role == VideoMediaRoles.Poster && f.Path == "poster.jpg");
            Assert.Equal(new byte[] { 1, 2, 3, 4 }, File.ReadAllBytes(_store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Poster)));
            Assert.Equal(_store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video), _extractor.InputPath);
            Assert.Equal("C:\\tools\\ffmpeg.exe", _extractor.FfmpegPath);
            Assert.Contains(outputPath, _tempFiles.DeleteAttempts);
        }

        [Fact]
        public async Task TryPublishPosterAsync_MissingFfmpegReturnsTypedSkip()
        {
            var artifact = GeneratedVideo();
            _resolver.Result = FfmpegBinaryResolution.Failed(
                FfmpegBinaryResolutionError.NotFound,
                "ffmpeg.exe was not found.");

            var producer = Producer();
            var result = await producer.TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.SkippedFfmpegMissing, result.Code);
            Assert.DoesNotContain(_store.Get(artifact.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
            Assert.Equal(0, _extractor.CallCount);
        }

        private Artifact GeneratedVideo() =>
            _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, new byte[] { 0, 1, 2 }, "mp4") });

        private VideoPosterSidecarProducer Producer() =>
            new(
                artifactStore: _store,
                publisher: new VideoSidecarPublisher(_store),
                resolver: _resolver,
                extractor: _extractor,
                tempFiles: _tempFiles,
                posterBytes: _posterBytes,
                extractionTimeout: TimeSpan.FromSeconds(5));

        private sealed class FakeFfmpegResolver : IVideoPosterFfmpegResolver
        {
            public FfmpegBinaryResolution Result { get; set; } =
                FfmpegBinaryResolution.Found("C:\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);

            public FfmpegBinaryResolution Resolve() => Result;
        }

        private sealed class FakePosterExtractor : IVideoPosterExtractor
        {
            public int CallCount { get; private set; }
            public string? FfmpegPath { get; private set; }
            public string? InputPath { get; private set; }
            public string? OutputPath { get; private set; }
            public FfmpegPosterExtractionResult Result { get; set; } =
                FfmpegPosterExtractionResult.Completed("cmd", 0, "", "poster.jpg", 10, 10, TimeSpan.Zero);

            public Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
                string ffmpegPath,
                string inputPath,
                string outputPath,
                TimeSpan timeout,
                CancellationToken cancellationToken)
            {
                CallCount++;
                FfmpegPath = ffmpegPath;
                InputPath = inputPath;
                OutputPath = outputPath;
                return Task.FromResult(Result);
            }
        }

        private sealed class FakeTempFiles : IVideoPosterTempFiles
        {
            private readonly string _defaultRoot;

            public FakeTempFiles(string defaultRoot)
            {
                _defaultRoot = defaultRoot;
            }

            public string? NextPath { get; set; }
            public List<string> DeleteAttempts { get; } = new();

            public string CreatePosterPath(Guid artifactId)
            {
                var path = NextPath ?? Path.Combine(_defaultRoot, $"{artifactId:D}.jpg");
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                return path;
            }

            public void DeleteIfExists(string path)
            {
                DeleteAttempts.Add(path);
                if (File.Exists(path))
                    File.Delete(path);
            }
        }

        private sealed class FakePosterBytes : IVideoPosterByteReader
        {
            public Dictionary<string, byte[]> BytesByPath { get; } = new();

            public byte[] ReadAllBytes(string path) => BytesByPath[path];
        }
    }
}
```

- [ ] **Step 2: Run the new tests and verify they fail because production types do not exist**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests" --no-restore
```

Expected: build fails with missing types such as `VideoPosterSidecarProducer`, `IVideoPosterFfmpegResolver`, `IVideoPosterExtractor`, `IVideoPosterTempFiles`, `IVideoPosterByteReader`, and `VideoPosterSidecarResultCode`.

- [ ] **Step 3: Add the minimal producer implementation for these two tests**

Create `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`:

```csharp
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.Video
{
    internal enum VideoPosterSidecarResultCode
    {
        Published,
        SkippedAlreadyExists,
        SkippedFfmpegMissing,
        TimedOut,
        ExtractionFailed,
        InvalidOutput,
        PublishFailed,
        VideoBlobUnavailable,
        TempPathUnavailable,
        PosterReadFailed,
        FinalizerFailed,
        CancelledAfterArtifactCreated,
    }

    internal sealed record VideoPosterSidecarResult(
        VideoPosterSidecarResultCode Code,
        Guid ArtifactId,
        string Message,
        string? Diagnostic = null)
    {
        public bool Success =>
            Code == VideoPosterSidecarResultCode.Published
            || Code == VideoPosterSidecarResultCode.SkippedAlreadyExists;

        public static VideoPosterSidecarResult From(
            VideoPosterSidecarResultCode code,
            Guid artifactId,
            string message,
            string? diagnostic = null) =>
            new(code, artifactId, message, Truncate(diagnostic));

        private static string? Truncate(string? value)
        {
            if (string.IsNullOrEmpty(value))
                return value;

            const int max = 2048;
            return value.Length <= max
                ? value
                : value.Substring(0, max);
        }
    }

    internal interface IVideoPosterSidecarProducer
    {
        Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Artifact artifact,
            CancellationToken cancellationToken);
    }

    internal interface IVideoPosterFfmpegResolver
    {
        FfmpegBinaryResolution Resolve();
    }

    internal sealed class DefaultVideoPosterFfmpegResolver : IVideoPosterFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve() => FfmpegBinaryResolver.Resolve();
    }

    internal interface IVideoPosterExtractor
    {
        Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
            string ffmpegPath,
            string inputPath,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken);
    }

    internal sealed class DefaultVideoPosterExtractor : IVideoPosterExtractor
    {
        private readonly FfmpegPosterFrameExtractor _extractor = new();

        public Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
            string ffmpegPath,
            string inputPath,
            string outputPath,
            TimeSpan timeout,
            CancellationToken cancellationToken) =>
            _extractor.ExtractPosterAsync(
                ffmpegPath,
                inputPath,
                outputPath,
                timeout,
                cancellationToken);
    }

    internal interface IVideoPosterTempFiles
    {
        string CreatePosterPath(Guid artifactId);
        void DeleteIfExists(string path);
    }

    internal sealed class DefaultVideoPosterTempFiles : IVideoPosterTempFiles
    {
        public string CreatePosterPath(Guid artifactId)
        {
            var root = Path.Combine(Path.GetTempPath(), "rook", "video-posters");
            Directory.CreateDirectory(root);
            return Path.Combine(root, $"{artifactId:D}-{Guid.NewGuid():N}.jpg");
        }

        public void DeleteIfExists(string path)
        {
            if (File.Exists(path))
                File.Delete(path);
        }
    }

    internal interface IVideoPosterByteReader
    {
        byte[] ReadAllBytes(string path);
    }

    internal sealed class DefaultVideoPosterByteReader : IVideoPosterByteReader
    {
        public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);
    }

    internal sealed class VideoPosterSidecarProducer : IVideoPosterSidecarProducer
    {
        private static readonly TimeSpan DefaultExtractionTimeout = TimeSpan.FromSeconds(15);

        private readonly ArtifactStore _artifactStore;
        private readonly VideoSidecarPublisher _publisher;
        private readonly IVideoPosterFfmpegResolver _resolver;
        private readonly IVideoPosterExtractor _extractor;
        private readonly IVideoPosterTempFiles _tempFiles;
        private readonly IVideoPosterByteReader _posterBytes;
        private readonly TimeSpan _extractionTimeout;

        public VideoPosterSidecarProducer(ArtifactStore artifactStore)
            : this(
                artifactStore,
                new VideoSidecarPublisher(artifactStore),
                new DefaultVideoPosterFfmpegResolver(),
                new DefaultVideoPosterExtractor(),
                new DefaultVideoPosterTempFiles(),
                new DefaultVideoPosterByteReader(),
                DefaultExtractionTimeout)
        {
        }

        internal VideoPosterSidecarProducer(
            ArtifactStore artifactStore,
            VideoSidecarPublisher publisher,
            IVideoPosterFfmpegResolver resolver,
            IVideoPosterExtractor extractor,
            IVideoPosterTempFiles tempFiles,
            IVideoPosterByteReader posterBytes,
            TimeSpan extractionTimeout)
        {
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _publisher = publisher ?? throw new ArgumentNullException(nameof(publisher));
            _resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
            _extractor = extractor ?? throw new ArgumentNullException(nameof(extractor));
            _tempFiles = tempFiles ?? throw new ArgumentNullException(nameof(tempFiles));
            _posterBytes = posterBytes ?? throw new ArgumentNullException(nameof(posterBytes));
            _extractionTimeout = extractionTimeout <= TimeSpan.Zero
                ? DefaultExtractionTimeout
                : extractionTimeout;
        }

        public async Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Artifact artifact,
            CancellationToken cancellationToken)
        {
            if (artifact is null)
                throw new ArgumentNullException(nameof(artifact));

            string? tempPath = null;
            try
            {
                var videoPath = _artifactStore.GetBlobAbsolutePath(
                    artifact.Id,
                    VideoMediaRoles.Video);

                var resolution = _resolver.Resolve();
                if (!resolution.Success)
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.SkippedFfmpegMissing,
                        artifact.Id,
                        resolution.Message);
                }

                tempPath = _tempFiles.CreatePosterPath(artifact.Id);
                var extraction = await _extractor.ExtractPosterAsync(
                    resolution.Path!,
                    videoPath,
                    tempPath,
                    _extractionTimeout,
                    cancellationToken).ConfigureAwait(false);

                if (!extraction.Success)
                {
                    return VideoPosterSidecarResult.From(
                        MapExtractionFailure(extraction.ErrorCode),
                        artifact.Id,
                        extraction.Message,
                        extraction.Stderr);
                }

                var bytes = _posterBytes.ReadAllBytes(tempPath);
                var published = _publisher.Publish(
                    artifact.Id,
                    VideoMediaRoles.Poster,
                    bytes,
                    "jpg");

                if (published.Code == VideoSidecarPublishResultCode.Succeeded)
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.Published,
                        artifact.Id,
                        "Published generated-video poster sidecar.");
                }

                if (published.Code == VideoSidecarPublishResultCode.SkippedAlreadyExists)
                {
                    return VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.SkippedAlreadyExists,
                        artifact.Id,
                        published.Message ?? "Generated-video poster sidecar already exists.");
                }

                return VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.PublishFailed,
                    artifact.Id,
                    published.Message ?? $"Poster sidecar publish failed with {published.Code}.");
            }
            finally
            {
                if (!string.IsNullOrEmpty(tempPath))
                    _tempFiles.DeleteIfExists(tempPath);
            }
        }

        private static VideoPosterSidecarResultCode MapExtractionFailure(
            FfmpegPosterExtractionError? errorCode) =>
            errorCode switch
            {
                FfmpegPosterExtractionError.TimedOut => VideoPosterSidecarResultCode.TimedOut,
                FfmpegPosterExtractionError.InvalidOutputImage => VideoPosterSidecarResultCode.InvalidOutput,
                _ => VideoPosterSidecarResultCode.ExtractionFailed,
            };
    }
}
```

- [ ] **Step 4: Run the producer tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests" --no-restore
```

Expected: the two new tests pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoPosterSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\VideoPosterSidecarProducerTests.cs
git commit -m "feat: add video poster sidecar producer"
```

Expected: commit succeeds.

---

### Task 2: Complete Producer Failure Semantics

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoPosterSidecarProducerTests.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`

- [ ] **Step 1: Add failing tests for all non-happy producer outcomes**

Append these tests and helper members to `VideoPosterSidecarProducerTests`:

```csharp
        [Fact]
        public async Task TryPublishPosterAsync_DuplicatePosterIsIdempotentSkip()
        {
            var artifact = GeneratedVideo();
            new VideoSidecarPublisher(_store).Publish(
                artifact.Id,
                VideoMediaRoles.Poster,
                new byte[] { 9 },
                "jpg");
            ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg"));

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.SkippedAlreadyExists, result.Code);
            Assert.True(result.Success);
            Assert.Single(_store.Get(artifact.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Theory]
        [InlineData(FfmpegPosterExtractionError.TimedOut, VideoPosterSidecarResultCode.TimedOut)]
        [InlineData(FfmpegPosterExtractionError.InvalidOutputImage, VideoPosterSidecarResultCode.InvalidOutput)]
        [InlineData(FfmpegPosterExtractionError.ProcessFailed, VideoPosterSidecarResultCode.ExtractionFailed)]
        [InlineData(FfmpegPosterExtractionError.OutputMissing, VideoPosterSidecarResultCode.ExtractionFailed)]
        public async Task TryPublishPosterAsync_ExtractionFailureMapsToTypedResult(
            FfmpegPosterExtractionError extractionError,
            VideoPosterSidecarResultCode expected)
        {
            var artifact = GeneratedVideo();
            var outputPath = Path.Combine(_root, "tmp", "poster.jpg");
            _resolver.Result = FfmpegBinaryResolution.Found("C:\\tools\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);
            _tempFiles.NextPath = outputPath;
            _extractor.Result = FfmpegPosterExtractionResult.Failed(
                "cmd",
                1,
                new string('x', 3000),
                outputPath,
                TimeSpan.FromMilliseconds(5),
                extractionError,
                "extract failed");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(expected, result.Code);
            Assert.NotNull(result.Diagnostic);
            Assert.True(result.Diagnostic!.Length <= 2048);
            Assert.DoesNotContain(_store.Get(artifact.Id)!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public async Task TryPublishPosterAsync_VideoBlobResolutionFailureReturnsTypedResult()
        {
            var image = _store.Create(
                "generated_video",
                new[] { new BlobInput("not_video", new byte[] { 1 }, "bin") });

            var result = await Producer().TryPublishPosterAsync(image, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.VideoBlobUnavailable, result.Code);
        }

        [Fact]
        public async Task TryPublishPosterAsync_TempPathFailureReturnsTypedResult()
        {
            var artifact = GeneratedVideo();
            _resolver.Result = FfmpegBinaryResolution.Found("C:\\tools\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);
            _tempFiles.ThrowOnCreate = new IOException("temp unavailable");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.TempPathUnavailable, result.Code);
        }

        [Fact]
        public async Task TryPublishPosterAsync_PosterReadFailureReturnsTypedResult()
        {
            var artifact = GeneratedVideo();
            ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg"));
            _posterBytes.ThrowOnRead = new IOException("read failed");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.PosterReadFailed, result.Code);
        }

        [Fact]
        public async Task TryPublishPosterAsync_CancellationAfterArtifactCreatedReturnsTypedResult()
        {
            var artifact = GeneratedVideo();
            _resolver.Result = FfmpegBinaryResolution.Found("C:\\tools\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);
            _tempFiles.NextPath = Path.Combine(_root, "tmp", "poster.jpg");
            _extractor.ThrowOnExtract = new OperationCanceledException("cancelled in poster stage");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.CancelledAfterArtifactCreated, result.Code);
        }

        [Fact]
        public async Task TryPublishPosterAsync_UnexpectedProducerExceptionReturnsFinalizerFailed()
        {
            var artifact = GeneratedVideo();
            _resolver.ThrowOnResolve = new InvalidOperationException("resolver crashed");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.FinalizerFailed, result.Code);
            Assert.Contains("resolver crashed", result.Message);
        }

        [Fact]
        public async Task TryPublishPosterAsync_CleanupFailureDoesNotOverridePublishedResult()
        {
            var artifact = GeneratedVideo();
            ConfigureSuccessfulExtraction(Path.Combine(_root, "tmp", "poster.jpg"));
            _tempFiles.ThrowOnDelete = new IOException("cleanup failed");

            var result = await Producer().TryPublishPosterAsync(artifact, CancellationToken.None);

            Assert.Equal(VideoPosterSidecarResultCode.Published, result.Code);
            Assert.Contains("cleanup failed", result.Diagnostic);
        }

        private void ConfigureSuccessfulExtraction(string outputPath)
        {
            _resolver.Result = FfmpegBinaryResolution.Found("C:\\tools\\ffmpeg.exe", FfmpegBinaryResolutionSource.ConfiguredPath);
            _tempFiles.NextPath = outputPath;
            _extractor.Result = FfmpegPosterExtractionResult.Completed(
                "ffmpeg command",
                0,
                "",
                outputPath,
                640,
                360,
                TimeSpan.FromMilliseconds(10));
            _posterBytes.BytesByPath[outputPath] = new byte[] { 5, 6, 7 };
        }
```

Replace the existing fake members from Task 1 with these expanded versions.
Do not add duplicate `Resolve`, `ExtractPosterAsync`, `CreatePosterPath`,
`DeleteIfExists`, or `ReadAllBytes` methods.

Replace `FakeFfmpegResolver.Resolve()` and add `ThrowOnResolve`:

```csharp
            public Exception? ThrowOnResolve { get; set; }

            public FfmpegBinaryResolution Resolve()
            {
                if (ThrowOnResolve is not null)
                    throw ThrowOnResolve;
                return Result;
            }
```

Replace `FakePosterExtractor.ExtractPosterAsync(...)` and add `ThrowOnExtract`:

```csharp
            public Exception? ThrowOnExtract { get; set; }

            public Task<FfmpegPosterExtractionResult> ExtractPosterAsync(
                string ffmpegPath,
                string inputPath,
                string outputPath,
                TimeSpan timeout,
                CancellationToken cancellationToken)
            {
                CallCount++;
                FfmpegPath = ffmpegPath;
                InputPath = inputPath;
                OutputPath = outputPath;
                if (ThrowOnExtract is not null)
                    throw ThrowOnExtract;
                return Task.FromResult(Result);
            }
```

Replace `FakeTempFiles.CreatePosterPath(...)` / `DeleteIfExists(...)` and add
`ThrowOnCreate` / `ThrowOnDelete`:

```csharp
            public Exception? ThrowOnCreate { get; set; }
            public Exception? ThrowOnDelete { get; set; }

            public string CreatePosterPath(Guid artifactId)
            {
                if (ThrowOnCreate is not null)
                    throw ThrowOnCreate;
                var path = NextPath ?? Path.Combine(_defaultRoot, $"{artifactId:D}.jpg");
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                return path;
            }

            public void DeleteIfExists(string path)
            {
                DeleteAttempts.Add(path);
                if (ThrowOnDelete is not null)
                    throw ThrowOnDelete;
                if (File.Exists(path))
                    File.Delete(path);
            }
```

Replace `FakePosterBytes.ReadAllBytes(...)` and add `ThrowOnRead`:

```csharp
            public Exception? ThrowOnRead { get; set; }

            public byte[] ReadAllBytes(string path)
            {
                if (ThrowOnRead is not null)
                    throw ThrowOnRead;
                return BytesByPath[path];
            }
```

- [ ] **Step 2: Run the producer tests and verify the new tests fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests" --no-restore
```

Expected: at least the local I/O, cancellation, and cleanup tests fail because Task 1 has not mapped those exceptions yet.

- [ ] **Step 3: Update the producer to catch and map all post-artifact outcomes**

Replace `TryPublishPosterAsync` and add helpers in `VideoPosterSidecarProducer`:

```csharp
        public async Task<VideoPosterSidecarResult> TryPublishPosterAsync(
            Artifact artifact,
            CancellationToken cancellationToken)
        {
            if (artifact is null)
                throw new ArgumentNullException(nameof(artifact));

            string? tempPath = null;
            try
            {
                string videoPath;
                try
                {
                    videoPath = _artifactStore.GetBlobAbsolutePath(
                        artifact.Id,
                        VideoMediaRoles.Video);
                }
                catch (Exception ex)
                {
                    return CleanupAndReturn(
                        null,
                        VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.VideoBlobUnavailable,
                        artifact.Id,
                        $"Could not resolve generated-video blob: {ex.Message}"));
                }

                var resolution = _resolver.Resolve();
                if (!resolution.Success)
                {
                    return CleanupAndReturn(
                        null,
                        VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.SkippedFfmpegMissing,
                        artifact.Id,
                        resolution.Message));
                }

                try
                {
                    tempPath = _tempFiles.CreatePosterPath(artifact.Id);
                }
                catch (Exception ex)
                {
                    return CleanupAndReturn(
                        null,
                        VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.TempPathUnavailable,
                        artifact.Id,
                        $"Could not create generated-video poster temp path: {ex.Message}"));
                }

                FfmpegPosterExtractionResult extraction;
                try
                {
                    extraction = await _extractor.ExtractPosterAsync(
                        resolution.Path!,
                        videoPath,
                        tempPath,
                        _extractionTimeout,
                        cancellationToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException ex)
                {
                    return CleanupAndReturn(
                        tempPath,
                        VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.CancelledAfterArtifactCreated,
                        artifact.Id,
                        "Poster extraction observed cancellation after the video artifact was saved.",
                        ex.Message));
                }

                if (!extraction.Success)
                {
                    return CleanupAndReturn(
                        tempPath,
                        VideoPosterSidecarResult.From(
                        MapExtractionFailure(extraction.ErrorCode),
                        artifact.Id,
                        extraction.Message,
                        extraction.Stderr));
                }

                byte[] bytes;
                try
                {
                    bytes = _posterBytes.ReadAllBytes(tempPath);
                }
                catch (Exception ex)
                {
                    return CleanupAndReturn(
                        tempPath,
                        VideoPosterSidecarResult.From(
                        VideoPosterSidecarResultCode.PosterReadFailed,
                        artifact.Id,
                        $"Could not read generated-video poster bytes: {ex.Message}"));
                }

                var published = _publisher.Publish(
                    artifact.Id,
                    VideoMediaRoles.Poster,
                    bytes,
                    "jpg");

                return CleanupAndReturn(
                    tempPath,
                    MapPublishResult(artifact.Id, published));
            }
            catch (OperationCanceledException ex)
            {
                return CleanupAndReturn(
                    tempPath,
                    VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.CancelledAfterArtifactCreated,
                    artifact.Id,
                    "Poster finalization observed cancellation after the video artifact was saved.",
                    ex.Message));
            }
            catch (Exception ex)
            {
                return CleanupAndReturn(
                    tempPath,
                    VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.FinalizerFailed,
                    artifact.Id,
                    $"Generated-video poster finalizer failed: {ex.Message}"));
            }
        }

        private VideoPosterSidecarResult CleanupAndReturn(
            string? tempPath,
            VideoPosterSidecarResult result)
        {
            if (string.IsNullOrEmpty(tempPath))
                return result;

            try
            {
                _tempFiles.DeleteIfExists(tempPath);
                return result;
            }
            catch (Exception ex)
            {
                return result with
                {
                    Diagnostic = AppendDiagnostic(result.Diagnostic, ex.Message),
                };
            }
        }

        private static VideoPosterSidecarResult MapPublishResult(
            Guid artifactId,
            VideoSidecarPublishResult published)
        {
            if (published.Code == VideoSidecarPublishResultCode.Succeeded)
            {
                return VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.Published,
                    artifactId,
                    "Published generated-video poster sidecar.");
            }

            if (published.Code == VideoSidecarPublishResultCode.SkippedAlreadyExists)
            {
                return VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.SkippedAlreadyExists,
                    artifactId,
                    published.Message ?? "Generated-video poster sidecar already exists.");
            }

            return VideoPosterSidecarResult.From(
                VideoPosterSidecarResultCode.PublishFailed,
                artifactId,
                published.Message ?? $"Poster sidecar publish failed with {published.Code}.");
        }

        private static string AppendDiagnostic(string? existing, string addition)
        {
            var combined = string.IsNullOrEmpty(existing)
                ? $"Cleanup failed: {addition}"
                : $"{existing}\nCleanup failed: {addition}";
            return combined.Length <= 2048 ? combined : combined.Substring(0, 2048);
        }
```

- [ ] **Step 4: Run producer tests and verify all pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests" --no-restore
```

Expected: all `VideoPosterSidecarProducerTests` pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoPosterSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\VideoPosterSidecarProducerTests.cs
git commit -m "test: cover video poster finalizer failures"
```

Expected: commit succeeds.

---

### Task 3: Wire Shared Video Finalization Into VideoJobManager

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoJobManager.cs`

- [ ] **Step 1: Add manager test seam and failing manager tests**

In `VideoJobManagerTests.Manager(...)`, add a new optional parameter:

```csharp
            IVideoPosterSidecarProducer? posterProducer = null
```

Pass it to the internal `VideoJobManager` constructor:

```csharp
                materializer: materializer,
                posterProducer: posterProducer);
```

Add this fake class near the other test helpers:

```csharp
        private sealed class FakePosterProducer : IVideoPosterSidecarProducer
        {
            public List<Guid> ArtifactIds { get; } = new();

            public Func<Artifact, CancellationToken, Task<VideoPosterSidecarResult>> OnPublishAsync { get; set; } =
                (artifact, _) => Task.FromResult(VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.Published,
                    artifact.Id,
                    "published"));

            public Task<VideoPosterSidecarResult> TryPublishPosterAsync(
                Artifact artifact,
                CancellationToken cancellationToken)
            {
                ArtifactIds.Add(artifact.Id);
                return OnPublishAsync(artifact, cancellationToken);
            }
        }
```

Add these tests near `Queued_job_completes_and_materializes_artifact`:

```csharp
        [Fact]
        public async Task Complete_video_publishes_poster_before_Complete_when_poster_succeeds()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var posterStarted = new TaskCompletionSource<Guid>(TaskCreationOptions.RunContinuationsAsynchronously);
            var releasePoster = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var poster = new FakePosterProducer();
            poster.OnPublishAsync = async (artifact, _) =>
            {
                posterStarted.SetResult(artifact.Id);
                await releasePoster.Task.ConfigureAwait(false);
                new VideoSidecarPublisher(_artifactStore).Publish(
                    artifact.Id,
                    VideoMediaRoles.Poster,
                    new byte[] { 8, 8, 8 },
                    "jpg");
                return VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.Published,
                    artifact.Id,
                    "published");
            };

            var mgr = Manager(posterProducer: poster);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            await WaitForSignalAsync(
                posterStarted.Task,
                "Poster producer was not reached.");
            var artifactId = await posterStarted.Task.ConfigureAwait(false);

            var duringPoster = await mgr.GetStatusAsync(jobId, CancellationToken.None);
            Assert.NotEqual(VideoJobState.Complete, duringPoster.State);
            Assert.DoesNotContain(_ledger.AllRecords, r => r.JobId == jobId && r.State == VideoJobState.Complete);
            Assert.Equal(VideoJobState.Saving, _ledger.AllRecords.Last(r => r.JobId == jobId).State);

            releasePoster.SetResult(true);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Contains(artifact!.Files, f => f.Role == VideoMediaRoles.Video);
            Assert.Contains(artifact.Files, f => f.Role == VideoMediaRoles.Poster);
            Assert.Equal(artifactId, artifact.Id);
            Assert.Equal(new[] { artifact.Id }, poster.ArtifactIds);
            Assert.Equal(VideoJobState.Complete, _ledger.AllRecords.Last(r => r.JobId == jobId).State);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_fails()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var poster = new FakePosterProducer
            {
                OnPublishAsync = (artifact, _) => Task.FromResult(VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.PublishFailed,
                    artifact.Id,
                    "publish failed"))
            };

            var mgr = Manager(posterProducer: poster);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            var artifact = _artifactStore.Get(final.ResultArtifactId!.Value);
            Assert.NotNull(artifact);
            Assert.Contains(artifact!.Files, f => f.Role == VideoMediaRoles.Video);
            Assert.DoesNotContain(artifact.Files, f => f.Role == VideoMediaRoles.Poster);
            Assert.DoesNotContain(_ledger.AllRecords, r => r.JobId == jobId && r.State == VideoJobState.Error);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_duplicate_is_skipped()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var poster = new FakePosterProducer
            {
                OnPublishAsync = (artifact, _) => Task.FromResult(VideoPosterSidecarResult.From(
                    VideoPosterSidecarResultCode.SkippedAlreadyExists,
                    artifact.Id,
                    "poster already exists"))
            };

            var mgr = Manager(posterProducer: poster);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.Single(poster.ArtifactIds);
            Assert.Equal(final.ResultArtifactId, poster.ArtifactIds[0]);
            Assert.DoesNotContain(_ledger.AllRecords, r => r.JobId == jobId && r.State == VideoJobState.Error);
            Assert.DoesNotContain(_ledger.AllRecords, r => r.JobId == jobId && r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Complete_video_still_completes_when_poster_stage_observes_cancellation()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            ConfigureProviderHappyPath();
            var poster = new FakePosterProducer
            {
                OnPublishAsync = (_, _) => throw new OperationCanceledException("poster cancelled")
            };

            var mgr = Manager(posterProducer: poster);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.NotNull(final.ResultArtifactId);
            Assert.DoesNotContain(_ledger.AllRecords, r => r.JobId == jobId && r.State == VideoJobState.Cancelled);
        }

        [Fact]
        public async Task Sync_submit_completion_uses_same_poster_finalization()
        {
            var jobId = Guid.NewGuid();
            _idGen.Sequence.Enqueue(jobId);
            _provider.OnSubmit = (_, _) =>
                new GenSyncSubmitOutcome(
                    new GenSuccessResultOutcome(
                        new GenProviderResultEnvelope(
                            new[]
                            {
                                new GenResultArtifact(
                                    Role: VideoMediaRoles.Video,
                                    Body: new GenInlineArtifactBody(FakeMp4),
                                    DeclaredMimeType: "video/mp4",
                                    ProviderMetadata: new Dictionary<string, JsonNode?>()),
                            },
                            new Dictionary<string, JsonNode?>())));
            var poster = new FakePosterProducer();

            var mgr = Manager(posterProducer: poster);
            await mgr.SubmitAsync(T2vRequest(), CancellationToken.None);
            var final = await WaitForTerminalAsync(mgr, jobId);

            Assert.Equal(VideoJobState.Complete, final.State);
            Assert.Single(poster.ArtifactIds);
            Assert.Equal(final.ResultArtifactId, poster.ArtifactIds[0]);
        }
```

- [ ] **Step 2: Run manager tests and verify they fail before production wiring**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoJobManagerTests" --no-restore
```

Expected: build fails because `VideoJobManager` does not accept `posterProducer`, or the new tests fail because the producer is not called.

- [ ] **Step 3: Update `VideoJobManager` constructor and fields**

In `VideoJobManager`, add the field:

```csharp
        private readonly IVideoPosterSidecarProducer _posterProducer;
```

Update the internal constructor signature:

```csharp
            int maxConcurrentJobs,
            VideoArtifactMaterializer? materializer,
            IVideoPosterSidecarProducer? posterProducer = null)
```

Initialize the field:

```csharp
            _posterProducer = posterProducer ?? new VideoPosterSidecarProducer(artifactStore);
```

Update the public constructor forwarding call:

```csharp
                maxConcurrentJobs,
                materializer: null,
                posterProducer: null)
```

- [ ] **Step 4: Extract shared save/poster/complete helper**

Add this helper below `CompleteSyncSubmitAsync`:

```csharp
        private async Task<VideoJobRecord> SaveGeneratedVideoAndCompleteAsync(
            VideoJobRecord current,
            RunningJob running,
            VideoGenerationRequest request,
            VideoArtifactMaterializationResult materialized)
        {
            var ext = ExtensionFromMime(materialized.MimeType!);
            var artifact = _artifactStore.Create(
                kind: "generated_video",
                blobs: new[] { new BlobInput(VideoMediaRoles.Video, materialized.Bytes!, ext) },
                parentIds: CollectMediaParents(request));

            try
            {
                await _posterProducer.TryPublishPosterAsync(
                    artifact,
                    CancellationToken.None).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                // Poster production after artifact creation is best-effort.
            }
            catch
            {
                // Poster production after artifact creation is best-effort.
            }

            current = AppendTransition(
                current,
                VideoJobState.Complete,
                resultArtifactId: artifact.Id);
            running.LatestRecord = current;
            return current;
        }
```

In both current completion paths, replace the duplicated `ArtifactStore.Create(...)` and `AppendTransition(... Complete ...)` block with:

```csharp
                    current = await SaveGeneratedVideoAndCompleteAsync(
                        current,
                        running,
                        request,
                        materialized).ConfigureAwait(false);
```

and:

```csharp
            current = await SaveGeneratedVideoAndCompleteAsync(
                current,
                running,
                request,
                materialized).ConfigureAwait(false);
```

- [ ] **Step 5: Run manager tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoJobManagerTests" --no-restore
```

Expected: all `VideoJobManagerTests` pass.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src\Rook\Services\Vision\Video\VideoJobManager.cs src\Rook.Tests\Services\Vision\Video\VideoJobManagerTests.cs
git commit -m "feat: publish video posters before completion"
```

Expected: commit succeeds.

---

### Task 4: Preserve UI Contract And Focused Verification

**Files:**
- Read: `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
- Read: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Confirm existing UI source tests cover Slice 3 UI boundaries**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VisionVideoSidecarContractSourceTests" --no-restore
```

Expected: tests pass and continue to pin:

```csharp
Assert.Contains("const posterRole = isVideo", js);
Assert.Contains("f.role === \"poster\"", js);
Assert.Contains("<img src=\"${posterUrl}\" alt=\"Video poster\">", js);
Assert.DoesNotContain("\"poster\"", generatedVideoBranch);
Assert.DoesNotContain("\"video\"", generatedVideoBranch);
```

- [ ] **Step 2: Run the full focused Slice 3 managed test set**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoSidecarPublisherTests|FullyQualifiedName~FfmpegPosterFrameExtractorTests|FullyQualifiedName~VisionVideoSidecarContractSourceTests" --no-restore
```

Expected: all selected tests pass.

- [ ] **Step 3: Run formatting/whitespace verification**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit verification-only source test adjustments only if any were needed**

If no files changed in this task, do not create a commit.

If a UI source test needed a narrow assertion update, run:

```powershell
git add src\Rook.Tests\UI\Vision\VisionVideoSidecarContractSourceTests.cs
git commit -m "test: preserve video poster ui contract"
```

Expected when a commit is needed: commit succeeds.

---

### Task 5: Update Roadmap And Work Queue After Implementation Passes

**Files:**
- Modify: `docs/rook_docs/video-thumbnail-roadmap.md`
- Modify: `docs/rook_docs/work-queue.md`

- [ ] **Step 1: Update roadmap Slice 3 status**

In `docs/rook_docs/video-thumbnail-roadmap.md`, change the current state text so Slice 3 is done and Slice 4 is current next. Update the table rows to:

```markdown
| 3. Poster thumbnail producer | Done | Produce display-only `poster` from the local MP4 for completed generated videos. | New completed videos show Gallery thumbnails without eager MP4 preload; video generation still succeeds if poster extraction fails; `poster` remains picker-ineligible. |
| 4. Frame-exact sidecar producer | Next | Produce `start_frame` and `end_frame` from the local MP4 for completed generated videos. | Generated videos expose distinct role-level picker choices for frame sidecars; extracted frames are not confused with posters. |
```

Set the "Current next slice" section to:

```markdown
Current next slice:

- Produce frame-exact `start_frame` and `end_frame` sidecars from the local MP4 for completed generated videos.
```

- [ ] **Step 2: Update work queue top triage entry**

At the top of `docs/rook_docs/work-queue.md`, prepend a new `Last triaged` entry dated `2026-05-12` with this content:

```markdown
**Last triaged:** 2026-05-12 (**RookVision video thumbnail Slice 3 complete.** Newly completed generated-video artifacts now attempt synchronous best-effort `poster` sidecar creation after the MP4 artifact is durably saved and before the video job appends `Complete`. `ArtifactStore.Create(generated_video/video)` remains the durable success boundary: missing ffmpeg, extraction failure, invalid output, sidecar publish failure, post-artifact local I/O failure, cleanup failure, unexpected poster finalizer failure, and poster-stage cancellation cannot convert the saved video into `Error` or `Cancelled`. Poster publication uses `VideoSidecarPublisher`; duplicate posters remain idempotent no-ops; Gallery consumes `poster` when present without eager MP4 preload; and generated-video frame picker eligibility remains limited to future `start_frame` / `end_frame` roles. **Promoted to Now:** Slice 4 frame-exact `start_frame` / `end_frame` sidecar producer. **Do not skip ahead** to existing-video backfill, provider-payload poster ingestion, installer ffmpeg packaging, or GH NLE token work until Slice 4 gates are satisfied.)
```

- [ ] **Step 3: Run docs checks**

Run:

```powershell
git diff --check -- docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit docs update**

Run:

```powershell
git add docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
git commit -m "docs: advance video thumbnail roadmap to frame sidecars"
```

Expected: commit succeeds.

---

### Task 6: Final Verification

**Files:**
- No source edits.

- [ ] **Step 1: Run focused Slice 3 suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --filter "FullyQualifiedName~VideoPosterSidecarProducerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoSidecarPublisherTests|FullyQualifiedName~FfmpegPosterFrameExtractorTests|FullyQualifiedName~VisionVideoSidecarContractSourceTests" --no-restore
```

Expected: all selected tests pass.

- [ ] **Step 2: Run managed test project if time allows**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net7.0 --no-restore
```

Expected: all tests pass. If this is too slow or blocked by local environment issues, capture the exact failure and run the focused suite from Step 1.

- [ ] **Step 3: Run build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore
```

Expected: build succeeds. Existing warnings are acceptable only if they predate this work and are not caused by the edited files.

- [ ] **Step 4: Run final diff checks**

Run:

```powershell
git status --short
git diff --check
```

Expected: `git status --short` shows only intentional uncommitted changes, or no changes if every task was committed. `git diff --check` has no output and exits 0.

- [ ] **Step 5: Report verification**

In the final implementation summary, report:

- producer tests result;
- manager tests result;
- UI source contract test result;
- focused Slice 3 suite result;
- full managed suite/build result or exact reason it was not run.
