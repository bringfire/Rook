# Studio Image-Processing (Background Removal) — Design Spec

**Date:** 2026-06-23
**Status:** Approved design — pending spec review gate
**Author:** Claude (brainstormed with reviewer)
**Scope owner:** RookVision / Studio tab

---

## 1. Goal

Expose the already-shipped background-removal capability (`fal-ai/birefnet/v2`,
op `remove_background`) in the Vision UI by giving Studio a small **Operations**
group, plus a **Pick from Gallery** source path, so Studio becomes a light
"image processing" tab without rewriting its generation flow. Make the derived
`preprocessed_image` outputs first-class: visible in Gallery and sendable to 3D.

This is the first, deliberately-bounded slice. It ships the capability
end-to-end while keeping the surface minimal.

## 2. Architecture

**Pattern A (in-process JS bridge), UI-only.** No native plugin changes, no new
C++ route, no new C# reconstruction route, no catalog change. All work lands in
the managed companion's owned UI resources:

- `src/Rook/UI/Vision/Resources/index.html`
- `src/Rook/UI/Vision/Resources/app.js`
- `src/Rook/UI/Vision/Resources/styles.css`
- Tests in `src/Rook.Tests/UI/Vision/` (source-assertion / panel-dark regression tests)

Background removal is a **Reconstruction job**, not an ImageJob. Studio drives it
via the existing `reconstructionBridgeCall(op, args)` helper, which internally
invokes the `"reconstruction"` bridge domain — the same domain Reconstruct uses.
Studio adds no new bridge channel; it reuses the established ops (call shape is
`reconstructionBridgeCall("remove_background", { … })`, not a positional domain
argument):

| Op (bridge) | Use |
|-------------|-----|
| `remove_background` | async submit; returns a job envelope `{ job_id, state, … }` |
| `job_status` | poll until terminal; carries `result_artifact_id` on completion |
| `job_result` | (optional) full result envelope; `result_artifact_id` is sufficient here |

A completed `remove_background` job materializes a derived `preprocessed_image`
artifact (roles `image` + `mask`), **linked to the source; the source is never
mutated**. Its id surfaces as `result_artifact_id` on the job envelope.

### Backend already functions — no change required

`fal-ai/birefnet/v2` is `enabled: true` (status `experimental`). The handler's
`RemoveBackgroundAsync` → `ResolveRemoveBackgroundModel("")` resolves the *first
enabled* `remove_background` model, so the op works today. `experimental` only
gates visibility in the 3D-model picker (`ProducesImportable3D`), which does not
apply here. Flipping BiRefNet to `stable` is **optional polish at the live gate**,
not a functional requirement, and is out of scope unless explicitly added.

## 3. Components & data flow

### 3.1 Studio source acquisition — Pick from Gallery

- **index.html:** a **Pick from Gallery** button in the source-control row beside
  Load Image / Capture Depth / Clear.
- **app.js — `studioPickFromGallery()`:** opens a **Studio-local** picker modal
  (modeled on the Reconstruct picker pattern; **not** an extracted shared helper).
  Lists image-like artifact kinds via parallel `bridgeCall("list_artifacts", …)`:
  - `generated_image`
  - `imported_image`
  - `captured_viewport`
  - `preprocessed_image`

  Selecting a cell calls the existing Studio source path verbatim:

  ```js
  applyStudioSource({
      source: "artifact",
      artifact_id: a.artifact_id,
      role: "image",
      previewSrc: `/blob/${encodeURIComponent(a.artifact_id)}/image?ts=${Date.now()}`,
      label: a.kind,
  });
  ```

- The Studio picker modal must use **its own scoped ids and close handlers** so it
  does not collide with existing Gallery / Video (`ve.pickerModal`) / Reconstruct
  modals. (Panel-dark constraint — see §5.)

### 3.2 Operations group — Remove Background

- **index.html:** an **Operations** group beneath the source preview, containing a
  **Remove Background** button and an op status strip.
- **app.js — `studioRemoveBackground()`:**
  1. Guard: requires an artifact-backed source. If `!hasStudioSourceImage()` or the
     source lacks `artifact_id`, do not submit.
  2. `reconstructionBridgeCall("remove_background", { source_artifact_id, source_role: "image" })`.
  3. Poll `reconstructionBridgeCall("job_status", { job_id })` until terminal,
     surfacing states in the strip (queued / submitting / polling / materializing /
     complete / cancelled / error) using the reconstruction status vocabulary.
  4. On `complete`, read `result_artifact_id` (the `preprocessed_image`).
- **Enablement:** the Remove Background button is **disabled with the hint
  "Load or pick a source image first"** until `studioSource.artifact_id` exists.
  Path-only / legacy-transient sources are treated as not-ready — **no
  auto-materialize** (YAGNI). Enablement is recomputed whenever the source changes
  (`applyStudioSource` / `clearStudioSource`).

### 3.3 Result surface — reuse the existing Studio result panel

Background removal **reuses Studio's existing result panel**, not a second
competing surface. On completion it:

- sets `latestStudioArtifactId = result_artifact_id`,
- sets `studioResultImage.src = /blob/{id}/image?ts=…`,
- reveals `studioResultPanel`,
- shows success in the op status strip.

**Operation-aware title/actions (required).** The existing panel is hardcoded
`<h3 class="result-title">Generated</h3>` with `Approve` (`studio-approve-btn`) and
`New Generation` (`studio-new-btn`). Reusing it for background removal MUST NOT
leave misleading "Generated" / "New Generation" copy around a background-removed
result. The panel's title and action set must be operation-aware: for the
background-removal operation, the title reflects the operation (e.g.
"Background removed") and the actions are the three reuse actions below — the
generation-specific `New Generation` action is hidden (and `Approve` reused or
hidden as appropriate). The implementation may parameterize the panel's
title/action rendering or swap an operation-specific action row; either way no
stale generation copy may surround a processed result.

Three **result-reuse actions** are offered on the result:

1. **Use as source** → `applyStudioSource({ source:"artifact", artifact_id: result_artifact_id, role:"image", previewSrc, label:"background removed" })`. Enables chaining (a `preprocessed_image` is itself a valid source kind).
2. **Open in Gallery** → `switchView("gallery")`, `await loadGallery()`, then `openArtifactModal(result_artifact_id)` — opens/focuses the produced artifact, not just the tab.
3. **Send to Reconstruct** → fetch the full artifact (`bridgeCall("get_artifact", { artifact_id })`) so it carries `kind` + `files[role="image"]`, then `Reconstruct.presetSource(artifact)`. (A bare id is insufficient — `presetSource` / `canReconstructArtifact` inspect kind and files.)

### 3.4 Gallery — list and reconstruct `preprocessed_image`

- **app.js — `loadGallery()` (the gallery grid loader, ~L1232 only):** add a 5th
  parallel `bridgeCall("list_artifacts", { kind: "preprocessed_image", limit: 100 })`
  and merge it into the existing sorted grid. **Do not** touch the Video frame
  picker (~L2698) or Settings/overview counts — those are out of scope for this
  spec and are not "Gallery listing."
- **app.js — `canReconstructArtifact()`:** add `preprocessed_image` so the gallery
  modal's **Send to 3D** button lights up for background-removed outputs. This
  closes the existing inconsistency where the Reconstruct picker already lists
  `preprocessed_image` but the gallery modal could not send it.

### 3.5 Data flow summary

```
source artifact (generated/imported/captured/preprocessed)
  → studioRemoveBackground()
  → reconstructionBridgeCall("remove_background")   [reconstruction job, async]
  → poll job_status …
  → result_artifact_id = preprocessed_image (image + mask, linked to source; source untouched)
  → reuse Studio result panel  +  Use-as-source / Open-in-Gallery / Send-to-Reconstruct
```

## 4. Error / edge handling

- **No source artifact:** button disabled + hint; never submits.
- **Terminal job states:** surfaced in the op status strip; errors render structured
  text via `errorToText` (field-prefixed), consistent with Studio generate.
- **Provider / credential failure:** surfaced like Studio generate's structured
  error path.
- **Chaining:** re-running Remove Background on a `preprocessed_image` is allowed
  (valid source kind).
- **Picker empty / load failure:** show the standard empty/error state inside the
  Studio picker grid; never throw out of the click handler.

## 5. Panel-dark (WebView/presentation) mitigations — FIRST-CLASS ACCEPTANCE CRITERION

This spec is **not** "just HTML/JS." Every UI change must preserve the RookVision
WebView/presentation safety invariants. These are acceptance criteria, not
cosmetic niceties:

1. **Id integrity:** every new `$("id")` cached in `app.js` MUST have a matching
   element in `index.html`. A missing id nulls the cache entry and can blank the
   entire panel at init.
2. **Tolerant wiring:** event wiring must tolerate optional elements
   (`el.x?.addEventListener(…)` / `if (el.x)` guards) where appropriate. **No
   uncaught init-time exceptions.**
3. **No bypass:** no direct WebView HTTP and no bypass of the established bridge
   channels. All new ops route through `bridgeCall` / `reconstructionBridgeCall`.
4. **Routing rules:** respect the async vs off-UI routing rules in
   `VisionWebSurface.cs` / the reconstruction dispatch (`remove_background`,
   `job_status` are already correctly classified — Studio only consumes them).
5. **Modal scoping:** the new Studio picker modal's close handlers and query
   selectors must be scoped so they do not collide with existing Gallery / Video /
   Reconstruct modals (unique ids, no global `.modal` selector reuse that would
   cross-close another modal).
6. **Panel-dark regression tests:** add/adjust source-assertion tests that catch
   **missing ids, route omissions, and unsafe init wiring** — treated as
   panel-dark regression tests. At minimum assert: every new cached id exists in
   index.html; `studioRemoveBackground` routes through
   `reconstructionBridgeCall("remove_background")`; the picker lists the four kinds;
   `loadGallery` includes `preprocessed_image`; `canReconstructArtifact` includes
   `preprocessed_image`.
7. **Final panel-dark verification step (plan closeout):** run the relevant
   Vision/WebView source tests; after deployment, if possible exercise the
   presentation diagnostics/repair path (`rhino_vision_presentation` /
   `get_presentation_diagnostics` / `repair_presentation`) to confirm the panel
   composits.

## 6. Testing strategy

- **Source-assertion / panel-dark tests** in `src/Rook.Tests/UI/Vision/`
  (`ReconstructScaffoldSourceTests.cs` and/or `VisionWebSurfaceTests.cs`, matching
  where Studio/Reconstruct scaffold tests already live). Assertions per §5.6.
- **No backend tests required** (no backend change). If BiRefNet is optionally
  flipped to `stable` at the live gate, that is a separate one-line change with its
  own catalog test and is out of this spec.
- **Live gate (closeout, manual):** one BiRefNet background-removal roundtrip in
  Rhino through the Studio Operations group: load/pick a source → Remove Background
  → verify `preprocessed_image` result renders in the Studio result panel, appears
  in Gallery, and Send-to-Reconstruct presets it. Then run the §5.7 panel-dark
  verification.

## 7. Scope boundaries

**In scope:**
- Studio Operations group with Remove Background (artifact-backed source required).
- Studio-local Pick-from-Gallery source picker (four image kinds).
- Reuse of the existing Studio result panel + three result-reuse actions.
- `loadGallery()` lists `preprocessed_image`.
- `canReconstructArtifact()` accepts `preprocessed_image` (gallery modal Send-to-3D).
- Panel-dark mitigations + regression tests (§5).

**Explicitly out of scope (future specs):**
- Gallery-modal "Remove Background" action.
- Generalized operation framework / registry / descriptor on the UI side.
- Generate MV3D Views (top/left/right/bottom/etc.) workflow.
- Shared picker extraction (defer until a genuine 3rd consumer forces rule-of-three).
- BiRefNet in the Studio image-generation model dropdown.
- Settings/overview count changes for `preprocessed_image`.
- BiRefNet `experimental` → `stable` flip (optional, separate).

## 8. Open risks / notes

- `Reconstruct.presetSource` requires a full artifact object (kind + `files`
  with role `image`); Send-to-Reconstruct must `get_artifact` first, not pass a id.
- Studio gets a **focused local poller** for the reconstruction job; the existing
  reconstruction poll lives inside the Reconstruct IIFE and is not reached into.
- Capture-Depth-sourced artifacts: kind is not asserted here; the picker lists the
  four agreed kinds regardless of what depth capture is classified as.
