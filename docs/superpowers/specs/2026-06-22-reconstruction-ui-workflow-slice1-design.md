# Reconstruction 2D→3D — RookVision UI Workflow (Slice 1) Design

**Date:** 2026-06-22
**Status:** Approved design, ready for implementation plan
**Base:** `origin/main` @ `5fa48b28` (worktree `.worktrees/reconstruction-ui`, branch `feature/reconstruction-ui-workflow-slice1`)
**Related backend:** PR #285 (substrate), #298 (`model_id` required), #301 (D1 submit guard), #305 (D2/D3 result warnings)

---

## 1. Problem & framing

A **v0 reconstruction path already exists** inside the RookVision surface on `origin/main`. It is a gallery-modal shortcut, not a workflow:

- **Bridge (C#):** a dedicated `"reconstruction"` bridge channel registered in `VisionWebSurface.cs:344`, routed by `HandleReconstructionBridgeCallAsync` (`VisionWebSurface.cs:505`). Async ops `submit_job/job_status/cancel_job` → `RookSubsystemRoot.Instance.Reconstruction.DispatchAsync`; off-UI ops `models/list_jobs/job_result` → `DispatchOffUi`. Import ops are intentionally unwired.
- **UI (`index.html`):** one hidden gallery-modal button `modal-reconstruct-btn` ("Send to 3D", line 780) and one status strip `modal-reconstruction-status` (line 784).
- **UI (`app.js`):** `canReconstructArtifact()`, `reconstructCurrentArtifact()` (submit **hardcoded** to `fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d` + `{enable_pbr:true, enable_geometry:false}`), `pollReconstructionJob()`, `setReconstructionStatus()`.

**Three concrete deficiencies** this slice fixes:
1. **No model or options choice** — model and PBR/geometry flags are hardcoded in the modal submit.
2. **Warnings are ignored** — `setReconstructionStatus(msg, type, result)` receives the full `result` but uses only `result_artifact_id`. `result.warnings[]` (the entire D2/D3 backend deliverable: `result_artifact_missing`, `pbr_unsupported_by_model`, `result_missing_texture`) is dropped on the floor.
3. **No way back to a completed package** — a job runs ~60–90 s; if the user closes the modal or switches views, the package is unreachable. `list_jobs` is wired in the bridge but unused.

**This slice is a promotion, not a green-field build.** We turn the v0 modal shortcut into a first-class, RookVision-consistent **Reconstruct** view, with **one** submit path.

## 2. Goal (one sentence)

Promote the existing v0 gallery-modal reconstruction affordance into a first-class **Reconstruct** view in the RookVision surface that supports explicit model selection, a textured-vs-geometry-only control, submit/poll, a result-package panel that renders `result.warnings[]`, a lightweight job history, and an import **handoff** — reusing the existing `"reconstruction"` bridge channel.

## 3. Scope

### In scope (Slice 1)
- New **Reconstruct** nav view (6th, beside Generate/Studio/Video/Gallery/Settings).
- **Source artifact selection** (an existing image artifact; reuses Vision's artifact currency).
- **Model selection** via `models`, explicit required pick (no hidden default).
- **Textured ↔ geometry-only** segmented control → emits `{enable_pbr:true}` xor `{enable_geometry:true}`, never both.
- **Submit → poll → result package panel.**
- **Warnings display** from `result.warnings[]` by code.
- **Lightweight job history** via `list_jobs` (recent jobs, state/stage/result_available, click a completed job → `job_result`, refresh button).
- **Import handoff only** (package id / asset roles / preferred asset + clear handoff copy; **no** native import button).
- **"Send to 3D" gallery-modal button becomes a shortcut** that preselects the artifact and navigates to the Reconstruct view — its hardcoded inline submit path is removed.
- **Bridge hardening:** bring reconstruction async bridge ops under the same `AsyncOpTimeout` wrapper Vision/Video use.

### Out of scope (explicitly deferred)
- **One-click Rhino import.** The actual `_-Import` orchestration lives in native C++ (`ImportExportHandler.cpp:352`, route `POST /reconstruction/2d-to-3d/import`); a `connect-src 'none'` WebView cannot reach it and the bridge does not expose it. Separate slice.
- **Three.js GLB preview.** Slice 1 uses thumbnail + asset-role list + metadata. (Substrate rules name 2D→3D review a good first Three.js use; revisit when the view feels weak without it.)
- **Cost/estimate modal.** No backend `estimate` op exists; submit is unconditional. (Standard "spends provider credits" copy only, if RookVision already uses that language.)
- **`preprocessing_chain`** (backend rejects non-empty in v0).
- **`cancel_job` UI.** Wired in the bridge but no cancel button this slice unless it falls out trivially. (Decision: omit; revisit with import slice.)

## 4. Architecture

**Extend the existing Vision surface; do not fork.** Reconstruction keeps its **own** `"reconstruction"` bridge channel (already present) — we do not move it into the `"vision"` `OpRoutes` table. The new view is added to the same `index.html`/`app.js`/`styles.css` trio and the same `VisionWebSurface` host. This preserves one surface, one security model (in-process Pattern A, `connect-src 'none'`), one artifact store, one blob virtual-host.

```
Reconstruct view (index.html section + app.js controller)
        │  window.rookBridge.invoke("reconstruction", {op, ...})
        ▼
VisionWebSurface.HandleReconstructionBridgeCallAsync   (existing channel; + AsyncOpTimeout)
        │
        ▼
RookSubsystemRoot.Instance.Reconstruction  (ReconstructionOpHandler — shared singleton)
        │   models · submit_job · job_status · job_result · list_jobs
        ▼
ReconstructionJobManager / ModelCatalog / ArtifactStore
```

Blob assets (thumbnail, model roles) are served by the existing `/blob/{artifact_id:D}/{role}` virtual resource from the shared `ArtifactStore` — reconstruction packages are artifacts in that same store. **Verify** during implementation that `/blob/{package_id}/thumbnail` and `/blob/{package_id}/model_glb` resolve (role regex `^[a-z0-9][a-z0-9_-]*$` permits these names).

## 5. Components

### 5.1 C# — bridge timeout hardening (`VisionWebSurface.cs`)
`HandleReconstructionBridgeCallAsync` currently calls `DispatchAsync(body, CancellationToken.None)` for `submit_job/job_status/cancel_job` with **no** timeout, unlike Video (`DispatchVideoAsyncWithTimeoutAsync` → `DispatchWithTimeoutAsync(op, AsyncOpTimeout, …)`).

**Decision:** wrap the three reconstruction async ops under the same `AsyncOpTimeout` (180 s) pattern used by Vision/Video, so a hung provider call rewrites to a structured timeout failure instead of hanging the bridge. Off-UI ops (`models/list_jobs/job_result`) keep `Task.Run → DispatchOffUi` unchanged. This is a consistency fix, not a feature; it is the one C# change in the slice and the one place with a focused unit test.

### 5.2 Web UI — new Reconstruct view (`index.html`, `app.js`, `styles.css`)

**Layout (top to bottom):**
1. **Source panel** — selected source image (thumbnail + label) with a "Choose image…" affordance that opens the existing gallery picker filtered to reconstructable kinds (`generated_image | imported_image | captured_viewport` with a file role `image`, per `canReconstructArtifact`). When arrived via "Send to 3D", this is preselected.
2. **Model select** — `<select>` populated by `models`; empty/placeholder default forces an explicit choice (backend requires `model_id`; there is no implicit default). Show model id and, where present, `supports_pbr` as an advisory note.
3. **Output control** — a **segmented control** Textured | Geometry-only. Mutually exclusive. Textured → `options:{enable_pbr:true}`; Geometry-only → `options:{enable_geometry:true}`. Never emits both (the D1 backend guard would reject it; the UI makes it unrepresentable).
4. **Submit button** + status strip (reuse `.status-message` conventions).
5. **Result package panel** (shown on completion) — package id, `asset_roles[]`, `preferred_asset_role`, thumbnail via `/blob/{package_id}/thumbnail`, source/result metadata, and the **warnings list** (§5.3), and the **import handoff** (§5.4).
6. **Job history panel** (§5.5).

**Controller (`app.js`):** a `reconstruct`-view module mirroring the Video controller shape — `loadReconstructView()`, `loadReconstructionModels()`, `submitReconstruction()`, reuse `pollReconstructionJob()` (generalized off the modal), `renderReconstructionResult(result)`, `renderReconstructionWarnings(result.warnings)`, `loadReconstructionJobs()`. Reuse `reconstructionBridgeCall`, `errorToText`, `showStatus`, `delay`, `escapeHtml`, `formatTimestamp`.

### 5.3 Warnings rendering (the mandatory deliverable)
On `job_result`, render `result.warnings[]` (array of `{code, message, details}`) as a visible list in the result panel. **Read by code; never infer degradation from raw `asset_roles`.**

| code | human copy (UI) | severity |
|---|---|---|
| `result_artifact_missing` | "The reconstruction completed but its package could not be found. The result may be unavailable; try re-running." | error |
| `pbr_unsupported_by_model` | "Textured output was requested, but this model isn't catalogued as supporting textured/PBR output. The result may have no materials." | warning |
| `result_missing_texture` | "Textured output was expected and this model supports it, but the delivered package contains no material or texture assets." | warning |

Unknown future codes render with their backend `message` verbatim (forward-compatible). Each warning shows its `message` as the source of truth; the table above is the friendly headline per known code. When `warnings[]` is empty, render nothing (no "no warnings" chrome).

### 5.4 Import handoff (deferred one-click)
Replace the leaked literal `Import via /reconstruction/2d-to-3d/import` string. The result panel shows the package id, asset roles, and preferred asset, plus handoff copy directing the user to import via the agent / MCP tool (`rhino_2d_to_3d_import`). No native import button this slice. A "copy package id" affordance is acceptable if cheap.

### 5.5 Job history (lightweight)
A panel listing recent jobs from `list_jobs` (default limit is fine):
- rows show job id (short), state, stage, `result_available`, updated_at;
- a **refresh** button re-calls `list_jobs`;
- clicking a row with `result_available` loads `job_result` into the result panel (§5.3/5.4);
- no filters unless they fall out trivially from the existing data.

Keep it simple — it is a way back to a finished package, not a job manager.

### 5.6 "Send to 3D" shortcut (remove the duplicate submit path)
The gallery-modal `modal-reconstruct-btn` stops doing its own hardcoded `submit_job`. Instead it: (a) records the modal artifact as the Reconstruct view's preselected source, (b) navigates to the Reconstruct view, (c) closes the modal. The submit then flows through the single Reconstruct-view path with the user's model/options. Delete `reconstructCurrentArtifact()`'s inline submit and the modal-only status plumbing made redundant (`setReconstructionStatus`/`clearReconstructionStatus`/`modal-reconstruction-status`) unless still needed for the gate. Keep `canReconstructArtifact()` (reused for both the modal button gate and the source picker filter).

## 6. Data flow / contracts (from `ReconstructionOpHandler.cs`)
- `models` → `{ models:[{model_id, provider, supports_pbr, output_roles, preferred_asset_role, fallback_order, …}], … }`
- `submit_job` body → `{ source_artifact_id (GUID, required), source_role:"image", model_id (required), preprocessing_chain:[], options:{…}, estimate_requested:false }` → `{ job_id, state, stage, … }`
- `job_status` → `{ job:{…, state, stage}, result_available, warnings:[] }`
- `job_result` → `{ job_id, result_artifact_id, result_available, package:{artifact_id, kind, asset_roles[], preferred_asset_role}, warnings:[{code,message,details}] }`
- `list_jobs` → `{ jobs:[…], warnings:[], applied_limit }`
- Failure DTO (any op) → `{ code, message, retryable, field }` (already unwrapped by `reconstructionBridgeCall`).
- States: `queued · submitting · polling · materializing · complete · error · cancelled · interrupted · cancellation_requested`.

## 7. Error handling
- Bridge/op failures surface via the existing structured-error unwrap in `reconstructionBridgeCall` → `errorToText` (`field: message`).
- Submit validation failures (e.g. missing model) render in the submit status strip; the UI prevents the `enable_pbr`+`enable_geometry` contradiction pre-submit so the D1 guard is a backstop, not the primary UX.
- Poll terminal states `error/cancelled/interrupted` render as an error status; timeout (180 attempts × 1.5 s) renders a timeout status (unchanged from v0).
- Bridge async timeout (§5.1) rewrites a hung provider call to a structured failure.

## 8. Testing strategy
- **C# (xUnit):** focused test(s) for the reconstruction bridge timeout wrapper — assert `submit_job/job_status/cancel_job` route through the `AsyncOpTimeout` path and that an overrunning dispatch yields a structured timeout failure (mirror the existing Video timeout test shape). This is the one mechanically-testable unit; `Rook.Tests` already covers `ReconstructionOpHandler`.
- **JS:** the Vision UI has no JS unit harness; UI behavior is verified manually (consistent with how Generate/Video views are validated). Provide a **manual verification checklist** in the plan: model list loads & forces explicit pick; textured/geometry-only mutual exclusion; Send-to-3D preselects & navigates; submit→poll→result; warnings render for a `result_missing_texture` case (reproducible by submitting geometry-only against a PBR-default model, per D2/D3); job history refresh + click-to-load; blob thumbnail resolves.
- **Blob verification:** confirm `/blob/{package_id}/{thumbnail|model_glb}` serves during manual verification.
- Full `dotnet test -c Debug` green (Debug skips the `%AppData%` deploy; Rhino need not be closed).

## 9. Risks
- **Copying Vision too literally:** Vision's result is a single `<img>`; reconstruction's is a multi-file package + warnings. The result panel is genuinely new structure, not a clone of the Generate result panel.
- **Two submit paths drifting:** mitigated by deleting the modal's inline submit (§5.6) — one path only.
- **Blob route assumption:** if reconstruction package blobs are not served by the existing `/blob` route, the thumbnail degrades to a placeholder; flagged as a verification gate, not a blocker (text/roles/warnings still render).
- **Backend gap (import):** intentionally deferred; the handoff copy sets correct expectations.

## 10. Verify-before-spec-relies-on-it checklist (carried into the plan)
1. `/blob/{package_id}/thumbnail` and a model role resolve from the shared `ArtifactStore`.
2. `models` returns `supports_pbr` / `preferred_asset_role` for display.
3. The Video timeout-wrapper pattern (`DispatchWithTimeoutAsync`) is reusable for reconstruction as-is.
