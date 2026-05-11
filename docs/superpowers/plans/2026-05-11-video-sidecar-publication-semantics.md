# Video Sidecar Publication Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe append-style artifact blob publication primitive and a video-specific sidecar publisher wrapper without wiring production extraction, UI, backfill, or video job integration.

**Architecture:** `ArtifactStore.AppendBlob(...)` owns generic storage mechanics and manifest atomicity. `VideoSidecarPublisher` owns video policy: only `poster`, `start_frame`, and `end_frame` can be appended to `generated_video` artifacts, and duplicate storage roles become idempotent skips for video workflows.

**Tech Stack:** C#/.NET, xUnit, existing `Rook.Artifacts.ArtifactStore`, existing `Rook.Services.Vision.Video.VideoMediaRoles`.

---

## Spec

Implement against:

- `docs/superpowers/specs/2026-05-11-video-sidecar-publication-semantics-design.md`

Keep these out of scope:

- no ffmpeg production invocation;
- no `VideoJobManager` integration;
- no Gallery or picker changes;
- no backfill execution;
- no installer changes;
- no provider calls;
- no replace/delete sidecar semantics.

## File Map

Modify:

- `src/Rook/Artifacts/Artifact.cs`
  - Add `AppendBlobResultCode` and `AppendBlobResult`.
- `src/Rook/Artifacts/ArtifactStore.cs`
  - Add `AppendBlob(...)`.
  - Reuse current role/extension/path validation rules.
  - Preserve existing `Create(...)`, `SetFlag(...)`, `Get(...)`, `List(...)`, and `GetBlobAbsolutePath(...)` behavior.
- `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`
  - Add append-blob tests near existing `SetFlag` and casing tests.

Create:

- `src/Rook/Services/Vision/Video/VideoSidecarPublisher.cs`
  - Add video-domain result codes and wrapper.
- `src/Rook.Tests/Services/Vision/Video/VideoSidecarPublisherTests.cs`
  - Add policy and mapping tests.

Do not modify:

- `src/Rook/Services/Vision/Video/VideoJobManager.cs`
- `src/Rook/UI/Vision/Resources/*`
- installer scripts
- provider implementations

## Task 1: Add Failing ArtifactStore Append Tests

**Files:**
- Modify: `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`
- Later implementation: `src/Rook/Artifacts/Artifact.cs`
- Later implementation: `src/Rook/Artifacts/ArtifactStore.cs`

- [ ] **Step 1: Add helper methods to `ArtifactStoreTests`**

Add these helpers near the existing helper methods at the top of `ArtifactStoreTests`:

```csharp
private string ArtifactDir(Guid id)
    => Directory.EnumerateDirectories(_root)
        .SelectMany(Directory.EnumerateDirectories)
        .Single(d => Path.GetFileName(d) == id.ToString("D"));

private string ManifestPath(Guid id)
    => Path.Combine(ArtifactDir(id), "manifest.json");

private string BlobPath(Guid id, string fileName)
    => Path.Combine(ArtifactDir(id), fileName);

private string ManifestText(Guid id)
    => File.ReadAllText(ManifestPath(id));
```

- [ ] **Step 2: Add failing append success test**

Add this test after the `SetFlag` tests and before `Create_WritesSnakeCaseFieldNames`:

```csharp
[Fact]
public void AppendBlob_Success_AddsBlobAndManifestRole()
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));

    var result = _store.AppendBlob(created.Id, "poster", Bytes("jpg"), "jpg");

    Assert.Equal(AppendBlobResultCode.Succeeded, result.Code);
    Assert.NotNull(result.Artifact);
    Assert.Equal(created.Id, result.Artifact!.Id);
    Assert.Contains(result.Artifact.Files, f => f.Role == "video" && f.Path == "video.mp4");
    Assert.Contains(result.Artifact.Files, f => f.Role == "poster" && f.Path == "poster.jpg");
    Assert.True(File.Exists(BlobPath(created.Id, "poster.jpg")));
    Assert.Equal("jpg", File.ReadAllText(BlobPath(created.Id, "poster.jpg")));

    var reloaded = _store.Get(created.Id);
    Assert.NotNull(reloaded);
    Assert.Contains(reloaded!.Files, f => f.Role == "poster" && f.Path == "poster.jpg");
    Assert.Equal(BlobPath(created.Id, "poster.jpg"), _store.GetBlobAbsolutePath(created.Id, "poster"));
}
```

- [ ] **Step 3: Add failing duplicate-role test**

```csharp
[Fact]
public void AppendBlob_DuplicateRole_ReturnsDuplicateRole_AndLeavesArtifactUnchanged()
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    var before = ManifestText(created.Id);

    var result = _store.AppendBlob(created.Id, "video", Bytes("new"), "mp4");

    Assert.Equal(AppendBlobResultCode.DuplicateRole, result.Code);
    Assert.Null(result.Artifact);
    Assert.Equal(before, ManifestText(created.Id));
    Assert.Equal("mp4", File.ReadAllText(BlobPath(created.Id, "video.mp4")));
    Assert.False(File.Exists(BlobPath(created.Id, "video.mp4.tmp")));
}
```

- [ ] **Step 4: Add failing validation tests**

```csharp
[Theory]
[InlineData("")]
[InlineData("UPPER")]
[InlineData("a/b")]
[InlineData("a.b")]
public void AppendBlob_InvalidRole_ReturnsInvalidRole_AndWritesNothing(string role)
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    var before = ManifestText(created.Id);

    var result = _store.AppendBlob(created.Id, role, Bytes("x"), "jpg");

    Assert.Equal(AppendBlobResultCode.InvalidRole, result.Code);
    Assert.Equal(before, ManifestText(created.Id));
    Assert.Equal(
        new[] { "manifest.json", "video.mp4" },
        Directory.EnumerateFiles(ArtifactDir(created.Id))
            .Select(Path.GetFileName)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray());
}

[Theory]
[InlineData("")]
[InlineData(".jpg")]
[InlineData("JPG")]
[InlineData("jpg.gz")]
public void AppendBlob_InvalidExtension_ReturnsInvalidExtension_AndWritesNothing(string extension)
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    var before = ManifestText(created.Id);

    var result = _store.AppendBlob(created.Id, "poster", Bytes("x"), extension);

    Assert.Equal(AppendBlobResultCode.InvalidExtension, result.Code);
    Assert.Equal(before, ManifestText(created.Id));
    Assert.Equal(
        new[] { "manifest.json", "video.mp4" },
        Directory.EnumerateFiles(ArtifactDir(created.Id))
            .Select(Path.GetFileName)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray());
}
```

- [ ] **Step 5: Add failing missing/corrupt artifact tests**

```csharp
[Fact]
public void AppendBlob_MissingArtifact_ReturnsArtifactNotFound()
{
    var result = _store.AppendBlob(Guid.NewGuid(), "poster", Bytes("x"), "jpg");

    Assert.Equal(AppendBlobResultCode.ArtifactNotFound, result.Code);
    Assert.Null(result.Artifact);
}

[Fact]
public void AppendBlob_CorruptManifest_ReturnsManifestReadFailed_AndWritesNothing()
{
    var id = Guid.NewGuid();
    var dir = CreateRawArtifactDir("2026-04-22", id);
    File.WriteAllBytes(Path.Combine(dir, "video.mp4"), Bytes("mp4"));
    WriteRawManifest(dir, "{ not valid json");

    var result = _store.AppendBlob(id, "poster", Bytes("x"), "jpg");

    Assert.Equal(AppendBlobResultCode.ManifestReadFailed, result.Code);
    Assert.Null(result.Artifact);
    Assert.Equal("{ not valid json", File.ReadAllText(Path.Combine(dir, "manifest.json")));
    Assert.False(File.Exists(Path.Combine(dir, "poster.jpg")));
}
```

- [ ] **Step 6: Add failing final-collision and loose-file tests**

```csharp
[Fact]
public void AppendBlob_FinalFileCollision_ReturnsFinalFileCollision_AndDoesNotOverwrite()
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    File.WriteAllText(BlobPath(created.Id, "poster.jpg"), "orphan");
    var before = ManifestText(created.Id);

    var result = _store.AppendBlob(created.Id, "poster", Bytes("new"), "jpg");

    Assert.Equal(AppendBlobResultCode.FinalFileCollision, result.Code);
    Assert.Null(result.Artifact);
    Assert.Equal(before, ManifestText(created.Id));
    Assert.Equal("orphan", File.ReadAllText(BlobPath(created.Id, "poster.jpg")));
    var loaded = _store.Get(created.Id);
    Assert.DoesNotContain(loaded!.Files, f => f.Role == "poster");
}

[Fact]
public void LooseFiles_AreIgnoredByReaders_UntilManifestReferencesThem()
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    File.WriteAllText(BlobPath(created.Id, "poster.jpg"), "orphan");

    var loaded = _store.Get(created.Id);

    Assert.NotNull(loaded);
    Assert.DoesNotContain(loaded!.Files, f => f.Role == "poster");
    Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(created.Id, "poster"));
}
```

- [ ] **Step 7: Add failing manifest-replace failure test**

This test uses an internal test hook that Task 2 will add to `ArtifactStore`.

```csharp
[Fact]
public void AppendBlob_ManifestReplaceFailure_ReturnsManifestReplaceFailed_WithValidOriginalManifest()
{
    var created = _store.Create("generated_video", OneBlob("video", "mp4", "mp4"));
    var before = ManifestText(created.Id);
    _store.AppendBlobManifestReplaceOverrideForTests = (_, _) =>
        throw new IOException("simulated replace failure");

    var result = _store.AppendBlob(created.Id, "poster", Bytes("jpg"), "jpg");

    Assert.Equal(AppendBlobResultCode.ManifestReplaceFailed, result.Code);
    Assert.Null(result.Artifact);
    Assert.Equal(before, ManifestText(created.Id));
    Assert.True(File.Exists(BlobPath(created.Id, "poster.jpg")));

    var loaded = _store.Get(created.Id);
    Assert.NotNull(loaded);
    Assert.DoesNotContain(loaded!.Files, f => f.Role == "poster");
    Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(created.Id, "poster"));
}
```

- [ ] **Step 8: Run failing ArtifactStore tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~ArtifactStoreTests
```

Expected:

- build fails because `AppendBlob`, `AppendBlobResultCode`, and `AppendBlobManifestReplaceOverrideForTests` do not exist yet.

- [ ] **Step 9: Commit failing tests**

```powershell
git add src\Rook.Tests\Artifacts\ArtifactStoreTests.cs
git commit -m "test: pin artifact append blob semantics"
```

## Task 2: Implement ArtifactStore.AppendBlob

**Files:**
- Modify: `src/Rook/Artifacts/Artifact.cs`
- Modify: `src/Rook/Artifacts/ArtifactStore.cs`
- Test: `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`

- [ ] **Step 1: Add append result types**

In `src/Rook/Artifacts/Artifact.cs`, after `BlobInput`, add:

```csharp
public enum AppendBlobResultCode
{
    Succeeded,
    ArtifactNotFound,
    ManifestReadFailed,
    InvalidRole,
    InvalidExtension,
    DuplicateRole,
    FinalFileCollision,
    StagedWriteFailed,
    FinalizeBlobFailed,
    ManifestReplaceFailed,
}

public sealed record AppendBlobResult(
    AppendBlobResultCode Code,
    Artifact? Artifact = null,
    string? Message = null)
{
    public bool Success => Code == AppendBlobResultCode.Succeeded;

    public static AppendBlobResult Succeeded(Artifact artifact) =>
        new(AppendBlobResultCode.Succeeded, artifact);

    public static AppendBlobResult Fail(
        AppendBlobResultCode code,
        string message) =>
        new(code, null, message);
}
```

- [ ] **Step 2: Add test hook and `AppendBlob` method skeleton**

In `ArtifactStore`, after the constructor, add:

```csharp
internal Action<string, string>? AppendBlobManifestReplaceOverrideForTests { get; set; }
```

After `SetFlag(...)` and before `GetBlobAbsolutePath(...)`, add:

```csharp
public AppendBlobResult AppendBlob(
    Guid id,
    string role,
    byte[] content,
    string fileExtension)
{
    try
    {
        ValidateRoleArg(role);
    }
    catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
    {
        return AppendBlobResult.Fail(AppendBlobResultCode.InvalidRole, ex.Message);
    }

    try
    {
        ValidateExtensionArg(fileExtension);
    }
    catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
    {
        return AppendBlobResult.Fail(AppendBlobResultCode.InvalidExtension, ex.Message);
    }

    if (content is null)
    {
        return AppendBlobResult.Fail(
            AppendBlobResultCode.StagedWriteFailed,
            "AppendBlob content is null.");
    }

    var dirs = FindFinalizedDirs(id);
    if (dirs.Count == 0)
        return AppendBlobResult.Fail(
            AppendBlobResultCode.ArtifactNotFound,
            $"Artifact '{id}' not found.");
    if (dirs.Count > 1)
        return AppendBlobResult.Fail(
            AppendBlobResultCode.ManifestReadFailed,
            DuplicateUuid(id).Message);

    var artifactDir = dirs[0];
    Artifact existing;
    try
    {
        existing = ReadArtifact(artifactDir);
    }
    catch (Exception ex)
    {
        return AppendBlobResult.Fail(
            AppendBlobResultCode.ManifestReadFailed,
            ex.Message);
    }

    if (existing.Files.Any(f => f.Role == role))
    {
        return AppendBlobResult.Fail(
            AppendBlobResultCode.DuplicateRole,
            $"Role '{role}' already exists in artifact '{id}'.");
    }

    var finalFileName = $"{role}.{fileExtension}";
    var finalPath = Path.Combine(artifactDir, finalFileName);
    if (File.Exists(finalPath))
    {
        return AppendBlobResult.Fail(
            AppendBlobResultCode.FinalFileCollision,
            $"File '{finalFileName}' already exists in artifact '{id}' without a manifest role.");
    }

    var stagedFileName = $"{role}.{Guid.NewGuid():N}.{fileExtension}.tmp";
    var stagedPath = Path.Combine(artifactDir, stagedFileName);

    try
    {
        File.WriteAllBytes(stagedPath, content);
    }
    catch (Exception ex)
    {
        return AppendBlobResult.Fail(
            AppendBlobResultCode.StagedWriteFailed,
            ex.Message);
    }

    try
    {
        File.Move(stagedPath, finalPath);
    }
    catch (Exception ex)
    {
        TryDeleteFile(stagedPath);
        return AppendBlobResult.Fail(
            AppendBlobResultCode.FinalizeBlobFailed,
            ex.Message);
    }

    var updatedFiles = existing.Files
        .Concat(new[] { new ArtifactFile(role, finalFileName) })
        .ToList();
    var updated = new Artifact(
        existing.Id,
        existing.Kind,
        existing.CreatedAt,
        updatedFiles,
        existing.ParentIds,
        existing.Metadata,
        existing.Flags);

    var manifestPath = Path.Combine(artifactDir, ManifestFileName);
    var tmpManifestPath = Path.Combine(artifactDir, ManifestFileName + ".tmp");

    try
    {
        File.WriteAllText(tmpManifestPath, SerializeManifest(updated));
        if (AppendBlobManifestReplaceOverrideForTests is not null)
        {
            AppendBlobManifestReplaceOverrideForTests(tmpManifestPath, manifestPath);
        }
        else
        {
            File.Replace(
                sourceFileName: tmpManifestPath,
                destinationFileName: manifestPath,
                destinationBackupFileName: null);
        }
    }
    catch (Exception ex)
    {
        TryDeleteFile(tmpManifestPath);
        return AppendBlobResult.Fail(
            AppendBlobResultCode.ManifestReplaceFailed,
            ex.Message);
    }

    return AppendBlobResult.Succeeded(updated);
}
```

- [ ] **Step 3: Add file cleanup helper**

Near other private helpers in `ArtifactStore`, add:

```csharp
private static void TryDeleteFile(string path)
{
    try
    {
        if (File.Exists(path))
            File.Delete(path);
    }
    catch { /* best-effort cleanup only */ }
}
```

- [ ] **Step 4: Run ArtifactStore tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~ArtifactStoreTests
```

Expected:

- all `ArtifactStoreTests` pass.

- [ ] **Step 5: Run focused storage regression**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ArtifactStoreTests|FullyQualifiedName~ArtifactOnlyVideoMediaResolverTests"
```

Expected:

- all selected tests pass.

- [ ] **Step 6: Commit storage implementation**

```powershell
git add src\Rook\Artifacts\Artifact.cs src\Rook\Artifacts\ArtifactStore.cs
git commit -m "feat: add atomic artifact blob append"
```

## Task 3: Add Failing VideoSidecarPublisher Tests

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Video/VideoSidecarPublisherTests.cs`
- Later implementation: `src/Rook/Services/Vision/Video/VideoSidecarPublisher.cs`

- [ ] **Step 1: Create test file**

Create `src/Rook.Tests/Services/Vision/Video/VideoSidecarPublisherTests.cs`:

```csharp
using System;
using System.IO;
using System.Linq;
using System.Text;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoSidecarPublisherTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly VideoSidecarPublisher _publisher;

        public VideoSidecarPublisherTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-sidecar-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _publisher = new VideoSidecarPublisher(_store);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private Artifact GeneratedImage()
            => _store.Create(
                "generated_image",
                new[] { new BlobInput("image", Bytes("png"), "png") });

        [Theory]
        [InlineData(VideoMediaRoles.Poster)]
        [InlineData(VideoMediaRoles.StartFrame)]
        [InlineData(VideoMediaRoles.EndFrame)]
        public void Publish_accepts_known_video_sidecar_roles(string role)
        {
            var video = GeneratedVideo();

            var result = _publisher.Publish(video.Id, role, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.Succeeded, result.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.Contains(loaded!.Files, f => f.Role == role && f.Path == $"{role}.jpg");
        }

        [Theory]
        [InlineData(VideoMediaRoles.Video)]
        [InlineData(VideoMediaRoles.Image)]
        [InlineData("reference")]
        [InlineData("bad role")]
        public void Publish_rejects_unsupported_roles_before_storage_append(string role)
        {
            var video = GeneratedVideo();

            var result = _publisher.Publish(video.Id, role, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.RejectedUnsupportedRole, result.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.DoesNotContain(loaded!.Files, f => f.Role == role);
        }

        [Fact]
        public void Publish_rejects_non_generated_video_artifact()
        {
            var image = GeneratedImage();

            var result = _publisher.Publish(image.Id, VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.RejectedWrongArtifactKind, result.Code);
            var loaded = _store.Get(image.Id);
            Assert.NotNull(loaded);
            Assert.DoesNotContain(loaded!.Files, f => f.Role == VideoMediaRoles.Poster);
        }

        [Fact]
        public void Publish_missing_artifact_returns_artifact_not_found()
        {
            var result = _publisher.Publish(Guid.NewGuid(), VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.ArtifactNotFound, result.Code);
        }

        [Fact]
        public void Publish_duplicate_role_maps_to_skipped_already_exists()
        {
            var video = GeneratedVideo();
            var first = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("one"), "jpg");
            Assert.Equal(VideoSidecarPublishResultCode.Succeeded, first.Code);

            var second = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("two"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.SkippedAlreadyExists, second.Code);
            var loaded = _store.Get(video.Id);
            Assert.NotNull(loaded);
            Assert.Single(loaded!.Files.Where(f => f.Role == VideoMediaRoles.Poster));
            Assert.Equal("one", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.Poster)));
        }

        [Fact]
        public void Publish_storage_failure_maps_to_storage_failed()
        {
            var video = GeneratedVideo();
            var artifactDir = Directory.EnumerateDirectories(_root)
                .SelectMany(Directory.EnumerateDirectories)
                .Single(d => Path.GetFileName(d) == video.Id.ToString("D"));
            File.WriteAllText(Path.Combine(artifactDir, "poster.jpg"), "orphan");

            var result = _publisher.Publish(video.Id, VideoMediaRoles.Poster, Bytes("jpg"), "jpg");

            Assert.Equal(VideoSidecarPublishResultCode.StorageFailed, result.Code);
            Assert.Equal(AppendBlobResultCode.FinalFileCollision, result.StorageCode);
        }
    }
}
```

- [ ] **Step 2: Run failing VideoSidecarPublisher tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VideoSidecarPublisherTests
```

Expected:

- build fails because `VideoSidecarPublisher`, `VideoSidecarPublishResultCode`, and `VideoSidecarPublishResult` do not exist.

- [ ] **Step 3: Commit failing video wrapper tests**

```powershell
git add src\Rook.Tests\Services\Vision\Video\VideoSidecarPublisherTests.cs
git commit -m "test: pin video sidecar publisher policy"
```

## Task 4: Implement VideoSidecarPublisher

**Files:**
- Create: `src/Rook/Services/Vision/Video/VideoSidecarPublisher.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/VideoSidecarPublisherTests.cs`

- [ ] **Step 1: Create `VideoSidecarPublisher.cs`**

Create `src/Rook/Services/Vision/Video/VideoSidecarPublisher.cs`:

```csharp
using System;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    public enum VideoSidecarPublishResultCode
    {
        Succeeded,
        SkippedAlreadyExists,
        RejectedUnsupportedRole,
        RejectedWrongArtifactKind,
        ArtifactNotFound,
        StorageFailed,
    }

    public sealed record VideoSidecarPublishResult(
        VideoSidecarPublishResultCode Code,
        Guid ArtifactId,
        string Role,
        AppendBlobResultCode? StorageCode = null,
        string? Message = null)
    {
        public bool Success => Code == VideoSidecarPublishResultCode.Succeeded;
    }

    public sealed class VideoSidecarPublisher
    {
        private const string GeneratedVideoKind = "generated_video";

        private readonly ArtifactStore _store;

        public VideoSidecarPublisher(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension)
        {
            if (!IsSupportedSidecarRole(role))
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.RejectedUnsupportedRole,
                    artifactId,
                    role,
                    Message: $"Role '{role ?? "<null>"}' is not a generated-video sidecar role.");
            }

            Artifact? artifact;
            try
            {
                artifact = _store.Get(artifactId);
            }
            catch (Exception ex)
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.StorageFailed,
                    artifactId,
                    role,
                    Message: ex.Message);
            }

            if (artifact is null)
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.ArtifactNotFound,
                    artifactId,
                    role,
                    Message: $"Artifact '{artifactId:D}' not found.");
            }

            if (!string.Equals(artifact.Kind, GeneratedVideoKind, StringComparison.Ordinal))
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.RejectedWrongArtifactKind,
                    artifactId,
                    role,
                    Message: $"Artifact '{artifactId:D}' has kind '{artifact.Kind}', not '{GeneratedVideoKind}'.");
            }

            var storage = _store.AppendBlob(artifactId, role, content, fileExtension);
            return storage.Code switch
            {
                AppendBlobResultCode.Succeeded =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.Succeeded,
                        artifactId,
                        role,
                        StorageCode: storage.Code),

                AppendBlobResultCode.DuplicateRole =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.SkippedAlreadyExists,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),

                AppendBlobResultCode.ArtifactNotFound =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.ArtifactNotFound,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),

                _ =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.StorageFailed,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),
            };
        }

        private static bool IsSupportedSidecarRole(string role) =>
            string.Equals(role, VideoMediaRoles.Poster, StringComparison.Ordinal)
            || string.Equals(role, VideoMediaRoles.StartFrame, StringComparison.Ordinal)
            || string.Equals(role, VideoMediaRoles.EndFrame, StringComparison.Ordinal);
    }
}
```

- [ ] **Step 2: Run VideoSidecarPublisher tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VideoSidecarPublisherTests
```

Expected:

- all `VideoSidecarPublisherTests` pass.

- [ ] **Step 3: Run focused sidecar publication suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ArtifactStoreTests|FullyQualifiedName~VideoSidecarPublisherTests"
```

Expected:

- all selected tests pass.

- [ ] **Step 4: Commit video wrapper implementation**

```powershell
git add src\Rook\Services\Vision\Video\VideoSidecarPublisher.cs
git commit -m "feat: add video sidecar publisher"
```

## Task 5: Boundary Verification And Review Handoff

**Files:**
- Read/verify only unless tests expose a real issue:
  - `src/Rook/Services/Vision/Video/VideoJobManager.cs`
  - `src/Rook/UI/Vision/Resources/app.js`
  - `src/Rook/UI/Vision/Resources/styles.css`
  - installer scripts
  - provider files

- [ ] **Step 1: Run focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~ArtifactStoreTests|FullyQualifiedName~VideoSidecarPublisherTests|FullyQualifiedName~ArtifactOnlyVideoMediaResolverTests"
```

Expected:

- all selected tests pass.

- [ ] **Step 2: Run existing video smoke slice**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VideoArtifactMaterializerTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoOpHandlerTests"
```

Expected:

- all selected tests pass.

- [ ] **Step 3: Run whitespace checks**

Run:

```powershell
git diff origin/main --check
git show --check --format=short HEAD
```

Expected:

- both commands exit 0.

- [ ] **Step 4: Run scope boundary scans**

Run:

```powershell
rg -n "AppendBlob|VideoSidecarPublisher" src\Rook\Services\Vision\Video\VideoJobManager.cs src\Rook\UI\Vision\Resources scripts mcp_server src\RookNative
```

Expected:

- no output. `rg` exit code 1 for no matches is acceptable.

Run:

```powershell
git diff --name-only origin/main...HEAD | rg "\.mp4$|\.exe$|installer|RookSetup\.iss"
```

Expected:

- no output. `rg` exit code 1 for no matches is acceptable.

Run:

```powershell
rg -n "ffmpeg|VideoJobManager|Gallery|picker|provider|backfill|replace: true|delete sidecar" src\Rook\Artifacts src\Rook\Services\Vision\Video\VideoSidecarPublisher.cs src\Rook.Tests\Artifacts src\Rook.Tests\Services\Vision\Video\VideoSidecarPublisherTests.cs
```

Expected:

- no production integration scope creep.
- `VideoJobManager`, `Gallery`, provider, picker, and backfill should not appear in implementation files.

- [ ] **Step 5: Check worktree status**

Run:

```powershell
git status --short --branch
```

Expected:

- clean worktree on the implementation branch.

- [ ] **Step 6: Prepare senior reviewer prompt**

Use this prompt:

```text
Please review the Video Sidecar Publication Semantics implementation against docs/superpowers/specs/2026-05-11-video-sidecar-publication-semantics-design.md.

Focus areas:
- ArtifactStore.AppendBlob must stay generic and avoid video-domain policy.
- VideoSidecarPublisher must own video-specific policy: generated_video only, poster/start_frame/end_frame only.
- Storage duplicate roles must be strict DuplicateRole failures; video wrapper duplicate roles should become SkippedAlreadyExists.
- AppendBlob must never publish a manifest entry before the referenced blob exists at its final path.
- Manifest replace failure must leave the original manifest valid and not referencing the new blob; an orphan final blob is acceptable.
- Final-file collision must not overwrite loose files.
- Readers must continue to trust manifest entries only, not loose files.
- The implementation must not wire production extraction, VideoJobManager, Gallery, picker, providers, installer, backfill, replacement, or deletion behavior.

Please report critical, important, and minor issues, and give a readiness verdict for moving to the poster thumbnail producer slice.
```

## Self-Review Checklist For The Implementer

Before asking for review:

- [ ] `ArtifactStore.AppendBlob(...)` returns structured codes and does not throw for expected duplicate/missing/corrupt/collision cases.
- [ ] `AppendBlob(...)` reuses current role and extension validation patterns.
- [ ] `AppendBlob(...)` moves the blob to final path before manifest replacement.
- [ ] Manifest replacement uses `File.Replace(...)`.
- [ ] Manifest replacement failure leaves original manifest valid.
- [ ] `VideoSidecarPublisher` does not call extraction, providers, `VideoJobManager`, Gallery, picker, or GH NLE code.
- [ ] No committed media or binary files.
- [ ] No installer changes.
- [ ] Worktree clean.

## Plan Self-Review

Spec coverage:

- Generic append storage primitive: Task 1 and Task 2.
- Video wrapper policy and result mapping: Task 3 and Task 4.
- Strict duplicate behavior: Task 1, Task 2, Task 3, Task 4.
- Observable atomicity: Task 1 and Task 2.
- No production integration scope creep: Task 5.
- Metadata/provenance deferral: no implementation task adds file-level metadata.

Placeholder scan:

- No placeholder tokens or vague future-work markers are intentionally present.
- Scope exclusions are explicit rather than placeholders.

Type consistency:

- Storage result types are `AppendBlobResultCode` and `AppendBlobResult`.
- Video result types are `VideoSidecarPublishResultCode` and `VideoSidecarPublishResult`.
- Storage method is `ArtifactStore.AppendBlob(...)`.
- Video wrapper method is `VideoSidecarPublisher.Publish(...)`.
