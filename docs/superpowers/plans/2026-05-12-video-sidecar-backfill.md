# Video Sidecar Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill missing `poster`, `start_frame`, and `end_frame` sidecars for a bounded number of existing generated-video artifacts from their saved local MP4 blobs during startup.

**Architecture:** Add a role-targeted frame sidecar producer overload, then add an internal `VideoSidecarBackfillService` that scans artifacts, plans missing roles, enforces cap/budget checks, and delegates extraction/publication to the existing poster/frame producers. Wire the service into `VideoSubsystemBundle` and schedule it through a separate `RookSubsystemRoot.BackfillVideoSidecarsOnce()` async one-shot guard invoked by `RookPlugin` after the existing startup reconcile path.

**Tech Stack:** C# managed companion, `ArtifactStore`, existing video sidecar producers, xUnit tests, no Rhino runtime requirement for the focused suite.

---

## File Structure

- Modify `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`
  - Add internal role-targeted overload.
  - Add `UnsupportedRole` result code.
  - Validate requested frame roles before resolving video blob or ffmpeg.

- Create `src/Rook/Services/Vision/Video/VideoSidecarBackfillService.cs`
  - Define backfill options, result records, clock seam, service interface, and service implementation.
  - Enforce eligible-artifact cap and elapsed budget.
  - Call poster producer only for missing `poster`.
  - Call frame producer one role per call for missing `start_frame` and `end_frame`.

- Modify `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs`
  - Add `SidecarBackfill` to `VideoSubsystemBundle`.
  - Construct `VideoSidecarBackfillService` from the shared `ArtifactStore` and existing producer types.
  - Add optional test override for the backfill service.

- Modify `src/Rook/RookSubsystemRoot.cs`
  - Add separate backfill one-shot flag.
  - Add scheduler seam and startup options.
  - Implement `BackfillVideoSidecarsOnce(...)` with "fired once scheduling succeeds" semantics.

- Modify `src/Rook/RookPlugin.cs`
  - Invoke `BackfillVideoSidecarsOnce(...)` after video/image startup reconcile blocks.
  - Keep wrapper non-fatal and async scheduling-only.

- Modify `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`
  - Add targeted-role tests.
  - Extend existing fakes with call counters.

- Create `src/Rook.Tests/Services/Vision/Video/VideoSidecarBackfillServiceTests.cs`
  - Cover eligibility, cap, budget, per-role attempts, and structured diagnostics.

- Modify `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`
  - Cover bundle wiring and root one-shot guard behavior.

- Modify `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`
  - Pin startup source wrapper separate from `ReconcileVideoJobsOnce()`.

- Modify `docs/rook_docs/video-thumbnail-roadmap.md`
  - Mark Slice 5 done after implementation verification.

- Modify `docs/rook_docs/work-queue.md`
  - Add completion note after implementation verification.

---

### Task 1: Role-Targeted Frame Producer

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoFrameSidecarProducerTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs`

- [ ] **Step 1: Add failing tests for role-targeted frame production**

Add these tests inside `VideoFrameSidecarProducerTests` before the helper methods:

```csharp
[Fact]
public async Task TryPublishFrameSidecarsAsync_TargetedEndOnlyPublishesOnlyEnd()
{
    var video = GeneratedVideo();
    var extractor = new FakeFrameExtractor();
    var publisher = new FakeFrameSidecarPublisher();
    var producer = CreateProducer(extractor: extractor, publisher: publisher);

    var result = await producer.TryPublishFrameSidecarsAsync(
        video.Id,
        new[] { VideoMediaRoles.EndFrame },
        CancellationToken.None);

    var roleResult = Assert.Single(result.RoleResults);
    Assert.Equal(VideoMediaRoles.EndFrame, roleResult.Role);
    Assert.Equal(VideoFrameSelectorKind.Last, roleResult.Selector.Kind);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, roleResult.Code);
    Assert.Equal(new[] { VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
    Assert.Equal(new[] { VideoMediaRoles.EndFrame }, publisher.Roles);
    Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.StartFrame);
    Assert.Equal("end jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.EndFrame)));
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_TargetedStartOnlyPublishesOnlyStart()
{
    var video = GeneratedVideo();
    var extractor = new FakeFrameExtractor();
    var publisher = new FakeFrameSidecarPublisher();
    var producer = CreateProducer(extractor: extractor, publisher: publisher);

    var result = await producer.TryPublishFrameSidecarsAsync(
        video.Id,
        new[] { VideoMediaRoles.StartFrame },
        CancellationToken.None);

    var roleResult = Assert.Single(result.RoleResults);
    Assert.Equal(VideoMediaRoles.StartFrame, roleResult.Role);
    Assert.Equal(VideoFrameSelectorKind.First, roleResult.Selector.Kind);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, roleResult.Code);
    Assert.Equal(new[] { VideoFrameSelectorKind.First }, extractor.Selectors.Select(s => s.Kind));
    Assert.Equal(new[] { VideoMediaRoles.StartFrame }, publisher.Roles);
    Assert.Equal("start jpg", File.ReadAllText(_store.GetBlobAbsolutePath(video.Id, VideoMediaRoles.StartFrame)));
    Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == VideoMediaRoles.EndFrame);
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_AllUnknownRolesDoesNotResolveVideoOrFfmpeg()
{
    var video = GeneratedVideo();
    var resolver = FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe"));
    var extractor = new FakeFrameExtractor();
    var tempFiles = new FakeFrameTempFiles(
        Path.Combine(_root, "tmp", "start.jpg"),
        Path.Combine(_root, "tmp", "end.jpg"));
    var producer = CreateProducer(
        resolver: resolver,
        extractor: extractor,
        tempFiles: tempFiles);

    var result = await producer.TryPublishFrameSidecarsAsync(
        video.Id,
        new[] { "bogus_role" },
        CancellationToken.None);

    var roleResult = Assert.Single(result.RoleResults);
    Assert.Equal("bogus_role", roleResult.Role);
    Assert.Equal(VideoFrameSidecarRoleResultCode.UnsupportedRole, roleResult.Code);
    Assert.Equal(0, resolver.ResolveCount);
    Assert.Equal(0, tempFiles.CreateCallCount);
    Assert.Empty(extractor.Selectors);
    Assert.DoesNotContain(_store.Get(video.Id)!.Files, f => f.Role == "bogus_role");
}

[Fact]
public async Task TryPublishFrameSidecarsAsync_MixedUnknownAndKnownReportsUnknownAndAttemptsKnown()
{
    var video = GeneratedVideo();
    var resolver = FakeFrameFfmpegResolver.Found(Path.Combine(_root, "tools", "ffmpeg.exe"));
    var extractor = new FakeFrameExtractor();
    var producer = CreateProducer(resolver: resolver, extractor: extractor);

    var result = await producer.TryPublishFrameSidecarsAsync(
        video.Id,
        new[] { "bogus_role", VideoMediaRoles.EndFrame },
        CancellationToken.None);

    Assert.Equal(new[] { "bogus_role", VideoMediaRoles.EndFrame }, result.RoleResults.Select(r => r.Role));
    Assert.Equal(VideoFrameSidecarRoleResultCode.UnsupportedRole, result.RoleResults[0].Code);
    Assert.Equal(VideoFrameSidecarRoleResultCode.Published, result.RoleResults[1].Code);
    Assert.Equal(1, resolver.ResolveCount);
    Assert.Equal(new[] { VideoFrameSelectorKind.Last }, extractor.Selectors.Select(s => s.Kind));
}
```

Extend `FakeFrameFfmpegResolver` with a counter:

```csharp
public int ResolveCount { get; private set; }

public FfmpegBinaryResolution Resolve()
{
    ResolveCount++;
    if (ThrowOnResolve is not null)
        throw ThrowOnResolve;
    return _resolution;
}
```

Extend `FakeFrameTempFiles` with a counter:

```csharp
public int CreateCallCount { get; private set; }

public string CreateFrameTempPath(Guid artifactId, string role)
{
    CreateCallCount++;
    if (role == VideoMediaRoles.StartFrame && ThrowOnCreateStart is not null)
        throw ThrowOnCreateStart;
    if (role == VideoMediaRoles.EndFrame && ThrowOnCreateEnd is not null)
        throw ThrowOnCreateEnd;
    return role == VideoMediaRoles.StartFrame ? StartPath : EndPath;
}
```

- [ ] **Step 2: Run targeted tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoFrameSidecarProducerTests"
```

Expected: compile fails because `UnsupportedRole` and the role-targeted overload do not exist.

- [ ] **Step 3: Add the role-targeted producer API**

In `VideoFrameSidecarProducer.cs`, add the enum value:

```csharp
UnsupportedRole,
```

Update `IVideoFrameSidecarProducer`:

```csharp
internal interface IVideoFrameSidecarProducer
{
    Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
        Guid artifactId,
        CancellationToken cancellationToken);

    Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
        Guid artifactId,
        IReadOnlyList<string> roles,
        CancellationToken cancellationToken);
}
```

Replace the current public method body with a delegating call:

```csharp
public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
    Guid artifactId,
    CancellationToken cancellationToken)
    => TryPublishFrameSidecarsAsync(
        artifactId,
        new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
        cancellationToken);
```

Add the overload below it:

```csharp
public async Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
    Guid artifactId,
    IReadOnlyList<string> roles,
    CancellationToken cancellationToken)
{
    var rolePlans = CreateRolePlans(roles);
    var unsupported = rolePlans
        .Where(p => p.UnsupportedResult is not null)
        .Select(p => p.UnsupportedResult!)
        .ToList();
    var supportedPlans = rolePlans
        .Where(p => p.UnsupportedResult is null)
        .ToList();

    if (supportedPlans.Count == 0)
        return new VideoFrameSidecarResult(artifactId, unsupported);

    string videoPath;
    try
    {
        videoPath = _store.GetBlobAbsolutePath(artifactId, VideoMediaRoles.Video);
    }
    catch (Exception ex)
    {
        var failures = ResultsForAll(
            supportedPlans,
            VideoFrameSidecarRoleResultCode.VideoBlobUnavailable,
            ex.Message,
            ex.ToString());
        return new VideoFrameSidecarResult(
            artifactId,
            unsupported.Concat(failures).ToList());
    }

    FfmpegBinaryResolution ffmpeg;
    try
    {
        ffmpeg = _ffmpegResolver.Resolve();
    }
    catch (Exception ex)
    {
        var failures = ResultsForAll(
            supportedPlans,
            VideoFrameSidecarRoleResultCode.FinalizerFailed,
            ex.Message,
            ex.ToString());
        return new VideoFrameSidecarResult(
            artifactId,
            unsupported.Concat(failures).ToList());
    }

    if (!ffmpeg.Success || string.IsNullOrWhiteSpace(ffmpeg.Path))
    {
        var failures = ResultsForAll(
            supportedPlans,
            VideoFrameSidecarRoleResultCode.FfmpegMissing,
            ffmpeg.Message,
            ffmpeg.ErrorCode?.ToString());
        return new VideoFrameSidecarResult(
            artifactId,
            unsupported.Concat(failures).ToList());
    }

    var results = new List<VideoFrameSidecarRoleResult>(rolePlans.Count);
    results.AddRange(unsupported);
    foreach (var plan in supportedPlans)
    {
        var result = await TryPublishRoleAsync(
                artifactId,
                videoPath,
                ffmpeg.Path!,
                plan,
                cancellationToken)
            .ConfigureAwait(false);
        results.Add(result);
    }

    return new VideoFrameSidecarResult(artifactId, results);
}
```

Replace `CreateRolePlans()` with:

```csharp
private static List<VideoFrameSidecarRolePlan> CreateRolePlans(IReadOnlyList<string> roles)
{
    if (roles is null || roles.Count == 0)
        return new List<VideoFrameSidecarRolePlan>();

    var plans = new List<VideoFrameSidecarRolePlan>(roles.Count);
    foreach (var role in roles)
    {
        if (string.Equals(role, VideoMediaRoles.StartFrame, StringComparison.Ordinal))
        {
            plans.Add(new VideoFrameSidecarRolePlan(
                VideoMediaRoles.StartFrame,
                VideoFrameSelector.First,
                UnsupportedResult: null));
        }
        else if (string.Equals(role, VideoMediaRoles.EndFrame, StringComparison.Ordinal))
        {
            plans.Add(new VideoFrameSidecarRolePlan(
                VideoMediaRoles.EndFrame,
                VideoFrameSelector.Last,
                UnsupportedResult: null));
        }
        else
        {
            var unsupportedRole = role ?? "<null>";
            plans.Add(new VideoFrameSidecarRolePlan(
                unsupportedRole,
                VideoFrameSelector.FrameIndex(0),
                VideoFrameSidecarRoleResult.From(
                    unsupportedRole,
                    VideoFrameSelector.FrameIndex(0),
                    VideoFrameSidecarRoleResultCode.UnsupportedRole,
                    $"Role '{unsupportedRole}' is not a supported frame sidecar role.")));
        }
    }

    return plans;
}
```

Replace the private record with:

```csharp
private sealed record VideoFrameSidecarRolePlan(
    string Role,
    VideoFrameSelector Selector,
    VideoFrameSidecarRoleResult? UnsupportedResult);
```

Update the existing `FakeFrameProducer` in
`src/Rook.Tests/Services/Vision/Video/VideoJobManagerTests.cs` to implement the
new overload without changing existing manager-test behavior:

```csharp
public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
    Guid artifactId,
    IReadOnlyList<string> roles,
    CancellationToken cancellationToken)
    => TryPublishFrameSidecarsAsync(artifactId, cancellationToken);
```

- [ ] **Step 4: Run targeted tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoFrameSidecarProducerTests"
```

Expected: all `VideoFrameSidecarProducerTests` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src\Rook\Services\Vision\Video\VideoFrameSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\VideoFrameSidecarProducerTests.cs src\Rook.Tests\Services\Vision\Video\VideoJobManagerTests.cs
git commit -m "Add role-targeted video frame sidecars"
```

---

### Task 2: Backfill Service

**Files:**
- Create: `src/Rook/Services/Vision/Video/VideoSidecarBackfillService.cs`
- Create: `src/Rook.Tests/Services/Vision/Video/VideoSidecarBackfillServiceTests.cs`

- [ ] **Step 1: Write failing backfill service tests**

Create `VideoSidecarBackfillServiceTests.cs`:

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
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoSidecarBackfillServiceTests : IDisposable
    {
        private readonly string _root;
        private readonly ArtifactStore _store;
        private readonly FakePosterProducer _poster = new();
        private readonly FakeFrameProducer _frames = new();
        private readonly FakeBackfillClock _clock;

        public VideoSidecarBackfillServiceTests()
        {
            _root = Path.Combine(Path.GetTempPath(), $"rook-video-backfill-test-{Guid.NewGuid():N}");
            _store = new ArtifactStore(_root);
            _clock = new FakeBackfillClock(DateTimeOffset.UtcNow);
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsNonGeneratedVideoWithoutConsumingCap()
        {
            _store.Create("generated_image", new[] { new BlobInput("image", Bytes("png"), "png") });
            var video = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(1, TimeSpan.FromMinutes(1)),
                CancellationToken.None);

            Assert.Equal(2, result.ScannedArtifacts);
            Assert.Equal(1, result.EligibleArtifacts);
            Assert.Equal(1, result.ArtifactsAttempted);
            Assert.Equal(video.Id, Assert.Single(_poster.ArtifactIds));
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsGeneratedVideoWithoutVideoRole()
        {
            var artifact = _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg") });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedNoVideoRole, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsGeneratedVideoWithUnreadableVideoBlob()
        {
            var artifact = GeneratedVideo();
            File.Delete(_store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video));
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedVideoBlobUnavailable, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_SkipsArtifactWithAllRolesPresent()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                    new BlobInput(VideoMediaRoles.EndFrame, Bytes("end"), "jpg"),
                });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(VideoSidecarBackfillArtifactResultCode.SkippedNoMissingRoles, artifactResult.Code);
            Assert.Empty(_poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_PosterOnlyMissingRunsOnlyPoster()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                    new BlobInput(VideoMediaRoles.EndFrame, Bytes("end"), "jpg"),
                });
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
            Assert.Equal(1, result.RoleAttempts);
            Assert.Equal(1, result.RolesPublished);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_EndOnlyMissingRunsOnlyEndFrame()
        {
            var artifact = _store.Create(
                "generated_video",
                new[]
                {
                    new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4"),
                    new BlobInput(VideoMediaRoles.Poster, Bytes("poster"), "jpg"),
                    new BlobInput(VideoMediaRoles.StartFrame, Bytes("start"), "jpg"),
                });
            var service = CreateService();

            await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var request = Assert.Single(_frames.Requests);
            Assert.Equal(artifact.Id, request.ArtifactId);
            Assert.Equal(new[] { VideoMediaRoles.EndFrame }, request.Roles);
            Assert.Empty(_poster.ArtifactIds);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_MissingAllRolesAttemptsDeterministicOrderOneFrameRolePerCall()
        {
            var artifact = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(
                new[] { VideoMediaRoles.Poster, VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                artifactResult.RoleResults.Select(r => r.Role));
            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Equal(2, _frames.Requests.Count);
            Assert.Equal(new[] { VideoMediaRoles.StartFrame }, _frames.Requests[0].Roles);
            Assert.Equal(new[] { VideoMediaRoles.EndFrame }, _frames.Requests[1].Roles);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_MaxArtifactsCountsEligibleArtifactsOnly()
        {
            _store.Create("generated_image", new[] { new BlobInput("image", Bytes("png"), "png") });
            var first = GeneratedVideo();
            var second = GeneratedVideo();
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(1, TimeSpan.FromMinutes(1)),
                CancellationToken.None);

            Assert.True(result.StoppedByCap);
            Assert.Equal(1, result.EligibleArtifacts);
            Assert.Single(_poster.ArtifactIds);
            Assert.Contains(_poster.ArtifactIds[0], new[] { first.Id, second.Id });
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_BudgetStopsBeforeStartingNextRole()
        {
            var artifact = GeneratedVideo();
            _poster.OnPublish = () => _clock.Advance(TimeSpan.FromMinutes(5));
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                new VideoSidecarBackfillOptions(10, TimeSpan.FromSeconds(1)),
                CancellationToken.None);

            Assert.True(result.BudgetExhausted);
            Assert.Equal(new[] { artifact.Id }, _poster.ArtifactIds);
            Assert.Empty(_frames.Requests);
        }

        [Fact]
        public async Task BackfillMissingSidecarsAsync_RoleFailureDoesNotBlockLaterRole()
        {
            var artifact = GeneratedVideo();
            _poster.ResultCode = VideoPosterSidecarResultCode.ExtractionFailed;
            var service = CreateService();

            var result = await service.BackfillMissingSidecarsAsync(
                VideoSidecarBackfillOptions.StartupDefault,
                CancellationToken.None);

            var artifactResult = Assert.Single(result.Artifacts, a => a.ArtifactId == artifact.Id);
            Assert.Equal(3, artifactResult.RoleResults.Count);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Failed, artifactResult.RoleResults[0].Code);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Published, artifactResult.RoleResults[1].Code);
            Assert.Equal(VideoSidecarBackfillRoleResultCode.Published, artifactResult.RoleResults[2].Code);
        }

        private VideoSidecarBackfillService CreateService()
            => new VideoSidecarBackfillService(_store, _poster, _frames, _clock);

        private Artifact GeneratedVideo()
            => _store.Create(
                "generated_video",
                new[] { new BlobInput(VideoMediaRoles.Video, Bytes("mp4"), "mp4") });

        private static byte[] Bytes(string value) => Encoding.UTF8.GetBytes(value);

        private sealed class FakePosterProducer : IVideoPosterSidecarProducer
        {
            public List<Guid> ArtifactIds { get; } = new();
            public VideoPosterSidecarResultCode ResultCode { get; set; } =
                VideoPosterSidecarResultCode.Published;
            public Action? OnPublish { get; set; }

            public Task<VideoPosterSidecarResult> TryPublishPosterAsync(
                Guid artifactId,
                CancellationToken cancellationToken)
            {
                ArtifactIds.Add(artifactId);
                OnPublish?.Invoke();
                return Task.FromResult(VideoPosterSidecarResult.From(ResultCode, artifactId));
            }
        }

        private sealed class FakeFrameProducer : IVideoFrameSidecarProducer
        {
            public List<FrameRequest> Requests { get; } = new();

            public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
                Guid artifactId,
                CancellationToken cancellationToken)
                => TryPublishFrameSidecarsAsync(
                    artifactId,
                    new[] { VideoMediaRoles.StartFrame, VideoMediaRoles.EndFrame },
                    cancellationToken);

            public Task<VideoFrameSidecarResult> TryPublishFrameSidecarsAsync(
                Guid artifactId,
                IReadOnlyList<string> roles,
                CancellationToken cancellationToken)
            {
                Requests.Add(new FrameRequest(artifactId, roles.ToArray()));
                return Task.FromResult(new VideoFrameSidecarResult(
                    artifactId,
                    roles.Select(role => VideoFrameSidecarRoleResult.From(
                            role,
                            role == VideoMediaRoles.EndFrame
                                ? VideoFrameSelector.Last
                                : VideoFrameSelector.First,
                            VideoFrameSidecarRoleResultCode.Published))
                        .ToList()));
            }
        }

        private sealed record FrameRequest(Guid ArtifactId, IReadOnlyList<string> Roles);

        private sealed class FakeBackfillClock : IVideoSidecarBackfillClock
        {
            public FakeBackfillClock(DateTimeOffset now)
            {
                UtcNow = now;
            }

            public DateTimeOffset UtcNow { get; private set; }

            public void Advance(TimeSpan duration)
            {
                UtcNow = UtcNow.Add(duration);
            }
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoSidecarBackfillServiceTests"
```

Expected: compile fails because the backfill service types do not exist.

- [ ] **Step 3: Implement the backfill service**

Create `VideoSidecarBackfillService.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    internal sealed record VideoSidecarBackfillOptions(int MaxArtifacts, TimeSpan MaxElapsed)
    {
        public static VideoSidecarBackfillOptions StartupDefault { get; } =
            new VideoSidecarBackfillOptions(10, TimeSpan.FromSeconds(10));
    }

    internal enum VideoSidecarBackfillArtifactResultCode
    {
        Attempted,
        SkippedNotGeneratedVideo,
        SkippedNoVideoRole,
        SkippedVideoBlobUnavailable,
        SkippedNoMissingRoles,
        StoppedByBudget,
    }

    internal enum VideoSidecarBackfillRoleResultCode
    {
        Published,
        SkippedAlreadyExists,
        Failed,
        NotStartedBudgetExhausted,
    }

    internal sealed record VideoSidecarBackfillRoleResult(
        string Role,
        VideoSidecarBackfillRoleResultCode Code,
        string? Message = null,
        string? Diagnostic = null);

    internal sealed record VideoSidecarBackfillArtifactResult(
        Guid ArtifactId,
        VideoSidecarBackfillArtifactResultCode Code,
        IReadOnlyList<string> MissingRoles,
        IReadOnlyList<VideoSidecarBackfillRoleResult> RoleResults,
        string? Message = null);

    internal sealed record VideoSidecarBackfillResult(
        int ScannedArtifacts,
        int EligibleArtifacts,
        int ArtifactsSkipped,
        int ArtifactsAttempted,
        int RoleAttempts,
        int RolesPublished,
        int RolesSkippedAlreadyPresent,
        int RoleFailures,
        bool StoppedByCap,
        bool BudgetExhausted,
        IReadOnlyList<VideoSidecarBackfillArtifactResult> Artifacts)
    {
        public string ToTraceSummary()
            => $"scanned={ScannedArtifacts} eligible={EligibleArtifacts} " +
               $"attempted={ArtifactsAttempted} roles={RoleAttempts} " +
               $"published={RolesPublished} failed={RoleFailures} " +
               $"cap={StoppedByCap} budget={BudgetExhausted}";
    }

    internal interface IVideoSidecarBackfillClock
    {
        DateTimeOffset UtcNow { get; }
    }

    internal sealed class SystemVideoSidecarBackfillClock : IVideoSidecarBackfillClock
    {
        public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
    }

    internal interface IVideoSidecarBackfillService
    {
        Task<VideoSidecarBackfillResult> BackfillMissingSidecarsAsync(
            VideoSidecarBackfillOptions options,
            CancellationToken cancellationToken);
    }

    internal sealed class VideoSidecarBackfillService : IVideoSidecarBackfillService
    {
        private const string GeneratedVideoKind = "generated_video";
        private const int MaxDiagnosticLength = 2048;

        private readonly ArtifactStore _store;
        private readonly IVideoPosterSidecarProducer _posterProducer;
        private readonly IVideoFrameSidecarProducer _frameProducer;
        private readonly IVideoSidecarBackfillClock _clock;

        public VideoSidecarBackfillService(
            ArtifactStore store,
            IVideoPosterSidecarProducer posterProducer,
            IVideoFrameSidecarProducer frameProducer,
            IVideoSidecarBackfillClock? clock = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _posterProducer = posterProducer ?? throw new ArgumentNullException(nameof(posterProducer));
            _frameProducer = frameProducer ?? throw new ArgumentNullException(nameof(frameProducer));
            _clock = clock ?? new SystemVideoSidecarBackfillClock();
        }

        public async Task<VideoSidecarBackfillResult> BackfillMissingSidecarsAsync(
            VideoSidecarBackfillOptions options,
            CancellationToken cancellationToken)
        {
            if (options.MaxArtifacts <= 0)
                return EmptyResult();

            var startedAt = _clock.UtcNow;
            var artifactResults = new List<VideoSidecarBackfillArtifactResult>();
            var scanned = 0;
            var eligible = 0;
            var attempted = 0;
            var stoppedByCap = false;
            var budgetExhausted = false;

            foreach (var artifact in _store.List())
            {
                scanned++;
                if (!string.Equals(artifact.Kind, GeneratedVideoKind, StringComparison.Ordinal))
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNotGeneratedVideo,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                if (!artifact.Files.Any(f => f.Role == VideoMediaRoles.Video))
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNoVideoRole,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                try
                {
                    _ = _store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video);
                }
                catch (Exception ex)
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedVideoBlobUnavailable,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>(),
                        Truncate(ex.Message)));
                    continue;
                }

                if (eligible >= options.MaxArtifacts)
                {
                    stoppedByCap = true;
                    break;
                }

                eligible++;
                if (IsBudgetExhausted(startedAt, options))
                {
                    budgetExhausted = true;
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.StoppedByBudget,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    break;
                }

                var missingRoles = MissingRoles(artifact);
                if (missingRoles.Count == 0)
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNoMissingRoles,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                attempted++;
                var roleResults = new List<VideoSidecarBackfillRoleResult>();

                foreach (var role in missingRoles)
                {
                    if (IsBudgetExhausted(startedAt, options))
                    {
                        budgetExhausted = true;
                        break;
                    }

                    roleResults.Add(await TryBackfillRoleAsync(
                            artifact.Id,
                            role,
                            cancellationToken)
                        .ConfigureAwait(false));
                }

                artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                    artifact.Id,
                    VideoSidecarBackfillArtifactResultCode.Attempted,
                    missingRoles,
                    roleResults));

                if (budgetExhausted)
                    break;
            }

            return BuildResult(
                scanned,
                eligible,
                attempted,
                stoppedByCap,
                budgetExhausted,
                artifactResults);
        }

        private async Task<VideoSidecarBackfillRoleResult> TryBackfillRoleAsync(
            Guid artifactId,
            string role,
            CancellationToken cancellationToken)
        {
            try
            {
                if (role == VideoMediaRoles.Poster)
                {
                    var result = await _posterProducer.TryPublishPosterAsync(
                            artifactId,
                            cancellationToken)
                        .ConfigureAwait(false);
                    return FromPoster(result);
                }

                var frameResult = await _frameProducer.TryPublishFrameSidecarsAsync(
                        artifactId,
                        new[] { role },
                        cancellationToken)
                    .ConfigureAwait(false);
                var roleResult = frameResult.RoleResults.FirstOrDefault();
                return roleResult is null
                    ? Failed(role, "Frame sidecar producer returned no role result.", null)
                    : FromFrame(roleResult);
            }
            catch (Exception ex)
            {
                return Failed(role, ex.Message, ex.ToString());
            }
        }

        private static List<string> MissingRoles(Artifact artifact)
        {
            var existing = new HashSet<string>(
                artifact.Files.Select(f => f.Role),
                StringComparer.Ordinal);
            var missing = new List<string>(3);
            if (!existing.Contains(VideoMediaRoles.Poster))
                missing.Add(VideoMediaRoles.Poster);
            if (!existing.Contains(VideoMediaRoles.StartFrame))
                missing.Add(VideoMediaRoles.StartFrame);
            if (!existing.Contains(VideoMediaRoles.EndFrame))
                missing.Add(VideoMediaRoles.EndFrame);
            return missing;
        }

        private bool IsBudgetExhausted(DateTimeOffset startedAt, VideoSidecarBackfillOptions options)
            => options.MaxElapsed > TimeSpan.Zero
               && _clock.UtcNow - startedAt >= options.MaxElapsed;

        private static VideoSidecarBackfillRoleResult FromPoster(VideoPosterSidecarResult result)
            => result.Code switch
            {
                VideoPosterSidecarResultCode.Published =>
                    new VideoSidecarBackfillRoleResult(VideoMediaRoles.Poster, VideoSidecarBackfillRoleResultCode.Published, result.Message),
                VideoPosterSidecarResultCode.SkippedAlreadyExists =>
                    new VideoSidecarBackfillRoleResult(VideoMediaRoles.Poster, VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists, result.Message),
                _ => Failed(VideoMediaRoles.Poster, result.Message, result.Diagnostic),
            };

        private static VideoSidecarBackfillRoleResult FromFrame(VideoFrameSidecarRoleResult result)
            => result.Code switch
            {
                VideoFrameSidecarRoleResultCode.Published =>
                    new VideoSidecarBackfillRoleResult(result.Role, VideoSidecarBackfillRoleResultCode.Published, result.Message),
                VideoFrameSidecarRoleResultCode.SkippedAlreadyExists =>
                    new VideoSidecarBackfillRoleResult(result.Role, VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists, result.Message),
                _ => Failed(result.Role, result.Message, result.Diagnostic),
            };

        private static VideoSidecarBackfillRoleResult Failed(string role, string? message, string? diagnostic)
            => new VideoSidecarBackfillRoleResult(
                role,
                VideoSidecarBackfillRoleResultCode.Failed,
                Truncate(message),
                Truncate(diagnostic));

        private static string? Truncate(string? value)
            => value is null || value.Length <= MaxDiagnosticLength
                ? value
                : value.Substring(0, MaxDiagnosticLength);

        private static VideoSidecarBackfillResult EmptyResult()
            => new VideoSidecarBackfillResult(
                0, 0, 0, 0, 0, 0, 0, 0,
                StoppedByCap: true,
                BudgetExhausted: false,
                Artifacts: Array.Empty<VideoSidecarBackfillArtifactResult>());

        private static VideoSidecarBackfillResult BuildResult(
            int scanned,
            int eligible,
            int attempted,
            bool stoppedByCap,
            bool budgetExhausted,
            IReadOnlyList<VideoSidecarBackfillArtifactResult> artifacts)
        {
            var roleResults = artifacts.SelectMany(a => a.RoleResults).ToList();
            return new VideoSidecarBackfillResult(
                scanned,
                eligible,
                artifacts.Count(a => a.Code != VideoSidecarBackfillArtifactResultCode.Attempted),
                attempted,
                roleResults.Count,
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.Published),
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists),
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.Failed),
                stoppedByCap,
                budgetExhausted,
                artifacts);
        }
    }
}
```

- [ ] **Step 4: Run backfill service tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoSidecarBackfillServiceTests"
```

Expected: all `VideoSidecarBackfillServiceTests` pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src\Rook\Services\Vision\Video\VideoSidecarBackfillService.cs src\Rook.Tests\Services\Vision\Video\VideoSidecarBackfillServiceTests.cs
git commit -m "Add bounded video sidecar backfill service"
```

---

### Task 3: Video Subsystem Wiring And Root Guard

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs`
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`

- [ ] **Step 1: Add failing factory and root guard tests**

In `VideoSubsystemFactoryTests`, add this assertion to `Build_ReturnsNonNullBundle_WithAllSubsystems`:

```csharp
Assert.NotNull(bundle.SidecarBackfill);
```

Add these usings at the top of `VideoSubsystemFactoryTests.cs`:

```csharp
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
```

Add these tests to `RookSubsystemRootLifecycleTests`:

```csharp
[Fact]
public void BackfillVideoSidecarsOnce_RepeatedCallsScheduleOnlyOnce()
{
    var fakeBackfill = new FakeBackfillService();
    var scheduler = new FakeBackfillScheduler();
    var root = FreshRoot(sidecarBackfill: fakeBackfill, backfillScheduler: scheduler);
    try
    {
        root.BackfillVideoSidecarsOnce();
        root.BackfillVideoSidecarsOnce();
        root.BackfillVideoSidecarsOnce();

        Assert.Single(scheduler.WorkItems);
    }
    finally { root.DisposeVideoSubsystemIfCreated(); }
}

[Fact]
public void BackfillVideoSidecarsOnce_DisabledModeSchedulesNothingAndDoesNotRunBackfill()
{
    var fakeBackfill = new FakeBackfillService();
    var scheduler = new FakeBackfillScheduler();
    var root = FreshRoot(sidecarBackfill: fakeBackfill, backfillScheduler: scheduler);

    root.BackfillVideoSidecarsOnce(VideoSidecarBackfillStartupOptions.Disabled);

    Assert.Empty(scheduler.WorkItems);
    Assert.Equal(0, fakeBackfill.Calls);
    root.DisposeVideoSubsystemIfCreated();
}

[Fact]
public async Task BackfillVideoSidecarsOnce_AsyncFailureDoesNotReopenGuard()
{
    var fakeBackfill = new FakeBackfillService
    {
        ThrowAsync = new InvalidOperationException("backfill failed"),
    };
    var scheduler = new FakeBackfillScheduler();
    var failures = new List<Exception>();
    var root = FreshRoot(sidecarBackfill: fakeBackfill, backfillScheduler: scheduler);
    try
    {
        root.BackfillVideoSidecarsOnce(new VideoSidecarBackfillStartupOptions(
            Enabled: true,
            ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
            OnCompleted: null,
            OnFailed: failures.Add));

        await scheduler.RunAllAsync();
        root.BackfillVideoSidecarsOnce();

        Assert.Single(scheduler.WorkItems);
        Assert.Single(failures);
    }
    finally { root.DisposeVideoSubsystemIfCreated(); }
}

[Fact]
public void BackfillVideoSidecarsOnce_SynchronousSchedulingFailureResetsForRetry()
{
    var fakeBackfill = new FakeBackfillService();
    var scheduler = new FakeBackfillScheduler
    {
        ThrowOnSchedule = new IOException("schedule failed"),
    };
    var root = FreshRoot(sidecarBackfill: fakeBackfill, backfillScheduler: scheduler);
    try
    {
        Assert.Throws<IOException>(() => root.BackfillVideoSidecarsOnce());
        scheduler.ThrowOnSchedule = null;

        root.BackfillVideoSidecarsOnce();

        Assert.Single(scheduler.WorkItems);
    }
    finally { root.DisposeVideoSubsystemIfCreated(); }
}
```

Change `FreshRoot` signature in the same test class:

```csharp
private static RookSubsystemRoot FreshRoot(
    IVideoJobLedger? ledger = null,
    IImageJobLedger? imageLedger = null,
    IVideoSidecarBackfillService? sidecarBackfill = null,
    IVideoSidecarBackfillTaskScheduler? backfillScheduler = null) =>
    new(
        artifactStore: new ArtifactStore(),
        generationSecretStore: new DpapiGenerationSecretStore(),
        ledger: ledger ?? new FakeVideoJobLedger(),
        imageLedger: imageLedger ?? new FakeImageJobLedger(),
        sidecarBackfill: sidecarBackfill,
        backfillScheduler: backfillScheduler);
```

Add fakes at the bottom of `RookSubsystemRootLifecycleTests`:

```csharp
private sealed class FakeBackfillService : IVideoSidecarBackfillService
{
    public Exception? ThrowAsync { get; set; }
    public int Calls { get; private set; }

    public Task<VideoSidecarBackfillResult> BackfillMissingSidecarsAsync(
        VideoSidecarBackfillOptions options,
        CancellationToken cancellationToken)
    {
        Calls++;
        if (ThrowAsync is not null)
            throw ThrowAsync;

        return Task.FromResult(new VideoSidecarBackfillResult(
            0, 0, 0, 0, 0, 0, 0, 0,
            StoppedByCap: false,
            BudgetExhausted: false,
            Artifacts: Array.Empty<VideoSidecarBackfillArtifactResult>()));
    }
}

private sealed class FakeBackfillScheduler : IVideoSidecarBackfillTaskScheduler
{
    public List<Func<Task>> WorkItems { get; } = new();
    public Exception? ThrowOnSchedule { get; set; }

    public void Schedule(Func<Task> work)
    {
        if (ThrowOnSchedule is not null)
            throw ThrowOnSchedule;
        WorkItems.Add(work);
    }

    public async Task RunAllAsync()
    {
        foreach (var work in WorkItems)
            await work().ConfigureAwait(false);
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoSubsystemFactoryTests|FullyQualifiedName~RookSubsystemRootLifecycleTests"
```

Expected: compile fails because `SidecarBackfill`, startup options, scheduler, and root method do not exist.

- [ ] **Step 3: Wire backfill into the video subsystem**

Modify `VideoSubsystemBundle`:

```csharp
internal sealed record VideoSubsystemBundle(
    VideoJobManager Manager,
    IVideoProviderRegistry Registry,
    IVideoCostEstimator Estimator,
    IVideoSidecarBackfillService SidecarBackfill);
```

Change `Build` signature:

```csharp
public static VideoSubsystemBundle Build(
    IGenerationSecretStore generationSecrets,
    ArtifactStore artifactStore,
    IVideoJobLedger? ledger = null,
    IVideoSidecarBackfillService? sidecarBackfill = null)
```

Before return, create the default service:

```csharp
var actualSidecarBackfill = sidecarBackfill
    ?? new VideoSidecarBackfillService(
        artifactStore,
        new VideoPosterSidecarProducer(artifactStore),
        new VideoFrameSidecarProducer(artifactStore));

return new VideoSubsystemBundle(manager, registry, estimator, actualSidecarBackfill);
```

- [ ] **Step 4: Add root startup guard and scheduler**

In `RookSubsystemRoot.cs`, add fields:

```csharp
private readonly IVideoSidecarBackfillTaskScheduler _backfillScheduler;
private int _videoSidecarBackfillFired = 0;
```

Add internal startup types near the root class:

```csharp
internal sealed record VideoSidecarBackfillStartupOptions(
    bool Enabled,
    VideoSidecarBackfillOptions ServiceOptions,
    Action<VideoSidecarBackfillResult>? OnCompleted,
    Action<Exception>? OnFailed)
{
    public static VideoSidecarBackfillStartupOptions Default { get; } =
        new VideoSidecarBackfillStartupOptions(
            Enabled: true,
            ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
            OnCompleted: null,
            OnFailed: null);

    public static VideoSidecarBackfillStartupOptions Disabled { get; } =
        new VideoSidecarBackfillStartupOptions(
            Enabled: false,
            ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
            OnCompleted: null,
            OnFailed: null);
}

internal interface IVideoSidecarBackfillTaskScheduler
{
    void Schedule(Func<Task> work);
}

internal sealed class ThreadPoolVideoSidecarBackfillTaskScheduler
    : IVideoSidecarBackfillTaskScheduler
{
    public void Schedule(Func<Task> work)
    {
        _ = Task.Run(work);
    }
}
```

Add `using System.Threading.Tasks;` at the top.

Extend the internal constructor signature:

```csharp
internal RookSubsystemRoot(
    ArtifactStore? artifactStore,
    IGenerationSecretStore? generationSecretStore,
    IVideoJobLedger? ledger,
    IImageJobLedger? imageLedger,
    IVideoSidecarBackfillService? sidecarBackfill = null,
    IVideoSidecarBackfillTaskScheduler? backfillScheduler = null)
```

Update `_video` construction:

```csharp
_video = new Lazy<VideoSubsystemBundle>(
    () => VideoSubsystemFactory.Build(
        SharedGenerationSecretStore,
        SharedArtifactStore,
        ledger,
        sidecarBackfill),
    LazyThreadSafetyMode.ExecutionAndPublication);
_backfillScheduler = backfillScheduler ?? new ThreadPoolVideoSidecarBackfillTaskScheduler();
```

Add the method:

```csharp
public void BackfillVideoSidecarsOnce(
    VideoSidecarBackfillStartupOptions? startupOptions = null)
{
    var options = startupOptions ?? VideoSidecarBackfillStartupOptions.Default;
    if (!options.Enabled)
        return;

    if (Interlocked.CompareExchange(ref _videoSidecarBackfillFired, 1, 0) != 0)
        return;

    try
    {
        var bundle = Video;
        _backfillScheduler.Schedule(async () =>
        {
            try
            {
                var result = await bundle.SidecarBackfill
                    .BackfillMissingSidecarsAsync(
                        options.ServiceOptions,
                        CancellationToken.None)
                    .ConfigureAwait(false);
                TryInvokeCompleted(options.OnCompleted, result);
            }
            catch (Exception ex)
            {
                TryInvokeFailed(options.OnFailed, ex);
            }
        });
    }
    catch
    {
        Volatile.Write(ref _videoSidecarBackfillFired, 0);
        throw;
    }
}

private static void TryInvokeCompleted(
    Action<VideoSidecarBackfillResult>? callback,
    VideoSidecarBackfillResult result)
{
    if (callback is null)
        return;

    try { callback(result); }
    catch { }
}

private static void TryInvokeFailed(Action<Exception>? callback, Exception exception)
{
    if (callback is null)
        return;

    try { callback(exception); }
    catch { }
}
```

- [ ] **Step 5: Run root/factory tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoSubsystemFactoryTests|FullyQualifiedName~RookSubsystemRootLifecycleTests"
```

Expected: all targeted tests pass.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src\Rook\Services\Vision\Video\VideoSubsystemFactory.cs src\Rook\RookSubsystemRoot.cs src\Rook.Tests\Services\Vision\Video\VideoSubsystemFactoryTests.cs
git commit -m "Wire video sidecar backfill startup guard"
```

---

### Task 4: Plugin Startup Invocation

**Files:**
- Modify: `src/Rook/RookPlugin.cs`
- Modify: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`

- [ ] **Step 1: Add failing source lifecycle test**

Add this test to `RookPluginLifecycleSourceTests`:

```csharp
[Fact]
public void StartupVideoSidecarBackfill_IsScheduledAsSeparateNonFatalAsyncStep()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    var tryInitializeRuntime = ExtractMethod(source, "private void TryInitializeRuntime()");

    var reconcileBlock = ExtractTryCatchContaining(
        tryInitializeRuntime,
        "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");
    Assert.DoesNotContain("BackfillVideoSidecarsOnce", reconcileBlock.TryBody);

    var backfillBlock = ExtractTryCatchContaining(
        tryInitializeRuntime,
        "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(");

    Assert.Contains(
        "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(",
        backfillBlock.TryBody);
    Assert.Contains(
        "VideoSidecarBackfillStartupOptions",
        backfillBlock.TryBody);
    Assert.Contains(
        "TraceStartup($\"Video sidecar backfill completed:",
        backfillBlock.TryBody);
    Assert.Contains(
        "TraceStartup($\"Video sidecar backfill failed (non-fatal):",
        backfillBlock.TryBody);
    Assert.Contains(
        "TraceStartup($\"Video sidecar backfill scheduling failed (non-fatal):",
        backfillBlock.CatchBody);
    Assert.DoesNotContain("throw", backfillBlock.CatchBody);
}
```

- [ ] **Step 2: Run lifecycle source test and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~RookPluginLifecycleSourceTests"
```

Expected: new test fails because plugin startup does not schedule backfill.

- [ ] **Step 3: Wire startup scheduling**

Add this using to `RookPlugin.cs`:

```csharp
using Rook.Services.Vision.Video;
```

Inside `TryInitializeRuntime()`, after the existing image job reconcile block and before removing `EnsureNativeGhBridgeRegistered`, add:

```csharp
try
{
    RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(
        new VideoSidecarBackfillStartupOptions(
            Enabled: true,
            ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
            OnCompleted: result =>
                TraceStartup($"Video sidecar backfill completed: {result.ToTraceSummary()}"),
            OnFailed: ex =>
                TraceStartup($"Video sidecar backfill failed (non-fatal): {ex.GetType().Name}: {ex.Message}")));
    TraceStartup("Video sidecar backfill scheduled (or no-op if already scheduled)");
}
catch (Exception ex)
{
    TraceStartup($"Video sidecar backfill scheduling failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
    RhinoApp.WriteLine(
        "Rook: video sidecar backfill could not be scheduled at startup; continuing. " +
        $"Reason: {ex.GetType().Name}.");
}
```

- [ ] **Step 4: Run lifecycle source tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~RookPluginLifecycleSourceTests"
```

Expected: all `RookPluginLifecycleSourceTests` pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src\Rook\RookPlugin.cs src\Rook.Tests\Plugin\RookPluginLifecycleSourceTests.cs
git commit -m "Schedule video sidecar backfill at startup"
```

---

### Task 5: Documentation And Verification

**Files:**
- Modify: `docs/rook_docs/video-thumbnail-roadmap.md`
- Modify: `docs/rook_docs/work-queue.md`

- [ ] **Step 1: Run focused Slice 5 tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~VideoFrameSidecarProducerTests|FullyQualifiedName~VideoSidecarBackfillServiceTests|FullyQualifiedName~VideoSubsystemFactoryTests|FullyQualifiedName~RookPluginLifecycleSourceTests"
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run full managed test suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore
```

Expected: full managed suite passes.

- [ ] **Step 3: Run managed build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore /p:RhinoPluginDir=C:\__rook_missing_rhino_plugin_dir__
```

Expected: build passes with zero errors. This command avoids deploying into Rhino's real plugin directory during plan verification.

- [ ] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Update roadmap**

In `docs/rook_docs/video-thumbnail-roadmap.md`:

Change current next slice from:

```markdown
- Populate missing sidecars for older video artifacts from local MP4 files when possible.
```

to:

```markdown
- Provider/model payload audit for opportunistic display-poster ingestion, or Grasshopper NLE integration after explicit selection.
```

Change Slice 5 status row from:

```markdown
| 5. Existing-video reconcile/backfill | Next | Populate missing sidecars for older video artifacts from local MP4 files when possible. | Reconcile is idempotent, bounded, observable, and does not rerun provider jobs. |
```

to:

```markdown
| 5. Existing-video reconcile/backfill | Done | Populate missing sidecars for older video artifacts from local MP4 files when possible. | Startup schedules a bounded async one-shot backfill for eligible generated-video artifacts, attempts only missing roles, reports structured diagnostics, and never reruns provider jobs. |
```

Add under `Done:`:

```markdown
- Existing generated-video artifacts opportunistically backfill missing `poster`, `start_frame`, and `end_frame` sidecars from their saved local MP4s during a bounded async startup one-shot.
```

- [ ] **Step 6: Update work queue**

Prepend a new `Last triaged` entry to `docs/rook_docs/work-queue.md`:

```markdown
**Last triaged:** 2026-05-12 (**RookVision video thumbnail Slice 5 implemented.** Startup now schedules a separate async one-shot generated-video sidecar backfill after the companion video subsystem is available. The sweep is capped to eligible existing `generated_video` artifacts with readable local `video` blobs, attempts only missing `poster`, `start_frame`, and `end_frame` roles, checks elapsed budget between artifacts/roles without cancelling in-flight ffmpeg work, reports structured diagnostics, and treats failures as non-fatal. No provider jobs are rerun, no provider payload fields are inferred, and no public route, MCP tool, GH/NLE surface, or generic repair framework was introduced. **Next selection needed:** provider/model payload audit remains optional/parallel for display-poster optimization, while Grasshopper NLE integration is the next major video workflow slice if product direction selects it.)
```

- [ ] **Step 7: Commit docs**

```powershell
git add docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
git commit -m "Document video sidecar backfill completion"
```

- [ ] **Step 8: Final verification**

Run:

```powershell
git status -sb
git log --oneline -5
```

Expected: only unrelated pre-existing proto-skills files remain unstaged/untracked, and the Slice 5 implementation commits are on top of the plan/spec commit.

---

## Self-Review Checklist

- [ ] `VideoFrameSidecarProducer` validates requested roles before resolving artifact paths or ffmpeg when all roles are unknown.
- [ ] Backfill service calls the frame producer once per missing frame role.
- [ ] `maxArtifacts` counts eligible generated-video artifacts only.
- [ ] Budget is checked before artifacts and before each role attempt.
- [ ] Budget expiration does not cancel in-flight ffmpeg work.
- [ ] Startup backfill guard is separate from `ReconcileVideoJobsOnce()`.
- [ ] One-shot guard marks fired once scheduling succeeds.
- [ ] Disabled mode schedules nothing and does not run backfill.
- [ ] Failures remain diagnostic-only and non-fatal.
- [ ] No provider rerun, provider payload inference, public route, MCP tool, GH/NLE behavior, or generic repair framework is introduced.
