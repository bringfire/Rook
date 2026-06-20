# Typed `missing_credential` at the fal edge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A missing fal API key surfaces as a typed, public `ReconstructionFailure` (`missing_credential`, non-retryable, remediation message) across submit, poll, and cancel — replacing the opaque `submit_failed`/`poll_failed`/unhandled-throw paths.

**Architecture:** An internal marker exception (`ReconstructionCredentialMissingException`) is thrown at the two reconstruction fal-edge sites (`FalApiTransport.Key()`, `FalReconstructionSourceImagePublisher.PublishAsync`) and caught at the three `ReconstructionJobManager` boundaries (each ordered **before** any generic catch). A single `ReconstructionErrorMapping.MissingCredentialFailure()` factory builds the canonical public failure.

**Tech Stack:** C# (net48), xUnit. Spec: `docs/superpowers/specs/2026-06-20-reconstruction-missing-credential-design.md`.

## Global Constraints

- Reconstruction-local only. Do **not** change `GenerationErrorCode` or any file under `src/Rook/Services/Vision/`.
- The exception type is `internal` (not public contract). Public surface stays `ReconstructionFailure`.
- One factory builds the failure: `ReconstructionErrorMapping.MissingCredentialFailure()`. Submit, poll, and cancel must all call it — no inline duplication of code/message/retryability.
- `catch (ReconstructionCredentialMissingException)` MUST be ordered **before** any generic `catch (Exception)` (and after any `catch (OperationCanceledException) when (ct.IsCancellationRequested)` rethrow).
- Internal diagnostic text (exception message) and public remediation text (factory) stay decoupled.
- Public remediation message (verbatim): `fal API key is not configured. Set it in Vision settings before starting reconstruction.`
- Non-retryable: the failure's `Retryable` is `false`.
- Cancel semantics unchanged: `CancellationRequested` is already recorded before the provider cancel call; only make the response typed.
- Run C# tests with `-c Debug` (the `%AppData%` `DeployToRhino` target is `Release`-gated). The string "Deployed Rook.rhp" must NOT appear in test output.
- Regression guards must stay green: `Submit_PublisherFailure_RecordsTerminalError` (`InvalidOperationException` → `submit_failed`); transport-fault tests (`HttpRequestException`/`TaskCanceledException` → `provider_unavailable`); caller-cancel propagation.
- Branch: `codex/reconstruction-missing-credential` (already created off `origin/main` `5a0114f9`). Stage explicit files only — never `git add -A`/`-a`.

---

### Task 1: Internal exception + transport throw site

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (add the exception type; change `FalApiTransport.Key()`)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

**Interfaces:**
- Produces: `internal sealed class ReconstructionCredentialMissingException : Exception` in namespace `Rook.Services.Reconstruction.Fal` (parameterless ctor; base message `"fal API key is not configured."`). Used by Tasks 3–5.

- [ ] **Step 1: Add the internal exception type**

In `FalReconstructionProvider.cs`, immediately after the `namespace Rook.Services.Reconstruction.Fal;` line (before `public sealed record ReconstructionProviderSubmitRequest`), add:

```csharp
/// <summary>
/// Internal signal that the fal API key is not configured, raised at the reconstruction fal edge
/// (<see cref="FalApiTransport"/> / <see cref="FalReconstructionSourceImagePublisher"/>) and caught at
/// the <c>ReconstructionJobManager</c> boundary, which maps it to the public
/// <c>missing_credential</c> failure. NOT part of the public contract. Carries a short diagnostic only —
/// the public remediation text is owned by <c>ReconstructionErrorMapping.MissingCredentialFailure()</c>.
/// </summary>
internal sealed class ReconstructionCredentialMissingException : System.Exception
{
    public ReconstructionCredentialMissingException()
        : base("fal API key is not configured.")
    {
    }
}
```

- [ ] **Step 2: Change `FalApiTransport.Key()` to throw it**

In the same file, replace the body of `private string Key()`:

```csharp
    private string Key()
    {
        var apiKey = _apiKey();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("fal API key is required for reconstruction.");
        return apiKey!;
    }
```

with:

```csharp
    private string Key()
    {
        var apiKey = _apiKey();
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new ReconstructionCredentialMissingException();
        return apiKey!;
    }
```

- [ ] **Step 3: Write the failing transport test**

In `FalReconstructionProviderTests.cs`, add this test method to the `FalReconstructionProviderTests` class (e.g. after `Submit_CallerCancels_PropagatesOperationCanceled`):

```csharp
    [Fact]
    public void Transport_MissingApiKey_ThrowsCredentialMissing_Synchronously()
    {
        // Key() is evaluated synchronously before the Task is returned, so this throws synchronously
        // (assert with Assert.Throws, NOT Assert.ThrowsAsync).
        var transport = new FalApiTransport(new FalApiClient(), () => null);

        Assert.Throws<ReconstructionCredentialMissingException>(() =>
        {
            _ = transport.PostJsonAsync(new Uri("https://queue.fal.run/req"), "{}", CancellationToken.None);
        });
        Assert.Throws<ReconstructionCredentialMissingException>(() =>
        {
            _ = transport.GetAsync(new Uri("https://queue.fal.run/req"), CancellationToken.None);
        });
        Assert.Throws<ReconstructionCredentialMissingException>(() =>
        {
            _ = transport.SendAsync(HttpMethod.Put, new Uri("https://queue.fal.run/req"), null, CancellationToken.None);
        });
    }
```

(The file already imports `System` for `Uri`, `System.Net.Http` for `HttpMethod`/`FalApiClient` is via `Rook.Services.Vision.Fal`, `System.Threading` for `CancellationToken`, and `Rook.Services.Reconstruction.Fal` for `FalApiTransport`/`ReconstructionCredentialMissingException` — no new usings needed.)

- [ ] **Step 4: Run the test to verify it passes (and the suite stays green)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~FalReconstructionProviderTests" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!`. (Steps 1–2 must precede the test, because referencing `ReconstructionCredentialMissingException` and the new throw is what makes this assertion meaningful; verify no "Deployed Rook" line appears.)

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs
git commit -m "feat(reconstruction): throw typed credential-missing at the fal transport edge"
```

---

### Task 2: Canonical `missing_credential` failure factory

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionErrorMappingTests.cs` (create)

**Interfaces:**
- Produces: `public const string ReconstructionErrorMapping.MissingCredentialMessage` and `public static ReconstructionFailure ReconstructionErrorMapping.MissingCredentialFailure()`. Used by Tasks 3–5.

- [ ] **Step 1: Write the failing factory test**

Create `src/Rook.Tests/Services/Reconstruction/ReconstructionErrorMappingTests.cs`:

```csharp
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionErrorMappingTests
{
    [Fact]
    public void MissingCredentialFailure_IsNonRetryableTypedFailureWithRemediation()
    {
        var failure = ReconstructionErrorMapping.MissingCredentialFailure();

        Assert.Equal("missing_credential", failure.Code);
        Assert.False(failure.Retryable);
        Assert.Null(failure.Field);
        Assert.Contains("fal API key", failure.Message);
        Assert.Contains("Vision settings", failure.Message);
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionErrorMappingTests" 2>&1 | grep -iE "error CS|Failed!"`
Expected: FAIL — build error `'ReconstructionErrorMapping' does not contain a definition for 'MissingCredentialFailure'`.

- [ ] **Step 3: Add the const and factory**

In `ReconstructionErrorMapping.cs`, inside the `ReconstructionErrorMapping` class, add (after the `ToFailure` method, before `MapCode`):

```csharp
    /// <summary>
    /// Public, user-facing remediation text for a missing fal credential. Single source of truth so the
    /// submit/poll/cancel paths cannot drift. Distinct from the internal exception's diagnostic message.
    /// </summary>
    public const string MissingCredentialMessage =
        "fal API key is not configured. Set it in Vision settings before starting reconstruction.";

    /// <summary>
    /// Canonical missing-credential failure. A missing fal key is a configuration defect, not a transient
    /// outage, so it is non-retryable. The ONLY place a "missing_credential" failure is constructed.
    /// </summary>
    public static ReconstructionFailure MissingCredentialFailure()
        => new(
            "missing_credential",
            MissingCredentialMessage,
            Retryable: false,
            Field: null,
            Details: new Dictionary<string, object?>());
```

(`ReconstructionErrorMapping.cs` already has `using System.Collections.Generic;` and is in namespace `Rook.Services.Reconstruction`, where `ReconstructionFailure` lives — no new usings.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionErrorMappingTests" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!`, no "Deployed Rook" line.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs src/Rook.Tests/Services/Reconstruction/ReconstructionErrorMappingTests.cs
git commit -m "feat(reconstruction): add canonical missing_credential failure factory"
```

---

### Task 3: Submit path — publisher throws + ordered catch

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` (`FalReconstructionSourceImagePublisher.PublishAsync`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`SubmitAsync` catch ordering)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionCredentialMissingException` (Task 1), `ReconstructionErrorMapping.MissingCredentialFailure()` (Task 2), existing private `RecordSubmitFailure(...)`.

- [ ] **Step 1: Write the failing submit test**

In `ReconstructionJobManagerTests.cs`, add a nested fake secret store to the `ReconstructionJobManagerTests` class (next to the other `private sealed class Fake*` types):

```csharp
    private sealed class NullSecretStore : IGenerationSecretStore
    {
        public string? GetSecret(string secretKey) => null;
        public void SetSecret(string secretKey, string value) { }
        public void RemoveSecret(string secretKey) { }
        public bool HasSecret(string secretKey) => false;
        public string? GetPreview(string secretKey) => null;
    }
```

Then add the test (near the other `Submit_*` tests):

```csharp
    [Fact]
    public async Task Submit_MissingApiKey_RecordsMissingCredential_NotSubmitFailed()
    {
        // Real source publisher + a secret store with no fal key → PublishAsync throws the typed
        // credential exception at the fal edge, which the submit boundary maps to missing_credential.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FakeReconstructionProvider(),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FalReconstructionSourceImagePublisher(new FalApiClient(), new NullSecretStore()));
        _managers.Add(manager);
        var source = store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = await manager.SubmitAsync(Request(source.Id), CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("missing_credential", result.Failure!.Code);
        Assert.False(result.Failure.Retryable);
        var terminal = manager.List(10).Jobs.Single();
        Assert.Equal(ReconstructionJobState.Error, terminal.State);
        Assert.Equal("missing_credential", terminal.Error!.Code);
    }
```

(The file already imports `Rook.Services.Reconstruction.Fal` (`FalReconstructionSourceImagePublisher`), `Rook.Services.Vision.Fal` (`FalApiClient`), and `Rook.Services.Vision.Generation` (`IGenerationSecretStore`).)

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Submit_MissingApiKey_RecordsMissingCredential_NotSubmitFailed" 2>&1 | grep -iE "Expected:|Actual:|Failed!"`
Expected: FAIL — `Expected: "missing_credential"` / `Actual: "submit_failed"` (publisher still throws `InvalidOperationException`, caught by the generic submit catch).

- [ ] **Step 3: Change the publisher to throw the typed exception**

In `FalReconstructionProvider.cs`, in `FalReconstructionSourceImagePublisher.PublishAsync`, replace:

```csharp
        var apiKey = _secrets.GetSecret(GenerationSecretKeys.FalApiKey);
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("fal API key is required for reconstruction.");
```

with:

```csharp
        var apiKey = _secrets.GetSecret(GenerationSecretKeys.FalApiKey);
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new ReconstructionCredentialMissingException();
```

- [ ] **Step 4: Add the ordered submit catch**

In `ReconstructionJobManager.cs`, in `SubmitAsync`, locate:

```csharp
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (FalApiException ex)
        {
```

Insert a new catch between them so it reads:

```csharp
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            // Missing fal key (publisher edge, or provider edge if the key vanished mid-submit). Map to
            // the canonical typed failure rather than the generic submit_failed below. MUST stay before
            // the FalApiException/Exception catches.
            return RecordSubmitFailure(submitting, ReconstructionErrorMapping.MissingCredentialFailure());
        }
        catch (FalApiException ex)
        {
```

(`ReconstructionJobManager.cs` already imports `Rook.Services.Reconstruction.Fal` and is in namespace `Rook.Services.Reconstruction`, so both `ReconstructionCredentialMissingException` and `ReconstructionErrorMapping` resolve.)

- [ ] **Step 5: Run the new test + the submit-path regression guard**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Submit_MissingApiKey_RecordsMissingCredential_NotSubmitFailed|FullyQualifiedName~Submit_PublisherFailure_RecordsTerminalError|FullyQualifiedName~Submit_FalUploadFailure" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!`. (`Submit_PublisherFailure_RecordsTerminalError` still maps `InvalidOperationException` → `submit_failed`; `Submit_FalUploadFailure` still maps `FalApiException` → `provider_unavailable`.)

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): map missing fal key to missing_credential on submit"
```

---

### Task 4: Poll path — ordered catch

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`PollActiveJobAsync` catch ordering)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionCredentialMissingException` (Task 1), `ReconstructionErrorMapping.MissingCredentialFailure()` (Task 2), existing private `FindJob(...)`.

- [ ] **Step 1: Write the failing poll test**

In `ReconstructionJobManagerTests.cs`, add (near the other poll tests):

```csharp
    [Fact]
    public async Task Poll_MissingApiKey_RecordsMissingCredential_NotPollFailed()
    {
        // Real provider over a transport with no key. Seed a polling job directly (submit would itself
        // fail on the missing key), then poll → GetStatus → Key() throws → typed missing_credential.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(new FalApiTransport(new FalApiClient(), () => null)),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher());
        _managers.Add(manager);

        var jobId = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(jobId, HunyuanModelId, Guid.NewGuid(), "image") with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Polling,
            ProviderJobId = "req-1",
            ProviderStatusUrl = "https://queue.fal.run/status/req-1",
            ProviderResponseUrl = "https://queue.fal.run/response/req-1",
            ProviderCancelUrl = "https://queue.fal.run/cancel/req-1",
            ProviderCancelHttpMethod = "PUT",
        });

        await manager.PollActiveJobAsync(jobId, CancellationToken.None);

        var rec = manager.Status(jobId).Job!;
        Assert.Equal(ReconstructionJobState.Error, rec.State);
        Assert.Equal("missing_credential", rec.Error!.Code);   // typed, not opaque "poll_failed"
        Assert.False(rec.Error.Retryable);
    }
```

(`FalReconstructionProvider`/`FalApiTransport` come from `Rook.Services.Reconstruction.Fal`, `FalApiClient` from `Rook.Services.Vision.Fal` — both already imported.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Poll_MissingApiKey_RecordsMissingCredential_NotPollFailed" 2>&1 | grep -iE "Expected:|Actual:|Failed!"`
Expected: FAIL — `Expected: "missing_credential"` / `Actual: "poll_failed"`.

- [ ] **Step 3: Add the ordered poll catch**

In `ReconstructionJobManager.cs`, in `PollActiveJobAsync`, locate the catch block (after the materialization `try`):

```csharp
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex)
        {
            var latest = FindJob(jobId);
            if (latest is null)
                throw;
```

Insert a new catch between the `OperationCanceledException` catch and the `Exception` catch:

```csharp
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            // Missing fal key during status/result polling → typed missing_credential, not the opaque
            // poll_failed below. MUST stay before the generic Exception catch.
            var latest = FindJob(jobId);
            if (latest is null)
                throw;

            _ledger.Append(latest with
            {
                State = ReconstructionJobState.Error,
                Stage = ReconstructionJobStage.Error,
                Error = ReconstructionErrorMapping.MissingCredentialFailure(),
                UpdatedAt = DateTimeOffset.UtcNow,
            });
        }
        catch (Exception ex)
        {
            var latest = FindJob(jobId);
            if (latest is null)
                throw;
```

(The `finally { gate.Release(); }` already follows the catches and is unchanged.)

- [ ] **Step 4: Run the new test + the poll-path regression guards**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Poll_MissingApiKey_RecordsMissingCredential_NotPollFailed|FullyQualifiedName~ProviderTransportFailure_DuringStatusPoll|FullyQualifiedName~StatusAsync_DownloadFailure" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!`. (Transport faults still map to `provider_unavailable`; download failures still typed.)

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): map missing fal key to missing_credential on poll"
```

---

### Task 5: Cancel path — typed result, no unhandled throw

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`CancelAsync`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionCredentialMissingException` (Task 1), `ReconstructionErrorMapping.MissingCredentialFailure()` (Task 2).

- [ ] **Step 1: Write the failing cancel test**

In `ReconstructionJobManagerTests.cs`, add (near the other cancel tests):

```csharp
    [Fact]
    public async Task Cancel_MissingApiKey_ReturnsCancellationRequestedWithMissingCredential_NoThrow()
    {
        // Real provider over a transport with no key. Seed a polling job, then cancel → remote cancel
        // hits Key() → typed missing_credential returned (not an unhandled throw). CancellationRequested
        // is still recorded first.
        var root = NewTempRoot();
        var store = new ArtifactStore(Path.Combine(root, "artifacts"));
        var ledger = new JsonlReconstructionJobLedger(Path.Combine(root, "ledger.jsonl"));
        var manager = new ReconstructionJobManager(
            store,
            ReconstructionModelCatalog.FromJson(CatalogJson),
            ledger,
            new FalReconstructionProvider(new FalApiTransport(new FalApiClient(), () => null)),
            new ReconstructionPackageMaterializer(store, new FakeDownloader()),
            new FakeSourceImagePublisher());
        _managers.Add(manager);

        var jobId = Guid.NewGuid();
        ledger.Append(ReconstructionJobLedgerRecord.Queued(jobId, HunyuanModelId, Guid.NewGuid(), "image") with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Polling,
            ProviderJobId = "req-1",
            ProviderStatusUrl = "https://queue.fal.run/status/req-1",
            ProviderResponseUrl = "https://queue.fal.run/response/req-1",
            ProviderCancelUrl = "https://queue.fal.run/cancel/req-1",
            ProviderCancelHttpMethod = "PUT",
        });

        var cancel = await manager.CancelAsync(jobId, CancellationToken.None);

        Assert.Equal(ReconstructionJobState.CancellationRequested, cancel.State);
        Assert.Equal("missing_credential", cancel.Failure!.Code);
        Assert.False(cancel.Failure.Retryable);
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Cancel_MissingApiKey_ReturnsCancellationRequestedWithMissingCredential_NoThrow" 2>&1 | grep -iE "Failed!|ReconstructionCredentialMissingException|Exception"`
Expected: FAIL — the test throws `ReconstructionCredentialMissingException` (unhandled) out of `manager.CancelAsync`, so the test errors rather than asserting.

- [ ] **Step 3: Wrap the remote cancel call**

In `ReconstructionJobManager.cs`, in `CancelAsync`, replace:

```csharp
        if (!string.IsNullOrWhiteSpace(job.ProviderJobId))
            await _provider.CancelAsync(HandleFor(job), ct).ConfigureAwait(false);

        return new ReconstructionCancelResult(ReconstructionJobState.CancellationRequested, null);
```

with:

```csharp
        if (!string.IsNullOrWhiteSpace(job.ProviderJobId))
        {
            try
            {
                await _provider.CancelAsync(HandleFor(job), ct).ConfigureAwait(false);
            }
            catch (ReconstructionCredentialMissingException)
            {
                // Best-effort remote cancel hit a missing fal key. CancellationRequested was already
                // recorded above; surface a typed failure instead of an unhandled throw. Ledger
                // semantics unchanged.
                return new ReconstructionCancelResult(
                    ReconstructionJobState.CancellationRequested,
                    ReconstructionErrorMapping.MissingCredentialFailure());
            }
        }

        return new ReconstructionCancelResult(ReconstructionJobState.CancellationRequested, null);
```

- [ ] **Step 4: Run the new test + the cancel-path regression guard**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Cancel_MissingApiKey_ReturnsCancellationRequestedWithMissingCredential_NoThrow|FullyQualifiedName~Cancel_PollingJob_AttemptsRemoteCancel" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!`. (Normal cancel still records `CancellationRequested` and calls remote cancel.)

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): map missing fal key to missing_credential on cancel"
```

---

### Task 6: Full-suite verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full Debug C# suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|Passed:|Failed:|Total:|error CS"`
Expected: `Passed!` with `Failed: 0`. No "Deployed Rook" line. (Baseline before this slice was 2825 passing; this slice adds 5 tests → expect ~2830, 0 failed.)

- [ ] **Step 2: Run the MCP reconstruction parity tests**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q 2>&1 | tail -3`
Expected: `17 passed` (the `.pytest_cache` permission warning is pre-existing and fine).

- [ ] **Step 3: Confirm the constraint greps are clean**

Run: `grep -rn "GenerationErrorCode" src/Rook/Services/Reconstruction/ ; git diff --name-only origin/main | grep -i "Services/Vision" || echo "NO Vision files touched"`
Expected: no new `GenerationErrorCode` usage introduced in reconstruction by this slice; `NO Vision files touched`.

- [ ] **Step 4: No commit** (verification only). If anything is red, return to the owning task.

---

## Self-Review

**Spec coverage:**
- Internal exception (spec §1) → Task 1. ✓
- Decoupled strings (spec §2) → Task 1 (exception diagnostic) + Task 2 (factory message). ✓
- Single mapping factory (spec §3) → Task 2; called by Tasks 3/4/5. ✓
- Throw sites (spec §4) → transport in Task 1, publisher in Task 3. ✓
- Ordered manager catches (spec §5) → submit Task 3, poll Task 4, cancel Task 5; each inserts before the generic catch and after the caller-cancel rethrow. ✓
- Testing (spec) → transport unit (Task 1), submit (Task 3), poll (Task 4), cancel (Task 5), regression guards exercised in Tasks 3/4/5 and the full gate (Task 6). ✓
- Non-goals (no GenerationErrorCode/Vision change, no preflight probe, cancel semantics unchanged) → respected; verified in Task 6 Step 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `ReconstructionCredentialMissingException` (Task 1) — used verbatim in Tasks 3/4/5. `ReconstructionErrorMapping.MissingCredentialFailure()` / `MissingCredentialMessage` (Task 2) — used verbatim in Tasks 3/4/5. `ReconstructionFailure(Code, Message, Retryable, Field, Details)` ctor matches the record in `ReconstructionContracts.cs`. `IGenerationSecretStore` fake implements all five interface members. `RecordSubmitFailure` / `FindJob` are existing private members consumed as-is. ✓
