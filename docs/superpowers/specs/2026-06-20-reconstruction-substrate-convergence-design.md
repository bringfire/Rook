# Reconstruction 2D-to-3D — Substrate Convergence Design

Date: 2026-06-20
Branch: `codex/reconstruction-2d-to-3d` (worktree `.worktrees/reconstruction-2d-to-3d`)
Supersedes nothing; hardens the implementation of
[`2026-06-19-reconstruction-2d-to-3d-design.md`](2026-06-19-reconstruction-2d-to-3d-design.md).

## Goal

Converge the Reconstruction 2D-to-3D subsystem's **fal / media / job primitives** onto
RookVision's proven generation substrate, fixing seven confirmed robustness gaps — **without**
a UI/native/MCP rewrite and **without** modifying already-shipped Vision code.

This is a behavioral/semantic convergence at the substrate layer, **not** a product-domain
merge. Reconstruction keeps its own domain: routes, package model, import path, ledger record
shape, and MCP tool surface.

## Background: why this pass exists

An audit (two independent passes — Claude + Codex, corroborated) found that Reconstruction
correctly reuses fal **transport** (`FalApiClient`) and **secrets**
(`DpapiGenerationSecretStore` + `GenerationSecretKeys.FalApiKey`), but **re-implemented the
mid-level fal queue contract** instead of reusing the shared mappers. The shared
`FalErrorMapper` / `FalLifecycleMapper` are called **0×** in Reconstruction versus **7× / 5×**
in the Vision fal providers. This is the root of the "pulling from fal.ai was difficult" pain:
fal failures collapse into an opaque `InvalidOperationException` → `poll_failed` / `submit_failed`,
losing retry/quota/auth discrimination.

Baseline at design time: **55 C# reconstruction tests + 17 MCP tests pass.** This pass hardens
working code; it does not rescue broken code. All new behavior must be pinned by tests, and the
existing green suites must stay green.

## Confirmed gaps (the problem set)

| # | Gap | Severity |
|---|-----|----------|
| 1 | Fal error/lifecycle hand-rolled; mappers unused; bare `InvalidOperationException` on non-2xx → opaque `poll_failed`/`submit_failed` | High |
| 2 | Source bytes via `File.ReadAllBytes(absolutePath)` + MIME-from-extension; bypasses the resolver pattern; recouples provider to storage | High |
| 3 | Lazy on-demand poll only; no background loop; no startup reconcile | Med-High |
| 4 | Downloader: `GetByteArrayAsync` sync-over-async, whole-file-into-memory, no cap/retry/streaming; third standalone `HttpClient` | Med |
| 5 | Package can be marked `Complete` with no model asset (metadata-only) if provider JSON drifts | Med (correctness) |
| 6 | Duplicate outcome unions / `IReconstructionProvider` parallels `IGenerationProvider` primitives | Architecture/maintainability |
| 7 | `ReplaceJsonBlob` (Task 1) duplicated across the worktree (committed) and main (uncommitted) | Process hygiene |

## Decision: convergence depth = B (substrate convergence)

Considered alternatives:

- **A — Surgical robustness only.** Fix the gaps in place, keep the parallel provider/manager/
  ledger shapes. Rejected: patches symptoms while preserving the duplicate fal/job/materialization
  semantics that caused the drift. Two provider contracts to maintain forever.
- **C — Full Generation-modality adoption.** Implement `IGenerationProvider<TRequest,TCapability>`,
  retire all reconstruction-specific provider types. Rejected for now: overfits the single-artifact
  image/video abstraction onto a multi-asset reconstruction package, and churns the most green code.
- **B — Substrate convergence (chosen).** Converge the fal/media/job **primitives** in behavior and
  semantics; keep Reconstruction's product domain. Reuse shared outcome/envelope primitives; keep a
  reconstruction-specific provider **interface** only where package semantics genuinely differ.

## Scope boundary

**Changes:** `FalReconstructionProvider`, `ReconstructionJobManager`,
`ReconstructionPackageMaterializer`, a new `ReconstructionRemoteAssetDownloader`, source
resolution, startup reconcile wiring (`RookSubsystemRoot`), and the provider/outcome types.

**Untouched:** native `/reconstruction/2d-to-3d/*` routes, the hybrid import route, MCP
`rhino_2d_to_3d_*` tools, the `reconstruction_package` / `import_manifest` schema, the ledger
state/stage vocabulary, and the Vision materializers/providers.

## Workstreams

### W0 — Pre-req: resolve the `ReplaceJsonBlob` duplication

Two divergent implementations of the package/import-history JSON-replace primitive exist (worktree
committed; main uncommitted). The plan must **compare both versions, choose the canonical one, and
incorporate that canonical version into the reconstruction worktree**. This is in-pass, not a
separate chore: divergent implementations of the same import-history primitive are exactly the
checkout fragmentation this pass exists to stop.

**Do not revert main's uncommitted changes** as part of this pass. Main is a separate working tree
with the user's in-progress edits; cleaning up main's copy (if it turns out to be the non-canonical
one) is a separate, explicit action taken only when directed — never an automatic revert here.

Minor (P4): move `ReplaceJsonBlobResultCode` / `ReplaceJsonBlobResult` beside `AppendBlobResult` in
`Artifact.cs` for consistency.

### W1 — Fal queue substrate

`FalReconstructionProvider` calls the injected `FalApiClient` directly and uses the shared mappers
inline, exactly as `FalVideoProvider` / `FalImageProvider` do:

- submit handle via `FalLifecycleMapper.ParseSubmitHandle`
- status via `FalLifecycleMapper.MapStatus`
- every non-2xx via `FalErrorMapper.MapHttpFailure`

It returns the shared `ProviderSubmitOutcome` / `ProviderStatusOutcome` / `ProviderResultOutcome`.
The throwing `FalReconstructionQueueClient` / `IFalReconstructionQueueClient` seam is removed.

**Invariants:** no fal HTTP failure becomes a generic `InvalidOperationException`; the
**COMPLETED-is-terminal-not-success** doctrine is honored — success/failure is adjudicated at the
result-fetch step, not at status.

### W2 — Source resolution

The job manager pre-resolves the source artifact to **bytes + MIME** before the provider uploads;
the provider no longer calls `File.ReadAllBytes` and no longer infers MIME from file extension.
Path refs are rejected (artifact-only, per the existing submit contract).

The hard requirement is the contract, not a specific class dependency:

- bytes/MIME are resolved (via a resolver/validator adapting the `ArtifactOnlyVideoMediaResolver`
  concept) **before** provider upload, and
- upload uses `FalApiClient.UploadFileToCdnAsync` with the same lifecycle/header discipline
  (`FalUploadPlatformHeaders`).

Reusing `FalSourceFrameTransport` is acceptable, but Reconstruction must **not** be forced to depend
on video-specific internals if accessibility or naming is awkward — a small reconstruction source
publisher that follows the same upload contract is fine.

### W3 — Result envelope

`FetchResultAsync` parses the fal result JSON into the shared `ProviderResultEnvelope` carrying
multiple role'd `ResultArtifact`s, each with a `RemoteArtifactBody(url)`, declared MIME/content-type
when available, and provider metadata (filename / content-type / original key). Roles: `model_glb`,
`model_obj`, `material_mtl`, `texture_*`, `thumbnail`, etc.

`ReconstructionPackageMaterializer` becomes **provider-agnostic**: it consumes the envelope and must
not know fal field names (`model_urls`, `texture_urls`, `model_glb`); it knows only Rook package
roles and invariants. The sanitized raw fal result JSON is still materialized as
`provider_result_json`, but as a **diagnostic sidecar**, not operational input.

Provider-side result parsing is tested against both Hunyuan- and Meshy-shaped payloads.

### W4 — Download discipline

New `ReconstructionRemoteAssetDownloader` (kept under Reconstruction, cleanly extractable for a
future shared helper):

- async; cancellation-aware; **no sync-over-async**
- `HttpCompletionOption.ResponseHeadersRead` streaming
- **role-aware** byte cap enforced from the `Content-Length` header **and** while streaming
  (models may be larger than thumbnails/textures)
- retry **transient only** — 5xx, 408, 429, transport/timeout — and **never** retry validation
  failures (e.g. 404) or cancellation
- returns a typed materialization/reconstruction failure, never a raw `InvalidOperationException`
- `HttpMessageHandler` / client injected for tests (no network in unit tests)

This pass does **not** extract a shared `MediaDownloader` from the Vision materializers (that would
churn green Vision code for no immediate product gain). A later shared extraction — with golden
parity tests around image/video first — is a separate scoped change.

### W5 — Package invariant

`ReconstructionPackageMaterializer` validates a hard invariant: **at least one importable model role**
(`model_glb` or `model_obj`) must be present. If none is, materialization returns a typed failure and
the job becomes **`Error`** — never a metadata-only `Complete` package.

### W6 — Execution model (background poll + reconcile)

Adopt the Vision execution shape:

- per-job detached `Task.Run(RunJobAsync)` kicked at submit
- `SemaphoreSlim`-bounded concurrency
- a poll loop with `Task.Delay(interval)` between in-flight polls
- `StatusAsync` may still opportunistically drive a poll, but it is no longer the **only** progress
  driver

**Lifecycle / shutdown / disposal (required).** Background `Task.Run` work must not outlive the
plugin. Mirror Vision's lifecycle discipline:

- the manager owns a manager-wide shutdown `CancellationTokenSource` linked into every job's poll
  loop and download
- running jobs are tracked (e.g. a registry of in-flight tasks)
- the manager is disposable; **disposal on plugin unload cancels active jobs** and awaits/abandons
  them deterministically, leaving no orphaned background work in the Rhino process
- a job cancelled by shutdown lands in a non-terminal-safe state (its ledger record is left such that
  startup reconcile will mark it `Interrupted`)

Tested where practical (e.g. dispose mid-poll cancels the loop and stops further transitions).

**Single-flight / race discipline (required).** Because `StatusAsync` may poll while the background
loop is also polling, every job needs a **per-job gate** (the existing per-job lock), and any code
path that may fetch the result or materialize the package must **re-read the ledger record after
acquiring the lock** and bail if the job already advanced. The invariant is absolute: **exactly one
terminal transition and exactly one package materialization per job**, regardless of how many
pollers race.

**Startup reconcile semantics (explicit):** on startup, non-terminal ledger jobs are marked
**`Interrupted`** (mirroring Vision's `ReconcileInterruptedJobs`), wired into `RookSubsystemRoot`.
There is **no automatic remote resume** in this pass. Provider job id / status / cancel URLs are
preserved on the ledger record so an explicit cancel/status path can deal with remote leftovers.
Automatic remote resume is a larger design and is **out of scope** here.

W6 is sequenced last because it depends on the W1/W7 outcome semantics and the W3/W5 materialization-
failure behavior; building the loop before those would risk building it around the wrong abstractions.

### W7 — Outcome-union reuse

Reuse the shared primitives: `ProviderJobHandle`, `ProviderSubmitOutcome` /
`ProviderStatusOutcome` / `ProviderResultOutcome` (and leaves), `GenerationError` /
`GenerationErrorCode`, `ProviderResultEnvelope` / `ResultArtifact` / `ArtifactBody`. Retire the
duplicate **internal** types `ReconstructionProviderSubmitResult`, `ReconstructionProviderStatusResult`,
and `ReconstructionProviderLifecycleState`.

Keep a reconstruction-specific **`IReconstructionProvider`** interface only (the submit-request
semantics genuinely differ) — **not** the `IGenerationProvider<TRequest,TCapability>` generic.

**Public failure DTO is preserved.** `ReconstructionFailure` is the reconstruction **HTTP response
envelope shape** and is retained. `GenerationError` is mapped **into** `ReconstructionFailure` at the
handler/manager boundary. This keeps the native/MCP failure contract (`code` / `message` /
`retryable` / `field` / `details`) stable — consistent with the "no native/MCP rewrite" boundary.

## Error-handling philosophy

Every fal/HTTP boundary yields a typed `GenerationError` (code + retryable + detail) or a typed
materialization failure. The manager records ledger `Error` with that typed reason — never an opaque
`poll_failed` / `submit_failed`. The handler maps the typed failure into the `ReconstructionFailure`
response envelope. No sync-over-async; no bare exceptions crossing the fal/HTTP boundary.

## Testing strategy

New behavior is pinned by tests, not just happy-path route tests:

- **Provider:** fal 401/403/422/429/5xx → typed `GenerationErrorCode` + correct `retryable`
  (honoring `x-fal-needs-retry`); submit-handle parse; status lifecycle mapping
  (IN_QUEUE / IN_PROGRESS / COMPLETED / FAILED / CANCELLED); COMPLETED-is-terminal-not-success
  (HTTP 422 at fetch → failure); Hunyuan- **and** Meshy-shaped result → envelope roles.
- **Source resolver:** artifact → bytes/MIME; path ref rejected.
- **Downloader:** header-cap exceeded; stream-cap exceeded; empty body; 404 no-retry; 500 retry;
  timeout/transport retry; cancellation no-retry.
- **Materializer:** no-model envelope → typed failure (job `Error`); multi-asset envelope → correct
  blobs/roles; `provider_result_json` sidecar preserved.
- **Manager:** background poll drives a job to `Complete`; interrupted-job reconcile on startup marks
  non-terminal jobs `Interrupted` and preserves provider job id/URLs; **single-flight** — a
  background poll and a concurrent `StatusAsync` racing a near-terminal job produce exactly one
  terminal transition and one materialization; **shutdown** — disposing the manager mid-poll cancels
  the loop and stops further transitions (no orphaned background work).
- **Regression:** existing 55 C# + 17 MCP tests stay green.

## Substrate trajectory

This pass is a deliberate slice on the way to a fuller fal-roundtrip substrate, not the whole thing.
Naming the staircase so the next iteration doesn't re-litigate it:

- **What becomes substrate now (convergence by consumption):** the fal-semantics layer —
  `FalApiClient` + `FalLifecycleMapper` + `FalErrorMapper`, the secret store, and the shared
  outcome/envelope primitives (`ProviderJobHandle`, `Provider*Outcome`, `ProviderResultEnvelope` /
  `ResultArtifact`). After this pass it has **two domains / three modalities** consuming it
  identically (image, video, reconstruction). The "pulling from fal was hard" bind lived entirely in
  this layer and cannot recur in code that calls these mappers.

- **What stays "shared pattern, not shared code" (by the B-over-C choice):** the orchestration layer
  — job manager, ledger, materializer, downloader. Each modality still writes this boilerplate
  against the proven shape. This is the low-risk duplication (known pattern) rather than the
  high-risk duplication (subtle fal queue semantics) that hurt us.

- **Why not extract the orchestration substrate now:** rule of three. Extracting a generic
  job-runner / shared `MediaDownloader` / the `IGenerationProvider<TRequest,TCapability>` generic
  from a single example (Vision) is how you get an abstraction that fits image/video and then fights
  reconstruction's multi-asset package. This pass makes reconstruction a clean **second conforming
  consumer** and mandates the new downloader expose an extractable interface — which de-risks a later
  extraction by validating the abstraction's shape empirically.

- **The gated follow-up:** once this lands, an "extract shared generation-job substrate" change
  (shared download discipline, shared submit→poll→materialize runner, possibly the generic provider
  interface *if it fits all three*) becomes a low-churn lift with golden parity tests. That is the
  point at which a new fal roundtrip feature really is "write the provider + request/result shape,
  get the rest for free." It is **out of scope here** and gated on a third consumer / the next fal
  feature.

## Non-goals (YAGNI guard)

- No `IGenerationProvider<TRequest,TCapability>` adoption (that is option C).
- No shared `MediaDownloader` extraction from the Vision materializers (follow-up only).
- No UI / native / MCP contract rewrite unless a contract change forces it.
- No new ledger state/stage vocabulary.
- No automatic remote job resume (separate larger design).

## Slicing

Implementation order (final boundaries decided in the plan):

`W0 → W1 + W7 → W2 → W3 + W4 + W5 → W6`

- **W0** — `ReplaceJsonBlob` dedup + `Artifact.cs` tidy.
- **W1 + W7** — fal substrate + outcome-union reuse (naturally paired; the mappers return the shared
  outcome types).
- **W2** — source resolution.
- **W3 + W4 + W5** — materializer cluster: result envelope, download discipline, no-model invariant.
- **W6** — background execution + startup reconcile.

Each slice carries its pinned tests and keeps the existing suites green.

## Verification (baseline commands)

```
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore
pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```

Native build is verified separately and is not part of unit verification.
