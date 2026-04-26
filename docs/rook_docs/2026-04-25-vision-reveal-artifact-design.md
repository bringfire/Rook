# Per-Image "Show in Folder" Affordance — Design

**Date:** 2026-04-25
**Status:** Approved (post-Codex review, three rounds)
**Type:** Design doc (precedes implementation plan)
**Scope:** RookVision Gallery modal — per-image file-reveal affordance
**Source:** Promoted to Now in `work-queue.md` 2026-04-25 (was item (2) of the 2026-04-24 fix-it triage)

---

## Summary

Add a **Show in Folder** button to the RookVision Gallery modal that opens Windows Explorer with the modal's currently-displayed image file highlighted via `explorer.exe /select,<absolute-path>`. The op is artifact-scoped and role-explicit: the client passes the role it already chose for the modal preview (`pickDisplayRole`), the server resolves that role's blob path through `ArtifactStore.GetBlobAbsolutePath`, and Explorer is invoked with `/select,` to highlight the specific file.

The existing global `Open artifacts folder` button (op `open_artifacts_folder`) stays unchanged. The two ops have a clean semantic distinction: one opens the artifact root, the other reveals one specific blob.

---

## Context

The RookVision Gallery modal currently exposes two per-image actions: **Approve** and **Delete**. Users have asked for a third — a way to open the OS file manager pointed at the image they're viewing, so they can copy it elsewhere, inspect it externally, or audit the artifact directory.

The infrastructure required is fully shipped:

- `VisionHandler.OpenArtifactsFolder` ([VisionHandler.cs:1387-1414](../Rook/src/Rook/Handlers/VisionHandler.cs#L1387-L1414)) demonstrates the off-UI shell-out pattern.
- `ArtifactStore.GetBlobAbsolutePath(id, role)` provides path canonicalization plus directory-escape rejection (PR #99 substrate).
- `VisionWebSurface.OpRoutes` ([VisionWebSurface.cs:126](../Rook/src/Rook/UI/Vision/VisionWebSurface.cs#L126)) is the established op-allowlist surface (`internal static readonly IReadOnlyDictionary<string, VisionOpRoute>`); new ops add one entry plus rejection cases in the dispatcher guards (`Dispatch` for sync UI-thread, `DispatchOffUi`, `DispatchAsync`).
- `VisionHandler.RequireArtifactId` ([VisionHandler.cs:1426](../Rook/src/Rook/Handlers/VisionHandler.cs#L1426)) handles the standard Guid-from-args validation.

This design pass deliberately differentiates the new affordance from the global one rather than reusing it: opening the artifact root is not the same intent as "show me where *this* image lives," and `/select,` is the correct shell pattern for the latter.

---

## Goals

- One-click reveal of the modal's currently-displayed image file in Windows Explorer.
- Role-explicit request shape — server never re-guesses which file to reveal; client passes the same role it used for `pickDisplayRole`.
- Inherit the existing path-traversal protection from `ArtifactStore.GetBlobAbsolutePath`.
- Visible failure mode for missing artifact files; do not silently fall back to opening the parent directory (artifact-integrity problems should surface, not be masked).
- Visual + keyboard parity with the existing modal action row.

## Non-goals

- macOS / Linux file-reveal — Vision is Windows-only via Rhino; cross-platform path is hypothetical until that constraint changes.
- A generic file-reveal op accepting an arbitrary path — security profile is much wider, no current consumer.
- Renaming or restructuring `open_artifacts_folder` — kept as-is. The two ops have a clean semantic distinction.
- Toast notification on success — modal already has the user's eyes on the image; success is implicit when Explorer opens.
- Cross-platform abstraction for the shell-out helper — `BuildRevealFileStartInfo` ships Windows-only and is named accordingly.

---

## Naming surface

| Layer | Name |
|-------|------|
| Bridge op | `reveal_artifact_file` |
| C# method | `RevealArtifactFile` |
| Helper | `BuildRevealFileStartInfo` |
| UI button label | `Show in Folder` |
| Tooltip / `aria-label` / `title` | `Show this image file in its artifact folder` |
| HTML element id | `modal-reveal-btn` |

The op name is deliberately semantic ("reveal a file") rather than implementation-bound ("open select-flag explorer"). If the underlying shell-out ever changes (Finder, Nautilus, custom resolver) the op name does not become wrong.

---

## Design decisions

### Bridge contract

**Op:** `reveal_artifact_file`
**Route:** off-UI (`VisionOpRoute.OffUi`) — same lane as `open_artifacts_folder`. No Rhino UI thread interaction; threadpool-offloaded so a slow shell launch doesn't stall Rhino.

**Request:**
```json
{
  "op": "reveal_artifact_file",
  "artifact_id": "<guid>",
  "role": "image"
}
```

**Success response:**
```json
{ "path": "<absolute-path>", "opened": true }
```

**Failure modes** (see *Exception mapping* below for the full table):

- Missing or non-string `artifact_id` → `ArgumentException` (existing pattern via `RequireArtifactId`).
- Missing or empty `role` → `ArgumentException`.
- Role not present in artifact manifest, or the manifest references a file that no longer exists on disk → structured error with message `Image file is no longer available on disk.`
- Path canonicalization rejects an escape (manifest integrity violation) → structured error surfacing the real exception message; do not mask.

### Server side (`src/Rook/Handlers/VisionHandler.cs`)

New method `RevealArtifactFile(args)` mirroring `OpenArtifactsFolder`'s shape:

- Off-UI dispatcher entry. Returns `ApiResponse`.
- Validates `artifact_id` via existing `RequireArtifactId(args)` helper.
- Validates `role` via either a new `RequireNonEmptyString(args, "role")` helper or inline (decision deferred to implementation plan; helper makes sense if a second caller appears, otherwise inline).
- Resolves the absolute path via `ArtifactStore.GetBlobAbsolutePath(id, role)`. Path canonicalization and directory-escape rejection are inherited.
- Wraps the resolved path in a `ProcessStartInfo` via the new `BuildRevealFileStartInfo` helper, then `Process.Start`s it.
- Returns `{ path, opened: true }`.

### Shell-out helper

New static helper, sibling to `BuildOpenFolderStartInfo`:

```csharp
internal static ProcessStartInfo BuildRevealFileStartInfo(string filePath)
    => new()
    {
        FileName = "explorer.exe",
        Arguments = $"/select,\"{Path.GetFullPath(filePath)}\"",
    };
```

The intent is to use Explorer's `/select,` flag directly — `FileName = "explorer.exe"` plus the `/select,` argument is the canonical Windows pattern for highlighting a specific file. The helper exists separately from `BuildOpenFolderStartInfo` rather than as a parameter on the existing one to keep call sites unambiguous (no boolean argument deciding folder-vs-file behavior). `UseShellExecute` defaults are left to the runtime; behavior is unchanged with either setting because we are passing `FileName` + `Arguments` directly.

### Exception mapping

`ArtifactStore.GetBlobAbsolutePath` can raise multiple exception types. They map to user-facing error envelopes as follows:

| Exception | Cause | UI message | Notes |
|-----------|-------|------------|-------|
| `KeyNotFoundException` | Artifact id not present, or role not present in manifest | `Image file is no longer available on disk.` | Treat as artifact-integrity issue from user perspective. |
| `FileNotFoundException` | Manifest references a blob path that does not exist on disk | `Image file is no longer available on disk.` | Same UX message — distinct cause, identical user remediation. |
| `InvalidDataException` | Manifest blob path escapes the artifact directory | Real exception message, surfaced verbatim in structured error envelope | Security-significant; do not mask under a generic message. Indicates manifest tampering or a bug. |
| `ArgumentException` (from `RequireArtifactId` / role validation) | Bad request shape | Real exception message | Bridge contract violation; client bug. |

The first two share a UX message because the user's recovery action is identical: the file isn't there, regenerate or move on. The third is preserved verbatim because hiding it would conceal an integrity violation under cover of a benign-sounding message.

### Op-allowlist plumbing (`src/Rook/UI/Vision/VisionWebSurface.cs`)

- Add `["reveal_artifact_file"] = VisionOpRoute.OffUi` to `OpRoutes`.
- Add `"reveal_artifact_file"` to the rejection chains in `VisionHandler.Dispatch` (the sync UI-thread dispatcher) and `VisionHandler.DispatchAsync` so misrouted calls return structured failure rather than dispatcher mis-routing. The op's home is `VisionHandler.DispatchOffUi`.
- Op count: 14 → 15.

### Client side (`src/Rook/UI/Vision/Resources/`)

**`index.html` — modal-actions row, between Approve and Delete:**

```html
<div class="modal-actions">
    <button id="modal-approve-btn" class="btn btn-secondary">…Approve</button>
    <button id="modal-reveal-btn" class="btn btn-secondary"
            title="Show this image file in its artifact folder"
            aria-label="Show this image file in its artifact folder">
        …icon… Show in Folder
    </button>
    <button id="modal-delete-btn" class="btn btn-secondary btn-danger">…Delete</button>
</div>
```

Button placement preserves the existing convention: Approve leftmost (positive primary), Delete rightmost (destructive, anchored by existing `btn-danger` styling). The new button uses plain `btn-secondary` styling — same visual weight as Approve, no danger or primary treatment. If the row gets tight on narrow docked panels, the actions wrap rather than shrinking labels into illegibility (`.modal-actions { flex-wrap: wrap }` if not already present).

**`app.js`:**

- New module-level `modalDisplayRole = null;` parallel to `modalArtifact`.
- In `openArtifactModal`, store the role: assign immediately after the existing `pickDisplayRole(modalArtifact)` call.
- In `closeModal`, reset to `null`.
- New handler `revealCurrentArtifact()`: guards against null `modalArtifact` / `modalDisplayRole`, calls `bridgeCall("reveal_artifact_file", { artifact_id, role })`, surfaces errors via existing `showStatus(message, "error")` mechanism.
- Wire in `init()` block: `el.modalRevealBtn.addEventListener("click", revealCurrentArtifact);`.

### Error UX

A failed reveal (missing role, missing file, integrity violation) surfaces via the existing `showStatus(message, "error")` mechanism in `app.js`. The modal stays open so the user can still Approve / Delete if those remain meaningful. No silent fallback to opening the parent directory — the design choice here is that artifact-integrity problems should be visible, not masked.

### Tests

Tests use real fixtures, not mocks — `ArtifactStore` is concrete with no mocking seam, so handler tests construct a temp artifact root and write real manifest files for each scenario. The shell helper is unit-tested without launching Explorer.

**`VisionHandlerTests` additions (real-fixture):**
- Successful reveal: temp artifact root + manifest with one image-role file, assert returned `path` matches `Path.GetFullPath(expected)` and `opened == true`.
- Missing `artifact_id`: omitted / non-string / empty → `ApiResponse` failure.
- Missing `role`: omitted / non-string / empty → `ApiResponse` failure.
- Role not present in manifest: temp artifact with manifest listing only `thumbnail`, request `role: "image"` → failure with `Image file is no longer available on disk.`
- File missing on disk: manifest lists role but the blob has been removed → same UX message.
- Path-traversal manifest: hand-crafted manifest pointing outside artifact directory → real `InvalidDataException` message surfaced.

**`VisionHandlerTests` shell-helper unit:**
- `BuildRevealFileStartInfo(absolutePath)` returns a `ProcessStartInfo` with `FileName == "explorer.exe"` and `Arguments` containing `/select,` followed by the quoted absolute path. No `Process.Start` invocation in tests.

**`VisionWebSurfaceTests` op-routing regression:**
- Op count assertion: 14 → 15.
- Dispatcher mis-routing: `reveal_artifact_file` in UI dispatcher → reject; in async dispatcher → reject.
- Op-route map entry pin: `OpRoutes["reveal_artifact_file"] == VisionOpRoute.OffUi`.

**Embedded-resource HTML test (if existing test pattern checks button presence):**
- Assert `modal-reveal-btn` element exists in `index.html`.

---

## Estimated scope

~6 files, ~150-250 LOC including tests, single squashable commit. Similar shape to PR #102's installer fix bundle. Files touched:

- `src/Rook/UI/Vision/VisionWebSurface.cs` (op-route map + dispatcher rejection cases)
- `src/Rook/Handlers/VisionHandler.cs` (`RevealArtifactFile` + `BuildRevealFileStartInfo`)
- `src/Rook/UI/Vision/Resources/index.html` (modal button)
- `src/Rook/UI/Vision/Resources/app.js` (state + handler + wiring)
- `src/Rook/UI/Vision/Resources/styles.css` (only if `flex-wrap: wrap` needs adding to `.modal-actions`)
- Tests under `src/Rook.Tests/` — `VisionHandlerTests` + `VisionWebSurfaceTests`

Single Codex review round expected post-implementation; the design pass already absorbed three rounds of corrections.

---

## Review history

This design doc reflects three rounds of Codex review during the brainstorming pass:

**Round 1** (approach + role-explicitness):
- Affirmed approach A (`/select,` over directory-only).
- Required role-explicit request shape — client passes the role it already used for `pickDisplayRole`, server does not re-guess.
- Required explicit error UX over silent fallback for missing files.

**Round 2** (op naming + helper shape):
- Locked `reveal_artifact_file` as the op name on semantic-action grounds (not shell-implementation-bound).
- Pinned the full naming surface (handler, helper, UI label, tooltip, ARIA).
- Confirmed `BuildRevealFileStartInfo` as a sibling helper, not a parameter on the existing builder.
- Affirmed `open_artifacts_folder` stays unchanged — clean semantic distinction.

**Round 3** (testing seam + exception mapping + helper framing):
- Corrected test description to use real fixtures rather than implying a mock seam that doesn't exist.
- Required explicit exception mapping table — `KeyNotFoundException` and `FileNotFoundException` map to the user-facing message; `InvalidDataException` (traversal) surfaces verbatim because hiding it would mask integrity violations.
- Softened the shell-helper framing: `FileName + Arguments` to pass `/select,` directly is the contract; `UseShellExecute` is an implementation detail.

---

## Out of scope (deferred to implementation plan)

- Whether `RequireNonEmptyString` becomes a shared helper or stays inline — depends on whether a second caller emerges in the same PR.
- Exact icon glyph for the button (likely the existing folder-with-arrow SVG pattern from elsewhere in the panel).
- Whether `.modal-actions` already has `flex-wrap: wrap` — verify during implementation, add if missing.
- Whether to bundle a `flex-wrap: wrap` cleanup with adjacent narrow-panel work or scope it strictly to the reveal feature.

These are not design decisions — they are implementation details to be settled during the writing-plans phase.
