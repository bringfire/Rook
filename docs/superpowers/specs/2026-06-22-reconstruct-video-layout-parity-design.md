# Reconstruct Tab — Video-Layout / Queue Parity — Design

**Date:** 2026-06-22
**Status:** Approved
**Base:** origin/main `655ef4e5`. Worktree `.worktrees/reconstruct-layout-parity`, branch `feature/reconstruct-video-layout-parity`.

## Problem

The Reconstruct tab works but its page layout is a single vertical stack (form → result → "Recent jobs" list). The RookVision **Video** tab has a more mature pattern: a two-column composition with the creation/work area on the left and a dedicated **queue rail on the right** (filter chips with counts, summary, clickable rows with per-row actions). This slice brings Reconstruct into structural + interaction parity with the Video tab — a **behavior-preserving UI/layout refactor**. No backend, provider, or native changes.

## Scope

**In scope (layout + queue parity for the existing image-to-3D workflow):**
- Two-column Video-style layout (`.reconstruct-layout` grid mirroring `.video-layout`).
- Result/import panel **stays in the main (left) column**.
- Right queue rail with filter chips (**Active / Complete / Failed / All**) + live counts + filter summary.
- Queue rows show `state · short-id · model · stage`; failed rows show error copy.
- **Open/Load** affordance on completed rows → loads result into the main-column result panel.
- **Cancel** on `queued`/`running` rows via the existing `cancel_job` op; `cancellation_requested` shows a disabled "Canceling…".

**Out of scope (hard boundaries):**
- No provider expansion, no text-to-3D wiring, no multi-view wiring, no prompt-mode backend changes.
- **No prompt/input-mode scaffold** — no disabled prompt textarea, no hidden prompt field, no Image/Text switch. Prompt UI arrives with the provider/task-expansion slice when text-to-3D is actually wired.
- No native import changes, no second importer, no WebView HTTP (Pattern A only).
- No host/panel-lifecycle changes (`RookVisionPanel`, `VisionTab`, WebView init, presentation reconciler).
- No new backend op, no change to `ReconstructionOpHandler`, no C# changes.

## Why Reconstruct keeps its result in the main column (vs Video)

Video routes a completed job to the Gallery modal (an **Open** button) because video playback already lives there. Reconstruct's result is reconstruction-specific — resolved import role, `warnings[]`, Available assets / Catalog preferred / Import will use, and the **Import to Rhino** button. That state has no Gallery home, so parity here means *structure + queue interaction*, not Video's "open elsewhere." Clicking a completed queue row loads the result into the left-column result panel (the existing `job_result` → `renderResult` path).

## Layout composition

Mirror `.video-layout` (CSS grid `minmax(0, 1.4fr) minmax(0, 1fr)`, `gap: var(--space-4)`, collapses to one column at `max-width: 1024px`).

```
.reconstruct-layout (grid: 1.4fr | 1fr)
├── .reconstruct-main (left cell, flex column)
│   ├── .panel.reconstruct-form-panel
│   │   ├── .panel-header  (.panel-number "01" + .panel-title "Generate")
│   │   ├── source field   (#reconstruct-source-* , #reconstruct-choose-source)
│   │   ├── model select   (#reconstruct-model-select)
│   │   ├── Textured/Geometry segmented (#reconstruct-mode-textured / -geometry)
│   │   ├── submit          (#reconstruct-submit-btn)
│   │   └── status          (#reconstruct-status-message)
│   └── .panel.reconstruct-result-panel   (#reconstruct-result-panel, hidden until result)
│       ├── result meta      (#reconstruct-result-meta)
│       ├── warnings         (#reconstruct-result-warnings)
│       └── import           (#reconstruct-import-btn / #reconstruct-import-status)
└── .panel.reconstruct-queue-panel (right cell)
    ├── .panel-header (.panel-number "02" + .panel-title "Queue" + refresh icon #reconstruct-refresh-jobs)
    ├── #reconstruct-queue-filters    (chip group — NEW cached id)
    │   └── button.reconstruct-queue-filter[data-queue-filter] × 4, each with .reconstruct-queue-filter-count
    ├── #reconstruct-queue-filter-summary  (NEW cached id)
    └── #reconstruct-jobs-list        (existing id, restyled to queue rows)
```

The view-header (`Reconstruct` title/subtitle) is unchanged. The form controls are unchanged — only their container chrome changes (now inside a `.panel` with a `.panel-header`).

## ID strategy (panel-dark discipline)

The dark-panel failure mode is an init-time JS exception from a cached `$("id")` whose element is missing. To minimize that surface:

- **Reuse** all existing cached IDs: `reconstruct-source-thumb`, `reconstruct-source-label`, `reconstruct-choose-source`, `reconstruct-model-select`, `reconstruct-mode-textured`, `reconstruct-mode-geometry`, `reconstruct-submit-btn`, `reconstruct-status-message`, `reconstruct-result-panel`, `reconstruct-result-thumb`, `reconstruct-result-meta`, `reconstruct-result-warnings`, `reconstruct-import-btn`, `reconstruct-import-status`, `reconstruct-jobs-list`, `reconstruct-refresh-jobs`.
- **New cached IDs: exactly two** — `reconstruct-queue-filters` (chip group) and `reconstruct-queue-filter-summary`.
- Everything else uses **event delegation + data-attributes + scoped `querySelector`**:
  - Filter chips: `button.reconstruct-queue-filter[data-queue-filter="active|complete|failed|all"]`; one delegated click listener on `#reconstruct-queue-filters`.
  - Counts: `.reconstruct-queue-filter-count` spans, updated by scoped `querySelector` within each chip.
  - Row buttons: `.reconstruct-queue-cancel` / `.reconstruct-queue-open` with `data-id`, one delegated click listener on `#reconstruct-jobs-list` (the existing list already has a delegated click handler — extend it).

Every cached ID above must exist in `index.html`. The panel-dark gate enforces this after every JS checkpoint.

## State → filter mapping

Reconstruction job states (serialized): `queued`, `running`, `cancellation_requested`, `cancelled`, `complete`, `error`, `interrupted`.

| Chip | States counted/shown |
|------|----------------------|
| **Active** | `queued`, `running`, `cancellation_requested` |
| **Complete** | `complete` |
| **Failed** | `error`, `interrupted` |
| **All** | every job, including `cancelled` |

`cancelled` is **All-only** — terminal but not a failure; not counted under Failed, and there is no separate Cancelled chip in this slice. Define a single `JS` source of truth: `const ACTIVE_STATES = new Set(["queued","running","cancellation_requested"])`, `FAILED_STATES = new Set(["error","interrupted"])`; Complete = `state === "complete"`; All = no filter.

Counts are computed from the full job list each render. The filter summary echoes the active view, e.g. `Showing N active` / `Showing N complete` / `Showing N failed` / `Showing N jobs`.

## Per-row actions

Rows render `state · short-id (job_id.slice(0,8)) · model · stage`; a failed row also renders `error.message`.

- **Cancel** (`.reconstruct-queue-cancel`): rendered/enabled only when `state ∈ {queued, running}`. On click: disable the button, call `cancel_job {job_id}`, then re-`loadJobs`. **No optimistic removal.** When `state === "cancellation_requested"`, render a disabled `Canceling…` indicator instead of a Cancel button.
- **Open/Load** (`.reconstruct-queue-open`): rendered when `state === "complete"` and `result_artifact_id` present. On click: existing `openJobResult(job_id)` → `job_result` → `renderResult` into the main-column result panel.

`cancel_job` is an existing async reconstruction op (already exposed via `rhino_2d_to_3d_cancel`). Exposing it in the rail is a UI affordance over existing backend behavior — no new backend.

## Filter state across refresh / submission

- The selected filter **persists** across `loadJobs` refreshes (manual refresh or poll-driven). Counts update; the active chip stays selected.
- **On submit:** switch the active filter to **Active** before/right after the job is created, so the just-submitted in-flight job is visible in the rail (perceived responsiveness). This is the one place the filter changes automatically.
- Default filter on first view-enter: **Active**.

## CSS approach

Add `.reconstruct-layout`, `.reconstruct-main`, and reconstruct-scoped queue classes (`.reconstruct-queue-panel`, `.reconstruct-queue-filters`, `.reconstruct-queue-filter`, `.reconstruct-queue-filter-count`, `.reconstruct-queue-filter-summary`, `.reconstruct-queue-row`, `.reconstruct-queue-row-*`) mirroring the Video equivalents in look. Reuse the shared `.panel` / `.panel-header` / `.panel-number` / `.panel-title` rules verbatim (no duplication). Remove the now-obsolete `.reconstruct-body` / `.reconstruct-history*` rules that the refactor replaces. Use only existing CSS custom properties (`var(--…)`); the panel-dark gate scans for undefined tokens.

## Preserved behavior (unchanged)

Gallery "Send to 3D" handoff; explicit model selection; Textured/Geometry mode; submit→poll→`job_result`; `warnings[]` rendered by code; result summary (Available assets / Catalog preferred / Import will use); Import-to-Rhino + response-driven copy; click-completed-to-load. All reconstruction bridge calls stay on the `"reconstruction"` channel.

## Test strategy

This is an HTML/CSS/JS refactor of an embedded resource; there is no JS unit harness, so verification is the **panel-dark gate** plus the existing C# regression suite (backend untouched) plus a live smoke.

**Panel-dark gate — mandatory and BLOCKING after every JS checkpoint:**
1. `node --check src/Rook/UI/Vision/Resources/app.js` — clean.
2. Duplicate-ID scan in `index.html` — empty.
3. Every cached `$("id")` in the Reconstruct module exists in `index.html` (and the only new ones are the two queue IDs).
4. Dangling-reference grep — no reference to a removed symbol/id (e.g. old `.reconstruct-body`, `reconstruct-history` cache).
5. No undefined CSS custom properties introduced.

A failed gate is a **blocker**, not a cleanup item.

**Regression:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` stays green (backend unchanged).

## Live-smoke requirement (merge gate)

Managed Release build/deploy of `src/Rook/Rook.csproj` (Rhino closed for the `.rhp` copy; embedded web assets). Then with Rhino open:
- Reconstruct tab shows the two-column layout; result/import panel in the main column.
- Right rail shows filter chips with correct counts; switching chips filters rows; `cancelled` appears only under **All**.
- Submit a textured Hunyuan run → filter auto-switches to **Active**, the new job is visible; **Cancel** works on the in-flight job (disables, then refreshes; no optimistic removal).
- A completed job's **Open/Load** loads the result into the main-column panel; Import to Rhino still works with response-driven copy.

## Files touched

- `src/Rook/UI/Vision/Resources/index.html` — restructure the Reconstruct `<section>` into the two-column layout + queue rail markup (2 new IDs).
- `src/Rook/UI/Vision/Resources/app.js` — Reconstruct module: cache 2 new IDs, add filter state + delegated chip/row handlers, count/summary rendering, queue-row rendering with Cancel/Open, submit→Active filter switch. Preserve all existing behavior.
- `src/Rook/UI/Vision/Resources/styles.css` — add `.reconstruct-layout` + queue classes; remove obsolete `.reconstruct-body`/`.reconstruct-history*`.
