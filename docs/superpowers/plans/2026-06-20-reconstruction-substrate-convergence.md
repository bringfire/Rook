# Reconstruction Substrate Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the Reconstruction 2D-to-3D subsystem's fal/media/job primitives onto RookVision's proven generation substrate, fixing seven confirmed robustness gaps without rewriting UI/native/MCP or touching green Vision code.

**Architecture:** `FalReconstructionProvider` consumes the shared `FalApiClient` + `FalLifecycleMapper` + `FalErrorMapper` and returns the shared `Provider*Outcome` / `ProviderResultEnvelope` types (keeping a reconstruction-specific `IReconstructionProvider` interface, not the generic). `ReconstructionJobManager` adopts the Vision background-execution lifecycle (per-job `Task.Run`, shutdown CTS, single-flight, startup reconcile). `ReconstructionPackageMaterializer` consumes the shared envelope, downloads via a new disciplined `ReconstructionRemoteAssetDownloader`, and enforces a "≥1 model asset" package invariant. `ReconstructionFailure` stays the public HTTP DTO; `GenerationError` is mapped into it at the boundary.

**Tech Stack:** C# (.NET, RhinoCommon companion plugin `src/Rook/`), xUnit (`src/Rook.Tests/`), `System.Text.Json.Nodes`. fal.ai queue API via shared `FalApiClient`.

**Source spec:** [`docs/superpowers/specs/2026-06-20-reconstruction-substrate-convergence-design.md`](../specs/2026-06-20-reconstruction-substrate-convergence-design.md)

## Global Constraints

- Work ENTIRELY in the worktree `C:/Users/aryan/source/repos/Rook/.worktrees/reconstruction-2d-to-3d` on branch `codex/reconstruction-2d-to-3d`. Never edit the main checkout.
- Do NOT modify any RookVision file under `src/Rook/Services/Vision/` (Fal, Generation, Image, Video). They are the shared substrate; consume them, do not change them.
- Do NOT modify native (`src/RookNative/`), MCP (`mcp_server/`), the import route, the `reconstruction_package`/`import_manifest` schema, or the ledger state/stage enum vocabulary.
- No fal/HTTP boundary may throw a bare `InvalidOperationException`. Every fal failure becomes a typed `GenerationError`; every download failure a typed materialization failure.
- Keep `ReconstructionFailure` as the public HTTP response DTO. Map `GenerationError → ReconstructionFailure` only at the handler/manager boundary.
- No sync-over-async (`.GetAwaiter().GetResult()`) on any new code path.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. Frequent commits.
- Test run note: building `src/Rook.Tests` deploys `Rook.rhp` into `%AppData%` (it touches the local Rhino install). This is expected; do not be alarmed by the deploy step.
- Test command shape: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~<Name>" --no-restore`
- Baseline that must stay green: existing 55 reconstruction C# tests + 17 MCP tests.
- End every commit message with the Co-Authored-By trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**Modified (reconstruction-owned):**
- `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` — provider rewritten onto shared mappers/outcomes; the throwing `FalReconstructionQueueClient` and the duplicate `ReconstructionProviderSubmitResult`/`StatusResult`/`LifecycleState` types removed; source publisher takes bytes+mime.
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — consumes shared outcomes; gains background execution, single-flight, dispose, reconcile.
- `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs` — consumes `ProviderResultEnvelope`; uses the new downloader; enforces the model-asset invariant.
- `src/Rook/Handlers/ReconstructionOpHandler.cs` — `GenerationError → ReconstructionFailure` mapping at the boundary.
- `src/Rook/RookSubsystemRoot.cs` — wiring: new downloader, dispose, reconcile-on-start.

**Created (reconstruction-owned):**
- `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs` — disciplined async downloader (W4).
- `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs` — `GenerationError → ReconstructionFailure` helper (W7 boundary).

**Tests (modified/created under `src/Rook.Tests/Services/Reconstruction/`):**
- `Fal/FalReconstructionProviderTests.cs`, `ReconstructionJobManagerTests.cs`, `ReconstructionPackageMaterializerTests.cs` (modify), and new `ReconstructionRemoteAssetDownloaderTests.cs`.

**Consumed (shared, READ-ONLY) — verbatim signatures the tasks rely on:**

```csharp
// src/Rook/Services/Vision/Fal/FalApiClient.cs
public sealed class FalApiClient {
  public FalApiClient(HttpClient? httpClient = null);
  public Task<FalHttpResponse> PostJsonAsync(string apiKey, Uri url, string bodyJson, CancellationToken ct);
  public Task<FalHttpResponse> GetAsync(string apiKey, Uri url, CancellationToken ct);
  public Task<FalHttpResponse> SendAsync(string apiKey, HttpMethod method, Uri url, string? bodyJson, CancellationToken ct);
  public Task<string> UploadFileToCdnAsync(string apiKey, string fileName, byte[] bytes, string contentType, FalUploadPlatformHeaders platformHeaders, CancellationToken ct);
}
public readonly struct FalUploadPlatformHeaders { public static FalUploadPlatformHeaders ForSourceUpload(int objectLifecycleSeconds); }
// src/Rook/Services/Vision/Fal/FalHttpResponse.cs
public sealed class FalHttpResponse { public int StatusCode {get;} public string Body {get;} public IReadOnlyDictionary<string,IReadOnlyList<string>> Headers {get;} public bool IsSuccessStatusCode {get;} }
// src/Rook/Services/Vision/Fal/FalLifecycleMapper.cs
public static class FalLifecycleMapper {
  public static ProviderJobHandle ParseSubmitHandle(JsonNode submitBody, string cancelHttpMethod);
  public static ProviderStatusOutcome MapStatus(ProviderJobHandle handle, JsonNode statusBody);
}
// src/Rook/Services/Vision/Fal/FalErrorMapper.cs
public static class FalErrorMapper { public static GenerationError MapHttpFailure(FalHttpResponse response); }
// src/Rook/Services/Vision/Generation/ — outcomes & envelope
public abstract class ProviderSubmitOutcome {}
public sealed class QueuedSubmitOutcome : ProviderSubmitOutcome { public QueuedSubmitOutcome(ProviderJobHandle Handle); public ProviderJobHandle Handle {get;} }
public sealed class FailedSubmitOutcome : ProviderSubmitOutcome { public FailedSubmitOutcome(GenerationError Error); public GenerationError Error {get;} }
public sealed class SyncSubmitOutcome : ProviderSubmitOutcome { public SyncSubmitOutcome(ProviderResultOutcome Result); public ProviderResultOutcome Result {get;} }
public abstract class ProviderStatusOutcome {}
public sealed class InFlightStatusOutcome : ProviderStatusOutcome { public InFlightStatusOutcome(GenerationLifecycleState State, GenerationProgress? Progress); }
public sealed class ProviderCompleteStatusOutcome : ProviderStatusOutcome { public ProviderCompleteStatusOutcome(ProviderJobHandle UpdatedHandle); public ProviderJobHandle UpdatedHandle {get;} }
public sealed class FailedStatusOutcome : ProviderStatusOutcome { public FailedStatusOutcome(GenerationError Error); public GenerationError Error {get;} }
public abstract class ProviderResultOutcome {}
public sealed class SuccessResultOutcome : ProviderResultOutcome { public SuccessResultOutcome(ProviderResultEnvelope Envelope); public ProviderResultEnvelope Envelope {get;} }
public sealed class FailedResultOutcome : ProviderResultOutcome { public FailedResultOutcome(GenerationError Error); public GenerationError Error {get;} }
public abstract class ProviderCancelOutcome {}
public sealed class CanceledOutcome : ProviderCancelOutcome {}
public sealed class AlreadyTerminalOutcome : ProviderCancelOutcome { public AlreadyTerminalOutcome(GenerationLifecycleState TerminalState); }
public sealed class FailedCancelOutcome : ProviderCancelOutcome { public FailedCancelOutcome(GenerationError Error); }
public sealed class ProviderJobHandle {
  public ProviderJobHandle(string providerJobId, Uri? statusUrl=null, Uri? responseUrl=null, Uri? cancelUrl=null, string? cancelHttpMethod=null, string? providerResultToken=null, IReadOnlyDictionary<string,JsonNode>? providerMetadata=null);
  public string ProviderJobId {get;} public Uri? StatusUrl {get;} public Uri? ResponseUrl {get;} public Uri? CancelUrl {get;} public string? CancelHttpMethod {get;}
}
public sealed class ProviderResultEnvelope { public ProviderResultEnvelope(IReadOnlyList<ResultArtifact> Artifacts, IReadOnlyDictionary<string,JsonNode> EnvelopeMetadata); public IReadOnlyList<ResultArtifact> Artifacts {get;} }
public sealed class ResultArtifact { public ResultArtifact(string Role, ArtifactBody Body, string? DeclaredMimeType, IReadOnlyDictionary<string,JsonNode> ProviderMetadata); public string Role {get;} public ArtifactBody Body {get;} public string? DeclaredMimeType {get;} }
public abstract class ArtifactBody {}
public sealed class RemoteArtifactBody : ArtifactBody { public RemoteArtifactBody(Uri Url, TimeSpan? SignedUrlTtl=null); public Uri Url {get;} }
public sealed class InlineArtifactBody : ArtifactBody { public InlineArtifactBody(byte[] Bytes); public byte[] Bytes {get;} }
public sealed record GenerationError(GenerationErrorCode Code, string Message, bool Retryable, string? Field=null, string? ProviderErrorCode=null, IReadOnlyDictionary<string,JsonNode>? ProviderDetail=null);
public enum GenerationErrorCode { InvalidRequest, UnsupportedMedia, DependencyUnavailable, ExecutionFailed, Cancelled, Interrupted, QuotaExceeded, ContentPolicy }
public static class GenerationSecretKeys { public const string FalApiKey = "fal.api_key"; }
```

---

## Task 1: W0 — Confirm canonical `ReplaceJsonBlob`; do not touch main

**Files:**
- Inspect: `src/Rook/Artifacts/ArtifactStore.cs`, `src/Rook/Artifacts/Artifact.cs` (worktree)
- Test: `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs` (worktree)

**Context / decision:** The worktree (committed) and main (uncommitted) `ReplaceJsonBlob` implementations have diverged. Worktree defines `ReplaceJsonBlobResultCode`/`ReplaceJsonBlobResult` in `Artifact.cs` beside `AppendBlobResult` (this already satisfies the reviewer's P4 tidy). Main defines them inline in `ArtifactStore.cs` and adds a test seam `ReplaceJsonBlobFileReplaceOverrideForTests`. Neither is a strict superset.

**Decision for this pass:** The worktree's committed version is canonical for branch `codex/reconstruction-2d-to-3d` (it is what the rest of the reconstruction stack imports, and its type placement matches P4). Reconciling main's divergent copy is the user's separate, explicit action — **do not revert or edit main**, and do not port main's test seam unless a test in this task actually needs it.

- [ ] **Step 1: Verify the worktree version is self-consistent and the P4 tidy is already done**

Run:
```bash
grep -n "ReplaceJsonBlobResultCode\|ReplaceJsonBlobResult" .worktrees/reconstruction-2d-to-3d/src/Rook/Artifacts/Artifact.cs
```
Expected: both types are declared in `Artifact.cs` (around lines 115/127), beside `AppendBlobResult`. No action needed for P4.

- [ ] **Step 2: Confirm the existing ReplaceJsonBlob tests pass (baseline lock)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ArtifactStoreTests.ReplaceJsonBlob" --no-restore`
Expected: PASS (5 tests).

- [ ] **Step 3: Record the reconciliation note for the user (no code change)**

Add a single line to the spec's W0 section is unnecessary; instead leave the decision in this plan. The user reconciles main's uncommitted copy separately. No commit needed for this task unless Step 1 reveals the tidy is missing — in which case move the two result types into `Artifact.cs` beside `AppendBlobResult` and commit:

```bash
git add src/Rook/Artifacts/Artifact.cs src/Rook/Artifacts/ArtifactStore.cs
git commit -m "refactor(artifacts): keep ReplaceJsonBlob result types beside AppendBlobResult

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: W1+W7 — Provider submit/status/cancel on shared mappers & outcomes

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (poll glue only; keep lazy model for now)
- Modify: `src/Rook/RookSubsystemRoot.cs` (provider construction)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

**Interfaces:**
- Produces — the new provider contract (later tasks consume these exact types):
```csharp
namespace Rook.Services.Reconstruction.Fal;

public sealed record ReconstructionProviderSubmitRequest(string ModelId, Uri InputImageUrl, JsonObject Options);

public interface IReconstructionProvider
{
    Task<ProviderSubmitOutcome> SubmitAsync(ReconstructionProviderSubmitRequest request, CancellationToken ct);
    Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct);
    Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct); // body added in Task 5; stub-throws NotImplemented here
    Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct);
}
```
- Consumes — shared `FalApiClient`, `FalLifecycleMapper`, `FalErrorMapper`, `ProviderJobHandle`, the outcome unions (see File Structure).
- Removes — `IFalReconstructionQueueClient`, `FalReconstructionQueueClient`, `ReconstructionProviderSubmitResult`, `ReconstructionProviderStatusResult`, `ReconstructionProviderLifecycleState`.

- [ ] **Step 1: Write failing tests for submit-handle parse + status mapping + error mapping**

Add to `FalReconstructionProviderTests.cs`. A fake `FalApiClient` is not available, so test against a seam: construct `FalReconstructionProvider` with a fake `IFalTransport` (a tiny new internal interface the provider depends on, implemented in prod by a thin adapter over `FalApiClient`). Define the seam in the same file as the provider:

```csharp
// In FalReconstructionProvider.cs (production)
public interface IFalTransport
{
    Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct);
    Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct);
    Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct);
}
```

Test code:
```csharp
private static FalHttpResponse Resp(int status, string body) =>
    new(status, body, new Dictionary<string, IReadOnlyList<string>>());

private sealed class FakeTransport : IFalTransport
{
    public Queue<FalHttpResponse> Posts = new();
    public Queue<FalHttpResponse> Gets = new();
    public Queue<FalHttpResponse> Sends = new();
    public Task<FalHttpResponse> PostJsonAsync(Uri u, string b, CancellationToken ct) => Task.FromResult(Posts.Dequeue());
    public Task<FalHttpResponse> GetAsync(Uri u, CancellationToken ct) => Task.FromResult(Gets.Dequeue());
    public Task<FalHttpResponse> SendAsync(HttpMethod m, Uri u, string? b, CancellationToken ct) => Task.FromResult(Sends.Dequeue());
}

[Fact]
public async Task Submit_Queued_ReturnsHandleWithRequestId()
{
    var t = new FakeTransport();
    t.Posts.Enqueue(Resp(200, @"{""request_id"":""req-1"",""status_url"":""https://queue.fal.run/s"",""response_url"":""https://queue.fal.run/r"",""cancel_url"":""https://queue.fal.run/c""}"));
    var p = new FalReconstructionProvider(t);
    var outcome = await p.SubmitAsync(new ReconstructionProviderSubmitRequest("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", new Uri("https://cdn.fal.run/img.png"), new JsonObject()), CancellationToken.None);
    var queued = Assert.IsType<QueuedSubmitOutcome>(outcome);
    Assert.Equal("req-1", queued.Handle.ProviderJobId);
}

[Fact]
public async Task Submit_401_ReturnsFailedSubmitWithTypedError()
{
    var t = new FakeTransport();
    t.Posts.Enqueue(Resp(401, @"{""detail"":""bad key""}"));
    var p = new FalReconstructionProvider(t);
    var outcome = await p.SubmitAsync(new ReconstructionProviderSubmitRequest("m", new Uri("https://cdn.fal.run/i.png"), new JsonObject()), CancellationToken.None);
    var failed = Assert.IsType<FailedSubmitOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, failed.Error.Code);
}

[Fact]
public async Task Status_InProgress_MapsToInFlight()
{
    var t = new FakeTransport();
    t.Gets.Enqueue(Resp(200, @"{""status"":""IN_PROGRESS""}"));
    var p = new FalReconstructionProvider(t);
    var handle = new ProviderJobHandle("req-1", statusUrl: new Uri("https://queue.fal.run/s"));
    var outcome = await p.GetStatusAsync(handle, CancellationToken.None);
    Assert.IsType<InFlightStatusOutcome>(outcome);
}

[Fact]
public async Task Status_429_ReturnsFailedStatusRetryable()
{
    var t = new FakeTransport();
    t.Gets.Enqueue(new FalHttpResponse(429, "{}", new Dictionary<string, IReadOnlyList<string>> { ["x-fal-needs-retry"] = new[] { "true" } }));
    var p = new FalReconstructionProvider(t);
    var outcome = await p.GetStatusAsync(new ProviderJobHandle("req-1", statusUrl: new Uri("https://queue.fal.run/s")), CancellationToken.None);
    var failed = Assert.IsType<FailedStatusOutcome>(outcome);
    Assert.Equal(GenerationErrorCode.QuotaExceeded, failed.Error.Code);
    Assert.True(failed.Error.Retryable);
}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests" --no-restore`
Expected: FAIL to compile / type mismatch (provider still returns old `Reconstruction*Result` types).

- [ ] **Step 3: Rewrite the provider onto the shared mappers/outcomes**

Replace the provider body. Submit:
```csharp
public async Task<ProviderSubmitOutcome> SubmitAsync(ReconstructionProviderSubmitRequest request, CancellationToken ct)
{
    var payload = BuildSubmitPayload(request); // existing payload builder, kept
    var url = QueueSubmitUri(request.ModelId);
    var resp = await _transport.PostJsonAsync(url, payload.ToJsonString(), ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode)
        return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(resp));
    var body = JsonNode.Parse(resp.Body) ?? new JsonObject();
    var handle = FalLifecycleMapper.ParseSubmitHandle(body, cancelHttpMethod: "PUT");
    return new QueuedSubmitOutcome(handle);
}
```
Status:
```csharp
public async Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.StatusUrl is null)
        return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction job has no status URL.", Retryable: false));
    var resp = await _transport.GetAsync(handle.StatusUrl, ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode)
        return new FailedStatusOutcome(FalErrorMapper.MapHttpFailure(resp));
    var body = JsonNode.Parse(resp.Body) ?? new JsonObject();
    return FalLifecycleMapper.MapStatus(handle, body);
}
```
Cancel (reuse the existing CDN/cancel-url logic, but map failures):
```csharp
public async Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.CancelUrl is null) return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
    var method = new HttpMethod(handle.CancelHttpMethod ?? "PUT");
    var resp = await _transport.SendAsync(method, handle.CancelUrl, null, ct).ConfigureAwait(false);
    if (resp.IsSuccessStatusCode) return new CanceledOutcome();
    if (resp.StatusCode == 400) return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
    return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(resp));
}
```
`FetchResultAsync` body comes in Task 5 — for now: `=> throw new NotImplementedException();` (no test exercises it until Task 5).

Delete `IFalReconstructionQueueClient`, `FalReconstructionQueueClient`, `ReconstructionProviderSubmitResult`, `ReconstructionProviderStatusResult`, `ReconstructionProviderLifecycleState`. Add the prod `FalApiTransport : IFalTransport` adapter:
```csharp
public sealed class FalApiTransport : IFalTransport
{
    private readonly FalApiClient _client;
    private readonly Func<string?> _apiKey;
    public FalApiTransport(FalApiClient client, Func<string?> apiKey) { _client = client; _apiKey = apiKey; }
    private string Key() => _apiKey() ?? throw new GenerationSecretMissingException(); // see note
    public Task<FalHttpResponse> PostJsonAsync(Uri url, string body, CancellationToken ct) => _client.PostJsonAsync(Key(), url, body, ct);
    public Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct) => _client.GetAsync(Key(), url, ct);
    public Task<FalHttpResponse> SendAsync(HttpMethod m, Uri url, string? body, CancellationToken ct) => _client.SendAsync(Key(), m, url, body, ct);
}
```
Missing-key handling: rather than a new exception type, have the manager check `secrets.HasSecret(GenerationSecretKeys.FalApiKey)` before submit and fail with `ReconstructionFailure(code:"missing_credential", retryable:false)` (the manager already owns submit validation). Drop the `GenerationSecretMissingException` idea; `FalApiTransport.Key()` returns `_apiKey()!` and the manager guarantees presence.

- [ ] **Step 4: Update the manager poll glue to consume the new outcomes (keep lazy model)**

In `ReconstructionJobManager.PollActiveJobAsync`, build a `ProviderJobHandle` from the ledger record and switch on `ProviderStatusOutcome`:
```csharp
var handle = new ProviderJobHandle(
    providerJobId: job.ProviderJobId!,
    statusUrl: OptionalUri(job.ProviderStatusUrl),
    responseUrl: OptionalUri(job.ProviderResponseUrl),
    cancelUrl: OptionalUri(job.ProviderCancelUrl),
    cancelHttpMethod: job.ProviderCancelHttpMethod);

var status = await _provider.GetStatusAsync(handle, ct).ConfigureAwait(false);
switch (status)
{
    case InFlightStatusOutcome:
        _ledger.Append(job with { Stage = ReconstructionJobStage.Polling, UpdatedAt = Now() });
        return;
    case FailedStatusOutcome f:
        _ledger.Append(job with { State = ReconstructionJobState.Error, Stage = ReconstructionJobStage.Error, Error = ReconstructionErrorMapping.ToFailure(f.Error), UpdatedAt = Now() });
        return;
    case ProviderCompleteStatusOutcome complete:
        // FetchResult + materialize wired in Task 5/6; for now leave a TODO-free guard:
        // Until Task 5, treat complete by fetching via FetchResultAsync (NotImplemented) — so DO NOT
        // ship Task 2 to "complete" path in isolation; Task 5/6 land in the same slice branch before merge.
        break;
}
```
Note: `ReconstructionErrorMapping.ToFailure` is created in Task 9 but is a pure function with no dependencies; create the file early here (it is needed to compile). Its body:
```csharp
// src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs
public static class ReconstructionErrorMapping
{
    public static ReconstructionFailure ToFailure(GenerationError e) => new(
        Code: MapCode(e.Code),
        Message: e.Message,
        Retryable: e.Retryable,
        Field: e.Field,
        Details: new Dictionary<string, object?> { ["provider_error_code"] = e.ProviderErrorCode });

    private static string MapCode(GenerationErrorCode c) => c switch
    {
        GenerationErrorCode.InvalidRequest => "invalid_request",
        GenerationErrorCode.UnsupportedMedia => "invalid_source_file",
        GenerationErrorCode.DependencyUnavailable => "provider_unavailable",
        GenerationErrorCode.QuotaExceeded => "quota_exceeded",
        GenerationErrorCode.Cancelled => "cancelled",
        GenerationErrorCode.Interrupted => "interrupted",
        GenerationErrorCode.ContentPolicy => "content_policy",
        _ => "provider_failed",
    };
}
```
Update `RookSubsystemRoot.CreateReconstruction` to build `new FalReconstructionProvider(new FalApiTransport(falClient, () => SharedGenerationSecretStore.GetSecret(GenerationSecretKeys.FalApiKey)))`.

- [ ] **Step 5: Run tests, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS (the four new provider tests + existing reconstruction tests adjusted to the new types).

- [ ] **Step 6: Commit**
```bash
git add src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs src/Rook/RookSubsystemRoot.cs src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs
git commit -m "refactor(reconstruction): route fal submit/status/cancel through shared mappers and outcomes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: W2 — Resolve source bytes/MIME before upload; publisher stops reading files

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`FalReconstructionSourceImagePublisher`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (resolve bytes/mime, call publisher)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

**Interfaces:**
- Produces:
```csharp
public interface IReconstructionSourceImagePublisher
{
    Task<Uri> PublishAsync(byte[] bytes, string mimeType, string fileName, CancellationToken ct);
}
```
- Consumes: `FalApiClient.UploadFileToCdnAsync`, `FalUploadPlatformHeaders.ForSourceUpload`, `ArtifactStore` blob read (manager side).

- [ ] **Step 1: Write the failing test — publisher never touches the filesystem**

```csharp
private sealed class CapturingPublisher : IReconstructionSourceImagePublisher
{
    public byte[]? Bytes; public string? Mime; public string? FileName;
    public Task<Uri> PublishAsync(byte[] bytes, string mime, string fileName, CancellationToken ct)
    { Bytes = bytes; Mime = mime; FileName = fileName; return Task.FromResult(new Uri("https://cdn.fal.run/u.png")); }
}

[Fact]
public async Task Publisher_ReceivesResolvedBytesAndMime_NotAPath()
{
    // Arrange a manager with a real ArtifactStore holding one generated_image artifact,
    // a CapturingPublisher, and a stub provider. (Reuse the existing manager test harness builder.)
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var pub = new CapturingPublisher();
    var manager = bundle.BuildManager(publisher: pub, provider: bundle.QueuedThenInflightProvider());
    await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    Assert.NotNull(pub.Bytes);
    Assert.False(string.IsNullOrEmpty(pub.Mime));
}
```
(`ReconstructionTestBundle` is the existing manager test helper; extend it with `WithSourceImage`/`BuildManager(publisher:, provider:)` if not present.)

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Publisher_ReceivesResolvedBytesAndMime" --no-restore`
Expected: FAIL (publisher still has the `(Artifact, role, absolutePath)` signature).

- [ ] **Step 3: Change the publisher to byte-based; resolve bytes in the manager**

Publisher:
```csharp
public sealed class FalReconstructionSourceImagePublisher : IReconstructionSourceImagePublisher
{
    public const int SourceImageExpirationSeconds = 3600;
    private readonly FalApiClient _client;
    private readonly Func<string?> _apiKey;
    public FalReconstructionSourceImagePublisher(FalApiClient client, Func<string?> apiKey) { _client = client; _apiKey = apiKey; }
    public Task<Uri> PublishAsync(byte[] bytes, string mimeType, string fileName, CancellationToken ct) =>
        _client.UploadFileToCdnAsync(_apiKey()!, fileName, bytes, mimeType, FalUploadPlatformHeaders.ForSourceUpload(SourceImageExpirationSeconds), ct)
            .ContinueWith(t => new Uri(t.Result), ct, TaskContinuationOptions.OnlyOnRanToCompletion, TaskScheduler.Default);
}
```
Manager submit path: after source validation yields the artifact + role, read bytes + mime from the store and pass them to the publisher (no path to the publisher):
```csharp
var (bytes, mime, fileName) = ReadSourceBlob(_store, artifact, validation.Role); // store.OpenBlob → bytes; mime from blob metadata/extension map
var inputUrl = await _sourcePublisher.PublishAsync(bytes, mime, fileName, ct).ConfigureAwait(false);
```
Delete the `File.ReadAllBytes(absolutePath)` path entirely. `ReadSourceBlob` lives in the manager (it owns the store), keeping the provider/publisher storage-agnostic.

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "refactor(reconstruction): resolve source bytes/mime in manager; publisher is storage-agnostic

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: W4 — `ReconstructionRemoteAssetDownloader` (disciplined async download)

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionRemoteAssetDownloaderTests.cs`

**Interfaces:**
- Produces:
```csharp
public sealed record ReconstructionDownloadResult(bool Success, byte[]? Bytes, string? MimeType, GenerationError? Error);

public interface IReconstructionRemoteAssetDownloader
{
    Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct);
}
```
- Consumes: nothing from prior tasks (standalone). Injected `HttpMessageHandler` for tests.

**Behavior:** absolute-https only; `HttpCompletionOption.ResponseHeadersRead`; role-aware byte cap (models larger than thumbnails/textures); enforce cap from `Content-Length` header AND while streaming; retry transient only (5xx, 408, 429, `HttpRequestException`/`TaskCanceledException`-without-user-cancel) up to 3 attempts; never retry validation (404) or user cancellation; typed `GenerationError` on failure.

- [ ] **Step 1: Write failing tests (7 cases) with a stub handler**

```csharp
private sealed class StubHandler : HttpMessageHandler
{
    public Queue<Func<HttpResponseMessage>> Responses = new();
    public int Calls;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r, CancellationToken ct)
    { Calls++; ct.ThrowIfCancellationRequested(); return Task.FromResult(Responses.Dequeue()()); }
}
private static HttpResponseMessage Ok(byte[] body, string mime = "model/gltf-binary", long? len = null)
{ var m = new HttpResponseMessage(System.Net.HttpStatusCode.OK) { Content = new ByteArrayContent(body) }; m.Content.Headers.ContentType = new(mime); if (len is { } l) m.Content.Headers.ContentLength = l; return m; }
private static IReconstructionRemoteAssetDownloader Make(StubHandler h) =>
    new ReconstructionRemoteAssetDownloader(new HttpClient(h), maxBytesByRole: r => r.StartsWith("model_") ? 100_000_000 : 25_000_000);

[Fact] public async Task Download_Success_ReturnsBytesAndMime() {
    var h = new StubHandler(); h.Responses.Enqueue(() => Ok(new byte[]{1,2,3}));
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
    Assert.True(r.Success); Assert.Equal(3, r.Bytes!.Length); }

[Fact] public async Task Download_HeaderCapExceeded_FailsWithoutStreaming() {
    var h = new StubHandler(); h.Responses.Enqueue(() => Ok(new byte[]{1}, len: 999_999_999_999));
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
    Assert.False(r.Success); Assert.Equal(GenerationErrorCode.UnsupportedMedia, r.Error!.Code); }

[Fact] public async Task Download_StreamCapExceeded_Fails() {
    var big = new byte[26_000_000]; var h = new StubHandler(); h.Responses.Enqueue(() => Ok(big)); // role texture → 25MB cap
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/t.png"), "texture", CancellationToken.None);
    Assert.False(r.Success); }

[Fact] public async Task Download_EmptyBody_Fails() {
    var h = new StubHandler(); h.Responses.Enqueue(() => Ok(Array.Empty<byte>()));
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
    Assert.False(r.Success); }

[Fact] public async Task Download_404_NoRetry() {
    var h = new StubHandler(); h.Responses.Enqueue(() => new HttpResponseMessage(System.Net.HttpStatusCode.NotFound));
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
    Assert.False(r.Success); Assert.Equal(1, h.Calls); }

[Fact] public async Task Download_500_RetriesThenFails() {
    var h = new StubHandler(); for (int i=0;i<3;i++) h.Responses.Enqueue(() => new HttpResponseMessage(System.Net.HttpStatusCode.InternalServerError));
    var r = await Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", CancellationToken.None);
    Assert.False(r.Success); Assert.Equal(3, h.Calls); }

[Fact] public async Task Download_Cancellation_NoRetry() {
    var h = new StubHandler(); using var cts = new CancellationTokenSource(); cts.Cancel();
    await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Make(h).DownloadAsync(new Uri("https://cdn.fal.run/a.glb"), "model_glb", cts.Token));
    Assert.Equal(0, h.Calls); }
```

- [ ] **Step 2: Run, verify fail (type does not exist)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionRemoteAssetDownloaderTests" --no-restore`
Expected: FAIL (compile).

- [ ] **Step 3: Implement the downloader**

```csharp
public sealed class ReconstructionRemoteAssetDownloader : IReconstructionRemoteAssetDownloader
{
    private readonly HttpClient _http;
    private readonly Func<string, long> _maxBytesByRole;
    private const int MaxAttempts = 3;

    public ReconstructionRemoteAssetDownloader(HttpClient http, Func<string, long> maxBytesByRole)
    { _http = http; _maxBytesByRole = maxBytesByRole; }

    public async Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
    {
        if (!url.IsAbsoluteUri || url.Scheme != Uri.UriSchemeHttps)
            return Fail(GenerationErrorCode.InvalidRequest, "Asset URL must be absolute HTTPS.");
        var cap = _maxBytesByRole(role);
        for (var attempt = 1; ; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                using var resp = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    if (IsTransient((int)resp.StatusCode) && attempt < MaxAttempts) continue;
                    return Fail(GenerationErrorCode.DependencyUnavailable, $"Asset download failed: HTTP {(int)resp.StatusCode}.");
                }
                if (resp.Content.Headers.ContentLength is { } len && len > cap)
                    return Fail(GenerationErrorCode.UnsupportedMedia, $"Asset exceeds {cap} bytes (declared {len}).");
                var mime = resp.Content.Headers.ContentType?.MediaType;
                await using var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
                var bytes = await ReadCappedAsync(stream, cap, ct).ConfigureAwait(false);
                if (bytes is null) return Fail(GenerationErrorCode.UnsupportedMedia, $"Asset exceeds {cap} bytes while streaming.");
                if (bytes.Length == 0) return Fail(GenerationErrorCode.ExecutionFailed, "Asset body was empty.");
                return new ReconstructionDownloadResult(true, bytes, mime, null);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
            catch (Exception) when (attempt < MaxAttempts) { /* transient transport/timeout: retry */ }
            catch (Exception ex) { return Fail(GenerationErrorCode.DependencyUnavailable, $"Asset download error: {ex.Message}"); }
        }
    }

    private static async Task<byte[]?> ReadCappedAsync(Stream s, long cap, CancellationToken ct)
    {
        using var ms = new MemoryStream();
        var buf = new byte[81920]; int n; long total = 0;
        while ((n = await s.ReadAsync(buf.AsMemory(0, buf.Length), ct).ConfigureAwait(false)) > 0)
        { total += n; if (total > cap) return null; ms.Write(buf, 0, n); }
        return ms.ToArray();
    }

    private static bool IsTransient(int s) => s >= 500 || s == 408 || s == 429;
    private static ReconstructionDownloadResult Fail(GenerationErrorCode c, string m) => new(false, null, null, new GenerationError(c, m, Retryable: c is GenerationErrorCode.DependencyUnavailable));
}
```

- [ ] **Step 4: Run, verify all 7 pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionRemoteAssetDownloaderTests" --no-restore`
Expected: PASS (7).

- [ ] **Step 5: Commit**
```bash
git add src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs src/Rook.Tests/Services/Reconstruction/ReconstructionRemoteAssetDownloaderTests.cs
git commit -m "feat(reconstruction): add disciplined async remote asset downloader (cap/retry/streaming)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: W3 — `FetchResultAsync` parses fal JSON into a shared `ProviderResultEnvelope`

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`FetchResultAsync` body + fal-shape parsing)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

**Interfaces:**
- Consumes: `ProviderResultEnvelope`, `ResultArtifact`, `RemoteArtifactBody`, `FalErrorMapper`.
- Produces: `FetchResultAsync(ProviderJobHandle) → ProviderResultOutcome`. Role strings use `ReconstructionFileRoles` constants.

**Fal-shape knowledge lives HERE only.** The materializer (Task 6) must not see `model_urls`/`texture_urls`/`model_glb`.

- [ ] **Step 1: Write failing tests — Hunyuan & Meshy payloads → role'd artifacts; 422 → failure**

```csharp
[Fact]
public async Task Fetch_HunyuanShape_MapsModelAndThumbnailRoles()
{
    var t = new FakeTransport();
    t.Gets.Enqueue(Resp(200, @"{""model_glb"":{""url"":""https://cdn.fal.run/m.glb""},""thumbnail"":{""url"":""https://cdn.fal.run/t.png""}}"));
    var p = new FalReconstructionProvider(t);
    var outcome = await p.FetchResultAsync(new ProviderJobHandle("req-1", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None);
    var ok = Assert.IsType<SuccessResultOutcome>(outcome);
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.Thumbnail);
}

[Fact]
public async Task Fetch_MeshyShape_MapsModelUrlsBucket()
{
    var t = new FakeTransport();
    t.Gets.Enqueue(Resp(200, @"{""model_urls"":{""glb"":""https://cdn.fal.run/m.glb"",""obj"":""https://cdn.fal.run/m.obj""}}"));
    var p = new FalReconstructionProvider(t);
    var ok = Assert.IsType<SuccessResultOutcome>(await p.FetchResultAsync(new ProviderJobHandle("r", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None));
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
}

[Fact]
public async Task Fetch_422_ReturnsFailedResult()
{
    var t = new FakeTransport(); t.Gets.Enqueue(Resp(422, @"{""detail"":""bad""}"));
    var p = new FalReconstructionProvider(t);
    Assert.IsType<FailedResultOutcome>(await p.FetchResultAsync(new ProviderJobHandle("r", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None));
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests.Fetch" --no-restore`
Expected: FAIL (NotImplementedException / no mapping).

- [ ] **Step 3: Implement `FetchResultAsync` + the fal→envelope mapper**

```csharp
public async Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.ResponseUrl is null)
        return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction job has no response URL.", false));
    var resp = await _transport.GetAsync(handle.ResponseUrl, ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode)
        return new FailedResultOutcome(FalErrorMapper.MapHttpFailure(resp));
    var root = (JsonNode.Parse(resp.Body) ?? new JsonObject()).AsObject();
    var artifacts = new List<ResultArtifact>();
    AddRemote(artifacts, ReconstructionFileRoles.ModelGlb, Url(root["model_glb"]) ?? Url(root["model_urls"]?["glb"]));
    AddRemote(artifacts, ReconstructionFileRoles.ModelObj, Url(root["model_obj"]) ?? Url(root["model_urls"]?["obj"]));
    AddRemote(artifacts, ReconstructionFileRoles.MaterialMtl, Url(root["material_mtl"]) ?? Url(root["model_urls"]?["mtl"]));
    AddRemote(artifacts, ReconstructionFileRoles.Texture, Url(root["texture"]) ?? Url(root["texture_urls"]?["texture"]));
    AddRemote(artifacts, ReconstructionFileRoles.Thumbnail, Url(root["thumbnail"]));
    if (artifacts.Count == 0)
        return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal result contained no recognizable asset URLs.", false));
    var meta = new Dictionary<string, JsonNode> { ["provider_result_json"] = root.DeepClone() };
    return new SuccessResultOutcome(new ProviderResultEnvelope(artifacts, meta));

    static void AddRemote(List<ResultArtifact> list, string role, Uri? url)
    { if (url is not null) list.Add(new ResultArtifact(role, new RemoteArtifactBody(url), null, new Dictionary<string, JsonNode>())); }
}
private static Uri? Url(JsonNode? n) // accepts {"url":"..."} or a bare string
{ var s = n is JsonObject o ? o["url"]?.GetValue<string>() : n?.GetValue<string>(); return Uri.TryCreate(s, UriKind.Absolute, out var u) ? u : null; }
```
The sanitized raw JSON is carried in `EnvelopeMetadata["provider_result_json"]` so the materializer can write the diagnostic sidecar without re-parsing fal field names.

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): parse fal result into shared ProviderResultEnvelope (multi-asset roles)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: W5 — Materializer consumes the envelope, downloads, enforces model-asset invariant

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (call `FetchResultAsync` → `MaterializeAsync`; no-model → job Error)
- Modify: `src/Rook/RookSubsystemRoot.cs` (inject the new downloader)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionPackageMaterializerTests.cs`

**Interfaces:**
- Produces:
```csharp
public sealed record ReconstructionMaterializeResult(bool Success, Artifact? Package, GenerationError? Error);

public async Task<ReconstructionMaterializeResult> MaterializeAsync(
    Guid jobId, IReadOnlyList<Guid> sourceArtifactIds, string provider, string modelId,
    ProviderResultEnvelope envelope, CancellationToken ct);
```
- Consumes: `IReconstructionRemoteAssetDownloader` (Task 4), `ProviderResultEnvelope` (Task 5), `ArtifactStore.Create`, `ReconstructionFileRoles`, the existing `BuildInitialImportManifest`.
- Removes: `IReconstructionFileDownloader`, `HttpReconstructionFileDownloader`, the old synchronous `Materialize(... JsonNode ...)`.

- [ ] **Step 1: Write failing tests — no-model envelope fails; multi-asset writes blobs**

```csharp
private static ResultArtifact Remote(string role, string url) =>
    new(role, new RemoteArtifactBody(new Uri(url)), null, new Dictionary<string, JsonNode>());

[Fact]
public async Task Materialize_NoModelAsset_FailsAndDoesNotCreatePackage()
{
    var store = TestArtifactStore.Empty(out _);
    var dl = new FakeDownloader(); // returns bytes for any url
    var m = new ReconstructionPackageMaterializer(store, dl);
    var env = new ProviderResultEnvelope(new[] { Remote(ReconstructionFileRoles.Thumbnail, "https://cdn.fal.run/t.png") }, new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });
    var r = await m.MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "model", env, CancellationToken.None);
    Assert.False(r.Success);
    Assert.Equal(GenerationErrorCode.ExecutionFailed, r.Error!.Code);
}

[Fact]
public async Task Materialize_MultiAsset_WritesRoleBlobsAndSidecar()
{
    var store = TestArtifactStore.Empty(out _);
    var dl = new FakeDownloader();
    var m = new ReconstructionPackageMaterializer(store, dl);
    var env = new ProviderResultEnvelope(new[] {
        Remote(ReconstructionFileRoles.ModelGlb, "https://cdn.fal.run/m.glb"),
        Remote(ReconstructionFileRoles.Thumbnail, "https://cdn.fal.run/t.png"),
    }, new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });
    var r = await m.MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "model", env, CancellationToken.None);
    Assert.True(r.Success);
    var roles = r.Package!.Blobs.Select(b => b.Role).ToList();
    Assert.Contains(ReconstructionFileRoles.ModelGlb, roles);
    Assert.Contains(ReconstructionFileRoles.ProviderResultJson, roles);
    Assert.Contains(ReconstructionFileRoles.ImportManifest, roles);
}
```
(`FakeDownloader` implements `IReconstructionRemoteAssetDownloader` returning `new ReconstructionDownloadResult(true, new byte[]{1}, "application/octet-stream", null)`.)

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionPackageMaterializerTests" --no-restore`
Expected: FAIL (compile / signature change).

- [ ] **Step 3: Implement envelope-consuming materializer + invariant**

```csharp
public async Task<ReconstructionMaterializeResult> MaterializeAsync(
    Guid jobId, IReadOnlyList<Guid> sourceArtifactIds, string provider, string modelId,
    ProviderResultEnvelope envelope, CancellationToken ct)
{
    var hasModel = envelope.Artifacts.Any(a => a.Role == ReconstructionFileRoles.ModelGlb || a.Role == ReconstructionFileRoles.ModelObj);
    if (!hasModel)
        return new(false, null, new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction package has no model asset (model_glb/model_obj).", Retryable: false));

    var blobs = new List<BlobInput>();
    foreach (var art in envelope.Artifacts)
    {
        if (art.Body is not RemoteArtifactBody remote) continue;
        var dl = await _downloader.DownloadAsync(remote.Url, art.Role, ct).ConfigureAwait(false);
        if (!dl.Success) return new(false, null, dl.Error);
        blobs.Add(new BlobInput(art.Role, dl.Bytes!, ExtensionFor(art.Role, dl.MimeType)));
    }
    var providerJson = envelope.EnvelopeMetadata.TryGetValue("provider_result_json", out var pj) ? pj : new JsonObject();
    blobs.Add(new BlobInput(ReconstructionFileRoles.ProviderResultJson, Encoding.UTF8.GetBytes(providerJson.ToJsonString()), "json"));
    blobs.Add(new BlobInput(ReconstructionFileRoles.ImportManifest, Encoding.UTF8.GetBytes(BuildInitialImportManifest().ToJsonString()), "json"));
    var metadata = new Dictionary<string, JsonNode?> { ["provider"] = JsonValue.Create(provider), ["model_id"] = JsonValue.Create(modelId), ["job_id"] = JsonValue.Create(jobId.ToString("D")), ["asset_roles"] = ToJsonArray(blobs.Select(b => b.Role)) };
    var artifact = _store.Create(ReconstructionArtifactKinds.Package, blobs, parentIds: sourceArtifactIds, metadata: metadata);
    return new(true, artifact, null);
}
```
Constructor now takes `IReconstructionRemoteAssetDownloader`. Delete `IReconstructionFileDownloader`/`HttpReconstructionFileDownloader`. Manager poll/run glue, on `ProviderCompleteStatusOutcome`:
```csharp
var fetch = await _provider.FetchResultAsync(complete.UpdatedHandle, ct).ConfigureAwait(false);
if (fetch is FailedResultOutcome fr) { AppendError(job, fr.Error); return; }
var success = (SuccessResultOutcome)fetch;
var mat = await _materializer.MaterializeAsync(job.JobId, new[] { job.SourceArtifactId }, job.Provider, job.ModelId, success.Envelope, ct).ConfigureAwait(false);
if (!mat.Success) { AppendError(job, mat.Error!); return; }
_ledger.Append(ReconstructionJobLedgerRecord.Complete(job.JobId, mat.Package!.Id));
```
`AppendError` appends `State=Error, Stage=Error, Error=ReconstructionErrorMapping.ToFailure(err)`.

`RookSubsystemRoot.CreateReconstruction`: `new ReconstructionPackageMaterializer(SharedArtifactStore, new ReconstructionRemoteAssetDownloader(new HttpClient(), role => role.StartsWith("model_") ? 100_000_000L : 25_000_000L))`.

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): materializer consumes envelope, downloads disciplined, enforces model-asset invariant

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: W6 — Background execution, single-flight, dispose

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces: `ReconstructionJobManager : IDisposable`; per-job background run; preserves the existing public method signatures (`SubmitAsync`, `Status`, `StatusAsync`, `CancelAsync`, `Result`, `List`).
- Consumes: the shared outcomes + materializer from Tasks 2/5/6. Mirrors `VideoJobManager` (lines 39–112, 754–996, 780–785, 1409–1421).

**Single-flight invariant:** exactly one terminal transition and one materialization per job, regardless of racing pollers.

- [ ] **Step 1: Write failing tests — background drive, single-flight, dispose**

```csharp
[Fact]
public async Task Submit_BackgroundLoop_DrivesJobToComplete()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "IN_PROGRESS", "COMPLETED" }, resultEnvelope: bundle.GlbEnvelope());
    using var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(5));
    var submit = await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    await bundle.WaitUntil(() => manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Complete, timeoutMs: 2000);
    Assert.Equal(ReconstructionJobState.Complete, manager.Status(submit.Job!.JobId).Job!.State);
}

[Fact]
public async Task ConcurrentStatusAndBackgroundPoll_ProduceExactlyOneMaterialization()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var counting = bundle.CountingMaterializer(); // increments on each MaterializeAsync
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "COMPLETED" }, resultEnvelope: bundle.GlbEnvelope());
    using var manager = bundle.BuildManager(provider: provider, materializer: counting, pollInterval: TimeSpan.FromMilliseconds(1));
    var submit = await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    var jobId = submit.Job!.JobId;
    await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => manager.StatusAsync(jobId, CancellationToken.None)));
    await bundle.WaitUntil(() => manager.Status(jobId).Job!.State == ReconstructionJobState.Complete, 2000);
    Assert.Equal(1, counting.Count);
}

[Fact]
public async Task Dispose_MidPoll_CancelsLoopAndStopsTransitions()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "IN_PROGRESS", "IN_PROGRESS", "IN_PROGRESS" }, resultEnvelope: bundle.GlbEnvelope());
    var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(20));
    var submit = await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    manager.Dispose();
    var stateAfter = manager.Status(submit.Job!.JobId).Job!.State;
    Assert.NotEqual(ReconstructionJobState.Complete, stateAfter); // no completion after shutdown
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests" --no-restore`
Expected: FAIL (no background loop; not IDisposable).

- [ ] **Step 3: Add background lifecycle (mirror VideoJobManager)**

Add fields + ctor params (default poll interval 10s, max concurrency 2):
```csharp
public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
public const int DefaultMaxConcurrentJobs = 2;
private readonly CancellationTokenSource _shutdownCts = new();
private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();
private readonly SemaphoreSlim _concurrency;
private readonly TimeSpan _pollInterval;

private sealed class RunningJob
{
    public ReconstructionJobLedgerRecord Latest;
    public readonly CancellationTokenSource Cts;
    public RunningJob(ReconstructionJobLedgerRecord initial, CancellationTokenSource cts) { Latest = initial; Cts = cts; }
}
```
On submit (after queued record persisted + handle stored), kick the loop:
```csharp
var linked = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
var running = new RunningJob(record, linked);
_runningJobs[record.JobId] = running;
_ = Task.Run(() => RunJobAsync(running), CancellationToken.None);
```
`RunJobAsync` mirrors `VideoJobManager.RunJobAsync` (lines 789–996): `await _concurrency.WaitAsync(ct)`, poll loop with `await Task.Delay(_pollInterval, ct)`, switch on `ProviderStatusOutcome`, on complete → `FetchResultAsync` → `MaterializeAsync` → append `Complete`; `catch (OperationCanceledException) when (ct.IsCancellationRequested)` leaves the job non-terminal; `finally { _runningJobs.TryRemove(jobId, out _); running.Cts.Dispose(); _concurrency.Release(); }`.

**Single-flight:** keep `StatusAsync`/`PollActiveJobAsync` but make them acquire the existing per-job `_pollLocks[jobId]` semaphore AND re-read the ledger after acquiring; if the freshest record is already terminal, return without fetch/materialize. The background `RunJobAsync` terminal transition + materialization must also take that same per-job lock and re-read before appending `Complete`/`Error`, so a racing `StatusAsync` cannot double-materialize.

Implement `IDisposable`:
```csharp
public void Dispose()
{
    try { _shutdownCts.Cancel(); } catch { }
    _shutdownCts.Dispose();
    _concurrency.Dispose();
}
```

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): background job execution with single-flight and shutdown disposal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: W6 — Startup reconcile + subsystem wiring

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`ReconcileInterruptedJobs`)
- Modify: `src/Rook/RookSubsystemRoot.cs` (call reconcile on construct; dispose manager on shutdown)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces: `public void ReconcileInterruptedJobs()` — mirrors `VideoJobManager.ReconcileInterruptedJobs` (lines 754–776). No auto remote-resume.

- [ ] **Step 1: Write failing test — non-terminal jobs become Interrupted, provider ids preserved**

```csharp
[Fact]
public void Reconcile_NonTerminalJobs_BecomeInterrupted_PreservingProviderJobId()
{
    var bundle = ReconstructionTestBundle.Empty();
    bundle.Ledger.Append(bundle.RunningRecord(out var jobId, providerJobId: "req-9", statusUrl: "https://queue.fal.run/s"));
    using var manager = bundle.BuildManager();
    manager.ReconcileInterruptedJobs();
    var rec = manager.Status(jobId).Job!;
    Assert.Equal(ReconstructionJobState.Interrupted, rec.State);
    Assert.Equal("req-9", rec.ProviderJobId);
    Assert.Equal("https://queue.fal.run/s", rec.ProviderStatusUrl);
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconcile_NonTerminalJobs" --no-restore`
Expected: FAIL (method missing).

- [ ] **Step 3: Implement reconcile + wire into subsystem**

```csharp
public void ReconcileInterruptedJobs()
{
    var list = _ledger.List(int.MaxValue);
    foreach (var record in list.Jobs)
    {
        if (IsTerminal(record.State)) continue;
        _ledger.Append(record with
        {
            State = ReconstructionJobState.Interrupted,
            Stage = ReconstructionJobStage.Error,
            UpdatedAt = Now(),
            Error = new ReconstructionFailure("interrupted", "Job interrupted by plugin reload.", Retryable: true, Field: null, Details: new Dictionary<string, object?>()),
        });
    }
}
private static bool IsTerminal(ReconstructionJobState s) =>
    s is ReconstructionJobState.Complete or ReconstructionJobState.Error or ReconstructionJobState.Cancelled or ReconstructionJobState.Interrupted;
```
Provider job id/URLs are preserved automatically because `record with { ... }` copies the unchanged fields.

In `RookSubsystemRoot`: after building the manager in `CreateReconstruction`, call `manager.ReconcileInterruptedJobs();` before returning the handler. Ensure the manager is disposed in the subsystem's existing dispose path (where `_disposed` is set) — add `(_reconstruction.IsValueCreated ? _reconstruction.Value : null)?.ManagerForDispose?.Dispose();` or expose the manager via the handler for disposal. (Follow the existing video-subsystem dispose pattern in this file.)

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): startup reconcile of interrupted jobs + dispose wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: W7 boundary — `GenerationError → ReconstructionFailure` mapping verified end-to-end

**Files:**
- Verify/extend: `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs` (created in Task 2)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs` (+ handler test if a handler path surfaces it)

**Interfaces:**
- Consumes: `ReconstructionErrorMapping.ToFailure` (Task 2), `ReconstructionFailure` (public DTO, unchanged).

- [ ] **Step 1: Write failing test — a fal failure surfaces as a typed `ReconstructionFailure`, not opaque**

```csharp
[Fact]
public async Task ProviderQuotaFailure_SurfacesRetryableReconstructionFailure()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "FAILED_429" }, resultEnvelope: null); // 429 status
    using var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(2));
    var submit = await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    await bundle.WaitUntil(() => manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Error, 2000);
    var rec = manager.Status(submit.Job!.JobId).Job!;
    Assert.Equal("quota_exceeded", rec.Error!.Code);
    Assert.True(rec.Error!.Retryable);
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ProviderQuotaFailure" --no-restore`
Expected: FAIL (mapping/scripted provider not producing typed code) — implement the scripted provider's 429 path + confirm `AppendError` uses `ReconstructionErrorMapping.ToFailure`.

- [ ] **Step 3: Confirm the mapping is applied everywhere the manager records an error**

Audit `ReconstructionJobManager` for every `State = ReconstructionJobState.Error` append: each must set `Error = ReconstructionErrorMapping.ToFailure(generationError)` (never a hand-built opaque `poll_failed`). Confirm `ReconstructionErrorMapping.MapCode` covers all `GenerationErrorCode` members (it does — see Task 2). No change to `ReconstructionOpHandler.StatusFor` is required because the mapped codes (`quota_exceeded`, `provider_unavailable`, `invalid_request`, …) already route through its default/400/404 logic; if a new code needs a non-500 status, extend `StatusFor`'s allow-list.

- [ ] **Step 4: Run, verify pass + FULL reconstruction + MCP suite green**

Run:
```bash
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore
pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```
Expected: PASS (all reconstruction C# tests; 17 MCP tests).

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "test(reconstruction): pin GenerationError -> ReconstructionFailure boundary mapping

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Full reconstruction suite + MCP parity green:
  `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore` and `pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
- [ ] `grep -rn "InvalidOperationException" src/Rook/Services/Reconstruction/` returns no fal/HTTP-boundary throws.
- [ ] `grep -rn "GetAwaiter().GetResult()\|File.ReadAllBytes" src/Rook/Services/Reconstruction/` returns nothing.
- [ ] `grep -rn "FalErrorMapper\|FalLifecycleMapper" src/Rook/Services/Reconstruction/` shows the mappers are now used.
- [ ] No file under `src/Rook/Services/Vision/` was modified (`git diff --name-only origin/main... -- src/Rook/Services/Vision/` empty for this branch's new commits).
- [ ] Native build verified separately (out of unit scope).

## Notes / known follow-ups (out of scope here)

- Shared `MediaDownloader` extraction across image/video/reconstruction (rule-of-three follow-up; see spec Substrate Trajectory).
- `IGenerationProvider<TRequest,TCapability>` adoption (option C; deferred).
- Reconciling main's divergent uncommitted `ReplaceJsonBlob` copy — a separate, user-directed action; this pass does not touch main.
