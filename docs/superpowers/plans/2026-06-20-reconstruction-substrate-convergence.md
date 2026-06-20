# Reconstruction Substrate Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge the Reconstruction 2D-to-3D subsystem's fal/media/job primitives onto RookVision's proven generation substrate, fixing seven confirmed robustness gaps without rewriting UI/native/MCP or touching green Vision code.

**Architecture:** `FalReconstructionProvider` consumes the shared `FalApiClient` + `FalLifecycleMapper` + `FalErrorMapper` and returns the shared `Provider*Outcome` / `ProviderResultEnvelope` types (keeping a reconstruction-specific `IReconstructionProvider` interface, not the generic). `ReconstructionJobManager` adopts the Vision background-execution lifecycle (per-job `Task.Run`, shutdown CTS, single-flight, startup reconcile). `ReconstructionPackageMaterializer` consumes the shared envelope, downloads via a new disciplined `ReconstructionRemoteAssetDownloader`, and enforces a "≥1 model asset" package invariant. `ReconstructionFailure` stays the public HTTP DTO; `GenerationError` is mapped into it at the boundary.

**Green-slice ordering (revised per review):** the provider result type, the materializer input, and the manager's complete-path are one mutually-dependent refactor — splitting them mid-way commits a red slice (existing completion tests exercise the full path). So the spec's `W1+W7 → W2 → W3+W4+W5` is operationalized as: **W0 → W4 (downloader, standalone) → W2 (source, standalone) → CORE = W1+W3+W5+W7-provider (one atomic green slice) → W6 background+single-flight+dispose → W6 reconcile+wiring → W7 boundary test.** Every task ends green.

**Tech Stack:** C# (.NET, RhinoCommon companion plugin `src/Rook/`), xUnit (`src/Rook.Tests/`), `System.Text.Json.Nodes`. fal.ai queue API via shared `FalApiClient`.

**Source spec:** [`docs/superpowers/specs/2026-06-20-reconstruction-substrate-convergence-design.md`](../specs/2026-06-20-reconstruction-substrate-convergence-design.md)

## Global Constraints

- Work ENTIRELY in the worktree `C:/Users/aryan/source/repos/Rook/.worktrees/reconstruction-2d-to-3d` on branch `codex/reconstruction-2d-to-3d`. Never edit the main checkout. Commands are repo-relative (CWD = the worktree root).
- Do NOT modify any RookVision file under `src/Rook/Services/Vision/` (Fal, Generation, Image, Video). They are the shared substrate; consume them, do not change them.
- Do NOT modify native (`src/RookNative/`), MCP (`mcp_server/`), the import route, the `reconstruction_package`/`import_manifest` schema, or the ledger state/stage enum vocabulary.
- No fal/HTTP boundary may throw a bare `InvalidOperationException`. Every fal failure becomes a typed `GenerationError`; every download failure a typed materialization failure.
- Keep `ReconstructionFailure` as the public HTTP response DTO. Map `GenerationError → ReconstructionFailure` only at the handler/manager boundary.
- No sync-over-async (`.GetAwaiter().GetResult()`, `.Result`, `ContinueWith`-as-await) on any new code path. Use `async`/`await`.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. Frequent commits.
- Test run note: building `src/Rook.Tests` deploys `Rook.rhp` into `%AppData%` (it touches the local Rhino install). This is expected; do not be alarmed by the deploy step.
- Test command shape: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~<Name>" --no-restore`
- Baseline that must stay green: existing 55 reconstruction C# tests + 17 MCP tests.
- End every commit message with the Co-Authored-By trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**Modified (reconstruction-owned):**
- `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` — provider rewritten onto shared mappers/outcomes; throwing `FalReconstructionQueueClient` and duplicate `ReconstructionProviderSubmitResult`/`StatusResult`/`LifecycleState` types removed; source publisher takes bytes+mime.
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — consumes shared outcomes; gains background execution, single-flight, dispose, reconcile.
- `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs` — consumes `ProviderResultEnvelope`; uses the new downloader; enforces the model-asset invariant.
- `src/Rook/Handlers/ReconstructionOpHandler.cs` — `GenerationError → ReconstructionFailure` mapping at the boundary (only if `StatusFor` needs a new code).
- `src/Rook/RookSubsystemRoot.cs` — wiring: new downloader, transport, dispose, reconcile-on-start.

**Created (reconstruction-owned):**
- `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs` — disciplined async downloader (W4).
- `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs` — `GenerationError → ReconstructionFailure` helper.

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
public sealed class ProviderResultEnvelope { public ProviderResultEnvelope(IReadOnlyList<ResultArtifact> Artifacts, IReadOnlyDictionary<string,JsonNode> EnvelopeMetadata); public IReadOnlyList<ResultArtifact> Artifacts {get;} public IReadOnlyDictionary<string,JsonNode> EnvelopeMetadata {get;} }
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

**Context / decision:** The worktree (committed) and main (uncommitted) `ReplaceJsonBlob` implementations have diverged. Worktree defines `ReplaceJsonBlobResultCode`/`ReplaceJsonBlobResult` in `Artifact.cs` beside `AppendBlobResult` (this already satisfies the reviewer's P4 tidy). Main defines them inline in `ArtifactStore.cs` and adds a test seam `ReplaceJsonBlobFileReplaceOverrideForTests`. Neither is a strict superset. **Canonical for this branch = the worktree's committed version.** Reconciling main's divergent copy is the user's separate, explicit action — do not revert or edit main, and do not port main's test seam unless a test in this task needs it.

- [ ] **Step 1: Verify the worktree version is self-consistent and the P4 tidy is already done**

Run: `rg -n "ReplaceJsonBlobResultCode|ReplaceJsonBlobResult" src/Rook/Artifacts/Artifact.cs`
Expected: both types are declared in `Artifact.cs` (around lines 115/127), beside `AppendBlobResult`. No action needed for P4.

- [ ] **Step 2: Confirm the existing ReplaceJsonBlob tests pass (baseline lock)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ArtifactStoreTests.ReplaceJsonBlob" --no-restore`
Expected: PASS (5 tests).

- [ ] **Step 3: No commit unless Step 1 shows the tidy is missing**

If Step 1 shows the result types are NOT in `Artifact.cs`, move them there beside `AppendBlobResult` and commit:
```bash
git add src/Rook/Artifacts/Artifact.cs src/Rook/Artifacts/ArtifactStore.cs
git commit -m "refactor(artifacts): keep ReplaceJsonBlob result types beside AppendBlobResult

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Otherwise, no change. (Main's uncommitted copy is reconciled separately by the user — not here.)

---

## Task 2: W4 — `ReconstructionRemoteAssetDownloader` (disciplined async download)

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
- Consumes: nothing from prior tasks (standalone). Injected `HttpMessageHandler`/`HttpClient` for tests.

**Behavior:** absolute-https only; `HttpCompletionOption.ResponseHeadersRead`; role-aware byte cap (models larger than thumbnails/textures); enforce cap from `Content-Length` header AND while streaming; **retry transient transport only** (`HttpRequestException`, HTTP-timeout `TaskCanceledException`) AND transient status (5xx/408/429) up to 3 attempts; **user cancellation rethrows and never retries; programmer/validation errors propagate or fail without retry**; typed `GenerationError` on failure.

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
    var big = new byte[26_000_000]; var h = new StubHandler(); h.Responses.Enqueue(() => Ok(big)); // texture role → 25MB cap
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

- [ ] **Step 3: Implement the downloader (transient-only retry)**

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
                    if (IsTransientStatus((int)resp.StatusCode) && attempt < MaxAttempts) continue;
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
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw; // user cancellation: never retry, never swallow
            }
            catch (Exception ex) when (IsTransientTransport(ex) && attempt < MaxAttempts)
            {
                // transient transport error or HTTP client timeout: retry
            }
            catch (Exception ex) when (IsTransientTransport(ex))
            {
                return Fail(GenerationErrorCode.DependencyUnavailable, $"Asset download error: {ex.Message}");
            }
            // Any other exception type (programmer/validation error) is intentionally NOT caught here → propagates.
        }
    }

    // TaskCanceledException here is the HttpClient timeout case (user cancellation is handled by the filtered
    // OperationCanceledException catch above, which rethrows before reaching this).
    private static bool IsTransientTransport(Exception ex) => ex is HttpRequestException || ex is TaskCanceledException;
    private static bool IsTransientStatus(int s) => s >= 500 || s == 408 || s == 429;

    private static async Task<byte[]?> ReadCappedAsync(Stream s, long cap, CancellationToken ct)
    {
        using var ms = new MemoryStream();
        var buf = new byte[81920]; int n; long total = 0;
        while ((n = await s.ReadAsync(buf.AsMemory(0, buf.Length), ct).ConfigureAwait(false)) > 0)
        { total += n; if (total > cap) return null; ms.Write(buf, 0, n); }
        return ms.ToArray();
    }

    private static ReconstructionDownloadResult Fail(GenerationErrorCode c, string m) =>
        new(false, null, null, new GenerationError(c, m, Retryable: c is GenerationErrorCode.DependencyUnavailable));
}
```

- [ ] **Step 4: Run, verify all 7 pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionRemoteAssetDownloaderTests" --no-restore`
Expected: PASS (7).

- [ ] **Step 5: Commit**
```bash
git add src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs src/Rook.Tests/Services/Reconstruction/ReconstructionRemoteAssetDownloaderTests.cs
git commit -m "feat(reconstruction): add disciplined async remote asset downloader (cap/transient-retry/streaming)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: W2 — Resolve source bytes/MIME before upload; publisher stops reading files

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`FalReconstructionSourceImagePublisher`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (resolve bytes/mime, call publisher)
- Modify: `src/Rook/RookSubsystemRoot.cs` (publisher construction)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces:
```csharp
public interface IReconstructionSourceImagePublisher
{
    Task<Uri> PublishAsync(byte[] bytes, string mimeType, string fileName, CancellationToken ct);
}
```
- Consumes: `FalApiClient.UploadFileToCdnAsync`, `FalUploadPlatformHeaders.ForSourceUpload`, `ArtifactStore` blob read (manager side).

This task only touches the submit/source path; the complete/materialize path is unchanged, so the existing completion tests stay green.

- [ ] **Step 1: Write the failing test — publisher receives resolved bytes/mime, never a path**

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
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var pub = new CapturingPublisher();
    using var manager = bundle.BuildManager(publisher: pub, provider: bundle.QueuedThenInflightProvider());
    await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    Assert.NotNull(pub.Bytes);
    Assert.False(string.IsNullOrEmpty(pub.Mime));
}
```
(Extend the existing `ReconstructionTestBundle` helper with `WithSourceImage`/`BuildManager(publisher:, provider:)`/`QueuedThenInflightProvider` if not already present.)

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Publisher_ReceivesResolvedBytesAndMime" --no-restore`
Expected: FAIL (publisher still has the `(Artifact, role, absolutePath)` signature).

- [ ] **Step 3: Change the publisher to byte-based (async/await); resolve bytes in the manager**

Publisher — plain `async`/`await`, no `ContinueWith`:
```csharp
public sealed class FalReconstructionSourceImagePublisher : IReconstructionSourceImagePublisher
{
    public const int SourceImageExpirationSeconds = 3600;
    private readonly FalApiClient _client;
    private readonly Func<string?> _apiKey;
    public FalReconstructionSourceImagePublisher(FalApiClient client, Func<string?> apiKey) { _client = client; _apiKey = apiKey; }

    public async Task<Uri> PublishAsync(byte[] bytes, string mimeType, string fileName, CancellationToken ct)
    {
        var url = await _client.UploadFileToCdnAsync(
            _apiKey()!, fileName, bytes, mimeType,
            FalUploadPlatformHeaders.ForSourceUpload(SourceImageExpirationSeconds), ct).ConfigureAwait(false);
        return new Uri(url);
    }
}
```
Manager submit path: after source validation yields the artifact + role, read bytes + mime from the store and pass them to the publisher (no path reaches the publisher):
```csharp
var (bytes, mime, fileName) = ReadSourceBlob(_store, artifact, validation.Role); // store.OpenBlob → bytes; mime from blob metadata/extension map
var inputUrl = await _sourcePublisher.PublishAsync(bytes, mime, fileName, ct).ConfigureAwait(false);
```
Delete the `File.ReadAllBytes(absolutePath)` path entirely. `ReadSourceBlob` lives in the manager (it owns the store), keeping the provider/publisher storage-agnostic. `RookSubsystemRoot.CreateReconstruction` keeps constructing `new FalReconstructionSourceImagePublisher(falClient, () => SharedGenerationSecretStore.GetSecret(GenerationSecretKeys.FalApiKey))`.

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "refactor(reconstruction): resolve source bytes/mime in manager; publisher is storage-agnostic

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: CORE (W1+W3+W5+W7-provider) — provider onto shared mappers/outcomes + envelope materializer + manager glue, in one atomic green slice

This is the mutually-dependent core: the provider's result type, the materializer's input, and the manager's complete-path must change together or a slice commits red (existing completion tests at `ReconstructionJobManagerTests.cs:92`, `:130`, `:199` exercise the full submit→complete→materialize path). Do it as one task; commit once at the end with everything green.

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (poll/complete glue; lazy model retained — background is Task 5)
- Create: `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs`
- Modify: `src/Rook/RookSubsystemRoot.cs` (transport + downloader wiring)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`, `ReconstructionPackageMaterializerTests.cs`, `ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces — the new provider contract + materializer signature (consumed by Tasks 5–7):
```csharp
namespace Rook.Services.Reconstruction.Fal;
public sealed record ReconstructionProviderSubmitRequest(string ModelId, Uri InputImageUrl, JsonObject Options);
public interface IFalTransport
{
    Task<FalHttpResponse> PostJsonAsync(Uri url, string bodyJson, CancellationToken ct);
    Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct);
    Task<FalHttpResponse> SendAsync(HttpMethod method, Uri url, string? bodyJson, CancellationToken ct);
}
public interface IReconstructionProvider
{
    Task<ProviderSubmitOutcome> SubmitAsync(ReconstructionProviderSubmitRequest request, CancellationToken ct);
    Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct);
    Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct);
    Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct);
}
```
```csharp
namespace Rook.Services.Reconstruction;
public sealed record ReconstructionMaterializeResult(bool Success, Artifact? Package, GenerationError? Error);
// ReconstructionPackageMaterializer:
public async Task<ReconstructionMaterializeResult> MaterializeAsync(
    Guid jobId, IReadOnlyList<Guid> sourceArtifactIds, string provider, string modelId,
    ProviderResultEnvelope envelope, CancellationToken ct);
public static class ReconstructionErrorMapping { public static ReconstructionFailure ToFailure(GenerationError e); }
```
- Consumes — shared mappers/outcomes/envelope (File Structure), `IReconstructionRemoteAssetDownloader` (Task 2).
- Removes — `IFalReconstructionQueueClient`, `FalReconstructionQueueClient`, `ReconstructionProviderSubmitResult`, `ReconstructionProviderStatusResult`, `ReconstructionProviderLifecycleState`, `IReconstructionFileDownloader`, `HttpReconstructionFileDownloader`, the old `Materialize(... JsonNode ...)`.

- [ ] **Step 1: Write failing provider tests (submit/status/error + fetch→envelope)**

```csharp
private static FalHttpResponse Resp(int s, string b) => new(s, b, new Dictionary<string, IReadOnlyList<string>>());
private sealed class FakeTransport : IFalTransport
{
    public Queue<FalHttpResponse> Posts = new(); public Queue<FalHttpResponse> Gets = new(); public Queue<FalHttpResponse> Sends = new();
    public Task<FalHttpResponse> PostJsonAsync(Uri u, string b, CancellationToken ct) => Task.FromResult(Posts.Dequeue());
    public Task<FalHttpResponse> GetAsync(Uri u, CancellationToken ct) => Task.FromResult(Gets.Dequeue());
    public Task<FalHttpResponse> SendAsync(HttpMethod m, Uri u, string? b, CancellationToken ct) => Task.FromResult(Sends.Dequeue());
}

[Fact] public async Task Submit_Queued_ReturnsHandleWithRequestId() {
    var t = new FakeTransport(); t.Posts.Enqueue(Resp(200, @"{""request_id"":""req-1"",""status_url"":""https://queue.fal.run/s"",""response_url"":""https://queue.fal.run/r"",""cancel_url"":""https://queue.fal.run/c""}"));
    var outcome = await new FalReconstructionProvider(t).SubmitAsync(new("m", new Uri("https://cdn.fal.run/i.png"), new JsonObject()), CancellationToken.None);
    Assert.Equal("req-1", Assert.IsType<QueuedSubmitOutcome>(outcome).Handle.ProviderJobId); }

[Fact] public async Task Submit_401_ReturnsFailedSubmitTyped() {
    var t = new FakeTransport(); t.Posts.Enqueue(Resp(401, @"{""detail"":""bad key""}"));
    var outcome = await new FalReconstructionProvider(t).SubmitAsync(new("m", new Uri("https://cdn.fal.run/i.png"), new JsonObject()), CancellationToken.None);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, Assert.IsType<FailedSubmitOutcome>(outcome).Error.Code); }

[Fact] public async Task Status_InProgress_MapsToInFlight() {
    var t = new FakeTransport(); t.Gets.Enqueue(Resp(200, @"{""status"":""IN_PROGRESS""}"));
    Assert.IsType<InFlightStatusOutcome>(await new FalReconstructionProvider(t).GetStatusAsync(new ProviderJobHandle("req-1", statusUrl: new Uri("https://queue.fal.run/s")), CancellationToken.None)); }

[Fact] public async Task Status_429_ReturnsFailedRetryable() {
    var t = new FakeTransport(); t.Gets.Enqueue(new FalHttpResponse(429, "{}", new Dictionary<string, IReadOnlyList<string>> { ["x-fal-needs-retry"] = new[] { "true" } }));
    var f = Assert.IsType<FailedStatusOutcome>(await new FalReconstructionProvider(t).GetStatusAsync(new ProviderJobHandle("r", statusUrl: new Uri("https://queue.fal.run/s")), CancellationToken.None));
    Assert.Equal(GenerationErrorCode.QuotaExceeded, f.Error.Code); Assert.True(f.Error.Retryable); }

[Fact] public async Task Fetch_HunyuanShape_MapsModelAndThumbnail() {
    var t = new FakeTransport(); t.Gets.Enqueue(Resp(200, @"{""model_glb"":{""url"":""https://cdn.fal.run/m.glb""},""thumbnail"":{""url"":""https://cdn.fal.run/t.png""}}"));
    var ok = Assert.IsType<SuccessResultOutcome>(await new FalReconstructionProvider(t).FetchResultAsync(new ProviderJobHandle("r", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None));
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.Thumbnail); }

[Fact] public async Task Fetch_MeshyShape_MapsModelUrlsBucket() {
    var t = new FakeTransport(); t.Gets.Enqueue(Resp(200, @"{""model_urls"":{""glb"":""https://cdn.fal.run/m.glb"",""obj"":""https://cdn.fal.run/m.obj""}}"));
    var ok = Assert.IsType<SuccessResultOutcome>(await new FalReconstructionProvider(t).FetchResultAsync(new ProviderJobHandle("r", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None));
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
    Assert.Contains(ok.Envelope.Artifacts, a => a.Role == ReconstructionFileRoles.ModelObj); }

[Fact] public async Task Fetch_422_ReturnsFailedResult() {
    var t = new FakeTransport(); t.Gets.Enqueue(Resp(422, @"{""detail"":""bad""}"));
    Assert.IsType<FailedResultOutcome>(await new FalReconstructionProvider(t).FetchResultAsync(new ProviderJobHandle("r", responseUrl: new Uri("https://queue.fal.run/r")), CancellationToken.None)); }
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests" --no-restore`
Expected: FAIL (compile — provider still returns old types).

- [ ] **Step 3: Rewrite the provider fully (submit/status/cancel/fetch→envelope)**

Create `ReconstructionErrorMapping.cs`:
```csharp
public static class ReconstructionErrorMapping
{
    public static ReconstructionFailure ToFailure(GenerationError e) => new(
        Code: MapCode(e.Code), Message: e.Message, Retryable: e.Retryable, Field: e.Field,
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
Provider (`_transport` is `IFalTransport`). Submit:
```csharp
public async Task<ProviderSubmitOutcome> SubmitAsync(ReconstructionProviderSubmitRequest request, CancellationToken ct)
{
    var payload = BuildSubmitPayload(request);                 // existing payload builder, kept
    var resp = await _transport.PostJsonAsync(QueueSubmitUri(request.ModelId), payload.ToJsonString(), ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode) return new FailedSubmitOutcome(FalErrorMapper.MapHttpFailure(resp));
    var body = JsonNode.Parse(resp.Body) ?? new JsonObject();
    return new QueuedSubmitOutcome(FalLifecycleMapper.ParseSubmitHandle(body, cancelHttpMethod: "PUT"));
}
```
Status:
```csharp
public async Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.StatusUrl is null) return new FailedStatusOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction job has no status URL.", false));
    var resp = await _transport.GetAsync(handle.StatusUrl, ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode) return new FailedStatusOutcome(FalErrorMapper.MapHttpFailure(resp));
    return FalLifecycleMapper.MapStatus(handle, JsonNode.Parse(resp.Body) ?? new JsonObject());
}
```
FetchResult → envelope (fal-shape knowledge lives ONLY here):
```csharp
public async Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.ResponseUrl is null) return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction job has no response URL.", false));
    var resp = await _transport.GetAsync(handle.ResponseUrl, ct).ConfigureAwait(false);
    if (!resp.IsSuccessStatusCode) return new FailedResultOutcome(FalErrorMapper.MapHttpFailure(resp));
    var root = (JsonNode.Parse(resp.Body) ?? new JsonObject()).AsObject();
    var artifacts = new List<ResultArtifact>();
    AddRemote(artifacts, ReconstructionFileRoles.ModelGlb, Url(root["model_glb"]) ?? Url(root["model_urls"]?["glb"]));
    AddRemote(artifacts, ReconstructionFileRoles.ModelObj, Url(root["model_obj"]) ?? Url(root["model_urls"]?["obj"]));
    AddRemote(artifacts, ReconstructionFileRoles.MaterialMtl, Url(root["material_mtl"]) ?? Url(root["model_urls"]?["mtl"]));
    AddRemote(artifacts, ReconstructionFileRoles.Texture, Url(root["texture"]) ?? Url(root["texture_urls"]?["texture"]));
    AddRemote(artifacts, ReconstructionFileRoles.Thumbnail, Url(root["thumbnail"]));
    if (artifacts.Count == 0) return new FailedResultOutcome(new GenerationError(GenerationErrorCode.ExecutionFailed, "fal result contained no recognizable asset URLs.", false));
    var meta = new Dictionary<string, JsonNode> { ["provider_result_json"] = root.DeepClone() };
    return new SuccessResultOutcome(new ProviderResultEnvelope(artifacts, meta));

    static void AddRemote(List<ResultArtifact> list, string role, Uri? url)
    { if (url is not null) list.Add(new ResultArtifact(role, new RemoteArtifactBody(url), null, new Dictionary<string, JsonNode>())); }
}
private static Uri? Url(JsonNode? n)
{ var s = n is JsonObject o ? o["url"]?.GetValue<string>() : n?.GetValue<string>(); return Uri.TryCreate(s, UriKind.Absolute, out var u) ? u : null; }
```
Cancel:
```csharp
public async Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct)
{
    if (handle.CancelUrl is null) return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
    var resp = await _transport.SendAsync(new HttpMethod(handle.CancelHttpMethod ?? "PUT"), handle.CancelUrl, null, ct).ConfigureAwait(false);
    if (resp.IsSuccessStatusCode) return new CanceledOutcome();
    if (resp.StatusCode == 400) return new AlreadyTerminalOutcome(GenerationLifecycleState.Completed);
    return new FailedCancelOutcome(FalErrorMapper.MapHttpFailure(resp));
}
```
Delete `IFalReconstructionQueueClient`, `FalReconstructionQueueClient`, and the three duplicate `Reconstruction*Result`/`*LifecycleState` types. Add the prod adapter:
```csharp
public sealed class FalApiTransport : IFalTransport
{
    private readonly FalApiClient _client; private readonly Func<string?> _apiKey;
    public FalApiTransport(FalApiClient client, Func<string?> apiKey) { _client = client; _apiKey = apiKey; }
    private string Key() => _apiKey()!; // manager guarantees presence before submit (see Step 5)
    public Task<FalHttpResponse> PostJsonAsync(Uri url, string body, CancellationToken ct) => _client.PostJsonAsync(Key(), url, body, ct);
    public Task<FalHttpResponse> GetAsync(Uri url, CancellationToken ct) => _client.GetAsync(Key(), url, ct);
    public Task<FalHttpResponse> SendAsync(HttpMethod m, Uri url, string? body, CancellationToken ct) => _client.SendAsync(Key(), m, url, body, ct);
}
```

- [ ] **Step 4: Write failing materializer tests (no-model + multi-asset)**

```csharp
private sealed class FakeDownloader : IReconstructionRemoteAssetDownloader
{ public Task<ReconstructionDownloadResult> DownloadAsync(Uri u, string role, CancellationToken ct) => Task.FromResult(new ReconstructionDownloadResult(true, new byte[]{1}, "application/octet-stream", null)); }
private static ResultArtifact Remote(string role, string url) => new(role, new RemoteArtifactBody(new Uri(url)), null, new Dictionary<string, JsonNode>());

[Fact] public async Task Materialize_NoModelAsset_FailsAndCreatesNoPackage() {
    var store = TestArtifactStore.Empty(out _);
    var env = new ProviderResultEnvelope(new[] { Remote(ReconstructionFileRoles.Thumbnail, "https://cdn.fal.run/t.png") }, new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });
    var r = await new ReconstructionPackageMaterializer(store, new FakeDownloader()).MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "m", env, CancellationToken.None);
    Assert.False(r.Success); Assert.Equal(GenerationErrorCode.ExecutionFailed, r.Error!.Code); }

[Fact] public async Task Materialize_MultiAsset_WritesRoleBlobsAndSidecar() {
    var store = TestArtifactStore.Empty(out _);
    var env = new ProviderResultEnvelope(new[] { Remote(ReconstructionFileRoles.ModelGlb, "https://cdn.fal.run/m.glb"), Remote(ReconstructionFileRoles.Thumbnail, "https://cdn.fal.run/t.png") }, new Dictionary<string, JsonNode> { ["provider_result_json"] = new JsonObject() });
    var r = await new ReconstructionPackageMaterializer(store, new FakeDownloader()).MaterializeAsync(Guid.NewGuid(), Array.Empty<Guid>(), "fal", "m", env, CancellationToken.None);
    Assert.True(r.Success);
    var roles = r.Package!.Blobs.Select(b => b.Role).ToList();   // confirm the real Artifact blob API (Blobs/Role) when implementing
    Assert.Contains(ReconstructionFileRoles.ModelGlb, roles);
    Assert.Contains(ReconstructionFileRoles.ProviderResultJson, roles);
    Assert.Contains(ReconstructionFileRoles.ImportManifest, roles); }
```

- [ ] **Step 5: Rewrite the materializer + manager glue; wire subsystem**

Materializer:
```csharp
public sealed class ReconstructionPackageMaterializer
{
    private readonly ArtifactStore _store; private readonly IReconstructionRemoteAssetDownloader _downloader;
    public ReconstructionPackageMaterializer(ArtifactStore store, IReconstructionRemoteAssetDownloader downloader)
    { _store = store; _downloader = downloader; }

    public async Task<ReconstructionMaterializeResult> MaterializeAsync(Guid jobId, IReadOnlyList<Guid> sourceArtifactIds, string provider, string modelId, ProviderResultEnvelope envelope, CancellationToken ct)
    {
        var hasModel = envelope.Artifacts.Any(a => a.Role == ReconstructionFileRoles.ModelGlb || a.Role == ReconstructionFileRoles.ModelObj);
        if (!hasModel) return new(false, null, new GenerationError(GenerationErrorCode.ExecutionFailed, "Reconstruction package has no model asset (model_glb/model_obj).", Retryable: false));
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
        return new(true, _store.Create(ReconstructionArtifactKinds.Package, blobs, parentIds: sourceArtifactIds, metadata: metadata), null);
    }
    // keep existing BuildInitialImportManifest / ToJsonArray; add ExtensionFor(role, mime) (model_glb→glb, model_obj→obj, material_mtl→mtl, thumbnail→png, texture→png/derived-from-mime)
}
```
Delete `IReconstructionFileDownloader` + `HttpReconstructionFileDownloader`. Manager glue — replace lazy `PollActiveJobAsync`'s body to consume shared outcomes (still lazy/on-demand; background is Task 5):
```csharp
var handle = new ProviderJobHandle(job.ProviderJobId!, OptionalUri(job.ProviderStatusUrl), OptionalUri(job.ProviderResponseUrl), OptionalUri(job.ProviderCancelUrl), job.ProviderCancelHttpMethod);
switch (await _provider.GetStatusAsync(handle, ct).ConfigureAwait(false))
{
    case InFlightStatusOutcome:
        _ledger.Append(job with { Stage = ReconstructionJobStage.Polling, UpdatedAt = Now() }); return;
    case FailedStatusOutcome f:
        AppendError(job, f.Error); return;
    case ProviderCompleteStatusOutcome complete:
        var fetch = await _provider.FetchResultAsync(complete.UpdatedHandle, ct).ConfigureAwait(false);
        if (fetch is FailedResultOutcome fr) { AppendError(job, fr.Error); return; }
        var mat = await _materializer.MaterializeAsync(job.JobId, new[] { job.SourceArtifactId }, job.Provider, job.ModelId, ((SuccessResultOutcome)fetch).Envelope, ct).ConfigureAwait(false);
        if (!mat.Success) { AppendError(job, mat.Error!); return; }
        _ledger.Append(ReconstructionJobLedgerRecord.Complete(job.JobId, mat.Package!.Id));
        return;
}
// helper:
void AppendError(ReconstructionJobLedgerRecord j, GenerationError e) =>
    _ledger.Append(j with { State = ReconstructionJobState.Error, Stage = ReconstructionJobStage.Error, Error = ReconstructionErrorMapping.ToFailure(e), UpdatedAt = Now() });
```
Manager submit guards the key before kicking the provider: if `!_secrets.HasSecret(GenerationSecretKeys.FalApiKey)` return `ReconstructionFailure("missing_credential", "fal.ai API key is not configured.", Retryable:false, Field:null, Details:new Dictionary<string,object?>())`. (Inject `IGenerationSecretStore _secrets` into the manager if not already present.) Update existing completion tests at `ReconstructionJobManagerTests.cs:92/130/199` to drive the new provider/materializer shapes (scripted provider returns `QueuedSubmitOutcome`→`ProviderCompleteStatusOutcome`→`SuccessResultOutcome(glb envelope)`; fake downloader returns bytes) so they stay green.

`RookSubsystemRoot.CreateReconstruction`:
```csharp
var falClient = new FalApiClient();
Func<string?> falKey = () => SharedGenerationSecretStore.GetSecret(GenerationSecretKeys.FalApiKey);
var provider = new FalReconstructionProvider(new FalApiTransport(falClient, falKey));
var materializer = new ReconstructionPackageMaterializer(SharedArtifactStore, new ReconstructionRemoteAssetDownloader(new HttpClient(), role => role.StartsWith("model_") ? 100_000_000L : 25_000_000L));
var manager = new ReconstructionJobManager(SharedArtifactStore, catalog, new JsonlReconstructionJobLedger(JsonlReconstructionJobLedger.DefaultPath()), provider, materializer, new FalReconstructionSourceImagePublisher(falClient, falKey), SharedGenerationSecretStore);
```

- [ ] **Step 6: Run the FULL reconstruction suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS (new provider + materializer tests, plus the updated completion tests).

- [ ] **Step 7: Commit (one atomic slice)**
```bash
git add -A && git commit -m "refactor(reconstruction): converge provider+materializer+manager onto shared fal mappers, outcomes, and result envelope

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: W6 — Background execution, single-flight, no-orphan shutdown

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces: `ReconstructionJobManager : IDisposable`; per-job background run; preserves the existing public method signatures. Mirrors `VideoJobManager` (lines 39–112, 789–996, 754–785, 1409–1421).
- Single-flight invariant: exactly one terminal transition and one materialization per job, regardless of racing pollers.
- Shutdown invariant: disposal cancels, then bounded-waits/observes running tasks before disposing shared primitives — no orphaned background work.

- [ ] **Step 1: Write failing tests — background drive, single-flight, no-orphan dispose**

```csharp
[Fact]
public async Task Submit_BackgroundLoop_DrivesJobToComplete()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "IN_PROGRESS", "COMPLETED" }, resultEnvelope: bundle.GlbEnvelope());
    using var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(5));
    var submit = await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None);
    await bundle.WaitUntil(() => manager.Status(submit.Job!.JobId).Job!.State == ReconstructionJobState.Complete, 2000);
    Assert.Equal(ReconstructionJobState.Complete, manager.Status(submit.Job!.JobId).Job!.State);
}

[Fact]
public async Task ConcurrentStatusAndBackgroundPoll_ProduceExactlyOneMaterialization()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var counting = bundle.CountingMaterializer();
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "COMPLETED" }, resultEnvelope: bundle.GlbEnvelope());
    using var manager = bundle.BuildManager(provider: provider, materializer: counting, pollInterval: TimeSpan.FromMilliseconds(1));
    var jobId = (await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None)).Job!.JobId;
    await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => manager.StatusAsync(jobId, CancellationToken.None)));
    await bundle.WaitUntil(() => manager.Status(jobId).Job!.State == ReconstructionJobState.Complete, 2000);
    Assert.Equal(1, counting.Count);
}

[Fact]
public async Task Dispose_DrainsRunningLoop_NoCompletionAfterShutdown()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var gate = new SemaphoreSlim(0);                                      // provider blocks inside status until released
    var provider = bundle.BlockingStatusProvider(gate, statuses: new[] { "IN_PROGRESS" });
    var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(5));
    var jobId = (await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None)).Job!.JobId;
    manager.Dispose();                                                   // must cancel + drain, not throw, not hang
    gate.Release(10);
    Assert.NotEqual(ReconstructionJobState.Complete, manager.Status(jobId).Job!.State);
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests" --no-restore`
Expected: FAIL (no background loop; not IDisposable).

- [ ] **Step 3: Add background lifecycle with deterministic shutdown (mirror VideoJobManager)**

```csharp
public static readonly TimeSpan DefaultPollInterval = TimeSpan.FromSeconds(10);
public const int DefaultMaxConcurrentJobs = 2;
private readonly CancellationTokenSource _shutdownCts = new();
private readonly ConcurrentDictionary<Guid, RunningJob> _runningJobs = new();
private readonly SemaphoreSlim _concurrency = new(DefaultMaxConcurrentJobs, DefaultMaxConcurrentJobs);
private readonly TimeSpan _pollInterval; // ctor param, default DefaultPollInterval

private sealed class RunningJob
{
    public ReconstructionJobLedgerRecord Latest;
    public readonly CancellationTokenSource Cts;
    public Task Loop = Task.CompletedTask;          // tracked for drain
    public RunningJob(ReconstructionJobLedgerRecord initial, CancellationTokenSource cts) { Latest = initial; Cts = cts; }
}
```
On submit (after the queued record is persisted with the handle), kick the loop and TRACK the task:
```csharp
var linked = CancellationTokenSource.CreateLinkedTokenSource(_shutdownCts.Token);
var running = new RunningJob(record, linked);
_runningJobs[record.JobId] = running;
running.Loop = Task.Run(() => RunJobAsync(record.JobId, running), CancellationToken.None);
```
`RunJobAsync` mirrors `VideoJobManager.RunJobAsync`: guard the semaphore acquire with an `acquired` flag so a shutdown-before-acquire never releases a slot it didn't take:
```csharp
private async Task RunJobAsync(Guid jobId, RunningJob running)
{
    var ct = running.Cts.Token;
    var acquired = false;
    try
    {
        await _concurrency.WaitAsync(ct).ConfigureAwait(false);
        acquired = true;
        // poll loop: while (true) { ct.ThrowIfCancellationRequested(); status = GetStatusAsync(handle); 
        //   InFlight → await Task.Delay(_pollInterval, ct); continue;
        //   Failed → AppendErrorLocked; return;
        //   Complete → FetchResultAsync → MaterializeAsync → AppendCompleteLocked; return; }
    }
    catch (OperationCanceledException) when (ct.IsCancellationRequested) { /* leave non-terminal; reconcile handles it */ }
    catch (Exception ex) { AppendErrorLocked(running, new GenerationError(GenerationErrorCode.ExecutionFailed, ex.Message, false)); }
    finally
    {
        _runningJobs.TryRemove(jobId, out _);
        if (acquired) _concurrency.Release();
        running.Cts.Dispose();
    }
}
```
**Single-flight:** the terminal transition + materialization inside `RunJobAsync`, AND the on-demand `StatusAsync`/`PollActiveJobAsync` path, both acquire the existing per-job `_pollLocks[jobId]` semaphore and **re-read the freshest ledger record after acquiring**; if it is already terminal, return without fetch/materialize. (`AppendCompleteLocked`/`AppendErrorLocked` take that lock + re-read.)

`IDisposable` with deterministic drain:
```csharp
public void Dispose()
{
    try { _shutdownCts.Cancel(); } catch { }
    Task[] loops; loops = _runningJobs.Values.Select(r => r.Loop).ToArray();
    try { Task.WaitAll(loops, TimeSpan.FromSeconds(5)); } catch { /* faulted/cancelled loops are fine */ }
    _shutdownCts.Dispose();
    _concurrency.Dispose();
}
```

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): background job execution with single-flight and deterministic no-orphan shutdown

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: W6 — Startup reconcile + subsystem wiring

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
    foreach (var record in _ledger.List(int.MaxValue).Jobs)
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
Provider job id/URLs survive automatically because `record with { ... }` copies the unchanged fields. In `RookSubsystemRoot`: after building the manager in `CreateReconstruction`, call `manager.ReconcileInterruptedJobs();` before returning the handler; and dispose the manager in the subsystem's existing dispose path (where `_disposed` is set) following the existing video-subsystem dispose wiring in this file — expose the manager from `ReconstructionOpHandler` (e.g. an internal `Manager` property) so the root can dispose it.

- [ ] **Step 4: Run, verify pass + suite green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(reconstruction): startup reconcile of interrupted jobs + dispose wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: W7 boundary — `GenerationError → ReconstructionFailure` verified end-to-end

**Files:**
- Verify: `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs` (from Task 4)
- Modify (only if needed): `src/Rook/Handlers/ReconstructionOpHandler.cs` (`StatusFor` allow-list)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

- [ ] **Step 1: Write failing test — a fal quota failure surfaces a typed, retryable `ReconstructionFailure`**

```csharp
[Fact]
public async Task ProviderQuotaFailure_SurfacesRetryableReconstructionFailure()
{
    var bundle = ReconstructionTestBundle.WithSourceImage(out var sourceId);
    var provider = bundle.ScriptedProvider(queued: true, statuses: new[] { "STATUS_429" }, resultEnvelope: null); // status poll → HTTP 429
    using var manager = bundle.BuildManager(provider: provider, pollInterval: TimeSpan.FromMilliseconds(2));
    var jobId = (await manager.SubmitAsync(bundle.SubmitRequest(sourceId), CancellationToken.None)).Job!.JobId;
    await bundle.WaitUntil(() => manager.Status(jobId).Job!.State == ReconstructionJobState.Error, 2000);
    var rec = manager.Status(jobId).Job!;
    Assert.Equal("quota_exceeded", rec.Error!.Code);
    Assert.True(rec.Error!.Retryable);
}
```

- [ ] **Step 2: Run, verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ProviderQuotaFailure" --no-restore`
Expected: FAIL (implement the scripted provider's 429 status path).

- [ ] **Step 3: Confirm the mapping is applied at every error append**

Audit `ReconstructionJobManager`: every `State = ReconstructionJobState.Error` append must set `Error = ReconstructionErrorMapping.ToFailure(generationError)` (never a hand-built opaque `poll_failed`). `MapCode` already covers all `GenerationErrorCode` members. `ReconstructionOpHandler.StatusFor` needs no change unless a mapped code (`quota_exceeded`, `provider_unavailable`, `missing_credential`) should be non-500; if so, add it to the existing 400/404 allow-list.

- [ ] **Step 4: Run, verify pass + FULL reconstruction + MCP suites green**

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
- [ ] `rg -n "InvalidOperationException" src/Rook/Services/Reconstruction/` returns no fal/HTTP-boundary throws.
- [ ] `rg -n "GetAwaiter\(\)\.GetResult\(\)|\.Result\b|ContinueWith|File\.ReadAllBytes" src/Rook/Services/Reconstruction/` returns nothing.
- [ ] `rg -n "FalErrorMapper|FalLifecycleMapper" src/Rook/Services/Reconstruction/` shows the mappers are now used.
- [ ] No file under `src/Rook/Services/Vision/` was modified by this branch's new commits.
- [ ] Native build verified separately (out of unit scope).

## Notes / known follow-ups (out of scope here)

- Shared `MediaDownloader` extraction across image/video/reconstruction (rule-of-three follow-up; see spec Substrate Trajectory).
- `IGenerationProvider<TRequest,TCapability>` adoption (option C; deferred).
- Reconciling main's divergent uncommitted `ReplaceJsonBlob` copy — a separate, user-directed action; this pass does not touch main.
