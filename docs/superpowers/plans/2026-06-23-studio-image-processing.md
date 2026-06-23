# Studio Image-Processing (Background Removal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose background removal (`fal-ai/birefnet/v2`, op `remove_background`) in the Vision UI by adding a Studio Operations group + Pick-from-Gallery source picker, reusing the existing Studio result panel (operation-aware), and making derived `preprocessed_image` artifacts visible in Gallery and sendable to 3D.

**Architecture:** Vision web resources (`index.html`, `app.js`, `styles.css`) plus a one-line managed Vision bridge allowlist/test update (add `remove_background` to the reconstruction async ops). Pattern A (in-process JS bridge): background removal is driven as a *Reconstruction job* over `reconstructionBridgeCall(op, args)` (`"reconstruction"` bridge domain). The reconstruction handler's `RemoveBackgroundAsync` already exists and BiRefNet is already `enabled: true`; **no native route, no backend handler, no catalog change.**

**Tech Stack:** Embedded HTML/CSS/vanilla-JS Vision UI; C# xUnit source-assertion tests (net48) reading embedded resources via `typeof(VisionWebSurface).Assembly.GetManifestResourceStream("Rook.UI.Vision.Resources.<file>")`.

## Global Constraints

- Pattern A. Changes are confined to Vision web resources + a managed Vision bridge allowlist/test update. No new bridge channel; no native (`src/RookNative`), no backend reconstruction handler, no catalog (`fal-model-catalog.json`) change. The ONLY C# change is adding `remove_background` to `VisionWebSurface.ReconstructionAsyncOps` (+ its pinning test).
- All new ops use existing reconstruction op strings verbatim: `remove_background`, `job_status` (and `get_artifact` / `list_artifacts` on the `bridgeCall` domain). Call shape is `reconstructionBridgeCall("remove_background", { … })` — op as first positional arg, NOT a domain argument.
- **Panel-dark (WebView/presentation) safety is a first-class acceptance criterion** (spec §5):
  - Every new `$("id")` cached in `app.js` MUST have a matching `id="…"` element in `index.html`.
  - Event wiring MUST tolerate optional elements (`el.x?.addEventListener` / `if (el.x)`); no uncaught init-time exceptions.
  - The new Studio picker modal's close handlers and selectors MUST be scoped to `studio-picker-modal` (no global `.modal` selectors that could cross-close Gallery/Video/Reconstruct modals).
  - Add source-assertion tests that catch missing ids, route omissions, and unsafe init wiring (panel-dark regression tests, not cosmetic).
- Background removal produces a derived `preprocessed_image` (roles `image` + `mask`) linked to the source; **the source is never mutated**.
- Remove Background requires an **artifact-backed source** (`studioSource.artifact_id`); path-only/transient sources are not-ready (no auto-materialize). Disabled hint copy is exactly: `Load or pick a source image first`.
- No stale "Generated" / "New Generation" copy may surround a background-removed result (operation-aware result panel).
- Out of scope: Gallery-modal Remove Background, operation registry/framework, MV3D view generation, shared picker extraction, BiRefNet in the generation model dropdown, Settings/overview counts, BiRefNet experimental→stable flip.

**Reference facts (verified against current `main`):**
- Vision reconstruction bridge allowlist: `VisionWebSurface.ReconstructionAsyncOps` (`src/Rook/UI/Vision/VisionWebSurface.cs:263-270`) currently `{ submit_job, job_status, cancel_job, import_package }`. `HandleReconstructionBridgeCallAsync` (`:521`) routes async-set ops through `DispatchWithTimeoutAsync(... DispatchAsync ...)`; off-UI ops (`models`/`list_jobs`/`job_result`) via `DispatchOffUi`; anything else → `"Unknown reconstruction op"` (`:549-554`). The async-set pinning test is `VisionWebSurfaceTests.ReconstructionAsyncOps_AreExactly_Submit_Status_Cancel_Import` (`src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs:1588`). The reconstruction handler already implements `remove_background` (`RemoveBackgroundAsync`); only the companion allowlist is missing it.
- Studio element cache block: `app.js:2031-2057`. Studio event wiring: `app.js:2151-2178`.
- Studio source controls markup: `index.html:266-286` (`.source-controls`, buttons `studio-upload-btn` / `studio-capture-depth-btn` / `studio-clear-source`). Source label: `index.html:287`.
- Studio result panel markup: `index.html:395-412` (`result-title` "Generated", `studio-approve-btn`, `studio-new-btn`, `studio-result-image`). `.result-header` is a non-wrapping `space-between` flex row (`styles.css:1353-1361`).
- Studio section closes at `index.html:413` (`</section>`).
- `applyStudioSource(src)`: `app.js:1025`. `clearStudioSource()`: `app.js:1052`. `studioGenerate` reveal sites: `app.js:1136` (sync) and `app.js:1170` (async job).
- Reconstruct picker (pattern to mirror, DO NOT modify): modal `index.html:841-850`; JS `openReconstructPicker` `app.js:3726-3738`; CSS `.reconstruct-picker-grid` / `.reconstruct-picker-cell` `styles.css:2724-2746` (reused as-is).
- Global helpers available at top level: `delay(ms)` (`app.js:526`), `escapeAttr(s)` (`app.js:1987`), `errorToText(e)` (`app.js:81`), `showStudioStatus` / `hideStudioStatus`, `switchView` (`app.js:126`, auto-calls `loadGallery` for "gallery"), `openArtifactModal(id)` (`app.js:1509`, async, uses `get_artifact`), `Reconstruct.presetSource(artifact)` (`app.js:4001`, fills front slot AND calls `switchView("reconstruct")`).
- `job_status` envelope unwrap: `const job = status.job || status;` then read `job.state` and `job.result_artifact_id` (mirrors `app.js:3625-3626`). Terminal states: `complete`, `error`, `cancelled`.
- `bridgeCall("get_artifact", { artifact_id })` returns the artifact object with `.kind`, `.files`, `.artifact_id`.
- Gallery loader to change: `loadGallery()` `app.js:1232-1242` (the 4-kind parallel fetch). `canReconstructArtifact()` `app.js:1594-1601`. DO NOT touch the Video frame picker (`app.js:2698-2705`) or Settings/overview counts.
- Test pattern: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs` — `[Fact]` + `ReadVisionResource("index.html"|"app.js"|"styles.css")` + `Assert.Contains`. Test command: `dotnet test src/Rook.Tests/Rook.Tests.csproj` (rebuilds Rook so edited embedded resources are re-embedded).

---

### Task 1: Managed Vision bridge routing for `remove_background`

The companion WebView bridge (`HandleReconstructionBridgeCallAsync`) has its OWN allowlist, separate from the native trampoline. `remove_background` is network-bound (a Fal job submit) so it belongs in the async set alongside `submit_job`. Without this, every Studio `reconstructionBridgeCall("remove_background", …)` returns `"Unknown reconstruction op"`.

**Files:**
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs:263-270` (add op to `ReconstructionAsyncOps`)
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs:1588-1596` (update the exact-set pin)

**Interfaces:**
- Consumes: existing `DispatchWithTimeoutAsync` + `Reconstruction.DispatchAsync` routing (unchanged).
- Produces: `remove_background` reachable through `reconstructionBridgeCall` under the 180 s async timeout. (Task 4's JS depends on this at runtime.)

- [ ] **Step 1: Update the failing pin test**

In `VisionWebSurfaceTests.cs`, replace the `ReconstructionAsyncOps_AreExactly_Submit_Status_Cancel_Import` test (lines 1588-1596) with:

```csharp
        [Fact]
        public void ReconstructionAsyncOps_AreExactly_Submit_Status_Cancel_Import_RemoveBackground()
        {
            // import_package loops back to the native importer; it MUST be async/off-UI
            // (the deadlock invariant) on this surface. remove_background is a network-bound
            // Fal job submit and is routed through the same async/timeout wrapper as submit_job.
            Assert.Equal(
                new[] { "cancel_job", "import_package", "job_status", "remove_background", "submit_job" },
                VisionWebSurface.ReconstructionAsyncOps.OrderBy(o => o, StringComparer.Ordinal).ToArray());
        }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.ReconstructionAsyncOps_AreExactly"`
Expected: FAIL — actual set lacks `remove_background`.

- [ ] **Step 3: Add `remove_background` to the async allowlist**

In `VisionWebSurface.cs`, change the `ReconstructionAsyncOps` initializer (lines 263-270) to:

```csharp
        internal static readonly HashSet<string> ReconstructionAsyncOps =
            new(StringComparer.Ordinal)
            {
                "submit_job",
                "job_status",
                "cancel_job",
                "import_package",
                "remove_background",
            };
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.ReconstructionAsyncOps"`
Expected: PASS (the exact-set test + `ReconstructionAsyncOps_ExcludeOffUiOps`, which stays valid since `remove_background` is not an off-UI op).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Vision/VisionWebSurface.cs src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(vision): route remove_background through the reconstruction async bridge"
```

---

### Task 2: Pick-from-Gallery source picker

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html` (source-controls button + new picker modal)
- Modify: `src/Rook/UI/Vision/Resources/app.js` (cache ids, picker functions, wiring)
- Create: `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs`

**Interfaces:**
- Consumes: existing `applyStudioSource(src)`, `bridgeCall`, `escapeAttr`, `.reconstruct-picker-grid`/`.reconstruct-picker-cell` CSS.
- Produces: `el.studioPickGalleryBtn`, `el.studioPickerModal`, `el.studioPickerGrid`, `el.studioPickerClose`; functions `openStudioPicker()`, `closeStudioPicker()`, `selectStudioPickerArtifact(artifactId)`; const `STUDIO_SOURCE_KINDS`; module var `studioPickerArtifactsById`. (Task 6 asserts the cached ids exist.)

- [ ] **Step 1: Write the failing test (new test file)**

Create `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs`:

```csharp
using System.IO;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    /// <summary>
    /// Source-assertion (panel-dark regression) tests for the Studio
    /// image-processing slice: Pick-from-Gallery picker, operation-aware
    /// result panel, Remove Background operation, and Gallery eligibility
    /// for preprocessed_image. Structural checks against embedded
    /// HTML/JS/CSS resources — no WebView2 runtime is exercised.
    /// </summary>
    public class StudioImageProcessingSourceTests
    {
        // ─── Task 2: Pick from Gallery ────────────────────────────────

        [Fact]
        public void IndexHtml_PickFromGallery_ControlAndModalPresent()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-pick-gallery-btn\"", html);
            Assert.Contains("id=\"studio-picker-modal\"", html);
            Assert.Contains("id=\"studio-picker-grid\"", html);
            Assert.Contains("id=\"studio-picker-close\"", html);
        }

        [Fact]
        public void AppJs_StudioPicker_CachesIdsAndListsFourKinds()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioPickGalleryBtn = $(\"studio-pick-gallery-btn\");", js);
            Assert.Contains("el.studioPickerModal = $(\"studio-picker-modal\");", js);
            Assert.Contains("el.studioPickerGrid = $(\"studio-picker-grid\");", js);
            Assert.Contains("el.studioPickerClose = $(\"studio-picker-close\");", js);
            Assert.Contains("function openStudioPicker(", js);
            Assert.Contains("function selectStudioPickerArtifact(", js);
            // The four agreed image kinds.
            Assert.Contains("\"generated_image\", \"imported_image\", \"captured_viewport\", \"preprocessed_image\"", js);
            // Picker selection routes through the existing Studio source path.
            Assert.Contains("applyStudioSource({", js);
        }

        // ─── helper ───────────────────────────────────────────────────

        private static string ReadVisionResource(string fileName)
        {
            var asm = typeof(VisionWebSurface).Assembly;
            var resourceName = "Rook.UI.Vision.Resources." + fileName;
            using var stream = asm.GetManifestResourceStream(resourceName);
            Assert.NotNull(stream);
            using var reader = new StreamReader(stream!);
            return reader.ReadToEnd();
        }
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: FAIL — `studio-pick-gallery-btn` / picker ids not yet present.

- [ ] **Step 3: Add the Pick-from-Gallery button to `.source-controls`**

In `index.html`, inside `.source-controls` (after the `studio-clear-source` button block ending at line 285, before the closing `</div>` at line 286), add:

```html
                            <button id="studio-pick-gallery-btn" class="btn btn-capture" title="Pick a source image from the Gallery">
                                <svg viewBox="0 0 24 24" fill="none">
                                    <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                                    <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
                                    <path d="M21 15L16 10L5 21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                                <span>Pick from Gallery</span>
                            </button>
```

- [ ] **Step 4: Add the Studio picker modal**

In `index.html`, immediately before the Studio section close `</section>` (line 413), add the picker modal (scoped ids; reuses the existing picker grid CSS):

```html
                <!-- Studio source picker modal (Studio-local; mirrors the Reconstruct picker pattern) -->
                <div id="studio-picker-modal" class="modal hidden">
                  <div class="modal-backdrop"></div>
                  <div class="modal-content modal-content-picker">
                    <div class="modal-header">
                      <span id="studio-picker-title">Pick a Gallery image</span>
                      <button id="studio-picker-close" class="btn-icon" aria-label="Close">×</button>
                    </div>
                    <div id="studio-picker-grid" class="reconstruct-picker-grid"></div>
                  </div>
                </div>
```

- [ ] **Step 5: Cache the new ids**

In `app.js`, in the Studio cache block, after `el.studioNewBtn = $("studio-new-btn");` (line 2057) add:

```js
    el.studioPickGalleryBtn = $("studio-pick-gallery-btn");
    el.studioPickerModal = $("studio-picker-modal");
    el.studioPickerGrid = $("studio-picker-grid");
    el.studioPickerClose = $("studio-picker-close");
```

- [ ] **Step 6: Add the picker functions**

In `app.js`, immediately after `clearStudioSource()` (ends at line 1064) add:

```js
// ─── Studio: Pick from Gallery ────────────────────────────────────

const STUDIO_SOURCE_KINDS = ["generated_image", "imported_image", "captured_viewport", "preprocessed_image"];
let studioPickerArtifactsById = {};

async function openStudioPicker() {
    if (!el.studioPickerModal || !el.studioPickerGrid) return;
    studioPickerArtifactsById = {};
    el.studioPickerGrid.innerHTML = '<div class="gallery-empty"><span>Loading…</span></div>';
    el.studioPickerModal.classList.remove("hidden");
    try {
        // list_artifacts filters by a SINGLE kind; fan out one call per kind and merge.
        const results = await Promise.all(STUDIO_SOURCE_KINDS.map(
            k => bridgeCall("list_artifacts", { kind: k, limit: 100 }).catch(() => ({ artifacts: [] }))));
        const artifacts = results.flatMap(r => (r && r.artifacts) || []);
        artifacts.forEach(a => { studioPickerArtifactsById[a.artifact_id] = a; });
        el.studioPickerGrid.innerHTML = artifacts.length
            ? artifacts.map(a =>
                `<button class="reconstruct-picker-cell" data-artifact-id="${escapeAttr(a.artifact_id)}"><img src="/blob/${encodeURIComponent(a.artifact_id)}/image" alt="${escapeAttr(a.kind)}"/></button>`).join("")
            : '<div class="gallery-empty"><span>No images yet</span></div>';
    } catch (e) {
        el.studioPickerGrid.innerHTML = '<div class="gallery-empty"><span>Failed to load images</span></div>';
    }
}

function closeStudioPicker() {
    if (el.studioPickerModal) el.studioPickerModal.classList.add("hidden");
}

function selectStudioPickerArtifact(artifactId) {
    const a = studioPickerArtifactsById[artifactId];
    if (!a) return;
    applyStudioSource({
        source: "artifact",
        artifact_id: a.artifact_id,
        role: "image",
        previewSrc: `/blob/${encodeURIComponent(a.artifact_id)}/image?ts=${Date.now()}`,
        label: a.kind,
    });
    closeStudioPicker();
}
```

- [ ] **Step 7: Wire the picker (scoped, guarded)**

In `app.js`, in the Studio wiring block after the `studioClearReferencesBtn` handler (ends line 2178) add:

```js
    el.studioPickGalleryBtn?.addEventListener("click", openStudioPicker);
    el.studioPickerClose?.addEventListener("click", closeStudioPicker);
    el.studioPickerModal?.querySelector(".modal-backdrop")?.addEventListener("click", closeStudioPicker);
    el.studioPickerGrid?.addEventListener("click", (e) => {
        if (!(e.target instanceof Element)) return;
        const cell = e.target.closest(".reconstruct-picker-cell");
        if (cell) selectStudioPickerArtifact(cell.dataset.artifactId);
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && el.studioPickerModal && !el.studioPickerModal.classList.contains("hidden")) {
            closeStudioPicker();
        }
    });
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs
git commit -m "feat(vision): Studio Pick-from-Gallery source picker"
```

---

### Task 3: Operation-aware Studio result panel + reuse actions

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html` (result-panel title id + split action groups)
- Modify: `src/Rook/UI/Vision/Resources/app.js` (cache ids, `setStudioResultMode`, reuse-action functions, wiring, generate sets generate-mode)
- Modify: `src/Rook/UI/Vision/Resources/styles.css` (scoped op-actions wrap — P2 overflow fix)
- Modify: `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs` (add facts)

**Interfaces:**
- Consumes: `latestStudioArtifactId`, `applyStudioSource`, `switchView`, `loadGallery`, `openArtifactModal`, `bridgeCall`, `Reconstruct.presetSource`, `showStudioStatus`, `errorToText`.
- Produces: `el.studioResultTitle`, `el.studioResultGenActions`, `el.studioResultOpActions`, `el.studioUseAsSourceBtn`, `el.studioOpenInGalleryBtn`, `el.studioSendToReconstructBtn`; functions `setStudioResultMode(mode)`, `studioUseResultAsSource()`, `studioOpenResultInGallery()`, `studioSendResultToReconstruct()`. (Task 4 calls `setStudioResultMode("background_removed")`.)

- [ ] **Step 1: Write the failing test**

Append these facts to `StudioImageProcessingSourceTests.cs` (before the `helper` region):

```csharp
        // ─── Task 3: Operation-aware result panel ─────────────────────

        [Fact]
        public void IndexHtml_ResultPanel_HasTitleIdAndSplitActionGroups()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-result-title\"", html);
            Assert.Contains("id=\"studio-result-gen-actions\"", html);
            Assert.Contains("id=\"studio-result-op-actions\"", html);
            Assert.Contains("id=\"studio-use-as-source-btn\"", html);
            Assert.Contains("id=\"studio-open-in-gallery-btn\"", html);
            Assert.Contains("id=\"studio-send-to-reconstruct-btn\"", html);
        }

        [Fact]
        public void AppJs_ResultPanel_IsOperationAware()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioResultTitle = $(\"studio-result-title\");", js);
            Assert.Contains("el.studioResultGenActions = $(\"studio-result-gen-actions\");", js);
            Assert.Contains("el.studioResultOpActions = $(\"studio-result-op-actions\");", js);
            Assert.Contains("function setStudioResultMode(", js);
            // operation-aware copy: background-removed result is titled, not "Generated"
            Assert.Contains("\"Background removed\"", js);
            // generation path explicitly restores generate-mode header/actions
            Assert.Contains("setStudioResultMode(\"generate\")", js);
            // reuse actions exist and route correctly
            Assert.Contains("function studioUseResultAsSource(", js);
            Assert.Contains("function studioOpenResultInGallery(", js);
            Assert.Contains("function studioSendResultToReconstruct(", js);
            Assert.Contains("Reconstruct.presetSource(", js);
            Assert.Contains("openArtifactModal(", js);
        }

        [Fact]
        public void Styles_OpActions_WrapToAvoidOverflow()
        {
            // P2: three reuse buttons must not overflow the non-wrapping result header row.
            var css = ReadVisionResource("styles.css");
            Assert.Contains("#studio-result-op-actions", css);
            Assert.Contains("flex-wrap: wrap", css);
        }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: FAIL — new ids/functions/CSS not present.

- [ ] **Step 3: Update the result-panel markup**

In `index.html`, replace the result header block (lines 397-407) — the `<div class="result-header">` through its closing `</div>` — with:

```html
                    <div class="result-header">
                        <h3 class="result-title" id="studio-result-title">Generated</h3>
                        <div class="result-actions" id="studio-result-gen-actions">
                            <button id="studio-approve-btn" class="btn btn-secondary" title="Mark this image as approved so Rook can use it as the selected concept for downstream workflows." aria-label="Mark this image as approved so Rook can use it as the selected concept for downstream workflows.">
                                <svg viewBox="0 0 24 24" fill="none">
                                    <path d="M5 13L9 17L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                                Approve
                            </button>
                            <button id="studio-new-btn" class="btn btn-primary">New Generation</button>
                        </div>
                        <div class="result-actions hidden" id="studio-result-op-actions">
                            <button id="studio-use-as-source-btn" class="btn btn-secondary">Use as source</button>
                            <button id="studio-open-in-gallery-btn" class="btn btn-secondary">Open in Gallery</button>
                            <button id="studio-send-to-reconstruct-btn" class="btn btn-primary">Send to Reconstruct</button>
                        </div>
                    </div>
```

- [ ] **Step 4: Add the scoped op-actions wrap CSS (P2 overflow fix)**

In `styles.css`, immediately after the `.result-title::before { … }` rule block (the result-panel section near line 1371), add:

```css
/* Studio operation result actions (3 buttons) wrap instead of overflowing
   the non-wrapping result-header row. */
#studio-result-op-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    justify-content: flex-end;
}
#studio-result-op-actions .btn {
    white-space: nowrap;
}
```

- [ ] **Step 5: Cache the new result-panel ids**

In `app.js`, after the `el.studioPickerClose = …` line added in Task 2 (in the Studio cache block) add:

```js
    el.studioResultTitle = $("studio-result-title");
    el.studioResultGenActions = $("studio-result-gen-actions");
    el.studioResultOpActions = $("studio-result-op-actions");
    el.studioUseAsSourceBtn = $("studio-use-as-source-btn");
    el.studioOpenInGalleryBtn = $("studio-open-in-gallery-btn");
    el.studioSendToReconstructBtn = $("studio-send-to-reconstruct-btn");
```

- [ ] **Step 6: Add `setStudioResultMode` and reuse-action functions**

In `app.js`, immediately after `selectStudioPickerArtifact` (added in Task 2) add:

```js
// ─── Studio: operation-aware result panel ─────────────────────────

// Switch the shared Studio result panel between generation and operation
// presentation. For an operation result (e.g. background removal) the title
// reflects the operation and the generation-specific actions ("New Generation")
// are hidden in favor of the result-reuse actions — no stale "Generated" copy.
function setStudioResultMode(mode) {
    const isOp = mode === "background_removed";
    if (el.studioResultTitle) el.studioResultTitle.textContent = isOp ? "Background removed" : "Generated";
    if (el.studioResultGenActions) el.studioResultGenActions.classList.toggle("hidden", isOp);
    if (el.studioResultOpActions) el.studioResultOpActions.classList.toggle("hidden", !isOp);
}

function studioUseResultAsSource() {
    if (!latestStudioArtifactId) return;
    applyStudioSource({
        source: "artifact",
        artifact_id: latestStudioArtifactId,
        role: "image",
        previewSrc: `/blob/${encodeURIComponent(latestStudioArtifactId)}/image?ts=${Date.now()}`,
        label: "background removed",
    });
}

async function studioOpenResultInGallery() {
    if (!latestStudioArtifactId) return;
    const id = latestStudioArtifactId;
    switchView("gallery");
    await loadGallery();
    await openArtifactModal(id);
}

async function studioSendResultToReconstruct() {
    if (!latestStudioArtifactId) return;
    try {
        const artifact = await bridgeCall("get_artifact", { artifact_id: latestStudioArtifactId });
        if (artifact && artifact.artifact_id) Reconstruct.presetSource(artifact);
    } catch (e) {
        showStudioStatus(e.message, "error");
    }
}
```

- [ ] **Step 7: Make the generation path set generate-mode**

In `app.js`, in `studioGenerate` (sync reveal at line 1136), change:

```js
            el.studioResultPanel.classList.remove("hidden");
            showStudioStatus("Image generated.", "success");
```
to:
```js
            setStudioResultMode("generate");
            el.studioResultPanel.classList.remove("hidden");
            showStudioStatus("Image generated.", "success");
```

And in `studioGenerateImageJob` (async reveal at line 1170), change:

```js
        el.studioResultPanel.classList.remove("hidden");
        showStudioStatus("Image generated.", "success");
```
to:
```js
        setStudioResultMode("generate");
        el.studioResultPanel.classList.remove("hidden");
        showStudioStatus("Image generated.", "success");
```

- [ ] **Step 8: Wire the reuse-action buttons (guarded)**

In `app.js`, in the Studio wiring block after the Task 2 picker wiring add:

```js
    el.studioUseAsSourceBtn?.addEventListener("click", studioUseResultAsSource);
    el.studioOpenInGalleryBtn?.addEventListener("click", studioOpenResultInGallery);
    el.studioSendToReconstructBtn?.addEventListener("click", studioSendResultToReconstruct);
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: PASS (5 tests).

- [ ] **Step 10: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs
git commit -m "feat(vision): operation-aware Studio result panel + reuse actions"
```

---

### Task 4: Operations group + Remove Background operation

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html` (Operations group)
- Modify: `src/Rook/UI/Vision/Resources/app.js` (cache, op functions, poll, enablement, wiring; enablement hooks in `applyStudioSource`/`clearStudioSource`)
- Modify: `src/Rook/UI/Vision/Resources/styles.css` (Operations group layout)
- Modify: `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs` (add facts)

**Interfaces:**
- Consumes: `studioSource`, `reconstructionBridgeCall` (now routes `remove_background` — Task 1), `delay`, `errorToText`, `latestStudioArtifactId`, `setStudioResultMode` (Task 3), `el.studioResultImage`, `el.studioResultPanel`.
- Produces: `el.studioOperations`, `el.studioRemoveBgBtn`, `el.studioOperationStatus`; functions `studioRemoveBackground()`, `awaitStudioRemoveBackground(jobId)`, `showStudioOperationStatus(text, kind)`, `updateStudioOperationsEnabled()`.

- [ ] **Step 1: Write the failing test**

Append to `StudioImageProcessingSourceTests.cs`:

```csharp
        // ─── Task 4: Operations group + Remove Background ──────────────

        [Fact]
        public void IndexHtml_OperationsGroup_HasRemoveBackground()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-operations\"", html);
            Assert.Contains("id=\"studio-remove-bg-btn\"", html);
            Assert.Contains("id=\"studio-operation-status\"", html);
            // Ships disabled until an artifact-backed source exists.
            Assert.Contains("id=\"studio-remove-bg-btn\" class=\"btn btn-capture\" disabled", html);
        }

        [Fact]
        public void AppJs_RemoveBackground_RoutesAndGatesOnArtifactSource()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioRemoveBgBtn = $(\"studio-remove-bg-btn\");", js);
            Assert.Contains("el.studioOperationStatus = $(\"studio-operation-status\");", js);
            Assert.Contains("function studioRemoveBackground(", js);
            Assert.Contains("function awaitStudioRemoveBackground(", js);
            Assert.Contains("function updateStudioOperationsEnabled(", js);
            // routes through the reconstruction bridge op (correct call shape)
            Assert.Contains("reconstructionBridgeCall(\"remove_background\", {", js);
            Assert.Contains("reconstructionBridgeCall(\"job_status\", { job_id:", js);
            // artifact-backed gating + exact disabled hint copy
            Assert.Contains("studioSource && studioSource.artifact_id", js);
            Assert.Contains("Load or pick a source image first", js);
            // success drives the operation-aware result panel
            Assert.Contains("setStudioResultMode(\"background_removed\")", js);
            // enablement is recomputed when the source changes
            Assert.Contains("updateStudioOperationsEnabled();", js);
        }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: FAIL — Operations group / functions absent.

- [ ] **Step 3: Add the Operations group markup**

In `index.html`, immediately after the source label (`<div id="studio-source-label" …></div>`, line 287) add (still inside the source panel `</div>` at line 288):

```html
                        <div id="studio-operations" class="studio-operations">
                            <span class="section-label">Operations</span>
                            <button id="studio-remove-bg-btn" class="btn btn-capture" disabled title="Load or pick a source image first">
                                <svg viewBox="0 0 24 24" fill="none">
                                    <path d="M3 3L21 21M21 3L3 21" stroke="currentColor" stroke-width="1" stroke-opacity="0.4"/>
                                    <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
                                </svg>
                                <span>Remove Background</span>
                            </button>
                            <div id="studio-operation-status" class="status-message hidden"></div>
                        </div>
```

- [ ] **Step 4: Add Operations group CSS**

In `styles.css`, after the `.reconstruct-picker-cell img { … }` rule (ends line 2746) add:

```css
.studio-operations {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-3);
}
.studio-operations .section-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--ink-soft);
}
.studio-operations .btn[disabled] {
    opacity: 0.5;
    cursor: not-allowed;
}
```

- [ ] **Step 5: Cache the new ids**

In `app.js`, after the Task 3 result-panel cache lines (in the Studio cache block) add:

```js
    el.studioOperations = $("studio-operations");
    el.studioRemoveBgBtn = $("studio-remove-bg-btn");
    el.studioOperationStatus = $("studio-operation-status");
```

- [ ] **Step 6: Add the operation functions**

In `app.js`, immediately after `studioSendResultToReconstruct` (added in Task 3) add:

```js
// ─── Studio: Remove Background operation ──────────────────────────

function showStudioOperationStatus(text, kind) {
    if (!el.studioOperationStatus) return;
    el.studioOperationStatus.textContent = text;
    el.studioOperationStatus.className = "status-message " + (kind || "info");
}

// Remove Background is enabled only for an artifact-backed source. Path-only /
// transient sources are not-ready (the backend op is artifact-only; we do not
// auto-materialize). Recompute on every source change.
function updateStudioOperationsEnabled() {
    const ready = !!(studioSource && studioSource.artifact_id);
    if (el.studioRemoveBgBtn) {
        el.studioRemoveBgBtn.disabled = !ready;
        el.studioRemoveBgBtn.title = ready
            ? "Remove the background from the source image"
            : "Load or pick a source image first";
    }
}

async function studioRemoveBackground() {
    if (!(studioSource && studioSource.artifact_id)) {
        showStudioOperationStatus("Load or pick a source image first.", "error");
        return;
    }
    el.studioRemoveBgBtn.disabled = true;
    showStudioOperationStatus("Removing background…", "info");
    try {
        const job = await reconstructionBridgeCall("remove_background", {
            source_artifact_id: studioSource.artifact_id,
            source_role: studioSource.role || "image",
        });
        const jobId = job && job.job_id;
        if (!jobId) {
            showStudioOperationStatus("Background removal did not start.", "error");
            return;
        }
        const resultArtifactId = await awaitStudioRemoveBackground(jobId);
        if (!resultArtifactId) {
            showStudioOperationStatus("Background removal returned no artifact.", "error");
            return;
        }
        latestStudioArtifactId = resultArtifactId;
        el.studioResultImage.src = `/blob/${encodeURIComponent(resultArtifactId)}/image?ts=${Date.now()}`;
        setStudioResultMode("background_removed");
        el.studioResultPanel.classList.remove("hidden");
        showStudioOperationStatus("Background removed.", "success");
    } catch (e) {
        showStudioOperationStatus(errorToText(e), "error");
    } finally {
        updateStudioOperationsEnabled();
    }
}

// Poll the reconstruction job to terminal; return result_artifact_id on success.
async function awaitStudioRemoveBackground(jobId) {
    for (let attempt = 0; attempt < 600; attempt++) {
        const status = await reconstructionBridgeCall("job_status", { job_id: jobId });
        const job = status.job || status;
        const state = job && job.state;
        if (state === "queued") showStudioOperationStatus("Background removal queued…", "info");
        else if (state === "submitting") showStudioOperationStatus("Submitting…", "info");
        else if (state === "materializing") showStudioOperationStatus("Saving result…", "info");
        else if (state === "polling" || !state) showStudioOperationStatus("Removing background…", "info");
        if (state === "complete") return (job && job.result_artifact_id) || null;
        if (state === "cancelled") throw new Error("Background removal cancelled.");
        if (state === "error") throw new Error("Background removal failed.");
        await delay(1000);
    }
    throw new Error("Background removal timed out.");
}
```

- [ ] **Step 7: Hook enablement into source changes**

In `app.js`, at the END of `applyStudioSource(src)` (after the label block closes at line 1049, before the function's closing `}` at line 1050) add:

```js
    updateStudioOperationsEnabled();
```

At the END of `clearStudioSource()` (after the label block closes at line 1063, before the closing `}` at line 1064) add:

```js
    updateStudioOperationsEnabled();
```

- [ ] **Step 8: Wire the Remove Background button + initial enablement**

In `app.js`, in the Studio wiring block after the Task 3 reuse-action wiring add:

```js
    el.studioRemoveBgBtn?.addEventListener("click", studioRemoveBackground);
    updateStudioOperationsEnabled();   // initial disabled state (no source yet)
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: PASS (7 tests).

- [ ] **Step 10: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs
git commit -m "feat(vision): Studio Operations group + Remove Background operation"
```

---

### Task 5: Gallery lists + reconstruct-eligibility for `preprocessed_image`

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js` (`loadGallery` 5th kind; `canReconstructArtifact`)
- Modify: `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs` (add facts)

**Interfaces:**
- Consumes: existing `bridgeCall("list_artifacts", …)`, `canReconstructArtifact`.
- Produces: nothing new; behavior change only.

- [ ] **Step 1: Write the failing test**

Append to `StudioImageProcessingSourceTests.cs`:

```csharp
        // ─── Task 5: Gallery listing + reconstruct eligibility ────────

        [Fact]
        public void AppJs_LoadGallery_IncludesPreprocessedImage()
        {
            var js = ReadVisionResource("app.js");
            // loadGallery() fans out a parallel list_artifacts call per kind; it must include preprocessed_image.
            var s = js.IndexOf("async function loadGallery(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "loadGallery() not found");
            var e = js.IndexOf("async function ", s + 1, System.StringComparison.Ordinal);
            var body = js.Substring(s, (e > s ? e : js.Length) - s);
            Assert.Contains("kind: \"preprocessed_image\"", body);
        }

        [Fact]
        public void AppJs_CanReconstructArtifact_AcceptsPreprocessedImage()
        {
            var js = ReadVisionResource("app.js");
            var s = js.IndexOf("function canReconstructArtifact(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "canReconstructArtifact() not found");
            var e = js.IndexOf("\n}", s, System.StringComparison.Ordinal);
            var body = js.Substring(s, e - s);
            Assert.Contains("preprocessed_image", body);
        }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: FAIL — `preprocessed_image` not yet in `loadGallery`/`canReconstructArtifact`.

- [ ] **Step 3: Add `preprocessed_image` to `loadGallery`**

In `app.js`, in `loadGallery()` (lines 1232-1242), add the 5th parallel call and merge it.

Change the `Promise.all` array (lines 1232-1237) to:

```js
        const [imgData, vidData, importedImageData, importedVideoData, preprocessedImageData] = await Promise.all([
            bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "imported_image", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "imported_video", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "preprocessed_image", limit: 100 }),
        ]);
```

Change the `galleryItems` spread (lines 1238-1242) to include the new data:

```js
        galleryItems = [
            ...(imgData.artifacts || []),
            ...(vidData.artifacts || []),
            ...(importedImageData.artifacts || []),
            ...(importedVideoData.artifacts || []),
            ...(preprocessedImageData.artifacts || []),
        ].sort((a, b) => {
```

- [ ] **Step 4: Add `preprocessed_image` to `canReconstructArtifact`**

In `app.js`, change `canReconstructArtifact` (lines 1594-1601) to accept the new kind:

```js
function canReconstructArtifact(artifact) {
    return !!artifact
        && (artifact.kind === "generated_image"
            || artifact.kind === "imported_image"
            || artifact.kind === "captured_viewport"
            || artifact.kind === "preprocessed_image")
        && Array.isArray(artifact.files)
        && artifact.files.some(f => f.role === "image");
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/UI/Vision/Resources/app.js src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs
git commit -m "feat(vision): Gallery lists + reconstruct-eligibility for preprocessed_image"
```

---

### Task 6: Panel-dark id-integrity guard + full-suite & live verification

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs` (id-integrity meta-test)

**Interfaces:**
- Consumes: all ids cached in Tasks 2-4.
- Produces: a regression guard that every new Studio `$("id")` exists in `index.html`.

- [ ] **Step 1: Write the panel-dark id-integrity test**

Append to `StudioImageProcessingSourceTests.cs`:

```csharp
        // ─── Task 6: Panel-dark id-integrity guard ────────────────────

        // Every id this slice caches in app.js MUST have a matching element in
        // index.html. A missing id nulls the cache entry and can blank the whole
        // Vision panel at init. This is the panel-dark regression guard.
        [Theory]
        [InlineData("studio-pick-gallery-btn")]
        [InlineData("studio-picker-modal")]
        [InlineData("studio-picker-grid")]
        [InlineData("studio-picker-close")]
        [InlineData("studio-result-title")]
        [InlineData("studio-result-gen-actions")]
        [InlineData("studio-result-op-actions")]
        [InlineData("studio-use-as-source-btn")]
        [InlineData("studio-open-in-gallery-btn")]
        [InlineData("studio-send-to-reconstruct-btn")]
        [InlineData("studio-operations")]
        [InlineData("studio-remove-bg-btn")]
        [InlineData("studio-operation-status")]
        public void EveryCachedStudioId_ExistsInIndexHtml(string id)
        {
            var js = ReadVisionResource("app.js");
            var html = ReadVisionResource("index.html");
            // The id is cached in app.js …
            Assert.Contains($"$(\"{id}\")", js);
            // … and a matching element exists in index.html.
            Assert.Contains($"id=\"{id}\"", html);
        }
```

- [ ] **Step 2: Run the new test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~StudioImageProcessingSourceTests"`
Expected: PASS (10 facts/theories; 13 inline cases for the theory).

- [ ] **Step 3: Run the full Vision/WebView source suite (panel-dark regression)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~UI.Vision"`
Expected: PASS — confirms no other Vision source test regressed (ids, routes, init wiring), including the updated `ReconstructionAsyncOps` pin.

- [ ] **Step 4: Run the full test suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS — full green (record the count for the PR body).

- [ ] **Step 5: Commit**

```bash
git add src/Rook.Tests/UI/Vision/StudioImageProcessingSourceTests.cs
git commit -m "test(vision): panel-dark id-integrity guard for Studio image-processing"
```

- [ ] **Step 6: Live gate + panel-dark presentation verification (manual, post-deploy)**

This is the closeout acceptance gate — NOT automated. After deploying the managed Release build (Vision web assets are embedded resources, so a managed build re-embeds them; the `remove_background` allowlist change is also managed-only):

1. Open the Vision panel → **Studio** tab. Confirm the panel renders (not dark).
2. Load or **Pick from Gallery** a source image → confirm **Remove Background** enables (was disabled with "Load or pick a source image first").
3. Click **Remove Background** → confirm the op status strip advances and a `preprocessed_image` result renders in the **Studio result panel** titled "Background removed" with the three reuse actions (no "Generated"/"New Generation" copy). **Confirm the three reuse buttons wrap/fit without overlap in the Studio right pane (P2).**
4. **Use as source** → result becomes the Studio source. **Open in Gallery** → the produced artifact's modal opens. **Send to Reconstruct** → Reconstruct opens with the front slot preset.
5. Confirm the `preprocessed_image` appears in **Gallery** and its modal **Send to 3D** button is enabled.
6. **Panel-dark presentation check:** exercise the presentation diagnostics/repair path if available (`rhino_vision_presentation` → dump/repair, i.e. the companion's `get_presentation_diagnostics` / `repair_presentation`) and confirm the panel composits with no stuck renderer.

Record the live-gate result (single BiRefNet roundtrip) for the PR body. Do not claim the live gate passed unless it was actually run.

---

## Self-Review

**1. Spec coverage** (spec §-by-§):
- §2 architecture (Pattern A, reconstruction bridge) → Tasks 1-5. The reconstruction-bridge reachability gap is closed by **Task 1** (managed allowlist), the one C# change; everything else is Vision resources.
- §3.1 Pick from Gallery (4 kinds, `applyStudioSource`, beside source controls, scoped modal) → Task 2.
- §3.2 Operations group + Remove Background (artifact-backed gate, exact hint, recomputed enablement) → Task 4.
- §3.3 result-panel reuse (sets `latestStudioArtifactId`/`studioResultImage`/`studioResultPanel`, operation-aware title/actions, three reuse actions; Open-in-Gallery opens the artifact; Send-to-Reconstruct fetches full artifact) → Task 3.
- §3.4 Gallery lists `preprocessed_image` (loadGallery only) + `canReconstructArtifact` accepts it → Task 5.
- §4 error/edge (disabled gate, terminal states, errorToText, chaining) → Tasks 3/4.
- §5 panel-dark (id integrity, guarded wiring, scoped modal, regression tests, final verification) → Global Constraints + scoped/guarded wiring in every task + Task 6 guard + Task 6 Step 6.
- §6 testing (source-assertion tests, the one managed bridge test, live gate) → each task's tests + Task 6.
- §7 scope (in/out) → Global Constraints; no out-of-scope task present.
- §8 risks (`presetSource` needs full artifact → get_artifact; Studio-local poller) → Task 3 Send-to-Reconstruct uses get_artifact; Task 4 has its own `awaitStudioRemoveBackground`.

No gaps.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows complete code; every test step shows real assertions; every command has an expected result. Clean.

**3. Type/name consistency:** Function and id names match across tasks — `setStudioResultMode` (defined Task 3, called Task 4), `updateStudioOperationsEnabled` (Task 4, hooked into `applyStudioSource`/`clearStudioSource`), `studioPickerArtifactsById`, `STUDIO_SOURCE_KINDS`, `latestStudioArtifactId` (existing), `el.studio*` ids identical between markup, cache, wiring, and the Task 6 id-integrity theory. `reconstructionBridgeCall("remove_background"…)` / `("job_status"…)` and `bridgeCall("get_artifact"…)` / `("list_artifacts"…)` match the verified bridge op strings; `remove_background` is reachable because Task 1 adds it to `ReconstructionAsyncOps`. Consistent.
