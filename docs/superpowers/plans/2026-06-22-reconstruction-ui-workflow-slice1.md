# Reconstruction UI Workflow (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the existing v0 gallery-modal reconstruction shortcut into a first-class **Reconstruct** view in the RookVision surface — explicit model selection, a textured/geometry-only control, submit→poll→result, a result-package panel that renders `result.warnings[]`, a lightweight job history, and an import handoff — with one submit path and the reconstruction async bridge ops under `AsyncOpTimeout`.

**Architecture:** Extend the existing Vision WebView surface; do not fork. Reconstruction keeps its own existing `"reconstruction"` bridge channel (`VisionWebSurface.cs:344`). The view is a self-contained `Reconstruct` IIFE module in `app.js` mirroring the existing `Video` module shape (`cacheEls`/`wireEvents`/`onEnter`), with markup in `index.html` and styles in `styles.css`. One C# change: route the three reconstruction async bridge ops through the existing `DispatchWithTimeoutAsync` helper.

**Tech Stack:** C# (.NET Framework 4.8, Eto.Forms, WebView2), vanilla JS/HTML/CSS (no framework, no JS test harness), xUnit (`Rook.Tests`, net48).

## Global Constraints

- Base: `origin/main` @ `5fa48b28`; worktree `.worktrees/reconstruction-ui`, branch `feature/reconstruction-ui-workflow-slice1`. All work in this worktree.
- Reconstruction uses its **own** `"reconstruction"` bridge channel — do **not** add reconstruction ops to the `"vision"` `OpRoutes` table.
- Source for a reconstruction is an existing **image artifact** (`source_artifact_id`, GUID); local paths are rejected by the backend.
- `model_id` is **required**; there is no implicit default — the UI must force an explicit model pick.
- Output options are **mutually exclusive**: textured → `options:{enable_pbr:true}`; geometry-only → `options:{enable_geometry:true}`. The UI never emits both (backend D1 guard rejects the combination).
- Warnings are read from `result.warnings[]` **by `code`**; never infer degradation from raw `asset_roles`. Geometry-only must produce **no** texture warning (`TextureExpected=false` suppresses `result_missing_texture` by design).
- One submit path only: the gallery "Send to 3D" button becomes a preselect+navigate shortcut, not a second submit.
- One-click native import, Three.js preview, and a cost modal are **out of scope** (import is native-C++-only behind `/reconstruction/2d-to-3d/import`; show handoff copy instead).
- Tests: only the C# timeout-routing change is mechanically unit-tested. JS UI is verified manually (no JS harness exists, consistent with Generate/Video). `dotnet test -c Debug` must stay green (Debug skips the `%AppData%` deploy).
- JS helpers available globally: `$(id)`=getElementById, `$$(sel)`=querySelectorAll, `escapeHtml`, `escapeAttr`, `delay(ms)`, `formatTimestamp`, `reconstructionBridgeCall(op,args)`, `errorToText(e)`, `canReconstructArtifact(artifact)`, `switchView(view)`, `el.navBtns`.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `src/Rook/UI/Vision/VisionWebSurface.cs` | Reconstruction bridge channel | Add `domainLabel` param to `DispatchWithTimeoutAsync`; route async ops through it with `domainLabel:"Reconstruction"`; add `ReconstructionAsyncOps` set (Task 1) |
| `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs` | Bridge unit tests | Pin `ReconstructionAsyncOps` (Task 1) |
| `src/Rook/UI/Vision/Resources/index.html` | Reconstruct view markup + nav | New nav button + `#reconstruct-view` section; modal button stays (Tasks 2–6); modal status strip removed (Task 7) |
| `src/Rook/UI/Vision/Resources/app.js` | Reconstruct module + switch wiring + shortcut | New `Reconstruct` IIFE module; `switchView` dispatch; init wiring; modal-button rewire + delete v0 modal submit (Tasks 2–7) |
| `src/Rook/UI/Vision/Resources/styles.css` | Reconstruct view styles | New `.reconstruct-*` rules (Tasks 3–6) |

---

## Task 1: Reconstruction async bridge ops under `AsyncOpTimeout`

**Files:**
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs` (`HandleReconstructionBridgeCallAsync`, ~line 505)
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

**Interfaces:**
- Consumes: existing `internal static readonly TimeSpan AsyncOpTimeout`.
- Modifies: `DispatchWithTimeoutAsync` gains an optional `string domainLabel = "Vision"` param so the timeout message reads `"{domainLabel} op '{op}' timed out…"` ([P2] — reconstruction must not say "Vision op").
- Produces: `internal static readonly HashSet<string> ReconstructionAsyncOps` = {`submit_job`,`job_status`,`cancel_job`}; `HandleReconstructionBridgeCallAsync` routes async ops through `DispatchWithTimeoutAsync(... domainLabel: "Reconstruction")`.

**Why this test shape ([P1]):** the pure timeout/rewrite behavior of `DispatchWithTimeoutAsync` is already covered by the `DispatchWithTimeout_*` tests — we don't duplicate it. But a set-membership pin alone would pass even if the handler never used the set, so we add (a) a **source assertion** that `HandleReconstructionBridgeCallAsync` actually consults `ReconstructionAsyncOps.Contains(op)` and calls `DispatchWithTimeoutAsync(` with `domainLabel: "Reconstruction"` (mirroring the `RepoRoot` source-guard convention in `NativeReconstructionDispatchSourceTests`), and (b) a **behavioral** test of the new `domainLabel` path. Together these prove routing + correct labeling without re-testing timeout mechanics.

- [ ] **Step 1: Write the failing tests**

In `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`, add `using System.Linq;` to the usings if absent, then add a `RepoRoot` helper to the class (mirrors `NativeReconstructionDispatchSourceTests`) and four tests:

```csharp
private static string RepoRoot
    => Path.GetFullPath(Path.Combine(System.AppContext.BaseDirectory, "..", "..", "..", "..", ".."));

[Fact]
public void ReconstructionAsyncOps_AreExactlySubmitStatusCancel()
{
    Assert.Equal(
        new[] { "cancel_job", "job_status", "submit_job" },
        VisionWebSurface.ReconstructionAsyncOps.OrderBy(o => o, StringComparer.Ordinal).ToArray());
}

[Fact]
public void ReconstructionAsyncOps_ExcludeOffUiOps()
{
    Assert.DoesNotContain("models", VisionWebSurface.ReconstructionAsyncOps);
    Assert.DoesNotContain("list_jobs", VisionWebSurface.ReconstructionAsyncOps);
    Assert.DoesNotContain("job_result", VisionWebSurface.ReconstructionAsyncOps);
}

[Fact]
public void HandleReconstructionBridge_RoutesAsyncOpsThroughTimeoutWrapper()
{
    // The set must actually drive the timeout wrapper — pin the wiring in
    // source so a future edit that bypasses ReconstructionAsyncOps or
    // DispatchWithTimeoutAsync fails here, not silently in production.
    var source = File.ReadAllText(Path.Combine(
        RepoRoot, "src", "Rook", "UI", "Vision", "VisionWebSurface.cs"));
    var start = source.IndexOf(
        "HandleReconstructionBridgeCallAsync", StringComparison.Ordinal);
    Assert.True(start >= 0, "HandleReconstructionBridgeCallAsync not found.");
    // Bound to the method: from its declaration to the next 'private ' member.
    var bodyStart = source.IndexOf('{', start);
    var next = source.IndexOf("\n        private ", bodyStart, StringComparison.Ordinal);
    var method = next > bodyStart ? source.Substring(bodyStart, next - bodyStart) : source.Substring(bodyStart);

    Assert.Contains("ReconstructionAsyncOps.Contains(op)", method);
    Assert.Contains("DispatchWithTimeoutAsync(", method);
    Assert.Contains("domainLabel: \"Reconstruction\"", method);
}

[Fact]
public async Task DispatchWithTimeout_ReconstructionLabel_EmitsReconstructionTimeoutMessage()
{
    var response = await VisionWebSurface.DispatchWithTimeoutAsync(
        "submit_job",
        TimeSpan.FromMilliseconds(30),
        async token =>
        {
            await Task.Delay(TimeSpan.FromSeconds(2), token).ConfigureAwait(false);
            return new ApiResponse { Success = true };
        },
        domainLabel: "Reconstruction");

    Assert.False(response.Success);
    var message = Assert.IsType<string>(response.Data);
    Assert.Contains("Reconstruction op 'submit_job' timed out", message, StringComparison.Ordinal);
    Assert.DoesNotContain("Vision op", message);
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VisionWebSurfaceTests.ReconstructionAsyncOps|FullyQualifiedName~VisionWebSurfaceTests.HandleReconstructionBridge_Routes|FullyQualifiedName~VisionWebSurfaceTests.DispatchWithTimeout_ReconstructionLabel"`
Expected: FAIL — `ReconstructionAsyncOps` undefined; `DispatchWithTimeoutAsync` has no `domainLabel` param; source lacks the routing tokens.

- [ ] **Step 3a: Add the `domainLabel` param to the shared timeout helper**

In `src/Rook/UI/Vision/VisionWebSurface.cs`, change the `DispatchWithTimeoutAsync` signature and its two message strings:

```csharp
        internal static async Task<ApiResponse> DispatchWithTimeoutAsync(
            string op,
            TimeSpan timeout,
            Func<CancellationToken, Task<ApiResponse>> dispatch,
            string domainLabel = "Vision")
        {
            using var cts = new CancellationTokenSource(timeout);
            ApiResponse response;
            try
            {
                response = await dispatch(cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cts.IsCancellationRequested)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"{domainLabel} op '{op}' timed out after {timeout.TotalSeconds:F0}s.",
                };
            }

            if (!response.Success && cts.IsCancellationRequested)
            {
                response.Data = $"{domainLabel} op '{op}' timed out after {timeout.TotalSeconds:F0}s.";
            }
            return response;
        }
```

The existing Vision/Video callers omit the new arg and keep `"Vision"` — their tests (`DispatchWithTimeout_*`) don't assert the prefix, so they stay green.

- [ ] **Step 3b: Add the op set and route async ops through the timeout helper**

In the same file, add the set near the other op-routing fields (just after the `MediaImportOps` set, ~line 254):

```csharp
        /// <summary>
        /// Reconstruction bridge ops that are network-bound and must run
        /// under <see cref="AsyncOpTimeout"/> via
        /// <see cref="DispatchWithTimeoutAsync"/> — parity with the Vision
        /// and Video async paths. Off-UI ops (models / list_jobs /
        /// job_result) are disk/catalog reads and are dispatched directly.
        /// </summary>
        internal static readonly HashSet<string> ReconstructionAsyncOps =
            new(StringComparer.Ordinal)
            {
                "submit_job",
                "job_status",
                "cancel_job",
            };
```

Then replace the `op switch` body inside `HandleReconstructionBridgeCallAsync` (the `try` block, ~lines 517–533) with:

```csharp
            ApiResponse response;
            try
            {
                if (ReconstructionAsyncOps.Contains(op))
                {
                    response = await DispatchWithTimeoutAsync(
                        op,
                        AsyncOpTimeout,
                        token => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync(body, token),
                        domainLabel: "Reconstruction")
                        .ConfigureAwait(false);
                }
                else if (op is "models" or "list_jobs" or "job_result")
                {
                    response = await Task.Run(
                        () => RookSubsystemRoot.Instance.Reconstruction.DispatchOffUi(body))
                        .ConfigureAwait(false);
                }
                else
                {
                    response = new ApiResponse
                    {
                        Success = false,
                        Data = $"Unknown reconstruction op '{op}'.",
                        HttpStatus = 400,
                    };
                }
            }
            catch (Exception ex)
            {
                Log($"Rook: reconstruction bridge op '{op}' threw: {ex.GetType().Name}: {ex.Message}");
                return BuildFailure($"Reconstruction op '{op}' failed.");
            }
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VisionWebSurfaceTests.ReconstructionAsyncOps|FullyQualifiedName~VisionWebSurfaceTests.HandleReconstructionBridge_Routes|FullyQualifiedName~VisionWebSurfaceTests.DispatchWithTimeout_ReconstructionLabel"`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the surface test class to confirm no regression**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VisionWebSurfaceTests"`
Expected: all green, including the pre-existing `DispatchWithTimeout_*` tests (default `"Vision"` label unchanged). No "Deployed Rook.rhp" line — Debug skips deploy.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/UI/Vision/VisionWebSurface.cs src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(reconstruction-ui): route async bridge ops under AsyncOpTimeout with Reconstruction label"
```

---

## Task 2: Reconstruct nav button, empty view, and module skeleton

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html` (nav ~line 24; new section after `#video-view` ~line 654)
- Modify: `src/Rook/UI/Vision/Resources/app.js` (`switchView` ~line 127; init wiring ~line 2171 and ~line 2294)

**Interfaces:**
- Produces: global `loadReconstructView()`; `Reconstruct` module exposing `{ cacheEls, wireEvents, onEnter }` (onEnter is a no-op stub in this task); nav `data-view="reconstruct"` → section `#reconstruct-view`.

- [ ] **Step 1: Add the nav button**

In `index.html`, inside `<nav class="nav">`, add after the `video` nav button (after line 36, before the `gallery` button):

```html
                <button class="nav-btn" data-view="reconstruct">
                    <span class="nav-label">Reconstruct</span>
                    <span class="nav-indicator"></span>
                </button>
```

- [ ] **Step 2: Add the empty view section**

In `index.html`, add immediately after the closing `</section>` of `#video-view` (before `#gallery-view`, ~line 654):

```html
            <section id="reconstruct-view" class="view">
                <div class="view-header">
                    <h1 class="view-title">Reconstruct</h1>
                    <p class="view-subtitle">Turn an image into a 3D package</p>
                </div>
                <div class="reconstruct-body">
                    <!-- Populated in Tasks 3–6 -->
                </div>
            </section>
```

- [ ] **Step 3: Add the module skeleton in `app.js`**

In `app.js`, immediately after the `Video` module's closing `})();` (after line 3375), add:

```javascript
// ─── Reconstruct module (image → 3D package) ────────────────────────
//
// Self-contained like `Video`: own state namespace, own DOM cache,
// driven on view-enter. All bridge calls go through
// `reconstructionBridgeCall(op, args)` on the dedicated "reconstruction"
// channel; op names match ReconstructionOpHandler constants.

function loadReconstructView() { Reconstruct.onEnter(); }

const Reconstruct = (() => {
    const POLL_INTERVAL_MS = 1500;
    const POLL_MAX_ATTEMPTS = 180;
    const TERMINAL_FAIL = new Set(["error", "cancelled", "interrupted"]);

    let models = [];
    let modelsLoaded = false;
    let source = null;            // { artifact_id, role, previewSrc, label }
    let outputMode = "textured";  // "textured" | "geometry"

    const re = {};                // DOM cache

    function cacheEls() {
        // Filled in Tasks 3–6.
    }

    function wireEvents() {
        // Filled in Tasks 3–6.
    }

    async function onEnter() {
        // Filled in Tasks 3 & 6 (load models + job history).
    }

    return { cacheEls, wireEvents, onEnter, presetSource };

    // presetSource is defined in Task 7 (Send-to-3D shortcut).
    function presetSource(_artifact) { /* Task 7 */ }
})();
```

- [ ] **Step 4: Dispatch the view on switch**

In `app.js` `switchView` (~line 142, alongside the other per-view loaders), add:

```javascript
    if (view === "reconstruct") loadReconstructView();
```

- [ ] **Step 5: Cache + wire the module during init**

In `app.js`, find `Video.cacheEls();` (~line 2171) and add directly after it:

```javascript
    Reconstruct.cacheEls();
```

Find `Video.wireEvents();` (~line 2294) and add directly after it:

```javascript
    Reconstruct.wireEvents();
```

(The nav button is already wired generically: `el.navBtns.forEach(btn => btn.addEventListener("click", () => switchView(btn.dataset.view)));`.)

- [ ] **Step 6: Manual verification**

Build/deploy not required for markup-only review, but the implementer must visually confirm in Rhino (or note it for the slice's manual-verification pass): the **Reconstruct** nav item appears between Video and Gallery; clicking it activates an (empty) Reconstruct view with the header; no JS console errors. If a deploy is impractical mid-task, record this as a checklist item for the end-of-slice manual pass.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js
git commit -m "feat(reconstruction-ui): add Reconstruct nav, empty view, and module skeleton"
```

---

## Task 3: Source selection + model selection

**Files:**
- Modify: `index.html` (`#reconstruct-view .reconstruct-body`)
- Modify: `app.js` (`Reconstruct` module)
- Modify: `styles.css`

**Interfaces:**
- Consumes: `reconstructionBridgeCall("models")` → `{ models: [{ model_id, provider, supports_pbr, preferred_asset_role, ... }] }`; `canReconstructArtifact(artifact)`; `loadGallery`/artifact list for the source picker.
- Produces: `re.sourceThumb`, `re.sourceLabel`, `re.chooseSourceBtn`, `re.modelSelect`; module fns `loadModels()`, `renderSource()`, `chooseSource()`, `selectedModelId()`.

- [ ] **Step 1: Add source + model markup**

In `index.html`, replace the `<!-- Populated in Tasks 3–6 -->` comment inside `.reconstruct-body` with:

```html
                    <div class="reconstruct-form">
                        <div class="reconstruct-field">
                            <label class="reconstruct-label">Source image</label>
                            <div class="reconstruct-source">
                                <img id="reconstruct-source-thumb" class="reconstruct-source-thumb hidden" alt="source" />
                                <span id="reconstruct-source-label" class="reconstruct-source-label">No image selected</span>
                                <button id="reconstruct-choose-source" class="btn btn-secondary">Choose in Gallery…</button>
                            </div>
                        </div>
                        <div class="reconstruct-field">
                            <label class="reconstruct-label" for="reconstruct-model-select">Model</label>
                            <select id="reconstruct-model-select" class="select"></select>
                        </div>
                    </div>
```

- [ ] **Step 2: Cache the new elements**

In `app.js`, fill `Reconstruct.cacheEls()`:

```javascript
    function cacheEls() {
        re.sourceThumb = $("reconstruct-source-thumb");
        re.sourceLabel = $("reconstruct-source-label");
        re.chooseSourceBtn = $("reconstruct-choose-source");
        re.modelSelect = $("reconstruct-model-select");
    }
```

- [ ] **Step 3: Implement model loading + source rendering + picker**

In `app.js`, inside the `Reconstruct` module (above the `return`), add:

```javascript
    function selectedModelId() {
        return re.modelSelect && re.modelSelect.value ? re.modelSelect.value : null;
    }

    function buildModelOption(model) {
        const pbr = model.supports_pbr ? "" : " · no PBR";
        return `<option value="${escapeAttr(model.model_id)}">${escapeHtml(model.model_id)}${escapeHtml(pbr)}</option>`;
    }

    async function loadModels() {
        if (modelsLoaded) return;
        try {
            const data = await reconstructionBridgeCall("models", {});
            models = Array.isArray(data.models) ? data.models : [];
        } catch (e) {
            models = [];
        }
        // Leading placeholder forces an explicit pick (model_id is required).
        const placeholder = `<option value="" disabled selected>Select a model…</option>`;
        re.modelSelect.innerHTML = placeholder + models.map(buildModelOption).join("");
        modelsLoaded = true;
    }

    function renderSource() {
        if (source && source.previewSrc) {
            re.sourceThumb.src = source.previewSrc;
            re.sourceThumb.classList.remove("hidden");
        } else {
            re.sourceThumb.removeAttribute("src");
            re.sourceThumb.classList.add("hidden");
        }
        re.sourceLabel.textContent = source ? (source.label || source.artifact_id) : "No image selected";
    }

    async function chooseSource() {
        // Reuse the gallery list; pick the first reconstructable image.
        // (Slice 1: a lightweight chooser — open the Gallery so the user
        // selects via the existing modal "Send to 3D" shortcut, which
        // calls presetSource and returns here. See Task 7.)
        switchView("gallery");
        showStatus("Pick an image in the Gallery, then use “Send to 3D”.", "info");
    }
```

> Note: `chooseSource` intentionally routes through the Gallery + the Send-to-3D shortcut (Task 7) rather than duplicating a picker — that keeps a single source-selection path. `presetSource` (Task 7) sets `source` and navigates back.

- [ ] **Step 4: Wire events and load models on enter**

Fill `Reconstruct.wireEvents()`:

```javascript
    function wireEvents() {
        re.chooseSourceBtn.addEventListener("click", chooseSource);
    }
```

Set `onEnter` (extended again in Task 6):

```javascript
    async function onEnter() {
        await loadModels();
        renderSource();
    }
```

- [ ] **Step 5: Add styles**

In `styles.css`, append:

```css
/* ── Reconstruct view ─────────────────────────────────────────── */
.reconstruct-body { display: flex; flex-direction: column; gap: 1.5rem; }
.reconstruct-form { display: flex; flex-direction: column; gap: 1.25rem; }
.reconstruct-field { display: flex; flex-direction: column; gap: 0.5rem; }
.reconstruct-label { font-family: var(--font-mono); font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.7; }
.reconstruct-source { display: flex; align-items: center; gap: 0.75rem; }
.reconstruct-source-thumb { width: 64px; height: 64px; object-fit: cover; border: 1px solid var(--line); }
.reconstruct-source-label { flex: 1; font-size: 0.9rem; opacity: 0.85; }
```

- [ ] **Step 6: Manual verification**

Confirm (or record for the manual pass): entering the Reconstruct view loads the model dropdown with a disabled "Select a model…" placeholder selected (no implicit pick), and the model ids appear; "Choose in Gallery…" navigates to Gallery with the hint.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-ui): source + model selection in Reconstruct view"
```

---

## Task 4: Textured/geometry-only control + submit + poll (single path)

**Files:** `index.html`, `app.js`, `styles.css` (`Reconstruct` module).

**Interfaces:**
- Consumes: `selectedModelId()`, `source`, `reconstructionBridgeCall("submit_job"|"job_status")`, `delay`.
- Produces: `re.modeTextured`, `re.modeGeometry`, `re.submitBtn`, `re.statusMessage`; fns `optionsForMode()`, `submit()`, `poll(jobId)`, `showReconstructStatus(msg,type)`; calls `renderResult(result)` (Task 5) on completion.

- [ ] **Step 1: Add the control, submit button, and status strip**

In `index.html`, add inside `.reconstruct-form`, after the model field:

```html
                        <div class="reconstruct-field">
                            <label class="reconstruct-label">Output</label>
                            <div class="reconstruct-segmented" role="radiogroup" aria-label="Output type">
                                <button type="button" id="reconstruct-mode-textured" class="seg-btn active" data-mode="textured">Textured</button>
                                <button type="button" id="reconstruct-mode-geometry" class="seg-btn" data-mode="geometry">Geometry only</button>
                            </div>
                        </div>
                        <div class="reconstruct-actions">
                            <button id="reconstruct-submit-btn" class="btn btn-primary">Reconstruct</button>
                        </div>
                        <div id="reconstruct-status-message" class="status-message hidden"></div>
```

- [ ] **Step 2: Extend the DOM cache**

Add to `Reconstruct.cacheEls()`:

```javascript
        re.modeTextured = $("reconstruct-mode-textured");
        re.modeGeometry = $("reconstruct-mode-geometry");
        re.submitBtn = $("reconstruct-submit-btn");
        re.statusMessage = $("reconstruct-status-message");
```

- [ ] **Step 3: Implement options encoding, submit, poll, status**

Add inside the module (above `return`):

```javascript
    function showReconstructStatus(message, type) {
        re.statusMessage.textContent = message;
        re.statusMessage.className = `status-message ${type || "info"}`;
        re.statusMessage.classList.remove("hidden");
    }

    function setOutputMode(mode) {
        outputMode = mode === "geometry" ? "geometry" : "textured";
        re.modeTextured.classList.toggle("active", outputMode === "textured");
        re.modeGeometry.classList.toggle("active", outputMode === "geometry");
    }

    function optionsForMode() {
        // Mutually exclusive — never emit both (backend D1 guard).
        return outputMode === "geometry"
            ? { enable_geometry: true }
            : { enable_pbr: true };
    }

    async function submit() {
        if (!source || !source.artifact_id) {
            showReconstructStatus("Choose a source image first.", "error");
            return;
        }
        const modelId = selectedModelId();
        if (!modelId) {
            showReconstructStatus("Select a model first.", "error");
            return;
        }
        try {
            re.submitBtn.disabled = true;
            showReconstructStatus("Submitting reconstruction…", "info");
            const job = await reconstructionBridgeCall("submit_job", {
                source_artifact_id: source.artifact_id,
                source_role: source.role || "image",
                model_id: modelId,
                preprocessing_chain: [],
                options: optionsForMode(),
                estimate_requested: false,
            });
            if (!job || !job.job_id) {
                throw new Error("Reconstruction submit did not return a job id.");
            }
            await poll(job.job_id);
        } catch (e) {
            showReconstructStatus(errorToText(e), "error");
        } finally {
            re.submitBtn.disabled = false;
        }
    }

    async function poll(jobId) {
        for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
            const status = await reconstructionBridgeCall("job_status", { job_id: jobId });
            const job = status.job || status;
            showReconstructStatus(`3D ${job.stage || job.state || "working"} · ${jobId}`, "info");
            if (job.state === "complete") {
                const result = await reconstructionBridgeCall("job_result", { job_id: jobId });
                renderResult(result);   // Task 5
                showReconstructStatus("Reconstruction complete.", "success");
                if (typeof loadJobs === "function") loadJobs(); // Task 6 (refresh history)
                return;
            }
            if (TERMINAL_FAIL.has(job.state)) {
                showReconstructStatus(`Reconstruction ${job.state}.`, "error");
                return;
            }
            await delay(POLL_INTERVAL_MS);
        }
        showReconstructStatus("Reconstruction polling timed out.", "error");
    }
```

> `renderResult` and `loadJobs` are defined in Tasks 5 and 6. Because they live in the same module scope and are only **called** at runtime (after those tasks land), the references resolve when the slice is complete. If implementing strictly task-by-task and testing Task 4 in isolation, temporarily stub `function renderResult(r){ showReconstructStatus("Package " + (r.result_artifact_id||""), "success"); }` and remove the stub in Task 5.

- [ ] **Step 4: Wire events**

Extend `Reconstruct.wireEvents()`:

```javascript
        re.modeTextured.addEventListener("click", () => setOutputMode("textured"));
        re.modeGeometry.addEventListener("click", () => setOutputMode("geometry"));
        re.submitBtn.addEventListener("click", submit);
```

- [ ] **Step 5: Add styles**

Append to `styles.css`:

```css
.reconstruct-segmented { display: inline-flex; border: 1px solid var(--line); width: max-content; }
.seg-btn { padding: 0.5rem 1rem; background: transparent; border: none; cursor: pointer; font-family: var(--font-mono); font-size: 0.8rem; }
.seg-btn + .seg-btn { border-left: 1px solid var(--line); }
.seg-btn.active { background: var(--ink); color: var(--paper); }
.reconstruct-actions { display: flex; gap: 0.75rem; }
```

- [ ] **Step 6: Manual verification**

Confirm (or record): textured/geometry toggle is mutually exclusive (clicking one deactivates the other); submitting with no source or no model shows the right error; a real submit progresses through stages and reaches a terminal state. Geometry-only completes without a texture warning (Task 5 renders warnings; here just confirm it runs).

- [ ] **Step 7: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-ui): output-mode control, submit, and poll"
```

---

## Task 5: Result package panel + warnings rendering

**Files:** `index.html`, `app.js`, `styles.css` (`Reconstruct` module).

**Interfaces:**
- Consumes: `job_result` → `{ result_artifact_id, result_available, package:{ asset_roles[], preferred_asset_role }, warnings:[{code,message,details}] }`; blob route `/blob/{package_id}/thumbnail`.
- Produces: `re.resultPanel`, `re.resultThumb`, `re.resultMeta`, `re.resultWarnings`, `re.resultHandoff`; fns `renderResult(result)`, `renderWarnings(warnings)`.

- [ ] **Step 1: Add result panel markup**

In `index.html`, add after the status strip, still inside `.reconstruct-body`:

```html
                    <div id="reconstruct-result-panel" class="reconstruct-result hidden">
                        <div class="reconstruct-result-head">
                            <img id="reconstruct-result-thumb" class="reconstruct-result-thumb hidden" alt="result" />
                            <div id="reconstruct-result-meta" class="reconstruct-result-meta"></div>
                        </div>
                        <ul id="reconstruct-result-warnings" class="reconstruct-warnings"></ul>
                        <div id="reconstruct-result-handoff" class="reconstruct-handoff"></div>
                    </div>
```

- [ ] **Step 2: Extend the DOM cache**

Add to `cacheEls()`:

```javascript
        re.resultPanel = $("reconstruct-result-panel");
        re.resultThumb = $("reconstruct-result-thumb");
        re.resultMeta = $("reconstruct-result-meta");
        re.resultWarnings = $("reconstruct-result-warnings");
        re.resultHandoff = $("reconstruct-result-handoff");
```

- [ ] **Step 3: Implement result + warnings rendering**

Add inside the module (above `return`). Remove any temporary `renderResult` stub from Task 4.

```javascript
    // Friendly headline per known warning code. Unknown codes fall back
    // to the backend message verbatim (forward-compatible). Read by CODE,
    // never inferred from asset_roles.
    const WARNING_COPY = {
        result_artifact_missing: {
            severity: "error",
            text: "The reconstruction completed but its package could not be found. The result may be unavailable; try re-running.",
        },
        pbr_unsupported_by_model: {
            severity: "warning",
            text: "Textured output was requested, but this model isn't catalogued as supporting textured/PBR output. The result may have no materials.",
        },
        result_missing_texture: {
            severity: "warning",
            text: "Textured output was expected and this model supports it, but the delivered package contains no material or texture assets.",
        },
    };

    function renderWarnings(warnings) {
        const list = Array.isArray(warnings) ? warnings : [];
        if (list.length === 0) {
            re.resultWarnings.innerHTML = "";
            re.resultWarnings.classList.add("hidden");
            return;
        }
        re.resultWarnings.innerHTML = list.map(w => {
            const known = WARNING_COPY[w.code];
            const severity = known ? known.severity : "warning";
            const headline = known ? known.text : (w.message || w.code || "Unknown warning.");
            const detail = !known && w.message ? "" : (w.message ? `<span class="reconstruct-warning-detail">${escapeHtml(w.message)}</span>` : "");
            return `<li class="reconstruct-warning ${severity}"><span class="reconstruct-warning-code">${escapeHtml(w.code || "warning")}</span>${escapeHtml(headline)}${detail}</li>`;
        }).join("");
        re.resultWarnings.classList.remove("hidden");
    }

    function renderResult(result) {
        const pkg = result.package || {};
        const packageId = result.result_artifact_id || "";
        const roles = Array.isArray(pkg.asset_roles) ? pkg.asset_roles : [];
        const preferred = pkg.preferred_asset_role || "";

        if (packageId && result.result_available) {
            re.resultThumb.src = `/blob/${packageId}/thumbnail`;
            re.resultThumb.classList.remove("hidden");
        } else {
            re.resultThumb.removeAttribute("src");
            re.resultThumb.classList.add("hidden");
        }
        re.resultThumb.onerror = () => re.resultThumb.classList.add("hidden");

        re.resultMeta.innerHTML = [
            `<div class="reconstruct-result-id">Package ${escapeHtml(packageId || "—")}</div>`,
            roles.length
                ? `<div class="reconstruct-result-roles">Assets: ${escapeHtml(roles.join(", "))}</div>`
                : "",
            preferred
                ? `<div class="reconstruct-result-preferred">Preferred: ${escapeHtml(preferred)}</div>`
                : "",
        ].join("");

        renderWarnings(result.warnings);

        re.resultHandoff.innerHTML = packageId
            ? `Import this package into Rhino with the agent tool <code>rhino_2d_to_3d_import</code> (package id above).`
            : "";

        re.resultPanel.classList.remove("hidden");
    }
```

- [ ] **Step 4: Add styles**

Append to `styles.css`:

```css
.reconstruct-result { border: 1px solid var(--line); padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
.reconstruct-result-head { display: flex; gap: 1rem; align-items: flex-start; }
.reconstruct-result-thumb { width: 96px; height: 96px; object-fit: cover; border: 1px solid var(--line); }
.reconstruct-result-meta { font-size: 0.85rem; display: flex; flex-direction: column; gap: 0.25rem; }
.reconstruct-result-id { font-family: var(--font-mono); }
.reconstruct-warnings { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.reconstruct-warning { padding: 0.5rem 0.75rem; border-left: 4px solid var(--accent-red); font-size: 0.85rem; }
.reconstruct-warning.warning { border-left-color: var(--brass, #b8860b); }
.reconstruct-warning-code { display: inline-block; font-family: var(--font-mono); font-size: 0.7rem; opacity: 0.7; margin-right: 0.5rem; text-transform: uppercase; }
.reconstruct-warning-detail { display: block; opacity: 0.7; font-size: 0.78rem; margin-top: 0.2rem; }
.reconstruct-handoff { font-size: 0.85rem; opacity: 0.85; }
.reconstruct-handoff code { font-family: var(--font-mono); }
```

(If `--brass`/`--accent-red` are not defined in `:root`, the fallback `#b8860b` and an existing red variable apply; verify against the `:root` block and substitute the project's existing accent variables if different.)

- [ ] **Step 5: Manual verification (warnings are the key check)**

- A normal textured completion shows the package id, asset roles, preferred role, thumbnail, no warnings.
- **`result_missing_texture` render (primary path):** select, in the Task-6 job history, a completed job whose `job_result.warnings[]` already includes `result_missing_texture`, and confirm the warning renders with its headline. (`renderResult` lives inside the `Reconstruct` IIFE and is **not** console-callable — do not attempt a console injection of it.)
- **`result_missing_texture` render (fallback if no such job exists):** temporarily add `__debugRenderResult: renderResult` to the module's `return { … }` object, reload, call `Reconstruct.__debugRenderResult({ result_artifact_id:"00000000-0000-0000-0000-000000000000", result_available:true, package:{asset_roles:["model_obj"]}, warnings:[{code:"result_missing_texture", message:"no material or texture assets"}] })` from the console, confirm rendering, then **remove the `__debugRenderResult` line before committing**. Gate: `grep -n "__debugRenderResult" src/Rook/UI/Vision/Resources/app.js` must return nothing at commit time.
- **Geometry-only produces no texture warning** — submit geometry-only and confirm `warnings[]` is empty (it sets `TextureExpected=false`).
- Unknown future code falls back to its `message`.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-ui): result package panel + warnings rendering"
```

---

## Task 6: Lightweight job history

**Files:** `index.html`, `app.js`, `styles.css` (`Reconstruct` module).

**Interfaces:**
- Consumes: `reconstructionBridgeCall("list_jobs")` → `{ jobs:[{job_id, state, stage, result_available, updated_at}], applied_limit }`; `reconstructionBridgeCall("job_result")`; `renderResult` (Task 5); `formatTimestamp`.
- Produces: `re.jobsList`, `re.refreshJobsBtn`; fns `loadJobs()`, `renderJobs(jobs)`, `openJobResult(jobId)`.

- [ ] **Step 1: Add job-history markup**

In `index.html`, add after the result panel, still inside `.reconstruct-body`:

```html
                    <div class="reconstruct-history">
                        <div class="reconstruct-history-head">
                            <h2 class="reconstruct-history-title">Recent jobs</h2>
                            <button id="reconstruct-refresh-jobs" class="btn btn-secondary">Refresh</button>
                        </div>
                        <ul id="reconstruct-jobs-list" class="reconstruct-jobs"></ul>
                    </div>
```

- [ ] **Step 2: Extend the DOM cache**

Add to `cacheEls()`:

```javascript
        re.jobsList = $("reconstruct-jobs-list");
        re.refreshJobsBtn = $("reconstruct-refresh-jobs");
```

- [ ] **Step 3: Implement job list**

Add inside the module (above `return`):

```javascript
    async function loadJobs() {
        try {
            const data = await reconstructionBridgeCall("list_jobs", {});
            renderJobs(Array.isArray(data.jobs) ? data.jobs : []);
        } catch (e) {
            re.jobsList.innerHTML = `<li class="reconstruct-job empty">${escapeHtml(errorToText(e))}</li>`;
        }
    }

    function renderJobs(jobs) {
        if (jobs.length === 0) {
            re.jobsList.innerHTML = `<li class="reconstruct-job empty">No reconstruction jobs yet.</li>`;
            return;
        }
        re.jobsList.innerHTML = jobs.map(j => {
            const ts = j.updated_at ? formatTimestamp(j.updated_at) : "";
            const openable = j.state === "complete" && j.result_available;
            const cls = openable ? "reconstruct-job openable" : "reconstruct-job";
            return `<li class="${cls}" data-job-id="${escapeAttr(j.job_id)}" data-openable="${openable ? "1" : "0"}">
                <span class="reconstruct-job-state">${escapeHtml(j.state || "")}${j.stage ? " · " + escapeHtml(j.stage) : ""}</span>
                <span class="reconstruct-job-id">${escapeHtml(j.job_id)}</span>
                <span class="reconstruct-job-ts">${escapeHtml(ts)}</span>
            </li>`;
        }).join("");
    }

    async function openJobResult(jobId) {
        try {
            showReconstructStatus(`Loading package for ${jobId}…`, "info");
            const result = await reconstructionBridgeCall("job_result", { job_id: jobId });
            renderResult(result);
            showReconstructStatus("Package loaded.", "success");
        } catch (e) {
            showReconstructStatus(errorToText(e), "error");
        }
    }
```

- [ ] **Step 4: Wire events + load on enter**

Extend `wireEvents()`:

```javascript
        re.refreshJobsBtn.addEventListener("click", loadJobs);
        re.jobsList.addEventListener("click", (e) => {
            const li = e.target.closest("li.reconstruct-job");
            if (li && li.dataset.openable === "1") openJobResult(li.dataset.jobId);
        });
```

Extend `onEnter()` to also load jobs:

```javascript
    async function onEnter() {
        await loadModels();
        renderSource();
        await loadJobs();
    }
```

- [ ] **Step 5: Add styles**

Append to `styles.css`:

```css
.reconstruct-history { display: flex; flex-direction: column; gap: 0.5rem; }
.reconstruct-history-head { display: flex; align-items: center; justify-content: space-between; }
.reconstruct-history-title { font-size: 0.95rem; margin: 0; }
.reconstruct-jobs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.reconstruct-job { display: grid; grid-template-columns: 1fr 1.4fr auto; gap: 0.75rem; padding: 0.45rem 0.5rem; border-bottom: 1px solid var(--line); font-size: 0.82rem; align-items: center; }
.reconstruct-job.openable { cursor: pointer; }
.reconstruct-job.openable:hover { background: rgba(0,0,0,0.04); }
.reconstruct-job-id { font-family: var(--font-mono); opacity: 0.7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reconstruct-job-ts { opacity: 0.6; }
.reconstruct-job.empty { display: block; opacity: 0.6; }
```

- [ ] **Step 6: Manual verification**

Entering the view lists recent jobs; Refresh re-fetches; clicking a completed (`result_available`) job loads its package into the result panel (with warnings); in-flight/failed rows are not clickable.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-ui): lightweight job history"
```

---

## Task 7: "Send to 3D" becomes a shortcut; remove the duplicate modal submit path

**Files:** `index.html` (gallery modal), `app.js` (modal handlers + `Reconstruct.presetSource`).

**Interfaces:**
- Consumes: `modalArtifact`, `canReconstructArtifact`, `switchView`, `closeModal`.
- Produces: `Reconstruct.presetSource(artifact)` (fully implemented); deletes `reconstructCurrentArtifact`, `pollReconstructionJob`, `setReconstructionStatus`, `clearReconstructionStatus`, and the `reconstructionJobs` global.

- [ ] **Step 1: Implement `presetSource` in the Reconstruct module**

In `app.js`, replace the Task-2 stub `function presetSource(_artifact){ /* Task 7 */ }` with a real implementation, and export it (it's already in the `return`):

```javascript
    function presetSource(artifact) {
        if (!artifact) return;
        const imageRole = (artifact.files || []).some(f => f.role === "image") ? "image" : "image";
        source = {
            artifact_id: artifact.artifact_id,
            role: imageRole,
            previewSrc: `/blob/${artifact.artifact_id}/image`,
            label: (artifact.metadata && artifact.metadata.prompt) || artifact.kind || artifact.artifact_id,
        };
        switchView("reconstruct");
        renderSource();
    }
```

- [ ] **Step 2: Rewire the gallery modal button**

In `app.js`, find the modal reconstruct wiring (~line 2281):

```javascript
    el.modalReconstructBtn?.addEventListener("click", () => reconstructCurrentArtifact());
```

Replace with:

```javascript
    el.modalReconstructBtn?.addEventListener("click", () => {
        if (modalArtifact && canReconstructArtifact(modalArtifact)) {
            const artifact = modalArtifact;
            closeModal();
            Reconstruct.presetSource(artifact);
        }
    });
```

- [ ] **Step 3: Delete the v0 modal submit path**

In `app.js`, delete these now-unused functions entirely: `reconstructCurrentArtifact` (~1605), `pollReconstructionJob` (~1631), `setReconstructionStatus` (~1657), `clearReconstructionStatus` (~1667). Also delete the `let reconstructionJobs = new Map();` global (~line 104). Keep `canReconstructArtifact` (reused in Step 2) and `reconstructionBridgeCall` (reused by the module).

Remove the now-dead references to `clearReconstructionStatus()` in `openArtifactModal` (~1555) and `closeModal` (~1570), and the `el.modalReconstructionStatus` usages — but **keep** `el.modalReconstructBtn` show/hide gating in `openArtifactModal` (the button still gates on `canReconstructArtifact`). Specifically, in `openArtifactModal`, delete the line `clearReconstructionStatus();`; in `closeModal`, delete the line `clearReconstructionStatus();`.

- [ ] **Step 4: Remove the dead modal status strip + element cache**

In `index.html`, delete the modal status strip line (~784):

```html
                    <div id="modal-reconstruction-status" class="reconstruction-status hidden"></div>
```

In `app.js`, delete the element cache line (~2161):

```javascript
    el.modalReconstructionStatus = $("modal-reconstruction-status");
```

Leave the `modal-reconstruct-btn` markup and its `el.modalReconstructBtn` cache in place (still used as the shortcut trigger). The `.reconstruction-status` / `.reconstruction-import-hint` CSS rules in `styles.css` are now unused; delete those two rule blocks to avoid dead CSS.

- [ ] **Step 5: Grep for stragglers**

Run:
```bash
grep -nE "reconstructCurrentArtifact|pollReconstructionJob|setReconstructionStatus|clearReconstructionStatus|reconstructionJobs|modal-reconstruction-status|reconstruction-import-hint" src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/styles.css
```
Expected: no matches. (If any remain, remove them — there must be exactly one reconstruction submit path: `Reconstruct.submit`.)

- [ ] **Step 6: Manual verification**

From the Gallery, open an image artifact and click "Send to 3D": the modal closes, the Reconstruct view opens with that image preselected as the source, and submitting uses the chosen model/output mode. There is no second hardcoded Hunyuan submit anywhere.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "refactor(reconstruction-ui): make Send-to-3D a shortcut; remove duplicate v0 submit path"
```

---

## Task 8: Full-suite verification + manual checklist

**Files:** none (verification only).

- [ ] **Step 1: Full managed test suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: all green; no "Deployed Rook.rhp" tripwire (Debug skips the `%AppData%` deploy).

- [ ] **Step 2: Blob-route verification (spec §10)**

Confirm the existing `/blob/{artifact_id:D}/{role}` virtual resource serves reconstruction package assets from the shared `ArtifactStore`. Inspect `VisionWebSurface.cs` blob handler (~lines 670–770) and confirm it does not filter by artifact `kind`; the role-name regex `^[a-z0-9][a-z0-9_-]*$` accepts `thumbnail` / `model_glb` / `model_obj`. If the thumbnail does not render in manual smoke, the result panel still shows id/roles/warnings (the `onerror` hides the broken image) — record it as a follow-up, not a slice blocker.

- [ ] **Step 3: Manual verification checklist (record results)**

1. Reconstruct nav item appears (Video → **Reconstruct** → Gallery); switches view; no console errors.
2. Model list loads with a disabled "Select a model…" placeholder; submit without a model is rejected client-side.
3. Textured/geometry-only toggle is mutually exclusive; encodes `{enable_pbr:true}` xor `{enable_geometry:true}`.
4. Gallery "Send to 3D" preselects the source and navigates to Reconstruct (single submit path; no hardcoded Hunyuan submit remains — Task 7 grep clean).
5. Submit → poll → result package panel (id, roles, preferred, thumbnail).
6. **Warnings:** `result_missing_texture` renders (bare-package fixture / synthetic `job_result`); **geometry-only produces no texture warning**; unknown code falls back to its message.
7. Job history: lists recent jobs; Refresh works; click a completed job → loads package + warnings.

- [ ] **Step 4: Finish the branch**

Announce and use **superpowers:finishing-a-development-branch** to verify tests, present options, and (per prior-slice convention) push + open a ready PR into `main` — do not merge locally.

---

## Self-review

**Spec coverage:** §3 in-scope items all map to tasks — Reconstruct view (T2), source+model (T3), textured/geometry control (T4), submit/poll (T4), result+warnings (T5), job history (T6), Send-to-3D shortcut + one submit path (T7), bridge timeout (T1), import handoff (T5). Out-of-scope items (one-click import, Three.js, cost modal, preprocessing, cancel UI) are not implemented. §8 testing (C# routing pin + manual JS checklist) → T1 + T8. §10 verify gates → T8 Step 2 (blob), T1 (timeout reuse), T3 (models fields used).

**Placeholder scan:** no "TBD"/"add error handling"-style gaps; every code step shows real code. The Task 4 forward-reference to `renderResult`/`loadJobs` is explicitly handled (same-scope, runtime-only call; optional stub noted).

**Type/name consistency:** `Reconstruct` module exposes `{cacheEls, wireEvents, onEnter, presetSource}` (T2) — all used (T2/T3/T6/T7). `re.*` DOM cache names are consistent across tasks. `reconstructionBridgeCall(op, args)` signature consistent. C# `ReconstructionAsyncOps` name consistent between impl and test (T1). Warning codes match the backend (`result_artifact_missing`, `pbr_unsupported_by_model`, `result_missing_texture`).
