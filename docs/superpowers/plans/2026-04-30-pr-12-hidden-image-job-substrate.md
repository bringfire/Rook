# PR-12 Hidden Image Job Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hidden managed-bridge image jobs and authenticated image materialization seams so async image providers can be exercised without exposing Replicate models or Settings UI.

**Architecture:** Add an image-specific in-memory `ImageJobManager` under `Rook.Services.Vision.Image.Jobs`, parallel to the video job manager but deliberately not generalized yet. Add an authenticated request-factory extension point to `ImageArtifactMaterializer`; providers/substrates may create requests, but the materializer sends/reads/limits/resolves MIME/classifies errors. Add managed-bridge-only image job ops through `VisionWebSurface`, with no native route, MCP, Replicate credential metadata, or default Replicate model exposure.

**Tech Stack:** C# multi-targeted `net7.0;net48`, `System.Text.Json`, `System.Text.Json.Nodes`, `HttpClient`, existing `Rook.Services.Vision.Generation` seams, xUnit.

---

## Scope Guard

This plan implements only PR-12 from the PR-11 spec.

Do:

- Add image job domain/result types.
- Add `ImageJobManager` with in-memory state only.
- Add fake-provider tests for sync and async image job flows.
- Add authenticated request-factory materialization support.
- Add managed bridge op routing for image job ops.
- Keep existing `generate` behavior unchanged.

Do not:

- Register a production Replicate image model.
- Add Replicate Settings credential metadata.
- Add native routes or edit `src/RookNative/**`.
- Add MCP tools.
- Add live Replicate or network-spend tests.
- Generalize `VideoJobManager` and `ImageJobManager`.
- Persist image job ledgers.

## File Structure

Create:

- `src/Rook/Services/Vision/Image/Jobs/ImageJobState.cs`
  Image-specific lifecycle enum: queued, submitting, polling, materializing, complete, error, cancelled, interrupted.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobStartRequest.cs`
  Manager input containing `ImageGenerationRequest`, resolved media bytes, and parent artifact ids.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobRecord.cs`
  In-memory job snapshot.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobResultFile.cs`
  Result file projection for job result responses.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobSubmitResult.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobStatusResult.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobCancelResult.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobFetchResult.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobListResult.cs`
- `src/Rook/Services/Vision/Image/Jobs/IImageJobManager.cs`
- `src/Rook/Services/Vision/Image/Jobs/IImageJobClock.cs`
- `src/Rook/Services/Vision/Image/Jobs/IImageJobIdGenerator.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobSubsystemBundle.cs`
- `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- `src/Rook/Handlers/ImageJobOpHandler.cs`
- `src/Rook.Tests/Services/Vision/Image/FakeImageProvider.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobClock.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobIdGenerator.cs`
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

Modify:

- `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs`
  Add optional authenticated request factory overload; preserve current unauthenticated behavior.
- `src/Rook/RookSubsystemRoot.cs`
  Own one lazy process-wide image job bundle, matching the video subsystem lifetime pattern.
- `src/Rook/Handlers/VisionHandler.cs`
  Extract reusable internal image work-item builder result from `GenerateAsync`; keep structured failures and sync-only behavior unchanged.
- `src/Rook/UI/Vision/VisionWebSurface.cs`
  Add image job bridge op constants to `OpRoutes`, route them to the root-owned `ImageJobOpHandler`, and keep them managed-bridge-only.
- `src/Rook.Tests/Services/Vision/Image/ImageArtifactMaterializerTests.cs`
- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

Do not modify:

- `src/RookNative/**`
- `src/Rook/Services/Vision/VisionProviderRegistrations.cs`
- `src/Rook/UI/Vision/Resources/app.js`
- `src/Rook/UI/Vision/Resources/index.html`
- `src/Rook/UI/Vision/Resources/styles.css`

## Task 1: Authenticated Request Factory For Image Materialization

**Files:**
- Modify: `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/ImageArtifactMaterializerTests.cs`

- [ ] **Step 1: Add failing authenticated-fetch tests**

Add these tests to `src/Rook.Tests/Services/Vision/Image/ImageArtifactMaterializerTests.cs`. If the file already has helper methods for byte assertions or HTTP handlers, reuse them and keep the assertions below.

```csharp
[Fact]
public async Task MaterializeAsync_UsesAuthenticatedRequestFactoryForRemoteArtifact()
{
    HttpRequestMessage? observed = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            observed = req;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(new byte[] { 1, 2, 3 }),
            };
        },
    };
    var materializer = new ImageArtifactMaterializer(handler);
    var artifact = new ResultArtifact(
        Role: ImageMediaRoles.Image,
        Body: new RemoteArtifactBody(new Uri("https://replicate.delivery/pbxt/out.png")),
        DeclaredMimeType: null,
        ProviderMetadata: new Dictionary<string, JsonNode>());

    var result = await materializer.MaterializeAsync(
        artifact,
        CancellationToken.None,
        artifactForRequest =>
        {
            var remote = Assert.IsType<RemoteArtifactBody>(artifactForRequest.Body);
            var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
            request.Headers.Authorization =
                new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "r8_token");
            return ImageArtifactFetchRequest.Created(request);
        });

    Assert.True(result.Success);
    Assert.Equal(new byte[] { 1, 2, 3 }, result.Bytes);
    Assert.NotNull(observed);
    Assert.Equal("Bearer", observed!.Headers.Authorization!.Scheme);
    Assert.Equal("r8_token", observed.Headers.Authorization.Parameter);
}

[Fact]
public async Task MaterializeAsync_RequestFactoryFailureDoesNotSendNetworkRequest()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => throw new InvalidOperationException("network should not run"),
    };
    var materializer = new ImageArtifactMaterializer(handler);
    var artifact = new ResultArtifact(
        Role: ImageMediaRoles.Image,
        Body: new RemoteArtifactBody(new Uri("https://replicate.delivery/pbxt/out.png")),
        DeclaredMimeType: null,
        ProviderMetadata: new Dictionary<string, JsonNode>());

    var result = await materializer.MaterializeAsync(
        artifact,
        CancellationToken.None,
        _ => ImageArtifactFetchRequest.Failed(new GenerationError(
            GenerationErrorCode.DependencyUnavailable,
            "Replicate API token is not configured.",
            Retryable: false)));

    Assert.False(result.Success);
    Assert.Null(result.Bytes);
    Assert.NotNull(result.Error);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
    Assert.Contains("Replicate API token", result.Error.Message);
}

[Fact]
public async Task MaterializeAsync_DefaultPathStillUsesUnauthenticatedGet()
{
    HttpRequestMessage? observed = null;
    var handler = new TestHttpMessageHandler
    {
        OnSend = req =>
        {
            observed = req;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(new byte[] { 9, 8, 7 }),
            };
        },
    };
    var materializer = new ImageArtifactMaterializer(handler);
    var artifact = new ResultArtifact(
        Role: ImageMediaRoles.Image,
        Body: new RemoteArtifactBody(new Uri("https://v3b.fal.media/out.png")),
        DeclaredMimeType: "image/png",
        ProviderMetadata: new Dictionary<string, JsonNode>());

    var result = await materializer.MaterializeAsync(
        artifact,
        CancellationToken.None);

    Assert.True(result.Success);
    Assert.Equal(new byte[] { 9, 8, 7 }, result.Bytes);
    Assert.NotNull(observed);
    Assert.Null(observed!.Headers.Authorization);
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageArtifactMaterializerTests"
```

Expected: compile failure because `ImageArtifactFetchRequest` and the new `MaterializeAsync` overload do not exist.

- [ ] **Step 3: Add request-factory types and overload**

In `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs`, add these delegates/classes inside namespace `Rook.Services.Vision.Image`, before `ImageArtifactMaterializer`:

```csharp
internal delegate ImageArtifactFetchRequest ImageArtifactRequestFactory(
    ResultArtifact artifact);

internal sealed class ImageArtifactFetchRequest
{
    private ImageArtifactFetchRequest(
        HttpRequestMessage? request,
        GenerationError? error)
    {
        Request = request;
        Error = error;
    }

    public HttpRequestMessage? Request { get; }
    public GenerationError? Error { get; }

    public static ImageArtifactFetchRequest Created(HttpRequestMessage request)
    {
        if (request is null) throw new ArgumentNullException(nameof(request));
        return new ImageArtifactFetchRequest(request, error: null);
    }

    public static ImageArtifactFetchRequest Failed(GenerationError error)
    {
        if (error is null) throw new ArgumentNullException(nameof(error));
        return new ImageArtifactFetchRequest(request: null, error);
    }
}
```

Change the existing signature:

```csharp
public async Task<ImageArtifactMaterializationResult> MaterializeAsync(
    ResultArtifact artifact,
    CancellationToken cancellationToken)
```

to call the new overload:

```csharp
public Task<ImageArtifactMaterializationResult> MaterializeAsync(
    ResultArtifact artifact,
    CancellationToken cancellationToken) =>
    MaterializeAsync(artifact, cancellationToken, requestFactory: null);

public async Task<ImageArtifactMaterializationResult> MaterializeAsync(
    ResultArtifact artifact,
    CancellationToken cancellationToken,
    ImageArtifactRequestFactory? requestFactory)
```

Replace remote request creation:

```csharp
using var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
```

with:

```csharp
using var request = CreateRequest(artifact, remote, requestFactory, out var requestError);
if (requestError is not null)
    return ImageArtifactMaterializationResult.Fail(requestError);
```

Add this helper inside `ImageArtifactMaterializer`:

```csharp
private static HttpRequestMessage CreateRequest(
    ResultArtifact artifact,
    RemoteArtifactBody remote,
    ImageArtifactRequestFactory? requestFactory,
    out GenerationError? error)
{
    error = null;
    if (requestFactory is null)
        return new HttpRequestMessage(HttpMethod.Get, remote.Url);

    var fetchRequest = requestFactory(artifact);
    if (fetchRequest.Error is not null)
    {
        error = fetchRequest.Error;
        return new HttpRequestMessage(HttpMethod.Get, remote.Url);
    }

    if (fetchRequest.Request is null)
    {
        error = ExecutionFailed("Image artifact request factory did not return a request.");
        return new HttpRequestMessage(HttpMethod.Get, remote.Url);
    }

    return fetchRequest.Request;
}
```

Do not move HTTP sending, response reading, byte limits, MIME resolution, or retry classification into providers.

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageArtifactMaterializerTests"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\ImageArtifactMaterializer.cs `
        src\Rook.Tests\Services\Vision\Image\ImageArtifactMaterializerTests.cs
git commit -m "feat(vision): support authenticated image artifact requests"
```

## Task 2: Image Job Domain Types

**Files:**
- Create: `src/Rook/Services/Vision/Image/Jobs/*.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobResultTypesTests.cs`

- [ ] **Step 1: Write failing result-type invariant tests**

Create `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobResultTypesTests.cs`:

```csharp
using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobResultTypesTests
    {
        [Fact]
        public void SubmitOk_requires_non_empty_job_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobSubmitResult.Ok(Guid.Empty, ImageJobState.Queued));
        }

        [Fact]
        public void StatusComplete_requires_artifact_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Complete(Guid.Empty));
        }

        [Fact]
        public void StatusFailed_requires_terminal_failure_state()
        {
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "boom",
                Retryable: false);

            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Failed(ImageJobState.Polling, error));
        }

        [Fact]
        public void FetchComplete_requires_files()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobFetchResult.Complete(
                    Guid.NewGuid(),
                    Array.Empty<ImageJobResultFile>()));
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobResultTypesTests
```

Expected: compile failure because `Rook.Services.Vision.Image.Jobs` types do not exist.

- [ ] **Step 3: Add domain files**

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobState.cs`:

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageJobState
    {
        Queued = 0,
        Submitting = 1,
        Polling = 2,
        Materializing = 3,
        Complete = 4,
        Error = 5,
        Cancelled = 6,
        Interrupted = 7,
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobStartRequest.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobStartRequest
    {
        public ImageJobStartRequest(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            IReadOnlyList<Guid> parentArtifactIds)
        {
            Request = request ?? throw new ArgumentNullException(nameof(request));
            ResolvedMedia = resolvedMedia ?? throw new ArgumentNullException(nameof(resolvedMedia));
            ParentArtifactIds = parentArtifactIds ?? throw new ArgumentNullException(nameof(parentArtifactIds));
        }

        public ImageGenerationRequest Request { get; }
        public IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedMedia { get; }
        public IReadOnlyList<Guid> ParentArtifactIds { get; }
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobRecord.cs`:

```csharp
using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobRecord
    {
        public ImageJobRecord(
            Guid jobId,
            ImageJobState state,
            string model,
            string provider,
            DateTimeOffset updatedAt,
            ProviderJobHandle? providerHandle = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null)
        {
            if (jobId == Guid.Empty) throw new ArgumentException("JobId must be non-empty.", nameof(jobId));
            JobId = jobId;
            State = state;
            Model = model ?? string.Empty;
            Provider = provider ?? string.Empty;
            UpdatedAt = updatedAt;
            ProviderHandle = providerHandle;
            ResultArtifactId = resultArtifactId;
            Error = error;
        }

        public Guid JobId { get; }
        public ImageJobState State { get; }
        public string Model { get; }
        public string Provider { get; }
        public DateTimeOffset UpdatedAt { get; }
        public ProviderJobHandle? ProviderHandle { get; }
        public Guid? ResultArtifactId { get; }
        public GenerationError? Error { get; }
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobResultFile.cs`:

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobResultFile(string Role, string Path);
}
```

Create `ImageJobSubmitResult.cs`, `ImageJobStatusResult.cs`, `ImageJobCancelResult.cs`, and `ImageJobFetchResult.cs` with these exact shapes:

```csharp
using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobSubmitResult
    {
        private ImageJobSubmitResult(ImageJobState state, Guid? jobId, GenerationError? error)
        {
            State = state;
            JobId = jobId;
            Error = error;
        }

        public ImageJobState State { get; }
        public Guid? JobId { get; }
        public GenerationError? Error { get; }

        public static ImageJobSubmitResult Ok(Guid jobId, ImageJobState state)
        {
            if (jobId == Guid.Empty) throw new ArgumentException("JobId must be non-empty.", nameof(jobId));
            return new ImageJobSubmitResult(state, jobId, error: null);
        }

        public static ImageJobSubmitResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ImageJobSubmitResult(ImageJobState.Error, jobId: null, error);
        }
    }

    public sealed record ImageJobStatusResult
    {
        private ImageJobStatusResult(
            ImageJobState state,
            GenerationProgress? progress,
            Guid? resultArtifactId,
            GenerationError? error)
        {
            State = state;
            Progress = progress;
            ResultArtifactId = resultArtifactId;
            Error = error;
        }

        public ImageJobState State { get; }
        public GenerationProgress? Progress { get; }
        public Guid? ResultArtifactId { get; }
        public GenerationError? Error { get; }

        public static ImageJobStatusResult InFlight(ImageJobState state, GenerationProgress? progress)
        {
            if (state is ImageJobState.Complete or ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted)
                throw new ArgumentException($"InFlight requires non-terminal state; got {state}.", nameof(state));
            return new ImageJobStatusResult(state, progress, resultArtifactId: null, error: null);
        }

        public static ImageJobStatusResult Complete(Guid resultArtifactId)
        {
            if (resultArtifactId == Guid.Empty) throw new ArgumentException("ResultArtifactId must be non-empty.", nameof(resultArtifactId));
            return new ImageJobStatusResult(ImageJobState.Complete, progress: null, resultArtifactId, error: null);
        }

        public static ImageJobStatusResult Failed(ImageJobState terminal, GenerationError error)
        {
            if (terminal is not (ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted))
                throw new ArgumentException($"Failed requires terminal failure state; got {terminal}.", nameof(terminal));
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ImageJobStatusResult(terminal, progress: null, resultArtifactId: null, error);
        }
    }

    public sealed record ImageJobCancelResult
    {
        private ImageJobCancelResult(ImageJobState state, GenerationError? error)
        {
            State = state;
            Error = error;
        }

        public ImageJobState State { get; }
        public GenerationError? Error { get; }

        public static ImageJobCancelResult Ok(ImageJobState state) => new(state, error: null);

        public static ImageJobCancelResult Fail(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ImageJobCancelResult(ImageJobState.Error, error);
        }
    }

    public sealed record ImageJobFetchResult
    {
        private ImageJobFetchResult(
            ImageJobState state,
            Guid? resultArtifactId,
            IReadOnlyList<ImageJobResultFile>? files,
            GenerationError? error)
        {
            State = state;
            ResultArtifactId = resultArtifactId;
            Files = files;
            Error = error;
        }

        public ImageJobState State { get; }
        public Guid? ResultArtifactId { get; }
        public IReadOnlyList<ImageJobResultFile>? Files { get; }
        public GenerationError? Error { get; }

        public static ImageJobFetchResult Complete(Guid resultArtifactId, IReadOnlyList<ImageJobResultFile> files)
        {
            if (resultArtifactId == Guid.Empty) throw new ArgumentException("ResultArtifactId must be non-empty.", nameof(resultArtifactId));
            if (files is null) throw new ArgumentNullException(nameof(files));
            if (files.Count == 0) throw new ArgumentException("Files must be non-empty.", nameof(files));
            return new ImageJobFetchResult(ImageJobState.Complete, resultArtifactId, files, error: null);
        }

        public static ImageJobFetchResult Failed(ImageJobState state, GenerationError error)
        {
            if (state == ImageJobState.Complete) throw new ArgumentException("Failed requires non-Complete state.", nameof(state));
            if (error is null) throw new ArgumentNullException(nameof(error));
            return new ImageJobFetchResult(state, resultArtifactId: null, files: null, error);
        }
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobListResult.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobListResult
    {
        public ImageJobListResult(IReadOnlyList<ImageJobRecord> jobs, int appliedLimit)
        {
            Jobs = jobs ?? throw new ArgumentNullException(nameof(jobs));
            AppliedLimit = appliedLimit;
        }

        public IReadOnlyList<ImageJobRecord> Jobs { get; }
        public int AppliedLimit { get; }
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/IImageJobManager.cs`:

```csharp
using System;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobManager
    {
        Task<ImageJobSubmitResult> SubmitAsync(ImageJobStartRequest start, CancellationToken ct);
        Task<ImageJobStatusResult> GetStatusAsync(Guid jobId, CancellationToken ct);
        Task<ImageJobCancelResult> CancelAsync(Guid jobId, CancellationToken ct);
        Task<ImageJobFetchResult> FetchResultAsync(Guid jobId, CancellationToken ct);
        Task<ImageJobListResult> ListJobsAsync(int limit, CancellationToken ct);
    }
}
```

Create `IImageJobClock.cs` and `IImageJobIdGenerator.cs`:

```csharp
using System;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobClock
    {
        DateTimeOffset UtcNow();
    }

    public sealed class SystemImageJobClock : IImageJobClock
    {
        public DateTimeOffset UtcNow() => DateTimeOffset.UtcNow;
    }

    public interface IImageJobIdGenerator
    {
        Guid NewJobId();
    }

    public sealed class GuidImageJobIdGenerator : IImageJobIdGenerator
    {
        public Guid NewJobId() => Guid.NewGuid();
    }
}
```

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobSubsystemBundle.cs`:

```csharp
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobSubsystemBundle
    {
        public ImageJobSubsystemBundle(
            IImageJobManager manager,
            IImageProviderRegistry registry)
        {
            Manager = manager ?? throw new System.ArgumentNullException(nameof(manager));
            Registry = registry ?? throw new System.ArgumentNullException(nameof(registry));
        }

        public IImageJobManager Manager { get; }
        public IImageProviderRegistry Registry { get; }
    }
}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobResultTypesTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobResultTypesTests.cs
git commit -m "feat(vision): add image job domain types"
```

## Task 3: Fake Image Provider Test Substrate

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Image/FakeImageProvider.cs`

- [ ] **Step 1: Add fake provider**

Create `src/Rook.Tests/Services/Vision/Image/FakeImageProvider.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Tests.Services.Vision.Image
{
    public sealed class FakeImageProvider : IImageProvider
    {
        public Func<ImageGenerationRequest, IReadOnlyDictionary<MediaRef, ResolvedMedia>, ProviderSubmitOutcome>? OnSubmit { get; set; }
        public Func<ProviderJobHandle, ProviderStatusOutcome>? OnGetStatus { get; set; }
        public Func<ProviderJobHandle, ProviderCancelOutcome>? OnCancel { get; set; }
        public Func<ProviderJobHandle, ProviderResultOutcome>? OnFetchResult { get; set; }

        public List<string> Calls { get; } = new();
        public string ProviderName => "fake-image";

        public Task<ProviderSubmitOutcome> SubmitAsync(
            ImageGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
            CancellationToken ct)
        {
            Calls.Add("Submit");
            return Task.FromResult(OnSubmit?.Invoke(request, resolvedMedia) ?? SyncPng());
        }

        public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            Calls.Add("GetStatus");
            return Task.FromResult(OnGetStatus?.Invoke(handle)
                ?? new ProviderCompleteStatusOutcome(handle));
        }

        public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            Calls.Add("Cancel");
            return Task.FromResult(OnCancel?.Invoke(handle) ?? new CanceledOutcome());
        }

        public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            Calls.Add("FetchResult");
            return Task.FromResult(OnFetchResult?.Invoke(handle) ?? ImageResult(new byte[] { 4, 5, 6 }));
        }

        public static ProviderSubmitOutcome SyncPng() =>
            new SyncSubmitOutcome(ImageResult(new byte[] { 1, 2, 3 }));

        public static ProviderSubmitOutcome Queued(string providerJobId) =>
            new QueuedSubmitOutcome(new ProviderJobHandle(providerJobId));

        public static ProviderSubmitOutcome SubmitFailed(GenerationError error) =>
            new FailedSubmitOutcome(error);

        public static ProviderStatusOutcome Running() =>
            new InFlightStatusOutcome(
                GenerationLifecycleState.Running,
                new GenerationProgress(PercentComplete: 50, Message: "running"));

        public static ProviderStatusOutcome Complete(ProviderJobHandle handle) =>
            new ProviderCompleteStatusOutcome(handle);

        public static ProviderStatusOutcome StatusFailed(GenerationError error) =>
            new FailedStatusOutcome(error);

        public static ProviderResultOutcome ImageResult(byte[] bytes) =>
            new SuccessResultOutcome(new ProviderResultEnvelope(
                new[]
                {
                    new ResultArtifact(
                        Role: ImageMediaRoles.Image,
                        Body: new InlineArtifactBody(bytes),
                        DeclaredMimeType: "image/png",
                        ProviderMetadata: EmptyMetadata),
                },
                EmptyMetadata));

        public static ProviderResultOutcome RemoteImageResult(
            string url,
            string? declaredMime = null,
            bool requiresAuthenticatedFetch = false) =>
            new SuccessResultOutcome(new ProviderResultEnvelope(
                new[]
                {
                    new ResultArtifact(
                        Role: ImageMediaRoles.Image,
                        Body: new RemoteArtifactBody(new Uri(url)),
                        DeclaredMimeType: declaredMime,
                        ProviderMetadata: requiresAuthenticatedFetch
                            ? AuthFetchMetadata
                            : EmptyMetadata),
                },
                EmptyMetadata));

        public static ProviderResultOutcome ResultFailed(GenerationError error) =>
            new FailedResultOutcome(error);

        private static readonly IReadOnlyDictionary<string, JsonNode> EmptyMetadata =
            new Dictionary<string, JsonNode>();

        private static readonly IReadOnlyDictionary<string, JsonNode> AuthFetchMetadata =
            new Dictionary<string, JsonNode>
            {
                ["requires_authenticated_fetch"] = JsonValue.Create(true)!,
            };
    }
}
```

- [ ] **Step 2: Run compile-focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FakeImageProvider
```

Expected: no matching tests or PASS compile. If compilation fails, fix namespace/import drift before continuing.

- [ ] **Step 3: Commit**

```powershell
git add src\Rook.Tests\Services\Vision\Image\FakeImageProvider.cs
git commit -m "test(vision): add fake image provider"
```

## Task 4: ImageJobManager Core Lifecycle

**Files:**
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Create: `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobClock.cs`
- Create: `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobIdGenerator.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`

- [ ] **Step 1: Write failing manager tests**

Create `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobManagerTests : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "rook-image-jobs-" + Guid.NewGuid().ToString("N"));
        private readonly Guid _jobId = Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public async Task SubmitAsync_SyncProvider_CompletesAndWritesArtifact()
        {
            var provider = new FakeImageProvider();
            var manager = NewManager(provider);

            var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);
            var fetch = await manager.FetchResultAsync(_jobId, CancellationToken.None);

            Assert.Equal(_jobId, submit.JobId);
            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.NotNull(status.ResultArtifactId);
            Assert.Equal(ImageJobState.Complete, fetch.State);
            Assert.NotNull(fetch.Files);
            Assert.Contains(provider.Calls, c => c == "Submit");
            Assert.DoesNotContain(provider.Calls, c => c == "GetStatus");
            Assert.DoesNotContain(provider.Calls, c => c == "FetchResult");
        }

        [Fact]
        public async Task SubmitAsync_AsyncProvider_PollsFetchesThenMaterializes()
        {
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = handle => FakeImageProvider.Complete(handle),
                OnFetchResult = _ => FakeImageProvider.ImageResult(new byte[] { 7, 8, 9 }),
            };
            var manager = NewManager(provider, pollInterval: TimeSpan.FromMilliseconds(5));

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.Contains(provider.Calls, c => c == "Submit");
            Assert.Contains(provider.Calls, c => c == "GetStatus");
            Assert.Contains(provider.Calls, c => c == "FetchResult");
        }

        [Fact]
        public async Task ProviderCompleteIsNotJobCompleteUntilMaterializationSucceeds()
        {
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = handle => FakeImageProvider.Complete(handle),
                OnFetchResult = _ => FakeImageProvider.RemoteImageResult("https://example.test/missing.png"),
            };
            var manager = NewManager(provider, pollInterval: TimeSpan.FromMilliseconds(5));

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, status.State);
            Assert.NotNull(status.Error);
            Assert.NotNull(status.Error!.Message);
        }

        [Fact]
        public async Task RemoteProviderOwnedArtifactUsesAuthenticatedRequestFactory()
        {
            HttpRequestMessage? observed = null;
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = handle => FakeImageProvider.Complete(handle),
                OnFetchResult = _ => FakeImageProvider.RemoteImageResult(
                    "https://replicate.delivery/pbxt/out.png",
                    requiresAuthenticatedFetch: true),
            };
            var manager = NewManager(
                provider,
                pollInterval: TimeSpan.FromMilliseconds(5),
                onSend: req =>
                {
                    observed = req;
                    return new System.Net.Http.HttpResponseMessage(System.Net.HttpStatusCode.OK)
                    {
                        Content = new System.Net.Http.ByteArrayContent(new byte[] { 9, 8, 7 }),
                    };
                },
                requestFactorySelector: (model, artifact) =>
                {
                    var remote = Assert.IsType<RemoteArtifactBody>(artifact.Body);
                    if (!string.Equals(remote.Url.Host, "replicate.delivery", StringComparison.OrdinalIgnoreCase))
                        return null;

                    return _ =>
                    {
                        var request = new HttpRequestMessage(HttpMethod.Get, remote.Url);
                        request.Headers.Authorization =
                            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "r8_token");
                        return ImageArtifactFetchRequest.Created(request);
                    };
                });

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.NotNull(observed);
            Assert.Equal("Bearer", observed!.Headers.Authorization!.Scheme);
            Assert.Equal("r8_token", observed.Headers.Authorization.Parameter);
        }

        [Fact]
        public async Task PublicFalStyleArtifactDoesNotUseAuthenticatedRequestFactory()
        {
            HttpRequestMessage? observed = null;
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = handle => FakeImageProvider.Complete(handle),
                OnFetchResult = _ => FakeImageProvider.RemoteImageResult("https://v3b.fal.media/out.png", "image/png"),
            };
            var manager = NewManager(
                provider,
                onSend: req =>
                {
                    observed = req;
                    return new System.Net.Http.HttpResponseMessage(System.Net.HttpStatusCode.OK)
                    {
                        Content = new System.Net.Http.ByteArrayContent(new byte[] { 4, 5, 6 }),
                    };
                },
                requestFactorySelector: (model, artifact) =>
                    throw new InvalidOperationException("request factory should not be called for public fal URLs"));

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Complete, status.State);
            Assert.NotNull(observed);
            Assert.Null(observed!.Headers.Authorization);
        }

        [Fact]
        public async Task CancelAsync_WithProviderHandle_CallsProviderCancel()
        {
            var cancelCalls = 0;
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = _ => FakeImageProvider.Running(),
                OnCancel = _ =>
                {
                    cancelCalls++;
                    return new CanceledOutcome();
                },
            };
            var manager = NewManager(provider, pollInterval: TimeSpan.FromSeconds(10));

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForState(manager, _jobId, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(1, cancelCalls);
        }

        [Fact]
        public async Task CancelAsync_WhenProviderAlreadyTerminal_DoesNotStampLocalCancelled()
        {
            var cancelCalls = 0;
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = _ => FakeImageProvider.Running(),
                OnCancel = _ =>
                {
                    cancelCalls++;
                    return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
                },
            };
            var manager = NewManager(provider, pollInterval: TimeSpan.FromSeconds(10));

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForState(manager, _jobId, ImageJobState.Polling);
            var cancel = await manager.CancelAsync(_jobId, CancellationToken.None);
            var status = await manager.GetStatusAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Polling, cancel.State);
            Assert.Equal(ImageJobState.Polling, status.State);
            Assert.Equal(1, cancelCalls);
        }

        [Fact]
        public async Task CancelAsync_DuringMaterialization_CancelsLocalFetchAndAttemptsProviderCancel()
        {
            var releaseResponse = new TaskCompletionSource<bool>();
            var cancelCalls = 0;
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
                OnGetStatus = handle => FakeImageProvider.Complete(handle),
                OnFetchResult = _ => FakeImageProvider.RemoteImageResult("https://v3b.fal.media/out.png", "image/png"),
                OnCancel = _ =>
                {
                    cancelCalls++;
                    return new CanceledOutcome();
                },
            };
            var manager = NewManager(
                provider,
                pollInterval: TimeSpan.FromMilliseconds(5),
                onSend: _ =>
                {
                    releaseResponse.Task.GetAwaiter().GetResult();
                    return new System.Net.Http.HttpResponseMessage(System.Net.HttpStatusCode.OK)
                    {
                        Content = new System.Net.Http.ByteArrayContent(new byte[] { 1, 2, 3 }),
                    };
                });

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForState(manager, _jobId, ImageJobState.Materializing);
            var cancel = await manager.CancelAsync(_jobId, CancellationToken.None);
            releaseResponse.SetResult(true);
            await WaitForTerminal(manager, _jobId);

            Assert.Equal(ImageJobState.Cancelled, cancel.State);
            Assert.Equal(1, cancelCalls);
        }

        [Fact]
        public async Task FetchResultAsync_CompleteStateVerifiesArtifactStillExists()
        {
            var provider = new FakeImageProvider();
            var manager = NewManager(provider);

            await manager.SubmitAsync(Start(), CancellationToken.None);
            await WaitForTerminal(manager, _jobId);
            Directory.Delete(_root, recursive: true);

            var result = await manager.FetchResultAsync(_jobId, CancellationToken.None);

            Assert.Equal(ImageJobState.Error, result.State);
            Assert.NotNull(result.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, result.Error!.Code);
        }

        [Fact]
        public async Task GeneratePathStillRejectsAsyncProviderOutsideJobManager()
        {
            var provider = new FakeImageProvider
            {
                OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
            };

            var handler = NewHandlerWithImageProvider(provider, _root);
            var input = Path.Combine(_root, "input.png");
            Directory.CreateDirectory(_root);
            File.WriteAllBytes(input, new byte[] { 1, 2, 3 });

            var response = await handler.GenerateAsync(
                GenerateArgs(input, GeminiImageCapabilities.DefaultModel),
                CancellationToken.None);

            Assert.False(response.Success);
            Assert.Contains("Provider returned an async job", response.Data?.ToString());
        }

        private ImageJobManager NewManager(
            FakeImageProvider provider,
            TimeSpan? pollInterval = null,
            Func<HttpRequestMessage, HttpResponseMessage>? onSend = null,
            ImageArtifactRequestFactorySelector? requestFactorySelector = null)
        {
            var registry = new DefaultImageProviderRegistry(new[]
            {
                new TestImageProviderRegistration(provider),
            });
            return new ImageJobManager(
                registry,
                new ArtifactStore(_root),
                new FakeImageJobClock(new DateTimeOffset(2026, 4, 30, 12, 0, 0, TimeSpan.Zero)),
                new FakeImageJobIdGenerator(_jobId),
                pollInterval ?? TimeSpan.FromMilliseconds(1),
                maxConcurrentJobs: 1,
                materializer: new ImageArtifactMaterializer(new TestHttpMessageHandler
                {
                    OnSend = onSend ?? (_ => new HttpResponseMessage(HttpStatusCode.NotFound)),
                }),
                requestFactorySelector: requestFactorySelector);
        }

        private static ImageJobStartRequest Start()
        {
            var request = new ImageGenerationRequest(
                Model: GeminiImageCapabilities.DefaultModel,
                Prompt: "red cube",
                Resolution: "1K",
                AspectRatio: "",
                NumberOfImages: 1,
                ReferenceImages: null,
                Options: new GeminiImageOptions());

            return new ImageJobStartRequest(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>());
        }

        private static Dictionary<string, JsonElement> GenerateArgs(string inputPath, string model)
        {
            using var doc = JsonDocument.Parse($$"""
                {
                  "prompt": "red cube",
                  "input_image_path": "{{JsonEncodedText.Encode(inputPath).ToString()}}",
                  "model": "{{model}}",
                  "resolution": "1K",
                  "aspect_ratio": "auto"
                }
                """);
            var args = new Dictionary<string, JsonElement>();
            foreach (var prop in doc.RootElement.EnumerateObject())
                args[prop.Name] = prop.Value.Clone();
            return args;
        }

        private static VisionHandler NewHandlerWithImageProvider(
            IImageProvider provider,
            string root)
        {
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new TestImageProviderRegistration(provider),
            });
            return new VisionHandler(
                new ArtifactStore(root),
                new EmptyGenerationSecretStore(),
                new PromptEnhancer(),
                new ViewportHandler(),
                imageProviderRegistry: registry);
        }

        private static async Task WaitForTerminal(ImageJobManager manager, Guid jobId)
        {
            for (var i = 0; i < 100; i++)
            {
                var status = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (status.State is ImageJobState.Complete or ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted)
                    return;
                await Task.Delay(10);
            }
            throw new TimeoutException("Image job did not reach terminal state.");
        }

        private static async Task WaitForState(
            ImageJobManager manager,
            Guid jobId,
            ImageJobState expected)
        {
            for (var i = 0; i < 100; i++)
            {
                var status = await manager.GetStatusAsync(jobId, CancellationToken.None);
                if (status.State == expected)
                    return;
                await Task.Delay(10);
            }
            throw new TimeoutException($"Image job did not reach state {expected}.");
        }

        private sealed class EmptyGenerationSecretStore : IGenerationSecretStore
        {
            public string? GetSecret(string key) => null;
            public bool HasSecret(string key) => false;
            public string? GetPreview(string key) => null;
            public void SetSecret(string key, string value) { }
            public void RemoveSecret(string key) { }
        }
    }
}
```

Add supporting fakes:

`src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobClock.cs`

```csharp
using System;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobClock : IImageJobClock
    {
        private DateTimeOffset _now;

        public FakeImageJobClock(DateTimeOffset now)
        {
            _now = now;
        }

        public DateTimeOffset UtcNow()
        {
            _now = _now.AddMilliseconds(1);
            return _now;
        }
    }
}
```

`src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobIdGenerator.cs`

```csharp
using System;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobIdGenerator : IImageJobIdGenerator
    {
        private readonly Guid _jobId;

        public FakeImageJobIdGenerator(Guid jobId)
        {
            _jobId = jobId;
        }

        public Guid NewJobId() => _jobId;
    }
}
```

Add this private nested helper in the test file:

```csharp
private sealed class TestImageProviderRegistration : IImageProviderRegistration
{
    private readonly IImageProvider _provider;
    private readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models;

    public TestImageProviderRegistration(IImageProvider provider)
    {
        _provider = provider;
        _models = new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>
        {
            [GeminiImageCapabilities.DefaultModel] = (
                GeminiImageCapabilities.Models[GeminiImageCapabilities.DefaultModel],
                new GeminiImagePricingModel()),
        };
    }

    public string ProviderName => _provider.ProviderName;
    public IImageProvider Provider => _provider;
    public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; } =
        new GeminiImageOptionsCodec();
    public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models =>
        _models;
    public IReadOnlyList<ProviderSecretRequirement> SecretRequirements { get; } =
        Array.Empty<ProviderSecretRequirement>();
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobManagerTests
```

Expected: compile failure because `ImageJobManager` does not exist.

- [ ] **Step 3: Implement `ImageJobManager`**

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs` using this structure:

```csharp
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;

namespace Rook.Services.Vision.Image.Jobs
{
    internal delegate ImageArtifactRequestFactory? ImageArtifactRequestFactorySelector(
        ResolvedImageModel model,
        ResultArtifact artifact);

    public sealed class ImageJobManager : IImageJobManager, IDisposable
    {
        public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(2);
        public const int DefaultMaxConcurrentJobs = 2;

        private readonly IImageProviderRegistry _registry;
        private readonly ArtifactStore _artifactStore;
        private readonly ImageArtifactMaterializer _materializer;
        private readonly IImageJobClock _clock;
        private readonly IImageJobIdGenerator _idGenerator;
        private readonly ImageArtifactRequestFactorySelector? _requestFactorySelector;
        private readonly TimeSpan _pollInterval;
        private readonly SemaphoreSlim _concurrency;
        private readonly CancellationTokenSource _shutdownCts = new();
        private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();
        private readonly ConcurrentDictionary<Guid, ImageJobRecord> _records = new();

        public ImageJobManager(
            IImageProviderRegistry registry,
            ArtifactStore artifactStore,
            IImageJobClock? clock = null,
            IImageJobIdGenerator? idGenerator = null,
            TimeSpan? pollInterval = null,
            int maxConcurrentJobs = DefaultMaxConcurrentJobs)
            : this(
                registry,
                artifactStore,
                clock,
                idGenerator,
                pollInterval,
                maxConcurrentJobs,
                materializer: null,
                requestFactorySelector: null)
        {
        }

        internal ImageJobManager(
            IImageProviderRegistry registry,
            ArtifactStore artifactStore,
            IImageJobClock? clock,
            IImageJobIdGenerator? idGenerator,
            TimeSpan? pollInterval,
            int maxConcurrentJobs,
            ImageArtifactMaterializer? materializer,
            ImageArtifactRequestFactorySelector? requestFactorySelector)
        {
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _clock = clock ?? new SystemImageJobClock();
            _idGenerator = idGenerator ?? new GuidImageJobIdGenerator();
            _pollInterval = pollInterval ?? DefaultPollInterval;
            _materializer = materializer ?? new ImageArtifactMaterializer();
            _requestFactorySelector = requestFactorySelector;
            _concurrency = new SemaphoreSlim(maxConcurrentJobs, maxConcurrentJobs);
        }

        public Task<ImageJobSubmitResult> SubmitAsync(ImageJobStartRequest start, CancellationToken ct)
        {
            if (start is null)
                return Task.FromResult(ImageJobSubmitResult.Fail(Invalid("Request is null.", "request")));
            if (!_registry.TryResolve(start.Request.Model, out var model))
                return Task.FromResult(ImageJobSubmitResult.Fail(Invalid($"Unknown image model '{start.Request.Model}'.", "model")));

            var validation = model.OptionsCodec.Validate(start.Request, start.Request.Options, model.Capability);
            if (!validation.Success)
                return Task.FromResult(ImageJobSubmitResult.Fail(Invalid(validation.Message ?? "Image provider request is invalid.", "options")));

            var jobId = _idGenerator.NewJobId();
            var initial = new ImageJobRecord(jobId, ImageJobState.Queued, start.Request.Model, model.ProviderName, _clock.UtcNow());
            _records[jobId] = initial;
            var cts = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
            var running = new RunningJob(initial, cts, model, start);
            _runningJobs[jobId] = running;
            _ = Task.Run(() => RunJobAsync(jobId, running), cts.Token);
            return Task.FromResult(ImageJobSubmitResult.Ok(jobId, ImageJobState.Queued));
        }

        public Task<ImageJobStatusResult> GetStatusAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(ImageJobStatusResult.Failed(ImageJobState.Error, Invalid("JobId must be non-empty.", "job_id")));
            if (!_records.TryGetValue(jobId, out var record))
                return Task.FromResult(ImageJobStatusResult.Failed(ImageJobState.Error, Invalid($"Unknown job_id: {jobId:D}.", "job_id")));
            return Task.FromResult(ToStatus(record));
        }

        public async Task<ImageJobCancelResult> CancelAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return ImageJobCancelResult.Fail(Invalid("JobId must be non-empty.", "job_id"));
            if (!_records.TryGetValue(jobId, out var record))
                return ImageJobCancelResult.Fail(Invalid($"Unknown job_id: {jobId:D}.", "job_id"));
            if (IsTerminal(record.State))
                return ImageJobCancelResult.Ok(record.State);

            var providerHandle = record.ProviderHandle;
            if (providerHandle is not null)
            {
                var provider = _runningJobs.TryGetValue(jobId, out var runningForCancel)
                    ? runningForCancel.Model.Provider
                    : ResolveProviderByName(record.Provider);
                if (provider is null)
                {
                    return ImageJobCancelResult.Fail(Invalid(
                        $"Cannot cancel image job {jobId:D}: provider '{record.Provider}' is not registered.",
                        "provider_name"));
                }

                var remote = await provider.CancelAsync(providerHandle, ct).ConfigureAwait(false);
                if (remote is FailedCancelOutcome failed)
                    return ImageJobCancelResult.Fail(failed.Error);
                if (remote is AlreadyTerminalOutcome)
                {
                    // Remote completion won the race. Do not overwrite the
                    // local record with Cancelled; preserve the current local
                    // state and let the polling/materialization path finish.
                    var current = _records.TryGetValue(jobId, out var latest)
                        ? latest
                        : record;
                    return ImageJobCancelResult.Ok(current.State);
                }
            }

            if (_runningJobs.TryGetValue(jobId, out var running))
            {
                try { running.Cts.Cancel(); } catch { }
            }
            var cancelled = Transition(record, ImageJobState.Cancelled, error: new GenerationError(
                GenerationErrorCode.Cancelled, "Image job cancelled.", Retryable: false));
            if (running is not null)
                running.Record = cancelled;
            _records[jobId] = cancelled;
            return ImageJobCancelResult.Ok(ImageJobState.Cancelled);
        }

        public Task<ImageJobFetchResult> FetchResultAsync(Guid jobId, CancellationToken ct)
        {
            if (jobId == Guid.Empty)
                return Task.FromResult(ImageJobFetchResult.Failed(ImageJobState.Error, Invalid("JobId must be non-empty.", "job_id")));
            if (!_records.TryGetValue(jobId, out var record))
                return Task.FromResult(ImageJobFetchResult.Failed(ImageJobState.Error, Invalid($"Unknown job_id: {jobId:D}.", "job_id")));
            if (record.State != ImageJobState.Complete || record.ResultArtifactId is not Guid artifactId)
            {
                return Task.FromResult(ImageJobFetchResult.Failed(
                    record.State,
                    record.Error ?? new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        $"Image job is not complete; current state is {record.State}.",
                        Retryable: true)));
            }
            try
            {
                _artifactStore.GetBlobAbsolutePath(artifactId, ImageMediaRoles.Image);
            }
            catch (Exception ex) when (
                ex is KeyNotFoundException
                || ex is FileNotFoundException
                || ex is DirectoryNotFoundException
                || ex is InvalidDataException)
            {
                return Task.FromResult(ImageJobFetchResult.Failed(
                    ImageJobState.Error,
                    new GenerationError(
                        GenerationErrorCode.DependencyUnavailable,
                        $"Image job artifact is no longer available: {artifactId:D}.",
                        Retryable: false)));
            }
            return Task.FromResult(ImageJobFetchResult.Complete(
                artifactId,
                new[] { new ImageJobResultFile(ImageMediaRoles.Image, $"/blob/{artifactId:D}/image") }));
        }

        public Task<ImageJobListResult> ListJobsAsync(int limit, CancellationToken ct)
        {
            var applied = Math.Max(1, Math.Min(limit, 100));
            var rows = new List<ImageJobRecord>(_records.Values);
            rows.Sort((a, b) => b.UpdatedAt.CompareTo(a.UpdatedAt));
            if (rows.Count > applied) rows = rows.GetRange(0, applied);
            return Task.FromResult(new ImageJobListResult(rows, applied));
        }

        private async Task RunJobAsync(Guid jobId, RunningJob running)
        {
            var ct = running.Cts.Token;
            var current = running.Record;
            var provider = running.Model.Provider;
            try
            {
                await _concurrency.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    current = Save(running, Transition(current, ImageJobState.Submitting));
                    var submit = await provider.SubmitAsync(running.Start.Request, running.Start.ResolvedMedia, ct).ConfigureAwait(false);
                    if (submit is FailedSubmitOutcome failedSubmit)
                    {
                        Save(running, Transition(current, ImageJobState.Error, error: failedSubmit.Error));
                        return;
                    }
                    if (submit is SyncSubmitOutcome sync)
                    {
                        await CompleteResultAsync(running, current, sync.Result, ct).ConfigureAwait(false);
                        return;
                    }
                    if (submit is not QueuedSubmitOutcome queued)
                    {
                        Save(running, Transition(current, ImageJobState.Error, error: Execution($"Unknown provider submit outcome: {submit.GetType().Name}.")));
                        return;
                    }

                    var handle = queued.Handle;
                    current = Save(running, Transition(current, ImageJobState.Polling, providerHandle: handle));
                    while (true)
                    {
                        ct.ThrowIfCancellationRequested();
                        var status = await provider.GetStatusAsync(handle, ct).ConfigureAwait(false);
                        if (status is InFlightStatusOutcome)
                        {
                            await Task.Delay(_pollInterval, ct).ConfigureAwait(false);
                            continue;
                        }
                        if (status is FailedStatusOutcome failedStatus)
                        {
                            Save(running, Transition(current, ImageJobState.Error, error: failedStatus.Error));
                            return;
                        }
                        if (status is ProviderCompleteStatusOutcome complete)
                        {
                            handle = complete.UpdatedHandle;
                            current = Save(running, Transition(current, ImageJobState.Materializing, providerHandle: handle));
                            break;
                        }
                        Save(running, Transition(current, ImageJobState.Error, error: Execution($"Unknown provider status outcome: {status.GetType().Name}.")));
                        return;
                    }

                    var fetch = await provider.FetchResultAsync(handle, ct).ConfigureAwait(false);
                    await CompleteResultAsync(running, current, fetch, ct).ConfigureAwait(false);
                }
                finally
                {
                    _concurrency.Release();
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                if (!IsTerminal(current.State))
                    Save(running, Transition(current, ImageJobState.Cancelled, error: new GenerationError(
                        GenerationErrorCode.Cancelled, "Image job cancelled.", Retryable: false)));
            }
            catch (Exception ex)
            {
                if (!IsTerminal(current.State))
                    Save(running, Transition(current, ImageJobState.Error, error: Execution($"Unexpected image job error: {ex.Message}")));
            }
            finally
            {
                _runningJobs.TryRemove(jobId, out _);
                running.Cts.Dispose();
            }
        }

        private async Task CompleteResultAsync(
            RunningJob running,
            ImageJobRecord current,
            ProviderResultOutcome result,
            CancellationToken ct)
        {
            if (result is FailedResultOutcome failed)
            {
                Save(running, Transition(current, ImageJobState.Error, error: failed.Error));
                return;
            }
            if (result is not SuccessResultOutcome success)
            {
                Save(running, Transition(current, ImageJobState.Error, error: Execution($"Unknown provider result outcome: {result.GetType().Name}.")));
                return;
            }
            var artifact = FindImageArtifact(success.Envelope);
            if (artifact is null)
            {
                Save(running, Transition(current, ImageJobState.Error, error: Execution("Provider result did not contain an image artifact.")));
                return;
            }
            current = Save(running, Transition(current, ImageJobState.Materializing));
            var requestFactory = RequiresAuthenticatedFetch(artifact)
                ? _requestFactorySelector?.Invoke(running.Model, artifact)
                : null;
            var materialized = await _materializer.MaterializeAsync(
                artifact,
                ct,
                requestFactory).ConfigureAwait(false);
            if (!materialized.Success || materialized.Bytes is null)
            {
                Save(running, Transition(current, ImageJobState.Error, error: materialized.Error ?? Execution("Image artifact could not be materialized.")));
                return;
            }
            ct.ThrowIfCancellationRequested();
            var ext = ExtensionForMime(materialized.MimeType ?? "image/png");
            var stored = _artifactStore.Create(
                kind: "generated_image",
                blobs: new[] { new BlobInput(ImageMediaRoles.Image, materialized.Bytes, ext) },
                parentIds: running.Start.ParentArtifactIds);
            Save(running, Transition(current, ImageJobState.Complete, resultArtifactId: stored.Id));
        }

        private ImageJobRecord Save(RunningJob running, ImageJobRecord next)
        {
            running.Record = next;
            _records[next.JobId] = next;
            return next;
        }

        private ImageJobRecord Transition(
            ImageJobRecord prior,
            ImageJobState state,
            ProviderJobHandle? providerHandle = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null) =>
            new ImageJobRecord(
                prior.JobId,
                state,
                prior.Model,
                prior.Provider,
                _clock.UtcNow(),
                providerHandle ?? prior.ProviderHandle,
                resultArtifactId,
                error);

        private static ImageJobStatusResult ToStatus(ImageJobRecord record) =>
            record.State switch
            {
                ImageJobState.Complete when record.ResultArtifactId is Guid id => ImageJobStatusResult.Complete(id),
                ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted =>
                    ImageJobStatusResult.Failed(record.State, record.Error ?? Execution($"Terminal state {record.State} without error.")),
                _ => ImageJobStatusResult.InFlight(record.State, progress: null),
            };

        private static ResultArtifact? FindImageArtifact(ProviderResultEnvelope envelope)
        {
            foreach (var artifact in envelope.Artifacts)
                if (artifact.Role == ImageMediaRoles.Image)
                    return artifact;
            return envelope.Artifacts.Count > 0 ? envelope.Artifacts[0] : null;
        }

        private static bool RequiresAuthenticatedFetch(ResultArtifact artifact)
        {
            return artifact.ProviderMetadata.TryGetValue(
                    "requires_authenticated_fetch",
                    out var node)
                && node is not null
                && node.GetValue<bool>();
        }

        private static string ExtensionForMime(string mimeType) => mimeType.ToLowerInvariant() switch
        {
            "image/png" => "png",
            "image/jpeg" => "jpg",
            "image/webp" => "webp",
            "image/gif" => "gif",
            "image/bmp" => "bmp",
            _ => "bin",
        };

        private static bool IsTerminal(ImageJobState state) =>
            state is ImageJobState.Complete or ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted;

        private IImageProvider? ResolveProviderByName(string providerName) =>
            _registry.TryResolveProviderByName(providerName, out var provider)
                ? provider
                : null;

        private static GenerationError Invalid(string message, string field) =>
            new(GenerationErrorCode.InvalidRequest, message, Retryable: false, Field: field);

        private static GenerationError Execution(string message) =>
            new(GenerationErrorCode.ExecutionFailed, message, Retryable: false);

        public void Dispose()
        {
            try { _shutdownCts.Cancel(); } catch { }
            _shutdownCts.Dispose();
            _concurrency.Dispose();
        }

        private sealed class RunningJob
        {
            public ImageJobRecord Record;
            public readonly CancellationTokenSource Cts;
            public readonly ResolvedImageModel Model;
            public readonly ImageJobStartRequest Start;

            public RunningJob(ImageJobRecord record, CancellationTokenSource cts, ResolvedImageModel model, ImageJobStartRequest start)
            {
                Record = record;
                Cts = cts;
                Model = model;
                Start = start;
            }
        }
    }
}
```

- [ ] **Step 4: Run manager tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobManagerTests
```

Expected: PASS after fixing any signature drift in test helpers.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\FakeImageJobClock.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\FakeImageJobIdGenerator.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs
git commit -m "feat(vision): add hidden image job manager"
```

## Task 5: Extract Image Work Item Builder From VisionHandler

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add a test proving `generate` behavior stays sync-only**

In `src/Rook.Tests/Handlers/VisionHandlerTests.cs`, add or keep a test equivalent to:

```csharp
[Fact]
public async Task GenerateAsync_AsyncImageProviderStillFailsWithCompatibilityMessage()
{
    var root = CreateTempRoot("rook-vision-async-image-generate");
    var provider = new FakeImageProvider
    {
        OnSubmit = (_, _) => FakeImageProvider.Queued("pred-1"),
    };
    var handler = NewHandlerWithImageProvider(provider, root);
    var inputPath = Path.Combine(root, "input.png");
    File.WriteAllBytes(inputPath, new byte[] { 1, 2, 3 });

    var response = await handler.GenerateAsync(
        GenerateArgs(inputPath, GeminiImageCapabilities.DefaultModel),
        CancellationToken.None);

    Assert.False(response.Success);
    Assert.Contains("Provider returned an async job", response.Data?.ToString());
}
```

Add these private helpers in `VisionHandlerTests`:

```csharp
private static VisionHandler NewHandlerWithImageProvider(
    IImageProvider provider,
    string root)
{
    var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
    {
        new TestImageProviderRegistration(provider),
    });
    return new VisionHandler(
        new ArtifactStore(root),
        new InMemoryGenerationSecretStore(),
        new PromptEnhancer(),
        new ViewportHandler(),
        imageProviderRegistry: registry);
}

private static Dictionary<string, JsonElement> GenerateArgs(
    string inputPath,
    string model)
{
    using var doc = JsonDocument.Parse($$"""
        {
          "prompt": "red cube",
          "input_image_path": "{{JsonEncodedText.Encode(inputPath).ToString()}}",
          "model": "{{model}}",
          "resolution": "1K",
          "aspect_ratio": "auto"
        }
        """);
    var args = new Dictionary<string, JsonElement>();
    foreach (var prop in doc.RootElement.EnumerateObject())
        args[prop.Name] = prop.Value.Clone();
    return args;
}
```

`GenerateAsync` is internal and already accessible to `Rook.Tests` through the project `InternalsVisibleTo` setup.

- [ ] **Step 2: Run test before refactor**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter GenerateAsync_AsyncImageProviderStillFailsWithCompatibilityMessage
```

Expected: PASS before refactor. This is a regression pin.

- [ ] **Step 3: Extract internal work item**

In `VisionHandler.cs`, add:

```csharp
internal sealed class ImageGenerationWorkItemResult
{
    private ImageGenerationWorkItemResult(
        ImageGenerationWorkItem? workItem,
        ApiResponse? failure)
    {
        WorkItem = workItem;
        Failure = failure;
    }

    public ImageGenerationWorkItem? WorkItem { get; }
    public ApiResponse? Failure { get; }
    public bool Success => WorkItem is not null;

    public static ImageGenerationWorkItemResult Ok(ImageGenerationWorkItem workItem)
    {
        if (workItem is null) throw new ArgumentNullException(nameof(workItem));
        return new ImageGenerationWorkItemResult(workItem, failure: null);
    }

    public static ImageGenerationWorkItemResult Fail(ApiResponse failure)
    {
        if (failure is null) throw new ArgumentNullException(nameof(failure));
        return new ImageGenerationWorkItemResult(workItem: null, failure);
    }
}

internal sealed class ImageGenerationWorkItem
{
    public ImageGenerationWorkItem(
        ImageGenerationRequest request,
        ResolvedImageModel resolvedModel,
        IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
        IReadOnlyList<Guid> parentArtifactIds)
    {
        Request = request;
        ResolvedModel = resolvedModel;
        ResolvedMedia = resolvedMedia;
        ParentArtifactIds = parentArtifactIds;
    }

    public ImageGenerationRequest Request { get; }
    public ResolvedImageModel ResolvedModel { get; }
    public IReadOnlyDictionary<MediaRef, ResolvedMedia> ResolvedMedia { get; }
    public IReadOnlyList<Guid> ParentArtifactIds { get; }
}
```

Extract the top half of `GenerateAsync` through request construction into:

```csharp
internal ImageGenerationWorkItemResult BuildImageGenerationWorkItem(
    Dictionary<string, JsonElement> args)
```

The helper must:

- keep the existing `prompt`, `input_image_path`, `reference_image_paths`, max byte checks, model fallback, options decoding, and validation behavior;
- return `ImageGenerationWorkItemResult.Fail(Fail(...))` for the same unknown model, option decode, and validation cases that currently return structured `ApiResponse` failures from `GenerateAsync`;
- keep argument/file validation exceptions unchanged for now, because the existing bridge dispatcher already catches those around `GenerateAsync`;
- return the same `ResolvedImageModel` and `resolvedMedia` that `GenerateAsync` currently uses;
- set `ParentArtifactIds` to `Array.Empty<Guid>()` for now because existing `generate` path is file/path based.

Then change `GenerateAsync` to:

```csharp
var workResult = BuildImageGenerationWorkItem(args);
if (!workResult.Success)
    return workResult.Failure!;

var work = workResult.WorkItem!;
var submit = await work.ResolvedModel.Provider.SubmitAsync(
    work.Request,
    work.ResolvedMedia,
    cancellationToken).ConfigureAwait(false);
```

Preserve the rest of `GenerateAsync`, including:

```csharp
if (submit is not SyncSubmitOutcome sync)
{
    return Fail("Image generation failed. Provider returned an async job.");
}
```

- [ ] **Step 4: Run focused VisionHandler tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "GenerateAsync|GetSettingsOverview|ListImageModels"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\VisionHandler.cs src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "refactor(vision): extract image generation work item"
```

## Task 6: Image Job Operation Handler

**Files:**
- Create: `src/Rook/Handlers/ImageJobOpHandler.cs`
- Test: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

- [ ] **Step 1: Write failing handler tests**

Create `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Handlers;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class ImageJobOpHandlerTests
    {
        private static readonly Guid JobId = Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        private static readonly Guid ArtifactId = Guid.Parse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");

        [Fact]
        public async Task DispatchAsync_Start_ReturnsJobIdAndQueuedState()
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-image-job-handler-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            var inputPath = Path.Combine(root, "input.png");
            File.WriteAllBytes(inputPath, new byte[] { 1, 2, 3 });
            var manager = new StubImageJobManager
            {
                SubmitImpl = (_, _) => ImageJobSubmitResult.Ok(JobId, ImageJobState.Queued),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = await handler.DispatchAsync($$"""
                {
                  "op": "image_generate_start",
                  "prompt": "x",
                  "input_image_path": "{{JsonEncodedText.Encode(inputPath).ToString()}}",
                  "model": "gemini-3.1-flash-image-preview",
                  "resolution": "1K",
                  "aspect_ratio": "auto"
                }
                """);

            Assert.True(response.Success);
            var data = AssertData(response);
            Assert.Equal(JobId.ToString("D"), data["job_id"]);
            Assert.Equal("queued", data["state"]);
        }

        [Fact]
        public void DispatchOffUi_Status_ReturnsSnakeCaseState()
        {
            var manager = new StubImageJobManager
            {
                StatusImpl = _ => ImageJobStatusResult.InFlight(ImageJobState.Materializing, null),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi($$"""{"op":"image_job_status","job_id":"{{JobId:D}}"}""");

            Assert.True(response.Success);
            var data = AssertData(response);
            Assert.Equal("materializing", data["state"]);
        }

        [Fact]
        public void DispatchOffUi_Result_ReturnsBlobFilePath()
        {
            var manager = new StubImageJobManager
            {
                FetchImpl = _ => ImageJobFetchResult.Complete(
                    ArtifactId,
                    new[] { new ImageJobResultFile("image", $"/blob/{ArtifactId:D}/image") }),
            };
            var handler = new ImageJobOpHandler(manager, NewVisionHandler());

            var response = handler.DispatchOffUi($$"""{"op":"image_job_result","job_id":"{{JobId:D}}"}""");

            Assert.True(response.Success);
            var data = AssertData(response);
            Assert.Equal(ArtifactId.ToString("D"), data["result_artifact_id"]);
        }

        [Fact]
        public async Task DispatchAsync_StatusOpRejectedOnAsyncDispatcher()
        {
            var handler = new ImageJobOpHandler(new StubImageJobManager(), NewVisionHandler());

            var response = await handler.DispatchAsync($$"""{"op":"image_job_status","job_id":"{{JobId:D}}"}""");

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
        }

        private static VisionHandler NewVisionHandler() => new VisionHandler();

        private static Dictionary<string, object?> AssertData(ApiResponse response)
        {
            var data = response.Data as Dictionary<string, object?>;
            Assert.NotNull(data);
            return data!;
        }

        private sealed class StubImageJobManager : IImageJobManager
        {
            public Func<ImageJobStartRequest, CancellationToken, ImageJobSubmitResult>? SubmitImpl { get; set; }
            public Func<Guid, ImageJobStatusResult>? StatusImpl { get; set; }
            public Func<Guid, CancellationToken, ImageJobCancelResult>? CancelImpl { get; set; }
            public Func<Guid, ImageJobFetchResult>? FetchImpl { get; set; }
            public Func<int, ImageJobListResult>? ListImpl { get; set; }

            public Task<ImageJobSubmitResult> SubmitAsync(ImageJobStartRequest start, CancellationToken ct) =>
                Task.FromResult(SubmitImpl?.Invoke(start, ct)
                    ?? ImageJobSubmitResult.Fail(new GenerationError(GenerationErrorCode.ExecutionFailed, "submit missing", false)));

            public Task<ImageJobStatusResult> GetStatusAsync(Guid jobId, CancellationToken ct) =>
                Task.FromResult(StatusImpl?.Invoke(jobId)
                    ?? ImageJobStatusResult.Failed(ImageJobState.Error, new GenerationError(GenerationErrorCode.ExecutionFailed, "status missing", false)));

            public Task<ImageJobCancelResult> CancelAsync(Guid jobId, CancellationToken ct) =>
                Task.FromResult(CancelImpl?.Invoke(jobId, ct)
                    ?? ImageJobCancelResult.Fail(new GenerationError(GenerationErrorCode.ExecutionFailed, "cancel missing", false)));

            public Task<ImageJobFetchResult> FetchResultAsync(Guid jobId, CancellationToken ct) =>
                Task.FromResult(FetchImpl?.Invoke(jobId)
                    ?? ImageJobFetchResult.Failed(ImageJobState.Error, new GenerationError(GenerationErrorCode.ExecutionFailed, "fetch missing", false)));

            public Task<ImageJobListResult> ListJobsAsync(int limit, CancellationToken ct) =>
                Task.FromResult(ListImpl?.Invoke(limit)
                    ?? new ImageJobListResult(Array.Empty<ImageJobRecord>(), appliedLimit: limit));
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobOpHandlerTests
```

Expected: compile failure because `ImageJobOpHandler` does not exist.

- [ ] **Step 3: Implement handler**

Create `src/Rook/Handlers/ImageJobOpHandler.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Handlers
{
    public sealed class ImageJobOpHandler
    {
        public const string OpStart = "image_generate_start";
        public const string OpStatus = "image_job_status";
        public const string OpCancel = "image_job_cancel";
        public const string OpResult = "image_job_result";
        public const string OpList = "image_jobs";
        public const int DefaultListLimit = 50;

        private readonly IImageJobManager _manager;
        private readonly VisionHandler _visionHandler;

        public ImageJobOpHandler(IImageJobManager manager, VisionHandler visionHandler)
        {
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _visionHandler = visionHandler ?? throw new ArgumentNullException(nameof(visionHandler));
        }

        public async Task<ApiResponse> DispatchAsync(string? body, CancellationToken cancellationToken = default)
        {
            var args = ParseObjectBody(body);
            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return Fail(Invalid("Image job request missing required 'op' discriminator.", "op"));

            return op switch
            {
                OpStart => await StartAsync(args, cancellationToken).ConfigureAwait(false),
                OpCancel => await CancelAsync(args, cancellationToken).ConfigureAwait(false),
                OpStatus or OpResult or OpList => Fail(Invalid($"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher.", "op")),
                _ => Fail(Invalid($"Unknown image job op '{op}'.", "op")),
            };
        }

        public ApiResponse DispatchOffUi(string? body)
        {
            var args = ParseObjectBody(body);
            var op = GetStringArg(args, "op");
            if (string.IsNullOrEmpty(op))
                return Fail(Invalid("Image job request missing required 'op' discriminator.", "op"));

            return op switch
            {
                OpStatus => Status(args),
                OpResult => Result(args),
                OpList => List(args),
                OpStart or OpCancel => Fail(Invalid($"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher.", "op")),
                _ => Fail(Invalid($"Unknown image job op '{op}'.", "op")),
            };
        }

        private async Task<ApiResponse> StartAsync(Dictionary<string, JsonElement> args, CancellationToken ct)
        {
            var workResult = _visionHandler.BuildImageGenerationWorkItem(args);
            if (!workResult.Success)
                return workResult.Failure!;

            var work = workResult.WorkItem!;
            var start = new ImageJobStartRequest(work.Request, work.ResolvedMedia, work.ParentArtifactIds);
            var result = await _manager.SubmitAsync(start, ct).ConfigureAwait(false);
            if (result.Error is not null) return Fail(result.Error);
            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = result.JobId!.Value.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private async Task<ApiResponse> CancelAsync(Dictionary<string, JsonElement> args, CancellationToken ct)
        {
            if (!TryParseJobId(args, out var jobId, out var error)) return Fail(error!);
            var result = await _manager.CancelAsync(jobId, ct).ConfigureAwait(false);
            if (result.Error is not null) return Fail(result.Error);
            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
            });
        }

        private ApiResponse Status(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var error)) return Fail(error!);
            var result = _manager.GetStatusAsync(jobId, default).GetAwaiter().GetResult();
            if (result.Error is { Code: GenerationErrorCode.InvalidRequest }) return Fail(result.Error);
            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["progress"] = result.Progress is null ? null : ProgressToObj(result.Progress),
                ["result_artifact_id"] = result.ResultArtifactId?.ToString("D"),
                ["error"] = result.Error is null ? null : ErrorToObj(result.Error),
            });
        }

        private ApiResponse Result(Dictionary<string, JsonElement> args)
        {
            if (!TryParseJobId(args, out var jobId, out var error)) return Fail(error!);
            var result = _manager.FetchResultAsync(jobId, default).GetAwaiter().GetResult();
            if (result.Error is not null) return Fail(result.Error);
            var files = new List<Dictionary<string, object?>>();
            foreach (var file in result.Files!)
                files.Add(new Dictionary<string, object?> { ["role"] = file.Role, ["path"] = file.Path });
            return Ok(new Dictionary<string, object?>
            {
                ["job_id"] = jobId.ToString("D"),
                ["state"] = StateToString(result.State),
                ["result_artifact_id"] = result.ResultArtifactId!.Value.ToString("D"),
                ["files"] = files,
            });
        }

        private ApiResponse List(Dictionary<string, JsonElement> args)
        {
            var limit = DefaultListLimit;
            if (args.TryGetValue("limit", out var limitEl)
                && limitEl.ValueKind == JsonValueKind.Number
                && limitEl.TryGetInt32(out var parsed)
                && parsed > 0)
            {
                limit = parsed;
            }
            var result = _manager.ListJobsAsync(limit, default).GetAwaiter().GetResult();
            var jobs = new List<Dictionary<string, object?>>();
            foreach (var job in result.Jobs)
            {
                jobs.Add(new Dictionary<string, object?>
                {
                    ["job_id"] = job.JobId.ToString("D"),
                    ["state"] = StateToString(job.State),
                    ["updated_at"] = job.UpdatedAt.ToString("o", System.Globalization.CultureInfo.InvariantCulture),
                    ["model"] = job.Model,
                    ["provider_name"] = job.Provider,
                    ["result_artifact_id"] = job.ResultArtifactId?.ToString("D"),
                    ["error"] = job.Error is null ? null : ErrorToObj(job.Error),
                });
            }
            return Ok(new Dictionary<string, object?>
            {
                ["jobs"] = jobs,
                ["applied_limit"] = result.AppliedLimit,
            });
        }

        private static bool TryParseJobId(Dictionary<string, JsonElement> args, out Guid jobId, out GenerationError? error)
        {
            jobId = Guid.Empty;
            error = null;
            var raw = GetStringArg(args, "job_id");
            if (string.IsNullOrWhiteSpace(raw) || !Guid.TryParseExact(raw, "D", out jobId) || jobId == Guid.Empty)
            {
                error = Invalid("'job_id' must be a non-empty GUID in 'D' format.", "job_id");
                return false;
            }
            return true;
        }

        private static Dictionary<string, JsonElement> ParseObjectBody(string? body)
        {
            if (string.IsNullOrWhiteSpace(body)) return new Dictionary<string, JsonElement>();
            using var doc = JsonDocument.Parse(body);
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
                throw new ArgumentException("Image job request body must be a JSON object.");
            var dict = new Dictionary<string, JsonElement>();
            foreach (var prop in doc.RootElement.EnumerateObject())
                dict[prop.Name] = prop.Value.Clone();
            return dict;
        }

        private static string? GetStringArg(Dictionary<string, JsonElement> args, string key) =>
            args.TryGetValue(key, out var el) && el.ValueKind == JsonValueKind.String
                ? el.GetString()
                : null;

        private static ApiResponse Ok(object? data) => new() { Success = true, Data = data, HttpStatus = 200 };
        private static ApiResponse Fail(GenerationError error) => new() { Success = false, Data = ErrorToObj(error), HttpStatus = MapStatus(error.Code) };
        private static GenerationError Invalid(string message, string field) => new(GenerationErrorCode.InvalidRequest, message, Retryable: false, Field: field);

        private static int MapStatus(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => 400,
            GenerationErrorCode.UnsupportedMedia => 415,
            GenerationErrorCode.DependencyUnavailable => 503,
            GenerationErrorCode.ExecutionFailed => 500,
            GenerationErrorCode.Cancelled => 200,
            GenerationErrorCode.Interrupted => 200,
            GenerationErrorCode.QuotaExceeded => 429,
            GenerationErrorCode.ContentPolicy => 422,
            _ => 500,
        };

        private static string StateToString(ImageJobState state) => state switch
        {
            ImageJobState.Queued => "queued",
            ImageJobState.Submitting => "submitting",
            ImageJobState.Polling => "polling",
            ImageJobState.Materializing => "materializing",
            ImageJobState.Complete => "complete",
            ImageJobState.Error => "error",
            ImageJobState.Cancelled => "cancelled",
            ImageJobState.Interrupted => "interrupted",
            _ => state.ToString().ToLowerInvariant(),
        };

        private static Dictionary<string, object?> ErrorToObj(GenerationError error) => new()
        {
            ["code"] = ErrorCodeToString(error.Code),
            ["message"] = error.Message,
            ["retryable"] = error.Retryable,
            ["field"] = error.Field,
        };

        private static string ErrorCodeToString(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => "invalid_request",
            GenerationErrorCode.UnsupportedMedia => "unsupported_media",
            GenerationErrorCode.DependencyUnavailable => "dependency_unavailable",
            GenerationErrorCode.ExecutionFailed => "execution_failed",
            GenerationErrorCode.Cancelled => "cancelled",
            GenerationErrorCode.Interrupted => "interrupted",
            GenerationErrorCode.QuotaExceeded => "quota_exceeded",
            GenerationErrorCode.ContentPolicy => "content_policy",
            _ => code.ToString().ToLowerInvariant(),
        };

        private static Dictionary<string, object?> ProgressToObj(GenerationProgress progress) => new()
        {
            ["pct"] = progress.PercentComplete,
            ["message"] = progress.Message,
        };
    }
}
```

- [ ] **Step 4: Run handler tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobOpHandlerTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\Rook\Handlers\ImageJobOpHandler.cs src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "feat(vision): add image job bridge handler"
```

## Task 7: Bridge Routing And Composition

**Files:**
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add failing route-table tests**

In `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`, update `OpRoutes_Contains_All_Expected_Ops` to include:

```csharp
"image_generate_start", "image_job_cancel",
"image_job_status", "image_job_result", "image_jobs",
```

Add route assertions:

```csharp
[InlineData("image_generate_start", "Async")]
[InlineData("image_job_cancel", "Async")]
[InlineData("image_job_status", "OffUi")]
[InlineData("image_job_result", "OffUi")]
[InlineData("image_jobs", "OffUi")]
```

Add a new test:

```csharp
[Fact]
public void ImageJobOps_AreNotVideoOps()
{
    Assert.DoesNotContain("image_generate_start", VisionWebSurface.VideoOps);
    Assert.DoesNotContain("image_job_cancel", VisionWebSurface.VideoOps);
    Assert.DoesNotContain("image_job_status", VisionWebSurface.VideoOps);
    Assert.DoesNotContain("image_job_result", VisionWebSurface.VideoOps);
    Assert.DoesNotContain("image_jobs", VisionWebSurface.VideoOps);
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "OpRoutes_Contains_All_Expected_Ops|OpRoutes_Map_To_Correct_Dispatchers|ImageJobOps_AreNotVideoOps"
```

Expected: route tests fail because image job ops are absent.

- [ ] **Step 3: Wire image job handler into `VisionWebSurface`**

First add a root-owned lazy image job bundle in `RookSubsystemRoot.cs`. Add `using Rook.Services.Vision.Image;` and `using Rook.Services.Vision.Image.Jobs;`, then add fields/properties parallel to `Video`:

```csharp
private readonly Lazy<ImageJobSubsystemBundle> _imageJobs;

public ImageJobSubsystemBundle ImageJobs
{
    get
    {
        if (Volatile.Read(ref _disposed) != 0)
            throw new ObjectDisposedException(
                nameof(RookSubsystemRoot),
                "Image job subsystem accessed after shutdown.");
        return _imageJobs.Value;
    }
}
```

Initialize it in the internal constructor after `_video`:

```csharp
_imageJobs = new Lazy<ImageJobSubsystemBundle>(
    () =>
    {
        var registry = new DefaultImageProviderRegistry(
            VisionProviderRegistrations.CreateImageRegistrations(
                () => SharedGenerationSecretStore.GetSecret(
                    GenerationSecretKeys.GeminiApiKey),
                () => SharedGenerationSecretStore.GetSecret(
                    GenerationSecretKeys.FalApiKey)));
        var manager = new ImageJobManager(
            registry,
            SharedArtifactStore);
        return new ImageJobSubsystemBundle(manager, registry);
    },
    LazyThreadSafetyMode.ExecutionAndPublication);
```

Update `DisposeVideoSubsystemIfCreated()` so the first line still closes the root with `_disposed`, but image jobs are disposed before or alongside video:

```csharp
public void DisposeVideoSubsystemIfCreated()
{
    if (Interlocked.CompareExchange(ref _disposed, 1, 0) != 0)
        return;

    if (_imageJobs.IsValueCreated && _imageJobs.Value.Manager is IDisposable imageDisposable)
        imageDisposable.Dispose();

    if (_video.IsValueCreated)
        _video.Value.Manager.Dispose();
}
```

In `RookPlugin.OnShutdown`, keep the existing call to `DisposeVideoSubsystemIfCreated()`. Do not add a second separate dispose call unless you also prove it is ordered before `_disposed` closes the root. The amended root method disposes both lazy subsystems in one guarded shutdown path.

Add lifecycle tests to `RookSubsystemRootLifecycleTests` in `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`:

```csharp
[Fact]
public void ImageJobs_ReturnsSameInstance_OnRepeatedAccess()
{
    var root = FreshRoot();
    try
    {
        var first = root.ImageJobs;
        var second = root.ImageJobs;

        Assert.Same(first, second);
        Assert.Same(first.Manager, second.Manager);
        Assert.Same(first.Registry, second.Registry);
    }
    finally { root.DisposeVideoSubsystemIfCreated(); }
}

[Fact]
public void ImageJobs_AfterDispose_ThrowsObjectDisposed()
{
    var root = FreshRoot();
    root.DisposeVideoSubsystemIfCreated();

    Assert.Throws<ObjectDisposedException>(() => _ = root.ImageJobs);
}
```

Now update `VisionWebSurface.cs`:

Add field:

```csharp
private readonly ImageJobOpHandler? _imageJobHandler;
```

Update constructors so the primary internal constructor accepts `ImageJobOpHandler? imageJobHandler`. Existing test constructors should pass `null`.

Update the production constructor to pass the shared handler:

```csharp
public VisionWebSurface() : this(
    BuildSharedVisionHandler(),
    BuildSharedVideoHandler(),
    BuildSharedImageJobHandler(),
    RookSubsystemRoot.Instance.SharedArtifactStore)
{ }
```

Add production builder:

```csharp
private static ImageJobOpHandler BuildSharedImageJobHandler()
{
    var handler = BuildSharedVisionHandler();
    var bundle = RookSubsystemRoot.Instance.ImageJobs;
    return new ImageJobOpHandler(bundle.Manager, handler);
}
```

This mirrors the video pattern: `VisionWebSurface` consumes a process-wide root-owned manager instead of constructing a surface-local manager. The root bundle must not add Replicate registrations.

Add routes:

```csharp
[ImageJobOpHandler.OpStart] = VisionOpRoute.Async,
[ImageJobOpHandler.OpCancel] = VisionOpRoute.Async,
[ImageJobOpHandler.OpStatus] = VisionOpRoute.OffUi,
[ImageJobOpHandler.OpResult] = VisionOpRoute.OffUi,
[ImageJobOpHandler.OpList] = VisionOpRoute.OffUi,
```

Add helper:

```csharp
private static readonly HashSet<string> ImageJobOps =
    new(StringComparer.Ordinal)
    {
        ImageJobOpHandler.OpStart,
        ImageJobOpHandler.OpCancel,
        ImageJobOpHandler.OpStatus,
        ImageJobOpHandler.OpResult,
        ImageJobOpHandler.OpList,
    };
```

In `HandleVisionBridgeCallAsync`, route image job ops before the video branch:

```csharp
var isImageJobOp = ImageJobOps.Contains(op!);
var isVideoOp = VideoOps.Contains(op!);

if (isImageJobOp && _imageJobHandler is null)
    return BuildFailure("Image job subsystem unavailable in this surface.");
```

For `VisionOpRoute.Async`:

```csharp
response = isImageJobOp
    ? await DispatchImageJobAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false)
    : isVideoOp
        ? await DispatchVideoAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false)
        : await DispatchAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false);
```

For `VisionOpRoute.OffUi`:

```csharp
response = isImageJobOp
    ? await Task.Run(() => _imageJobHandler!.DispatchOffUi(body)).ConfigureAwait(false)
    : isVideoOp
        ? await Task.Run(() => _videoHandler!.DispatchOffUi(body)).ConfigureAwait(false)
        : await Task.Run(() => _handler.DispatchOffUi(body)).ConfigureAwait(false);
```

Add:

```csharp
private Task<ApiResponse> DispatchImageJobAsyncWithTimeoutAsync(string op, string? body)
    => DispatchWithTimeoutAsync(
        op,
        AsyncOpTimeout,
        token => _imageJobHandler!.DispatchAsync(body, token));
```

- [ ] **Step 4: Run route tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests"
```

Expected: PASS.

- [ ] **Step 5: Boundary scan for native exposure**

Run:

```powershell
rg -n "image_generate_start|image_job_status|image_job_cancel|image_job_result|image_jobs" src\RookNative src\Rook\InternalBridge mcp_server
```

Expected: no hits. These ops are managed bridge only.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\RookSubsystemRoot.cs `
        src\Rook\UI\Vision\VisionWebSurface.cs `
        src\Rook.Tests\Services\Vision\Video\VideoSubsystemFactoryTests.cs `
        src\Rook.Tests\UI\Vision\VisionWebSurfaceTests.cs
git commit -m "feat(vision): route hidden image job bridge ops"
```

## Task 8: Provider Boundary Guards

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add or strengthen no-Replicate assertions**

In `VisionProviderRegistrationsTests`, ensure the default credential metadata test contains:

```csharp
Assert.DoesNotContain(providers, p => p.ProviderName == "replicate");
Assert.DoesNotContain(
    providers.SelectMany(p => p.SecretRequirements),
    r => r.Key == GenerationSecretKeys.ReplicateApiToken);
```

In `VisionHandlerTests`, ensure the default provider-secret rejection test remains:

```csharp
[Fact]
public void SetProviderSecret_RejectsReplicateBecauseDefaultMetadataDoesNotExposeIt()
{
    var store = new InMemoryGenerationSecretStore();
    var handler = NewHandlerWithSecrets(store);

    var response = handler.DispatchOffUi(JsonSerializer.Serialize(new Dictionary<string, object?>
    {
        ["op"] = "set_provider_secret",
        ["provider_name"] = "replicate",
        ["secret_key"] = GenerationSecretKeys.ReplicateApiToken,
        ["value"] = "r8_token",
    }));

    Assert.False(response.Success);
    Assert.Null(store.GetSecret(GenerationSecretKeys.ReplicateApiToken));
    Assert.Contains("Unknown provider", response.Data?.ToString());
}
```

- [ ] **Step 2: Run guard tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionProviderRegistrationsTests|SetProviderSecret_RejectsReplicateBecauseDefaultMetadataDoesNotExposeIt"
```

Expected: PASS.

- [ ] **Step 3: Commit if files changed**

If the assertions were already present and no files changed, skip this commit. Otherwise:

```powershell
git add src\Rook.Tests\Services\Vision\VisionProviderRegistrationsTests.cs `
        src\Rook.Tests\Handlers\VisionHandlerTests.cs
git commit -m "test(vision): preserve Replicate UI boundary"
```

## Task 9: Verification

**Files:**
- No production files unless verification reveals a scoped bug.

- [ ] **Step 1: Run focused image job suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJob|ImageArtifactMaterializerTests"
```

Expected: PASS.

- [ ] **Step 2: Run Vision handler and surface suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionHandlerTests|VisionWebSurfaceTests|ImageJobOpHandlerTests"
```

Expected: PASS.

- [ ] **Step 3: Run provider boundary scans**

Run:

```powershell
rg -n "replicate|Replicate|replicate.api_token" src\Rook\UI\Vision src\RookNative src\Rook\InternalBridge src\Rook\Services\Vision\VisionProviderRegistrations.cs
```

Expected:

- no hits under `src\RookNative`;
- no hits under `src\Rook\UI\Vision`;
- no hits under `src\Rook\InternalBridge`;
- no `replicate` hit in `VisionProviderRegistrations.cs`.

Run:

```powershell
rg -n "image_generate_start|image_job_status|image_job_cancel|image_job_result|image_jobs" src\RookNative mcp_server
```

Expected: no hits.

- [ ] **Step 4: Run broad managed generation suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Vision|Image|Generation|Fal|Replicate"
```

Expected: PASS.

- [ ] **Step 5: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If a local Rhino/tooling prerequisite prevents this from completing, record the exact failure and the focused test evidence. Do not claim full verification unless this passes.

- [ ] **Step 6: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` clean;
- changed files limited to the PR-12 managed/test files listed in this plan;
- no files under `src/RookNative/**`;
- no UI resource edits.

## Self-Review Checklist

- [ ] Existing `generate` op still returns the current sync image response and still rejects async providers.
- [ ] Image job ops are managed-bridge-only.
- [ ] No native route or MCP tool exposes image jobs.
- [ ] No Replicate model is registered in default image catalogs.
- [ ] No Replicate Settings card or credential metadata is exposed.
- [ ] Authenticated materialization uses request factories/context only; providers do not send/read artifact bytes.
- [ ] Materializer/job-manager-owned code sends the request, reads streams, enforces byte limits, resolves MIME, and classifies errors.
- [ ] Image jobs invoke provider `CancelAsync` when a non-terminal job has a `ProviderJobHandle`.
- [ ] Provider `AlreadyTerminalOutcome` from cancel does not overwrite local job state with `Cancelled`; local polling/materialization remains authoritative.
- [ ] Image job manager is owned by `RookSubsystemRoot`, not by individual `VisionWebSurface` instances.
- [ ] Provider-complete is not job-complete until local artifact write succeeds.
- [ ] Result fetch verifies the local image artifact still exists before returning blob paths.
- [ ] Image jobs use in-memory state only; no durable image ledger is introduced.
- [ ] `VideoJobManager` is not generalized or refactored.
- [ ] No live provider calls run in normal tests.
