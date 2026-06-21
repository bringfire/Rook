# Rename `DisposeVideoSubsystemIfCreated` → `DisposeCreatedSubsystems`

**Date:** 2026-06-20
**Type:** Lifecycle naming clarity (behavior-neutral rename)
**Branch:** `codex/rename-created-subsystem-disposal` (off `origin/main`)

## Problem

`RookSubsystemRoot.DisposeVideoSubsystemIfCreated()` is named as if it only
disposes the video subsystem. It no longer does. The method:

1. **Atomically marks the root disposed** via
   `Interlocked.CompareExchange(ref _disposed, 1, 0)`. After it returns, *every*
   subsystem accessor (`Video`, `ImageJobs`, `MediaImports`, `Reconstruction`)
   throws `ObjectDisposedException` — not just `Video`.
2. **Disposes whichever lazy subsystem bundles were created** — image jobs,
   media imports, video, and reconstruction — each guarded by its own
   `Lazy<T>.IsValueCreated` check.

The `Video`-specific name predates the image-job, media-import, and
reconstruction subsystems being folded into the same shutdown pass. It misleads
readers about both what gets disposed and the root-close side effect.

## Decision

Rename to **`DisposeCreatedSubsystems`**.

- Drops the false `Video` specificity.
- Accurately names the disposal work: it disposes lazy subsystems that were
  created.
- Does not over-claim a new lifecycle contract the way `ShutdownSubsystems`
  would. This is a rename, not a lifecycle redesign.
- Short enough to keep call sites readable.

Rejected: `DisposeLazySubsystemsIfCreated` (precise but clunky; the
`IsValueCreated` guards are an implementation detail), `ShutdownSubsystems`
(implies a broader semantic contract).

## Scope

Strictly mechanical rename. **No** restructuring of the disposal block, **no**
change to `Interlocked.CompareExchange`, **no** change to which lazy values are
checked, **no** change to exception swallowing or disposal ordering.

### Source (2 files)
- `src/Rook/RookSubsystemRoot.cs`
  - Method declaration `DisposeVideoSubsystemIfCreated()` → `DisposeCreatedSubsystems()`.
  - `<see cref="DisposeVideoSubsystemIfCreated"/>` in the `Video` accessor doc
    comment → new name.
  - Refresh the method `<summary>`. The current first line ("Dispose the video
    subsystem if it was ever built") is now inaccurate. New lead line, restrained
    and factual, with the body remaining the source of truth for *which*
    subsystems:

    > Atomically marks the root disposed and disposes any lazy subsystem bundles
    > that were created.

    The existing idempotency / late-caller / production-lifecycle-only paragraphs
    are retained verbatim.
- `src/Rook/RookPlugin.cs`
  - `OnShutdown` call site.
  - The `<item>` doc-comment reference.

### Tests (2 files)
- `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs` — two literal
  source-assertion strings that pin the exact `OnShutdown` call text. Must change
  in lockstep with the call site or the assertions fail.
- `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs` — all call
  sites plus two test-method names
  (`DisposeVideoSubsystemIfCreated_BeforeBuild_DoesNotForceBuild`,
  `DisposeVideoSubsystemIfCreated_RepeatedCalls_AreIdempotent`).

### Out of scope
- `docs/superpowers/plans/*.md` — historical plan records of shipped PRs. Frozen
  artifacts; not code or live comments. Left unchanged to preserve accurate
  history.
- No shared `MediaDownloader` extraction. No `ReplaceJsonBlob` reconciliation.
  No behavior changes of any kind.

## Verification

- `rg "DisposeVideoSubsystemIfCreated"` → only the historical `docs/superpowers/plans/*.md` hits remain.
- `rg "DisposeCreatedSubsystems"` → only the declaration, call site, comments, and tests.
- Focused: lifecycle source-assertion + video subsystem factory tests.
- Full Debug C# suite: `dotnet test src\Rook.Tests\Rook.Tests.csproj -c Debug`.
- Tripwire: `"Deployed Rook.rhp"` must NOT appear in Debug test output.
- MCP parity not required (pure C# lifecycle rename; no Python touched).
