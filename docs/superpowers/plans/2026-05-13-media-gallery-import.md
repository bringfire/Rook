# RookVision Media Gallery Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable, artifact-backed local image/video ingestion through the RookVision Gallery.

**Architecture:** Add file-backed artifact publishing, a bridge-only managed media import job subsystem, and UI flows that import local media through Gallery before using it as source material. Imported media is stored as `imported_image` / `imported_video` artifacts, and generation/pickers consume artifact refs rather than local paths.

**Tech Stack:** C# `net7.0;net48`, xUnit, `System.Text.Json.Nodes`, Eto file picker, existing `ArtifactStore`, existing RookVision bridge, existing FFmpeg sidecar extraction helpers, HTML/CSS/vanilla JS.

---

## File Structure

Create these managed files:

- `src/Rook/Services/Vision/MediaImport/MediaImportConstants.cs`
  Shared import kinds, role names, format lists, limits, and retention caps.
- `src/Rook/Services/Vision/MediaImport/MediaImportModels.cs`
  Job/item states, failure codes, job snapshots, item snapshots, start/list results, prepared artifact inputs.
- `src/Rook/Services/Vision/MediaImport/IMediaImportProcessor.cs`
  Processor interface used by the job manager tests.
- `src/Rook/Services/Vision/MediaImport/MediaImportJobManager.cs`
  In-memory bounded async job manager. No UI and no Eto dependency.
- `src/Rook/Services/Vision/MediaImport/MediaImportProcessor.cs`
  Chooses image vs video importer and publishes one complete artifact.
- `src/Rook/Services/Vision/MediaImport/ImageMediaImporter.cs`
  Image validation, decode, metadata, and file-backed prepared artifact input.
- `src/Rook/Services/Vision/MediaImport/VideoMediaImporter.cs`
  Video validation, FFmpeg probe/extraction orchestration, metadata, and prepared sidecar files.
- `src/Rook/Services/Vision/MediaImport/FfmpegVideoProbe.cs`
  FFmpeg metadata probe using the existing FFmpeg binary resolver and process runner.
- `src/Rook/Services/Vision/MediaImport/MediaImportSubsystemFactory.cs`
  Composition helper for production `MediaImportJobManager`.
- `src/Rook/Handlers/MediaImportOpHandler.cs`
  Bridge-only op handler for `start_media_import`, `get_media_import_job`, and `list_media_import_jobs`.
- `src/Rook/Services/Vision/Image/ArtifactImageMediaResolver.cs`
  Artifact/path media resolver for image generation, preserving legacy path support but allowing UI artifact refs.

Modify these managed files:

- `src/Rook/Artifacts/Artifact.cs`
  Add `BlobFileInput`.
- `src/Rook/Artifacts/ArtifactStore.cs`
  Add staged file-backed `CreateFromFiles`.
- `src/Rook/RookSubsystemRoot.cs`
  Add lazy shared media import subsystem.
- `src/Rook/UI/Vision/VisionWebSurface.cs`
  Route media import ops to `MediaImportOpHandler`.
- `src/Rook/Handlers/VisionHandler.cs`
  Parse image artifact refs for sync image generation and record parent IDs.
- `src/Rook/Handlers/ImageJobOpHandler.cs`
  Reuse the same image artifact-ref parsing through `VisionHandler.BuildImageGenerationWorkItem`.

Modify these UI files:

- `src/Rook/UI/Vision/Resources/index.html`
  Gallery toolbar import button and import status panel.
- `src/Rook/UI/Vision/Resources/app.js`
  Import job UI, Gallery imported kinds, picker imported kinds, image source artifact refs.
- `src/Rook/UI/Vision/Resources/styles.css`
  Import status rows and toolbar layout.

Create these tests:

- `src/Rook.Tests/Services/Vision/MediaImport/MediaImportJobManagerTests.cs`
- `src/Rook.Tests/Services/Vision/MediaImport/ImageMediaImporterTests.cs`
- `src/Rook.Tests/Services/Vision/MediaImport/VideoMediaImporterTests.cs`
- `src/Rook.Tests/Services/Vision/Image/ArtifactImageMediaResolverTests.cs`
- `src/Rook.Tests/Handlers/MediaImportOpHandlerTests.cs`

Modify these tests:

- `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
- `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`

## Implementation Notes

Use these fixed v1 limits unless a failing test exposes a platform constraint:

- `MaxBatchFiles = 20`
- `MaxImageBytes = 50L * 1024 * 1024`
- `MaxVideoBytes = 2L * 1024 * 1024 * 1024`
- `RecentJobLimit = 50`
- `VideoImportConcurrency = 1`

Import ops stay bridge-only. Do not add native C++ route wiring, MCP tools, or native allowlist entries.

## Task 1: File-Backed Artifact Publishing

**Files:**
- Modify: `src/Rook/Artifacts/Artifact.cs`
- Modify: `src/Rook/Artifacts/ArtifactStore.cs`
- Modify: `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`

- [ ] **Step 1: Add failing tests for file-backed artifact creation**

Append these tests to `ArtifactStoreTests` near the existing create tests:

```csharp
[Fact]
public void CreateFromFiles_CopiesRoleNamedFiles_AndPreservesSource()
{
    var sourceDir = Path.Combine(_root, "sources");
    Directory.CreateDirectory(sourceDir);
    var imageSource = Path.Combine(sourceDir, "Original Name.PNG");
    File.WriteAllText(imageSource, "image-bytes");

    var artifact = _store.CreateFromFiles(
        "imported_image",
        new[] { new BlobFileInput("image", imageSource, "png") },
        metadata: new Dictionary<string, JsonNode?>
        {
            ["original_filename"] = JsonValue.Create("Original Name.PNG"),
        });

    Assert.Equal("imported_image", artifact.Kind);
    Assert.Contains(artifact.Files, f => f.Role == "image" && f.Path == "image.png");
    Assert.Equal("image-bytes", File.ReadAllText(BlobPath(artifact.Id, "image.png")));
    Assert.Equal("image-bytes", File.ReadAllText(imageSource));
    Assert.Equal(
        "Original Name.PNG",
        artifact.Metadata["original_filename"]!.GetValue<string>());
}

[Fact]
public void CreateFromFiles_RejectsDirectorySource_AndPublishesNothing()
{
    var sourceDir = Path.Combine(_root, "source-directory");
    Directory.CreateDirectory(sourceDir);

    Assert.Throws<ArgumentException>(() => _store.CreateFromFiles(
        "imported_image",
        new[] { new BlobFileInput("image", sourceDir, "png") }));

    Assert.Empty(_store.List());
}

[Fact]
public void CreateFromFiles_UsesFlatRoleFilenames_NotOriginalNames()
{
    var sourceDir = Path.Combine(_root, "sources");
    Directory.CreateDirectory(sourceDir);
    var videoSource = Path.Combine(sourceDir, "phone clip.mov");
    File.WriteAllText(videoSource, "movie");

    var artifact = _store.CreateFromFiles(
        "imported_video",
        new[] { new BlobFileInput("video", videoSource, "mov") });

    Assert.Contains(artifact.Files, f => f.Role == "video" && f.Path == "video.mov");
    Assert.DoesNotContain(artifact.Files, f => f.Path == "phone clip.mov");
    Assert.Equal("movie", File.ReadAllText(BlobPath(artifact.Id, "video.mov")));
}
```

- [ ] **Step 2: Run failing artifact tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Artifacts.ArtifactStoreTests.CreateFromFiles" -v minimal
```

Expected: fails because `BlobFileInput` and `CreateFromFiles` do not exist.

- [ ] **Step 3: Add `BlobFileInput`**

In `src/Rook/Artifacts/Artifact.cs`, add this record after `BlobInput`:

```csharp
/// <summary>
/// Caller input for one file-backed blob during artifact creation.
/// <see cref="SourcePath"/> is copied into the staged artifact directory;
/// the original file is never moved or deleted.
/// </summary>
public sealed record BlobFileInput(
    string Role,
    string SourcePath,
    string FileExtension);

public sealed class ArtifactBlobCopyException : IOException
{
    public ArtifactBlobCopyException(string role, string sourcePath, string destinationPath, Exception innerException)
        : base($"Artifact blob '{role}' could not be copied.", innerException)
    {
        Role = role;
        SourcePath = sourcePath;
        DestinationPath = destinationPath;
    }

    public string Role { get; }
    public string SourcePath { get; }
    public string DestinationPath { get; }
}
```

- [ ] **Step 4: Implement `CreateFromFiles`**

In `ArtifactStore`, add a public method beside `Create`. The implementation mirrors `Create` but uses `File.Copy`:

```csharp
public Artifact CreateFromFiles(
    string kind,
    IReadOnlyList<BlobFileInput> files,
    IReadOnlyList<Guid>? parentIds = null,
    IReadOnlyDictionary<string, JsonNode?>? metadata = null,
    IReadOnlyDictionary<string, JsonNode?>? flags = null)
{
    ValidateKindArg(kind);
    ValidateFileInputsArg(files);

    var id = Guid.NewGuid();
    var now = DateTimeOffset.UtcNow;
    var dayKey = now.ToString(DayKeyFormat, CultureInfo.InvariantCulture);
    var dayDir = Path.Combine(_root, dayKey);
    var idStr = id.ToString("D");
    var finalDir = Path.Combine(dayDir, idStr);
    var tmpDir = finalDir + TempDirSuffix;

    var artifactFiles = files
        .Select(f => new ArtifactFile(f.Role, $"{f.Role}.{f.FileExtension}"))
        .ToList();

    var artifact = new Artifact(
        Id: id,
        Kind: kind,
        CreatedAt: now,
        Files: artifactFiles,
        ParentIds: parentIds is null ? Array.Empty<Guid>() : new List<Guid>(parentIds),
        Metadata: CloneOrEmpty(metadata),
        Flags: CloneOrEmpty(flags));

    Directory.CreateDirectory(dayDir);
    try
    {
        Directory.CreateDirectory(tmpDir);
        foreach (var file in files)
        {
            var destination = Path.Combine(tmpDir, $"{file.Role}.{file.FileExtension}");
            try
            {
                File.Copy(file.SourcePath, destination, overwrite: false);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException)
            {
                throw new ArtifactBlobCopyException(file.Role, file.SourcePath, destination, ex);
            }
        }

        var manifestPath = Path.Combine(tmpDir, ManifestFileName);
        File.WriteAllText(manifestPath, SerializeManifest(artifact));
        Directory.Move(tmpDir, finalDir);
        return artifact;
    }
    catch
    {
        try
        {
            if (Directory.Exists(tmpDir))
                Directory.Delete(tmpDir, recursive: true);
        }
        catch { }

        throw;
    }
}
```

Add this validator near `ValidateBlobsArg`:

```csharp
private static void ValidateFileInputsArg(IReadOnlyList<BlobFileInput> files)
{
    if (files is null) throw new ArgumentNullException(nameof(files));
    if (files.Count == 0) throw new ArgumentException("At least one file is required.", nameof(files));

    var roles = new HashSet<string>(StringComparer.Ordinal);
    foreach (var file in files)
    {
        if (file is null) throw new ArgumentException("File input cannot contain null entries.", nameof(files));
        ValidateRoleArg(file.Role);
        ValidateExtensionArg(file.FileExtension);
        if (!roles.Add(file.Role))
            throw new ArgumentException($"Duplicate blob role '{file.Role}'.", nameof(files));
        if (string.IsNullOrWhiteSpace(file.SourcePath))
            throw new ArgumentException("SourcePath must be non-empty.", nameof(files));
        FileAttributes attrs;
        try
        {
            attrs = File.GetAttributes(file.SourcePath);
        }
        catch (FileNotFoundException)
        {
            throw new FileNotFoundException($"Source file not found: {file.SourcePath}", file.SourcePath);
        }
        catch (DirectoryNotFoundException)
        {
            throw new FileNotFoundException($"Source file not found: {file.SourcePath}", file.SourcePath);
        }
        if ((attrs & FileAttributes.Directory) != 0)
            throw new ArgumentException($"Source path is not a regular file: {file.SourcePath}", nameof(files));
        if (!File.Exists(file.SourcePath))
            throw new FileNotFoundException($"Source file not found: {file.SourcePath}", file.SourcePath);
    }
}
```

- [ ] **Step 5: Run artifact tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Artifacts.ArtifactStoreTests" -v minimal
```

Expected: all `ArtifactStoreTests` pass.

- [ ] **Step 6: Commit artifact publishing**

```powershell
git add src\Rook\Artifacts\Artifact.cs src\Rook\Artifacts\ArtifactStore.cs src\Rook.Tests\Artifacts\ArtifactStoreTests.cs
git commit -m "feat(vision): add file-backed artifact creation"
```

## Task 2: Media Import Domain And Job Manager

**Files:**
- Create: `src/Rook/Services/Vision/MediaImport/MediaImportConstants.cs`
- Create: `src/Rook/Services/Vision/MediaImport/MediaImportModels.cs`
- Create: `src/Rook/Services/Vision/MediaImport/IMediaImportProcessor.cs`
- Create: `src/Rook/Services/Vision/MediaImport/MediaImportJobManager.cs`
- Create: `src/Rook.Tests/Services/Vision/MediaImport/MediaImportJobManagerTests.cs`

- [ ] **Step 1: Write failing job manager tests**

Create `MediaImportJobManagerTests.cs` with tests for server-side cap, basename-only snapshots, independent failures, sequential processing, and retention:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public class MediaImportJobManagerTests
    {
        [Fact]
        public async Task StartAsync_RejectsMoreThanTwentyFiles_AndCreatesNoJob()
        {
            var processor = new FakeProcessor();
            var manager = new MediaImportJobManager(processor);
            var paths = Enumerable.Range(0, 21)
                .Select(i => $@"C:\media\file-{i}.png")
                .ToArray();

            var result = await manager.StartAsync(paths, CancellationToken.None);

            Assert.False(result.Created);
            Assert.Equal(MediaImportStartFailureCode.TooManyFiles, result.FailureCode);
            Assert.Null(result.Job);
            Assert.Empty(manager.ListJobs().Jobs);
        }

        [Fact]
        public async Task StartAsync_EmptySelection_ReturnsNeutralNoJob()
        {
            var manager = new MediaImportJobManager(new FakeProcessor());

            var result = await manager.StartAsync(Array.Empty<string>(), CancellationToken.None);

            Assert.False(result.Created);
            Assert.Equal(MediaImportStartFailureCode.EmptySelection, result.FailureCode);
            Assert.Null(result.Job);
        }

        [Fact]
        public async Task StartAsync_ReturnsBasenames_NotFullPaths()
        {
            var processor = new FakeProcessor();
            var manager = new MediaImportJobManager(processor);

            var result = await manager.StartAsync(
                new[] { @"C:\secret\family\clip.mp4" },
                CancellationToken.None);

            Assert.True(result.Created);
            var item = Assert.Single(result.Job!.Items);
            Assert.Equal("clip.mp4", item.Basename);
            Assert.DoesNotContain("secret", item.Basename, StringComparison.OrdinalIgnoreCase);
            Assert.Null(item.ArtifactId);
        }

        [Fact]
        public async Task Processing_IsSequential_AndKeepsSuccessfulItemsWhenAnotherFails()
        {
            var processor = new FakeProcessor
            {
                Delay = TimeSpan.FromMilliseconds(20),
                Results =
                {
                    [@"C:\media\a.png"] = MediaImportProcessResult.Success(Guid.Parse("11111111-1111-1111-1111-111111111111"), "imported_image"),
                    [@"C:\media\b.mov"] = MediaImportProcessResult.Failed(MediaImportFailureCode.VideoProbeFailed, "Could not probe video."),
                },
            };
            var manager = new MediaImportJobManager(processor);

            var start = await manager.StartAsync(
                new[] { @"C:\media\a.png", @"C:\media\b.mov" },
                CancellationToken.None);

            await WaitForTerminal(manager, start.Job!.JobId);

            Assert.Equal(1, processor.MaxConcurrentObserved);
            var job = manager.GetJob(start.Job.JobId)!;
            Assert.Equal(MediaImportJobState.Complete, job.State);
            Assert.Contains(job.Items, i => i.State == MediaImportItemState.Imported && i.ArtifactId.HasValue);
            Assert.Contains(job.Items, i => i.State == MediaImportItemState.Failed && i.FailureCode == MediaImportFailureCode.VideoProbeFailed);
        }

        [Fact]
        public async Task ListJobs_DropsOldTerminalJobsBeyondRetentionLimit()
        {
            var manager = new MediaImportJobManager(new FakeProcessor(), recentJobLimit: 2);
            var a = await manager.StartAsync(new[] { @"C:\media\a.png" }, CancellationToken.None);
            var b = await manager.StartAsync(new[] { @"C:\media\b.png" }, CancellationToken.None);
            var c = await manager.StartAsync(new[] { @"C:\media\c.png" }, CancellationToken.None);

            await WaitForTerminal(manager, c.Job!.JobId);
            await Task.Delay(20);

            var jobs = manager.ListJobs().Jobs;
            Assert.Equal(2, jobs.Count);
            Assert.DoesNotContain(jobs, j => j.JobId == a.Job!.JobId);
            Assert.Contains(jobs, j => j.JobId == b.Job!.JobId);
            Assert.Contains(jobs, j => j.JobId == c.Job!.JobId);
        }

        private static async Task WaitForTerminal(MediaImportJobManager manager, Guid jobId)
        {
            for (var i = 0; i < 100; i++)
            {
                var job = manager.GetJob(jobId);
                if (job is not null && job.State == MediaImportJobState.Complete)
                    return;
                await Task.Delay(10);
            }
            throw new TimeoutException("Import job did not finish.");
        }

        private sealed class FakeProcessor : IMediaImportProcessor
        {
            private int _active;
            public int MaxConcurrentObserved { get; private set; }
            public TimeSpan Delay { get; set; }
            public Dictionary<string, MediaImportProcessResult> Results { get; } = new(StringComparer.OrdinalIgnoreCase);

            public async Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct)
            {
                var active = Interlocked.Increment(ref _active);
                MaxConcurrentObserved = Math.Max(MaxConcurrentObserved, active);
                try
                {
                    if (Delay > TimeSpan.Zero)
                        await Task.Delay(Delay, ct);
                    if (Results.TryGetValue(path, out var result))
                        return result;
                    return MediaImportProcessResult.Success(Guid.NewGuid(), "imported_image");
                }
                finally
                {
                    Interlocked.Decrement(ref _active);
                }
            }
        }
    }
}
```

- [ ] **Step 2: Run failing manager tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.MediaImportJobManagerTests" -v minimal
```

Expected: fails because media import types do not exist.

- [ ] **Step 3: Add constants and models**

Create `MediaImportConstants.cs`:

```csharp
namespace Rook.Services.Vision.MediaImport
{
    internal static class MediaImportConstants
    {
        public const string ImportedImageKind = "imported_image";
        public const string ImportedVideoKind = "imported_video";
        public const int MaxBatchFiles = 20;
        public const int RecentJobLimit = 50;
        public const int VideoImportConcurrency = 1;
        public const long MaxImageBytes = 50L * 1024 * 1024;
        public const long MaxVideoBytes = 2L * 1024 * 1024 * 1024;
    }
}
```

Create `MediaImportModels.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.MediaImport
{
    public enum MediaImportFailureCode
    {
        UnsupportedMediaType,
        FileNotFound,
        NotRegularFile,
        FileInaccessible,
        FileTooLarge,
        DecodeFailed,
        VideoProbeFailed,
        SidecarExtractionFailed,
        CopyFailed,
        PublishFailed,
    }

    public enum MediaImportStartFailureCode
    {
        EmptySelection,
        TooManyFiles,
    }

    public enum MediaImportItemState
    {
        Queued,
        Copying,
        Probing,
        ExtractingSidecars,
        Publishing,
        Imported,
        Failed,
    }

    public enum MediaImportJobState
    {
        Queued,
        Running,
        Complete,
    }

    public sealed record MediaImportItemSnapshot(
        Guid ImportItemId,
        string Basename,
        MediaImportItemState State,
        Guid? ArtifactId,
        string? ArtifactKind,
        MediaImportFailureCode? FailureCode,
        string? Message);

    public sealed record MediaImportJobSnapshot(
        Guid JobId,
        MediaImportJobState State,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt,
        IReadOnlyList<MediaImportItemSnapshot> Items);

    public sealed record MediaImportStartResult(
        bool Created,
        MediaImportJobSnapshot? Job,
        MediaImportStartFailureCode? FailureCode,
        string? Message);

    public sealed record MediaImportJobListResult(IReadOnlyList<MediaImportJobSnapshot> Jobs);

    public sealed record MediaImportProcessResult(
        bool Success,
        Guid? ArtifactId,
        string? ArtifactKind,
        MediaImportFailureCode? FailureCode,
        string? Message)
    {
        public static MediaImportProcessResult Success(Guid artifactId, string artifactKind) =>
            new(true, artifactId, artifactKind, null, null);

        public static MediaImportProcessResult Failed(MediaImportFailureCode code, string message) =>
            new(false, null, null, code, message);
    }
}
```

Create `IMediaImportProcessor.cs`:

```csharp
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.MediaImport
{
    public interface IMediaImportProcessor
    {
        Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct);
    }
}
```

- [ ] **Step 4: Implement `MediaImportJobManager`**

Create `MediaImportJobManager.cs` with a lock-protected in-memory job list and sequential background processing:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class MediaImportJobManager
    {
        private readonly IMediaImportProcessor _processor;
        private readonly int _recentJobLimit;
        private readonly object _gate = new();
        private readonly List<JobState> _jobs = new();

        public MediaImportJobManager(
            IMediaImportProcessor processor,
            int recentJobLimit = MediaImportConstants.RecentJobLimit)
        {
            _processor = processor ?? throw new ArgumentNullException(nameof(processor));
            _recentJobLimit = recentJobLimit <= 0 ? MediaImportConstants.RecentJobLimit : recentJobLimit;
        }

        public Task<MediaImportStartResult> StartAsync(
            IReadOnlyList<string> paths,
            CancellationToken ct)
        {
            if (paths is null || paths.Count == 0)
            {
                return Task.FromResult(new MediaImportStartResult(
                    false, null, MediaImportStartFailureCode.EmptySelection, "No files selected."));
            }
            if (paths.Count > MediaImportConstants.MaxBatchFiles)
            {
                return Task.FromResult(new MediaImportStartResult(
                    false, null, MediaImportStartFailureCode.TooManyFiles,
                    $"Select {MediaImportConstants.MaxBatchFiles} files or fewer."));
            }

            var now = DateTimeOffset.UtcNow;
            var job = new JobState(
                Guid.NewGuid(),
                MediaImportJobState.Queued,
                now,
                now,
                paths.Select(p => new ItemState(Guid.NewGuid(), p)).ToList());

            lock (_gate)
            {
                _jobs.Add(job);
                TrimLocked();
            }

            _ = Task.Run(() => ProcessJobAsync(job.JobId, CancellationToken.None));
            return Task.FromResult(new MediaImportStartResult(true, Snapshot(job), null, null));
        }

        public MediaImportJobSnapshot? GetJob(Guid jobId)
        {
            lock (_gate)
            {
                var job = _jobs.FirstOrDefault(j => j.JobId == jobId);
                return job is null ? null : Snapshot(job);
            }
        }

        public MediaImportJobListResult ListJobs()
        {
            lock (_gate)
            {
                return new MediaImportJobListResult(
                    _jobs.OrderByDescending(j => j.CreatedAt).Select(Snapshot).ToList());
            }
        }

        private async Task ProcessJobAsync(Guid jobId, CancellationToken ct)
        {
            SetJobState(jobId, MediaImportJobState.Running);
            List<ItemState> items;
            lock (_gate)
            {
                items = _jobs.First(j => j.JobId == jobId).Items.ToList();
            }

            foreach (var item in items)
            {
                SetItemState(jobId, item.ImportItemId, MediaImportItemState.Copying, null);
                MediaImportProcessResult result;
                try
                {
                    result = await _processor.ProcessAsync(item.Path, ct).ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    result = MediaImportProcessResult.Failed(
                        MediaImportFailureCode.PublishFailed,
                        $"Import failed unexpectedly: {ex.Message}");
                }

                lock (_gate)
                {
                    var live = _jobs.First(j => j.JobId == jobId);
                    var liveItem = live.Items.First(i => i.ImportItemId == item.ImportItemId);
                    live.UpdatedAt = DateTimeOffset.UtcNow;
                    if (result.Success)
                    {
                        liveItem.State = MediaImportItemState.Imported;
                        liveItem.ArtifactId = result.ArtifactId;
                        liveItem.ArtifactKind = result.ArtifactKind;
                        liveItem.Message = "Imported.";
                    }
                    else
                    {
                        liveItem.State = MediaImportItemState.Failed;
                        liveItem.FailureCode = result.FailureCode;
                        liveItem.Message = result.Message;
                    }
                }
            }
            SetJobState(jobId, MediaImportJobState.Complete);
        }

        private void SetJobState(Guid jobId, MediaImportJobState state)
        {
            lock (_gate)
            {
                var job = _jobs.First(j => j.JobId == jobId);
                job.State = state;
                job.UpdatedAt = DateTimeOffset.UtcNow;
                TrimLocked();
            }
        }

        private void SetItemState(Guid jobId, Guid itemId, MediaImportItemState state, string? message)
        {
            lock (_gate)
            {
                var job = _jobs.First(j => j.JobId == jobId);
                var item = job.Items.First(i => i.ImportItemId == itemId);
                item.State = state;
                item.Message = message;
                job.UpdatedAt = DateTimeOffset.UtcNow;
            }
        }

        private void TrimLocked()
        {
            while (_jobs.Count > _recentJobLimit)
            {
                var terminal = _jobs
                    .Where(j => j.State == MediaImportJobState.Complete)
                    .OrderBy(j => j.UpdatedAt)
                    .FirstOrDefault();
                if (terminal is null) return;
                _jobs.Remove(terminal);
            }
        }

        private static MediaImportJobSnapshot Snapshot(JobState job) =>
            new(
                job.JobId,
                job.State,
                job.CreatedAt,
                job.UpdatedAt,
                job.Items.Select(i => new MediaImportItemSnapshot(
                    i.ImportItemId,
                    Path.GetFileName(i.Path),
                    i.State,
                    i.ArtifactId,
                    i.ArtifactKind,
                    i.FailureCode,
                    i.Message)).ToList());

        private sealed class JobState
        {
            public JobState(Guid jobId, MediaImportJobState state, DateTimeOffset createdAt, DateTimeOffset updatedAt, List<ItemState> items)
            {
                JobId = jobId;
                State = state;
                CreatedAt = createdAt;
                UpdatedAt = updatedAt;
                Items = items;
            }
            public Guid JobId { get; }
            public MediaImportJobState State { get; set; }
            public DateTimeOffset CreatedAt { get; }
            public DateTimeOffset UpdatedAt { get; set; }
            public List<ItemState> Items { get; }
        }

        private sealed class ItemState
        {
            public ItemState(Guid importItemId, string path)
            {
                ImportItemId = importItemId;
                Path = path;
            }
            public Guid ImportItemId { get; }
            public string Path { get; }
            public MediaImportItemState State { get; set; } = MediaImportItemState.Queued;
            public Guid? ArtifactId { get; set; }
            public string? ArtifactKind { get; set; }
            public MediaImportFailureCode? FailureCode { get; set; }
            public string? Message { get; set; }
        }
    }
}
```

- [ ] **Step 5: Run manager tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.MediaImportJobManagerTests" -v minimal
```

Expected: pass.

- [ ] **Step 6: Commit job manager**

```powershell
git add src\Rook\Services\Vision\MediaImport src\Rook.Tests\Services\Vision\MediaImport\MediaImportJobManagerTests.cs
git commit -m "feat(vision): add media import job manager"
```

## Task 3: Image Import Processor

**Files:**
- Create: `src/Rook/Services/Vision/MediaImport/ImageMediaImporter.cs`
- Create: `src/Rook/Services/Vision/MediaImport/MediaImportProcessor.cs`
- Modify: `src/Rook.Tests/Services/Vision/MediaImport/ImageMediaImporterTests.cs`

- [ ] **Step 1: Write failing image importer tests**

Create `ImageMediaImporterTests.cs`:

```csharp
using System;
using System.IO;
using System.Linq;
using Rook.Artifacts;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public class ImageMediaImporterTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-image-import-" + Guid.NewGuid().ToString("N"));
        private readonly ArtifactStore _store;

        public ImageMediaImporterTests()
        {
            _store = new ArtifactStore(_root);
            Directory.CreateDirectory(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void ImportPng_PublishesImportedImage_WithTechnicalMetadata()
        {
            var source = Path.Combine(_root, "source.png");
            WriteTinyPng(source);
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.True(result.Success, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal("imported_image", artifact.Kind);
            Assert.Contains(artifact.Files, f => f.Role == "image" && f.Path == "image.png");
            Assert.Equal("source.png", artifact.Metadata["original_filename"]!.GetValue<string>());
            Assert.Equal("png", artifact.Metadata["original_extension"]!.GetValue<string>());
            Assert.Equal("image/png", artifact.Metadata["mime_type"]!.GetValue<string>());
            Assert.Equal(1, artifact.Metadata["width"]!.GetValue<int>());
            Assert.Equal(1, artifact.Metadata["height"]!.GetValue<int>());
            Assert.True(artifact.Metadata["imported"]!.GetValue<bool>());
            Assert.DoesNotContain(artifact.Metadata.Keys, k => k.Contains("path", StringComparison.OrdinalIgnoreCase));
        }

        [Fact]
        public void ImportWebp_ReadsDimensionsFromHeader_AndPublishesImportedImage()
        {
            var source = Path.Combine(_root, "source.webp");
            WriteTinyWebp(source);
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.True(result.Success, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal("image/webp", artifact.Metadata["mime_type"]!.GetValue<string>());
            Assert.Equal(1, artifact.Metadata["width"]!.GetValue<int>());
            Assert.Equal(1, artifact.Metadata["height"]!.GetValue<int>());
        }

        [Fact]
        public void MapPublishException_CopyException_ReturnsCopyFailed()
        {
            var ex = new ArtifactBlobCopyException("image", "source.png", "image.png", new IOException("copy denied"));

            var result = ImageMediaImporter.MapPublishException("image", ex);

            Assert.False(result.Success);
            Assert.Equal(MediaImportFailureCode.CopyFailed, result.FailureCode);
        }

        [Fact]
        public void ImportGif_ReturnsUnsupportedMediaType_AndPublishesNothing()
        {
            var source = Path.Combine(_root, "source.gif");
            File.WriteAllText(source, "not used");
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(source);

            Assert.False(result.Success);
            Assert.Equal(MediaImportFailureCode.UnsupportedMediaType, result.FailureCode);
            Assert.Empty(_store.List());
        }

        [Fact]
        public void ImportDirectory_ReturnsNotRegularFile()
        {
            var dir = Path.Combine(_root, "folder.png");
            Directory.CreateDirectory(dir);
            var importer = new ImageMediaImporter(_store);

            var result = importer.Import(dir);

            Assert.False(result.Success);
            Assert.Equal(MediaImportFailureCode.NotRegularFile, result.FailureCode);
        }

        private static void WriteTinyPng(string path)
        {
            var bytes = Convert.FromBase64String(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=");
            File.WriteAllBytes(path, bytes);
        }

        private static void WriteTinyWebp(string path)
        {
            File.WriteAllBytes(path, new byte[]
            {
                0x52, 0x49, 0x46, 0x46, 0x18, 0x00, 0x00, 0x00,
                0x57, 0x45, 0x42, 0x50, 0x56, 0x50, 0x38, 0x58,
                0x0A, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00,
                0x00, 0x00, 0x00,
                0x00, 0x00
            });
        }
    }
}
```

- [ ] **Step 2: Run failing image importer tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.ImageMediaImporterTests" -v minimal
```

Expected: fails because `ImageMediaImporter` does not exist.

- [ ] **Step 3: Implement `ImageMediaImporter`**

Create `ImageMediaImporter.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class ImageMediaImporter
    {
        private readonly ArtifactStore _store;

        public ImageMediaImporter(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public MediaImportProcessResult Import(string path)
        {
            var validation = ValidatePath(path, MediaImportConstants.MaxImageBytes);
            if (!validation.Success) return validation;

            var extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (extension is not ("png" or "jpg" or "jpeg" or "webp"))
                return MediaImportProcessResult.Failed(MediaImportFailureCode.UnsupportedMediaType, "Unsupported image type.");

            if (!TryReadDimensions(path, extension, out var width, out var height, out var decodeError))
                return MediaImportProcessResult.Failed(MediaImportFailureCode.DecodeFailed, decodeError);

            try
            {
                var info = new FileInfo(path);
                var metadata = new Dictionary<string, JsonNode?>
                {
                    ["imported"] = JsonValue.Create(true),
                    ["import_source"] = JsonValue.Create("local_file"),
                    ["original_filename"] = JsonValue.Create(Path.GetFileName(path)),
                    ["original_extension"] = JsonValue.Create(extension),
                    ["mime_type"] = JsonValue.Create(ImageMimeDetector.FromExtension("." + extension)),
                    ["byte_size"] = JsonValue.Create(info.Length),
                    ["imported_at"] = JsonValue.Create(DateTimeOffset.UtcNow.ToString("o")),
                    ["width"] = JsonValue.Create(width),
                    ["height"] = JsonValue.Create(height),
                    ["normalized"] = JsonValue.Create(false),
                };

                var artifact = _store.CreateFromFiles(
                    MediaImportConstants.ImportedImageKind,
                    new[] { new BlobFileInput(ImageMediaRoles.Image, path, extension) },
                    metadata: metadata);

                return MediaImportProcessResult.Success(artifact.Id, artifact.Kind);
            }
            catch (Exception ex)
            {
                return MapPublishException("image", ex);
            }
        }

        internal static MediaImportProcessResult MapPublishException(string mediaKind, Exception ex)
        {
            if (ex is ArtifactBlobCopyException)
                return MediaImportProcessResult.Failed(MediaImportFailureCode.CopyFailed, $"Imported {mediaKind} blob could not be copied: {ex.InnerException?.Message ?? ex.Message}");
            return MediaImportProcessResult.Failed(MediaImportFailureCode.PublishFailed, $"Imported {mediaKind} could not be published: {ex.Message}");
        }

        internal static MediaImportProcessResult ValidatePath(string path, long maxBytes)
        {
            if (string.IsNullOrWhiteSpace(path))
                return MediaImportProcessResult.Failed(MediaImportFailureCode.FileNotFound, "File not found.");
            try
            {
                var attrs = File.GetAttributes(path);
                if ((attrs & FileAttributes.Directory) != 0)
                    return MediaImportProcessResult.Failed(MediaImportFailureCode.NotRegularFile, "Selected item is not a regular file.");
                if (!File.Exists(path))
                    return MediaImportProcessResult.Failed(MediaImportFailureCode.FileNotFound, "File not found.");
                var info = new FileInfo(path);
                if (info.Length > maxBytes)
                    return MediaImportProcessResult.Failed(MediaImportFailureCode.FileTooLarge, "File exceeds the import size limit.");
            }
            catch (FileNotFoundException)
            {
                return MediaImportProcessResult.Failed(MediaImportFailureCode.FileNotFound, "File not found.");
            }
            catch (DirectoryNotFoundException)
            {
                return MediaImportProcessResult.Failed(MediaImportFailureCode.FileNotFound, "File not found.");
            }
            catch (UnauthorizedAccessException ex)
            {
                return MediaImportProcessResult.Failed(MediaImportFailureCode.FileInaccessible, $"File is inaccessible: {ex.Message}");
            }
            catch (IOException ex)
            {
                return MediaImportProcessResult.Failed(MediaImportFailureCode.FileInaccessible, $"File is inaccessible: {ex.Message}");
            }
            return MediaImportProcessResult.Success(Guid.Empty, string.Empty);
        }

        private static bool TryReadDimensions(
            string path,
            string extension,
            out int width,
            out int height,
            out string error)
        {
            width = 0;
            height = 0;
            error = "";

            if (extension == "webp")
                return TryReadWebpDimensions(path, out width, out height, out error);

            try
            {
                using var image = System.Drawing.Image.FromFile(path);
                width = image.Width;
                height = image.Height;
                if (width > 0 && height > 0)
                    return true;
                error = "Image dimensions could not be read.";
                return false;
            }
            catch (Exception ex)
            {
                error = $"Image could not be decoded: {ex.Message}";
                return false;
            }
        }

        private static bool TryReadWebpDimensions(
            string path,
            out int width,
            out int height,
            out string error)
        {
            width = 0;
            height = 0;
            error = "WebP dimensions could not be read.";
            var bytes = File.ReadAllBytes(path);
            if (bytes.Length < 30
                || bytes[0] != 'R' || bytes[1] != 'I' || bytes[2] != 'F' || bytes[3] != 'F'
                || bytes[8] != 'W' || bytes[9] != 'E' || bytes[10] != 'B' || bytes[11] != 'P')
                return false;

            if (bytes[12] == 'V' && bytes[13] == 'P' && bytes[14] == '8' && bytes[15] == 'X')
            {
                width = 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16);
                height = 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16);
                return width > 0 && height > 0;
            }

            if (bytes[12] == 'V' && bytes[13] == 'P' && bytes[14] == '8' && bytes[15] == 'L')
            {
                if (bytes.Length < 25 || bytes[20] != 0x2f)
                    return false;
                width = 1 + bytes[21] + ((bytes[22] & 0x3F) << 8);
                height = 1 + ((bytes[22] & 0xC0) >> 6) + (bytes[23] << 2) + ((bytes[24] & 0x0F) << 10);
                return width > 0 && height > 0;
            }

            if (bytes[12] == 'V' && bytes[13] == 'P' && bytes[14] == '8' && bytes[15] == ' ')
            {
                if (bytes.Length < 30 || bytes[23] != 0x9d || bytes[24] != 0x01 || bytes[25] != 0x2a)
                    return false;
                width = (bytes[26] | (bytes[27] << 8)) & 0x3FFF;
                height = (bytes[28] | (bytes[29] << 8)) & 0x3FFF;
                return width > 0 && height > 0;
            }

            error = "WebP variant is not supported by v1 import dimension probing.";
            return false;
        }
    }
}
```

- [ ] **Step 4: Implement `MediaImportProcessor` image path**

Create `MediaImportProcessor.cs`:

```csharp
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.MediaImport
{
    public sealed class MediaImportProcessor : IMediaImportProcessor
    {
        private readonly ImageMediaImporter _imageImporter;

        public MediaImportProcessor(ArtifactStore store)
        {
            _imageImporter = new ImageMediaImporter(store ?? throw new ArgumentNullException(nameof(store)));
        }

        public Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var ext = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (ext is "png" or "jpg" or "jpeg" or "webp" or "gif" or "tiff" or "heic" or "heif" or "svg")
                return Task.FromResult(_imageImporter.Import(path));

            return Task.FromResult(MediaImportProcessResult.Failed(
                MediaImportFailureCode.UnsupportedMediaType,
                "Unsupported media type."));
        }
    }
}
```

- [ ] **Step 5: Run image importer tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.ImageMediaImporterTests" -v minimal
```

Expected: pass.

- [ ] **Step 6: Commit image import**

```powershell
git add src\Rook\Services\Vision\MediaImport src\Rook.Tests\Services\Vision\MediaImport\ImageMediaImporterTests.cs
git commit -m "feat(vision): import local images as artifacts"
```

## Task 4: Video Import Processor

**Files:**
- Create: `src/Rook/Services/Vision/MediaImport/FfmpegVideoProbe.cs`
- Create: `src/Rook/Services/Vision/MediaImport/VideoMediaImporter.cs`
- Modify: `src/Rook/Services/Vision/MediaImport/MediaImportProcessor.cs`
- Create/modify: `src/Rook.Tests/Services/Vision/MediaImport/VideoMediaImporterTests.cs`

- [ ] **Step 1: Write failing video importer tests with fake extractors**

Create `VideoMediaImporterTests.cs` with fake probe and sidecar writer interfaces. The tests assert required roles and no partial artifact on failure:

```csharp
using System;
using System.IO;
using System.Linq;
using Rook.Artifacts;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Services.Vision.MediaImport
{
    public class VideoMediaImporterTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-video-import-" + Guid.NewGuid().ToString("N"));
        private readonly ArtifactStore _store;

        public VideoMediaImporterTests()
        {
            Directory.CreateDirectory(_root);
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void ImportMov_PublishesVideoPosterStartAndEnd()
        {
            var source = Path.Combine(_root, "clip.mov");
            File.WriteAllText(source, "video");
            var sidecars = new FakeSidecarExtractor(_root);
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(success: true),
                sidecars);

            var result = importer.Import(source, default).GetAwaiter().GetResult();

            Assert.True(result.Success, result.Message);
            var artifact = _store.Get(result.ArtifactId!.Value)!;
            Assert.Equal("imported_video", artifact.Kind);
            Assert.Contains(artifact.Files, f => f.Role == "video" && f.Path == "video.mov");
            Assert.Contains(artifact.Files, f => f.Role == "poster" && f.Path == "poster.jpg");
            Assert.Contains(artifact.Files, f => f.Role == "start_frame" && f.Path == "start_frame.jpg");
            Assert.Contains(artifact.Files, f => f.Role == "end_frame" && f.Path == "end_frame.jpg");
            Assert.Equal("clip.mov", artifact.Metadata["original_filename"]!.GetValue<string>());
            Assert.Equal(2.5, artifact.Metadata["duration_seconds"]!.GetValue<double>());
            Assert.Equal(1920, artifact.Metadata["width"]!.GetValue<int>());
            Assert.Equal(1080, artifact.Metadata["height"]!.GetValue<int>());
        }

        [Fact]
        public void ImportMp4_WhenEndFrameFails_PublishesNothing()
        {
            var source = Path.Combine(_root, "clip.mp4");
            File.WriteAllText(source, "video");
            var sidecars = new FakeSidecarExtractor(_root) { FailEndFrame = true };
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(success: true),
                sidecars);

            var result = importer.Import(source, default).GetAwaiter().GetResult();

            Assert.False(result.Success);
            Assert.Equal(MediaImportFailureCode.SidecarExtractionFailed, result.FailureCode);
            Assert.Empty(_store.List());
        }

        [Fact]
        public void ImportAvi_ReturnsUnsupportedMediaType()
        {
            var source = Path.Combine(_root, "clip.avi");
            File.WriteAllText(source, "video");
            var importer = new VideoMediaImporter(
                _store,
                new FakeVideoProbe(success: true),
                new FakeSidecarExtractor(_root));

            var result = importer.Import(source, default).GetAwaiter().GetResult();

            Assert.False(result.Success);
            Assert.Equal(MediaImportFailureCode.UnsupportedMediaType, result.FailureCode);
        }
    }
}
```

Add fake probe/sidecar types in the same test file with these signatures matching production:

```csharp
internal sealed class FakeVideoProbe : IVideoImportProbe
{
    private readonly bool _success;
    public FakeVideoProbe(bool success) { _success = success; }
    public Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct) =>
        Task.FromResult(_success
            ? VideoImportProbeResult.Success(2.5, 1920, 1080, 30)
            : VideoImportProbeResult.Failed("probe failed"));
}

internal sealed class FakeSidecarExtractor : IVideoImportSidecarExtractor
{
    private readonly string _root;
    public FakeSidecarExtractor(string root) { _root = root; }
    public bool FailEndFrame { get; set; }

    public Task<VideoImportSidecarResult> ExtractAsync(string sourcePath, CancellationToken ct)
    {
        var dir = Path.Combine(_root, "sidecars-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var poster = Path.Combine(dir, "poster.jpg");
        var start = Path.Combine(dir, "start_frame.jpg");
        var end = Path.Combine(dir, "end_frame.jpg");
        File.WriteAllText(poster, "poster");
        File.WriteAllText(start, "start");
        if (FailEndFrame)
            return Task.FromResult(VideoImportSidecarResult.Failed("end frame failed"));
        File.WriteAllText(end, "end");
        return Task.FromResult(VideoImportSidecarResult.Success(poster, start, end));
    }
}
```

- [ ] **Step 2: Run failing video importer tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.VideoMediaImporterTests" -v minimal
```

Expected: fails because video import types do not exist.

- [ ] **Step 3: Add probe and sidecar contracts**

Create `FfmpegVideoProbe.cs` with these contracts and a production probe shell:

```csharp
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.MediaImport
{
    public interface IVideoImportProbe
    {
        Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct);
    }

    public sealed record VideoImportProbeResult(
        bool Success,
        double DurationSeconds,
        int Width,
        int Height,
        double? FrameRate,
        string? Message)
    {
        public static VideoImportProbeResult Success(double durationSeconds, int width, int height, double? frameRate) =>
            new(true, durationSeconds, width, height, frameRate, null);
        public static VideoImportProbeResult Failed(string message) =>
            new(false, 0, 0, 0, null, message);
    }

    public sealed class FfmpegVideoProbe : IVideoImportProbe
    {
        private static readonly Regex DurationRegex = new(@"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", RegexOptions.Compiled);
        private static readonly Regex SizeRegex = new(@"\b(\d{2,5})x(\d{2,5})\b", RegexOptions.Compiled);
        private readonly IVideoImportFfmpegResolver _resolver;
        private readonly IProcessRunner _runner;

        public FfmpegVideoProbe()
            : this(new DefaultVideoImportFfmpegResolver(), new DefaultProcessRunner()) { }

        internal FfmpegVideoProbe(IVideoImportFfmpegResolver resolver, IProcessRunner runner)
        {
            _resolver = resolver;
            _runner = runner;
        }

        public async Task<VideoImportProbeResult> ProbeAsync(string path, CancellationToken ct)
        {
            var resolved = _resolver.Resolve();
            if (!resolved.Success || string.IsNullOrWhiteSpace(resolved.Path))
                return VideoImportProbeResult.Failed(resolved.Message ?? "ffmpeg.exe was not found.");

            var psi = new ProcessStartInfo
            {
                FileName = resolved.Path,
                Arguments = "-hide_banner -i \"" + path.Replace("\"", "\\\"") + "\"",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = false,
            };
            var run = await _runner.RunAsync(psi, TimeSpan.FromSeconds(15), ct).ConfigureAwait(false);
            var stderr = run.StandardError ?? string.Empty;
            var duration = DurationRegex.Match(stderr);
            var size = SizeRegex.Match(stderr);
            if (!duration.Success || !size.Success)
                return VideoImportProbeResult.Failed("ffmpeg could not read video duration and dimensions.");
            var seconds =
                int.Parse(duration.Groups[1].Value, CultureInfo.InvariantCulture) * 3600d +
                int.Parse(duration.Groups[2].Value, CultureInfo.InvariantCulture) * 60d +
                double.Parse(duration.Groups[3].Value, CultureInfo.InvariantCulture);
            return VideoImportProbeResult.Success(
                seconds,
                int.Parse(size.Groups[1].Value, CultureInfo.InvariantCulture),
                int.Parse(size.Groups[2].Value, CultureInfo.InvariantCulture),
                frameRate: null);
        }
    }

    public interface IVideoImportFfmpegResolver
    {
        FfmpegBinaryResolution Resolve();
    }

    internal sealed class DefaultVideoImportFfmpegResolver : IVideoImportFfmpegResolver
    {
        public FfmpegBinaryResolution Resolve() =>
            FfmpegBinaryResolver.Resolve(FfmpegBundledBinaryLocator.GetInstalledFfmpegPath());
    }
}
```

- [ ] **Step 4: Implement `VideoMediaImporter`**

Create `VideoMediaImporter.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Extraction;

namespace Rook.Services.Vision.MediaImport
{
    public interface IVideoImportSidecarExtractor
    {
        Task<VideoImportSidecarResult> ExtractAsync(string sourcePath, CancellationToken ct);
    }

    public sealed record VideoImportSidecarResult(bool Success, string? PosterPath, string? StartFramePath, string? EndFramePath, string? TempDirectory, string? Message)
    {
        public static VideoImportSidecarResult Success(string posterPath, string startFramePath, string endFramePath) =>
            new(true, posterPath, startFramePath, endFramePath, null, null);
        public static VideoImportSidecarResult Success(string posterPath, string startFramePath, string endFramePath, string tempDirectory) =>
            new(true, posterPath, startFramePath, endFramePath, tempDirectory, null);
        public static VideoImportSidecarResult Failed(string message) =>
            new(false, null, null, null, null, message);
    }

    public sealed class VideoMediaImporter
    {
        private readonly ArtifactStore _store;
        private readonly IVideoImportProbe _probe;
        private readonly IVideoImportSidecarExtractor _sidecars;

        public VideoMediaImporter(ArtifactStore store)
            : this(store, new FfmpegVideoProbe(), new DefaultVideoImportSidecarExtractor()) { }

        internal VideoMediaImporter(ArtifactStore store, IVideoImportProbe probe, IVideoImportSidecarExtractor sidecars)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _probe = probe ?? throw new ArgumentNullException(nameof(probe));
            _sidecars = sidecars ?? throw new ArgumentNullException(nameof(sidecars));
        }

        public async Task<MediaImportProcessResult> Import(string path, CancellationToken ct)
        {
            var validation = ImageMediaImporter.ValidatePath(path, MediaImportConstants.MaxVideoBytes);
            if (!validation.Success) return validation;
            var extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            if (extension is not ("mp4" or "mov" or "webm"))
                return MediaImportProcessResult.Failed(MediaImportFailureCode.UnsupportedMediaType, "Unsupported video type.");

            var probe = await _probe.ProbeAsync(path, ct).ConfigureAwait(false);
            if (!probe.Success)
                return MediaImportProcessResult.Failed(MediaImportFailureCode.VideoProbeFailed, probe.Message ?? "Video probe failed.");

            VideoImportSidecarResult? sidecars = null;
            try
            {
                sidecars = await _sidecars.ExtractAsync(path, ct).ConfigureAwait(false);
                if (!sidecars.Success || sidecars.PosterPath is null || sidecars.StartFramePath is null || sidecars.EndFramePath is null)
                    return MediaImportProcessResult.Failed(MediaImportFailureCode.SidecarExtractionFailed, sidecars.Message ?? "Video sidecar extraction failed.");

                var info = new FileInfo(path);
                var metadata = new Dictionary<string, JsonNode?>
                {
                    ["imported"] = JsonValue.Create(true),
                    ["import_source"] = JsonValue.Create("local_file"),
                    ["original_filename"] = JsonValue.Create(Path.GetFileName(path)),
                    ["original_extension"] = JsonValue.Create(extension),
                    ["mime_type"] = JsonValue.Create(MimeForVideoExtension(extension)),
                    ["byte_size"] = JsonValue.Create(info.Length),
                    ["imported_at"] = JsonValue.Create(DateTimeOffset.UtcNow.ToString("o")),
                    ["duration_seconds"] = JsonValue.Create(probe.DurationSeconds),
                    ["width"] = JsonValue.Create(probe.Width),
                    ["height"] = JsonValue.Create(probe.Height),
                    ["frame_rate"] = probe.FrameRate.HasValue ? JsonValue.Create(probe.FrameRate.Value) : null,
                    ["poster_timestamp_seconds"] = JsonValue.Create(0.1),
                    ["start_frame_timestamp_seconds"] = JsonValue.Create(0),
                    ["end_frame_timestamp_seconds"] = JsonValue.Create(probe.DurationSeconds),
                    ["sidecars"] = new JsonObject
                    {
                        ["poster"] = "ok",
                        ["start_frame"] = "ok",
                        ["end_frame"] = "ok",
                    },
                };

                var artifact = _store.CreateFromFiles(
                    MediaImportConstants.ImportedVideoKind,
                    new[]
                    {
                        new BlobFileInput(VideoMediaRoles.Video, path, extension),
                        new BlobFileInput(VideoMediaRoles.Poster, sidecars.PosterPath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.StartFrame, sidecars.StartFramePath, "jpg"),
                        new BlobFileInput(VideoMediaRoles.EndFrame, sidecars.EndFramePath, "jpg"),
                    },
                    metadata: metadata);
                return MediaImportProcessResult.Success(artifact.Id, artifact.Kind);
            }
            catch (Exception ex)
            {
                return ImageMediaImporter.MapPublishException("video", ex);
            }
            finally
            {
                DefaultVideoImportSidecarExtractor.TryDeleteDirectory(sidecars?.TempDirectory);
            }
        }

        private static string MimeForVideoExtension(string extension) => extension switch
        {
            "mp4" => "video/mp4",
            "mov" => "video/quicktime",
            "webm" => "video/webm",
            _ => "application/octet-stream",
        };
    }

    internal sealed class DefaultVideoImportSidecarExtractor : IVideoImportSidecarExtractor
    {
        public Task<VideoImportSidecarResult> ExtractAsync(string sourcePath, CancellationToken ct)
        {
            throw new NotSupportedException(
                "Use the production extractor implementation in Step 5 before wiring this class into production composition.");
        }
    }
}
```

- [ ] **Step 5: Replace default sidecar extractor with production extraction**

Update `DefaultVideoImportSidecarExtractor` to use `FfmpegBinaryResolver`, `FfmpegPosterFrameExtractor`, and `FfmpegVideoFrameExtractor`. The method should create a temp directory under `Path.GetTempPath()\rook-media-import-sidecars\{guid}`, run poster, first frame, and last frame extraction, and return all three paths only when all succeed:

```csharp
internal sealed class DefaultVideoImportSidecarExtractor : IVideoImportSidecarExtractor
{
    public async Task<VideoImportSidecarResult> ExtractAsync(string sourcePath, CancellationToken ct)
    {
        var resolved = FfmpegBinaryResolver.Resolve(FfmpegBundledBinaryLocator.GetInstalledFfmpegPath());
        if (!resolved.Success || string.IsNullOrWhiteSpace(resolved.Path))
            return VideoImportSidecarResult.Failed(resolved.Message ?? "ffmpeg.exe was not found.");

        var dir = Path.Combine(Path.GetTempPath(), "rook-media-import-sidecars", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var poster = Path.Combine(dir, "poster.jpg");
        var start = Path.Combine(dir, "start_frame.jpg");
        var end = Path.Combine(dir, "end_frame.jpg");

        try
        {
            var posterResult = await new FfmpegPosterFrameExtractor()
                .ExtractPosterAsync(resolved.Path!, sourcePath, poster, TimeSpan.FromSeconds(30), ct)
                .ConfigureAwait(false);
            if (!posterResult.Success)
                return CleanupAndFail(dir, posterResult.Message ?? "Poster extraction failed.");

            var frameExtractor = new FfmpegVideoFrameExtractor();
            var startResult = await frameExtractor
                .ExtractFrameAsync(resolved.Path!, sourcePath, VideoFrameSelector.First, start, TimeSpan.FromSeconds(30), ct)
                .ConfigureAwait(false);
            if (!startResult.Success)
                return CleanupAndFail(dir, startResult.Message ?? "Start frame extraction failed.");

            var endResult = await frameExtractor
                .ExtractFrameAsync(resolved.Path!, sourcePath, VideoFrameSelector.Last, end, TimeSpan.FromSeconds(30), ct)
                .ConfigureAwait(false);
            if (!endResult.Success)
                return CleanupAndFail(dir, endResult.Message ?? "End frame extraction failed.");

            return VideoImportSidecarResult.Success(poster, start, end, dir);
        }
        catch
        {
            TryDeleteDirectory(dir);
            throw;
        }
    }

    private static VideoImportSidecarResult CleanupAndFail(string dir, string message)
    {
        TryDeleteDirectory(dir);
        return VideoImportSidecarResult.Failed(message);
    }

    internal static void TryDeleteDirectory(string? dir)
    {
        if (string.IsNullOrWhiteSpace(dir)) return;
        try
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, recursive: true);
        }
        catch { }
    }
}
```

- [ ] **Step 6: Route videos through `MediaImportProcessor`**

Modify `MediaImportProcessor` to construct `VideoMediaImporter` and call it for `mp4`, `mov`, and `webm`:

```csharp
private readonly VideoMediaImporter _videoImporter;

public MediaImportProcessor(ArtifactStore store)
{
    if (store is null) throw new ArgumentNullException(nameof(store));
    _imageImporter = new ImageMediaImporter(store);
    _videoImporter = new VideoMediaImporter(store);
}

public Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct)
{
    ct.ThrowIfCancellationRequested();
    var ext = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
    if (ext is "png" or "jpg" or "jpeg" or "webp" or "gif" or "tiff" or "heic" or "heif" or "svg")
        return Task.FromResult(_imageImporter.Import(path));
    if (ext is "mp4" or "mov" or "webm")
        return _videoImporter.Import(path, ct);
    return Task.FromResult(MediaImportProcessResult.Failed(MediaImportFailureCode.UnsupportedMediaType, "Unsupported media type."));
}
```

- [ ] **Step 7: Run video importer tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Services.Vision.MediaImport.VideoMediaImporterTests" -v minimal
```

Expected: pass.

- [ ] **Step 8: Commit video import**

```powershell
git add src\Rook\Services\Vision\MediaImport src\Rook.Tests\Services\Vision\MediaImport\VideoMediaImporterTests.cs
git commit -m "feat(vision): import local videos as artifacts"
```

## Task 5: Bridge-Only Media Import Ops

**Files:**
- Create: `src/Rook/Handlers/MediaImportOpHandler.cs`
- Create: `src/Rook/Services/Vision/MediaImport/MediaImportSubsystemFactory.cs`
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Create: `src/Rook.Tests/Handlers/MediaImportOpHandlerTests.cs`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Write failing op handler tests**

Create `MediaImportOpHandlerTests.cs` with status/list serialization and start-level validation. Use a picker seam so tests do not show UI:

```csharp
using System;
using System.Linq;
using Rook.Handlers;
using Rook.Services.Vision.MediaImport;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class MediaImportOpHandlerTests
    {
        [Fact]
        public void Start_EmptySelection_ReturnsCreatedFalse()
        {
            var handler = new MediaImportOpHandler(
                new MediaImportJobManager(new FakeProcessor()),
                new FakePicker(Array.Empty<string>()));

            var response = handler.DispatchUi("""{"op":"start_media_import"}""");

            Assert.True(response.Success);
            var data = Assert.IsType<System.Collections.Generic.Dictionary<string, object?>>(response.Data);
            Assert.Equal(false, data["created"]);
            Assert.Equal("empty_selection", data["reason"]);
        }

        [Fact]
        public void Start_ReturnsBasenameOnly()
        {
            var handler = new MediaImportOpHandler(
                new MediaImportJobManager(new FakeProcessor()),
                new FakePicker(new[] { @"C:\private\clip.mp4" }));

            var response = handler.DispatchUi("""{"op":"start_media_import"}""");

            Assert.True(response.Success);
            var data = Assert.IsType<System.Collections.Generic.Dictionary<string, object?>>(response.Data);
            Assert.Equal(true, data["created"]);
            var files = Assert.IsAssignableFrom<System.Collections.IEnumerable>(data["files"]);
            var first = Assert.IsType<System.Collections.Generic.Dictionary<string, object?>>(files.Cast<object>().First());
            Assert.Equal("clip.mp4", first["basename"]);
        }
    }
}
```

Add fake types in the test file:

```csharp
internal sealed class FakePicker : IMediaImportPicker
{
    private readonly string[] _paths;
    public FakePicker(string[] paths) { _paths = paths; }
    public string[] PickFiles() => _paths;
}

internal sealed class FakeProcessor : IMediaImportProcessor
{
    public Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct) =>
        Task.FromResult(MediaImportProcessResult.Success(Guid.NewGuid(), MediaImportConstants.ImportedImageKind));
}
```

- [ ] **Step 2: Run failing op handler tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Handlers.MediaImportOpHandlerTests" -v minimal
```

Expected: fails because `MediaImportOpHandler` does not exist.

- [ ] **Step 3: Implement op handler and picker seam**

Create `MediaImportOpHandler.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Eto.Forms;
using Rook.Services.Vision.MediaImport;

namespace Rook.Handlers
{
    public interface IMediaImportPicker
    {
        string[] PickFiles();
    }

    public sealed class EtoMediaImportPicker : IMediaImportPicker
    {
        public string[] PickFiles()
        {
            var dialog = new OpenFileDialog
            {
                MultiSelect = true,
                Title = "Add Media to Gallery",
            };
            dialog.Filters.Add(new FileFilter("Supported media", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"));
            return dialog.ShowDialog(null) == DialogResult.Ok
                ? dialog.Filenames.ToArray()
                : Array.Empty<string>();
        }
    }

    public sealed class MediaImportOpHandler
    {
        public const string OpStart = "start_media_import";
        public const string OpStatus = "get_media_import_job";
        public const string OpList = "list_media_import_jobs";

        private readonly MediaImportJobManager _manager;
        private readonly IMediaImportPicker _picker;

        public MediaImportOpHandler(MediaImportJobManager manager, IMediaImportPicker picker)
        {
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _picker = picker ?? throw new ArgumentNullException(nameof(picker));
        }

        public ApiResponse DispatchUi(string? body)
        {
            var args = ParseObjectBody(body);
            var op = GetStringArg(args, "op");
            if (op != OpStart) return Fail($"Unknown media import UI op '{op}'.");
            var paths = _picker.PickFiles();
            var start = _manager.StartAsync(paths, default).GetAwaiter().GetResult();
            if (!start.Created)
            {
                return Ok(new Dictionary<string, object?>
                {
                    ["created"] = false,
                    ["reason"] = StartFailureToString(start.FailureCode!.Value),
                    ["message"] = start.Message,
                });
            }
            return Ok(JobToObj(start.Job!, includeCreated: true));
        }

        public ApiResponse DispatchOffUi(string? body)
        {
            var args = ParseObjectBody(body);
            var op = GetStringArg(args, "op");
            return op switch
            {
                OpStatus => Get(args),
                OpList => List(),
                OpStart => Fail("op 'start_media_import' must be routed through the UI dispatcher."),
                _ => Fail($"Unknown media import op '{op}'."),
            };
        }

        private ApiResponse Get(Dictionary<string, JsonElement> args)
        {
            var raw = GetStringArg(args, "job_id");
            if (!Guid.TryParseExact(raw, "D", out var id))
                return Fail("Missing or invalid 'job_id'.");
            var job = _manager.GetJob(id);
            return job is null ? Fail($"Media import job '{id:D}' not found.") : Ok(JobToObj(job));
        }

        private ApiResponse List() =>
            Ok(new Dictionary<string, object?>
            {
                ["jobs"] = _manager.ListJobs().Jobs.Select(j => JobToObj(j)).ToList(),
            });

        private static Dictionary<string, object?> JobToObj(MediaImportJobSnapshot job, bool includeCreated = false)
        {
            var obj = new Dictionary<string, object?>
            {
                ["job_id"] = job.JobId.ToString("D"),
                ["state"] = JobStateToString(job.State),
                ["created_at"] = job.CreatedAt.ToString("o"),
                ["updated_at"] = job.UpdatedAt.ToString("o"),
                ["files"] = job.Items.Select(ItemToObj).ToList(),
            };
            if (includeCreated) obj["created"] = true;
            return obj;
        }

        private static Dictionary<string, object?> ItemToObj(MediaImportItemSnapshot item) =>
            new()
            {
                ["import_item_id"] = item.ImportItemId.ToString("D"),
                ["basename"] = item.Basename,
                ["status"] = ItemStateToString(item.State),
                ["artifact_id"] = item.ArtifactId?.ToString("D"),
                ["artifact_kind"] = item.ArtifactKind,
                ["failure_code"] = item.FailureCode.HasValue ? FailureCodeToString(item.FailureCode.Value) : null,
                ["message"] = item.Message,
            };

        private static string JobStateToString(MediaImportJobState state) => state.ToString().ToLowerInvariant();
        private static string ItemStateToString(MediaImportItemState state) => state switch
        {
            MediaImportItemState.ExtractingSidecars => "extracting_sidecars",
            _ => state.ToString().ToLowerInvariant(),
        };
        private static string StartFailureToString(MediaImportStartFailureCode code) => code == MediaImportStartFailureCode.EmptySelection ? "empty_selection" : "too_many_files";
        private static string FailureCodeToString(MediaImportFailureCode code) => code switch
        {
            MediaImportFailureCode.UnsupportedMediaType => "unsupported_media_type",
            MediaImportFailureCode.FileNotFound => "file_not_found",
            MediaImportFailureCode.NotRegularFile => "not_regular_file",
            MediaImportFailureCode.FileInaccessible => "file_inaccessible",
            MediaImportFailureCode.FileTooLarge => "file_too_large",
            MediaImportFailureCode.DecodeFailed => "decode_failed",
            MediaImportFailureCode.VideoProbeFailed => "video_probe_failed",
            MediaImportFailureCode.SidecarExtractionFailed => "sidecar_extraction_failed",
            MediaImportFailureCode.CopyFailed => "copy_failed",
            _ => "publish_failed",
        };
        private static ApiResponse Ok(object? data) => new() { Success = true, Data = data, HttpStatus = 200 };
        private static ApiResponse Fail(string message) => new() { Success = false, Data = message, HttpStatus = 400 };
        private static string? GetStringArg(Dictionary<string, JsonElement> args, string key) => args.TryGetValue(key, out var el) && el.ValueKind == JsonValueKind.String ? el.GetString() : null;
        private static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrWhiteSpace(body)) return new Dictionary<string, JsonElement>();
            using var doc = JsonDocument.Parse(body);
            var dict = new Dictionary<string, JsonElement>();
            foreach (var prop in doc.RootElement.EnumerateObject()) dict[prop.Name] = prop.Value.Clone();
            return dict;
        }
    }
}
```

- [ ] **Step 4: Add media import composition**

Create `MediaImportSubsystemFactory.cs`:

```csharp
using Rook.Artifacts;

namespace Rook.Services.Vision.MediaImport
{
    internal static class MediaImportSubsystemFactory
    {
        public static MediaImportJobManager Build(ArtifactStore artifactStore) =>
            new(new MediaImportProcessor(artifactStore));
    }
}
```

In `RookSubsystemRoot`, add `using Rook.Services.Vision.MediaImport;`, add a lazy field beside `_video` and `_imageJobs`:

```csharp
private readonly Lazy<MediaImportJobManager> _mediaImports;
```

Add this public property after `ImageJobs`:

```csharp
public MediaImportJobManager MediaImports
{
    get
    {
        if (Volatile.Read(ref _disposed) != 0)
            throw new ObjectDisposedException(
                nameof(RookSubsystemRoot),
                "Media import subsystem accessed after shutdown.");
        return _mediaImports.Value;
    }
}
```

Initialize `_mediaImports` in the internal constructor after `_imageJobs` is initialized:

```csharp
_mediaImports = new Lazy<MediaImportJobManager>(
    () => MediaImportSubsystemFactory.Build(SharedArtifactStore),
    LazyThreadSafetyMode.ExecutionAndPublication);
```

- [ ] **Step 5: Route import ops in `VisionWebSurface`**

Add `MediaImportOpHandler? _mediaImportHandler`, build it in the parameterless constructor, add these op routes:

```csharp
[MediaImportOpHandler.OpStart] = VisionOpRoute.Ui,
[MediaImportOpHandler.OpStatus] = VisionOpRoute.OffUi,
[MediaImportOpHandler.OpList] = VisionOpRoute.OffUi,
```

Add a `MediaImportOps` set and route UI/off-UI dispatch to `_mediaImportHandler.DispatchUi(body)` or `_mediaImportHandler.DispatchOffUi(body)`.

- [ ] **Step 6: Update routing tests**

In `VisionWebSurfaceTests.OpRoutes_Contains_All_Expected_Ops`, add:

```csharp
"start_media_import", "get_media_import_job", "list_media_import_jobs",
```

Add `[InlineData]` rows:

```csharp
[InlineData("start_media_import", "Ui")]
[InlineData("get_media_import_job", "OffUi")]
[InlineData("list_media_import_jobs", "OffUi")]
```

- [ ] **Step 7: Run handler and routing tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~MediaImportOpHandlerTests|FullyQualifiedName~VisionWebSurfaceTests.OpRoutes" -v minimal
```

Expected: pass.

- [ ] **Step 8: Commit bridge ops**

```powershell
git add src\Rook\Handlers\MediaImportOpHandler.cs src\Rook\Services\Vision\MediaImport\MediaImportSubsystemFactory.cs src\Rook\RookSubsystemRoot.cs src\Rook\UI\Vision\VisionWebSurface.cs src\Rook.Tests\Handlers\MediaImportOpHandlerTests.cs src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): expose bridge-only media import ops"
```

## Task 6: Image Generation Artifact Refs

**Files:**
- Create: `src/Rook/Services/Vision/Image/ArtifactImageMediaResolver.cs`
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/ArtifactImageMediaResolverTests.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Modify: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

- [ ] **Step 1: Add failing resolver tests**

Create `ArtifactImageMediaResolverTests.cs`:

```csharp
using System;
using System.IO;
using System.Threading;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ArtifactImageMediaResolverTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-image-resolver-" + Guid.NewGuid().ToString("N"));
        private readonly ArtifactStore _store;

        public ArtifactImageMediaResolverTests()
        {
            _store = new ArtifactStore(_root);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task ResolveAllAsync_ResolvesArtifactBytesAndMime()
        {
            var artifact = _store.Create("imported_image", new[] { new BlobInput("image", TinyPng(), "png") });
            var mediaRef = MediaRef.ForArtifact(artifact.Id, "image");
            var resolver = new ArtifactImageMediaResolver(_store);

            var result = await resolver.ResolveAllAsync(new[] { mediaRef }, CancellationToken.None);

            Assert.True(result.Success);
            var media = result.Resolved![mediaRef];
            Assert.Equal("image/png", media.MimeType);
            Assert.Equal(TinyPng(), media.Bytes);
        }

        [Fact]
        public async Task ResolveAllAsync_ImageGenerationRoles_FallBackToArtifactImageBlob()
        {
            var artifact = _store.Create("imported_image", new[] { new BlobInput("image", TinyPng(), "png") });
            var mediaRef = MediaRef.ForArtifact(artifact.Id, ImageMediaRoles.InputImage);
            var resolver = new ArtifactImageMediaResolver(_store);

            var result = await resolver.ResolveAllAsync(new[] { mediaRef }, CancellationToken.None);

            Assert.True(result.Success);
            Assert.Equal(TinyPng(), result.Resolved![mediaRef].Bytes);
        }

        private static byte[] TinyPng() => Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=");
    }
}
```

- [ ] **Step 2: Implement `ArtifactImageMediaResolver`**

Create `ArtifactImageMediaResolver.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed class ArtifactImageMediaResolver : IMediaResolver
    {
        private readonly ArtifactStore _store;

        public ArtifactImageMediaResolver(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public Task<MediaResolutionResult> ResolveAllAsync(IReadOnlyList<MediaRef> refs, CancellationToken ct)
        {
            var resolved = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var mediaRef in refs)
            {
                ct.ThrowIfCancellationRequested();
                if (resolved.ContainsKey(mediaRef)) continue;
                try
                {
                    string path = mediaRef.Kind switch
                    {
                        MediaRefKind.Artifact when mediaRef.ArtifactId.HasValue =>
                            _store.GetBlobAbsolutePath(mediaRef.ArtifactId.Value, ResolveArtifactRole(mediaRef.Role)),
                        MediaRefKind.Path when !string.IsNullOrWhiteSpace(mediaRef.Path) =>
                            mediaRef.Path!,
                        _ => throw new InvalidOperationException("Invalid image media ref."),
                    };
                    var bytes = File.ReadAllBytes(path);
                    resolved[mediaRef] = new ResolvedMedia(bytes, ImageMimeDetector.Detect(bytes, path));
                }
                catch (Exception ex)
                {
                    return Task.FromResult(MediaResolutionResult.Fail(new GenerationError(
                        GenerationErrorCode.InvalidRequest,
                        $"Image media resolution failed: {ex.Message}",
                        Retryable: false,
                        Field: "MediaRef")));
                }
            }
            return Task.FromResult(MediaResolutionResult.Ok(resolved));
        }

        private static string ResolveArtifactRole(string role) =>
            role == ImageMediaRoles.InputImage || role == ImageMediaRoles.ReferenceImage
                ? ImageMediaRoles.Image
                : role;
    }
}
```

- [ ] **Step 3: Add artifact-ref parsing tests for sync and image job paths**

In `VisionHandlerTests`, add a test that calls `BuildImageGenerationWorkItem` with:

```json
{
  "prompt": "edit",
  "model": "gemini-2.5-flash-image-preview",
  "input_image": { "kind": "artifact_id", "artifact_id": "<artifact-id>", "role": "image" },
  "reference_images": [
    { "kind": "artifact_id", "artifact_id": "<artifact-id>", "role": "image" }
  ]
}
```

Assert:

```csharp
Assert.Contains(work.ParentArtifactIds, id => id == artifact.Id);
Assert.Contains(work.ResolvedMedia.Keys, r => r.Kind == MediaRefKind.Artifact && r.ArtifactId == artifact.Id);
```

In `ImageJobOpHandlerTests`, add the same request to `image_generate_start` and assert the fake manager receives artifact refs.

Add a sync `GenerateAsync` lineage test in `VisionHandlerTests` with a fake sync image provider. Submit an `input_image` artifact ref, generate an output, then assert the returned artifact's `parent_ids` contains the imported source artifact id.

- [ ] **Step 4: Update `BuildImageGenerationWorkItem`**

In `VisionHandler`, parse new fields before legacy path fields:

```csharp
var inputArtifactRef = TryParseOptionalMediaRef(args, "input_image", ImageMediaRoles.InputImage);
var referenceArtifactRefs = TryParseOptionalMediaRefArray(args, "reference_images", ImageMediaRoles.ReferenceImage);
```

Rules:

- If `input_image` is present, use it instead of `input_image_path`.
- If `reference_images` is present, use it instead of `reference_image_paths`.
- Artifact refs use the existing wire shape `{ "kind": "artifact_id", "artifact_id": "...", "role": "image" }`.
- Parse `input_image` into `MediaRef.ForArtifact(id, ImageMediaRoles.InputImage)`.
- Parse each `reference_images[]` entry into `MediaRef.ForArtifact(id, ImageMediaRoles.ReferenceImage)`.
- `ArtifactImageMediaResolver` maps image-generation roles `input_image` and `reference_image` back to artifact blob role `image` when reading from `ArtifactStore`.
- Provider code continues to classify media by `ImageMediaRoles.InputImage` and `ImageMediaRoles.ReferenceImage`; providers do not need to know the stored blob role fallback.

- [ ] **Step 5: Resolve artifact media and parent IDs**

After building all media refs, call the sync helper directly:

```csharp
var mediaResolution = ResolveImageMediaRefs(mediaRefs);
```

`BuildImageGenerationWorkItem` is sync, so add an internal sync helper:

```csharp
private MediaResolutionResult ResolveImageMediaRefs(IReadOnlyList<MediaRef> refs)
    => new ArtifactImageMediaResolver(_artifactStore)
        .ResolveAllAsync(refs, CancellationToken.None)
        .GetAwaiter()
        .GetResult();
```

Set `ParentArtifactIds` to distinct artifact IDs from artifact-kind input and reference refs. Keep legacy path behavior returning `Array.Empty<Guid>()`.

Also update `GenerateAsync` so sync image artifacts preserve lineage:

```csharp
var artifact = _artifactStore.Create(
    kind: ArtifactKindGeneratedImage,
    blobs: new[] { blob },
    parentIds: work.ParentArtifactIds,
    metadata: metadata);
```

- [ ] **Step 6: Run image generation tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~ImageJobOpHandlerTests|FullyQualifiedName~ArtifactImageMediaResolverTests" -v minimal
```

Expected: pass.

- [ ] **Step 7: Commit artifact-ref image generation**

```powershell
git add src\Rook\Services\Vision\Image\ArtifactImageMediaResolver.cs src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Services\Vision\Image\ArtifactImageMediaResolverTests.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "feat(vision): resolve image generation artifact refs"
```

## Task 7: Gallery And Picker UI Integration

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook/UI/Vision/Resources/styles.css`
- Modify: `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add source tests for imported kinds and import button**

In `VisionVideoSidecarContractSourceTests`, add assertions:

```csharp
[Fact]
public void AppJs_FramePickerIncludesImportedKinds()
{
    var js = ReadVisionResource("app.js");
    var openPicker = ExtractFunction(js, "async function openPicker(slot)");
    Assert.Contains("kind: \"imported_image\"", openPicker);
    Assert.Contains("kind: \"imported_video\"", openPicker);
    Assert.Contains("artifact.kind === \"generated_video\" || artifact.kind === \"imported_video\"", js);
}
```

In `VisionWebSurfaceTests`, add a source test for `id="add-media-gallery"` in `index.html`.

- [ ] **Step 2: Add Gallery toolbar button and status panel**

In `index.html`, add this button inside `.gallery-toolbar` after refresh:

```html
<button id="add-media-gallery" class="btn btn-secondary" title="Add media to Gallery">Add Media to Gallery</button>
```

Add a panel before `gallery-grid`:

```html
<div id="media-import-panel" class="media-import-panel hidden">
    <div class="media-import-header">
        <span>Media import</span>
        <button id="refresh-media-imports" class="btn btn-icon" title="Refresh imports" aria-label="Refresh imports">↻</button>
    </div>
    <div id="media-import-list" class="media-import-list"></div>
</div>
```

- [ ] **Step 3: Update Gallery loading to include imported kinds**

In `app.js`, replace the two-kind Gallery load with:

```javascript
const galleryKinds = ["generated_image", "generated_video", "imported_image", "imported_video"];
const responses = await Promise.all(
    galleryKinds.map(kind => bridgeCall("list_artifacts", { kind, limit: 100 }))
);
galleryItems = responses
    .flatMap(data => data.artifacts || [])
    .sort((a, b) => {
        const byTime = (b.created_at || "").localeCompare(a.created_at || "");
        if (byTime !== 0) return byTime;
        return (b.artifact_id || "").localeCompare(a.artifact_id || "");
    });
```

Update video checks:

```javascript
const isVideo = item.kind === "generated_video" || item.kind === "imported_video";
```

and in `pickDisplayRole`:

```javascript
const isVideo = summary.kind === "generated_video" || summary.kind === "imported_video";
```

- [ ] **Step 4: Add import job UI functions**

Add these globals near Gallery globals:

```javascript
let mediaImportJobs = new Map();
let mediaImportPollers = new Map();
```

Add functions:

```javascript
async function startMediaImport() {
    try {
        const data = await bridgeCall("start_media_import", {});
        if (data && data.created === false) return;
        rememberMediaImportJob(data);
        renderMediaImportJobs();
        pollMediaImportJob(data.job_id);
    } catch (e) {
        window.alert(`Could not add media: ${e.message}`);
    }
}

async function loadMediaImportJobs() {
    const data = await bridgeCall("list_media_import_jobs", {});
    (data.jobs || []).forEach(rememberMediaImportJob);
    renderMediaImportJobs();
    for (const job of mediaImportJobs.values()) {
        if (job.state !== "complete") pollMediaImportJob(job.job_id);
    }
}

function rememberMediaImportJob(job) {
    if (!job || !job.job_id) return;
    mediaImportJobs.set(job.job_id, job);
}

function renderMediaImportJobs() {
    if (!el.mediaImportPanel || !el.mediaImportList) return;
    const jobs = Array.from(mediaImportJobs.values());
    el.mediaImportPanel.classList.toggle("hidden", jobs.length === 0);
    el.mediaImportList.innerHTML = jobs.flatMap(job =>
        (job.files || []).map(file => `
            <div class="media-import-row media-import-${escapeAttr(file.status || "")}">
                <span class="media-import-name">${escapeHtml(file.basename || "")}</span>
                <span class="media-import-status">${escapeHtml(file.status || "")}</span>
                <span class="media-import-message">${escapeHtml(file.message || file.failure_code || "")}</span>
                ${file.artifact_id ? `<button class="btn btn-secondary btn-open-import" data-id="${escapeAttr(file.artifact_id)}">Open</button>` : ""}
            </div>`)).join("");
    el.mediaImportList.querySelectorAll(".btn-open-import").forEach(btn => {
        btn.addEventListener("click", () => openArtifactModal(btn.dataset.id));
    });
}

function pollMediaImportJob(jobId) {
    if (!jobId || mediaImportPollers.has(jobId)) return;
    const poller = window.setInterval(async () => {
        try {
            const job = await bridgeCall("get_media_import_job", { job_id: jobId });
            const before = mediaImportJobs.get(jobId);
            rememberMediaImportJob(job);
            renderMediaImportJobs();
            const publishedNow = (job.files || []).some(f => f.artifact_id)
                && (!before || JSON.stringify(before.files) !== JSON.stringify(job.files));
            if (publishedNow && currentView === "gallery") loadGallery();
            if (job.state === "complete") {
                window.clearInterval(poller);
                mediaImportPollers.delete(jobId);
                if (currentView === "gallery") loadGallery();
            }
        } catch (e) {
            window.clearInterval(poller);
            mediaImportPollers.delete(jobId);
        }
    }, 1000);
    mediaImportPollers.set(jobId, poller);
}
```

- [ ] **Step 5: Wire DOM elements**

In `cacheElements`, add:

```javascript
el.addMediaGalleryBtn = $("add-media-gallery");
el.mediaImportPanel = $("media-import-panel");
el.mediaImportList = $("media-import-list");
el.refreshMediaImportsBtn = $("refresh-media-imports");
```

In event binding:

```javascript
el.addMediaGalleryBtn.addEventListener("click", startMediaImport);
el.refreshMediaImportsBtn.addEventListener("click", loadMediaImportJobs);
```

When switching to Gallery, call both:

```javascript
if (view === "gallery") {
    loadGallery();
    loadMediaImportJobs();
}
```

- [ ] **Step 6: Update frame picker imported video behavior**

Change generated-video branch in `buildFramePickerChoices` to:

```javascript
if (artifact.kind === "generated_video" || artifact.kind === "imported_video") {
```

Change picker queries to include imported kinds:

```javascript
const [genData, capData, depthData, vidData, importedImageData, importedVideoData] = await Promise.all([
    bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
    bridgeCall("list_artifacts", { kind: "captured_viewport", limit: 100 }),
    bridgeCall("list_artifacts", { kind: "depth_map", limit: 100 }),
    bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
    bridgeCall("list_artifacts", { kind: "imported_image", limit: 100 }),
    bridgeCall("list_artifacts", { kind: "imported_video", limit: 100 }),
]);
```

and include both arrays in `items`.

- [ ] **Step 7: Add CSS**

Add compact styles:

```css
.media-import-panel {
    border: 1px solid var(--border-muted);
    padding: 12px;
    margin-bottom: 12px;
}

.media-import-header,
.media-import-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto;
    gap: 8px;
    align-items: center;
}

.media-import-list {
    display: grid;
    gap: 6px;
}

.media-import-name,
.media-import-message {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
```

- [ ] **Step 8: Run UI source tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI.Vision" -v minimal
```

Expected: pass.

- [ ] **Step 9: Commit Gallery UI**

```powershell
git add src\Rook\UI\Vision\Resources\index.html src\Rook\UI\Vision\Resources\app.js src\Rook\UI\Vision\Resources\styles.css src\Rook.Tests\UI\Vision
git commit -m "feat(vision): add Gallery media import UI"
```

## Task 8: Studio Source Artifact Flow

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add source test for artifact image payload fields**

Add a source test that asserts `app.js` contains `input_image` and `reference_images` and no longer builds new Studio requests from `input_image_path` for selected Gallery/imported media:

```csharp
[Fact]
public void AppJs_StudioUsesImageArtifactRefsForSelectedSource()
{
    var js = ReadSourceFile("src", "Rook", "UI", "Vision", "Resources", "app.js");
    Assert.Contains("input_image:", js);
    Assert.Contains("reference_images", js);
    Assert.Contains("kind: \"artifact_id\"", js);
}
```

- [ ] **Step 2: Update Studio source state shape**

Change selected source objects to include artifact refs:

```javascript
// { source: "artifact", artifact_id, role, previewSrc, label }
let studioSource = null;
```

When a source is chosen from import or Gallery, set:

```javascript
studioSource = {
    source: "artifact",
    artifact_id: artifactId,
    role: role || "image",
    previewSrc: `/blob/${encodeURIComponent(artifactId)}/${encodeURIComponent(role || "image")}`,
    label,
};
```

- [ ] **Step 3: Make Studio `Load Image` import first**

Replace direct `open_image_picker` use in the Studio load flow with `start_media_import`, then poll the returned job until the first `imported_image` artifact appears:

```javascript
async function importSourceImageForStudio() {
    const start = await bridgeCall("start_media_import", {});
    if (!start || start.created === false) return null;
    rememberMediaImportJob(start);
    renderMediaImportJobs();
    const job = await awaitMediaImportJob(start.job_id);
    const imported = (job.files || []).find(f => f.artifact_kind === "imported_image" && f.artifact_id);
    if (!imported) throw new Error("No imported image was created.");
    return {
        source: "artifact",
        artifact_id: imported.artifact_id,
        role: "image",
        previewSrc: `/blob/${encodeURIComponent(imported.artifact_id)}/image`,
        label: imported.basename,
    };
}
```

Add helper:

```javascript
const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

async function awaitMediaImportJob(jobId) {
    for (;;) {
        const job = await bridgeCall("get_media_import_job", { job_id: jobId });
        rememberMediaImportJob(job);
        renderMediaImportJobs();
        if (job.state === "complete") return job;
        await sleep(750);
    }
}
```

- [ ] **Step 4: Build image generation args from artifact refs**

Where Studio/Generate builds image generation args, use:

```javascript
if (studioSource && studioSource.source === "artifact") {
    args.input_image = {
        kind: "artifact_id",
        artifact_id: studioSource.artifact_id,
        role: studioSource.role || "image",
    };
}
if (studioReferences.length > 0) {
    args.reference_images = studioReferences.map(ref => ({
        kind: "artifact_id",
        artifact_id: ref.artifact_id,
        role: ref.role || "image",
    }));
}
```

Keep existing path fields only for legacy states that already hold `path`.

- [ ] **Step 5: Run UI source tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.AppJs_StudioUsesImageArtifactRefsForSelectedSource" -v minimal
```

Expected: pass.

- [ ] **Step 6: Commit Studio artifact source UI**

```powershell
git add src\Rook\UI\Vision\Resources\app.js src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): use artifact refs for image sources"
```

## Task 9: Final Verification And Boundary Scan

**Files:**
- No production code changes unless a verification failure identifies a specific fix.

- [ ] **Step 1: Run focused managed tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~MediaImport|FullyQualifiedName~ArtifactStoreTests|FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~VisionVideoSidecarContractSourceTests|FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~ImageJobOpHandlerTests" -v minimal
```

Expected: pass.

- [ ] **Step 2: Run full managed test suite**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -v minimal
```

Expected: pass. If unrelated pre-existing failures appear, capture failing test names and rerun one focused failing test before changing code.

- [ ] **Step 3: Verify import ops are bridge-only**

Run:

```powershell
rg -n "start_media_import|get_media_import_job|list_media_import_jobs" src\RookNative mcp_server src\Rook\InternalBridge src\Rook\UI\Vision src\Rook\Handlers
```

Expected:

- hits in managed RookVision UI/handler/routing files;
- no hits in `src\RookNative`;
- no hits in `mcp_server`;
- no public native route registration.

- [ ] **Step 4: Verify no routine path leaks in UI state strings**

Run:

```powershell
rg -n "source_path|SourcePath|selected.*path|paths\\]|input_image_path|reference_image_paths" src\Rook\UI\Vision\Resources src\Rook\Handlers\MediaImportOpHandler.cs src\Rook\Services\Vision\MediaImport
```

Expected:

- `SourcePath` appears only in server-side file-backed artifact input types or internal importer code;
- `input_image_path` / `reference_image_paths` appear only in legacy compatibility code and tests;
- media import bridge responses expose `basename`, not full paths.

- [ ] **Step 5: Inspect git status**

```powershell
git status --short
```

Expected: only intended implementation files are modified. Preserve unrelated pre-existing `knowledge/gh/operations_knowledge.json` changes unless the user explicitly asks to touch them.

- [ ] **Step 6: Commit final verification fixes if any were needed**

If Step 1-4 required code changes, commit them:

```powershell
git add <changed-files>
git commit -m "test(vision): verify media import boundaries"
```

If no fixes were needed, do not create an empty commit.

## Manual Smoke In Rhino

Run after automated tests on a machine with Rhino and the managed companion:

1. Open RookVision and switch to Gallery.
2. Click `Add Media to Gallery`.
3. Select a PNG, JPG, WEBP, MP4, MOV, and WEBM, up to 20 total.
4. Confirm status rows use basenames only.
5. Confirm successful imports appear in Gallery mixed with generated artifacts.
6. Open an imported image modal and reveal it in its artifact folder.
7. Open an imported video modal and play it from the `video` role.
8. In the video picker, confirm imported videos expose `start_frame` and `end_frame`, not `poster`.
9. Use an imported image as a Studio source and generate.
10. Confirm generated output has the imported artifact ID in `parent_ids`.
