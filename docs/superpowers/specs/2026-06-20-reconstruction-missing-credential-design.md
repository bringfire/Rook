# Reconstruction — typed `missing_credential` at the fal edge

- Date: 2026-06-20
- Status: Approved for implementation planning (brainstorm + spec review complete)
- Branch: `codex/reconstruction-missing-credential` (off `origin/main` `5a0114f9`)
- Follow-up to: reconstruction substrate convergence (PR #285, merged)

## Problem

When the fal API key is not configured, the reconstruction subsystem surfaces an
opaque, misleading failure. Two reconstruction-owned fal-edge sites throw a bare
`InvalidOperationException("fal API key is required for reconstruction.")`:

- `FalApiTransport.Key()` — hit on status/result polling and on cancel.
- `FalReconstructionSourceImagePublisher.PublishAsync` — hit on submit.

Both propagate to the `ReconstructionJobManager` catch-alls and become
`submit_failed` (submit) or `poll_failed` (poll); on cancel the exception is
unhandled and escapes `manager.CancelAsync` to the caller. None of these tell the
user the real problem — a missing configuration value they must set — and
`submit_failed`/`poll_failed` read as transient. This is the last opaque fal-edge
failure left after the convergence pass.

The shared `GenerationErrorCode` enum has no credential code; it folds "missing
api key" into `DependencyUnavailable` (→ `provider_unavailable`), and the Vision
fal providers do the same. A distinct `missing_credential` is therefore a
deliberate, reconstruction-local divergence — it separates "you have not
configured a key" (config defect, user action) from "the provider is
unavailable" (transient, retry later).

## Goals

- A missing fal key surfaces as a typed, public `ReconstructionFailure` with
  `Code = "missing_credential"`, `Retryable = false`, and a remediation message.
- Coverage across all three reconstruction paths that touch the fal edge:
  **submit, poll (status/result), and cancel**.
- One canonical mapping so the three paths cannot drift in code, message, or
  retryability.
- No change to the shared `GenerationErrorCode` enum and no Vision files touched.

## Non-goals

- No `GenerationErrorCode` change; no Vision (`src/Rook/Services/Vision/`) files.
- No preflight credential-presence probe / new credential API on the manager.
- No broader credential-management UX.
- No change to `provider_unavailable` semantics.
- No change to cancel semantics: cancel still records `CancellationRequested`
  first; this slice only makes the response typed instead of an unhandled throw.

## Design

### 1. Internal signal (not public contract)

Add `internal sealed class ReconstructionCredentialMissingException : Exception`
in `Rook.Services.Reconstruction.Fal`. It is a marker type used only inside the
reconstruction subsystem to carry "credential missing" from the fal edge to the
manager boundary. It is **not** part of the public contract — the public surface
remains `ReconstructionFailure`. (`Rook` already exposes internals to `Rook.Tests`
via `InternalsVisibleTo` (`Rook.csproj`), so tests may reference it.)

It derives from `Exception` (not `InvalidOperationException`) so it is not caught
by the unrelated `catch (InvalidOperationException)` in
`ReconstructionOpHandler.ProviderFileNamesByRole`, and so the existing
publisher-throws-`InvalidOperationException` path stays a genuine local-IO
`submit_failed`.

### 2. Two decoupled strings

- **Internal diagnostic** (on the exception): a short string such as
  `"fal API key is not configured"`. Used for logs/diagnostics only. The exception
  message is intentionally **not** reused as the public UX text.
- **Public remediation text** (owned by the mapping helper, see §3): the full
  user-facing message, e.g.
  `"fal API key is not configured. Set it in Vision settings before starting reconstruction."`

Keeping these separate prevents coupling internal diagnostic wording to public UX
wording.

### 3. Single mapping helper (no drift)

Add one canonical factory — `ReconstructionErrorMapping.MissingCredentialFailure()`
— returning:

```
new ReconstructionFailure(
    Code: "missing_credential",
    Message: <public remediation const>,
    Retryable: false,
    Field: null,
    Details: <empty>)
```

`ReconstructionErrorMapping` is the existing `GenerationError → ReconstructionFailure`
boundary mapper, so it is the natural home. All three manager catch sites call this
single factory; the public remediation text lives in one `const` here. The factory
is the only place that builds a `missing_credential` failure.

### 4. Throw sites (the fal edge)

Replace the bare `InvalidOperationException` with
`ReconstructionCredentialMissingException` (carrying the §2 internal diagnostic) in:

- `FalApiTransport.Key()`
- `FalReconstructionSourceImagePublisher.PublishAsync`

`Key()` is evaluated before any `FalApiClient` call, so the missing-key case
short-circuits with no network I/O.

### 5. Manager catch sites (3 boundaries) — explicit ordering requirement

The exception is **not** magically bypassed by the existing handlers — a generic
`catch (Exception)` will still catch it unless ordered correctly. The spec
therefore **requires** that, at each site, `catch (ReconstructionCredentialMissingException)`
is placed **before** any broader catch:

- **`SubmitAsync`** — add `catch (ReconstructionCredentialMissingException)`
  **before** the existing `catch (FalApiException)` and `catch (Exception)` (and
  after the existing `catch (OperationCanceledException) when (ct.IsCancellationRequested)`),
  returning `RecordSubmitFailure(submitting, MissingCredentialFailure())`.
  (The publisher throws here; the provider would too if the key vanished between
  publish and submit.)
- **`PollActiveJobAsync`** — add `catch (ReconstructionCredentialMissingException)`
  **before** the existing generic `catch (Exception)` that records `poll_failed`,
  recording a terminal `Error` ledger entry with `MissingCredentialFailure()`.
  (Must remain after the `catch (OperationCanceledException) when (...)` rethrow.)
- **`CancelAsync`** — wrap the `await _provider.CancelAsync(...)` call in
  `try { ... } catch (ReconstructionCredentialMissingException) { ... }` and return
  `ReconstructionCancelResult(ReconstructionJobState.CancellationRequested, MissingCredentialFailure())`.
  `CancellationRequested` is already appended to the ledger before this call, so
  cancel semantics are unchanged; only the response becomes typed instead of an
  unhandled throw.

The `catch (OperationCanceledException) when (ct.IsCancellationRequested)` rethrows
must remain first wherever they exist, so genuine caller cancellation still
propagates.

## Testing (TDD; drive the real edge)

Tests exercise the real edge with a missing key rather than re-throwing a fake, so
they prove the actual throw sites and the catch ordering:

- **Submit** — construct the manager with the **real**
  `FalReconstructionSourceImagePublisher` plus a fake `IGenerationSecretStore`
  returning `null` for the fal key → `PublishAsync` throws → assert the submit
  result and the terminal ledger record are `missing_credential`, `Retryable=false`.
- **Poll** — real `FalReconstructionProvider` over a real
  `FalApiTransport(apiKey: () => null)` → `GetStatusAsync` → `Key()` throws → after
  a poll the job is terminal `Error` with `missing_credential` (not `poll_failed`).
- **Cancel** — same real provider/transport → `manager.CancelAsync` returns
  `CancellationRequested` with a `missing_credential` failure and does **not** throw.
- **Transport unit** — `FalApiTransport` with a null key throws
  `ReconstructionCredentialMissingException` from `PostJsonAsync` / `GetAsync` /
  `SendAsync` (uses `InternalsVisibleTo`). Note: `Key()` is evaluated
  **synchronously** before the `Task` is returned, so assert with
  `Assert.Throws<ReconstructionCredentialMissingException>(() => transport.PostJsonAsync(...))`,
  **not** `Assert.ThrowsAsync` (which would only observe a faulted task). The
  async manager path is covered by the provider-level poll/cancel tests above.

### Regression guards (must stay green)

- The existing `Submit_PublisherFailure_RecordsTerminalError` test (publisher
  throws `InvalidOperationException`) must still produce `submit_failed` — proving
  the new typed path does not capture genuine local-IO faults.
- The existing transport-fault tests (`HttpRequestException` /
  `TaskCanceledException` → `provider_unavailable`) and caller-cancel propagation
  must stay green — proving the new catch ordering does not disturb them.

## Risks

- **Catch ordering** is the load-bearing detail: a misordered generic catch would
  silently re-collapse the new failure into `submit_failed`/`poll_failed`. The
  tests assert the resulting `missing_credential` code precisely to catch this.
- Build safety: run C# tests with `-c Debug` (the `%AppData%` `DeployToRhino`
  target is `Release`-gated; Debug skips it). Watch for the "Deployed Rook.rhp"
  tripwire (must not appear).

## Files touched

- `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`
  (new internal exception; `FalApiTransport.Key()` + publisher throw it).
- `src/Rook/Services/Reconstruction/ReconstructionErrorMapping.cs`
  (remediation `const` + `MissingCredentialFailure()` factory).
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`
  (three ordered catches → factory).
- `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`
  (submit/poll/cancel real-edge tests).
- `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`
  (transport unit test).

## Verification target

Full Debug C# suite green + 17/17 MCP reconstruction parity green. No Vision files
touched; no `GenerationErrorCode` change.
